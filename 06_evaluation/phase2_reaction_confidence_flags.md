# Phase 2 Reaction Confidence Flags

Generated: 2026-07-16T20:58:19

## Status Counts

| Status | Count |
|---|---:|
| curated_or_database_crossreferenced | 1959 |
| model_reaction_without_external_crossref | 2172 |
| underground_rxndb_provenance | 3330 |
| underground_no_selected_rxndb_match | 51 |

## Tier Counts

| Tier | Count |
|---|---:|
| external_crossref | 1959 |
| model_only | 2172 |
| prediction_provenance | 3330 |
| review_required | 51 |

## Output

- `02_id_mapping/model_reaction_confidence_flags.csv`

## Interpretation

Use `preferred_reference_label` rows as the first-pass curated training/reference pool. Use underground RXNdb rows as candidate pathway-extension evidence only after manual or additional database review. Rows marked `exclude_until_provenance_resolved` should not be used as labels.
