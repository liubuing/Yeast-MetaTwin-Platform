# Phase 2 Exact-Sequence Split Definitions

Generated: 2026-07-16T20:58:33
FASTA source: `C:\biological\Metabolic model prediction\Yeast-MetaTwin\Data\Saccharomyces_cerevisiae.fasta`

## Split Counts

| Pool | Rows | Train | Dev | Test | Exact-sequence keys | Crossing keys | Fallback rows |
|---|---:|---:|---:|---:|---:|---:|---:|
| reference_only | 1959 | 1583 | 188 | 188 | 1491 | 0 | 722 |
| reference_plus_candidate_no_overlap | 5282 | 4028 | 862 | 392 | 1653 | 0 | 727 |

## Outputs

- `05_training/exact_sequence_split_reference_only.csv`
- `05_training/exact_sequence_split_reference_plus_candidate_no_overlap.csv`
- `06_evaluation/phase2_exact_sequence_split_fallback_rows.csv`
- `06_evaluation/phase2_exact_sequence_splits.json`

## Rule

The split key is the sorted set of SHA256 protein sequence hashes for ORFs attached to a reaction. Reactions without matched ORF sequences fall back to exact equation, then reaction ID. This prevents identical protein sequence sets from crossing train/dev/test, but it is not a homolog-cluster split.
