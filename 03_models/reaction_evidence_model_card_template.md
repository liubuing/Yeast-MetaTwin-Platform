# {{ model_version }}

## Model Details

- Artifact and SHA256: recorded in the adjacent manifest
- Code version, Python, and dependencies: recorded in the adjacent manifest
- License: `{{ license_status }}`

## Intended Use

Prioritize yeast metabolic reaction evidence for review. Scores are reference-likeness rankings under a positive-unlabeled design. They are not probabilities that a reaction is biochemically true and must not replace database or experimental validation.

## Data And Splitting

Labeled positives are curated or database-cross-referenced reactions. Other rows are unlabeled, not confirmed negatives. Both classes are assigned together using connected groups built from protein homology clusters, normalized reaction stoichiometry, substrate structure signatures, and reaction identifiers.

## Evaluation

Report observed-label ranking metrics, labeled-positive recall, unlabeled selection rate, group-bootstrap 95% confidence intervals, observed-label calibration diagnostics, the development-set threshold rule, and cross-split leakage audit. External temporal evaluation is `blocked` unless a real timestamped external dataset is supplied.

## Limitations

Observed-label ROC AUC, average precision, Brier score, log loss, and calibration curves are biased by latent positives in the unlabeled pool. Applicability is limited to the feature schema and yeast reaction-evidence context documented in the manifest.

## Loading Safety

Joblib uses pickle-compatible serialization and can execute code while loading. Load only trusted artifacts after checking the manifest SHA256, preferably through `load_joblib_verified`.
