from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from train_phase2_reaction_evidence_baseline import (
    COMPOUND_PATH,
    EVAL_DIR,
    MMSEQS_CLUSTER_PATH,
    MODEL_DIR,
    NUMERIC_FIELDS,
    RANDOM_STATE,
    REPORT_DIR,
    ROOT,
    TEXT_FIELDS,
    TEMPORAL_TEST_PATH,
    TRAIN_DIR,
    candidate_terminal_rows,
    fit_features,
    load_balance_flags,
    load_grouped_training_dataframe,
    metrics_for_split,
    prepare_dataframe,
    score_dataframe,
    transform_features,
    write_csv,
)
from reaction_evidence_ml_utils import (
    audit_split_leakage,
    environment_provenance,
    file_records,
    select_positive_recall_threshold,
    sha256_file,
)


MODEL_VERSION = "phase2_reaction_evidence_pu_v2"
N_ESTIMATORS = 25
NEGATIVE_POSITIVE_RATIO = 0.6


def train_ensemble(df: pd.DataFrame) -> tuple[list[dict[str, Any]], list[LogisticRegression], Any, Any]:
    train_df = df[df["model_split"] == "train"].copy()
    positives = train_df[train_df["label"] == 1]
    unlabeled = train_df[train_df["label"] == 0]
    sample_size = min(len(unlabeled), max(1, int(len(positives) * NEGATIVE_POSITIVE_RATIO)))
    rng = np.random.default_rng(RANDOM_STATE)
    vectorizer, scaler, _ = fit_features(train_df)
    ensemble = []
    members = []
    for idx in range(N_ESTIMATORS):
        sampled_idx = rng.choice(unlabeled.index.to_numpy(), size=sample_size, replace=False)
        sampled_unlabeled = unlabeled.loc[sampled_idx]
        member_df = pd.concat([positives, sampled_unlabeled], ignore_index=True)
        x_member = transform_features(member_df, vectorizer, scaler)
        y_member = member_df["label"].astype(int)
        model = LogisticRegression(max_iter=2000, class_weight="balanced", random_state=RANDOM_STATE + idx, solver="liblinear")
        model.fit(x_member, y_member)
        members.append(model)
        ensemble.append(
            {
                "member": idx,
                "positive_rows": int(len(positives)),
                "sampled_unlabeled_negative_rows": int(len(sampled_unlabeled)),
            }
        )
    return ensemble, members, vectorizer, scaler


def predict_ensemble(df: pd.DataFrame, members: list[LogisticRegression], vectorizer: Any, scaler: Any) -> np.ndarray:
    matrix = transform_features(df, vectorizer, scaler)
    probs = np.vstack([model.predict_proba(matrix)[:, 1] for model in members])
    return probs.mean(axis=0)


def score_with_ensemble(input_df: pd.DataFrame, members: list[LogisticRegression], vectorizer: Any, scaler: Any) -> pd.DataFrame:
    work = prepare_dataframe(input_df.to_dict("records"))
    work["pu_reference_likeness_score"] = predict_ensemble(work, members, vectorizer, scaler)
    return work


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Phase 2 Reaction Evidence PU v2 Training",
        "",
        f"Generated: {payload['generated_at']}",
        f"Model version: `{payload['model_version']}`",
        "",
        "## Training Design",
        "",
        "Positive-unlabeled style ensemble. Curated references are labeled positives. Unlabeled candidates are sampled as temporary working negatives per ensemble member, then prediction probabilities are averaged. No sampled row is asserted to be a true negative.",
        "",
        "## PU Evaluation Against Observed Labels",
        "",
        "| Split | Labeled-positive recall | Unlabeled selected | Observed-label ROC AUC | Observed-label AP | Brier |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in payload["metrics"]:
        metric = row["metrics"]
        lines.append(f"| {row['split']} | {metric['labeled_positive_recall']:.6f} | {metric['unlabeled_predicted_positive_rate']:.6f} | {metric['observed_label_roc_auc']:.6f} | {metric['observed_label_average_precision']:.6f} | {metric['observed_label_brier_score']:.6f} |")
    lines.extend(["", "## 10H2DA Terminal PU Scores", "", "| Reaction | PU score |", "|---|---:|"])
    for row in payload["terminal_scores"]:
        lines.append(f"| {row['model_reaction_id']} | {row['pu_reference_likeness_score']:.6f} |")
    lines.extend(
        [
            "",
            "## Outputs",
            "",
            "- `03_models/phase2_reaction_evidence_pu_v2.joblib`",
            "- `03_models/phase2_reaction_evidence_pu_v2_manifest.json`",
            "- `06_evaluation/phase2_reaction_evidence_pu_v2_metrics.json`",
            "- `06_evaluation/phase2_reaction_evidence_pu_v2_calibration_curve.csv`",
            "- `06_evaluation/phase2_candidate_extension_evidence_pu_v2_scores.csv`",
            "- `06_evaluation/10h2da_terminal_candidate_pu_v2_scores.csv`",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    balance_flags = load_balance_flags()
    df = load_grouped_training_dataframe(balance_flags)
    ensemble, members, vectorizer, scaler = train_ensemble(df)

    dev_df = df[df["model_split"] == "dev"].copy()
    dev_probs = predict_ensemble(dev_df, members, vectorizer, scaler)
    threshold_selection = select_positive_recall_threshold(dev_df["label"].astype(int), dev_probs)
    threshold = threshold_selection["value"]
    metrics = []
    for split in ["train", "dev", "test"]:
        split_df = df[df["model_split"] == split].copy()
        probs = predict_ensemble(split_df, members, vectorizer, scaler)
        metrics.append(metrics_for_split(split, split_df["label"].astype(int), probs, split_df["split_group_key"], threshold))

    candidate_df = pd.read_csv(TRAIN_DIR / "reaction_candidate_extension_evidence.csv", dtype=str).fillna("")
    candidate_scores = score_with_ensemble(candidate_df, members, vectorizer, scaler)
    candidate_cols = ["model_reaction_id", "reaction_name", "model_equation", "rxndb_id", "rxndb_ec_number", "enzyme_ec_numbers", "pu_reference_likeness_score"]
    candidate_scores[candidate_cols].sort_values("pu_reference_likeness_score", ascending=False).to_csv(EVAL_DIR / "phase2_candidate_extension_evidence_pu_v2_scores.csv", index=False)

    terminal_scores = score_with_ensemble(pd.DataFrame(candidate_terminal_rows()), members, vectorizer, scaler)
    terminal_cols = ["model_reaction_id", "reaction_name", "model_equation", "enzyme_ec_numbers", "pu_reference_likeness_score"]
    terminal_scores[terminal_cols].to_csv(EVAL_DIR / "10h2da_terminal_candidate_pu_v2_scores.csv", index=False)

    model_payload = {
        "model_version": MODEL_VERSION,
        "members": members,
        "vectorizer": vectorizer,
        "scaler": scaler,
        "text_fields": TEXT_FIELDS,
        "numeric_fields": NUMERIC_FIELDS,
        "n_estimators": N_ESTIMATORS,
        "negative_positive_ratio": NEGATIVE_POSITIVE_RATIO,
        "label_semantics": {"1": "curated_reference", "0": "unlabeled_candidate_sampled_as_temporary_negative"},
        "decision_threshold": threshold,
    }
    model_path = MODEL_DIR / f"{MODEL_VERSION}.joblib"
    joblib.dump(model_payload, model_path)
    data_paths = [
        TRAIN_DIR / "homology_split_reference_only.csv",
        TRAIN_DIR / "reaction_negative_sample_candidates.csv",
        TRAIN_DIR / "reaction_model_context_only.csv",
    ]
    source_paths = [COMPOUND_PATH, MMSEQS_CLUSTER_PATH, EVAL_DIR / "phase2_reaction_balance_audit.csv"]
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "model_version": MODEL_VERSION,
        "model_path": str(model_path.relative_to(ROOT)),
        "artifact": {"path": str(model_path.relative_to(ROOT)), "sha256": sha256_file(model_path), "bytes": model_path.stat().st_size},
        "data_artifacts": file_records(data_paths, ROOT),
        "source_artifacts": file_records(source_paths, ROOT),
        "provenance": environment_provenance([Path(__file__), Path(__file__).with_name("train_phase2_reaction_evidence_baseline.py"), Path(__file__).with_name("reaction_evidence_ml_utils.py")], ROOT),
        "n_estimators": N_ESTIMATORS,
        "negative_positive_ratio": NEGATIVE_POSITIVE_RATIO,
        "ensemble_members": ensemble,
        "metrics": metrics,
        "threshold_selection": threshold_selection,
        "leakage_audit": audit_split_leakage(df),
        "pu_setting": {
            "positive": "curated or database-cross-referenced reactions",
            "unlabeled": "model-context candidates without positive provenance; may contain latent positives",
            "training_method": "bagged working-negative PU heuristic",
            "assumption": "Positive selection is potentially biased (non-SCAR); no class-prior correction or calibrated posterior claim is made.",
            "estimand": "reference-likeness ranking, not probability of biochemical truth",
        },
        "external_temporal_evaluation": {
            "status": "blocked",
            "reason": "No timestamped external temporal test dataset is available." if not TEMPORAL_TEST_PATH.exists() else "A candidate file exists but has not been validated as independent and timestamped.",
            "expected_path": str(TEMPORAL_TEST_PATH.relative_to(ROOT)),
        },
        "feature_schema": {"text_fields": TEXT_FIELDS, "numeric_fields": NUMERIC_FIELDS, "text_vectorizer": "char_wb_tfidf_3_5", "missing_value_policy": "empty text and numeric zero after coercion"},
        "intended_use": {"scope": "yeast metabolic reaction evidence prioritization", "out_of_scope": ["biochemical truth classification", "clinical use", "replacement for database or experimental validation"]},
        "license": {"status": "not_declared", "note": "No model artifact license was found; redistribution rights must be established before release."},
        "serialization_security": {"format": "joblib/pickle", "trusted_load_required": True, "verification": "Verify artifact.sha256 before loading with load_joblib_verified; hash verification does not make an untrusted pickle safe."},
        "candidate_extension_rows_scored": int(len(candidate_scores)),
        "terminal_scores": terminal_scores[terminal_cols].to_dict("records"),
        "notes": [
            "This is a PU-style prioritization model, not a final truth-label classifier.",
            "Observed-label metrics treat unlabeled rows as zero only for diagnostics and are biased by latent positives.",
        ],
    }
    (MODEL_DIR / f"{MODEL_VERSION}_manifest.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (EVAL_DIR / "phase2_reaction_evidence_pu_v2_metrics.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    metric_rows = [{"split": row["split"], "rows": row["rows"], "groups": row["groups"], "threshold": row["threshold"], **row["metrics"]} for row in metrics]
    write_csv(EVAL_DIR / "phase2_reaction_evidence_pu_v2_metrics.csv", metric_rows, list(metric_rows[0].keys()))
    calibration_rows = [{"split": row["split"], **point} for row in metrics for point in row["calibration_curve"]]
    write_csv(EVAL_DIR / "phase2_reaction_evidence_pu_v2_calibration_curve.csv", calibration_rows, list(calibration_rows[0].keys()))
    card = (MODEL_DIR / "reaction_evidence_model_card_template.md").read_text(encoding="utf-8").replace("{{ model_version }}", MODEL_VERSION).replace("{{ license_status }}", payload["license"]["status"])
    (MODEL_DIR / f"{MODEL_VERSION}_model_card.md").write_text(card, encoding="utf-8")
    (REPORT_DIR / "phase2_reaction_evidence_pu_v2_training.md").write_text(render_report(payload), encoding="utf-8")
    print(REPORT_DIR / "phase2_reaction_evidence_pu_v2_training.md")


if __name__ == "__main__":
    main()
