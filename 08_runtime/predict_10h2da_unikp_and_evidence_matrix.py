from __future__ import annotations

import csv
import json
import math
import pickle
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
from transformers import T5EncoderModel, T5Tokenizer
from deployment_config import load_deployment_config


ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT / "06_evaluation"
REPORT_DIR = ROOT / "07_reports"
UNIKP_DIR = ROOT / "04_prediction_plugins" / "UniKP"
UNIKP_CODE = UNIKP_DIR / "code"
UNIKP_MODELS = UNIKP_DIR / "models"
YEAST_FASTA = Path(load_deployment_config()["source_project_dir"]) / "Data" / "Saccharomyces_cerevisiae.fasta"

if str(UNIKP_CODE) not in sys.path:
    sys.path.insert(0, str(UNIKP_CODE))

import build_vocab  # noqa: E402
from build_vocab import WordVocab  # noqa: E402
from pretrain_trfm import TrfmSeq2seq  # noqa: E402


def split(sm: str) -> str:
    arr = []
    two_char = {"Cl", "Ca", "Cu", "Br", "Be", "Ba", "Bi", "Si", "Se", "Sr", "Na", "Ni", "Rb", "Ra", "Xe", "Li", "Al", "As", "Ag", "Au", "Mg", "Mn", "Te", "Zn", "si", "se", "te", "He", "+2", "+3", "+4", "-2", "-3", "-4", "Kr", "Fe"}
    i = 0
    while i < len(sm) - 1:
        if sm[i] == "%":
            arr.append(sm[i : i + 3])
            i += 3
        elif sm[i : i + 2] in two_char:
            arr.append(sm[i : i + 2])
            i += 2
        else:
            arr.append(sm[i])
            i += 1
    if i == len(sm) - 1:
        arr.append(sm[i])
    return " ".join(arr)


SUBSTRATES = {
    "trans_2_decenoic_acid": {
        "name": "trans-2-decenoic acid",
        "smiles": "CCCCCCC/C=C/C(=O)O",
        "smiles_source": "PubChem CID 5282724 isomeric SMILES",
    },
    "trans_dec_2_enoyl_coa": {
        "name": "trans-dec-2-enoyl-CoA",
        "smiles": "CCCCCCC/C=C/C(=O)SCCNC(=O)CCNC(=O)[C@@H](C(C)(C)COP(=O)(O)OP(=O)(O)OC[C@@H]1[C@H]([C@H]([C@@H](O1)N2C=NC3=C(N=CN=C32)N)O)OP(=O)(O)O)O",
        "smiles_source": "PubChem CID 24883423 isomeric SMILES",
    },
    "10h2da_coa": {
        "name": "10-hydroxy-trans-2-decenoyl-CoA",
        "smiles": "OCCCCCCC/C=C/C(=O)SCCNC(=O)CCNC(=O)[C@@H](C(C)(C)COP(=O)(O)OP(=O)(O)OC[C@@H]1[C@H]([C@H]([C@@H](O1)N2C=NC3=C(N=CN=C32)N)O)OP(=O)(O)O)O",
        "smiles_source": "derived from PubChem trans-dec-2-enoyl-CoA by omega hydroxyl substitution; no direct PubChem hit found",
    },
}

REACTION_SUBSTRATES = {
    "CAND_T2DEC_THIOESTERASE_P": ("trans_dec_2_enoyl_coa", "possible_thioesterase_class_support"),
    "CAND_T2DEC_OMEGA_HYDROXYLASE_P": ("trans_2_decenoic_acid", "possible_oxygenase_class_support"),
    "CAND_T2DEC_COA_OMEGA_HYDROXYLASE_P": ("trans_dec_2_enoyl_coa", "possible_oxygenase_class_support"),
    "CAND_10H2DA_COA_THIOESTERASE_P": ("10h2da_coa", "possible_thioesterase_class_support"),
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_fasta(path: Path) -> dict[str, str]:
    records: dict[str, str] = {}
    current: str | None = None
    parts: list[str] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            if line.startswith(">"):
                if current:
                    records[current] = "".join(parts)
                current = line[1:].split()[0]
                parts = []
            else:
                parts.append(line)
    if current:
        records[current] = "".join(parts)
    return records


def first_orf(gene_names: str, fasta: dict[str, str]) -> str:
    for token in re.split(r"[\s,;]+", gene_names):
        if re.fullmatch(r"Y[A-Z]{2}\d{3}[CW](?:-[A-Z])?", token) and token in fasta:
            return token
    return ""


def smiles_to_vec(smiles: list[str]) -> np.ndarray:
    pad_index = 0
    unk_index = 1
    eos_index = 2
    sos_index = 3
    vocab = WordVocab.load_vocab(str(UNIKP_MODELS / "vocab.pkl"))

    def get_inputs(sm: str) -> tuple[list[int], list[int]]:
        seq_len = 220
        tokens = sm.split()
        if len(tokens) > 218:
            tokens = tokens[:109] + tokens[-109:]
        ids = [vocab.stoi.get(token, unk_index) for token in tokens]
        ids = [sos_index] + ids + [eos_index]
        seg = [1] * len(ids)
        padding = [pad_index] * (seq_len - len(ids))
        ids.extend(padding)
        seg.extend(padding)
        return ids, seg

    split_smiles = [split(sm) for sm in smiles]
    x_id = []
    x_seg = []
    for sm in split_smiles:
        ids, seg = get_inputs(sm)
        x_id.append(ids)
        x_seg.append(seg)
    trfm = TrfmSeq2seq(len(vocab), 256, len(vocab), 4)
    trfm.load_state_dict(torch.load(UNIKP_MODELS / "trfm_12_23000.pkl", map_location="cpu"))
    trfm.eval()
    with torch.no_grad():
        return trfm.encode(torch.t(torch.tensor(x_id))).astype(float)


def sequence_to_vec(sequences: list[str]) -> np.ndarray:
    prepared = []
    for sequence in sequences:
        if len(sequence) > 1000:
            sequence = sequence[:500] + sequence[-500:]
        prepared.append(" ".join(sequence))

    tokenizer = T5Tokenizer.from_pretrained(str(UNIKP_MODELS / "prot_t5_xl_uniref50"), local_files_only=True, legacy=True, use_fast=False, do_lower_case=False)
    model = T5EncoderModel.from_pretrained(str(UNIKP_MODELS / "prot_t5_xl_uniref50"), local_files_only=True)
    model.eval()
    features = []
    for sequence in prepared:
        sequence = re.sub(r"[UZOB]", "X", sequence)
        ids = tokenizer([sequence], add_special_tokens=True, padding=True)
        input_ids = torch.tensor(ids["input_ids"])
        attention_mask = torch.tensor(ids["attention_mask"])
        with torch.no_grad():
            embedding = model(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state.cpu().numpy()
        seq_len = int((attention_mask[0] == 1).sum())
        features.append(embedding[0][: seq_len - 1].mean(axis=0))
    return np.array(features, dtype=float)


def load_model(name: str) -> Any:
    import __main__

    setattr(__main__, "WordVocab", build_vocab.WordVocab)
    with (UNIKP_MODELS / name).open("rb") as handle:
        return pickle.load(handle)


def build_prediction_inputs() -> list[dict[str, Any]]:
    fasta = parse_fasta(YEAST_FASTA)
    enzymes = read_csv(EVAL_DIR / "10h2da_terminal_yeast_enzyme_candidates.csv")
    reactions = {row["model_reaction_id"]: row for row in read_csv(EVAL_DIR / "10h2da_terminal_candidate_pu_v2_scores.csv")}
    rows: list[dict[str, Any]] = []
    for enzyme in enzymes:
        orf = first_orf(enzyme["gene_names"], fasta)
        if not orf:
            continue
        for reaction_id, (substrate_key, relevance) in REACTION_SUBSTRATES.items():
            if enzyme["terminal_relevance"] != relevance:
                continue
            substrate = SUBSTRATES[substrate_key]
            reaction = reactions[reaction_id]
            rows.append(
                {
                    "candidate_reaction_id": reaction_id,
                    "reaction_name": reaction["reaction_name"],
                    "entry": enzyme["entry"],
                    "orf": orf,
                    "gene_names": enzyme["gene_names"],
                    "protein_names": enzyme["protein_names"],
                    "ec_number": enzyme["ec_number"],
                    "terminal_relevance": enzyme["terminal_relevance"],
                    "substrate_name": substrate["name"],
                    "substrate_smiles": substrate["smiles"],
                    "substrate_smiles_source": substrate["smiles_source"],
                    "sequence": fasta[orf],
                    "sequence_length": len(fasta[orf]),
                }
            )
    return rows


def predict_unikp(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    smiles_features = smiles_to_vec([row["substrate_smiles"] for row in rows])
    sequence_features = sequence_to_vec([row["sequence"] for row in rows])
    features = np.concatenate((smiles_features, sequence_features), axis=1)
    models = {
        "kcat": load_model("UniKP for kcat.pkl"),
        "Km": load_model("UniKP for Km.pkl"),
        "kcat_Km": load_model("UniKP for kcat_Km.pkl"),
    }
    predictions = {name: model.predict(features) for name, model in models.items()}
    output = []
    for idx, row in enumerate(rows):
        out = {key: value for key, value in row.items() if key != "sequence"}
        for name, values in predictions.items():
            log_value = float(values[idx])
            out[f"unikp_log10_{name}"] = log_value
            out[f"unikp_pred_{name}"] = math.pow(10.0, log_value)
        output.append(out)
    return output


def best_flux_by_reaction() -> dict[str, float]:
    best: dict[str, float] = {}
    for row in read_csv(EVAL_DIR / "10h2da_candidate_extension_fba.csv"):
        fluxes = row.get("nonzero_key_fluxes_json", "")
        if not fluxes:
            continue
        try:
            parsed = json.loads(fluxes)
        except json.JSONDecodeError:
            continue
        for reaction_id, value in parsed.items():
            best[reaction_id] = max(best.get(reaction_id, 0.0), float(value))
    return best


def build_matrix(predictions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pu = {row["model_reaction_id"]: row for row in read_csv(EVAL_DIR / "10h2da_terminal_candidate_pu_v2_scores.csv")}
    external = {row["candidate_reaction_id"]: row for row in read_csv(EVAL_DIR / "10h2da_external_evidence_verdicts.csv")}
    local = {row["candidate_reaction_id"]: row for row in read_csv(EVAL_DIR / "10h2da_terminal_validation_verdicts.csv")}
    fba = best_flux_by_reaction()
    rows = []
    for row in predictions:
        reaction_id = row["candidate_reaction_id"]
        rows.append(
            {
                "candidate_reaction_id": reaction_id,
                "reaction_name": row["reaction_name"],
                "entry": row["entry"],
                "orf": row["orf"],
                "gene_names": row["gene_names"],
                "protein_names": row["protein_names"],
                "ec_number": row["ec_number"],
                "substrate_name": row["substrate_name"],
                "substrate_smiles_source": row["substrate_smiles_source"],
                "pu_reference_likeness_score": pu[reaction_id]["pu_reference_likeness_score"],
                "external_evidence_tier": external[reaction_id]["best_evidence_tier"],
                "local_validation_verdict": local[reaction_id]["validation_verdict"],
                "local_model_support": local[reaction_id]["local_model_support"],
                "local_validation_reason": local[reaction_id]["reason"],
                "best_candidate_fba_flux": fba.get(reaction_id, 0.0),
                "unikp_log10_kcat": row["unikp_log10_kcat"],
                "unikp_pred_kcat": row["unikp_pred_kcat"],
                "unikp_log10_Km": row["unikp_log10_Km"],
                "unikp_pred_Km": row["unikp_pred_Km"],
                "unikp_log10_kcat_Km": row["unikp_log10_kcat_Km"],
                "unikp_pred_kcat_Km": row["unikp_pred_kcat_Km"],
            }
        )
    rows.sort(key=lambda r: (r["candidate_reaction_id"], -float(r["unikp_log10_kcat_Km"]), -float(r["unikp_log10_kcat"])))
    return rows


def render_report(payload: dict[str, Any], matrix: list[dict[str, Any]]) -> str:
    lines = [
        "# 10H2DA UniKP Kinetic Prioritization and Terminal Evidence Matrix",
        "",
        f"Generated: {payload['generated_at']}",
        f"Python: `{payload['python']}`",
        f"Executable: `{payload['executable']}`",
        "",
        "## Scope",
        "",
        "This run scores S. cerevisiae endogenous terminal enzyme candidates against the four 10H2DA terminal candidate reactions. UniKP values are model predictions for prioritization only; they are not curated kinetic measurements and do not validate reaction chemistry.",
        "",
        "## Outputs",
        "",
        "- `06_evaluation/10h2da_unikp_terminal_predictions.csv`",
        "- `06_evaluation/10h2da_terminal_enzyme_evidence_matrix.csv`",
        "- `06_evaluation/10h2da_unikp_terminal_prediction_manifest.json`",
        "",
        "## Substrates",
        "",
        "| Key | Name | SMILES source |",
        "|---|---|---|",
    ]
    for key, value in SUBSTRATES.items():
        lines.append(f"| {key} | {value['name']} | {value['smiles_source']} |")
    lines.extend(["", "## Top Candidates By Reaction", ""])
    for reaction_id in REACTION_SUBSTRATES:
        subset = [row for row in matrix if row["candidate_reaction_id"] == reaction_id][:5]
        lines.extend([f"### {reaction_id}", "", "| ORF | Entry | Protein | log10 kcat | log10 Km | log10 kcat/Km | External tier | Local verdict |", "|---|---|---|---:|---:|---:|---|---|"])
        for row in subset:
            protein = row["protein_names"].replace("|", "/")[:80]
            lines.append(
                f"| {row['orf']} | {row['entry']} | {protein} | {float(row['unikp_log10_kcat']):.3f} | {float(row['unikp_log10_Km']):.3f} | {float(row['unikp_log10_kcat_Km']):.3f} | {row['external_evidence_tier']} | {row['local_validation_verdict']} |"
            )
        lines.append("")
    lines.extend(
        [
            "## Interpretation",
            "",
            "The matrix should be read as a triage table. PU/FBA/UniKP/external evidence are separate evidence types. High UniKP scores increase follow-up priority for an enzyme-substrate pair, but exact terminal validation still requires biochemical or curated reaction evidence.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    rows = build_prediction_inputs()
    predictions = predict_unikp(rows)
    matrix = build_matrix(predictions)
    pred_fields = [key for key in predictions[0].keys() if key != "substrate_smiles"]
    matrix_fields = list(matrix[0].keys())
    write_csv(EVAL_DIR / "10h2da_unikp_terminal_predictions.csv", predictions, pred_fields + ["substrate_smiles"])
    write_csv(EVAL_DIR / "10h2da_terminal_enzyme_evidence_matrix.csv", matrix, matrix_fields)
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "python": sys.version,
        "executable": sys.executable,
        "candidate_pairs": len(predictions),
        "substrates": SUBSTRATES,
        "outputs": [
            "06_evaluation/10h2da_unikp_terminal_predictions.csv",
            "06_evaluation/10h2da_terminal_enzyme_evidence_matrix.csv",
            "07_reports/10H2DA_unikp_terminal_prioritization.md",
        ],
    }
    (EVAL_DIR / "10h2da_unikp_terminal_prediction_manifest.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (REPORT_DIR / "10H2DA_unikp_terminal_prioritization.md").write_text(render_report(payload, matrix), encoding="utf-8")
    print(REPORT_DIR / "10H2DA_unikp_terminal_prioritization.md")


if __name__ == "__main__":
    main()
