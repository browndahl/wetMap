import unittest

from audit_public_quality import audit_report


def score(
    *,
    lead: int,
    hits: int,
    misses: int,
    false_alarms: int,
    persistence_csi: float,
) -> dict:
    denominator = hits + misses + false_alarms
    csi = hits / denominator if denominator else None
    return {
        "basedOnObservedAt": "2026-10-20T10:00:00Z",
        "predictedAt": f"2026-10-20T10:{lead:02d}:00Z",
        "observedAt": f"2026-10-20T10:{lead:02d}:00Z",
        "leadMinutes": lead,
        "scores": [
            {
                "thresholdDbz": 20,
                "hits": hits,
                "misses": misses,
                "falseAlarms": false_alarms,
                "correctNegatives": 100,
                "criticalSuccessIndex": csi,
                "precision": hits / (hits + false_alarms),
                "recall": hits / (hits + misses),
                "falseAlarmRate": false_alarms / (false_alarms + 100),
                "persistenceCriticalSuccessIndex": persistence_csi,
                "criticalSuccessIndexSkill": csi - persistence_csi,
                "meanAbsoluteErrorDbz": 1.25,
            }
        ],
    }


class PublicQualityAuditTests(unittest.TestCase):
    def test_recomputes_scores_and_alignment_independently(self) -> None:
        report = {
            "results": [score(lead=15, hits=30, misses=10, false_alarms=10, persistence_csi=0.5)]
        }

        audit = audit_report(report, minimum_pairs=1)

        self.assertEqual(audit["pairCount"], 1)
        self.assertEqual(audit["alignment"]["outsideToleranceCount"], 0)
        self.assertEqual(audit["metricRecalculation"]["mismatchCount"], 0)
        self.assertEqual(audit["persistence"]["comparisonCount"], 1)

    def test_detects_metric_tampering(self) -> None:
        entry = score(lead=15, hits=30, misses=10, false_alarms=10, persistence_csi=0.5)
        entry["scores"][0]["precision"] = 0.1

        audit = audit_report({"results": [entry]}, minimum_pairs=1)

        self.assertEqual(audit["metricRecalculation"]["mismatchCount"], 1)
        self.assertEqual(audit["status"], "fail")

    def test_exposes_pooled_vs_pair_weighted_skill_difference(self) -> None:
        report = {
            "results": [
                score(
                    lead=15,
                    hits=900,
                    misses=50,
                    false_alarms=50,
                    persistence_csi=0.85,
                ),
                score(
                    lead=15,
                    hits=1,
                    misses=9,
                    false_alarms=10,
                    persistence_csi=0.20,
                ),
            ]
        }

        audit = audit_report(report, minimum_pairs=2)
        horizon = audit["horizons"]["15"]

        self.assertGreater(horizon["pooledCriticalSuccessIndex"], 0.85)
        self.assertLess(horizon["meanPairSkillOverPersistence"], 0)
        self.assertTrue(horizon["aggregationDirectionDiffers"])

    def test_fails_when_evidence_floor_is_not_met(self) -> None:
        report = {
            "results": [score(lead=15, hits=30, misses=10, false_alarms=10, persistence_csi=0.5)]
        }

        audit = audit_report(report, minimum_pairs=50)

        self.assertEqual(audit["status"], "fail")
        self.assertIn("minimum-pairs", audit["failures"])

    def test_recomputes_reported_horizon_far_from_counts(self) -> None:
        entry = score(lead=15, hits=30, misses=10, false_alarms=10, persistence_csi=0.5)
        report = {
            "results": [entry],
            "observatory": {
                "horizons": [
                    {
                        "targetLeadMinutes": 15,
                        "sampleCount": 1,
                        "precision": 0.75,
                        "recall": 0.75,
                        "criticalSuccessIndex": 0.6,
                        "falseAlarmRate": 0.1,
                        "missRate": 0.25,
                    }
                ]
            },
        }

        audit = audit_report(report, minimum_pairs=1)

        self.assertEqual(audit["horizonRecalculation"]["mismatchCount"], 1)
        self.assertEqual(audit["horizonRecalculation"]["mismatches"][0]["metric"], "falseAlarmRate")
        self.assertEqual(audit["status"], "fail")


if __name__ == "__main__":
    unittest.main()
