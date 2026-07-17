from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, recall_score, roc_auc_score


SPLITS = ("train", "dev", "test")
DEPENDENCIES = ("joblib", "numpy", "pandas", "scikit-learn", "scipy")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_split(group_key: str) -> str:
    bucket = int(sha256_text(group_key)[:12], 16) % 100
    return "train" if bucket < 80 else ("dev" if bucket < 90 else "test")


def split_pipe(value: Any) -> list[str]:
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return []
    return sorted({item.strip() for item in re.split(r"[|;]", text) if item.strip() and item.strip().lower() != "nogene"})


def read_mmseqs_clusters(path: Path) -> dict[str, str]:
    member_to_representative: dict[str, str] = {}
    if not path.exists():
        return member_to_representative
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 2:
                representative, member = parts[:2]
                member_to_representative[member] = representative
                member_to_representative.setdefault(representative, representative)
    return member_to_representative


def compound_identifiers(compounds: pd.DataFrame) -> dict[str, tuple[str, bool]]:
    identifiers: dict[str, tuple[str, bool]] = {}
    priorities = (
        ("inchikey", "inchikey", True),
        ("smiles", "smiles", True),
        ("metanetx_id", "metanetx", False),
        ("chebi_id", "chebi", False),
        ("kegg_id", "kegg", False),
        ("compound_uid", "compound_uid", False),
    )
    for row in compounds.fillna("").to_dict("records"):
        model_id = str(row.get("model_metabolite_id", "")).strip()
        if not model_id:
            continue
        for field, prefix, is_structure in priorities:
            value = str(row.get(field, "")).strip()
            if value:
                normalized = re.sub(r"\s+", "", value).upper() if field == "inchikey" else re.sub(r"\s+", "", value)
                identifiers[model_id] = (f"{prefix}:{normalized}", is_structure)
                break
        else:
            identifiers[model_id] = (f"model_metabolite:{model_id}", False)
    return identifiers


def _canonical_stoichiometry(row: dict[str, Any], compounds: dict[str, tuple[str, bool]]) -> tuple[str, str, int, int]:
    try:
        stoichiometry = json.loads(str(row.get("stoichiometry_json", "")) or "{}")
    except (json.JSONDecodeError, TypeError, ValueError):
        stoichiometry = {}
    sides: dict[str, float] = defaultdict(float)
    structure_count = 0
    for metabolite, coefficient in stoichiometry.items():
        identifier, is_structure = compounds.get(str(metabolite), (f"model_metabolite:{metabolite}", False))
        sides[identifier] += float(coefficient)
        structure_count += int(is_structure)
    terms = sorted((identifier, round(value, 12)) for identifier, value in sides.items() if abs(value) > 1e-12)
    if not terms:
        equation = re.sub(r"\s+", "", str(row.get("model_equation", "")).lower())
        return f"equation:{equation}", "", 0, 0
    forward = "|".join(f"{identifier}:{coefficient:g}" for identifier, coefficient in terms)
    reverse = "|".join(f"{identifier}:{-coefficient:g}" for identifier, coefficient in sorted(terms))
    reaction = min(forward, reverse)
    substrates = sorted(identifier for identifier, coefficient in terms if coefficient < 0)
    products = sorted(identifier for identifier, coefficient in terms if coefficient > 0)
    substrate_set = min("|".join(substrates), "|".join(products))
    substrate_signature = f"substrates:{sha256_text(substrate_set)}" if structure_count else ""
    return f"stoich:{sha256_text(reaction)}", substrate_signature, structure_count, len(terms)


def _reaction_xrefs(row: dict[str, Any]) -> list[str]:
    fields = ("metanetx_reaction_id", "kegg_reaction_id", "bigg_reaction_id", "rxndb_id")
    return [f"xref:{field}:{value}" for field in fields for value in split_pipe(row.get(field, ""))]


def _row_tokens(
    row: dict[str, Any],
    compounds: dict[str, tuple[str, bool]],
    member_to_representative: dict[str, str],
) -> tuple[list[str], dict[str, Any]]:
    orfs = split_pipe(row.get("orfs", ""))
    clusters = sorted({member_to_representative.get(orf, f"unclustered:{orf}") for orf in orfs})
    reaction_signature, substrate_signature, structure_count, metabolite_count = _canonical_stoichiometry(row, compounds)
    tokens = [f"protein_cluster:{cluster}" for cluster in clusters]
    tokens.extend(_reaction_xrefs(row))
    if reaction_signature != "equation:":
        tokens.append(f"reaction:{reaction_signature}")
    if substrate_signature:
        tokens.append(substrate_signature)
    if not tokens:
        tokens.append(f"reaction_id:{row.get('model_reaction_id', '')}")
    annotation = {
        "protein_homology_clusters": "|".join(clusters),
        "normalized_reaction_signature": reaction_signature,
        "substrate_structure_signature": substrate_signature,
        "structure_identified_metabolites": structure_count,
        "reaction_metabolites": metabolite_count,
    }
    return sorted(set(tokens)), annotation


class _DisjointSet:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, left: int, right: int) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def assign_unified_group_splits(
    rows: list[dict[str, Any]],
    compounds: pd.DataFrame,
    member_to_representative: dict[str, str],
) -> list[dict[str, Any]]:
    compound_map = compound_identifiers(compounds)
    row_tokens: list[list[str]] = []
    annotations: list[dict[str, Any]] = []
    token_owner: dict[str, int] = {}
    groups = _DisjointSet(len(rows))
    for index, row in enumerate(rows):
        tokens, annotation = _row_tokens(row, compound_map, member_to_representative)
        row_tokens.append(tokens)
        annotations.append(annotation)
        for token in tokens:
            if token in token_owner:
                groups.union(index, token_owner[token])
            else:
                token_owner[token] = index
    component_tokens: dict[int, set[str]] = defaultdict(set)
    for index, tokens in enumerate(row_tokens):
        component_tokens[groups.find(index)].update(tokens)
    output: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        root = groups.find(index)
        anchor = min(component_tokens[root])
        group_key = "unified:" + sha256_text(anchor)
        out = dict(row)
        out.update(annotations[index])
        out["split_group_key"] = group_key
        out["split_group_evidence"] = "|".join(row_tokens[index])
        out["model_split"] = stable_split(group_key)
        output.append(out)
    return output


def audit_split_leakage(df: pd.DataFrame) -> dict[str, Any]:
    dimensions = {
        "split_group_key": False,
        "protein_homology_clusters": True,
        "normalized_reaction_signature": False,
        "substrate_structure_signature": False,
    }
    details: dict[str, Any] = {}
    for column, multi_value in dimensions.items():
        owners: dict[str, set[str]] = defaultdict(set)
        if column not in df.columns:
            details[column] = {"status": "missing", "cross_split_values": 0, "examples": []}
            continue
        for split, value in zip(df["model_split"], df[column]):
            values = split_pipe(value) if multi_value else ([str(value)] if str(value).strip() else [])
            for item in values:
                owners[item].add(str(split))
        crossing = sorted(item for item, splits in owners.items() if len(splits) > 1)
        details[column] = {"status": "pass" if not crossing else "fail", "cross_split_values": len(crossing), "examples": crossing[:10]}
    passed = all(result["status"] == "pass" for result in details.values())
    return {"status": "pass" if passed else "fail", "dimensions": details}


def select_positive_recall_threshold(y_true: Iterable[int], y_prob: Iterable[float], target_recall: float = 0.9) -> dict[str, Any]:
    labels = np.asarray(list(y_true), dtype=int)
    probabilities = np.asarray(list(y_prob), dtype=float)
    positive_probabilities = np.sort(probabilities[labels == 1])[::-1]
    if not len(positive_probabilities):
        raise ValueError("development split has no labeled positives")
    required = max(1, int(np.ceil(target_recall * len(positive_probabilities))))
    threshold = float(positive_probabilities[required - 1])
    achieved = float(recall_score(labels, probabilities >= threshold, zero_division=0))
    return {
        "value": threshold,
        "selected_on_split": "dev",
        "method": "highest score cutoff retaining target labeled-positive recall",
        "target_labeled_positive_recall": target_recall,
        "achieved_labeled_positive_recall": achieved,
        "warning": "The cutoff is an operating threshold for PU prioritization, not a truth-classification threshold.",
    }


def _calibration(y_true: np.ndarray, y_prob: np.ndarray, bins: int = 10) -> tuple[float, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    ece = 0.0
    edges = np.linspace(0.0, 1.0, bins + 1)
    for index in range(bins):
        mask = (y_prob >= edges[index]) & ((y_prob <= edges[index + 1]) if index == bins - 1 else (y_prob < edges[index + 1]))
        if not mask.any():
            continue
        mean_prediction = float(y_prob[mask].mean())
        observed_fraction = float(y_true[mask].mean())
        count = int(mask.sum())
        ece += count / len(y_true) * abs(mean_prediction - observed_fraction)
        rows.append({
            "bin_lower": float(edges[index]),
            "bin_upper": float(edges[index + 1]),
            "rows": count,
            "mean_score": mean_prediction,
            "observed_labeled_positive_fraction": observed_fraction,
        })
    return float(ece), rows


def _point_metrics(y_true: np.ndarray, y_prob: np.ndarray, threshold: float) -> dict[str, float | None]:
    predicted = y_prob >= threshold
    labeled = y_true == 1
    unlabeled = ~labeled
    ece, _ = _calibration(y_true, y_prob)
    result: dict[str, float | None] = {
        "labeled_positive_recall": float(recall_score(y_true, predicted, zero_division=0)),
        "unlabeled_predicted_positive_rate": float(predicted[unlabeled].mean()) if unlabeled.any() else None,
        "labeled_positive_mean_score": float(y_prob[labeled].mean()) if labeled.any() else None,
        "unlabeled_mean_score": float(y_prob[unlabeled].mean()) if unlabeled.any() else None,
        "observed_label_average_precision": float(average_precision_score(y_true, y_prob)) if labeled.any() else None,
        "observed_label_roc_auc": float(roc_auc_score(y_true, y_prob)) if len(np.unique(y_true)) == 2 else None,
        "observed_label_brier_score": float(brier_score_loss(y_true, y_prob)),
        "observed_label_log_loss": float(log_loss(y_true, np.clip(y_prob, 1e-7, 1 - 1e-7), labels=[0, 1])),
        "observed_label_expected_calibration_error": ece,
    }
    return result


def evaluate_pu_split(
    name: str,
    y_true: Iterable[int],
    y_prob: Iterable[float],
    group_keys: Iterable[str],
    threshold: float,
    bootstrap_samples: int = 500,
    random_state: int = 17,
) -> dict[str, Any]:
    labels = np.asarray(list(y_true), dtype=int)
    probabilities = np.asarray(list(y_prob), dtype=float)
    groups = np.asarray(list(group_keys), dtype=object)
    point = _point_metrics(labels, probabilities, threshold)
    _, curve = _calibration(labels, probabilities)
    unique_groups = np.unique(groups)
    rng = np.random.default_rng(random_state)
    samples: dict[str, list[float]] = defaultdict(list)
    for _ in range(bootstrap_samples):
        sampled_groups = rng.choice(unique_groups, size=len(unique_groups), replace=True)
        indices = np.concatenate([np.flatnonzero(groups == group) for group in sampled_groups])
        bootstrap = _point_metrics(labels[indices], probabilities[indices], threshold)
        for metric, value in bootstrap.items():
            if value is not None and np.isfinite(value):
                samples[metric].append(float(value))
    confidence_intervals = {
        metric: {"lower": float(np.percentile(values, 2.5)), "upper": float(np.percentile(values, 97.5)), "method": "group_bootstrap_percentile"}
        for metric, values in samples.items()
        if values
    }
    return {
        "split": name,
        "rows": int(len(labels)),
        "groups": int(len(unique_groups)),
        "labeled_positive_rows": int(labels.sum()),
        "unlabeled_rows": int(len(labels) - labels.sum()),
        "threshold": float(threshold),
        "metrics": point,
        "bootstrap_95_ci": confidence_intervals,
        "calibration_curve": curve,
        "calibration_semantics": "Observed-label calibration only; unlabeled rows may contain positives, so this is not probability-of-biochemical-truth calibration.",
    }


def environment_provenance(code_paths: Iterable[Path], root: Path) -> dict[str, Any]:
    dependencies = {}
    for package in DEPENDENCIES:
        try:
            dependencies[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            dependencies[package] = "not_installed"
    code_files = {str(path.relative_to(root)): sha256_file(path) for path in code_paths if path.exists()}
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, check=True, timeout=5
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        commit = "not_available_not_a_git_checkout"
    return {
        "code_version": {"git_commit": commit, "code_file_sha256": code_files},
        "runtime": {"python": sys.version.split()[0], "implementation": platform.python_implementation(), "platform": platform.platform()},
        "dependencies": dependencies,
    }


def file_records(paths: Iterable[Path], root: Path) -> list[dict[str, Any]]:
    return [
        {"path": str(path.relative_to(root)), "sha256": sha256_file(path), "bytes": path.stat().st_size}
        for path in paths
        if path.exists()
    ]


def verify_model_artifact(model_path: Path, manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = manifest.get("artifact", {}).get("sha256")
    if not expected:
        raise ValueError("manifest does not contain artifact.sha256")
    actual = sha256_file(model_path)
    if actual != expected:
        raise ValueError(f"model artifact SHA256 mismatch: expected {expected}, got {actual}")
    return manifest


def load_joblib_verified(model_path: Path, manifest_path: Path, required_keys: Iterable[str] = ()) -> Any:
    manifest = verify_model_artifact(model_path, manifest_path)
    payload = joblib.load(model_path)
    if not isinstance(payload, dict):
        raise ValueError("model payload must be a dictionary")
    missing = sorted(set(required_keys) - set(payload))
    if missing:
        raise ValueError(f"model payload missing required keys: {missing}")
    if manifest.get("model_version") != payload.get("model_version"):
        raise ValueError("manifest and model payload versions differ")
    return payload
