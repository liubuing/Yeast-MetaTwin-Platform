# Phase 2 Training Manifests

Generated: 2026-07-16T21:01:31

## Primary Inputs

| Manifest | Rows | Columns | Train | Dev | Test | Exact train | Exact dev | Exact test | Homology train | Homology dev | Homology test | File |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| reference_only | 1959 | 39 | 1593 | 172 | 194 | 0 | 0 | 0 | 0 | 0 | 0 | `05_training\split_definitions_reference_only.csv` |
| reference_plus_candidate_no_overlap | 5282 | 39 | 4250 | 503 | 529 | 0 | 0 | 0 | 0 | 0 | 0 | `05_training\split_definitions_reference_plus_candidate_no_overlap.csv` |
| exact_sequence_reference_only | 1959 | 47 | 1593 | 172 | 194 | 1583 | 188 | 188 | 0 | 0 | 0 | `05_training\exact_sequence_split_reference_only.csv` |
| exact_sequence_reference_plus_candidate_no_overlap | 5282 | 47 | 4250 | 503 | 529 | 4028 | 862 | 392 | 0 | 0 | 0 | `05_training\exact_sequence_split_reference_plus_candidate_no_overlap.csv` |
| mmseqs_homology_reference_only | 1959 | 47 | 1593 | 172 | 194 | 0 | 0 | 0 | 1584 | 159 | 216 | `05_training\homology_split_reference_only.csv` |
| mmseqs_homology_reference_plus_candidate_no_overlap | 5282 | 47 | 4250 | 503 | 529 | 0 | 0 | 0 | 4469 | 274 | 539 | `05_training\homology_split_reference_plus_candidate_no_overlap.csv` |

## Outputs

- `05_training/training_manifest_reference_only.json`
- `05_training/training_manifest_reference_plus_candidate_no_overlap.json`
- `05_training/training_manifest_exact_sequence_reference_only.json`
- `05_training/training_manifest_exact_sequence_reference_plus_candidate_no_overlap.json`
- `05_training/training_manifest_mmseqs_homology_reference_only.json`
- `05_training/training_manifest_mmseqs_homology_reference_plus_candidate_no_overlap.json`
- `05_training/training_manifest_index.csv`
- `06_evaluation/phase2_training_manifests.md`

## Rule

The manifest records immutable file hashes, row counts, columns, split distributions, and training-role distributions for the current training inputs. Regenerate it whenever any upstream training CSV changes.
