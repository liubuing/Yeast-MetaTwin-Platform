# Phase 2 Reaction Evidence Baseline v1

## Version And Artifact

- Model version: `phase2_reaction_evidence_baseline_v1`
- Manifest contract: `2.0.0`
- Artifact: `03_models/phase2_reaction_evidence_baseline_v1.joblib`
- SHA-256: `4b8cf9fa0349fc689833aef2f0ba2a61d626a71e49eaf8b6dde7fb8f57a600df`
- Size: `1,001,527` bytes

This digest matches the governed local inventory in `assets/checksums.sha256`, verified with `python 08_runtime/environment_check.py --verify-assets`. The inventory has no completed upstream origin review, so a match establishes local file identity but not source trust.

## Intended Use

Prioritize yeast metabolic reactions for evidence review. Output is a reference-likeness ranking signal, not a probability of biochemical truth. It must not replace database review, mass/charge validation, or experimental confirmation.

## Features

Each input row represents one metabolic reaction. Text fields are `reaction_name`, `model_equation`, `direction`, `enzyme_ec_numbers`, and `gpr`, concatenated and transformed by lowercase character-within-word TF-IDF 3-5 grams (`min_df=2`, up to 60,000 features). Numeric fields are `lower_bound_num`, `upper_bound_num`, `enzyme_evidence_rows_num`, `reactant_count`, `product_count`, `stoich_metabolite_count`, `has_gpr`, `has_ec`, `has_formula_balance`, and `has_charge_balance`, transformed with sparse `StandardScaler(with_mean=False)`. Missing text becomes empty text and invalid or missing numeric values become zero. External cross-reference and RXNdb identifier fields are excluded to reduce direct label leakage.

## Training Semantics

The baseline is a class-balanced liblinear logistic regression. Label 1 denotes curated or database-cross-referenced reactions. Label 0 denotes conservative unlabeled candidates and never means a confirmed false reaction. Train, development, and test membership is assigned jointly through connected groups based on protein homology clusters, normalized stoichiometry, substrate structure signatures, and reaction identifiers. The decision threshold is selected on the development split for labeled-positive recall.

## Evaluation

The recorded legacy evaluation contains 3,097 train rows (1,584 labeled positive), 352 development rows (159 labeled positive), and 396 test rows (216 labeled positive). Recorded observed-label metrics are:

| Split | ROC AUC | Average precision | Labeled-positive recall |
|---|---:|---:|---:|
| train | 0.995501 | 0.995529 | 0.986742 |
| dev | 0.988692 | 0.988093 | 0.968553 |
| test | 0.986291 | 0.985283 | 0.962963 |

These values come from the existing evaluation snapshot, where unlabeled rows were treated as observed zero labels. Latent positives therefore bias ROC AUC, average precision, precision, accuracy, F1, confusion matrices, and any calibration interpretation. The snapshot does not contain group-bootstrap confidence intervals, the selected threshold value, or an independent temporal test. It cannot support calibrated posterior, causal, broad cross-organism, or biochemical-truth claims.

External temporal evaluation is `blocked`: no validated, independent, timestamped external dataset is available.

## Runtime And Reproducibility

Inventory environment: CPython `3.14.5`; joblib `1.5.3`, NumPy `2.4.6`, pandas `2.3.3`, scikit-learn `1.9.0`, and SciPy `1.17.1`. Pinned reproduction dependencies are in `constraints.txt`. The repository has no commit (`master`, all files untracked), so file hashes in the adjacent manifest, rather than a Git revision, identify the inventoried code and inputs.

## License And Sources

The model artifact has no declared license, the repository has no root license, and upstream rights for the assembled Yeast-MetaTwin/reference, model-context, compound mapping, MMseqs2 cluster, and balance-audit inputs have not been consolidated. Redistribution is blocked until those rights and attribution obligations are resolved.

## Loading Safety

Joblib is pickle-compatible and may execute arbitrary code during loading. The default action is **do not deserialize**. First validate the v2 manifest, constrain every path to the deployment root, and verify declared byte sizes and SHA-256 values. Only after separately establishing source trust may an operator explicitly use `load_joblib_verified`. A matching hash proves identity with this inventory, not safety or trustworthiness.
