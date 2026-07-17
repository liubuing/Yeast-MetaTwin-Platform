# Phase 2 Reaction Evidence Baseline Training

Generated: 2026-07-16T21:22:20
Model version: `phase2_reaction_evidence_baseline_v1`

## Training Design

Binary baseline classifier trained with curated external-crossref reactions as positives and conservative unlabeled hard negatives as negatives. This is a reference-likeness model, not a final biochemical truth model.

## Dataset

| Split | Rows | Positives | Negatives |
|---|---:|---:|---:|
| dev | 352 | 159 | 193 |
| test | 396 | 216 | 180 |
| train | 3097 | 1584 | 1513 |

## Metrics

| Split | Accuracy | Precision | Recall | F1 | ROC AUC | Avg precision |
|---|---:|---:|---:|---:|---:|---:|
| train | 0.959961 | 0.938175 | 0.986742 | 0.961846 | 0.995501 | 0.995529 |
| dev | 0.937500 | 0.900585 | 0.968553 | 0.933333 | 0.988692 | 0.988093 |
| test | 0.949495 | 0.945455 | 0.962963 | 0.954128 | 0.986291 | 0.985283 |

## 10H2DA Terminal Scores

| Reaction | Score |
|---|---:|
| CAND_T2DEC_THIOESTERASE_P | 0.717819 |
| CAND_T2DEC_OMEGA_HYDROXYLASE_P | 0.913918 |
| CAND_T2DEC_COA_OMEGA_HYDROXYLASE_P | 0.864946 |
| CAND_10H2DA_COA_THIOESTERASE_P | 0.775210 |

## Outputs

- `03_models/phase2_reaction_evidence_baseline_v1.joblib`
- `03_models/phase2_reaction_evidence_baseline_v1_manifest.json`
- `05_training/reaction_evidence_baseline_training_matrix.csv`
- `06_evaluation/phase2_reaction_evidence_baseline_metrics.json`
- `06_evaluation/phase2_reaction_evidence_baseline_metrics.csv`
- `06_evaluation/phase2_candidate_extension_evidence_scores.csv`
- `06_evaluation/10h2da_terminal_candidate_scores.csv`
