# Integrated Yeast-MetaTwin Deployment

This directory is a reproducible research snapshot for an integrated Yeast-MetaTwin workflow. It contains model-query, FBA, evidence-ranking, target-specific analysis, and a generic workflow scaffold. It is not a production deployment.

## Readiness

**Research workflow, not a production or experimentally validated deployment.** The generic CLI has an executable reference smoke and can complete configured software stages while preserving scientific limitations in machine-readable outputs. Remaining scientific and operational limitations include:

- Reaction-evidence ML remains optional and has no generic executor; it does not block workflows that do not select it.
- CLEAN checkpoints/adapters remain incomplete, but CLEAN does not block workflows unless explicitly selected. DLKcat is registry-gated; pair-level missing inputs are reported as unsupported.
- UniKP uses pickle assets and a separate legacy environment. The generic executor requires both registry readiness and a fully ready UniKP inference manifest before invocation.
- No exact curated enzyme evidence validates the proposed 10H2DA terminal reactions, and no candidate reaches evidence tier A.
- External evidence is consumed only from configured local snapshots with hashes and review state; no-match output is not evidence of absence. Review approvals and production operational controls remain incomplete.

Use `python 08_runtime/environment_check.py --verify-assets` for the current machine-readable environment/asset check. Setup, asset trust, and run retention are documented in `00_docs/ENVIRONMENT.md`, `00_docs/ASSET_TRUST_POLICY.md`, and `00_docs/RUN_ARTIFACTS.md`.

## Folder Layout

| Folder | Purpose |
|---|---|
| `00_docs` | Deployment documents, user manuals, design notes, and generated Word/PDF reports for the integrated platform. |
| `01_databases` | Raw and processed external databases, such as KEGG, Rhea, MetaCyc, BRENDA, UniProt, MetaNetX, ChEBI, PubChem, and YMDB. |
| `02_id_mapping` | ID mapping tables and structure normalization outputs, including SMILES, InChIKey, KEGG, ChEBI, MetaNetX, PubChem, and YMDB cross-references. |
| `03_models` | Metabolic models and trained model artifacts, including yeast-GEM, Yeast-MetaTwin, candidate expanded models, and serialized ML models. |
| `04_prediction_plugins` | Pluggable prediction modules, such as CLEAN, DeepECtransformer, ESP, EnzRank, CatPred, UniKP, DLKcat, and P450-specific predictors. |
| `05_training` | Training datasets, split definitions, cold-start splits, training scripts, and model checkpoints. |
| `06_evaluation` | Evaluation outputs, leakage checks, recovery validation, pathway validation, and benchmark tables. |
| `07_reports` | Generated pathway reports, candidate enzyme reports, model audit reports, and decision-ready summaries. |
| `08_runtime` | Runtime scripts, command wrappers, notebooks, temporary run outputs, and local execution artifacts. |
| `09_configs` | Configuration files for database paths, model paths, thresholds, scoring weights, and environment settings. |
| `logs` | Run logs, error logs, and deployment verification logs. |

## Intended Integration Flow

```text
Input target compound
  -> normalize compound identity
  -> map IDs and structures across databases
  -> search Yeast-MetaTwin and yeast-GEM
  -> generate candidate reactions/pathways
  -> score enzymes and substrates with prediction plugins
  -> add candidate reactions to metabolic model
  -> run FBA/demand/knockout validation
  -> evaluate leakage and recovery risk
  -> export Word/Excel/Markdown reports
```

## Deployment Principle

Start with database normalization and model-query reliability before training new models. Training should only start after deduplication, ID mapping, reaction balancing, cold-start splits, and leakage checks are in place.

## Current Status

Phase 1 model-query verification was completed for the recorded source models. This is a historical verification result, not a production readiness claim.

- Configuration: `09_configs/deployment_config.json`
- Phase 1 verification script: `08_runtime/verify_phase1_deployment.py`
- Verification report: `06_evaluation/phase1_deployment_verification.md`
- Execution report: `00_docs/PHASE1_EXECUTION_REPORT.md`

Verified model status:

- `yeast-GEM`: 4131 reactions, 2806 metabolites, FBA optimal.
- `Yeast-MetaTwin`: 7512 reactions, 3301 metabolites, 3381 `rxn*` reactions, FBA optimal.

Phase 2 has progressed beyond startup and now includes normalization, split audits, research ML models, plugin-readiness audits, and target-specific 10H2DA analyses. These artifacts remain a research snapshot.

- Schema templates: `02_id_mapping/*_schema.csv`
- Asset scan report: `06_evaluation/phase2_database_asset_scan.md`
- Key database assets: `01_databases/phase2_key_database_assets.csv`
- Model compound seed table: `02_id_mapping/model_compound_seed.csv`
- Model reaction seed table: `02_id_mapping/model_reaction_seed.csv`
- Model enzyme evidence seed table: `02_id_mapping/model_enzyme_evidence_seed.csv`
- Enriched compound seed table: `02_id_mapping/model_compound_seed_enriched.csv`
- Enriched enzyme evidence seed table: `02_id_mapping/model_enzyme_evidence_seed_enriched.csv`
- Mapping enrichment report: `06_evaluation/phase2_mapping_enrichment.md`
- Reaction cross-reference table: `02_id_mapping/model_reaction_crossrefs.csv`
- Reaction cross-reference report: `06_evaluation/phase2_reaction_crossrefs.md`
- Underground reaction provenance table: `02_id_mapping/model_underground_rxn_provenance.csv`
- Underground reaction provenance report: `06_evaluation/phase2_rxn_provenance.md`
- Reaction confidence flags table: `02_id_mapping/model_reaction_confidence_flags.csv`
- Reaction confidence flags report: `06_evaluation/phase2_reaction_confidence_flags.md`
- Reaction label export report: `06_evaluation/phase2_reaction_label_exports.md`
- First-pass reference labels: `05_training/reaction_first_pass_reference_labels.csv`
- Candidate extension evidence: `05_training/reaction_candidate_extension_evidence.csv`
- Model context reactions: `05_training/reaction_model_context_only.csv`
- Review-required exclusions: `05_training/reaction_excluded_review_required.csv`
- Reaction label export QA: `06_evaluation/phase2_reaction_label_export_qa.md`
- Split-ready reference + candidate pool: `05_training/split_ready_reference_plus_candidate_no_overlap.csv`
- Split-ready candidate overlap review: `05_training/split_ready_candidate_reference_overlap_review.csv`
- Reference-only split definitions: `05_training/split_definitions_reference_only.csv`
- Reference + candidate split definitions: `05_training/split_definitions_reference_plus_candidate_no_overlap.csv`
- Split definition report: `06_evaluation/phase2_reaction_split_definitions.md`
- Training manifest index: `05_training/training_manifest_index.csv`
- Reference-only training manifest: `05_training/training_manifest_reference_only.json`
- Reference + candidate training manifest: `05_training/training_manifest_reference_plus_candidate_no_overlap.json`
- Exact-sequence reference-only split: `05_training/exact_sequence_split_reference_only.csv`
- Exact-sequence reference + candidate split: `05_training/exact_sequence_split_reference_plus_candidate_no_overlap.csv`
- Exact-sequence split report: `06_evaluation/phase2_exact_sequence_splits.md`
- MMseqs2 homology reference-only split: `05_training/homology_split_reference_only.csv`
- MMseqs2 homology reference + candidate split: `05_training/homology_split_reference_plus_candidate_no_overlap.csv`
- MMseqs2 homology split report: `06_evaluation/phase2_mmseqs_homology_splits.md`
- MMseqs2 threshold sensitivity report: `06_evaluation/phase2_mmseqs_threshold_sensitivity.md`
- Homology split readiness report: `06_evaluation/phase2_homology_split_readiness.md`
- 10H2DA candidate extension FBA report: `07_reports/10H2DA_candidate_extension_fba.md`
- Training readiness audit: `06_evaluation/phase2_training_readiness_audit.md`
- Reaction balance audit: `06_evaluation/phase2_reaction_balance_audit.csv`
- Candidate negative sample pool: `05_training/reaction_negative_sample_candidates.csv`
- Candidate validation matrix: `06_evaluation/phase2_candidate_validation_matrix.csv`
- Trained reaction evidence baseline model: `03_models/phase2_reaction_evidence_baseline_v1.joblib`
- Reaction evidence baseline training report: `07_reports/phase2_reaction_evidence_baseline_training.md`
- Candidate extension evidence scores: `06_evaluation/phase2_candidate_extension_evidence_scores.csv`
- 10H2DA terminal candidate scores: `06_evaluation/10h2da_terminal_candidate_scores.csv`
- PU v2 reaction evidence model: `03_models/phase2_reaction_evidence_pu_v2.joblib`
- PU v2 training report: `07_reports/phase2_reaction_evidence_pu_v2_training.md`
- Balance remediation audit: `06_evaluation/phase2_balance_remediation_audit.md`
- 10H2DA terminal evidence validation report: `07_reports/10H2DA_terminal_evidence_validation.md`
- Plugin asset readiness report: `06_evaluation/phase2_plugin_asset_readiness.md`
- Plugin runtime compatibility report: `06_evaluation/phase2_plugin_runtime_compatibility.md`
- 10H2DA external evidence supplement: `07_reports/10H2DA_external_evidence_supplement.md`
- 10H2DA UniKP terminal prioritization report: `07_reports/10H2DA_unikp_terminal_prioritization.md`
- 10H2DA terminal enzyme evidence matrix: `06_evaluation/10h2da_terminal_enzyme_evidence_matrix.csv`
- 10H2DA engineering candidate prioritization report: `07_reports/10H2DA_engineering_candidate_prioritization.md`
- 10H2DA engineering candidate matrix: `06_evaluation/10h2da_engineering_candidate_matrix.csv`
- 10H2DA pathway design candidates: `06_evaluation/10h2da_pathway_design_candidates.csv`
- 10H2DA P450 engineering feasibility report: `07_reports/10H2DA_p450_engineering_feasibility.md`
- 10H2DA P450 feasibility matrix: `06_evaluation/10h2da_p450_engineering_feasibility_matrix.csv`
- 10H2DA P450-adjusted design recommendations: `06_evaluation/10h2da_p450_design_recommendations.csv`
- 10H2DA construct/redox design report: `07_reports/10H2DA_construct_design_matrix.md`
- 10H2DA construct/redox design matrix: `06_evaluation/10h2da_construct_design_matrix.csv`
- Plugin asset recovery sources: `06_evaluation/phase2_plugin_asset_recovery_sources.md`
- Execution report: `00_docs/PHASE2_EXECUTION_REPORT.md`

Current reaction evidence tiers:

- `external_crossref`: 1959 reactions, preferred first-pass reference labels.
- `model_only`: 2172 reactions, useful as model context but not first-pass training labels.
- `prediction_provenance`: 3330 underground reactions with direct RXNdb provenance.
- `review_required`: 51 underground `rxnu*` reactions without selected RXNdb direct match.

Current reaction export groups:

- `first_pass_reference_label`: 1959 reactions for the initial reference label pool.
- `candidate_extension_evidence`: 3330 reactions for reviewed pathway-extension candidates.
- `model_context_only`: 2172 reactions for simulation and context, not labels.
- `excluded_review_required`: 51 unresolved `rxnu*` reactions excluded from labels.

Current split-ready pools:

- `split_ready_reference_labels`: 1959 reactions.
- `split_ready_candidate_extension_no_reference_overlap`: 3323 reactions.
- `split_ready_reference_plus_candidate_no_overlap`: 5282 reactions.
- `split_ready_candidate_reference_overlap_review`: 7 candidate reactions isolated because their exact model equations also appear in the reference pool.

Current deterministic split definitions:

- `reference_only`: 1959 reactions split into train 1593, dev 172, test 194.
- `reference_plus_candidate_no_overlap`: 5282 reactions split into train 4250, dev 503, test 529.
- Split rule: SHA256 hash of exact model equation, falling back to model reaction ID if equation is missing.
- Split key crossing count: 0 for both pools.

Current homology-cold split readiness:

- FASTA assets are present; ORF coverage is complete for `reference_only` and missing only the placeholder `nogene` for `reference_plus_candidate_no_overlap`.
- MMseqs2 was used for the recorded split artifacts. Its executable location is machine-specific and must be supplied or installed on a new host; CD-HIT was not used.

Current exact-sequence split definitions:

- `exact_sequence_reference_only`: 1959 reactions split into train 1583, dev 188, test 188; exact-sequence crossing count 0.
- `exact_sequence_reference_plus_candidate_no_overlap`: 5282 reactions split into train 4028, dev 862, test 392; exact-sequence crossing count 0.
- This prevents identical protein sequence sets from crossing splits, but it is still not a homolog-cluster split.

Current MMseqs2 homology split definitions:

- MMseqs2 parameters: `--min-seq-id 0.3 -c 0.8 --cov-mode 0`.
- ORFs clustered: 1745 input sequences into 1416 clusters.
- `homology_reference_only`: 1959 reactions split into train 1584, dev 159, test 216; homology crossing count 0.
- `homology_reference_plus_candidate_no_overlap`: 5282 reactions split into train 4469, dev 274, test 539; homology crossing count 0.
- Threshold sensitivity checked `min_seq_id` values 0.3, 0.5, 0.7, 0.9 with coverage 0.8; all had crossing count 0. The materialized primary homology split remains 0.3/0.8 as the stricter split.

Current 10H2DA candidate-extension FBA:

- Native Yeast-MetaTwin can carry demand flux to `trans-dec-2-enoyl-CoA` through `r_0120`, but cannot produce free trans-2-decenoate or 10H2DA without terminal candidate reactions.
- Adding either the free-acid route or the CoA-bound route makes 10H2DA demand feasible.
- With a 10% biomass floor, max 10H2DA demand is about `0.274011` in both terminal route designs.
- This is model feasibility, not enzyme validation; terminal thioesterase and omega-hydroxylase steps remain candidate additions.

Current training-readiness audit:

- Model reactions checked for formula/charge balance: 7512.
- Formula-balanced model reactions: 4792; charge-balanced model reactions: 5059.
- 10H2DA terminal candidate reactions checked: 4; formula-balanced: 4; charge-balanced: 4.
- Candidate unlabeled hard negatives: 1886. These are not true negatives and should be used only with conservative weighting or positive-unlabeled learning.
- Validation matrix rows: 5344, separating curated references, RXNdb-backed candidates, unresolved exclusions, and 10H2DA terminal hypotheses.

Current trained baseline model:

- Model version: `phase2_reaction_evidence_baseline_v1`.
- Task: binary reference-likeness classifier trained from curated external-crossref positives versus conservative unlabeled hard negatives.
- Training rows: 3845; train/dev/test rows: 3097/352/396.
- Test metrics: accuracy `0.949495`, precision `0.945455`, recall `0.962963`, F1 `0.954128`, ROC AUC `0.986291`, average precision `0.985283`.
- 10H2DA terminal candidate reference-likeness scores: free-acid hydroxylase `0.913918`, CoA-bound hydroxylase `0.864946`, hydroxylated-CoA thioesterase `0.775210`, trans-dec-2-enoyl-CoA thioesterase `0.717819`.
- Interpretation: this is a prioritization model, not final biochemical validation. Negative rows remain unlabeled hard negatives, and terminal enzymes still require external database or experimental support.

Current PU v2 model and remaining blockers:

- Model version: `phase2_reaction_evidence_pu_v2`.
- Training design: 25-member positive-unlabeled ensemble; each member samples 60% negative/positive ratio from unlabeled hard negatives as temporary negatives.
- Test metrics against the held-out unlabeled evaluation set: accuracy `0.944444`, precision `0.936937`, recall `0.962963`, F1 `0.949772`, ROC AUC `0.985854`, average precision `0.984997`.
- 10H2DA PU v2 terminal scores: free-acid hydroxylase `0.886367`, CoA-bound hydroxylase `0.834920`, hydroxylated-CoA thioesterase `0.741744`, trans-dec-2-enoyl-CoA thioesterase `0.686474`.
- Balance remediation audit separates `4728` training-ready mass/charge-balanced reactions, `1700` reactions that should be excluded from structure-sensitive training or handled by carrier rules, `1001` requiring manual balance review, and `87` requiring external structure mapping.
- Local 10H2DA terminal evidence search found enzyme-class support only, not exact curated substrate/reaction validation.
- CLEAN remains blocked for pretrained EC inference. UniKP and DLKcat pretrained kinetic inference are ready in isolated environments; their predictions remain prioritization evidence rather than curated validation.

Current external evidence supplement:

- External sources queried: UniProt, Rhea, PubMed.
- `CAND_T2DEC_OMEGA_HYDROXYLASE_P`: best tier `B_exact_compound_context_no_enzyme_specificity`; exact 10-HDA/10H2DA context exists, but not exact terminal omega-hydroxylation enzyme evidence.
- `CAND_T2DEC_COA_OMEGA_HYDROXYLASE_P`: best tier `D_enzyme_family_only`.
- `CAND_T2DEC_THIOESTERASE_P`: best tier `C_near_substrate_enzyme_family`.
- `CAND_10H2DA_COA_THIOESTERASE_P`: best tier `D_enzyme_family_only`.
- No 10H2DA terminal reaction currently reaches tier A. None should be promoted to curated model reaction without manual literature/database review.

Current plugin asset recovery status:

- CLEAN GitHub/paper sources are reachable and likely document downloads, including Zenodo/pretrained/checkpoint references.
- UniKP and DLKcat GitHub sources were reviewed; DLKcat is pinned to official commit `7c15d0d4a7ac029f9d75564d9f2a93874aeaaec7`.
- Some publisher pages are unreachable from this environment due HTTP restrictions/redirect behavior.
- Recovery-source availability is distinct from local readiness: CLEAN remains missing, while local UniKP and DLKcat inference gates pass.

Current plugin asset installation status:

- UniKP downloaded assets:
  - `04_prediction_plugins/UniKP/models/UniKP for kcat.pkl`
  - `04_prediction_plugins/UniKP/models/UniKP for Km.pkl`
  - `04_prediction_plugins/UniKP/models/UniKP for kcat_Km.pkl`
  - `04_prediction_plugins/UniKP/models/vocab.pkl`
  - `04_prediction_plugins/UniKP/models/trfm_12_23000.pkl`
  - `04_prediction_plugins/UniKP/models/prot_t5_xl_uniref50`
  - `04_prediction_plugins/UniKP/datasets/Kcat_combination_0918_wildtype_mutant.json`
  - `04_prediction_plugins/UniKP/datasets/Km_test_11722.pkl`
- DLKcat downloaded assets:
  - `04_prediction_plugins/DLKcat/DeeplearningApproach/Results/output/saved_model`
  - `04_prediction_plugins/DLKcat/DeeplearningApproach/Data/input.zip`
  - `04_prediction_plugins/DLKcat/DeeplearningApproach/Code/example/model.py`
  - `04_prediction_plugins/DLKcat/DeeplearningApproach/Code/example/prediction_for_input.py`
  - `04_prediction_plugins/DLKcat/data/Kcat_combination_0918_wildtype_mutant.json`
  - `04_prediction_plugins/DLKcat/data/Kcat_combination_0918.json`
  - `04_prediction_plugins/DLKcat/data/Kcat_combination_41559.tsv`
  - `04_prediction_plugins/DLKcat/example/input.tsv`
  - `04_prediction_plugins/DLKcat/example/output.tsv`
- Capability readiness after download:
  - UniKP deployed training data: ready `2/2`.
  - UniKP pretrained kinetic inference assets: present `6/6` in the recorded snapshot; runtime readiness is currently blocked pending isolated-environment validation.
  - DLKcat training raw data: ready `3/3`.
  - DLKcat example IO: ready `2/2`.
  - DLKcat fixed-input inference and three-row upstream example benchmark: ready.
  - CLEAN pretrained EC inference: still blocked `0/5`; Google Drive direct download produced only a small confirmation/HTML file, not the asset package.
- Runtime compatibility: UniKP requires an isolated Python 3.10/scikit-learn 1.2.2 environment described by `requirements-plugin-unikp.txt`. The current local legacy environment is incomplete (`transformers` is absent), so current readiness must be established by a fresh environment check and smoke run rather than the historical report alone.
- UniKP 10H2DA terminal prediction run: `98` S. cerevisiae endogenous enzyme-substrate pairs scored for kcat/Km/kcat_Km, then merged with PU score, FBA flux, external evidence tier, and local validation verdict in `06_evaluation/10h2da_terminal_enzyme_evidence_matrix.csv`.
- Important substrate caveat: `trans-2-decenoic acid` and `trans-dec-2-enoyl-CoA` SMILES are PubChem-backed; `10-hydroxy-trans-2-decenoyl-CoA` SMILES is structure-derived from the PubChem CoA thioester because no direct PubChem hit was found.
- Engineering candidate prioritization: endogenous matrix rows were sanity-filtered by enzyme family, and `18` external omega-hydroxylase/P450 enzyme-substrate pairs were added from UniProt evidence records plus a curated CYP52/CYP505/CYP4 panel. Combined engineering matrix rows: `116`; pathway design candidates: `50`.
- P450 engineering feasibility layer: `66` hydroxylase rows evaluated for P450 system type, CPR/redox partner requirement, likely localization, expression risk, host-context fit, and substrate-family fit; `80` P450-adjusted design recommendations generated.
- Current top P450-adjusted design class: free-acid or CoA-bound route using `B8QHP1` CYP52M1 from Starmerella bombicola plus endogenous TES1/PTE1 (`P41903`) thioesterase. CYP505/P450foxy (`Q9Y8G7`) is a self-sufficient fallback; mammalian CYP4 candidates remain secondary screens due expression/redox-coupling risk.
- Construct/redox design matrix: `80` construct-level design rows generated from P450-adjusted designs. Tier 1 build-first designs are `B8QHP1` CYP52M1 + TES1/PTE1 (`P41903`) for both free-acid and CoA-bound routes, with yeast NCP1/CPR1 support tested first and cognate CPR kept as fallback.
