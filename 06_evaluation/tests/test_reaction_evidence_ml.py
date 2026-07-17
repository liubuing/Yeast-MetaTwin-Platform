from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "08_runtime"))

from reaction_evidence_ml_utils import (  # noqa: E402
    assign_unified_group_splits,
    audit_split_leakage,
    evaluate_pu_split,
    load_joblib_verified,
    select_positive_recall_threshold,
    sha256_file,
    verify_model_artifact,
)


class UnifiedSplitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.compounds = pd.DataFrame(
            [
                {"model_metabolite_id": "a_c", "inchikey": "AAAA", "compound_uid": "A"},
                {"model_metabolite_id": "a_m", "inchikey": "AAAA", "compound_uid": "A2"},
                {"model_metabolite_id": "b_c", "smiles": "CCO", "compound_uid": "B"},
                {"model_metabolite_id": "c_c", "metanetx_id": "MNXM3", "compound_uid": "C"},
            ]
        ).fillna("")

    def test_positive_and_unlabeled_share_one_group_for_homology(self) -> None:
        rows = [
            {"model_reaction_id": "positive", "label": 1, "orfs": "P1", "stoichiometry_json": '{"a_c": -1, "b_c": 1}'},
            {"model_reaction_id": "unlabeled", "label": 0, "orfs": "P2", "stoichiometry_json": '{"a_c": -1, "c_c": 1}'},
        ]
        grouped = assign_unified_group_splits(rows, self.compounds, {"P1": "CLUSTER", "P2": "CLUSTER"})
        self.assertEqual(grouped[0]["split_group_key"], grouped[1]["split_group_key"])
        self.assertEqual(grouped[0]["model_split"], grouped[1]["model_split"])
        self.assertNotIn("negative:", grouped[1]["split_group_key"])

    def test_compartment_variants_share_normalized_reaction_group(self) -> None:
        rows = [
            {"model_reaction_id": "r1", "label": 1, "stoichiometry_json": '{"a_c": -1, "b_c": 1}'},
            {"model_reaction_id": "r2", "label": 0, "stoichiometry_json": '{"a_m": -1, "b_c": 1}'},
        ]
        grouped = assign_unified_group_splits(rows, self.compounds, {})
        self.assertEqual(grouped[0]["normalized_reaction_signature"], grouped[1]["normalized_reaction_signature"])
        self.assertEqual(grouped[0]["split_group_key"], grouped[1]["split_group_key"])
        self.assertEqual(audit_split_leakage(pd.DataFrame(grouped))["status"], "pass")

    def test_audit_detects_cross_split_homology(self) -> None:
        frame = pd.DataFrame(
            [
                {"model_split": "train", "split_group_key": "g1", "protein_homology_clusters": "C1", "normalized_reaction_signature": "r1", "substrate_structure_signature": "s1"},
                {"model_split": "test", "split_group_key": "g2", "protein_homology_clusters": "C1", "normalized_reaction_signature": "r2", "substrate_structure_signature": "s2"},
            ]
        )
        audit = audit_split_leakage(frame)
        self.assertEqual(audit["status"], "fail")
        self.assertEqual(audit["dimensions"]["protein_homology_clusters"]["cross_split_values"], 1)


class EvaluationTests(unittest.TestCase):
    def test_threshold_is_selected_from_labeled_positive_recall(self) -> None:
        selection = select_positive_recall_threshold([1, 1, 1, 0], [0.9, 0.8, 0.2, 0.7], target_recall=2 / 3)
        self.assertAlmostEqual(selection["value"], 0.8)
        self.assertGreaterEqual(selection["achieved_labeled_positive_recall"], 2 / 3)

    def test_metrics_include_group_bootstrap_and_calibration_curve(self) -> None:
        labels = np.array([1, 1, 0, 0, 1, 0])
        probabilities = np.array([0.9, 0.7, 0.6, 0.1, 0.8, 0.2])
        result = evaluate_pu_split("test", labels, probabilities, ["a", "a", "b", "b", "c", "d"], 0.65, bootstrap_samples=40)
        self.assertIn("observed_label_average_precision", result["metrics"])
        self.assertIn("observed_label_brier_score", result["metrics"])
        self.assertIn("observed_label_average_precision", result["bootstrap_95_ci"])
        self.assertIn("observed_label_expected_calibration_error", result["bootstrap_95_ci"])
        self.assertTrue(result["calibration_curve"])
        self.assertEqual(result["groups"], 4)


class ManifestAndLoadTests(unittest.TestCase):
    def test_verified_load_rejects_tampered_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model_path = root / "model.joblib"
            manifest_path = root / "manifest.json"
            joblib.dump({"model_version": "v1", "model": "sentinel"}, model_path)
            manifest_path.write_text(json.dumps({"model_version": "v1", "artifact": {"sha256": sha256_file(model_path)}}), encoding="utf-8")
            self.assertEqual(verify_model_artifact(model_path, manifest_path)["model_version"], "v1")
            loaded = load_joblib_verified(model_path, manifest_path, ["model"])
            self.assertEqual(loaded["model"], "sentinel")
            with model_path.open("ab") as handle:
                handle.write(b"tampered")
            with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
                load_joblib_verified(model_path, manifest_path, ["model"])

    def test_added_schemas_are_valid_json(self) -> None:
        for path in [
            ROOT / "03_models" / "reaction_evidence_model_manifest.schema.json",
            ROOT / "06_evaluation" / "phase2_reaction_evidence_evaluation.schema.json",
        ]:
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["$schema"], "https://json-schema.org/draft/2020-12/schema")

    def test_versioned_manifests_validate_against_schema(self) -> None:
        schema = json.loads((ROOT / "03_models" / "reaction_evidence_model_manifest.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        manifests = sorted((ROOT / "03_models").glob("*reaction_evidence*_manifest_v2.json"))
        self.assertEqual(len(manifests), 2)
        for path in manifests:
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(list(Draft202012Validator(schema).iter_errors(payload)), [], path.name)

    def test_manifest_schema_rejects_missing_security_policy(self) -> None:
        schema = json.loads((ROOT / "03_models" / "reaction_evidence_model_manifest.schema.json").read_text(encoding="utf-8"))
        manifest_path = ROOT / "03_models" / "phase2_reaction_evidence_baseline_v1_manifest_v2.json"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        del payload["serialization_security"]
        errors = list(Draft202012Validator(schema).iter_errors(payload))
        self.assertTrue(any(error.validator == "required" for error in errors))


if __name__ == "__main__":
    unittest.main()
