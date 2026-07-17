from __future__ import annotations

import math
import pickle
import re
import sys
from pathlib import Path
from typing import Any

from .schema import (
    ApplicabilityReport,
    BenchmarkReport,
    InputTransform,
    PluginInput,
    PluginResult,
    Prediction,
    RunStatus,
    UncertaintyReport,
)


PLUGIN_VERSION = "2023-paper-model-local-snapshot"
SEQUENCE_LIMIT = 1000
SMILES_TOKEN_LIMIT = 218


def split_smiles(smiles: str) -> list[str]:
    two_character = {
        "Cl", "Ca", "Cu", "Br", "Be", "Ba", "Bi", "Si", "Se", "Sr", "Na", "Ni", "Rb", "Ra",
        "Xe", "Li", "Al", "As", "Ag", "Au", "Mg", "Mn", "Te", "Zn", "si", "se", "te", "He",
        "+2", "+3", "+4", "-2", "-3", "-4", "Kr", "Fe",
    }
    tokens: list[str] = []
    index = 0
    while index < len(smiles):
        if smiles[index] == "%" and index + 2 < len(smiles):
            tokens.append(smiles[index : index + 3])
            index += 3
        elif smiles[index : index + 2] in two_character:
            tokens.append(smiles[index : index + 2])
            index += 2
        else:
            tokens.append(smiles[index])
            index += 1
    return tokens


def prepare_input(request: PluginInput) -> tuple[str, list[str], tuple[InputTransform, ...]]:
    if request.capability not in {"kcat_prediction", "km_prediction", "kcat_km_prediction"}:
        raise ValueError(f"unsupported UniKP capability: {request.capability}")
    if request.sequence is None or request.substrate_smiles is None:
        raise ValueError("UniKP requires sequence and substrate_smiles")

    sequence = re.sub(r"\s+", "", request.sequence.upper())
    invalid = sorted(set(sequence) - set("ABCDEFGHIKLMNPQRSTVWXYZUO"))
    if invalid:
        raise ValueError(f"sequence contains invalid residues: {''.join(invalid)}")
    sequence_truncated = len(sequence) > SEQUENCE_LIMIT
    effective_sequence = sequence[:500] + sequence[-500:] if sequence_truncated else sequence

    smiles_tokens = split_smiles(request.substrate_smiles)
    smiles_truncated = len(smiles_tokens) > SMILES_TOKEN_LIMIT
    effective_tokens = smiles_tokens[:109] + smiles_tokens[-109:] if smiles_truncated else smiles_tokens
    transforms = (
        InputTransform("sequence", len(sequence), len(effective_sequence), sequence_truncated, "head_500_tail_500" if sequence_truncated else "none"),
        InputTransform("substrate_smiles_tokens", len(smiles_tokens), len(effective_tokens), smiles_truncated, "head_109_tail_109" if smiles_truncated else "none"),
    )
    return effective_sequence, effective_tokens, transforms


def assess_applicability(transforms: tuple[InputTransform, ...]) -> ApplicabilityReport:
    reasons = tuple(f"{item.field}_truncated" for item in transforms if item.truncated)
    if reasons:
        return ApplicabilityReport(
            "assessed",
            False,
            True,
            "Input exceeds an upstream UniKP encoder limit and was truncated",
            reasons,
        )
    return ApplicabilityReport(
        "not_available",
        None,
        None,
        "No versioned UniKP training-domain reference is deployed",
    )


def _load_pickle(path: Path, code_dir: Path) -> Any:
    import __main__
    import build_vocab

    setattr(__main__, "WordVocab", build_vocab.WordVocab)
    with path.open("rb") as handle:
        return pickle.load(handle)


def predict(request: PluginInput, plugin_root: Path) -> PluginResult:
    sequence, smiles_tokens, transforms = prepare_input(request)
    models_dir = plugin_root / "UniKP" / "models"
    code_dir = plugin_root / "UniKP" / "code"
    if str(code_dir) not in sys.path:
        sys.path.insert(0, str(code_dir))

    try:
        import numpy as np
        import torch
        from build_vocab import WordVocab
        from pretrain_trfm import TrfmSeq2seq
        from transformers import T5EncoderModel, T5Tokenizer

        vocab = WordVocab.load_vocab(str(models_dir / "vocab.pkl"))
        ids = [3] + [vocab.stoi.get(token, 1) for token in smiles_tokens] + [2]
        ids.extend([0] * (220 - len(ids)))
        trfm = TrfmSeq2seq(len(vocab), 256, len(vocab), 4)
        trfm.load_state_dict(torch.load(models_dir / "trfm_12_23000.pkl", map_location="cpu"))
        trfm.eval()
        with torch.no_grad():
            smiles_vector = trfm.encode(torch.tensor(ids, dtype=torch.long).reshape(-1, 1)).astype(float)

        encoder_dir = models_dir / "prot_t5_xl_uniref50"
        tokenizer = T5Tokenizer.from_pretrained(str(encoder_dir), local_files_only=True, legacy=True, use_fast=False)
        encoder = T5EncoderModel.from_pretrained(str(encoder_dir), local_files_only=True)
        encoder.eval()
        prepared_sequence = " ".join(re.sub(r"[UZOB]", "X", sequence))
        encoded = tokenizer([prepared_sequence], add_special_tokens=True, padding=True, return_tensors="pt")
        with torch.no_grad():
            hidden = encoder(**encoded).last_hidden_state.cpu().numpy()
        amino_acids = int(encoded["attention_mask"][0].sum()) - 1
        sequence_vector = hidden[0][:amino_acids].mean(axis=0).reshape(1, -1)
        features = np.concatenate((smiles_vector, sequence_vector), axis=1)

        filenames = {
            "kcat_prediction": ("kcat", "UniKP for kcat.pkl", "s^-1"),
            "km_prediction": ("Km", "UniKP for Km.pkl", "mM"),
            "kcat_km_prediction": ("kcat/Km", "UniKP for kcat_Km.pkl", "s^-1 mM^-1"),
        }
        name, filename, unit = filenames[request.capability]
        model = _load_pickle(models_dir / filename, code_dir)
        log_value = float(model.predict(features)[0])
        tree_values = np.array([tree.predict(features)[0] for tree in getattr(model, "estimators_", [])], dtype=float)
        uncertainty = (
            UncertaintyReport(
                "available",
                "ExtraTrees member standard deviation and 5th-95th percentile member interval in log10 space (uncalibrated)",
                float(tree_values.std()),
                interval=(float(np.quantile(tree_values, 0.05)), float(np.quantile(tree_values, 0.95))),
                tree_member_count=int(tree_values.size),
                tree_member_interval_log10=(float(np.quantile(tree_values, 0.05)), float(np.quantile(tree_values, 0.95))),
                calibrated=False,
            )
            if tree_values.size
            else UncertaintyReport("not_available", method="model exposes no ensemble members")
        )
        applicability = assess_applicability(transforms)
        return PluginResult(
            request_id=request.request_id,
            plugin="UniKP",
            plugin_version=PLUGIN_VERSION,
            capability=request.capability,
            status=RunStatus.READY,
            predictions=(
                Prediction(f"log10_{name}", log_value, f"log10({unit})", "log10"),
                Prediction(name, math.pow(10.0, log_value), unit),
            ),
            transforms=transforms,
            applicability=applicability,
            uncertainty=uncertainty,
            benchmark=BenchmarkReport(),
            messages=("Prediction is for prioritization and is not curated kinetic evidence.",),
        )
    except Exception as exc:
        return PluginResult(
            request_id=request.request_id,
            plugin="UniKP",
            plugin_version=PLUGIN_VERSION,
            capability=request.capability,
            status=RunStatus.ERROR,
            transforms=transforms,
            applicability=ApplicabilityReport("not_available", None, None, "runtime failed before domain assessment"),
            uncertainty=UncertaintyReport("not_available"),
            messages=(f"{type(exc).__name__}: {exc}",),
        )
