# Phase 2 Training Readiness Audit

Generated: 2026-07-16T21:05:58

## Balance Summary

| Metric | Value |
|---|---:|
| model_reactions_checked | 7512 |
| model_formula_balanced | 4792 |
| model_charge_balanced | 5059 |
| candidate_reactions_checked | 4 |
| candidate_formula_balanced | 4 |
| candidate_charge_balanced | 4 |
| missing_formula_rows | 1661 |
| unparsable_formula_rows | 139 |

## Feature And Label Quality

| Export group | Rows | Equation % | Stoich % | All SMILES % | GPR % | ORF % | EC % | External xref % | RXNdb % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| first_pass_reference_label | 1959 | 100.00 | 100.00 | 91.32 | 63.14 | 63.14 | 51.91 | 100.00 | 0.00 |
| model_context_only | 2172 | 100.00 | 100.00 | 41.39 | 67.77 | 67.77 | 65.93 | 0.00 | 0.00 |
| candidate_extension_evidence | 3330 | 100.00 | 100.00 | 52.82 | 100.00 | 100.00 | 98.89 | 0.00 | 100.00 |
| excluded_review_required | 51 | 100.00 | 100.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

## Negative Sample Design

Candidate unlabeled hard negatives: 1886

These rows are not true negatives. They are balanced, model-context reactions without external/RXNdb provenance and can be used as candidate hard negatives only with conservative weighting or positive-unlabeled learning.

## Validation Matrix

Validation matrix rows: 5344

The matrix separates curated references, RXNdb-backed candidates, unresolved exclusions, and 10H2DA terminal hypotheses so they do not collapse into one training label type.

## Output Files

- `06_evaluation/phase2_training_readiness_audit.json`
- `06_evaluation/phase2_reaction_balance_audit.csv`
- `06_evaluation/phase2_feature_label_quality.csv`
- `05_training/reaction_negative_sample_candidates.csv`
- `06_evaluation/phase2_candidate_validation_matrix.csv`
