# Phase 2 Execution Report

Date: 2026-07-16

## Completed

- Scanned existing Yeast-MetaTwin database and retrosynthesis assets.
- Created unified schema templates for compounds, reactions, enzyme evidence, and pathway candidates.
- Created a lightweight Phase 2 database asset scanner.
- Generated complete and key database asset inventories.
- Extracted model-based seed tables from `Yeast-MetaTwin.yml`.

## Schema Files

- `02_id_mapping/compound_schema.csv`
- `02_id_mapping/reaction_schema.csv`
- `02_id_mapping/enzyme_evidence_schema.csv`
- `02_id_mapping/pathway_candidate_schema.csv`

## Database Asset Scan Outputs

- `01_databases/phase2_database_asset_inventory.csv`
- `01_databases/phase2_key_database_assets.csv`
- `06_evaluation/phase2_database_asset_scan.md`
- `06_evaluation/phase2_database_asset_scan.json`

## Database Asset Summary

| Database guess | Files | Total size MB |
|---|---:|---:|
| ChEBI | 3 | 252.71 |
| KEGG | 1 | 2.48 |
| MetaNetX | 9 | 1274.98 |
| Model | 3 | 1.29 |
| Other | 14 | 6.72 |
| Retrosynthesis | 1020895 | 8483.55 |
| UniProt | 2 | 264.79 |
| YMDB | 6 | 10.55 |

The full retrosynthesis directory contains many chunked JSON files. The key asset inventory records the main `RXNdb_all*` and filtered retrosynthesis outputs separately for practical use.

## Seed Table Outputs

- `02_id_mapping/model_compound_seed.csv`: 3301 rows
- `02_id_mapping/model_reaction_seed.csv`: 7512 rows
- `02_id_mapping/model_enzyme_evidence_seed.csv`: 160739 rows
- `06_evaluation/phase2_seed_table_build.md`
- `06_evaluation/phase2_seed_table_build.json`

## Current Capability

The integrated deployment now has a normalized internal backbone:

- Stable internal compound IDs for all Yeast-MetaTwin metabolites.
- Stable internal reaction IDs for all Yeast-MetaTwin reactions.
- Model reaction equations, bounds, direction labels, GPR rules, genes, ORFs, and underground `rxn*` flags.
- Enzyme evidence rows derived from model GPR associations.

## Important Caveat

The enzyme evidence seed table includes broad GPR assignments from underground `rxn*` reactions. These rows are useful as candidates but should not be used as high-confidence training labels until they are filtered with curated database evidence and leakage checks.

## Next Phase

Phase 2 should continue with actual ID normalization:

- Fill SMILES, InChIKey, KEGG, ChEBI, and MetaNetX IDs in `model_compound_seed.csv` using `yeast-GEM-final.csv`, MetaNetX, ChEBI, KEGG, PubChem, and YMDB sources.
- Attach EC numbers and UniProt IDs to `model_enzyme_evidence_seed.csv` using the local UniProt TSV and model GPR.
- Build reaction cross-references between model reactions, MetaNetX reactions, Rhea/KEGG where available, and retrosynthesis RXNdb IDs.
- Add quality flags for balanced reactions, missing structures, generic compounds, and predicted-only evidence.

## Mapping Enrichment Update

Additional Phase 2 enrichment has been executed.

New script:

- `08_runtime/enrich_phase2_mappings.py`

New outputs:

- `02_id_mapping/model_compound_seed_enriched.csv`
- `02_id_mapping/model_enzyme_evidence_seed_enriched.csv`
- `06_evaluation/phase2_mapping_enrichment.md`
- `06_evaluation/phase2_mapping_enrichment.json`

Compound enrichment coverage:

| Metric | Value |
|---|---:|
| Rows | 3301 |
| Mapped by model metabolite ID | 2806 |
| SMILES non-empty | 2124 |
| InChIKey non-empty | 2124 |
| KEGG ID non-empty | 1725 |
| ChEBI ID non-empty | 2399 |
| MetaNetX ID non-empty | 2250 |

Enzyme evidence enrichment coverage:

| Metric | Value |
|---|---:|
| Rows | 160739 |
| Unique ORFs | 2057 |
| Mapped rows by ORF | 160723 |
| Mapped unique ORFs | 2047 |
| EC non-empty rows | 103187 |

Remaining Phase 2 work:

- Map the 495 MetaTwin-only metabolites not covered by `yeast-GEM-final.csv` using MetaNetX, ChEBI, KEGG, YMDB, and structure matching.
- Build reaction cross-reference tables between model reactions, MetaNetX reaction IDs, and retrosynthesis RXNdb candidates.
- Add confidence flags so curated model reactions and predicted underground `rxn*` reactions are handled differently during training.

## Reaction Cross-Reference Update

Reaction cross-reference extraction has been executed using existing Yeast-MetaTwin reaction annotations and local MetaNetX reaction properties.

New script:

- `08_runtime/build_phase2_reaction_crossrefs.py`

New outputs:

- `02_id_mapping/model_reaction_crossrefs.csv`
- `06_evaluation/phase2_reaction_crossrefs.md`
- `06_evaluation/phase2_reaction_crossrefs.json`

Coverage:

| Metric | Value |
|---|---:|
| Total model reactions | 7512 |
| Underground rxn* reactions | 3381 |
| MetaNetX cross-reference non-empty | 1675 |
| MetaNetX property match | 876 |
| KEGG reaction non-empty | 909 |
| KEGG pathway non-empty | 1891 |
| BiGG reaction non-empty | 1407 |
| SBO non-empty | 4131 |
| Underground rxn* without external cross-reference | 3381 |

Key observation:

- Existing `r_*` model reactions often carry MetaNetX, KEGG, BiGG, SBO, or pathway annotations.
- Underground `rxn*` reactions currently lack direct external cross-references in model annotations. They require a dedicated RXNdb/retrosynthesis provenance mapping pass before they can be treated as high-confidence curated reaction labels.

## Underground Reaction Provenance Update

Underground reaction provenance extraction has been executed by matching model underground reaction IDs directly against the top-level keys in the selected local RXNdb file.

New script:

- `08_runtime/build_phase2_rxn_provenance.py`

New outputs:

- `02_id_mapping/model_underground_rxn_provenance.csv`
- `06_evaluation/phase2_rxn_provenance.md`
- `06_evaluation/phase2_rxn_provenance.json`

Coverage:

| Metric | Value |
|---|---:|
| Underground rxn* model reactions | 3381 |
| RXNdb direct matches | 3330 (98.49%) |
| Missing direct matches | 51 |
| RXNdb total records | 123661 |
| With template ID | 3330 |
| With rxn_smiles_basic | 3330 |
| With rxn_smiles_final | 3330 |
| With EC number | 2560 (75.72%) |

Key observation:

- The selected RXNdb file recovers provenance for almost all underground `rxn*` model reactions by direct ID match.
- The 51 missing reactions are `rxnu*` IDs and should remain review-required until mapped against another source or manually inspected.
- RXNdb provenance provides template, EC, SMILES, and similarity evidence, but this is still prediction provenance rather than curated biochemical validation.

## Reaction Confidence Flags Update

Reaction-level confidence flags have been generated to separate curated/reference reactions from model-only context and predicted underground extensions.

New script:

- `08_runtime/build_phase2_reaction_confidence_flags.py`

New outputs:

- `02_id_mapping/model_reaction_confidence_flags.csv`
- `06_evaluation/phase2_reaction_confidence_flags.md`
- `06_evaluation/phase2_reaction_confidence_flags.json`

Status counts:

| Status | Count |
|---|---:|
| curated_or_database_crossreferenced | 1959 |
| model_reaction_without_external_crossref | 2172 |
| underground_rxndb_provenance | 3330 |
| underground_no_selected_rxndb_match | 51 |

Evidence tiers:

| Tier | Count |
|---|---:|
| external_crossref | 1959 |
| model_only | 2172 |
| prediction_provenance | 3330 |
| review_required | 51 |

Training/deployment rule:

- Use `preferred_reference_label` rows as the first-pass curated training/reference pool.
- Use `prediction_provenance` rows as candidate pathway-extension evidence after additional review, not as validated labels.
- Exclude `review_required` rows from label exports until their provenance is resolved.

## Reaction Label Export Update

Reaction label export files have been generated from the reaction seed table, reaction confidence flags, underground RXNdb provenance, and enriched enzyme evidence. The export separates training/reference labels from candidate pathway-extension evidence and unresolved reactions.

New script:

- `08_runtime/build_phase2_reaction_label_exports.py`

New outputs:

- `05_training/reaction_all_label_export_groups.csv`
- `05_training/reaction_first_pass_reference_labels.csv`
- `05_training/reaction_candidate_extension_evidence.csv`
- `05_training/reaction_model_context_only.csv`
- `05_training/reaction_excluded_review_required.csv`
- `06_evaluation/phase2_reaction_label_exports.md`
- `06_evaluation/phase2_reaction_label_exports.json`

Export counts:

| Export group | Count | Use |
|---|---:|---|
| first_pass_reference_label | 1959 | Initial reference label pool |
| candidate_extension_evidence | 3330 | Reviewed pathway-extension candidates |
| model_context_only | 2172 | Simulation/context only, not labels |
| excluded_review_required | 51 | Exclude until provenance is resolved |

Key observation:

- The first training-ready export is intentionally conservative: only externally cross-referenced reactions are marked as first-pass labels.
- RXNdb-backed underground reactions are preserved with enzyme and provenance fields, but remain candidate evidence rather than validated labels.
- The 51 `rxnu*` reactions have no direct match in the selected local RXNdb JSON or `Data_retrosynthesis` search results and are exported separately for review.

## Reaction Label Export QA Update

Reaction label export QA has been executed against `05_training/reaction_all_label_export_groups.csv`. The QA checks duplicate reaction IDs, duplicate exact model equations, evidence coverage by export group, and cross-pool overlap risk.

New script:

- `08_runtime/audit_phase2_reaction_label_exports.py`

New outputs:

- `06_evaluation/phase2_reaction_label_export_qa.md`
- `06_evaluation/phase2_reaction_label_export_qa.json`
- `06_evaluation/phase2_reaction_label_export_coverage.csv`
- `06_evaluation/phase2_reaction_label_export_duplicate_ids.csv`
- `06_evaluation/phase2_reaction_label_export_duplicate_equations.csv`
- `06_evaluation/phase2_reaction_label_export_cross_pool_overlap.csv`

QA summary:

| Metric | Value |
|---|---:|
| Total rows | 7512 |
| Duplicate reaction IDs | 0 |
| Duplicate exact model equations | 7 |
| Cross-pool overlap records | 7 |

Coverage by export group:

| Export group | Rows | GPR % | Enzyme evidence % | Enzyme EC % | External database xref % | RXNdb % | RXNdb EC % |
|---|---:|---:|---:|---:|---:|---:|---:|
| first_pass_reference_label | 1959 | 63.14 | 63.14 | 51.91 | 100.00 | 0.00 | 0.00 |
| model_context_only | 2172 | 67.77 | 67.77 | 65.93 | 0.00 | 0.00 | 0.00 |
| candidate_extension_evidence | 3330 | 100.00 | 100.00 | 98.89 | 0.00 | 100.00 | 76.88 |
| excluded_review_required | 51 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

Note:

- SBO annotations are retained in `all_crossrefs_compact`, but are not counted as external database reaction cross-references in QA.
- The remaining 7 overlap records are exact model equations appearing in both the reference and candidate pools.

## Split-Ready Reaction Pool Update

Split-ready reaction pools have been generated by excluding candidate reactions whose exact model equations overlap the first-pass reference pool.

New script:

- `08_runtime/build_phase2_split_ready_reaction_pools.py`

New outputs:

- `05_training/split_ready_reference_labels.csv`
- `05_training/split_ready_candidate_extension_no_reference_overlap.csv`
- `05_training/split_ready_candidate_reference_overlap_review.csv`
- `05_training/split_ready_reference_plus_candidate_no_overlap.csv`
- `05_training/split_ready_model_context_only.csv`
- `05_training/split_ready_excluded_review_required.csv`
- `06_evaluation/phase2_split_ready_reaction_pools.md`
- `06_evaluation/phase2_split_ready_reaction_pools.json`

Split-ready counts:

| Pool | Count |
|---|---:|
| reference_labels | 1959 |
| candidate_extension_no_reference_overlap | 3323 |
| candidate_reference_overlap_review | 7 |
| reference_plus_candidate_no_overlap | 5282 |
| model_context_only | 2172 |
| excluded_review_required | 51 |

Training/deployment rule:

- Use `split_ready_reference_labels.csv` for the conservative reference label pool.
- Use `split_ready_reference_plus_candidate_no_overlap.csv` only when candidate extension evidence is intentionally included.
- Keep `split_ready_candidate_reference_overlap_review.csv` out of naive train/test splits to avoid exact equation leakage.

## Reaction Split Definition Update

Deterministic train/dev/test split definitions have been generated for the conservative reference-only pool and the reference-plus-candidate no-overlap pool.

New script:

- `08_runtime/build_phase2_reaction_split_definitions.py`

New outputs:

- `05_training/split_definitions_reference_only.csv`
- `05_training/split_definitions_reference_plus_candidate_no_overlap.csv`
- `06_evaluation/phase2_reaction_split_definitions.md`
- `06_evaluation/phase2_reaction_split_definitions.json`

Split rule:

- `split_key = exact model equation` when present.
- Fallback: `model reaction ID`.
- Assignment: `SHA256(split_key) % 100`, with train `<80`, dev `80-89`, test `>=90`.

Split counts:

| Pool | Rows | Train | Dev | Test | Split keys crossing splits |
|---|---:|---:|---:|---:|---:|
| reference_only | 1959 | 1593 | 172 | 194 | 0 |
| reference_plus_candidate_no_overlap | 5282 | 4250 | 503 | 529 | 0 |

Important limitation:

- This is a deterministic exact-equation structural split. It is not a homology-cold split and does not prevent enzyme sequence family leakage. Homology-aware splitting still requires MMseqs2/CD-HIT or an equivalent clustering step.

## Training Manifest Update

Training manifests have been generated for the current split definition files. These manifests record file hashes, row counts, column counts, split distributions, and training-role distributions, providing a reproducible data handoff point before any model training.

New script:

- `08_runtime/build_phase2_training_manifests.py`

New outputs:

- `05_training/training_manifest_reference_only.json`
- `05_training/training_manifest_reference_plus_candidate_no_overlap.json`
- `05_training/training_manifest_index.csv`
- `06_evaluation/phase2_training_manifests.md`
- `06_evaluation/phase2_training_manifests.json`

Manifest summary:

| Manifest | Rows | Columns | Train | Dev | Test |
|---|---:|---:|---:|---:|---:|
| reference_only | 1959 | 39 | 1593 | 172 | 194 |
| reference_plus_candidate_no_overlap | 5282 | 39 | 4250 | 503 | 529 |

Input hashes:

| Manifest | Primary input SHA256 |
|---|---|
| reference_only | `0e59e39b72bc24d66b9673e1cfa70884b78dd769b12555a49033a7f926cd504c` |
| reference_plus_candidate_no_overlap | `b36c66d748accc55332f85c55a46dd7a479059eb7053ef36774dd03f526ce171` |

## Homology Split Readiness Update

Homology-cold split readiness has been checked for tool availability, FASTA assets, and ORF coverage in the split definition pools.

New script:

- `08_runtime/check_phase2_homology_split_readiness.py`

New outputs:

- `06_evaluation/phase2_homology_split_readiness.md`
- `06_evaluation/phase2_homology_split_readiness.json`
- `06_evaluation/phase2_homology_split_missing_orfs.csv`

Tool availability:

| Tool | Available |
|---|---:|
| mmseqs | False |
| cd-hit | False |
| cd-hit-est | False |

FASTA assets:

| FASTA | Header IDs |
|---|---:|
| `Data/Saccharomyces_cerevisiae.fasta` | 5911 |
| `Code/ECnumber_prediction/CLEAN/data/Saccharomyces_cerevisiae.fasta` | 5911 |
| `audit/clean_unique_sequences.fasta` | 191460 |

ORF coverage:

| Pool | Rows with ORFs | Unique ORFs | ORFs in FASTA | Missing ORFs |
|---|---:|---:|---:|---:|
| reference_only | 1237 | 1033 | 1033 | 0 |
| reference_plus_candidate_no_overlap | 4560 | 1746 | 1745 | 1 |

Conclusion:

- Homology-cold split is not ready because MMseqs2/CD-HIT is unavailable on PATH.
- Sequence coverage is effectively sufficient; the only missing ORF is the placeholder `nogene`.

## Exact-Sequence Split Update

An exact-sequence split has been added as an executable intermediate between structural exact-equation splits and true homology-cold splits. It does not require MMseqs2/CD-HIT. For reactions with ORF-associated protein sequences, the split key is the sorted set of SHA256 protein sequence hashes. Reactions without matched ORF sequences fall back to exact equation and are listed separately.

New script:

- `08_runtime/build_phase2_exact_sequence_splits.py`

New outputs:

- `05_training/exact_sequence_split_reference_only.csv`
- `05_training/exact_sequence_split_reference_plus_candidate_no_overlap.csv`
- `06_evaluation/phase2_exact_sequence_splits.md`
- `06_evaluation/phase2_exact_sequence_splits.json`
- `06_evaluation/phase2_exact_sequence_split_fallback_rows.csv`

Split counts:

| Pool | Rows | Train | Dev | Test | Exact-sequence keys | Crossing keys | Fallback rows |
|---|---:|---:|---:|---:|---:|---:|---:|
| reference_only | 1959 | 1583 | 188 | 188 | 1491 | 0 | 722 |
| reference_plus_candidate_no_overlap | 5282 | 4028 | 862 | 392 | 1653 | 0 | 727 |

Manifest update:

- `05_training/training_manifest_exact_sequence_reference_only.json`
- `05_training/training_manifest_exact_sequence_reference_plus_candidate_no_overlap.json`

Important limitation:

- Exact-sequence split prevents identical protein sequence sets from crossing train/dev/test, but it does not prevent homologous but non-identical protein families from crossing splits. True homology-cold splitting still requires MMseqs2/CD-HIT or an equivalent clustering method.

## MMseqs2 Installation and Homology Split Update

MMseqs2 has been added locally and used to generate homology-aware split definitions. The Windows binary is installed under the deployment `tools` folder and can report its version, but its clustering workflow invokes generated shell scripts that fail under the current PowerShell execution path. A Linux MMseqs2 binary was therefore installed for WSL execution under the approved local temp tools path.

Installed tools:

| Tool | Status | Path |
|---|---|---|
| MMseqs2 Windows | Installed, version command works | `tools/mmseqs2/mmseqs/bin/mmseqs.exe` |
| MMseqs2 WSL/Linux | Installed and used for clustering | `<MMSEQS2_PATH>` |
| CD-HIT | Not installed | No Windows binary found in release assets; source build or conda/WSL install still needed if CD-HIT specifically required |

New script:

- `08_runtime/build_phase2_mmseqs_homology_splits.py`

New outputs:

- `05_training/homology_split_reference_only.csv`
- `05_training/homology_split_reference_plus_candidate_no_overlap.csv`
- `05_training/mmseqs_homology_clusters/yeast_orf_minid0_3_cov0_8_cluster.tsv`
- `06_evaluation/phase2_mmseqs_homology_splits.md`
- `06_evaluation/phase2_mmseqs_homology_splits.json`
- `06_evaluation/phase2_mmseqs_homology_split_fallback_rows.csv`
- `06_evaluation/phase2_mmseqs_homology_split_runlog.json`

MMseqs2 parameters:

- `--min-seq-id 0.3`
- `-c 0.8`
- `--cov-mode 0`

Clustering summary:

| Metric | Value |
|---|---:|
| Input ORFs | 1745 |
| FASTA sequences written | 1745 |
| ORFs missing sequence | 0 |
| MMseqs2 clusters | 1416 |

Homology split counts:

| Pool | Rows | Train | Dev | Test | Homology keys | Crossing keys | Fallback rows |
|---|---:|---:|---:|---:|---:|---:|---:|
| reference_only | 1959 | 1584 | 159 | 216 | 1376 | 0 | 722 |
| reference_plus_candidate_no_overlap | 5282 | 4469 | 274 | 539 | 1538 | 0 | 727 |

Manifest update:

- `05_training/training_manifest_mmseqs_homology_reference_only.json`
- `05_training/training_manifest_mmseqs_homology_reference_plus_candidate_no_overlap.json`

Important limitation:

- The split is homology-aware over available yeast ORF sequences clustered by MMseqs2. Reactions without ORFs still fall back to exact equation. CD-HIT remains unavailable unless compiled or installed through another environment.

## MMseqs2 Threshold Sensitivity Update

MMseqs2 homology split threshold sensitivity has been executed for multiple sequence identity cutoffs while holding coverage fixed at 0.8 and coverage mode fixed at 0.

New script:

- `08_runtime/audit_phase2_mmseqs_threshold_sensitivity.py`

New outputs:

- `06_evaluation/phase2_mmseqs_threshold_sensitivity.md`
- `06_evaluation/phase2_mmseqs_threshold_sensitivity.csv`
- `06_evaluation/phase2_mmseqs_threshold_sensitivity.json`
- `06_evaluation/phase2_mmseqs_threshold_0_3_runlog.json`
- `06_evaluation/phase2_mmseqs_threshold_0_5_runlog.json`
- `06_evaluation/phase2_mmseqs_threshold_0_7_runlog.json`
- `06_evaluation/phase2_mmseqs_threshold_0_9_runlog.json`

Sensitivity summary:

| min_seq_id | Pool | Clusters | Train | Dev | Test | Homology keys | Crossing keys | Fallback rows |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 0.3 | reference_only | 1416 | 1584 | 159 | 216 | 1376 | 0 | 722 |
| 0.3 | reference_plus_candidate_no_overlap | 1416 | 4469 | 274 | 539 | 1538 | 0 | 727 |
| 0.5 | reference_only | 1522 | 1584 | 163 | 212 | 1435 | 0 | 722 |
| 0.5 | reference_plus_candidate_no_overlap | 1522 | 4346 | 288 | 648 | 1597 | 0 | 727 |
| 0.7 | reference_only | 1621 | 1581 | 178 | 200 | 1473 | 0 | 722 |
| 0.7 | reference_plus_candidate_no_overlap | 1621 | 4526 | 300 | 456 | 1635 | 0 | 727 |
| 0.9 | reference_only | 1699 | 1556 | 184 | 219 | 1489 | 0 | 722 |
| 0.9 | reference_plus_candidate_no_overlap | 1699 | 3653 | 792 | 837 | 1651 | 0 | 727 |

Interpretation:

- Lower `min_seq_id` creates broader clusters and stricter homology separation.
- Higher `min_seq_id` approaches exact-sequence splitting.
- All tested thresholds have 0 homology keys crossing splits.
- The materialized primary homology split remains `min_seq_id=0.3`, `coverage=0.8`, `cov_mode=0` because it is the stricter default among the tested settings.

## 10H2DA Candidate Extension FBA Update

10H2DA model-extension feasibility testing has been executed without modifying the source Yeast-MetaTwin YAML model. Candidate metabolites and reactions are added in memory, then demand/FBA tests are run for the target and precursor nodes.

New script:

- `08_runtime/test_10h2da_candidate_extension_fba.py`

New outputs:

- `07_reports/10H2DA_candidate_extension_fba.md`
- `06_evaluation/10h2da_candidate_extension_fba.csv`
- `06_evaluation/10h2da_candidate_extension_fba.json`

Candidate terminal route designs:

| Route | Candidate reactions | Result |
|---|---|---|
| Target demand only | Adds demand reactions but no terminal chemistry | `trans-dec-2-enoyl-CoA` is feasible; 10H2DA is not feasible |
| Free-acid route | enoyl-CoA thioesterase plus free-acid omega-hydroxylase | 10H2DA demand feasible |
| CoA-bound route | CoA-bound omega-hydroxylase plus hydroxylated thioesterase | 10H2DA demand feasible |

Key FBA results:

| Scenario | Objective | Biomass floor | Max flux |
|---|---|---:|---:|
| target_demand_only | `DM_s_1507` | none | 0.140091 |
| target_demand_only | `DM_CAND_10H2DA_P` | none | 0 |
| free_acid_terminal_route | `DM_CAND_10H2DA_P` | none | 0.302724 |
| free_acid_terminal_route | `DM_CAND_10H2DA_P` | 10% native biomass | 0.274011 |
| coa_bound_terminal_route | `DM_CAND_10H2DA_P` | none | 0.302724 |
| coa_bound_terminal_route | `DM_CAND_10H2DA_P` | 10% native biomass | 0.274011 |

Interpretation:

- The current model can supply the C10 trans-2-enoyl-CoA precursor and peroxisomal cofactors.
- 10H2DA production requires terminal candidate chemistry. Positive demand flux after adding those reactions is feasibility evidence, not proof of enzyme specificity.

## Training Readiness Audit Update

Training-readiness auditing has been executed across label quality, feature coverage, reaction mass/charge balance, conservative negative-sample design, and validation action classes.

New script:

- `08_runtime/audit_phase2_training_readiness.py`

New outputs:

- `06_evaluation/phase2_training_readiness_audit.md`
- `06_evaluation/phase2_training_readiness_audit.json`
- `06_evaluation/phase2_reaction_balance_audit.csv`
- `06_evaluation/phase2_feature_label_quality.csv`
- `05_training/reaction_negative_sample_candidates.csv`
- `06_evaluation/phase2_candidate_validation_matrix.csv`

Balance summary:

| Metric | Value |
|---|---:|
| Model reactions checked | 7512 |
| Model formula-balanced reactions | 4792 |
| Model charge-balanced reactions | 5059 |
| 10H2DA candidate reactions checked | 4 |
| 10H2DA candidate formula-balanced reactions | 4 |
| 10H2DA candidate charge-balanced reactions | 4 |
| Model rows with missing formulas | 1661 |
| Model rows with unparsable formulas | 139 |

Feature and label quality summary:

| Export group | Rows | All SMILES % | GPR % | EC % | External xref % | RXNdb % |
|---|---:|---:|---:|---:|---:|---:|
| first_pass_reference_label | 1959 | 91.32 | 63.14 | 51.91 | 100.00 | 0.00 |
| model_context_only | 2172 | 41.39 | 67.77 | 65.93 | 0.00 | 0.00 |
| candidate_extension_evidence | 3330 | 52.82 | 100.00 | 98.89 | 0.00 | 100.00 |
| excluded_review_required | 51 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

Negative-sample design:

- `1886` model-context reactions were exported as candidate unlabeled hard negatives.
- These rows are not true negatives. Use them only with conservative weighting, positive-unlabeled learning, or explicit downstream review.

Validation matrix:

- `5344` rows separate curated references, RXNdb-backed candidate extensions, unresolved exclusions, and 10H2DA terminal hypotheses.
- 10H2DA terminal candidates are mass/charge balanced and FBA-feasible after addition, but still need external enzyme/database/experimental evidence before label promotion.

## Reaction Evidence Baseline Training Update

A first-pass reaction evidence baseline model has been trained. This is intentionally a conservative baseline, not the final enzyme-specific pathway predictor. It learns a reference-likeness score from curated external-crossref reactions versus conservative unlabeled hard negatives, then scores RXNdb-backed candidates and 10H2DA terminal hypotheses.

New script:

- `08_runtime/train_phase2_reaction_evidence_baseline.py`

New outputs:

- `03_models/phase2_reaction_evidence_baseline_v1.joblib`
- `03_models/phase2_reaction_evidence_baseline_v1_manifest.json`
- `05_training/reaction_evidence_baseline_training_matrix.csv`
- `06_evaluation/phase2_reaction_evidence_baseline_metrics.json`
- `06_evaluation/phase2_reaction_evidence_baseline_metrics.csv`
- `06_evaluation/phase2_candidate_extension_evidence_scores.csv`
- `06_evaluation/10h2da_terminal_candidate_scores.csv`
- `07_reports/phase2_reaction_evidence_baseline_training.md`

Dataset:

| Split | Rows | Positives | Negatives |
|---|---:|---:|---:|
| train | 3097 | 1584 | 1513 |
| dev | 352 | 159 | 193 |
| test | 396 | 216 | 180 |

Metrics:

| Split | Accuracy | Precision | Recall | F1 | ROC AUC | Average precision |
|---|---:|---:|---:|---:|---:|---:|
| train | 0.959961 | 0.938175 | 0.986742 | 0.961846 | 0.995501 | 0.995529 |
| dev | 0.937500 | 0.900585 | 0.968553 | 0.933333 | 0.988692 | 0.988093 |
| test | 0.949495 | 0.945455 | 0.962963 | 0.954128 | 0.986291 | 0.985283 |

10H2DA terminal candidate scores:

| Candidate reaction | Reference-likeness score |
|---|---:|
| `CAND_T2DEC_THIOESTERASE_P` | 0.717819 |
| `CAND_T2DEC_OMEGA_HYDROXYLASE_P` | 0.913918 |
| `CAND_T2DEC_COA_OMEGA_HYDROXYLASE_P` | 0.864946 |
| `CAND_10H2DA_COA_THIOESTERASE_P` | 0.775210 |

Important limitation:

- The model excludes direct external cross-reference and RXNdb ID fields from features to reduce direct label leakage, but it still uses reaction text, EC/GPR text, and simple structural metadata. Candidate scores should be used for prioritization only.
- The negative class consists of conservative unlabeled hard negatives, not experimentally disproven reactions.
- Enzyme specificity for 10H2DA terminal chemistry still requires database, literature, or experimental validation before curated promotion.

## PU v2 Training, Balance Remediation, Terminal Validation, And Plugin Asset Update

The main unresolved items have been converted into repeatable audits or a stronger training run.

New scripts:

- `08_runtime/audit_phase2_balance_remediation.py`
- `08_runtime/validate_10h2da_terminal_evidence.py`
- `08_runtime/train_phase2_reaction_evidence_pu_v2.py`
- `08_runtime/audit_phase2_plugin_asset_readiness.py`

New outputs:

- `06_evaluation/phase2_balance_remediation_audit.md`
- `06_evaluation/phase2_balance_remediation_reaction_flags.csv`
- `06_evaluation/phase2_balance_remediation_metabolite_issues.csv`
- `07_reports/10H2DA_terminal_evidence_validation.md`
- `06_evaluation/10h2da_terminal_evidence_matches.csv`
- `06_evaluation/10h2da_terminal_yeast_enzyme_candidates.csv`
- `06_evaluation/10h2da_terminal_validation_verdicts.csv`
- `03_models/phase2_reaction_evidence_pu_v2.joblib`
- `03_models/phase2_reaction_evidence_pu_v2_manifest.json`
- `07_reports/phase2_reaction_evidence_pu_v2_training.md`
- `06_evaluation/phase2_candidate_extension_evidence_pu_v2_scores.csv`
- `06_evaluation/10h2da_terminal_candidate_pu_v2_scores.csv`
- `06_evaluation/phase2_plugin_asset_readiness.md`

Balance remediation summary:

| Category | Reactions |
|---|---:|
| training_ready_mass_charge_balanced | 4728 |
| exclude_from_structure_sensitive_training_or_apply_curated_carrier_rules | 1700 |
| requires_manual_balance_review | 1001 |
| requires_external_structure_mapping | 87 |

Metabolite issue summary:

| Category | Metabolites | Occurrences |
|---|---:|---:|
| underground_template_metabolite_missing_formula | 393 | 1903 |
| generic_r_group_or_polymer_formula | 173 | 317 |
| missing_formula_no_local_mapping | 124 | 152 |
| macromolecule_or_redox_carrier_formula | 5 | 8 |

PU v2 model:

| Item | Value |
|---|---:|
| Ensemble members | 25 |
| Unlabeled temporary-negative sampling ratio | 0.6 |
| Test accuracy | 0.944444 |
| Test precision | 0.936937 |
| Test recall | 0.962963 |
| Test F1 | 0.949772 |
| Test ROC AUC | 0.985854 |
| Test average precision | 0.984997 |

10H2DA PU v2 terminal candidate scores:

| Candidate reaction | PU reference-likeness score |
|---|---:|
| `CAND_T2DEC_OMEGA_HYDROXYLASE_P` | 0.886367 |
| `CAND_T2DEC_COA_OMEGA_HYDROXYLASE_P` | 0.834920 |
| `CAND_10H2DA_COA_THIOESTERASE_P` | 0.741744 |
| `CAND_T2DEC_THIOESTERASE_P` | 0.686474 |

10H2DA terminal validation:

- Local database search found enzyme-class support only for thioesterase and oxygenase/hydroxylase/P450 classes.
- No direct local curated record was found for exact 10H2DA terminal substrate specificity or exact terminal reaction validation.
- Terminal reactions remain mass/charge-balanced, FBA-feasible hypotheses until external database/literature/experimental support is added.

Plugin asset readiness:

| Plugin | Required | Present | Missing | Status |
|---|---:|---:|---:|---|
| CLEAN | 5 | 0 | 5 | blocked_missing_assets |
| UniKP | 3 | 0 | 3 | blocked_missing_assets |
| DLKcat | 3 | 0 | 3 | blocked_missing_assets |

Interpretation:

- A real local model has now been trained twice: v1 baseline and v2 PU ensemble. v2 better respects the fact that negative rows are unlabeled hard negatives.
- Full enzyme-function or kinetic retraining through CLEAN/UniKP/DLKcat cannot be completed from the current local workspace because required pretrained/raw assets are absent.

## External Evidence Supplement And Plugin Recovery Source Update

External evidence and plugin recovery-source audits have been added with explicit separation between evidence levels and local asset availability.

New scripts:

- `08_runtime/collect_10h2da_external_evidence.py`
- `08_runtime/audit_phase2_plugin_asset_recovery_sources.py`

New outputs:

- `07_reports/10H2DA_external_evidence_supplement.md`
- `06_evaluation/10h2da_external_evidence_records.csv`
- `06_evaluation/10h2da_external_evidence_verdicts.csv`
- `06_evaluation/10h2da_external_evidence_supplement.json`
- `06_evaluation/phase2_plugin_asset_recovery_sources.md`
- `06_evaluation/phase2_plugin_asset_recovery_sources.csv`
- `06_evaluation/phase2_plugin_asset_recovery_sources.json`

External evidence tier definitions:

| Tier | Meaning | Promotion rule |
|---|---|---|
| A | Exact substrate or exact reaction candidate with enzyme/reaction context | Manual curation can consider promotion |
| B | Exact target compound context but no enzyme-specific terminal reaction | Prioritization only |
| C | Near substrate plus enzyme-family evidence | Prioritization only |
| D | Enzyme-family-only or near-substrate-only evidence | Weak support only |
| E | Weak keyword context only | Do not use for promotion |
| Z | Query/source error | Not evidence |

10H2DA terminal external evidence verdicts:

| Candidate reaction | Best tier | Records | Action |
|---|---|---:|---|
| `CAND_T2DEC_OMEGA_HYDROXYLASE_P` | `B_exact_compound_context_no_enzyme_specificity` | 32 | Prioritization only; no curated promotion |
| `CAND_T2DEC_COA_OMEGA_HYDROXYLASE_P` | `D_enzyme_family_only` | 55 | Enzyme-class support only |
| `CAND_T2DEC_THIOESTERASE_P` | `C_near_substrate_enzyme_family` | 17 | Prioritization only; no curated promotion |
| `CAND_10H2DA_COA_THIOESTERASE_P` | `D_enzyme_family_only` | 22 | Enzyme-class support only |

Important correction:

- A PubMed record with activity toward trans-10-hydroxy-2-decenoic acid was found, but it is a fumarate reductase context rather than terminal omega-hydroxylation biosynthesis. The tiering logic was tightened so this counts as exact compound context, not exact terminal reaction validation.

Plugin asset recovery-source status:

| Plugin | Source status | Local asset status |
|---|---|---|
| CLEAN | GitHub and paper sources reachable; Zenodo/pretrained/checkpoint keywords detected | Still missing locally |
| UniKP | GitHub source reachable; pretrained/data/model keywords detected | Still missing locally |
| DLKcat | GitHub source reachable; download/model/data keywords detected | Still missing locally |

Interpretation:

- External evidence has improved prioritization but has not validated exact 10H2DA terminal biosynthesis.
- Plugin assets have plausible recovery sources, but no plugin should be marked ready until the required files are downloaded and pass `phase2_plugin_asset_readiness`.

## Plugin Asset Download And Runtime Compatibility Update

Plugin asset recovery was attempted directly from official sources where public direct-download URLs were available.

Downloaded UniKP assets:

| Asset | Path | Status |
|---|---|---|
| UniKP kcat model | `04_prediction_plugins/UniKP/models/UniKP for kcat.pkl` | downloaded |
| UniKP Km model | `04_prediction_plugins/UniKP/models/UniKP for Km.pkl` | downloaded |
| UniKP kcat/Km model | `04_prediction_plugins/UniKP/models/UniKP for kcat_Km.pkl` | downloaded |
| SMILES Transformer vocab | `04_prediction_plugins/UniKP/models/vocab.pkl` | downloaded |
| SMILES Transformer weights | `04_prediction_plugins/UniKP/models/trfm_12_23000.pkl` | downloaded |
| UniKP Kcat dataset | `04_prediction_plugins/UniKP/datasets/Kcat_combination_0918_wildtype_mutant.json` | downloaded |
| UniKP Km test dataset | `04_prediction_plugins/UniKP/datasets/Km_test_11722.pkl` | downloaded |

Downloaded DLKcat assets:

| Asset | Path | Status |
|---|---|---|
| DLKcat Kcat wildtype/mutant JSON | `04_prediction_plugins/DLKcat/data/Kcat_combination_0918_wildtype_mutant.json` | downloaded |
| DLKcat Kcat JSON | `04_prediction_plugins/DLKcat/data/Kcat_combination_0918.json` | downloaded |
| DLKcat Kcat TSV | `04_prediction_plugins/DLKcat/data/Kcat_combination_41559.tsv` | downloaded |
| DLKcat example input | `04_prediction_plugins/DLKcat/example/input.tsv` | downloaded |
| DLKcat example output | `04_prediction_plugins/DLKcat/example/output.tsv` | downloaded |

Updated capability readiness:

| Plugin | Capability | Required | Present | Missing | Status |
|---|---|---:|---:|---:|---|
| CLEAN | pretrained_ec_inference | 5 | 0 | 5 | blocked_missing_assets |
| UniKP | deployed_training_data | 2 | 2 | 0 | ready |
| UniKP | pretrained_kinetic_inference | 6 | 6 | 0 | ready |
| UniKP | training_raw_data | 3 | 0 | 3 | blocked_missing_assets |
| DLKcat | training_raw_data | 3 | 3 | 0 | ready |
| DLKcat | example_inference_io | 2 | 2 | 0 | ready |
| DLKcat | legacy_training_input | 3 | 0 | 3 | blocked_missing_assets |

Runtime compatibility:

- New report: `06_evaluation/phase2_plugin_runtime_compatibility.md`.
- System Python 3.14 / scikit-learn 1.9 cannot load UniKP old sklearn pickles due tree dtype incompatibility.
- A dedicated short-path environment was created at `C:\ymt\unikp_sklearn12` using Python 3.10.20, scikit-learn 1.2.2, torch 2.13.0+cpu, transformers, and sentencepiece.
- In this environment, all downloaded UniKP local assets load successfully: `trfm_12_23000.pkl`, `vocab.pkl`, `UniKP for kcat.pkl`, `UniKP for Km.pkl`, `UniKP for kcat_Km.pkl`, and `prot_t5_xl_uniref50` as `T5EncoderModel`.
- scikit-learn still emits version warnings because the models were serialized from scikit-learn 0.24.2, but loading no longer fails.
- Complete UniKP kinetic inference is no longer blocked by missing pretrained assets; end-to-end target sequence/SMILES feature generation and prediction has been run for the current endogenous 10H2DA terminal candidate set.

CLEAN status:

- CLEAN pretrained package is only available through Google Drive from the README. Direct `uc?export=download` access produced a small confirmation/HTML file, not the archive.
- `gdown` could not be installed from the configured pip mirror due HTTP 403, so CLEAN remains manual-download-required in this environment.

Interpretation:

- Asset recovery has materially improved UniKP/DLKcat data availability.
- UniKP pretrained kinetic inference assets and runtime loading are ready in `C:\ymt\unikp_sklearn12`; DLKcat data/example assets are ready, while legacy source-project paths remain missing.
- CLEAN remains not installed because pretrained package download requires manual/specialized Google Drive handling.

## 10H2DA UniKP terminal prioritization

Runtime script:

- `08_runtime/predict_10h2da_unikp_and_evidence_matrix.py`

Generated outputs:

- `06_evaluation/10h2da_unikp_terminal_predictions.csv`
- `06_evaluation/10h2da_terminal_enzyme_evidence_matrix.csv`
- `06_evaluation/10h2da_unikp_terminal_prediction_manifest.json`
- `07_reports/10H2DA_unikp_terminal_prioritization.md`

Run summary:

- Environment: `C:\ymt\unikp_sklearn12\Scripts\python.exe`.
- Candidate enzyme-substrate pairs scored: `98` endogenous S. cerevisiae pairs.
- UniKP assets used: SMILES Transformer `trfm_12_23000.pkl`, `vocab.pkl`, ProtT5 encoder `prot_t5_xl_uniref50`, and pretrained `kcat`, `Km`, `kcat_Km` ExtraTreesRegressor models.
- The matrix merges UniKP kinetic predictions with reaction PU score, best candidate FBA flux, external evidence tier, and local validation verdict.

Substrate provenance:

- `trans-2-decenoic acid`: PubChem CID 5282724 isomeric SMILES.
- `trans-dec-2-enoyl-CoA`: PubChem CID 24883423 isomeric SMILES.
- `10-hydroxy-trans-2-decenoyl-CoA`: structure-derived from PubChem trans-dec-2-enoyl-CoA by omega hydroxyl substitution; no direct PubChem hit was found.

Interpretation:

- UniKP values are enzyme-substrate prioritization evidence, not curated kinetic measurements and not proof of exact terminal reaction chemistry.
- PU/FBA/UniKP/external literature evidence remain separate columns in the terminal evidence matrix and should not be collapsed into a single validation label.
- Current top-ranked endogenous candidates still only have enzyme-class or near-substrate support; no terminal 10H2DA reaction reaches exact A-tier validation.

## 10H2DA engineering candidate prioritization

Runtime script:

- `08_runtime/prioritize_10h2da_engineering_candidates.py`

Generated outputs:

- `06_evaluation/10h2da_external_omega_hydroxylase_unikp_predictions.csv`
- `06_evaluation/10h2da_engineering_candidate_matrix.csv`
- `06_evaluation/10h2da_pathway_design_candidates.csv`
- `06_evaluation/10h2da_engineering_candidate_prioritization_manifest.json`
- `07_reports/10H2DA_engineering_candidate_prioritization.md`

Run summary:

- Endogenous rows sanity-filtered: `98`.
- External omega-hydroxylase/P450 enzyme-substrate pairs added and UniKP-scored: `18`.
- Combined engineering candidate rows: `116`.
- Pathway design candidate rows: `50`.

Priority result:

- Endogenous thioesterase ranking is now family-filtered, with TES1/PTE1 (`P41903`) preferred over weak ubiquitin/protein thioesterase keyword hits despite some high raw UniKP values in those weaker families.
- External fatty-acid omega-hydroxylase/P450 candidates outrank endogenous weak oxygenase keyword hits for both free-acid and CoA-bound hydroxylation designs.
- The current top route class is CoA-bound hydroxylation with an external fatty-acid omega-hydroxylase/P450 candidate plus endogenous TES1/PTE1 thioesterase.

Interpretation:

- External enzyme candidates are engineering options, not native S. cerevisiae model evidence.
- Engineering priority combines family sanity, UniKP kinetic prioritization, PU score, FBA route feasibility, and external evidence tier. It does not prove exact terminal 10H2DA chemistry.

## 10H2DA P450 engineering feasibility layer

Runtime script:

- `08_runtime/build_10h2da_p450_feasibility_layer.py`

Generated outputs:

- `06_evaluation/10h2da_p450_engineering_feasibility_matrix.csv`
- `06_evaluation/10h2da_p450_design_recommendations.csv`
- `06_evaluation/10h2da_p450_engineering_feasibility_manifest.json`
- `07_reports/10H2DA_p450_engineering_feasibility.md`

Run summary:

- Hydroxylase rows evaluated: `66`.
- P450-adjusted design recommendation rows: `80`.
- Feasibility fields added: P450 system type, redox partner requirement, localization expectation, expression risk, substrate-family fit, host-context fit, and recommended P450 action.

Priority result after P450 feasibility correction:

- `B8QHP1` CYP52M1 from Starmerella bombicola becomes the highest-priority engineering P450 candidate because it combines fatty-acid omega-hydroxylase family evidence with yeast/fungal host compatibility.
- `Q9Y8G7` P450foxy/CYP505 from Fusarium oxysporum is prioritized as a self-sufficient P450 fallback because it has an internal reductase domain and reduces CPR coupling risk.
- Mammalian CYP4/CYP4F candidates remain useful secondary screens but are penalized for heterologous microsomal P450 expression and redox-coupling risk.
- Endogenous yeast CYP/oxygenase hits remain low-expression-risk but activity-limited because their native substrate classes are distant from 10H2DA terminal omega-hydroxylation.

Interpretation:

- This layer addresses the main engineering shortfall in the previous matrix: high UniKP/family scores alone do not capture P450 expression, localization, and redox-partner feasibility.
- The current best experimental design family is CYP52M1 or CYP505/P450foxy plus endogenous TES1/PTE1 thioesterase, with both free-acid and CoA-bound routes retained for testing.

## 10H2DA construct and redox design matrix

Runtime script:

- `08_runtime/build_10h2da_construct_design_matrix.py`

Generated outputs:

- `06_evaluation/10h2da_construct_design_matrix.csv`
- `06_evaluation/10h2da_construct_design_manifest.json`
- `07_reports/10H2DA_construct_design_matrix.md`

Run summary:

- Construct-level design rows: `80`.
- Tier counts: `tier1_build_first` = `2`, `tier2_parallel_or_followup` = `8`, `tier3_secondary_screen` = `39`, `tier4_deprioritize` = `31`.

Design translation:

- Tier 1 design 1: free-acid route with `B8QHP1` CYP52M1 and endogenous TES1/PTE1 (`P41903`).
- Tier 1 design 2: CoA-bound route with `B8QHP1` CYP52M1 and endogenous TES1/PTE1 (`P41903`).
- For CYP52M1 designs, yeast NCP1/CPR1 support is listed as the first redox-partner strategy, with cognate CPR retained as fallback if available.
- CYP505/P450foxy designs are kept as follow-up because the internal reductase domain reduces CPR uncertainty.

Readout and control separation:

- Matrix fields include route intermediates to monitor, negative controls, process controls, construct comparison controls, and primary readout.
- The report intentionally remains a design checklist, not a wet-lab protocol; it does not promote UniKP/P450 feasibility scores to curated biochemical validation.
