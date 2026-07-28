# Phase 2 MMseqs2 Homology Split Definitions

Generated: 2026-07-16T21:00:37
MMseqs2: `<MMSEQS2_PATH>`
FASTA source: `C:\biological\Metabolic model prediction\Yeast-MetaTwin\Data\Saccharomyces_cerevisiae.fasta`

## Clustering

| Metric | Value |
|---|---:|
| Input ORFs | 1745 |
| FASTA sequences written | 1745 |
| ORFs missing sequence | 0 |
| MMseqs2 clusters | 1416 |

## Split Counts

| Pool | Rows | Train | Dev | Test | Homology keys | Crossing keys | Fallback rows |
|---|---:|---:|---:|---:|---:|---:|---:|
| reference_only | 1959 | 1584 | 159 | 216 | 1376 | 0 | 722 |
| reference_plus_candidate_no_overlap | 5282 | 4469 | 274 | 539 | 1538 | 0 | 727 |

## Outputs

- `05_training/homology_split_reference_only.csv`
- `05_training/homology_split_reference_plus_candidate_no_overlap.csv`
- `06_evaluation/phase2_mmseqs_homology_split_fallback_rows.csv`
- `06_evaluation/phase2_mmseqs_homology_splits.json`

## Rule

MMseqs2 clusters ORF protein sequences, then reactions are split by the sorted set of cluster representatives attached to each reaction. Reactions without clusterable ORFs fall back to exact equation. This is a homology-aware split over available yeast ORF sequences, not an experimental validation split.
