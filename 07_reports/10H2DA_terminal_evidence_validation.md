# 10H2DA Terminal Evidence Validation

Generated: 2026-07-16T21:28:47

## Candidate Verdicts

| Candidate | Verdict | Reason |
|---|---|---|
| CAND_T2DEC_THIOESTERASE_P | enzyme_class_support_only | Yeast UniProt contains thioesterase-class entries, but no exact 10H2DA substrate record was found. |
| CAND_T2DEC_OMEGA_HYDROXYLASE_P | enzyme_class_support_only | Yeast UniProt contains oxygenase/hydroxylase/P450-class entries, but no exact omega-hydroxylation record for this substrate was found. |
| CAND_T2DEC_COA_OMEGA_HYDROXYLASE_P | enzyme_class_support_only | Yeast UniProt contains oxygenase/hydroxylase/P450-class entries, but no exact omega-hydroxylation record for this substrate was found. |
| CAND_10H2DA_COA_THIOESTERASE_P | enzyme_class_support_only | Yeast UniProt contains thioesterase-class entries, but no exact 10H2DA substrate record was found. |

## Search Summary

| Asset | Matches |
|---|---:|
| uniprot_yeast | 0 |
| uniprot_reaction_smiles | 0 |
| kegg_compound | 0 |
| ymdb | 0 |
| chebi_smiles | 0 |
| mnx_reaction_smile | 0 |

## Interpretation

Local database search finds enzyme-class support for thioesterase and oxygenase terms, but no direct curated local record proves the exact 10H2DA terminal reactions. The terminal reactions therefore remain FBA-feasible, mass/charge-balanced hypotheses, not curated validated reactions.

## Outputs

- `06_evaluation/10h2da_terminal_evidence_matches.csv`
- `06_evaluation/10h2da_terminal_yeast_enzyme_candidates.csv`
- `06_evaluation/10h2da_terminal_validation_verdicts.csv`
- `06_evaluation/10h2da_terminal_evidence_validation.json`
