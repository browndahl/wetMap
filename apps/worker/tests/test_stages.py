import json
import logging
from unittest.mock import Mock

import pytest

from wetmap_worker import stages


def test_stage_reports_static_timing_and_passes_arguments_and_result_unchanged(monkeypatch, caplog):
    ticks = iter([10, 10.125])
    monkeypatch.setattr(stages, "perf_counter", lambda: next(ticks))
    secret = object()
    result = {"private-sentinel": "not logged"}
    operation = Mock(return_value=result)
    with caplog.at_level(logging.INFO):
        assert stages.run_stage("verification-score", operation, secret, token=secret) is result
    operation.assert_called_once_with(secret, token=secret)
    assert [json.loads(record.message) for record in caplog.records] == [
        {"event": "worker.stage.started", "stage": "verification-score"},
        {"event": "worker.stage.completed", "stage": "verification-score", "durationMs": 125},
    ]
    assert "private-sentinel" not in caplog.text
    assert "token" not in caplog.text


@pytest.mark.parametrize("error", [TimeoutError("private-sentinel"), SystemExit(17)])
def test_stage_reraises_same_failure_without_raw_error_or_success(monkeypatch, caplog, error):
    ticks = iter([10, 10.75])
    monkeypatch.setattr(stages, "perf_counter", lambda: next(ticks))
    with caplog.at_level(logging.INFO), pytest.raises(type(error)) as raised:
        stages.run_stage("verification-state-load", Mock(side_effect=error))
    assert raised.value is error
    report = json.loads(caplog.records[-1].message)
    assert report == {
        "event": "worker.stage.failed",
        "stage": "verification-state-load",
        "durationMs": 750,
    }
    assert "private-sentinel" not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.parametrize("name", ["private-sentinel", None, [], "verification-state-load\nraw"])
def test_unknown_stage_cannot_become_log_data(caplog, name):
    operation = Mock()
    with pytest.raises(ValueError, match="^unsupported-worker-stage$"):
        stages.run_stage(name, operation)
    operation.assert_not_called()
    assert not caplog.records


def test_cli_instruments_every_registered_derived_boundary():
    import ast
    from pathlib import Path

    from wetmap_worker import cli

    tree = ast.parse(Path(cli.__file__).read_text())
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "run_stage"
    ]
    assert {node.args[0].value for node in calls} == stages.STAGES
    assert len(calls) == len(stages.STAGES)
