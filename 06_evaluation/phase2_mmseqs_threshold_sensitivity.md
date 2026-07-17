# Phase 2 MMseqs2 Threshold Sensitivity

Generated: 2026-07-16T21:01:29

## Input

- FASTA sequences written: 1745
- ORFs missing sequence: 0
- Coverage: 0.8
- Coverage mode: 0

## Results

| min_seq_id | Pool | Clusters | Rows | Train | Dev | Test | Homology keys | Crossing keys | Fallback rows |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.3 | reference_only | 1416 | 1959 | 1584 | 159 | 216 | 1376 | 0 | 722 |
| 0.3 | reference_plus_candidate_no_overlap | 1416 | 5282 | 4469 | 274 | 539 | 1538 | 0 | 727 |
| 0.5 | reference_only | 1522 | 1959 | 1584 | 163 | 212 | 1435 | 0 | 722 |
| 0.5 | reference_plus_candidate_no_overlap | 1522 | 5282 | 4346 | 288 | 648 | 1597 | 0 | 727 |
| 0.7 | reference_only | 1621 | 1959 | 1581 | 178 | 200 | 1473 | 0 | 722 |
| 0.7 | reference_plus_candidate_no_overlap | 1621 | 5282 | 4526 | 300 | 456 | 1635 | 0 | 727 |
| 0.9 | reference_only | 1699 | 1959 | 1556 | 184 | 219 | 1489 | 0 | 722 |
| 0.9 | reference_plus_candidate_no_overlap | 1699 | 5282 | 3653 | 792 | 837 | 1651 | 0 | 727 |

## Interpretation

Lower `min_seq_id` values create broader clusters and stricter homology separation. Higher values create more clusters and are closer to exact-sequence splitting. All rows here are summaries; the currently materialized homology split remains the 0.3 identity / 0.8 coverage split.
