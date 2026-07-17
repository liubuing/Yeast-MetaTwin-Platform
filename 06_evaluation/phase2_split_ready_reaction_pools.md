# Phase 2 Split-Ready Reaction Pools

Generated: 2026-07-16T20:58:27

## Counts

| Pool | Count | File |
|---|---:|---|
| reference_labels | 1959 | `05_training/split_ready_reference_labels.csv` |
| candidate_extension_no_reference_overlap | 3323 | `05_training/split_ready_candidate_extension_no_reference_overlap.csv` |
| candidate_reference_overlap_review | 7 | `05_training/split_ready_candidate_reference_overlap_review.csv` |
| reference_plus_candidate_no_overlap | 5282 | `05_training/split_ready_reference_plus_candidate_no_overlap.csv` |
| model_context_only | 2172 | `05_training/split_ready_model_context_only.csv` |
| excluded_review_required | 51 | `05_training/split_ready_excluded_review_required.csv` |

## Rule

The split-ready candidate pool excludes candidate reactions whose exact model equation also appears in the first-pass reference label pool. These overlap rows are exported separately for review and should not be used in naive train/test splits.
