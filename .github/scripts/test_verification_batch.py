import unittest

from check_verification_batch import validate_batch


class VerificationCompletenessTests(unittest.TestCase):
    def report(self, **overrides):
        return {
            "verificationBatch": {
                "scope": "retained-valid-time-pairs",
                "eligiblePairs": 100,
                "alreadyVerified": 90,
                "planned": 10,
                "attempted": 10,
                "completed": 10,
                "errors": 0,
                "deferred": 0,
                "rejectedForecasts": 0,
                "complete": True,
                "coverageFraction": 1.0,
                **overrides,
            }
        }

    def test_full_and_retry_accounting_pass(self):
        validate_batch(self.report())
        validate_batch(
            self.report(alreadyVerified=100, planned=0, attempted=0, completed=0)
        )
        validate_batch({})

    def test_partial_execution_is_not_reported_as_complete(self):
        with self.assertRaisesRegex(ValueError, "False verification"):
            validate_batch(self.report(completed=5, errors=5, coverageFraction=0.95))

    def test_existing_slo_is_enforced_not_relaxed(self):
        with self.assertRaisesRegex(ValueError, "95%"):
            validate_batch(
                self.report(
                    completed=0, errors=10, complete=False, coverageFraction=0.90
                )
            )
        validate_batch(
            self.report(completed=5, errors=5, complete=False, coverageFraction=0.95)
        )

    def test_empty_and_invalid_inputs_cannot_claim_coverage(self):
        with self.assertRaises(ValueError):
            validate_batch(self.report(eligiblePairs=0))
        with self.assertRaises(ValueError):
            validate_batch(self.report(coverageFraction=float("nan")))
