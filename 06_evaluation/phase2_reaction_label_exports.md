# Phase 2 Reaction Label Exports

Generated: 2026-07-16T20:58:23

## Export Counts

| Export group | Count | File |
|---|---:|---|
| first_pass_reference_label | 1959 | `05_training/reaction_first_pass_reference_labels.csv` |
| model_context_only | 2172 | `05_training/reaction_model_context_only.csv` |
| candidate_extension_evidence | 3330 | `05_training/reaction_candidate_extension_evidence.csv` |
| excluded_review_required | 51 | `05_training/reaction_excluded_review_required.csv` |

## Rule

- `first_pass_reference_label`: external database cross-referenced reactions; use as the initial reference label pool.
- `candidate_extension_evidence`: underground reactions with RXNdb provenance; use for pathway extension candidates after review.
- `model_context_only`: model reactions without external reaction cross-reference; use for simulation context, not labels.
- `excluded_review_required`: unresolved underground reactions; exclude from training labels.
