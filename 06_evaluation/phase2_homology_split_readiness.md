# Phase 2 Homology Split Readiness

Generated: 2026-07-16T20:58:30

## Tool Availability

| Tool | Available | Path |
|---|---:|---|
| mmseqs | True | `C:\biological\Metabolic model prediction\Integrated_Yeast_MetaTwin_Deployment\tools\mmseqs2\mmseqs\bin\mmseqs.exe` |
| cd-hit | False | `` |
| cd-hit-est | False | `` |

## FASTA Assets

| FASTA | Exists | Header IDs |
|---|---:|---:|
| `C:\biological\Metabolic model prediction\Yeast-MetaTwin\Data\Saccharomyces_cerevisiae.fasta` | True | 5911 |
| `C:\biological\Metabolic model prediction\Yeast-MetaTwin\Code\ECnumber_prediction\CLEAN\data\Saccharomyces_cerevisiae.fasta` | True | 5911 |
| `C:\biological\Metabolic model prediction\Yeast-MetaTwin\audit\clean_unique_sequences.fasta` | True | 191460 |

## ORF Coverage By Pool

| Pool | Rows | Rows with ORFs | Unique ORFs | ORFs in FASTA | ORFs missing FASTA |
|---|---:|---:|---:|---:|---:|
| reference_only | 1959 | 1237 | 1033 | 1033 | 0 |
| reference_plus_candidate_no_overlap | 5282 | 4560 | 1746 | 1745 | 1 |

## Status

Homology-cold split ready: `True`

A homology-cold split requires a clustering tool such as MMseqs2 or CD-HIT plus sequence coverage for the ORFs in the target split pool. Current deterministic splits remain structural exact-equation splits until clustering is available.
