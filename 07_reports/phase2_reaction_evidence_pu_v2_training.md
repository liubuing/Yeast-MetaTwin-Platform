# Phase 2 Reaction Evidence PU v2 Training

Generated: 2026-07-16T21:30:40
Model version: `phase2_reaction_evidence_pu_v2`

## Training Design

Positive-unlabeled style ensemble. Curated references are positives. Unlabeled hard negatives are sampled as temporary negatives per ensemble member, then prediction probabilities are averaged. This reduces reliance on any single unlabeled row being a true negative.

## Metrics Against Held-Out Unlabeled Evaluation Set

| Split | Accuracy | Precision | Recall | F1 | ROC AUC | Avg precision |
|---|---:|---:|---:|---:|---:|---:|
| train | 0.954472 | 0.928699 | 0.986742 | 0.956841 | 0.994583 | 0.994593 |
| dev | 0.931818 | 0.894737 | 0.962264 | 0.927273 | 0.987519 | 0.987072 |
| test | 0.944444 | 0.936937 | 0.962963 | 0.949772 | 0.985854 | 0.984997 |

## 10H2DA Terminal PU Scores

| Reaction | PU score |
|---|---:|
| CAND_T2DEC_THIOESTERASE_P | 0.686474 |
| CAND_T2DEC_OMEGA_HYDROXYLASE_P | 0.886367 |
| CAND_T2DEC_COA_OMEGA_HYDROXYLASE_P | 0.834920 |
| CAND_10H2DA_COA_THIOESTERASE_P | 0.741744 |

## Outputs

- `03_models/phase2_reaction_evidence_pu_v2.joblib`
- `03_models/phase2_reaction_evidence_pu_v2_manifest.json`
- `06_evaluation/phase2_reaction_evidence_pu_v2_metrics.json`
- `06_evaluation/phase2_candidate_extension_evidence_pu_v2_scores.csv`
- `06_evaluation/10h2da_terminal_candidate_pu_v2_scores.csv`
