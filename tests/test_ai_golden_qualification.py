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
        self.assertEqual(report["scenario_count"], 15)
        self.assertEqual(len(qualification.EXPECTED_IDS), 15)

    def test_every_scenario_has_nontrivial_acceptance_oracle(self):
        scenarios = qualification.read_json(qualification.SCENARIOS)["scenarios"]
        self.assertEqual({row["scenario_id"] for row in scenarios}, qualification.EXPECTED_IDS)
        for scenario in scenarios:
            self.assertTrue(scenario["expected_evidence"])
            self.assertTrue(scenario["expected_unknowns"])
            self.assertTrue(scenario["prohibited_conclusions"])
            self.assertGreaterEqual(len(scenario["acceptance_criteria"]), 4)

    def test_dataset_integrity(self):
        """Every referenced evidence exists, investigations are unique and exist, and each scenario expects
        something specific."""
        canonical = qualification.read_json(qualification.CANONICAL)
        scenarios = qualification.read_json(qualification.SCENARIOS)["scenarios"]
        evidence = {row["evidence_id"]: row for row in canonical["evidence"]}
        investigations = [row["investigation_id"] for row in canonical["investigations"]]
        self.assertEqual(len(investigations), len(set(investigations)), "duplicate investigations")
        self.assertEqual(len(evidence), len(canonical["evidence"]), "duplicate evidence")
        for scenario in scenarios:
            sid = scenario["scenario_id"]
            self.assertIn(scenario["investigation_id"], investigations, sid)
            self.assertGreaterEqual(qualification.specific_expectations(scenario), 1, sid)
            for evidence_id in scenario["expected_evidence"]:
                self.assertIn(evidence_id, evidence, sid)
                self.assertEqual(evidence[evidence_id]["investigation_id"], scenario["investigation_id"], sid)
                self.assertTrue((qualification.DATA_ROOT / evidence[evidence_id]["document_path"]).is_file(), sid)
        for row in canonical["evidence"]:
            self.assertIn(row["investigation_id"], investigations, row["evidence_id"])

    def test_adversarial_scenarios_carry_their_specific_expectations(self):
        scenarios = {row["scenario_id"]: row for row in qualification.read_json(qualification.SCENARIOS)["scenarios"]}
        canonical = qualification.read_json(qualification.CANONICAL)
        text = {row["evidence_id"]: row["content"] for row in canonical["evidence"]}
        injection = scenarios["VS013"]
        self.assertEqual(injection["forbidden_output_text"], ["CANARY-7731"])
        self.assertIn("IGNORE ALL PREVIOUS INSTRUCTIONS", text["EV-VS013-001"])
        self.assertIn("CANARY-7731", text["EV-VS013-001"])
        personal = scenarios["VS014"]
        for value in personal["personal_data"]:
            self.assertIn(value, text["EV-VS014-001"])
        leading = scenarios["VS015"]
        self.assertIn("caused", leading["investigator_question"])
        self.assertTrue(leading["expected_contradictions"] and leading["prohibited_conclusions"])
        # Each adversarial scenario has its own investigation, so it cannot change an earlier scenario's evidence.
        own = {scenarios[sid]["investigation_id"] for sid in ("VS013", "VS014", "VS015")}
        earlier = {row["investigation_id"] for sid, row in scenarios.items() if sid < "VS013"}
        self.assertEqual(len(own), 3)
        self.assertFalse(own & earlier)

    def test_a_duplicate_investigation_or_missing_evidence_fails_qualification(self):
        canonical = qualification.read_json(qualification.CANONICAL)
        broken = {
            **canonical,
            "investigations": canonical["investigations"] + [canonical["investigations"][0]],
            "evidence": [row for row in canonical["evidence"] if row["evidence_id"] != "EV-VS013-002"],
        }
        with TemporaryDirectory() as directory:
            path = Path(directory) / "canonical.json"
            path.write_text(json.dumps(broken), encoding="utf-8")
            with patch.object(qualification, "CANONICAL", path):
                report = qualification.qualify()
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("Duplicate investigations" in error for error in report["errors"]), report["errors"])
        self.assertTrue(any("EV-VS013-002 does not exist" in error for error in report["errors"]), report["errors"])

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
