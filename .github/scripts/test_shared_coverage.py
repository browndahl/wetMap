import unittest

from check_shared_coverage import validate_shared_coverage


class SharedCoverageChecks(unittest.TestCase):
    def report(self):
        score = {
            "validPixels": 4,
            "hits": 1,
            "misses": 1,
            "falseAlarms": 1,
            "correctNegatives": 1,
            "precision": 0.5,
            "recall": 0.5,
            "criticalSuccessIndex": 0.3333,
        }
        return {
            "comparisonAudit": {
                "comparisonVersion": "shared-coverage-v2",
                "mode": "shadow-only",
                "canAffectForecasts": False,
                "promotionEnabled": False,
                "thresholdDbz": 20,
                "failedPairCount": 0,
                "sampleCount": 1,
                "cohorts": [
                    {
                        "algorithmVersion": "v1",
                        "sampleCount": 1,
                        "byLeadMinutes": [
                            {
                                "sampleCount": 1,
                                "forecast": dict(score),
                                "persistence": dict(score),
                                "coverage": {
                                    "commonValidPixels": 4,
                                    "observedValidPixels": 5,
                                    "commonFractionOfObserved": 0.8,
                                },
                            }
                        ],
                        "candidates": [],
                    }
                ],
            }
        }

    def test_valid_shadow_and_legacy_reports_pass(self):
        validate_shared_coverage({})
        validate_shared_coverage(self.report())

    def test_diagnostic_cannot_enable_promotion(self):
        report = self.report()
        report["comparisonAudit"]["promotionEnabled"] = True
        with self.assertRaisesRegex(ValueError, "shadow-only"):
            validate_shared_coverage(report)

    def test_different_denominators_are_rejected(self):
        report = self.report()
        report["comparisonAudit"]["cohorts"][0]["byLeadMinutes"][0]["persistence"][
            "validPixels"
        ] = 5
        with self.assertRaisesRegex(ValueError, "same coverage"):
            validate_shared_coverage(report)

    def test_failed_pairs_and_wrong_counts_are_visible(self):
        report = self.report()
        report["comparisonAudit"]["failedPairCount"] = 1
        with self.assertRaises(ValueError):
            validate_shared_coverage(report)
        report = self.report()
        report["comparisonAudit"]["sampleCount"] = 2
        with self.assertRaises(ValueError):
            validate_shared_coverage(report)
