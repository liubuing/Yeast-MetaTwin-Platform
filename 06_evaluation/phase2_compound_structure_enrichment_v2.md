# Compound Structure Enrichment v2

Generated: 2026-07-17T12:28:13+00:00

## Net change

| Metric | Baseline | v2 | Delta |
|---|---:|---:|---:|
| Parseable structures | 2117 | 2753 | +636 |
| Unresolved structures | 1184 | 548 | -636 |
| Missing structures | 1177 | 544 | -633 |
| Parse failures | 7 | 4 | -3 |

## New mappings

| Deterministic method | Rows |
|---|---:|
| exact_chebi_id | 130 |
| exact_kegg_id | 25 |
| exact_metanetx_deprecated_redirect | 10 |
| exact_metanetx_id | 6 |
| exact_ymdb_id | 460 |
| unique_normalized_name | 5 |

Manual review conflicts: 114
Still unresolved after local exhaustion: 434

## Exhausted key spaces

For every previously unresolved row the pipeline attempted, in order: exact YMDB IDs embedded in model names; exact MetaNetX IDs; exact ChEBI primary/secondary IDs; exact KEGG IDs; exact PubChem CIDs through the local ChEBI SDF; and unique normalized names in local Yeast-GEM/YMDB tables. Formula disagreements and one-key/multiple-structure results were retained as manual review and were not promoted.

| Key space | Rows carrying key | Local candidate rows | Parseable candidate rows |
|---|---:|---:|---:|
| exact_ymdb_id | 482 | 482 | 480 |
| exact_metanetx_id | 234 | 63 | 56 |
| exact_chebi_id | 327 | 164 | 156 |
| exact_kegg_id | 218 | 176 | 167 |
| exact_pubchem_cid_via_chebi_sdf | 0 | 0 | 0 |
| unique_normalized_name | 1184 | 55 | 51 |

All 434 unresolved rows traversed all six spaces without an admissible candidate; the reason table separates absent candidates from locally present but unparsable structures. The 114 `manual_review` rows stopped at the first deterministic conflict.

| Remaining decision reason | Rows |
|---|---:|
| formula_conflict | 92 |
| local_key_space_exhausted | 429 |
| multiple_structures_for_key | 22 |
| no_parseable_local_structure | 5 |

## Outputs

- `02_id_mapping/model_compound_seed_enriched_v2.csv`
- `02_id_mapping/model_compound_structure_enrichment_v2_provenance.csv`
- `02_id_mapping/model_compound_structure_manual_review_v2.csv`
- `06_evaluation/data_quality_gate_enriched_v2/summary.json`
