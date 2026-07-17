from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from scipy.sparse import csr_matrix, hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from reaction_evidence_ml_utils import (
    assign_unified_group_splits,
    audit_split_leakage,
    environment_provenance,
    evaluate_pu_split,
    file_records,
    read_mmseqs_clusters,
    select_positive_recall_threshold,
    sha256_file,
)


ROOT = Path(__file__).resolve().parents[1]
MAP_DIR = ROOT / "02_id_mapping"
MODEL_DIR = ROOT / "03_models"
TRAIN_DIR = ROOT / "05_training"
EVAL_DIR = ROOT / "06_evaluation"
REPORT_DIR = ROOT / "07_reports"

RANDOM_STATE = 17
MODEL_VERSION = "phase2_reaction_evidence_baseline_v1"
COMPOUND_PATH = MAP_DIR / "model_compound_seed_enriched.csv"
MMSEQS_CLUSTER_PATH = TRAIN_DIR / "mmseqs_homology_clusters" / "yeast_orf_minid0_3_cov0_8_cluster.tsv"
TEMPORAL_TEST_PATH = TRAIN_DIR / "reaction_evidence_external_temporal_test.csv"

TEXT_FIELDS = [
    "reaction_name",
    "model_equation",
    "direction",
    "enzyme_ec_numbers",
    "gpr",
]

NUMERIC_FIELDS = [
    "lower_bound_num",
    "upper_bound_num",
    "enzyme_evidence_rows_num",
    "reactant_count",
    "product_count",
    "stoich_metabolite_count",
    "has_gpr",
    "has_ec",
    "has_formula_balance",
    "has_charge_balance",
]


def has_text(value: Any) -> bool:
    return str(value).strip().lower() not in {"", "nan", "none", "null"}


def split_values(value: Any) -> list[str]:
    if not has_text(value):
        return []
    return [chunk.strip() for chunk in str(value).replace(";", "|").split("|") if has_text(chunk)]


def load_balance_flags() -> dict[str, dict[str, bool]]:
    path = EVAL_DIR / "phase2_reaction_balance_audit.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype=str).fillna("")
    flags = {}
    for row in df.to_dict("records"):
        if row.get("source") == "Yeast-MetaTwin":
            flags[row["model_reaction_id"]] = {
                "formula": str(row.get("formula_balanced", "")).lower() == "true",
                "charge": str(row.get("charge_balanced", "")).lower() == "true",
            }
    return flags


def load_positive_rows(balance_flags: dict[str, dict[str, bool]]) -> list[dict[str, Any]]:
    df = pd.read_csv(TRAIN_DIR / "homology_split_reference_only.csv", dtype=str).fillna("")
    rows = []
    for row in df.to_dict("records"):
        flags = balance_flags.get(row["model_reaction_id"], {})
        row = dict(row)
        row["label"] = 1
        row["label_name"] = "curated_reference"
        row["has_formula_balance"] = int(bool(flags.get("formula", False)))
        row["has_charge_balance"] = int(bool(flags.get("charge", False)))
        rows.append(row)
    return rows


def load_negative_rows(balance_flags: dict[str, dict[str, bool]]) -> list[dict[str, Any]]:
    neg = pd.read_csv(TRAIN_DIR / "reaction_negative_sample_candidates.csv", dtype=str).fillna("")
    all_rows = pd.read_csv(TRAIN_DIR / "reaction_model_context_only.csv", dtype=str).fillna("")
    context_by_id = {row["model_reaction_id"]: row for row in all_rows.to_dict("records")}
    rows = []
    for row in neg.to_dict("records"):
        base = dict(context_by_id.get(row["model_reaction_id"], {}))
        base.update(row)
        flags = balance_flags.get(row["model_reaction_id"], {})
        base["label"] = 0
        base["label_name"] = "unlabeled_candidate"
        base["has_formula_balance"] = int(bool(flags.get("formula", True)))
        base["has_charge_balance"] = int(bool(flags.get("charge", True)))
        rows.append(base)
    return rows


def load_grouped_training_dataframe(balance_flags: dict[str, dict[str, bool]]) -> pd.DataFrame:
    rows = load_positive_rows(balance_flags) + load_negative_rows(balance_flags)
    compounds = pd.read_csv(COMPOUND_PATH, dtype=str).fillna("")
    clusters = read_mmseqs_clusters(MMSEQS_CLUSTER_PATH)
    return prepare_dataframe(assign_unified_group_splits(rows, compounds, clusters))


def candidate_terminal_rows() -> list[dict[str, Any]]:
    return [
        {
            "model_reaction_id": "CAND_T2DEC_THIOESTERASE_P",
            "reaction_name": "candidate trans-dec-2-enoyl-CoA thioesterase",
            "model_equation": "s_1507 + s_0809 --> cand_t2dec_p + s_0534 + s_0801",
            "direction": "forward",
            "lower_bound": 0,
            "upper_bound": 1000,
            "enzyme_evidence_rows": 0,
            "enzyme_ec_numbers": "3.1.2.-|3.1.2.2",
            "gpr": "",
            "has_formula_balance": 1,
            "has_charge_balance": 1,
            "score_group": "10h2da_terminal_hypothesis",
        },
        {
            "model_reaction_id": "CAND_T2DEC_OMEGA_HYDROXYLASE_P",
            "reaction_name": "candidate trans-2-decenoate omega-hydroxylase",
            "model_equation": "cand_t2dec_p + s_1215 + s_1279 + s_0801 --> cand_10h2da_p + s_1211 + s_0809",
            "direction": "forward",
            "lower_bound": 0,
            "upper_bound": 1000,
            "enzyme_evidence_rows": 0,
            "enzyme_ec_numbers": "1.14.-.-|1.14.14.-",
            "gpr": "",
            "has_formula_balance": 1,
            "has_charge_balance": 1,
            "score_group": "10h2da_terminal_hypothesis",
        },
        {
            "model_reaction_id": "CAND_T2DEC_COA_OMEGA_HYDROXYLASE_P",
            "reaction_name": "candidate trans-dec-2-enoyl-CoA omega-hydroxylase",
            "model_equation": "s_1507 + s_1215 + s_1279 + s_0801 --> cand_10h2da_coa_p + s_1211 + s_0809",
            "direction": "forward",
            "lower_bound": 0,
            "upper_bound": 1000,
            "enzyme_evidence_rows": 0,
            "enzyme_ec_numbers": "1.14.-.-|1.14.14.-",
            "gpr": "",
            "has_formula_balance": 1,
            "has_charge_balance": 1,
            "score_group": "10h2da_terminal_hypothesis",
        },
        {
            "model_reaction_id": "CAND_10H2DA_COA_THIOESTERASE_P",
            "reaction_name": "candidate 10-hydroxy-trans-2-decenoyl-CoA thioesterase",
            "model_equation": "cand_10h2da_coa_p + s_0809 --> cand_10h2da_p + s_0534 + s_0801",
            "direction": "forward",
            "lower_bound": 0,
            "upper_bound": 1000,
            "enzyme_evidence_rows": 0,
            "enzyme_ec_numbers": "3.1.2.-|3.1.2.2",
            "gpr": "",
            "has_formula_balance": 1,
            "has_charge_balance": 1,
            "score_group": "10h2da_terminal_hypothesis",
        },
    ]


def prepare_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(rows).fillna("")
    for col in TEXT_FIELDS:
        if col not in df.columns:
            df[col] = ""
    df["text"] = df[TEXT_FIELDS].astype(str).agg(" ; ".join, axis=1)
    df["lower_bound_num"] = pd.to_numeric(df.get("lower_bound", 0), errors="coerce").fillna(0.0)
    df["upper_bound_num"] = pd.to_numeric(df.get("upper_bound", 0), errors="coerce").fillna(0.0)
    df["enzyme_evidence_rows_num"] = pd.to_numeric(df.get("enzyme_evidence_rows", 0), errors="coerce").fillna(0.0)
    df["reactant_count"] = df.get("reactant_compound_uids", "").map(lambda value: len(split_values(value))) if "reactant_compound_uids" in df.columns else 0
    df["product_count"] = df.get("product_compound_uids", "").map(lambda value: len(split_values(value))) if "product_compound_uids" in df.columns else 0
    df["stoich_metabolite_count"] = df.get("stoichiometry_json", "").map(count_stoich) if "stoichiometry_json" in df.columns else 0
    df["has_gpr"] = df.get("gpr", "").map(lambda value: int(has_text(value)))
    df["has_ec"] = df.get("enzyme_ec_numbers", "").map(lambda value: int(has_text(value)))
    for col in ["has_formula_balance", "has_charge_balance"]:
        if col not in df.columns:
            df[col] = 0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    return df


def count_stoich(value: Any) -> int:
    if not has_text(value):
        return 0
    try:
        return len(json.loads(str(value)))
    except json.JSONDecodeError:
        return 0


def fit_features(train_df: pd.DataFrame) -> tuple[TfidfVectorizer, StandardScaler, csr_matrix]:
    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2, max_features=60000, lowercase=True)
    scaler = StandardScaler(with_mean=False)
    text_matrix = vectorizer.fit_transform(train_df["text"])
    num_matrix = scaler.fit_transform(csr_matrix(train_df[NUMERIC_FIELDS].astype(float).values))
    return vectorizer, scaler, hstack([text_matrix, num_matrix], format="csr")


def transform_features(df: pd.DataFrame, vectorizer: TfidfVectorizer, scaler: StandardScaler) -> csr_matrix:
    text_matrix = vectorizer.transform(df["text"])
    num_matrix = scaler.transform(csr_matrix(df[NUMERIC_FIELDS].astype(float).values))
    return hstack([text_matrix, num_matrix], format="csr")


def metrics_for_split(
    name: str,
    y_true: pd.Series,
    y_prob: Any,
    group_keys: Any | None = None,
    threshold: float = 0.5,
    bootstrap_samples: int = 500,
) -> dict[str, Any]:
    groups = group_keys if group_keys is not None else [f"row:{index}" for index in range(len(y_true))]
    return evaluate_pu_split(name, y_true, y_prob, groups, threshold, bootstrap_samples, RANDOM_STATE)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def score_dataframe(df: pd.DataFrame, model: LogisticRegression, vectorizer: TfidfVectorizer, scaler: StandardScaler) -> pd.DataFrame:
    work = prepare_dataframe(df.to_dict("records"))
    probs = model.predict_proba(transform_features(work, vectorizer, scaler))[:, 1]
    out = work.copy()
    out["reference_likeness_score"] = probs
    return out


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Phase 2 Reaction Evidence Baseline Training",
        "",
        f"Generated: {payload['generated_at']}",
        f"Model version: `{payload['model_version']}`",
        "",
        "## Training Design",
        "",
        "Working binary baseline trained with curated external-crossref reactions as labeled positives and model-context candidates as unlabeled working negatives. This is a reference-likeness model, not a final biochemical truth model.",
        "",
        "## Dataset",
        "",
        "| Split | Rows | Labeled positives | Unlabeled |",
        "|---|---:|---:|---:|",
    ]
    for split, counts in payload["split_counts"].items():
        lines.append(f"| {split} | {counts['rows']} | {counts['positives']} | {counts['unlabeled']} |")
    lines.extend(["", "## PU Metrics", "", "| Split | Labeled-positive recall | Unlabeled selected | Observed-label ROC AUC | Observed-label AP | Brier |", "|---|---:|---:|---:|---:|---:|"])
    for row in payload["metrics"]:
        metric = row["metrics"]
        roc = metric["observed_label_roc_auc"]
        lines.append(f"| {row['split']} | {metric['labeled_positive_recall']:.6f} | {metric['unlabeled_predicted_positive_rate']:.6f} | {roc:.6f} | {metric['observed_label_average_precision']:.6f} | {metric['observed_label_brier_score']:.6f} |")
    lines.extend(
        [
            "",
            "## 10H2DA Terminal Scores",
            "",
            "| Reaction | Score |",
            "|---|---:|",
        ]
    )
    for row in payload["terminal_scores"]:
        lines.append(f"| {row['model_reaction_id']} | {row['reference_likeness_score']:.6f} |")
    lines.extend(
        [
            "",
            "## Outputs",
            "",
            "- `03_models/phase2_reaction_evidence_baseline_v1.joblib`",
            "- `03_models/phase2_reaction_evidence_baseline_v1_manifest.json`",
            "- `05_training/reaction_evidence_baseline_training_matrix.csv`",
            "- `06_evaluation/phase2_reaction_evidence_baseline_metrics.json`",
            "- `06_evaluation/phase2_reaction_evidence_baseline_metrics.csv`",
            "- `06_evaluation/phase2_reaction_evidence_baseline_calibration_curve.csv`",
            "- `06_evaluation/phase2_candidate_extension_evidence_scores.csv`",
            "- `06_evaluation/10h2da_terminal_candidate_scores.csv`",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    MODEL_DIR.mkdir(exist_ok=True)
    EVAL_DIR.mkdir(exist_ok=True)
    REPORT_DIR.mkdir(exist_ok=True)
    balance_flags = load_balance_flags()
    df = load_grouped_training_dataframe(balance_flags)
    matrix_cols = [
        "model_reaction_id",
        "reaction_name",
        "model_equation",
        "label",
        "label_name",
        "model_split",
        "split_group_key",
        "protein_homology_clusters",
        "normalized_reaction_signature",
        "substrate_structure_signature",
        *NUMERIC_FIELDS,
        "text",
    ]
    df[matrix_cols].to_csv(TRAIN_DIR / "reaction_evidence_baseline_training_matrix.csv", index=False)

    train_df = df[df["model_split"] == "train"].copy()
    dev_df = df[df["model_split"] == "dev"].copy()
    test_df = df[df["model_split"] == "test"].copy()
    vectorizer, scaler, x_train = fit_features(train_df)
    y_train = train_df["label"].astype(int)
    model = LogisticRegression(max_iter=2000, class_weight="balanced", random_state=RANDOM_STATE, solver="liblinear")
    model.fit(x_train, y_train)

    dev_probs = model.predict_proba(transform_features(dev_df, vectorizer, scaler))[:, 1]
    threshold_selection = select_positive_recall_threshold(dev_df["label"].astype(int), dev_probs)
    threshold = threshold_selection["value"]
    metrics = []
    for name, split_df in [("train", train_df), ("dev", dev_df), ("test", test_df)]:
        probs = model.predict_proba(transform_features(split_df, vectorizer, scaler))[:, 1]
        metrics.append(metrics_for_split(name, split_df["label"].astype(int), probs, split_df["split_group_key"], threshold))

    candidate_df = pd.read_csv(TRAIN_DIR / "reaction_candidate_extension_evidence.csv", dtype=str).fillna("")
    candidate_scores = score_dataframe(candidate_df, model, vectorizer, scaler)
    candidate_score_cols = [
        "model_reaction_id",
        "reaction_name",
        "model_equation",
        "rxndb_id",
        "rxndb_ec_number",
        "enzyme_ec_numbers",
        "reference_likeness_score",
    ]
    candidate_scores[candidate_score_cols].sort_values("reference_likeness_score", ascending=False).to_csv(
        EVAL_DIR / "phase2_candidate_extension_evidence_scores.csv", index=False
    )

    terminal_scores = score_dataframe(pd.DataFrame(candidate_terminal_rows()), model, vectorizer, scaler)
    terminal_cols = ["model_reaction_id", "reaction_name", "model_equation", "enzyme_ec_numbers", "reference_likeness_score"]
    terminal_scores[terminal_cols].to_csv(EVAL_DIR / "10h2da_terminal_candidate_scores.csv", index=False)

    split_counts = {}
    for split, split_df in df.groupby("model_split"):
        split_counts[split] = {
            "rows": int(len(split_df)),
            "positives": int(split_df["label"].sum()),
            "unlabeled": int(len(split_df) - split_df["label"].sum()),
        }

    model_payload = {
        "model": model,
        "vectorizer": vectorizer,
        "scaler": scaler,
        "text_fields": TEXT_FIELDS,
        "numeric_fields": NUMERIC_FIELDS,
        "model_version": MODEL_VERSION,
        "label_semantics": {"1": "curated_reference", "0": "unlabeled_candidate_not_confirmed_negative"},
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
    provenance = environment_provenance([Path(__file__), Path(__file__).with_name("reaction_evidence_ml_utils.py")], ROOT)
    leakage_audit = audit_split_leakage(df)
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "model_version": MODEL_VERSION,
        "model_path": str(model_path.relative_to(ROOT)),
        "artifact": {"path": str(model_path.relative_to(ROOT)), "sha256": sha256_file(model_path), "bytes": model_path.stat().st_size},
        "data_artifacts": file_records(data_paths, ROOT),
        "source_artifacts": file_records(source_paths, ROOT),
        "provenance": provenance,
        "training_rows": int(len(df)),
        "split_counts": split_counts,
        "metrics": metrics,
        "threshold_selection": threshold_selection,
        "leakage_audit": leakage_audit,
        "pu_setting": {
            "positive": "curated or database-cross-referenced reactions",
            "unlabeled": "model-context candidates without positive provenance; may contain latent positives",
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
            "This baseline intentionally excludes external cross-reference and RXNdb ID fields from features to avoid direct label leakage.",
            "Label 0 means unlabeled and is never interpreted as a confirmed false reaction.",
            "Candidate scores are prioritization signals and do not replace database or experimental validation.",
        ],
    }
    (MODEL_DIR / f"{MODEL_VERSION}_manifest.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (EVAL_DIR / "phase2_reaction_evidence_baseline_metrics.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    metric_rows = [{"split": row["split"], "rows": row["rows"], "groups": row["groups"], "threshold": row["threshold"], **row["metrics"]} for row in metrics]
    write_csv(EVAL_DIR / "phase2_reaction_evidence_baseline_metrics.csv", metric_rows, list(metric_rows[0].keys()))
    calibration_rows = [{"split": row["split"], **point} for row in metrics for point in row["calibration_curve"]]
    write_csv(EVAL_DIR / "phase2_reaction_evidence_baseline_calibration_curve.csv", calibration_rows, list(calibration_rows[0].keys()))
    card = (MODEL_DIR / "reaction_evidence_model_card_template.md").read_text(encoding="utf-8").replace("{{ model_version }}", MODEL_VERSION).replace("{{ license_status }}", payload["license"]["status"])
    (MODEL_DIR / f"{MODEL_VERSION}_model_card.md").write_text(card, encoding="utf-8")
    (REPORT_DIR / "phase2_reaction_evidence_baseline_training.md").write_text(render_report(payload), encoding="utf-8")
    print(REPORT_DIR / "phase2_reaction_evidence_baseline_training.md")


if __name__ == "__main__":
    main()
