# 10H2DA Construct and Redox Design Matrix

Generated: 2026-07-17T17:01:06

## Scope

This report translates P450-adjusted route rankings into construct-level design choices: P450 module, redox partner handling, thioesterase module, route readouts, and controls. It is a design checklist, not an experimental protocol.

## Outputs

- `06_evaluation/10h2da_construct_design_matrix.csv`

## Tier 1 Designs

| Design | Route | P450 | Redox module | Thioesterase | Score |
|---|---|---|---|---|---:|
| 10H2DA_DESIGN_001 | free_acid_route | B8QHP1 | test yeast NCP1/CPR1 support first; keep cognate CPR as fallback if available | P41903 | 24.884 |
| 10H2DA_DESIGN_002 | coa_bound_route | B8QHP1 | test yeast NCP1/CPR1 support first; keep cognate CPR as fallback if available | P41903 | 24.681 |

## Interpretation

Build-first designs favor fungal/yeast CYP52M1 with TES1/PTE1 because this combination balances substrate-family relevance, yeast-compatible expression context, and endogenous thioesterase support. CYP505/P450foxy designs remain valuable follow-ups because self-sufficiency reduces CPR uncertainty even when raw route score is lower.
