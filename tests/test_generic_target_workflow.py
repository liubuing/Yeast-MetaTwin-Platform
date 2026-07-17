from __future__ import annotations

import json
import hashlib
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_ROOT = ROOT / "10_generic_target_workflow"
RUNTIME = WORKFLOW_ROOT / "runtime"
CLI = RUNTIME / "workflow_cli.py"
SECOND_CONFIG = WORKFLOW_ROOT / "examples" / "target_workflow_lactate_dry_run.json"

sys.path.insert(0, str(RUNTIME))
from executors import ConstructDesignExecutor, CobraFbaExecutor, EngineeringFeasibilityExecutor, ExternalEvidenceExecutor, KineticPredictionExecutor  # noqa: E402
from workflow_cli import reaction_evidence_readiness  # noqa: E402
from workflow import MANIFEST_SCHEMA_PATH, SCHEMA_PATH, WorkflowValidationError, instantiate, load_json, validate_config_path  # noqa: E402


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args], cwd=ROOT, text=True, capture_output=True, check=False
    )


def output_json(result: subprocess.CompletedProcess[str]) -> dict:
    assert result.stdout, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_shipped_configs_validate_against_canonical_schema() -> None:
    configs = [
        WORKFLOW_ROOT / "configs" / "target_workflow_template.json",
        *sorted((WORKFLOW_ROOT / "examples").glob("target_workflow_*.json")),
    ]
    assert len(configs) >= 3
    for config in configs:
        validate_config_path(config)


def test_schema_rejects_unknown_fields_and_bad_references(tmp_path: Path) -> None:
    config = json.loads(SECOND_CONFIG.read_text(encoding="utf-8"))
    config["unexpected"] = True
    config["routes"][0]["reaction_ids"] = ["MISSING"]
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(WorkflowValidationError) as caught:
        validate_config_path(path)
    message = str(caught.value)
    assert "Additional properties are not allowed" in message
    assert "references unknown reaction MISSING" in message


def test_strict_json_loader_rejects_duplicate_keys(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"schema_version":"1.0","schema_version":"2.0"}', encoding="utf-8")
    with pytest.raises(WorkflowValidationError, match="duplicate JSON key: schema_version"):
        load_json(duplicate)
    load_json(SCHEMA_PATH)


def test_instantiate_writes_hashed_manifest_without_absolute_paths(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "preexisting.formal-result").write_text("must not be claimed\n", encoding="utf-8")
    workspace = instantiate(SECOND_CONFIG, target, ROOT)
    manifest = json.loads((workspace / "workflow_manifest.json").read_text(encoding="utf-8"))
    assert manifest["claims"] == {"contains_predictions": False, "contains_fba_results": False, "evidence_status": "declared_inputs_only"}
    assert manifest["config"]["path"].startswith("10_generic_target_workflow/")
    assert len(manifest["config"]["sha256"]) == 64
    assert all(len(item["sha256"]) == 64 for item in manifest["outputs"])
    assert "preexisting.formal-result" not in {item["path"] for item in manifest["outputs"]}
    assert str(ROOT) not in json.dumps(manifest)
    from jsonschema import Draft202012Validator
    assert not list(Draft202012Validator(load_json(MANIFEST_SCHEMA_PATH)).iter_errors(manifest))


def test_lactate_config_executes_real_generic_fba(tmp_path: Path) -> None:
    import cobra

    model = cobra.Model("lactate-base")
    metabolites = {name: cobra.Metabolite(name, compartment="c") for name in ("pyruvate_c", "nadh_c", "h_c", "nad_c")}
    model.add_metabolites(list(metabolites.values()))
    definitions = {
        "SOURCE_PYR": ({"pyruvate_c": 1}, 10),
        "SOURCE_NADH": ({"nadh_c": 1}, 10),
        "SOURCE_H": ({"h_c": 1}, 10),
        "SINK_NAD": ({"nad_c": -1}, 1000),
        "BIOMASS": ({"pyruvate_c": -1}, 1000),
    }
    for reaction_id, (stoich, upper) in definitions.items():
        reaction = cobra.Reaction(reaction_id, lower_bound=0, upper_bound=upper)
        reaction.add_metabolites({metabolites[key]: value for key, value in stoich.items()})
        model.add_reactions([reaction])
    model.objective = "BIOMASS"
    model_path = tmp_path / "lactate_model.json"
    cobra.io.save_json_model(model, model_path)

    config = json.loads(SECOND_CONFIG.read_text(encoding="utf-8"))
    config["fba_validation"]["model_path"] = str(model_path)
    result = CobraFbaExecutor().execute(config, ROOT, tmp_path / "fba")
    route = result["routes"][0]
    assert result["native_growth_max"] == pytest.approx(10.0)
    assert result["biomass_floor"] == pytest.approx(1.0)
    assert route["status"] == "optimal"
    assert route["objective_value"] == pytest.approx(9.0)
    assert route["candidate_fluxes"]["CAND_L_LACTATE_FORMATION"] == pytest.approx(9.0)
    assert route["pfba"]["status"] == "optimal"
    assert route["fva"]["status"] == "optimal"
    assert route["cycle_detection"]["cycle_suspected"] is False
    assert route["validation"]["stoichiometric_feasibility"]["status"] == "blocked_unbalanced"
    assert route["validation"]["model_feasibility"]["status"] == "feasible"
    assert route["validation"]["enzymatic_validation"]["status"] == "blocked"
    assert route["single_gene_deletions"]["status"] == "not_applicable"
    assert {row["scenario"] for row in route["sensitivity"]} == {"configured_medium", "half_carbon", "no_carbon", "anaerobic"}
    assert all("oxygen_bypass_suspected" in row for row in route["sensitivity"])
    assert json.loads((tmp_path / "fba" / "fba_results.json").read_text(encoding="utf-8")) == result

    config_path = tmp_path / "lactate_config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    cli_result = run_cli(
        "run", "--config", str(config_path), "--project-root", str(ROOT),
        "--run-id", "lactate-fba", "--runs-dir", str(tmp_path / "runs"),
        "--output-dir", str(tmp_path / "workspace"),
    )
    assert cli_result.returncode == 0, cli_result.stdout + cli_result.stderr
    run_dir = tmp_path / "runs" / "lactate-fba"
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    statuses = {item["stage"]: item["status"] for item in state["stages"]}
    assert statuses["model_feasibility"] == "completed"
    assert statuses["reaction_evidence"] == "skipped"
    assert statuses["kinetic_prediction"] == "completed"
    assert statuses["external_evidence"] == "completed_with_no_exact_match"
    assert statuses["engineering_feasibility"] == "completed"
    assert statuses["construct_design"] == "completed_with_incomplete_inputs"
    assert (run_dir / "artifacts" / "model_feasibility" / "fba_results.json").is_file()
    kinetic = json.loads((run_dir / "artifacts" / "kinetic_prediction" / "kinetic_predictions.json").read_text(encoding="utf-8"))
    assert kinetic["result_counts"]["unsupported"] == 1
    assert kinetic["result_counts"]["ready"] == 0
    constructs = json.loads((run_dir / "artifacts" / "construct_design" / "construct_designs.json").read_text(encoding="utf-8"))
    assert constructs["designs"] == []
    run_manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert run_manifest["claims"] == {"contains_predictions": False, "contains_fba_results": True}


def test_second_target_dry_run_is_configuration_only_e2e(tmp_path: Path) -> None:
    result = run_cli(
        "run", "--config", str(SECOND_CONFIG), "--dry-run", "--run-id", "dry-run-test",
        "--runs-dir", str(tmp_path / "runs"), "--output-dir", str(tmp_path / "target"),
    )
    assert result.returncode == 0, result.stderr
    assert output_json(result)["status"] == "dry_run_completed"
    state = json.loads((tmp_path / "runs" / "dry-run-test" / "state.json").read_text(encoding="utf-8"))
    assert state["stages"][0]["status"] == "planned"
    assert any(stage["status"] == "planned_skipped" for stage in state["stages"])
    assert not any(stage["status"] == "planned_blocked" for stage in state["stages"])
    assert not (tmp_path / "target").exists()


def test_real_run_completes_and_resume_uses_cache(tmp_path: Path) -> None:
    common = (
        "run", "--config", str(SECOND_CONFIG), "--run-id", "blocked-test",
        "--runs-dir", str(tmp_path / "runs"), "--output-dir", str(tmp_path / "target"),
    )
    first = run_cli(*common)
    assert first.returncode == 0
    assert output_json(first)["status"] == "completed"
    manifest = json.loads((tmp_path / "runs" / "blocked-test" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["claims"]["contains_predictions"] is False
    assert all(len(item["sha256"]) == 64 for item in manifest["artifacts"])
    environment = json.loads((tmp_path / "runs" / "blocked-test" / "environment.json").read_text(encoding="utf-8"))
    assert environment["python"]["version"]
    assert len(environment["source_files"][0]["sha256"]) == 64

    resumed = run_cli(*common, "--resume")
    assert resumed.returncode == 0
    state = json.loads((tmp_path / "runs" / "blocked-test" / "state.json").read_text(encoding="utf-8"))
    statuses = {item["stage"]: item["status"] for item in state["stages"]}
    assert statuses["validate"] == "cached"
    assert statuses["instantiate"] == "cached"

    (tmp_path / "target" / "inputs" / "compounds.csv").write_text("tampered\n", encoding="utf-8")
    repaired = run_cli(*common, "--resume")
    assert repaired.returncode == 0
    state = json.loads((tmp_path / "runs" / "blocked-test" / "state.json").read_text(encoding="utf-8"))
    statuses = {item["stage"]: item["status"] for item in state["stages"]}
    assert statuses["instantiate"] == "completed"
    assert "tampered" not in (tmp_path / "target" / "inputs" / "compounds.csv").read_text(encoding="utf-8")


def test_verify_release_gate(tmp_path: Path) -> None:
    report = tmp_path / "readiness.json"
    result = run_cli("verify-release", "--project-root", str(ROOT), "--report", str(report))
    assert result.returncode == 0, result.stdout + result.stderr
    readiness = json.loads(report.read_text(encoding="utf-8"))
    assert readiness["status"] == "ready"
    assert readiness["core_contract_ready"] is True
    assert readiness["execution_ready"] is True
    assert readiness["blocked_capabilities"] == []
    assert all(check["status"] == "passed" for check in readiness["checks"])
    assert any(check["name"] == "complete_reference_workflow_smoke" for check in readiness["checks"])


def test_reaction_evidence_readiness_verifies_both_versioned_manifests() -> None:
    ready, detail = reaction_evidence_readiness(ROOT)
    assert ready is True, detail
    assert "verified 2 versioned" in detail


def test_automatic_objective_and_gpr_limited_gene_deletion(tmp_path: Path) -> None:
    import cobra

    model = cobra.Model("automatic-objective")
    source = cobra.Metabolite("source_c", formula="C1", compartment="c")
    target = cobra.Metabolite("target_c", formula="C1", compartment="c")
    uptake = cobra.Reaction("UPTAKE", lower_bound=0, upper_bound=10)
    uptake.add_metabolites({source: 1})
    biomass = cobra.Reaction("BIOMASS", lower_bound=0, upper_bound=1000)
    biomass.add_metabolites({source: -1})
    model.add_reactions([uptake, biomass])
    model.objective = biomass
    path = tmp_path / "model.json"
    cobra.io.save_json_model(model, path)
    config = json.loads(SECOND_CONFIG.read_text(encoding="utf-8"))
    config["fba_validation"]["model_path"] = str(path)
    config["compounds"] = [{"compound_id": "target", "name": "target", "role": "target", "formula": "C1", "charge": 0, "smiles": None, "smiles_source": "test", "model_metabolite_id": "target_c"}]
    config["candidate_reactions"] = [{"reaction_id": "MAKE", "name": "make", "equation": "source -> target", "stoichiometry": {"source_c": -1, "target_c": 1}, "enzyme_ec_numbers": [], "gene_reaction_rule": "geneA", "reaction_role": "formation", "evidence_scope": "hypothesis", "balance_expected": True}]
    config["routes"] = [{"route_id": "route", "name": "route", "reaction_ids": ["MAKE"], "route_risk_note": "test"}]
    result = CobraFbaExecutor().execute(config, ROOT, tmp_path / "out")
    route = result["routes"][0]
    assert route["objective_reaction_id"] == "DM_target_c"
    assert route["single_gene_deletions"]["status"] == "completed"
    assert route["single_gene_deletions"]["results"][0]["objective_value"] == pytest.approx(0.0)


def test_kinetic_executor_calls_selected_ready_plugin_and_keeps_missing_input_unsupported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import executors

    config = json.loads(SECOND_CONFIG.read_text(encoding="utf-8"))
    config["compounds"][0]["smiles"] = "CC(=O)C(=O)O"
    config["prediction_pairs"] = [
        {
            "reaction_id": "CAND_L_LACTATE_FORMATION", "enzyme_source": "external",
            "substrate_compound_id": "pyruvate", "sequence_source": "test", "sequence": "MKT",
            "prediction_plugins": [{"plugin": "DLKcat", "capability": "kcat_prediction"}],
        },
        {
            "reaction_id": "CAND_L_LACTATE_FORMATION", "enzyme_source": "external",
            "substrate_compound_id": "pyruvate", "sequence_source": "missing",
            "prediction_plugins": [{"plugin": "DLKcat", "capability": "kcat_prediction"}],
        },
    ]
    row = {"plugin": "DLKcat", "capability": "kcat_prediction", "status": "ready", "entrypoint": "fake_plugin:predict", "detail": "ready"}
    monkeypatch.setattr(executors, "_plugin_registry", lambda root: {("DLKcat", "kcat_prediction"): row})

    calls = []

    class FakeResult:
        def to_dict(self) -> dict:
            return {"request_id": "fake", "plugin": "DLKcat", "capability": "kcat_prediction", "status": "ready", "predictions": [{"name": "kcat", "value": 1.25, "unit": "s^-1"}]}

    class FakeModule:
        @staticmethod
        def predict(request, plugin_root):
            calls.append(request)
            return FakeResult()

    monkeypatch.setattr(executors.importlib, "import_module", lambda name: FakeModule)
    result = KineticPredictionExecutor().execute(config, ROOT, tmp_path / "kinetic")
    assert len(calls) == 1
    assert result["result_counts"] == {"ready": 1, "unsupported": 1, "error": 0, "blocked": 0}
    assert "sequence" in result["results"][1]["messages"][0]
    assert not any(item["plugin"] == "CLEAN" for item in result["results"])


def test_unikp_requires_registry_and_inference_manifest_readiness() -> None:
    import executors

    registry = executors._plugin_registry(ROOT)
    dlkcat_ready, _ = executors._plugin_fully_ready("DLKcat", registry[("DLKcat", "kcat_prediction")], ROOT)
    unikp_ready, unikp_detail = executors._plugin_fully_ready("UniKP", registry[("UniKP", "kcat_prediction")], ROOT)
    assert dlkcat_ready is True
    assert unikp_ready is False
    assert "not fully ready" in unikp_detail


def test_local_evidence_rules_and_construct_drafts_preserve_claim_boundaries(tmp_path: Path) -> None:
    raw_record = '{"primaryAccession":"P12345","uid":"12345678","reactionCrossReferences":[{"id":"RHEA:12345"}]}'
    snapshot = tmp_path / "evidence.json"
    snapshot.write_text(json.dumps({"records": [{
        "candidate_reaction_id": "CAND_L_LACTATE_FORMATION", "source": "UniProt",
        "record": raw_record, "review_status": "unreviewed"
    }]}), encoding="utf-8")
    config = json.loads(SECOND_CONFIG.read_text(encoding="utf-8"))
    config["external_evidence"] = {"input_paths": [str(snapshot)]}
    config["engineering_layers"]["construct_design"]["enabled"] = True
    artifacts = tmp_path / "artifacts"

    evidence = ExternalEvidenceExecutor().execute(config, ROOT, artifacts / "external_evidence")
    assert evidence["status"] == "completed_with_no_exact_match"
    assert evidence["input_snapshots"][0]["sha256"] == hashlib.sha256(snapshot.read_bytes()).hexdigest()
    record = evidence["records"][0]
    assert (record["source_accession"], record["pmid"], record["rhea_id"], record["uniprot_accession"]) == ("P12345", "12345678", "RHEA:12345", "P12345")
    assert record["snapshot_sha256"] == hashlib.sha256(raw_record.encode("utf-8")).hexdigest()
    assert record["review_status"] == "unreviewed"

    engineering = EngineeringFeasibilityExecutor().execute(config, ROOT, artifacts / "engineering_feasibility")
    assert engineering["rule_results"][0]["matched"] is True
    assert engineering["claims"]["experimentally_validated"] is False

    designs = ConstructDesignExecutor().execute(config, ROOT, artifacts / "construct_design")
    assert designs["status"] == "completed"
    assert designs["designs"][0]["status"] == "hypothetical"
    assert designs["designs"][0]["requires_review"] is True
    assert designs["claims"]["wet_lab_validated"] is False


def test_construct_executor_emits_no_draft_when_candidate_enzyme_input_is_incomplete(tmp_path: Path) -> None:
    config = json.loads(SECOND_CONFIG.read_text(encoding="utf-8"))
    config["engineering_layers"]["construct_design"]["enabled"] = True
    result = ConstructDesignExecutor().execute(config, ROOT, tmp_path / "artifacts" / "construct_design")
    assert result["status"] == "completed_with_incomplete_inputs"
    assert result["designs"] == []
    assert result["unsupported_routes"][0]["missing_candidate_enzyme_reactions"] == ["CAND_L_LACTATE_FORMATION"]
