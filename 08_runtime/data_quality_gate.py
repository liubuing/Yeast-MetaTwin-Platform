from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "09_configs" / "data_quality_gate.json"
SUMMARY_SCHEMA = ROOT / "09_configs" / "data_quality_gate_summary.schema.json"
FORMULA_RE = re.compile(r"([A-Z][a-z]?)([0-9.]*)")
MISSING = {"", "nan", "none", "null"}

METABOLITE_FIELDS = [
    "model_metabolite_id",
    "primary_name",
    "formula",
    "charge",
    "structure",
    "structure_status",
    "reason_code",
    "status",
    "source",
    "review",
]
REACTION_FIELDS = [
    "model_reaction_id",
    "reaction_name",
    "mass_balance_status",
    "charge_balance_status",
    "missing_formula_status",
    "structure_parse_status",
    "external_mapping_status",
    "manual_review_status",
    "missing_formula_metabolites",
    "unparsable_formula_metabolites",
]
REACTION_GOVERNANCE_FIELDS = REACTION_FIELDS[:8]


def has_text(value: Any) -> bool:
    return str(value).strip().lower() not in MISSING


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def load_json_contract(path: Path) -> dict[str, Any]:
    seen: set[Path] = set()
    current = path.resolve()
    while True:
        if current in seen:
            raise ValueError(f"cyclic compatibility_reference: {current}")
        seen.add(current)
        payload = json.loads(current.read_text(encoding="utf-8"))
        reference = payload.get("compatibility_reference")
        if not reference:
            return payload
        current = (current.parent / reference).resolve()


def parse_formula(value: Any) -> bool:
    text = str(value).strip()
    if not text or any(char in text for char in "R()[]+-"):
        return False
    parts = FORMULA_RE.findall(text)
    return bool(parts) and "".join(element + count for element, count in parts) == text


def parse_charge(value: Any) -> bool:
    if not has_text(value):
        return False
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


def load_smiles_parser() -> tuple[str, Callable[[str], bool]]:
    try:
        from pysmiles import read_smiles
    except ImportError:
        return "unavailable", lambda _value: False

    logging.getLogger("pysmiles").setLevel(logging.ERROR)

    def parse(value: str) -> bool:
        try:
            graph = read_smiles(value, explicit_hydrogen=False)
            return graph.number_of_nodes() > 0
        except ValueError as exc:
            # PySMILES 2.0 rejects valid /C=C/ notation as a dangling E/Z token.
            if "Dangling E/Z isomer token" not in str(exc) or not re.search(r"[/\\][^.=]*=[^.=]*[/\\]", value):
                return False
            try:
                graph = read_smiles(value.replace("/", "").replace("\\", ""), explicit_hydrogen=False)
                return graph.number_of_nodes() > 0
            except Exception:
                return False
        except Exception:
            return False

    return "pysmiles", parse


def missing_structure_reason(row: dict[str, str]) -> str:
    formula = row.get("formula", "")
    if not has_text(formula):
        return "missing_formula_and_structure"
    if not parse_formula(formula):
        return "generic_or_unparsable_formula_no_structure"
    if not has_text(row.get("mapping_source")):
        return "external_mapping_not_found"
    return "mapped_source_has_no_structure"


def compound_source(row: dict[str, str]) -> str:
    mapping = row.get("mapping_source", "").strip()
    database = row.get("source_database", "").strip()
    record = row.get("source_record_id", "").strip()
    provenance = ":".join(item for item in (database, record) if item)
    return mapping or provenance or "unrecorded"


def build_metabolite_rows(
    compounds: list[dict[str, str]], parser_name: str, parse_structure: Callable[[str], bool]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for compound in compounds:
        structure = compound.get("smiles", "").strip()
        if not structure:
            structure_status = "missing"
            reason_code = missing_structure_reason(compound)
            status = "unresolved"
            review = "not_reviewed"
        elif parser_name == "unavailable":
            structure_status = "parser_unavailable"
            reason_code = "structure_parser_unavailable"
            status = "blocked"
            review = "review_required"
        elif parse_structure(structure):
            structure_status = "parseable"
            reason_code = "not_applicable"
            status = "available"
            review = "not_required"
        else:
            structure_status = "parse_failed"
            reason_code = "structure_parse_failed"
            status = "unresolved"
            review = "review_required"
        rows.append(
            {
                "model_metabolite_id": compound.get("model_metabolite_id", ""),
                "primary_name": compound.get("primary_name", ""),
                "formula": compound.get("formula", ""),
                "charge": compound.get("charge", ""),
                "structure": structure,
                "structure_status": structure_status,
                "reason_code": reason_code,
                "status": status,
                "source": compound_source(compound),
                "review": review,
            }
        )
    return rows


def bool_status(value: str) -> str:
    normalized = value.strip().lower()
    if normalized == "true":
        return "balanced"
    if normalized == "false":
        return "unbalanced"
    return "unknown"


def build_reaction_rows(balance_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    rows = []
    for reaction in balance_rows:
        missing = reaction.get("missing_formula_metabolites", "").strip()
        unparsable = reaction.get("unparsable_formula_metabolites", "").strip()
        mass = bool_status(reaction.get("formula_balanced", ""))
        charge = bool_status(reaction.get("charge_balanced", ""))
        external = "pending" if missing else "not_required"
        manual = "required" if unparsable or mass != "balanced" or charge != "balanced" else "not_required"
        rows.append(
            {
                "model_reaction_id": reaction.get("model_reaction_id", ""),
                "reaction_name": reaction.get("reaction_name", ""),
                "mass_balance_status": mass,
                "charge_balance_status": charge,
                "missing_formula_status": "present" if missing else "absent",
                "structure_parse_status": "failed" if unparsable else "not_applicable",
                "external_mapping_status": external,
                "manual_review_status": manual,
                "missing_formula_metabolites": missing,
                "unparsable_formula_metabolites": unparsable,
            }
        )
    return rows


def validate_required_fields(rows: list[dict[str, Any]], fields: list[str], label: str) -> list[str]:
    failures = []
    for index, row in enumerate(rows, start=1):
        missing = [field for field in fields if not has_text(row.get(field))]
        if missing:
            failures.append(f"{label} row {index} missing required governance fields: {','.join(missing)}")
    return failures


def validate_strict_subsets(
    config: dict[str, Any],
    target: dict[str, Any],
    metabolite_rows: list[dict[str, Any]],
    reaction_rows: list[dict[str, Any]],
    parser_name: str,
    parse_structure: Callable[[str], bool],
) -> tuple[list[dict[str, Any]], list[str]]:
    model_compounds = {row["model_metabolite_id"]: row for row in metabolite_rows}
    target_compounds = {row.get("model_metabolite_id", ""): row for row in target.get("compounds", [])}
    target_reactions = {row.get("reaction_id", ""): row for row in target.get("candidate_reactions", [])}
    balance = {row["model_reaction_id"]: row for row in reaction_rows}
    results: list[dict[str, Any]] = []
    failures: list[str] = []

    for subset in config.get("strict_subsets", []):
        name = subset["name"]
        checks: list[dict[str, Any]] = []
        structure_parse_results: list[bool] = []

        def check(code: str, passed: bool, detail: str) -> None:
            checks.append({"code": code, "status": "passed" if passed else "failed", "detail": detail})
            if not passed:
                failures.append(f"{name}:{code}: {detail}")

        for met_id in subset.get("metabolite_ids", []):
            definition = target_compounds.get(met_id) or model_compounds.get(met_id)
            check("metabolite_id", definition is not None, met_id)
            if definition is None:
                continue
            formula = definition.get("formula", "")
            charge = definition.get("charge", "")
            structure = definition.get("smiles", definition.get("structure", ""))
            source = definition.get("smiles_source", definition.get("source", ""))
            check("formula", parse_formula(formula), f"{met_id}:{formula}")
            check("charge", parse_charge(charge), f"{met_id}:{charge}")
            check("structure_source", has_text(source) and source != "unrecorded", f"{met_id}:{source}")
            model_definition = model_compounds.get(met_id)
            target_definition = target_compounds.get(met_id)
            if model_definition is not None and target_definition is not None:
                check(
                    "formula_consistency",
                    str(model_definition.get("formula", "")) == str(target_definition.get("formula", "")),
                    met_id,
                )
                check(
                    "charge_consistency",
                    float(model_definition["charge"]) == float(target_definition["charge"]),
                    met_id,
                )
            structure_parse_results.append(
                parser_name != "unavailable" and has_text(structure) and parse_structure(str(structure))
            )

        required_fraction = float(subset.get("require_structure_parse_fraction", 1.0))
        parse_fraction = 0.0 if not structure_parse_results else sum(structure_parse_results) / len(structure_parse_results)
        check(
            "structure_parse_fraction",
            parse_fraction >= required_fraction,
            f"{sum(structure_parse_results)}/{len(structure_parse_results)}; required={required_fraction:.3f}; parser={parser_name}",
        )

        for reaction_id in subset.get("reaction_ids", []):
            definition = target_reactions.get(reaction_id)
            check("reaction_id", definition is not None, reaction_id)
            if definition is not None:
                check("reaction_source", has_text(definition.get("evidence_scope")), f"{reaction_id}:evidence_scope")
            audit = balance.get(reaction_id)
            check("reaction_balance_record", audit is not None, reaction_id)
            if audit is not None and subset.get("require_mass_charge_balanced", False):
                check("mass_balance", audit["mass_balance_status"] == "balanced", reaction_id)
                check("charge_balance", audit["charge_balance_status"] == "balanced", reaction_id)

        results.append({"name": name, "status": "passed" if all(c["status"] == "passed" for c in checks) else "failed", "checks": checks})
    return results, failures


def run_gate(root: Path, config_path: Path, output_dir: Path | None = None) -> tuple[dict[str, Any], Path]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    inputs = config["inputs"]
    compounds = read_csv(resolve(root, inputs["compounds_csv"]))
    balances = read_csv(resolve(root, inputs["reaction_balance_csv"]))
    target = load_json_contract(resolve(root, inputs["target_config_json"]))
    parser_name, parse_structure = load_smiles_parser()
    metabolite_rows = build_metabolite_rows(compounds, parser_name, parse_structure)
    reaction_rows = build_reaction_rows(balances)

    failures = validate_required_fields(
        [row for row in metabolite_rows if row["structure_status"] == "missing"],
        ["reason_code", "status", "source", "review"],
        "missing structure",
    )
    failures.extend(validate_required_fields(reaction_rows, REACTION_GOVERNANCE_FIELDS, "reaction"))
    subset_results, subset_failures = validate_strict_subsets(
        config, target, metabolite_rows, reaction_rows, parser_name, parse_structure
    )
    failures.extend(subset_failures)
    if config.get("fail_on_any_unresolved_structure", False):
        unresolved = sum(row["status"] in {"unresolved", "blocked"} for row in metabolite_rows)
        if unresolved:
            failures.append(f"unresolved structures are forbidden by policy: {unresolved}")

    output = output_dir or Path(tempfile.mkdtemp(prefix="metatwin-data-quality-"))
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "metabolite_structure_quality.csv", metabolite_rows, METABOLITE_FIELDS)
    write_csv(output / "reaction_quality.csv", reaction_rows, REACTION_FIELDS)
    structure_counts = Counter(row["structure_status"] for row in metabolite_rows)
    reason_counts = Counter(row["reason_code"] for row in metabolite_rows if row["structure_status"] == "missing")
    mass_counts = Counter(row["mass_balance_status"] for row in reaction_rows)
    charge_counts = Counter(row["charge_balance_status"] for row in reaction_rows)
    summary = {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "passed" if not failures else "failed",
        "parser": parser_name,
        "counts": {
            "metabolites_total": len(metabolite_rows),
            "structures_missing": structure_counts["missing"],
            "structures_parseable": structure_counts["parseable"],
            "structures_parse_failed": structure_counts["parse_failed"],
            "structures_parser_unavailable": structure_counts["parser_unavailable"],
            "structures_unresolved": sum(row["status"] in {"unresolved", "blocked"} for row in metabolite_rows),
            "missing_structure_missing_formula": reason_counts["missing_formula_and_structure"],
            "missing_structure_generic_formula": reason_counts["generic_or_unparsable_formula_no_structure"],
            "missing_structure_source_has_no_structure": reason_counts["mapped_source_has_no_structure"],
            "missing_structure_external_mapping_not_found": reason_counts["external_mapping_not_found"],
            "reactions_total": len(reaction_rows),
            "reactions_mass_unbalanced": mass_counts["unbalanced"],
            "reactions_charge_unbalanced": charge_counts["unbalanced"],
            "reactions_pending_external_mapping": sum(row["external_mapping_status"] == "pending" for row in reaction_rows),
            "reactions_manual_review_required": sum(row["manual_review_status"] == "required" for row in reaction_rows),
        },
        "strict_subsets": subset_results,
        "failures": failures,
        "artifacts": {
            "metabolite_quality": "metabolite_structure_quality.csv",
            "reaction_quality": "reaction_quality.csv",
            "summary_schema": str(SUMMARY_SCHEMA.relative_to(ROOT)).replace("\\", "/"),
        },
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary, output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit metabolite structure governance and reaction quality gates.")
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, help="Defaults to a newly-created system temporary directory.")
    args = parser.parse_args(argv)
    try:
        summary, output = run_gate(args.project_root.resolve(), args.config.resolve(), args.output_dir)
    except Exception as exc:
        print(json.dumps({"status": "error", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": summary["status"], "output_dir": str(output), "counts": summary["counts"]}, ensure_ascii=False))
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
