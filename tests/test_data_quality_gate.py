from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "08_runtime"
CLI = RUNTIME / "data_quality_gate.py"
sys.path.insert(0, str(RUNTIME))

import data_quality_gate as gate  # noqa: E402


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_shipped_gate_is_machine_readable_and_strict_target_subset_passes(tmp_path: Path) -> None:
    summary, output = gate.run_gate(ROOT, ROOT / "09_configs" / "data_quality_gate.json", tmp_path)
    schema = json.loads((ROOT / "09_configs" / "data_quality_gate_summary.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(summary)
    assert summary["status"] == "passed"
    assert summary["strict_subsets"][0]["status"] == "passed"
    assert summary["counts"]["structures_missing"] > 0
    assert summary["counts"]["structures_unresolved"] == (
        summary["counts"]["structures_missing"] + summary["counts"]["structures_parse_failed"]
    )
    with (output / "metabolite_structure_quality.csv").open(encoding="utf-8", newline="") as handle:
        missing = [row for row in csv.DictReader(handle) if row["structure_status"] == "missing"]
    assert missing
    assert all(row["reason_code"] and row["status"] and row["source"] and row["review"] for row in missing)


def test_reaction_governance_exposes_all_required_states() -> None:
    rows = gate.build_reaction_rows(
        [{
            "model_reaction_id": "R1", "reaction_name": "test", "formula_balanced": "False",
            "charge_balanced": "True", "missing_formula_metabolites": "M1",
            "unparsable_formula_metabolites": "M2",
        }]
    )
    assert rows[0]["mass_balance_status"] == "unbalanced"
    assert rows[0]["charge_balance_status"] == "balanced"
    assert rows[0]["missing_formula_status"] == "present"
    assert rows[0]["structure_parse_status"] == "failed"
    assert rows[0]["external_mapping_status"] == "pending"
    assert rows[0]["manual_review_status"] == "required"


def test_cli_returns_nonzero_without_marking_unresolved_completed(tmp_path: Path) -> None:
    compounds = tmp_path / "compounds.csv"
    balances = tmp_path / "balances.csv"
    target = tmp_path / "target.json"
    config = tmp_path / "gate.json"
    output = tmp_path / "audit"
    write_csv(compounds, [{
        "model_metabolite_id": "M1", "primary_name": "unknown", "formula": "", "charge": "",
        "smiles": "", "mapping_source": "", "source_database": "model", "source_record_id": "M1",
    }])
    write_csv(balances, [{
        "model_reaction_id": "R1", "reaction_name": "bad", "formula_balanced": "False",
        "charge_balanced": "False", "missing_formula_metabolites": "M1", "unparsable_formula_metabolites": "",
    }])
    target.write_text(json.dumps({"compounds": [], "candidate_reactions": []}), encoding="utf-8")
    config.write_text(json.dumps({
        "inputs": {
            "compounds_csv": str(compounds), "reaction_balance_csv": str(balances),
            "target_config_json": str(target),
        },
        "fail_on_any_unresolved_structure": True,
        "strict_subsets": [],
    }), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(CLI), "--project-root", str(tmp_path), "--config", str(config), "--output-dir", str(output)],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "failed"
    with (output / "metabolite_structure_quality.csv").open(encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["status"] == "unresolved"
    assert row["review"] == "not_reviewed"
