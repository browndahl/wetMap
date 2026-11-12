import io
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from wetmap_worker.retention import expired_image, retire_images

NOW = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)
OLD = "nowcast/dk.com.202611090000.500_max-plus-05m.webp"
ACTIVE = "nowcast/dk.com.202611121155.500_max-plus-05m.webp"


def object_entry(key=OLD, uploaded=None):
    return {"Key": key, "Size": 100, "LastModified": uploaded or NOW - timedelta(days=3)}


def client_for(entries, manifests=None):
    client = Mock()
    active = iter(manifests or [[ACTIVE]] * 10)
    client.get_object.side_effect = lambda **kwargs: {
        "Body": io.BytesIO(
            json.dumps({"frames": [{"url": "/" + key} for key in next(active)]}).encode()
        )
    }
    client.get_paginator.return_value.paginate.return_value = [{"Contents": entries}]
    client.delete_objects.side_effect = lambda **kwargs: {"Deleted": kwargs["Delete"]["Objects"]}
    return client


def test_dry_run_never_deletes_and_counts_only_expired_derived_images():
    entries = [
        object_entry(),
        object_entry(ACTIVE),
        object_entry("nowcast/verification-history.json"),
        object_entry("nowcast/point-risk-1.bin"),
        object_entry("frames/dk.com.202611090000.500_max.webp"),
        object_entry(OLD.replace("05m", "07m")),
        object_entry(OLD, NOW - timedelta(hours=1)),
    ]
    client = client_for(entries)
    report = retire_images(client, "bucket", now=NOW)
    assert report["candidateCount"] == 1
    assert report["candidateBytes"] == 100
    client.delete_objects.assert_not_called()


def test_apply_deletes_exact_allowlist_and_preserves_active_and_history():
    client = client_for(
        [
            object_entry(),
            object_entry(ACTIVE),
            object_entry("nowcast/verification-cubes/cube-01.npz"),
        ]
    )
    report = retire_images(client, "bucket", apply=True, now=NOW)
    assert report["deletedCount"] == 1
    assert report["deletedBytes"] == 100
    assert client.delete_objects.call_args.kwargs["Delete"]["Objects"] == [{"Key": OLD}]


def test_rechecks_active_manifest_immediately_before_deleting():
    client = client_for([object_entry()], [[ACTIVE], [OLD]])
    report = retire_images(client, "bucket", apply=True, now=NOW)
    assert report["deletedCount"] == 0
    client.delete_objects.assert_not_called()


def test_missing_or_invalid_manifest_fails_closed():
    client = client_for([object_entry()], [[]])
    with pytest.raises(ValueError, match="active nowcast manifest"):
        retire_images(client, "bucket", apply=True, now=NOW)
    client.delete_objects.assert_not_called()


def test_deletion_budget_is_checked_before_any_mutation():
    client = client_for([object_entry()])
    with pytest.raises(ValueError, match="deletion budget"):
        retire_images(client, "bucket", apply=True, max_delete=0, now=NOW)
    client.delete_objects.assert_not_called()


def test_partial_provider_error_is_not_reported_as_success():
    client = client_for([object_entry()])
    client.delete_objects.side_effect = None
    client.delete_objects.return_value = {"Errors": [{"Key": OLD, "Code": "InternalError"}]}
    report = retire_images(client, "bucket", apply=True, now=NOW)
    assert report["deletedCount"] == 0
    assert report["errors"] == [{"key": OLD, "code": "InternalError"}]


def test_both_upload_and_forecast_valid_time_must_exceed_48_hours():
    cutoff = NOW - timedelta(hours=48)
    assert not expired_image(object_entry(uploaded=cutoff), cutoff)
    assert not expired_image(object_entry(ACTIVE), cutoff)
    assert not expired_image(
        object_entry("nowcast/dk.com.202699990000.500_max-plus-05m.webp"), cutoff
    )


def test_once_per_day_skips_listing_and_deletion(tmp_path, monkeypatch):
    from wetmap_worker import retention

    client = Mock()
    client.get_object.return_value = {
        "Body": io.BytesIO(
            json.dumps({"completedAt": datetime.now(timezone.utc).isoformat()}).encode()
        )
    }
    monkeypatch.setattr(retention, "_r2_client", lambda: client)
    monkeypatch.setenv("R2_BUCKET", "bucket")
    monkeypatch.setattr(
        "sys.argv",
        ["retention", "--apply", "--once-per-day", "--report", str(tmp_path / "report.json")],
    )
    assert retention.main() == 0
    client.get_paginator.assert_not_called()
    client.delete_objects.assert_not_called()
