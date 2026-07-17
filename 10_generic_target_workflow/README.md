# Generic Target Workflow Core

This directory contains the target-agnostic configuration and orchestration layer. It declares candidate chemistry and evidence requests; it does not turn hypotheses or model feasibility into biochemical truth.

## Canonical Contract

`configs/target_workflow.schema.json` is the only formal target-workflow contract. It is a strict JSON Schema Draft 2020-12 document. The runtime validates the complete schema with `jsonschema` and then checks cross-object references and duplicate identifiers.

Earlier descriptive files outside this directory, including `09_configs/target_workflow_schema.json`, are not executable schemas and are not runtime inputs. New configuration must conform to the canonical contract above.

## CLI

Run commands from the project root:

```text
python 10_generic_target_workflow/runtime/workflow_cli.py validate --config <config.json>
python 10_generic_target_workflow/runtime/workflow_cli.py instantiate --config <config.json> [--output-dir <dir>]
python 10_generic_target_workflow/runtime/workflow_cli.py run --config <config.json> [--dry-run] [--run-id <id>] [--resume]
python 10_generic_target_workflow/runtime/workflow_cli.py verify-release
```

Every command emits one JSON object. Pipeline runs write `state.json`, `events.jsonl`, and `manifest.json`, including a run ID and SHA-256 hashes. `--resume` requires an unchanged configuration hash and marks reusable completed stages as `cached`.

The default project root is discovered from the runtime location. Override it with `--project-root` or `METATWIN_PROJECT_ROOT`; override run storage with `--runs-dir` or `METATWIN_RUNS_DIR`. Persisted metadata uses project-relative paths.

## Stage Semantics

`validate`, `instantiate`, model feasibility, kinetic prediction, local external-evidence collection, configured engineering rules, and hypothetical construct drafting are implemented generic stages. Model feasibility isolates each declared route and reports FBA, pFBA, FVA, closed-boundary cycle detection, carbon/oxygen sensitivity, carbon yield, and GPR-scoped single-gene deletions. Candidate reactions without a GPR are reported as `not_applicable`.

Stages are selected by configuration. Unselected stages are `skipped`; they are not release blockers. A configured stage is `blocked` only when an asset required to execute that stage is missing. Item-level limitations such as a missing sequence, missing substrate SMILES, or a selected plugin that is not fully ready are recorded as `unsupported` without stopping other pairs or stages. CLEAN has no effect unless it is explicitly selected in `prediction_plugins`.

Kinetic requests use `prediction_pairs[].sequence` or `sequence_path` and the substrate compound's `smiles`. The executor calls only a matching `ready` registry entry. UniKP additionally requires its own readiness manifest to report both `status: ready` and `inference_gate: ready`; a registry row alone is insufficient. Outputs are predictions for prioritization, never measured or curated kinetics.

`external_evidence.input_paths` accepts local JSON snapshots containing a `records` array. Each record may provide `candidate_id`/`candidate_reaction_id`, `source_database`/`source`, `source_accession`, `pmid`, `rhea_id`, `uniprot_accession`, `review_status`, `exact_match`, and either inline `record` content or `snapshot_path`. The collector reports SHA-256 for every input file and record. Exact matching is accepted only from explicit `exact_match: true`; zero exact matches yields `completed_with_no_exact_match`, not an invented evidence record or an assertion that no evidence exists.

Engineering feasibility evaluates only `engineering_layers.feasibility_rules` and records expected and observed values. It never claims experimental validation. Construct drafting uses route definitions plus UniProt candidate accessions from evidence output; incomplete routes receive per-route `unsupported` records and no draft. Every emitted design is `hypothetical` and `requires_review`.

No generic run invokes the 10H2DA-specific FBA or ML training scripts under `08_runtime`.

## Examples

- `examples/target_workflow_10h2da_reference.json` preserves the reference declaration.
- `examples/target_workflow_lactate_dry_run.json` is an independent executable reference smoke using the shipped minimal COBRA model. Its reaction is explicitly a hypothesis and no prediction result is claimed.

Install pinned core dependencies with `python -m pip install -r requirements-generic.txt`. Development and CI use `requirements-dev.txt`.
