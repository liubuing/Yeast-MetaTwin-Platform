# Phase 1 Deployment Verification

Generated: 2026-07-16T20:51:09
Deployment: Integrated_Yeast_MetaTwin_Deployment
Version: phase1_model_query

## Model Checks

| Model | Exists | Load OK | Reactions | Metabolites | Genes | rxn* | FBA status | Objective |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| yeast_gem | True | True | 4131 | 2806 | 1163 | 0 | optimal | 0.0819281 |
| yeast_metatwin | True | True | 7512 | 3301 | 2057 | 3381 | optimal | 0.0895347 |

## Audit Output Checks

| Output | Exists | Size bytes |
|---|---:|---:|
| pathway_audit_md | True | 4246 |
| all_metabolite_contribution_csv | True | 345905 |
| fatty_acid_contribution_csv | True | 20608 |

## Verdict

Phase 1 deployment check passed. The integrated deployment can load the baseline and expanded models and access existing audit outputs.
