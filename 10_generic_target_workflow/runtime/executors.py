from __future__ import annotations

import json
import csv
import hashlib
import importlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class StageReadiness:
    ready: bool
    detail: str


class StageExecutor(Protocol):
    stage: str

    def readiness(self, config: dict[str, Any], project_root: Path) -> StageReadiness: ...

    def execute(self, config: dict[str, Any], project_root: Path, output_dir: Path) -> dict[str, Any]: ...


class CobraFbaExecutor:
    stage = "model_feasibility"

    @staticmethod
    def _model_path(config: dict[str, Any], root: Path) -> Path:
        configured = Path(config["fba_validation"]["model_path"])
        return configured if configured.is_absolute() else (root / configured).resolve()

    def readiness(self, config: dict[str, Any], project_root: Path) -> StageReadiness:
        if "fba_validation" not in config:
            return StageReadiness(False, "fba_validation is not configured")
        try:
            import cobra  # noqa: F401
        except ImportError:
            return StageReadiness(False, "COBRApy is not installed")
        model_path = self._model_path(config, project_root)
        return StageReadiness(model_path.is_file(), f"model {'found' if model_path.is_file() else 'missing'}: {model_path.name}")

    @staticmethod
    def _load_model(path: Path):
        import cobra

        suffix = path.suffix.lower()
        if suffix in {".yml", ".yaml"}:
            return cobra.io.load_yaml_model(path)
        if suffix == ".json":
            return cobra.io.load_json_model(path)
        if suffix in {".xml", ".sbml"}:
            return cobra.io.read_sbml_model(path)
        raise ValueError(f"unsupported COBRA model format: {suffix}")

    @staticmethod
    def _biomass(model, configured: str | None):
        from cobra.util.solver import linear_reaction_coefficients

        if configured:
            return model.reactions.get_by_id(configured)
        reactions = [reaction for reaction, coefficient in linear_reaction_coefficients(model).items() if coefficient]
        if len(reactions) != 1:
            raise ValueError(f"cannot infer one biomass reaction from objective; found {[item.id for item in reactions]}")
        return reactions[0]

    @staticmethod
    def _objective_metabolite(config: dict[str, Any], route: dict[str, Any]) -> str:
        configured = route.get("objective_metabolite_id")
        if configured:
            return configured
        targets = [item["model_metabolite_id"] for item in config["compounds"] if item["role"] == "target"]
        if len(targets) != 1:
            raise ValueError(f"automatic objective requires exactly one target compound; found {targets}")
        return targets[0]

    @staticmethod
    def _carbon_atoms(formula: str | None) -> int | None:
        if not formula:
            return None
        match = re.search(r"C(\d*)", formula)
        return (int(match.group(1)) if match.group(1) else 1) if match else 0

    @staticmethod
    def _set_uptake_capacity(reaction, fraction: float) -> None:
        if reaction.lower_bound < 0:
            reaction.lower_bound *= fraction
        elif reaction.upper_bound > 0:
            reaction.upper_bound *= fraction

    @staticmethod
    def _optimize(work, demand, biomass_id: str, floor: float, route_ids: list[str], settings: dict[str, Any]) -> dict[str, Any]:
        from cobra.flux_analysis import flux_variability_analysis, pfba

        if floor > 0:
            work.add_cons_vars(work.problem.Constraint(
                work.reactions.get_by_id(biomass_id).flux_expression,
                lb=floor,
                name="target_biomass_floor",
            ))
        work.objective = demand
        solution = work.optimize()
        result: dict[str, Any] = {
            "status": solution.status,
            "objective_value": float(solution.objective_value) if solution.objective_value is not None else None,
            "candidate_fluxes": {},
            "pfba": {"status": "not_run"},
            "fva": {"status": "not_run", "fraction_of_optimum": float(settings.get("fva_fraction_of_optimum", 0.9)), "reactions": {}},
        }
        if solution.status != "optimal":
            return result
        result["candidate_fluxes"] = {reaction_id: float(solution.fluxes[reaction_id]) for reaction_id in route_ids}
        try:
            parsimonious = pfba(work)
            result["pfba"] = {
                "status": parsimonious.status,
                "objective_value": float(parsimonious.fluxes[demand.id]),
                "total_absolute_flux": float(parsimonious.fluxes.abs().sum()),
                "candidate_fluxes": {reaction_id: float(parsimonious.fluxes[reaction_id]) for reaction_id in route_ids},
            }
        except Exception as exc:
            result["pfba"] = {"status": "error", "detail": f"{type(exc).__name__}: {exc}"}
        try:
            reaction_ids = [*route_ids, demand.id]
            ranges = flux_variability_analysis(
                work,
                reaction_list=reaction_ids,
                fraction_of_optimum=result["fva"]["fraction_of_optimum"],
                loopless="cycleFreeFlux" if settings.get("loopless_fva", False) else None,
            )
            result["fva"] = {
                "status": "optimal",
                "fraction_of_optimum": result["fva"]["fraction_of_optimum"],
                "loopless": bool(settings.get("loopless_fva", False)),
                "reactions": {rid: {"minimum": float(ranges.at[rid, "minimum"]), "maximum": float(ranges.at[rid, "maximum"])} for rid in reaction_ids},
            }
        except Exception as exc:
            result["fva"] = {"status": "error", "detail": f"{type(exc).__name__}: {exc}"}
        return result

    @staticmethod
    def _cycle_detection(work, demand) -> dict[str, Any]:
        cycle_model = work.copy()
        for boundary in cycle_model.boundary:
            if boundary.id != demand.id:
                boundary.bounds = (0.0, 0.0)
        cycle_model.objective = cycle_model.reactions.get_by_id(demand.id)
        solution = cycle_model.optimize()
        value = float(solution.objective_value or 0.0) if solution.status == "optimal" else 0.0
        return {
            "method": "closed_boundary_target_test",
            "status": solution.status,
            "target_flux": value,
            "cycle_suspected": value > 1e-9,
            "interpretation": "positive target flux with all non-target boundaries closed indicates a stoichiometric cycle",
        }

    def _sensitivity(self, model, demand_id: str, biomass_id: str, floor: float, settings: dict[str, Any]) -> list[dict[str, Any]]:
        scenarios = [("configured_medium", 1.0, 1.0), ("half_carbon", 0.5, 1.0), ("no_carbon", 0.0, 1.0), ("anaerobic", 1.0, 0.0)]
        rows = []
        for name, carbon_fraction, oxygen_fraction in scenarios:
            work = model.copy()
            for key, fraction in (("carbon_exchange_id", carbon_fraction), ("oxygen_exchange_id", oxygen_fraction)):
                reaction_id = settings.get(key)
                if reaction_id:
                    self._set_uptake_capacity(work.reactions.get_by_id(reaction_id), fraction)
            if floor > 0:
                work.add_cons_vars(work.problem.Constraint(work.reactions.get_by_id(biomass_id).flux_expression, lb=floor, name=f"sensitivity_floor_{name}"))
            work.objective = demand_id
            solution = work.optimize()
            value = float(solution.objective_value) if solution.objective_value is not None else None
            exchange_fluxes = {
                key: float(solution.fluxes[reaction_id]) if solution.status == "optimal" else None
                for key in ("carbon_exchange_id", "oxygen_exchange_id")
                if (reaction_id := settings.get(key))
            }
            oxygen_bypass = name == "anaerobic" and solution.status == "optimal" and (value or 0.0) > 1e-9
            rows.append({
                "scenario": name,
                "status": solution.status,
                "objective_value": value,
                "configured_exchange_fluxes": exchange_fluxes,
                "oxygen_bypass_suspected": oxygen_bypass,
                "interpretation": "positive target flux with oxygen uptake disabled indicates model-internal oxygen generation; not evidence of anaerobic biology" if oxygen_bypass else "",
            })
        return rows

    def _gene_deletions(self, model, demand_id: str, biomass_id: str, floor: float, baseline: float, route_ids: list[str]) -> dict[str, Any]:
        genes = sorted({gene.id for rid in route_ids for gene in model.reactions.get_by_id(rid).genes})
        if not genes:
            return {"status": "not_applicable", "reason": "route candidate reactions have no GPR", "results": []}
        rows = []
        for gene_id in genes:
            work = model.copy()
            work.genes.get_by_id(gene_id).knock_out()
            if floor > 0:
                work.add_cons_vars(work.problem.Constraint(work.reactions.get_by_id(biomass_id).flux_expression, lb=floor, name=f"deletion_floor_{gene_id}"))
            work.objective = demand_id
            solution = work.optimize()
            value = float(solution.objective_value or 0.0) if solution.status == "optimal" else 0.0
            rows.append({"gene_id": gene_id, "status": solution.status, "objective_value": value, "fraction_of_baseline": value / baseline if baseline > 0 else None})
        return {"status": "completed", "scope": "genes referenced by route-reaction GPR only", "results": rows}

    def execute(self, config: dict[str, Any], project_root: Path, output_dir: Path) -> dict[str, Any]:
        import cobra

        settings = config["fba_validation"]
        model_path = self._model_path(config, project_root)
        model = self._load_model(model_path)
        if settings.get("solver"):
            model.solver = settings["solver"]

        compartment = config["target"]["compartment"]
        compounds = {item["model_metabolite_id"]: item for item in config["compounds"]}
        for metabolite_id, item in compounds.items():
            if metabolite_id in model.metabolites:
                continue
            model.add_metabolites([cobra.Metabolite(
                metabolite_id,
                name=item["name"],
                formula=item.get("formula"),
                charge=item.get("charge"),
                compartment=compartment,
            )])
        biomass = self._biomass(model, settings.get("biomass_reaction_id"))
        growth_model = model.copy()
        growth_model.objective = biomass.id
        growth = growth_model.optimize()
        growth_max = float(growth.objective_value or 0.0) if growth.status == "optimal" else 0.0
        floor = growth_max * float(settings["biomass_floor_fraction"])

        route_results = []
        for route in config["routes"]:
            work = model.copy()
            definitions = {item["reaction_id"]: item for item in config["candidate_reactions"]}
            balance = {}
            for reaction_id in route["reaction_ids"]:
                item = definitions[reaction_id]
                if reaction_id in work.reactions:
                    raise ValueError(f"candidate reaction already exists in model: {reaction_id}")
                reaction = cobra.Reaction(reaction_id)
                reaction.name = item["name"]
                reaction.bounds = (float(item.get("lower_bound", 0.0)), float(item.get("upper_bound", 1000.0)))
                reaction.gene_reaction_rule = item.get("gene_reaction_rule", "")
                reaction.add_metabolites({work.metabolites.get_by_id(key): value for key, value in item["stoichiometry"].items()})
                work.add_reactions([reaction])
                balance[reaction_id] = reaction.check_mass_balance()
            target_id = self._objective_metabolite(config, route)
            target = work.metabolites.get_by_id(target_id)
            demand = work.add_boundary(target, type="demand")
            analysis = self._optimize(work.copy(), demand, biomass.id, floor, route["reaction_ids"], settings)
            cycle = self._cycle_detection(work, demand)
            sensitivity = self._sensitivity(work, demand.id, biomass.id, floor, settings)
            carbon_id = settings.get("carbon_exchange_id")
            carbon_yield = {"status": "not_applicable", "reason": "carbon_exchange_id is not configured"}
            if analysis["status"] == "optimal" and carbon_id:
                carbon_reaction = work.reactions.get_by_id(carbon_id)
                carbon_work = work.copy()
                if floor > 0:
                    carbon_work.add_cons_vars(carbon_work.problem.Constraint(carbon_work.reactions.get_by_id(biomass.id).flux_expression, lb=floor, name="carbon_yield_biomass_floor"))
                carbon_work.objective = demand.id
                carbon_solution = carbon_work.optimize()
                uptake = abs(float(carbon_solution.fluxes[carbon_id]))
                source_atoms = self._carbon_atoms(next(iter(carbon_reaction.metabolites)).formula)
                target_atoms = self._carbon_atoms(target.formula)
                carbon_yield = {
                    "status": "computed" if uptake > 1e-12 and source_atoms is not None and target_atoms is not None else "not_applicable",
                    "target_carbon_mol_per_substrate_carbon_mol": (float(carbon_solution.fluxes[demand.id]) * target_atoms / (uptake * source_atoms)) if uptake > 1e-12 and source_atoms and target_atoms is not None else None,
                    "carbon_exchange_flux": float(carbon_solution.fluxes[carbon_id]),
                    "source_carbon_atoms": source_atoms,
                    "target_carbon_atoms": target_atoms,
                }
            stoichiometric_status = "feasible" if all(not value for value in balance.values()) else "blocked_unbalanced"
            model_status = "feasible" if analysis["status"] == "optimal" and (analysis["objective_value"] or 0.0) > 1e-9 and not cycle["cycle_suspected"] else "not_feasible"
            route_results.append({
                "route_id": route["route_id"],
                "objective_reaction_id": demand.id,
                **analysis,
                "validation": {
                    "stoichiometric_feasibility": {"status": stoichiometric_status, "reaction_imbalances": balance},
                    "model_feasibility": {"status": model_status, "requires_positive_target_flux": True, "cycle_free_required": True},
                    "enzymatic_validation": {"status": "blocked", "reason": "FBA/FVA do not validate enzyme activity or substrate specificity"},
                },
                "cycle_detection": cycle,
                "sensitivity": sensitivity,
                "carbon_yield": carbon_yield,
                "single_gene_deletions": self._gene_deletions(work, demand.id, biomass.id, floor, float(analysis["objective_value"] or 0.0), route["reaction_ids"]),
            })
        result = {
            "executor": "cobra_fba",
            "model": model_path.name,
            "biomass_reaction_id": biomass.id,
            "native_growth_status": growth.status,
            "native_growth_max": growth_max,
            "biomass_floor": floor,
            "routes": route_results,
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "fba_results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        return result


def _resolve_path(value: str, root: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (root / path).resolve()


def _write_result(output_dir: Path, filename: str, result: dict[str, Any]) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / filename).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def _plugin_registry(root: Path) -> dict[tuple[str, str], dict[str, str]]:
    path = root / "09_configs" / "prediction_plugins.csv"
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        return {(row["plugin"], row["capability"]): row for row in csv.DictReader(handle)}


def _plugin_fully_ready(plugin: str, row: dict[str, str], root: Path) -> tuple[bool, str]:
    if row.get("status") != "ready" or not row.get("entrypoint"):
        return False, row.get("detail") or f"registry status is {row.get('status', 'absent')}"
    if plugin == "UniKP":
        manifest_path = root / "04_prediction_plugins" / "UniKP" / "readiness_manifest.json"
        if not manifest_path.is_file():
            return False, "UniKP readiness manifest is missing"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("status") != "ready" or manifest.get("inference_gate") != "ready":
            return False, "UniKP inference readiness is not fully ready"
    return True, "registry and plugin inference readiness passed"


class KineticPredictionExecutor:
    stage = "kinetic_prediction"

    def readiness(self, config: dict[str, Any], project_root: Path) -> StageReadiness:
        registry = _plugin_registry(project_root)
        return StageReadiness(bool(registry), "plugin registry loaded" if registry else "plugin registry is missing or empty")

    def execute(self, config: dict[str, Any], project_root: Path, output_dir: Path) -> dict[str, Any]:
        plugin_root = project_root / "04_prediction_plugins"
        if str(plugin_root) not in sys.path:
            sys.path.insert(0, str(plugin_root))
        from plugin_runtime.schema import PluginInput

        compounds = {item["compound_id"]: item for item in config["compounds"]}
        registry = _plugin_registry(project_root)
        results = []
        for pair_index, pair in enumerate(config.get("prediction_pairs", [])):
            compound = compounds[pair["substrate_compound_id"]]
            sequence = pair.get("sequence")
            if not sequence and pair.get("sequence_path"):
                sequence_path = _resolve_path(pair["sequence_path"], project_root)
                if sequence_path.is_file():
                    sequence = "".join(
                        line.strip() for line in sequence_path.read_text(encoding="utf-8").splitlines()
                        if line.strip() and not line.startswith(">")
                    )
            for request in pair.get("prediction_plugins", []):
                plugin, capability = request["plugin"], request["capability"]
                request_id = f"{pair['reaction_id']}:{pair_index}:{plugin}:{capability}"
                base = {"request_id": request_id, "reaction_id": pair["reaction_id"], "plugin": plugin, "capability": capability}
                missing = [name for name, value in (("sequence", sequence), ("substrate_smiles", compound.get("smiles"))) if not value]
                if missing:
                    results.append({**base, "status": "unsupported", "messages": ["missing required input: " + ", ".join(missing)]})
                    continue
                row = registry.get((plugin, capability))
                if row is None:
                    results.append({**base, "status": "unsupported", "messages": ["plugin capability is absent from registry"]})
                    continue
                ready, detail = _plugin_fully_ready(plugin, row, project_root)
                if not ready:
                    results.append({**base, "status": "unsupported", "messages": [detail]})
                    continue
                module_name, _, attribute = row["entrypoint"].partition(":")
                try:
                    predictor = getattr(importlib.import_module(module_name), attribute)
                    plugin_result = predictor(
                        PluginInput(request_id=request_id, capability=capability, sequence=sequence, substrate_smiles=compound["smiles"], context={"reaction_id": pair["reaction_id"]}),
                        plugin_root,
                    )
                    results.append({**base, **plugin_result.to_dict()})
                except Exception as exc:
                    results.append({**base, "status": "error", "messages": [f"{type(exc).__name__}: {exc}"]})
        counts = {status: sum(item["status"] == status for item in results) for status in ("ready", "unsupported", "error", "blocked")}
        return _write_result(output_dir, "kinetic_predictions.json", {
            "executor": "registry_kinetic_prediction", "status": "completed", "result_counts": counts,
            "results": results, "claims": {"predictions_are_measured": False, "predictions_are_curated_evidence": False},
        })


class ExternalEvidenceExecutor:
    stage = "external_evidence"

    def readiness(self, config: dict[str, Any], project_root: Path) -> StageReadiness:
        settings = config.get("external_evidence", {})
        missing = [value for value in settings.get("input_paths", []) if not _resolve_path(value, project_root).is_file()]
        return StageReadiness(not missing, "local evidence inputs available" if not missing else "missing local evidence input(s): " + ", ".join(missing))

    @staticmethod
    def _identifiers(source: str, raw: str) -> tuple[str | None, str | None, str | None]:
        pmids = re.findall(r'(?i)(?:"uid"\s*:\s*"|PubMed[^0-9]{0,20})(\d{1,10})', raw)
        rheas = re.findall(r"RHEA:\d+", raw)
        accessions = re.findall(r'"primaryAccession"\s*:\s*"([A-Z0-9]{6,10})"', raw)
        return (pmids[0] if pmids else None, rheas[0] if rheas else None, accessions[0] if accessions else None)

    def execute(self, config: dict[str, Any], project_root: Path, output_dir: Path) -> dict[str, Any]:
        records: list[dict[str, Any]] = []
        input_snapshots = []
        explicit_exact = 0
        for configured_path in config.get("external_evidence", {}).get("input_paths", []):
            path = _resolve_path(configured_path, project_root)
            raw_file = path.read_bytes()
            input_snapshots.append({"path": configured_path, "sha256": hashlib.sha256(raw_file).hexdigest()})
            document = json.loads(raw_file)
            source_rows = document.get("records", []) if isinstance(document, dict) else document
            for index, item in enumerate(source_rows):
                raw = item.get("record")
                if raw is None and item.get("snapshot_path"):
                    raw = _resolve_path(item["snapshot_path"], project_root).read_text(encoding="utf-8")
                if raw is None:
                    continue
                raw = raw if isinstance(raw, str) else json.dumps(raw, sort_keys=True, ensure_ascii=False)
                source = item.get("source_database") or item.get("source") or "unknown"
                pmid, rhea, uniprot = self._identifiers(source, raw)
                explicit_exact += int(item.get("exact_match") is True)
                accession = item.get("source_accession") or uniprot or rhea or pmid
                records.append({
                    "evidence_id": item.get("evidence_id", f"{path.stem}:{index}"),
                    "candidate_id": item.get("candidate_id") or item.get("candidate_reaction_id"),
                    "source_database": source, "source_accession": accession, "pmid": item.get("pmid") or pmid,
                    "rhea_id": item.get("rhea_id") or rhea, "uniprot_accession": item.get("uniprot_accession") or uniprot,
                    "snapshot_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                    "review_status": item.get("review_status", "unreviewed"), "exact_match": item.get("exact_match") is True,
                })
        status = "completed" if explicit_exact else "completed_with_no_exact_match"
        return _write_result(output_dir, "external_evidence.json", {
            "executor": "local_external_evidence", "status": status, "record_count": len(records),
            "exact_match_count": explicit_exact, "input_snapshots": input_snapshots, "records": records,
            "claims": {"network_accessed": False, "absence_proves_no_evidence_exists": False},
        })


class EngineeringFeasibilityExecutor:
    stage = "engineering_feasibility"

    def readiness(self, config: dict[str, Any], project_root: Path) -> StageReadiness:
        return StageReadiness(True, "configuration-driven rule evaluator available")

    def execute(self, config: dict[str, Any], project_root: Path, output_dir: Path) -> dict[str, Any]:
        evidence_path = output_dir.parent / "external_evidence" / "external_evidence.json"
        evidence = json.loads(evidence_path.read_text(encoding="utf-8")) if evidence_path.is_file() else {"status": "not_configured", "records": [], "exact_match_count": 0}
        reviewed = sum(item.get("review_status") == "approved" for item in evidence.get("records", []))
        observed = {"external_evidence.status": evidence.get("status"), "external_evidence.exact_match_count": evidence.get("exact_match_count", 0), "external_evidence.approved_record_count": reviewed}
        rows = []
        for rule in config["engineering_layers"].get("feasibility_rules", []):
            value = observed[rule["evidence_field"]]
            expected = rule["value"]
            matched = value == expected if rule["operator"] == "equals" else value >= expected
            rows.append({"rule_id": rule["rule_id"], "evidence_field": rule["evidence_field"], "operator": rule["operator"], "expected": expected, "observed": value, "matched": matched, "result": rule["result_if_matched"] if matched else "not_triggered", "notes": rule.get("notes", "")})
        return _write_result(output_dir, "engineering_feasibility.json", {
            "executor": "configured_engineering_rules", "status": "completed", "rule_results": rows,
            "claims": {"experimentally_validated": False, "purpose": "traceable engineering prioritization only"},
        })


class ConstructDesignExecutor:
    stage = "construct_design"

    def readiness(self, config: dict[str, Any], project_root: Path) -> StageReadiness:
        return StageReadiness(True, "hypothetical design draft generator available")

    def execute(self, config: dict[str, Any], project_root: Path, output_dir: Path) -> dict[str, Any]:
        evidence_path = output_dir.parent / "external_evidence" / "external_evidence.json"
        evidence = json.loads(evidence_path.read_text(encoding="utf-8")) if evidence_path.is_file() else {"records": []}
        candidates: dict[str, set[str]] = {}
        for record in evidence.get("records", []):
            if record.get("candidate_id") and record.get("uniprot_accession"):
                candidates.setdefault(record["candidate_id"], set()).add(record["uniprot_accession"])
        drafts, incomplete = [], []
        for route in config.get("routes", []):
            missing = [reaction_id for reaction_id in route["reaction_ids"] if not candidates.get(reaction_id)]
            if missing:
                incomplete.append({"route_id": route["route_id"], "status": "unsupported", "missing_candidate_enzyme_reactions": missing})
                continue
            drafts.append({
                "design_id": f"hypothetical-{route['route_id']}", "route_id": route["route_id"],
                "reaction_candidates": [{"reaction_id": reaction_id, "uniprot_accessions": sorted(candidates[reaction_id])} for reaction_id in route["reaction_ids"]],
                "status": "hypothetical", "requires_review": True, "design_scope": config["engineering_layers"]["construct_design"]["design_scope"],
            })
        return _write_result(output_dir, "construct_designs.json", {
            "executor": "hypothetical_construct_design", "status": "completed" if drafts else "completed_with_incomplete_inputs",
            "designs": drafts, "unsupported_routes": incomplete,
            "claims": {"hypothetical": True, "requires_review": True, "wet_lab_validated": False},
        })


EXECUTORS: dict[str, StageExecutor] = {
    item.stage: item for item in (
        CobraFbaExecutor(), KineticPredictionExecutor(), ExternalEvidenceExecutor(),
        EngineeringFeasibilityExecutor(), ConstructDesignExecutor(),
    )
}
