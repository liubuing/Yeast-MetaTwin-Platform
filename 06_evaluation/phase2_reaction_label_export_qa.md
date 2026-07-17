# Phase 2 Reaction Label Export QA

Generated: 2026-07-16T20:58:25

## Summary

| Metric | Value |
|---|---:|
| Total rows | 7512 |
| Duplicate reaction IDs | 0 |
| Duplicate model equations | 7 |
| Cross-pool overlap records | 7 |

## Coverage By Export Group

| Export group | Rows | GPR % | Enzyme evidence % | Enzyme EC % | External database xref % | RXNdb % | RXNdb EC % |
|---|---:|---:|---:|---:|---:|---:|---:|
| first_pass_reference_label | 1959 | 63.14 | 63.14 | 51.91 | 100.00 | 0.00 | 0.00 |
| model_context_only | 2172 | 67.77 | 67.77 | 65.93 | 0.00 | 0.00 | 0.00 |
| candidate_extension_evidence | 3330 | 100.00 | 100.00 | 98.89 | 0.00 | 100.00 | 76.88 |
| excluded_review_required | 51 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

## Output Files

- `06_evaluation/phase2_reaction_label_export_qa.json`
- `06_evaluation/phase2_reaction_label_export_coverage.csv`
- `06_evaluation/phase2_reaction_label_export_duplicate_ids.csv`
- `06_evaluation/phase2_reaction_label_export_duplicate_equations.csv`
- `06_evaluation/phase2_reaction_label_export_cross_pool_overlap.csv`

## Interpretation

Duplicate model equations are expected in compartment-specific or direction-specific model reactions, but they should be reviewed before creating ML splits. Cross-pool overlap records identify exact equations or external cross-references appearing in more than one export group.
