from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "04_prediction_plugins"
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from evidence_runtime import EvidenceGrade, EvidenceRecord, ReviewStatus, sha256_snapshot
from plugin_runtime.audit import build_registry, gate_exit_code, write_registry
from plugin_runtime.dlkcat import prepare_input as prepare_dlkcat_input
from plugin_runtime.schema import BenchmarkReport, PluginInput, UncertaintyReport
from plugin_runtime.unikp import assess_applicability, prepare_input


class PluginSchemaTests(unittest.TestCase):
    def test_dlkcat_rejects_multicomponent_smiles(self) -> None:
        request = PluginInput(
            request_id="multicomponent",
            capability="kcat_prediction",
            sequence="MKT",
            substrate_smiles="CCO.[Na+]",
        )
        with self.assertRaisesRegex(ValueError, "multi-component"):
            prepare_dlkcat_input(request)

    def test_unikp_reports_both_truncations(self) -> None:
        request = PluginInput(
            request_id="truncate",
            capability="kcat_prediction",
            sequence="A" * 1001,
            substrate_smiles="C" * 219,
        )
        sequence, tokens, transforms = prepare_input(request)
        self.assertEqual(len(sequence), 1000)
        self.assertEqual(len(tokens), 218)
        self.assertTrue(all(item.truncated for item in transforms))
        self.assertEqual(transforms[0].strategy, "head_500_tail_500")
        self.assertEqual(transforms[1].strategy, "head_109_tail_109")
        applicability = assess_applicability(transforms)
        self.assertEqual(applicability.assessment_status, "assessed")
        self.assertFalse(applicability.in_domain)
        self.assertTrue(applicability.ood)
        self.assertEqual(
            applicability.reasons,
            ("sequence_truncated", "substrate_smiles_tokens_truncated"),
        )

    def test_unikp_tree_member_interval_fields_are_serialized(self) -> None:
        report = UncertaintyReport(
            "available",
            "test tree interval",
            0.25,
            interval=(-1.0, 1.0),
            tree_member_count=100,
            tree_member_interval_log10=(-1.0, 1.0),
        )
        self.assertEqual(report.tree_member_count, 100)
        self.assertEqual(report.tree_member_interval_log10, (-1.0, 1.0))

    def test_unikp_benchmark_is_blocked_on_training_overlap_without_metrics(self) -> None:
        script = PLUGIN_ROOT / "UniKP" / "benchmark.py"
        spec = importlib.util.spec_from_file_location("unikp_benchmark", script)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.ASSETS = ()
        benchmark, readiness = module.build_manifests()
        module.validate_manifest(benchmark)
        module.validate_manifest(readiness)
        self.assertEqual(benchmark["status"], "blocked")
        self.assertFalse(benchmark["independent"])
        self.assertFalse(benchmark["metrics_published"])
        self.assertEqual(benchmark["metrics"], {})
        self.assertTrue(all(row["training_overlap"] for row in benchmark["datasets"]))
        self.assertTrue(all(len(row["sha256"]) == 64 for row in benchmark["datasets"] if row["exists"]))
        self.assertEqual(readiness["output_contract"]["ood_field"], "applicability.ood")
        self.assertEqual(readiness["output_contract"]["tree_member_interval_field"], "uncertainty.tree_member_interval_log10")

    def test_metrics_require_public_versioned_benchmark(self) -> None:
        with self.assertRaises(ValueError):
            BenchmarkReport(status="completed", metrics={"rmse": 0.2})
        report = BenchmarkReport(
            status="completed",
            public_reference=True,
            dataset_name="public-test",
            dataset_version="1",
            snapshot_sha256="a" * 64,
            metrics={"rmse": 0.2},
        )
        self.assertEqual(report.metrics["rmse"], 0.2)

    def test_missing_third_party_assets_block_gate_and_registry_is_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plugin_root = Path(directory)
            rows = build_registry(plugin_root)
            managed = [row for row in rows if row["plugin"] in {"CLEAN", "DLKcat", "UniKP"}]
            self.assertTrue(managed)
            self.assertTrue(all(row["status"] == "blocked" and row["gate_exit_code"] == 1 for row in managed))
            self.assertEqual(gate_exit_code(rows, {"CLEAN", "DLKcat", "UniKP"}), 1)
            registry = plugin_root / "registry.csv"
            write_registry(registry, rows)
            with registry.open("r", encoding="utf-8", newline="") as handle:
                parsed = list(csv.DictReader(handle))
            self.assertEqual(len(parsed), len(rows))
            self.assertIsInstance(json.loads(parsed[0]["required_assets_json"]), list)


class EvidenceSchemaTests(unittest.TestCase):
    def base_fields(self) -> dict[str, object]:
        return {
            "evidence_id": "ev-1",
            "candidate_id": "rxn-1",
            "source_database": "Rhea",
            "database_version": "2026-07-01",
            "source_accession": "RHEA:12345",
            "source_url": "https://www.rhea-db.org/rhea/12345",
            "snapshot_sha256": sha256_snapshot(b"raw response bytes"),
            "automated_grade": EvidenceGrade.C,
            "pmid": "12345678",
            "rhea_id": "RHEA:12345",
            "uniprot_accession": "P12345",
        }

    def test_automatic_ab_promotion_is_rejected(self) -> None:
        fields = self.base_fields()
        fields["automated_grade"] = EvidenceGrade.A
        with self.assertRaises(ValueError):
            EvidenceRecord(**fields)

    def test_manual_ab_requires_complete_approval_record(self) -> None:
        fields = self.base_fields()
        fields.update(
            final_grade=EvidenceGrade.A,
            review_status=ReviewStatus.APPROVED,
            reviewer="curator@example.org",
            reviewed_at="2026-07-17T12:00:00Z",
            review_note="Exact reaction and enzyme activity verified in the cited record.",
        )
        record = EvidenceRecord(**fields)
        self.assertEqual(record.to_dict()["final_grade"], "A")


if __name__ == "__main__":
    unittest.main()
