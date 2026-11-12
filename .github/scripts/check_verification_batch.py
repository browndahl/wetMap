"""Validate retained-window accounting and the existing 95% completeness SLO."""


def validate_batch(report: dict) -> None:
    batch = report.get("verificationBatch")
    if batch is None:  # Backwards-compatible report rollout.
        return
    if batch.get("scope") != "retained-valid-time-pairs":
        raise ValueError("Unknown verification completeness scope")
    names = (
        "eligiblePairs",
        "alreadyVerified",
        "planned",
        "attempted",
        "completed",
        "errors",
        "deferred",
        "rejectedForecasts",
    )
    if any(type(batch.get(name)) is not int or batch[name] < 0 for name in names):
        raise ValueError("Invalid verification accounting counts")
    if (
        batch["eligiblePairs"] != batch["alreadyVerified"] + batch["planned"]
        or batch["planned"] != batch["attempted"] + batch["deferred"]
        or batch["attempted"] != batch["completed"] + batch["errors"]
    ):
        raise ValueError("Inconsistent verification accounting")
    complete = (
        not batch["errors"] and not batch["deferred"] and not batch["rejectedForecasts"]
    )
    if type(batch.get("complete")) is not bool or batch["complete"] != complete:
        raise ValueError("False verification completeness claim")
    if batch["rejectedForecasts"]:
        raise ValueError("Verification forecast contracts were rejected")
    eligible = batch["eligiblePairs"]
    fraction = batch.get("coverageFraction")
    if not eligible:
        if fraction is not None:
            raise ValueError("Empty window must not claim perfect verification")
        return
    expected = (batch["alreadyVerified"] + batch["completed"]) / eligible
    if type(fraction) not in (int, float) or not abs(fraction - expected) <= 1e-6:
        raise ValueError("Invalid verification coverage fraction")
    if fraction < 0.95:
        raise ValueError(
            "Retained-window verification completeness is below the existing 95% SLO"
        )
