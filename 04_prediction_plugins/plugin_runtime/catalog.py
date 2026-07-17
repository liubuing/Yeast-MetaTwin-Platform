from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AssetSpec:
    relative_path: str
    kind: str = "file"
    min_size_bytes: int = 1
    required_children: tuple[str, ...] = ()
    expected_sha256: str | None = None


@dataclass(frozen=True)
class PackageSpec:
    distribution: str
    minimum: tuple[int, ...] | None = None
    maximum_exclusive: tuple[int, ...] | None = None


@dataclass(frozen=True)
class PluginSpec:
    name: str
    plugin_version: str
    capabilities: tuple[str, ...]
    required_assets: tuple[AssetSpec, ...]
    packages: tuple[PackageSpec, ...] = ()
    source_url: str = ""


UNIKP_ASSETS = (
    AssetSpec("UniKP/code/build_vocab.py", min_size_bytes=100),
    AssetSpec("UniKP/code/pretrain_trfm.py", min_size_bytes=100),
    AssetSpec("UniKP/models/vocab.pkl", min_size_bytes=100),
    AssetSpec("UniKP/models/trfm_12_23000.pkl", min_size_bytes=1_000_000),
    AssetSpec("UniKP/models/UniKP for kcat.pkl", min_size_bytes=100_000),
    AssetSpec("UniKP/models/UniKP for Km.pkl", min_size_bytes=100_000),
    AssetSpec("UniKP/models/UniKP for kcat_Km.pkl", min_size_bytes=100_000),
    AssetSpec("UniKP/models/prot_t5_xl_uniref50/config.json", min_size_bytes=100),
    AssetSpec("UniKP/models/prot_t5_xl_uniref50/spiece.model", min_size_bytes=100_000),
    AssetSpec("UniKP/models/prot_t5_xl_uniref50/pytorch_model.bin", min_size_bytes=1_000_000_000),
)


PLUGIN_SPECS = (
    PluginSpec(
        name="CLEAN",
        plugin_version="upstream-unpinned",
        capabilities=("ec_prediction",),
        required_assets=(
            AssetSpec("CLEAN/app/CLEAN_infer_fasta.py", min_size_bytes=100),
            AssetSpec("CLEAN/data/pretrained/split100.pth", min_size_bytes=100_000),
            AssetSpec("CLEAN/data/pretrained/100.pt", min_size_bytes=100_000),
            AssetSpec("CLEAN/data/distance_map/split100_esm.pkl", min_size_bytes=100_000),
        ),
        packages=(PackageSpec("torch", (1, 11)), PackageSpec("fair-esm", (1, 0))),
        source_url="https://github.com/tttianhao/CLEAN",
    ),
    PluginSpec(
        name="DLKcat",
        plugin_version="upstream-7c15d0d4a7ac",
        capabilities=("kcat_prediction",),
        required_assets=(
            AssetSpec("DLKcat/DeeplearningApproach/Code/example/prediction_for_input.py", min_size_bytes=100, expected_sha256="5268b767bbcc5d206193e5008bde0eab5ab27b450ce7e1b0182097b16d21a496"),
            AssetSpec("DLKcat/DeeplearningApproach/Code/example/model.py", min_size_bytes=100, expected_sha256="63dd6c56c07fc691b717befe800bb893e0d8aed17c67b58fffd30983f35fd508"),
            AssetSpec("DLKcat/DeeplearningApproach/Data/input.zip", min_size_bytes=1_000_000, expected_sha256="5b364a0705acd232e49db8eea15658fa8981b3c28bd6207b4b1e81406d40158e"),
            AssetSpec("DLKcat/DeeplearningApproach/Data/input/fingerprint_dict.pickle", min_size_bytes=100_000, expected_sha256="4ecaa61f5822beda116c530aae53445cf9b16630e7f0da502f8f0f3fdeeac258"),
            AssetSpec("DLKcat/DeeplearningApproach/Data/input/sequence_dict.pickle", min_size_bytes=100_000, expected_sha256="2813556dff5a2e11164aec62306a62e790431417866ab9401aa0260593247030"),
            AssetSpec("DLKcat/DeeplearningApproach/Results/output/saved_model", min_size_bytes=1_000_000, expected_sha256="df5f6ab139b7a73557c6b1ba84e06dc28a120315409328631fc0887d364f786b"),
            AssetSpec("DLKcat/DeeplearningApproach/Code/example/input.tsv", min_size_bytes=10, expected_sha256="064529b4a9c429e05333fa7c6a0c4a41f102353d85a4303a96f79b7c80f6ebb1"),
            AssetSpec("DLKcat/DeeplearningApproach/Code/example/output.tsv", min_size_bytes=10, expected_sha256="4ce769edbdcf58592738aa6b1cabed59ab6e47c2d7a5bc1a007643e715a58338"),
        ),
        packages=(PackageSpec("torch"), PackageSpec("rdkit")),
        source_url="https://github.com/SysBioChalmers/DLKcat",
    ),
    PluginSpec(
        name="UniKP",
        plugin_version="2023-paper-model-local-snapshot",
        capabilities=("kcat_prediction", "km_prediction", "kcat_km_prediction"),
        required_assets=UNIKP_ASSETS,
        packages=(
            PackageSpec("numpy", (1, 23), (2, 0)),
            PackageSpec("scikit-learn", (1, 2), (1, 3)),
            PackageSpec("torch", (2, 0), (3, 0)),
            PackageSpec("transformers", (4, 0), (6, 0)),
            PackageSpec("sentencepiece", (0, 1)),
        ),
        source_url="https://github.com/Luo-SynBioLab/UniKP",
    ),
)


FIXED_SMOKE_INPUTS = {
    "CLEAN": {"request_id": "smoke-clean-001", "capability": "ec_prediction", "sequence": "MKTAYIAKQRQISFVKSHFSRQ"},
    "DLKcat": {
        "request_id": "smoke-dlkcat-001",
        "capability": "kcat_prediction",
        "sequence": "MKTAYIAKQRQISFVKSHFSRQ",
        "substrate_smiles": "CC(=O)O",
    },
    "UniKP": {
        "request_id": "smoke-unikp-001",
        "capability": "kcat_prediction",
        "sequence": "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQANL",
        "substrate_smiles": "CC(=O)O",
    },
}


UNMANAGED_PLUGINS = (
    ("DeepECtransformer", "ec_prediction", "adapter_not_implemented"),
    ("ESP", "enzyme_substrate_prediction", "adapter_not_implemented"),
    ("ProSmith", "enzyme_substrate_prediction", "adapter_not_implemented"),
    ("EnzRank", "enzyme_substrate_prediction", "adapter_not_implemented"),
    ("CatPred", "enzyme_substrate_kinetics", "adapter_not_implemented"),
    ("CYP/P450 scorer", "omega_hydroxylase_prediction", "adapter_not_implemented"),
)
