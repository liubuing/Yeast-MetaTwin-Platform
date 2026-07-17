from __future__ import annotations

import importlib.util
import math
import pickle
import re
from collections import defaultdict
from pathlib import Path
from types import ModuleType

from .schema import ApplicabilityReport, BenchmarkReport, InputTransform, PluginInput, PluginResult, Prediction, RunStatus, UncertaintyReport


PLUGIN_VERSION = "upstream-7c15d0d4a7ac"
CHECKPOINT = "saved_model"


def prepare_input(request: PluginInput) -> tuple[str, str, tuple[InputTransform, ...]]:
    if request.capability != "kcat_prediction":
        raise ValueError(f"unsupported DLKcat capability: {request.capability}")
    if request.sequence is None or request.substrate_smiles is None:
        raise ValueError("DLKcat requires sequence and substrate_smiles")
    sequence = re.sub(r"\s+", "", request.sequence.upper())
    if not sequence:
        raise ValueError("sequence is empty after whitespace normalization")
    if "." in request.substrate_smiles:
        raise ValueError("DLKcat upstream inference does not accept multi-component SMILES")
    return sequence, request.substrate_smiles, (
        InputTransform("sequence", len(request.sequence), len(sequence), False, "uppercase_remove_whitespace"),
    )


def _load_upstream_model(code_dir: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("dlkcat_upstream_model", code_dir / "model.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load upstream DLKcat model.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_pickle(path: Path):
    with path.open("rb") as handle:
        return pickle.load(handle)


def predict(request: PluginInput, plugin_root: Path) -> PluginResult:
    sequence, smiles, transforms = prepare_input(request)
    base = plugin_root / "DLKcat" / "DeeplearningApproach"
    input_dir = base / "Data" / "input"
    try:
        # PyTorch must load its OpenMP runtime before NumPy/RDKit on this Windows build.
        import torch
        import numpy as np
        from rdkit import Chem

        fingerprint_dict = _load_pickle(input_dir / "fingerprint_dict.pickle")
        atom_dict = _load_pickle(input_dir / "atom_dict.pickle")
        bond_dict = _load_pickle(input_dir / "bond_dict.pickle")
        edge_dict = _load_pickle(input_dir / "edge_dict.pickle")
        word_dict = _load_pickle(input_dir / "sequence_dict.pickle")

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError("RDKit could not parse substrate_smiles")
        mol = Chem.AddHs(mol)
        atoms = [atom.GetSymbol() for atom in mol.GetAtoms()]
        for atom in mol.GetAromaticAtoms():
            atoms[atom.GetIdx()] = (atoms[atom.GetIdx()], "aromatic")
        nodes = np.array([atom_dict.get(atom, 0) for atom in atoms])

        neighbors = defaultdict(list)
        for bond in mol.GetBonds():
            i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
            bond_id = bond_dict[str(bond.GetBondType())]
            neighbors[i].append((j, bond_id))
            neighbors[j].append((i, bond_id))
        edges = neighbors
        if len(nodes) == 1:
            nodes = np.array([fingerprint_dict.get(nodes[0], 0)])
        else:
            for _ in range(2):
                fingerprints = []
                for i, adjacent in edges.items():
                    fingerprint = (nodes[i], tuple(sorted((nodes[j], edge) for j, edge in adjacent)))
                    fingerprints.append(fingerprint_dict.get(fingerprint, 0))
                nodes = np.array(fingerprints)
                updated = defaultdict(list)
                for i, adjacent in edges.items():
                    for j, edge in adjacent:
                        updated[i].append((j, edge_dict.get((tuple(sorted((nodes[i], nodes[j]))), edge), 0)))
                edges = updated

        padded = "-" + sequence + "="
        words = np.array([word_dict.get(padded[i : i + 3], 0) for i in range(len(padded) - 2)])
        adjacency = Chem.GetAdjacencyMatrix(mol)
        upstream = _load_upstream_model(base / "Code" / "example")
        device = torch.device("cpu")
        network = upstream.KcatPrediction(device, len(fingerprint_dict), len(word_dict), 20, 3, 11, 3, 3).to(device)
        state = torch.load(base / "Results" / "output" / CHECKPOINT, map_location=device, weights_only=True)
        network.load_state_dict(state)
        network.eval()
        with torch.no_grad():
            log2_value = float(network.forward([
                torch.as_tensor(nodes, dtype=torch.long),
                torch.as_tensor(adjacency, dtype=torch.float32),
                torch.as_tensor(words, dtype=torch.long),
            ]).item())
        value = math.pow(2.0, log2_value)
        return PluginResult(
            request_id=request.request_id,
            plugin="DLKcat",
            plugin_version=PLUGIN_VERSION,
            capability=request.capability,
            status=RunStatus.READY,
            predictions=(Prediction("log2_kcat", log2_value, "log2(s^-1)", "log2"), Prediction("kcat", value, "s^-1")),
            transforms=transforms,
            applicability=ApplicabilityReport("not_available", None, None, "No versioned DLKcat training-domain reference is deployed"),
            uncertainty=UncertaintyReport("not_available", method="upstream model provides a point estimate only"),
            benchmark=BenchmarkReport(),
            messages=("Prediction is for prioritization and is not curated kinetic evidence.",),
        )
    except Exception as exc:
        return PluginResult(
            request_id=request.request_id,
            plugin="DLKcat",
            plugin_version=PLUGIN_VERSION,
            capability=request.capability,
            status=RunStatus.ERROR,
            transforms=transforms,
            applicability=ApplicabilityReport("not_available", None, None, "runtime failed before domain assessment"),
            uncertainty=UncertaintyReport("not_available"),
            messages=(f"{type(exc).__name__}: {exc}",),
        )
