# 10H2DA P450 Engineering Feasibility Layer

Generated: 2026-07-17T12:32:13

## Scope

This layer separates kinetic prioritization from P450 engineering feasibility. It evaluates redox partner requirements, likely expression risk, host compatibility, and substrate-family fit for hydroxylase candidates.

## Outputs

- `06_evaluation/10h2da_p450_engineering_feasibility_matrix.csv`
- `06_evaluation/10h2da_p450_design_recommendations.csv`

## Top P450/Hydroxylase Candidates

| Entry | Reaction | Origin | Organism | System | Redox | Substrate fit | Feasibility | Action |
|---|---|---|---|---|---|---:|---:|---|
| B8QHP1 | CAND_T2DEC_OMEGA_HYDROXYLASE_P | external_uniprot_curated_panel | Starmerella bombicola | fungal_cyp52_microsomal_p450 | requires_cpr_or_compatible_yeast_p450_reductase | 5 | 23.747 | high_priority_test_with_yeast_cpr_or_cognate_cpr |
| B8QHP1 | CAND_T2DEC_COA_OMEGA_HYDROXYLASE_P | external_uniprot_curated_panel | Starmerella bombicola | fungal_cyp52_microsomal_p450 | requires_cpr_or_compatible_yeast_p450_reductase | 4 | 23.110 | high_priority_test_with_yeast_cpr_or_cognate_cpr |
| Q9Y8G7 | CAND_T2DEC_OMEGA_HYDROXYLASE_P | external_uniprot_curated_panel | Fusarium oxysporum | self_sufficient_cyp505 | internal_reductase_domain | 5 | 20.040 | high_priority_test_self_sufficient_p450 |
| Q9Y8G7 | CAND_T2DEC_COA_OMEGA_HYDROXYLASE_P | external_uniprot_curated_panel | Fusarium oxysporum | self_sufficient_cyp505 | internal_reductase_domain | 4 | 19.529 | high_priority_test_self_sufficient_p450 |
| P54781 | CAND_T2DEC_COA_OMEGA_HYDROXYLASE_P | endogenous_s_cerevisiae | Saccharomyces cerevisiae | endogenous_or_yeast_cyp_keyword_hit | native_yeast_redox_context_possible_but_terminal_activity_unvalidated | 2 | 18.690 | low_expression_risk_but_activity_validation_required |
| P10614 | CAND_T2DEC_COA_OMEGA_HYDROXYLASE_P | endogenous_s_cerevisiae | Saccharomyces cerevisiae | endogenous_or_yeast_cyp_keyword_hit | native_yeast_redox_context_possible_but_terminal_activity_unvalidated | 2 | 18.650 | low_expression_risk_but_activity_validation_required |
| P10614 | CAND_T2DEC_OMEGA_HYDROXYLASE_P | endogenous_s_cerevisiae | Saccharomyces cerevisiae | endogenous_or_yeast_cyp_keyword_hit | native_yeast_redox_context_possible_but_terminal_activity_unvalidated | 2 | 17.994 | low_expression_risk_but_activity_validation_required |
| P54781 | CAND_T2DEC_OMEGA_HYDROXYLASE_P | endogenous_s_cerevisiae | Saccharomyces cerevisiae | endogenous_or_yeast_cyp_keyword_hit | native_yeast_redox_context_possible_but_terminal_activity_unvalidated | 2 | 17.904 | low_expression_risk_but_activity_validation_required |
| P21595 | CAND_T2DEC_COA_OMEGA_HYDROXYLASE_P | endogenous_s_cerevisiae | Saccharomyces cerevisiae | endogenous_or_yeast_cyp_keyword_hit | native_yeast_redox_context_possible_but_terminal_activity_unvalidated | 1 | 17.295 | low_expression_risk_but_activity_validation_required |
| P14581 | CAND_T2DEC_OMEGA_HYDROXYLASE_P | external_uniprot | Oryctolagus cuniculus | heterologous_microsomal_p450 | requires_cpr_or_cognate_reductase_engineering | 5 | 16.900 | secondary_priority_high_activity_but_expression_risk |
| P10611 | CAND_T2DEC_OMEGA_HYDROXYLASE_P | external_uniprot | Oryctolagus cuniculus | heterologous_microsomal_p450 | requires_cpr_or_cognate_reductase_engineering | 5 | 16.883 | secondary_priority_high_activity_but_expression_risk |
| Q6NT55 | CAND_T2DEC_OMEGA_HYDROXYLASE_P | external_uniprot_curated_panel | Homo sapiens | heterologous_microsomal_p450 | requires_cpr_or_cognate_reductase_engineering | 5 | 16.879 | secondary_priority_high_activity_but_expression_risk |

## Top Designs After P450 Feasibility

| Route | P450 | System | Thioesterase/Partner | Combined score | Action |
|---|---|---|---|---:|---|
| free_acid_route | B8QHP1 | fungal_cyp52_microsomal_p450 | P41903 | 24.884 | high_priority_test_with_yeast_cpr_or_cognate_cpr |
| coa_bound_route | B8QHP1 | fungal_cyp52_microsomal_p450 | P41903 | 24.681 | high_priority_test_with_yeast_cpr_or_cognate_cpr |
| free_acid_route | B8QHP1 | fungal_cyp52_microsomal_p450 | P38256 | 23.912 | high_priority_test_with_yeast_cpr_or_cognate_cpr |
| free_acid_route | B8QHP1 | fungal_cyp52_microsomal_p450 | P53208 | 23.887 | high_priority_test_with_yeast_cpr_or_cognate_cpr |
| free_acid_route | B8QHP1 | fungal_cyp52_microsomal_p450 | Q12354 | 23.789 | high_priority_test_with_yeast_cpr_or_cognate_cpr |
| coa_bound_route | B8QHP1 | fungal_cyp52_microsomal_p450 | P53208 | 23.642 | high_priority_test_with_yeast_cpr_or_cognate_cpr |
| coa_bound_route | B8QHP1 | fungal_cyp52_microsomal_p450 | P38256 | 23.632 | high_priority_test_with_yeast_cpr_or_cognate_cpr |
| coa_bound_route | B8QHP1 | fungal_cyp52_microsomal_p450 | Q12354 | 23.515 | high_priority_test_with_yeast_cpr_or_cognate_cpr |
| free_acid_route | B8QHP1 | fungal_cyp52_microsomal_p450 | P07149 | 22.803 | high_priority_test_with_yeast_cpr_or_cognate_cpr |
| coa_bound_route | B8QHP1 | fungal_cyp52_microsomal_p450 | P07149 | 22.541 | high_priority_test_with_yeast_cpr_or_cognate_cpr |

## Interpretation

CYP505/P450foxy and fungal/yeast CYP52 candidates receive higher feasibility because they reduce either redox-coupling or host-expression risk. Mammalian CYP4 candidates can remain useful secondary screens, but their high UniKP or family scores should not be read as lower engineering risk.
