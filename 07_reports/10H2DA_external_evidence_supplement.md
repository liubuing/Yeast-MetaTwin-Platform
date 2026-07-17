# 10H2DA External Evidence Supplement

Generated: 2026-07-16T21:41:29

## Evidence Tier Definitions

| Tier | Meaning |
|---|---|
| A | Exact substrate or exact reaction candidate with enzyme/reaction context |
| B | Exact target compound context but no enzyme-specific terminal reaction |
| C | Near substrate plus enzyme-family evidence |
| D | Enzyme-family-only or near-substrate-only evidence |
| E | Weak keyword context only |
| Z | Query error |

## Candidate Verdicts

| Candidate | Best tier | Records | Recommended action |
|---|---|---:|---|
| CAND_T2DEC_OMEGA_HYDROXYLASE_P | B_exact_compound_context_no_enzyme_specificity | 32 | candidate_supported_for_prioritization_not_curated_promotion |
| CAND_T2DEC_COA_OMEGA_HYDROXYLASE_P | D_enzyme_family_only | 55 | enzyme_class_or_keyword_support_only |
| CAND_T2DEC_THIOESTERASE_P | C_near_substrate_enzyme_family | 17 | candidate_supported_for_prioritization_not_curated_promotion |
| CAND_10H2DA_COA_THIOESTERASE_P | D_enzyme_family_only | 22 | enzyme_class_or_keyword_support_only |

## Source Counts

| Source | Records |
|---|---:|
| PubMed | 40 |
| Rhea | 46 |
| UniProt | 40 |

## Interpretation

External records are kept separate from model/FBA/PU evidence. Only tier A should be considered for curated reaction promotion after manual review. Lower tiers are prioritization evidence only.

## Outputs

- `06_evaluation/10h2da_external_evidence_records.csv`
- `06_evaluation/10h2da_external_evidence_verdicts.csv`
- `06_evaluation/10h2da_external_evidence_supplement.json`
