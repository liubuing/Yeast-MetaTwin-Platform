# Phase 2 Reaction Split Definitions

Generated: 2026-07-16T20:58:28

## Split Counts

| Pool | Rows | Train | Dev | Test | Split keys crossing splits |
|---|---:|---:|---:|---:|---:|
| reference_only | 1959 | 1593 | 172 | 194 | 0 |
| reference_plus_candidate_no_overlap | 5282 | 4250 | 503 | 529 | 0 |

## Outputs

- `05_training/split_definitions_reference_only.csv`
- `05_training/split_definitions_reference_plus_candidate_no_overlap.csv`
- `06_evaluation/phase2_reaction_split_definitions.json`

## Rule

Splits are deterministic SHA256 hash assignments over exact model equation when available, falling back to model reaction ID. The target ratio is 80/10/10 for train/dev/test. This is a structural split definition, not a homology-cold split.
