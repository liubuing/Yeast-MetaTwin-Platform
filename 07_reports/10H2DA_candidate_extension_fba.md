# 10H2DA Candidate Extension FBA

Generated: 2026-07-16T21:05:50

## Candidate Reactions

| ID | Equation | Interpretation |
|---|---|---|
| CAND_T2DEC_THIOESTERASE_P | trans-dec-2-enoyl-CoA + H2O -> trans-2-decenoate + CoA + H+ | TES1-like terminal hydrolysis candidate |
| CAND_T2DEC_OMEGA_HYDROXYLASE_P | trans-2-decenoate + NADPH + O2 + H+ -> 10H2DA + NADP+ + H2O | free-acid omega hydroxylation candidate |
| CAND_T2DEC_COA_OMEGA_HYDROXYLASE_P | trans-dec-2-enoyl-CoA + NADPH + O2 + H+ -> 10-hydroxy-trans-2-decenoyl-CoA + NADP+ + H2O | CoA-bound omega hydroxylation candidate |
| CAND_10H2DA_COA_THIOESTERASE_P | 10-hydroxy-trans-2-decenoyl-CoA + H2O -> 10H2DA + CoA + H+ | hydroxylated thioester hydrolysis candidate |

## FBA Results

| Scenario | Objective | Biomass floor | Status | Max flux | Key fluxes |
|---|---|---:|---|---:|---|
| target_demand_only | DM_s_1507 |  | optimal | 0.140091 | `{"DM_s_1507": 0.14009110198522634, "r_0120": 0.14009110198522634}` |
| target_demand_only | DM_CAND_T2DEC_P |  | optimal | 0 | `{}` |
| target_demand_only | DM_CAND_10H2DA_P |  | optimal | 0 | `{}` |
| target_demand_only | DM_s_1507 | 0.00895347 | optimal | 0.12631 | `{"DM_s_1507": 0.12630963095630746, "r_0120": 0.12630963095630746}` |
| target_demand_only | DM_CAND_T2DEC_P | 0.00895347 | optimal | 0 | `{}` |
| target_demand_only | DM_CAND_10H2DA_P | 0.00895347 | optimal | 0 | `{}` |
| free_acid_terminal_route | DM_s_1507 |  | optimal | 0.140091 | `{"DM_s_1507": 0.14009110198522579, "r_0120": 0.14009110198522579}` |
| free_acid_terminal_route | DM_CAND_T2DEC_P |  | optimal | 0.310771 | `{"CAND_T2DEC_THIOESTERASE_P": 0.31077117987940894, "DM_CAND_T2DEC_P": 0.31077117987940894, "r_0120": 0.31077117987940894}` |
| free_acid_terminal_route | DM_CAND_10H2DA_P |  | optimal | 0.302724 | `{"CAND_T2DEC_OMEGA_HYDROXYLASE_P": 0.30272419782429993, "CAND_T2DEC_THIOESTERASE_P": 0.30272419782429993, "DM_CAND_10H2DA_P": 0.30272419782429993, "r_0120": 0.30272419782429993}` |
| free_acid_terminal_route | DM_s_1507 | 0.00895347 | optimal | 0.12631 | `{"DM_s_1507": 0.1263096344039321, "r_0120": 0.1263096344039321}` |
| free_acid_terminal_route | DM_CAND_T2DEC_P | 0.00895347 | optimal | 0.281341 | `{"CAND_T2DEC_THIOESTERASE_P": 0.28134133917428455, "DM_CAND_T2DEC_P": 0.28134133917428455, "r_0120": 0.28134133917428455}` |
| free_acid_terminal_route | DM_CAND_10H2DA_P | 0.00895347 | optimal | 0.274011 | `{"CAND_T2DEC_OMEGA_HYDROXYLASE_P": 0.27401121243284626, "CAND_T2DEC_THIOESTERASE_P": 0.27401121243284626, "DM_CAND_10H2DA_P": 0.27401121243284626, "r_0120": 0.27401121243284626}` |
| coa_bound_terminal_route | DM_s_1507 |  | optimal | 0.140091 | `{"DM_s_1507": 0.1400911019852266, "r_0120": 0.1400911019852266}` |
| coa_bound_terminal_route | DM_CAND_T2DEC_P |  | optimal | 0 | `{}` |
| coa_bound_terminal_route | DM_CAND_10H2DA_P |  | optimal | 0.302724 | `{"CAND_10H2DA_COA_THIOESTERASE_P": 0.3027241978242993, "CAND_T2DEC_COA_OMEGA_HYDROXYLASE_P": 0.3027241978242993, "DM_CAND_10H2DA_P": 0.3027241978242994, "r_0120": 0.3027241978242993}` |
| coa_bound_terminal_route | DM_s_1507 | 0.00895347 | optimal | 0.12631 | `{"DM_s_1507": 0.12630963095630782, "r_0120": 0.12630963095630782}` |
| coa_bound_terminal_route | DM_CAND_T2DEC_P | 0.00895347 | optimal | 0 | `{}` |
| coa_bound_terminal_route | DM_CAND_10H2DA_P | 0.00895347 | optimal | 0.274011 | `{"CAND_10H2DA_COA_THIOESTERASE_P": 0.27401120521219163, "CAND_T2DEC_COA_OMEGA_HYDROXYLASE_P": 0.27401120521219163, "DM_CAND_10H2DA_P": 0.2740112052121917, "r_0120": 0.27401120521219163}` |
| combined_terminal_routes | DM_s_1507 |  | optimal | 0.140091 | `{"DM_s_1507": 0.14009110198522712, "r_0120": 0.14009110198522712}` |
| combined_terminal_routes | DM_CAND_T2DEC_P |  | optimal | 0.310771 | `{"CAND_T2DEC_THIOESTERASE_P": 0.3107711798794087, "DM_CAND_T2DEC_P": 0.3107711798794087, "r_0120": 0.3107711798794087}` |
| combined_terminal_routes | DM_CAND_10H2DA_P |  | optimal | 0.302724 | `{"CAND_10H2DA_COA_THIOESTERASE_P": 0.30272419782429894, "CAND_T2DEC_COA_OMEGA_HYDROXYLASE_P": 0.30272419782429894, "DM_CAND_10H2DA_P": 0.30272419782429894, "r_0120": 0.30272419782429894}` |
| combined_terminal_routes | DM_s_1507 | 0.00895347 | optimal | 0.12631 | `{"DM_s_1507": 0.12630963095630854, "r_0120": 0.12630963095630854}` |
| combined_terminal_routes | DM_CAND_T2DEC_P | 0.00895347 | optimal | 0.281341 | `{"CAND_T2DEC_THIOESTERASE_P": 0.2813413317604697, "DM_CAND_T2DEC_P": 0.28134133176046977, "r_0120": 0.2813413317604697}` |
| combined_terminal_routes | DM_CAND_10H2DA_P | 0.00895347 | optimal | 0.274011 | `{"CAND_10H2DA_COA_THIOESTERASE_P": 0.2740112052121955, "CAND_T2DEC_COA_OMEGA_HYDROXYLASE_P": 0.2740112052121955, "DM_CAND_10H2DA_P": 0.2740112052121955, "r_0120": 0.2740112052121955}` |

## Interpretation

This is a feasibility test, not proof of enzyme specificity. A positive 10H2DA demand flux means the current metabolic network can supply precursors and cofactors after adding the stated candidate terminal reactions. The terminal reactions still require external enzyme/database/experimental validation before they should be treated as curated model reactions.

## Output Files

- `06_evaluation/10h2da_candidate_extension_fba.json`
- `06_evaluation/10h2da_candidate_extension_fba.csv`
- `07_reports/10H2DA_candidate_extension_fba.md`
