"""Release-gate tests for the controlled AI golden dataset."""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import scripts.qualify_ai_golden_dataset as qualification


class AIGoldenQualificationTests(unittest.TestCase):
    def test_controlled_dataset_is_qualified(self):
        report = qualification.qualify()
        self.assertEqual(report["status"], "PASS", report["errors"])
        self.assertEqual(report["qualification_status"], "QUALIFIED_FOR_INTERNAL_MVP")
        self.assertEqual(report["scenario_count"], 12)

    def test_every_scenario_has_nontrivial_acceptance_oracle(self):
        scenarios = qualification.read_json(qualification.SCENARIOS)["scenarios"]
        self.assertEqual({row["scenario_id"] for row in scenarios}, qualification.EXPECTED_IDS)
        for scenario in scenarios:
            self.assertTrue(scenario["expected_evidence"])
            self.assertTrue(scenario["expected_unknowns"])
            self.assertTrue(scenario["prohibited_conclusions"])
            self.assertGreaterEqual(len(scenario["acceptance_criteria"]), 4)

    def test_changed_lock_hash_fails_closed(self):
        with TemporaryDirectory() as directory:
            bad_lock = Path(directory) / "qualification.json"
            lock = qualification.read_json(qualification.LOCK)
            lock["hashes"]["scenario_index_sha256"] = "0" * 64
            bad_lock.write_text(json.dumps(lock), encoding="utf-8")
            with patch.object(qualification, "LOCK", bad_lock):
                report = qualification.qualify()
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("Qualification lock does not match the controlled dataset", report["errors"])


if __name__ == "__main__":
    unittest.main()
