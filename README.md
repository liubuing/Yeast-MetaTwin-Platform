# Yeast-MetaTwin Platform

Cross-species metabolic pathway prediction platform built on the [Yeast-MetaTwin](https://github.com/LiLabTsinghua/Yeast-MetaTwin) genome-scale metabolic model. Combines ESM-2 protein representation learning, multi-task enzyme annotation, condition-specific constraint-based modeling, and active learning prioritization into a unified, reproducible workflow.

## Architecture

```
Target compound
  → Species GEM loading + FBA feasibility check
  → ESM-2 sequence encoding (species-agnostic, 1280-dim)
  → Multi-task prediction (EC classification + kcat regression + FBA feasibility)
  → Condition-specific FBA (GIMME/iMAT transcriptomics constraints)
  → Active learning acquisition (Deep Ensemble + EI/BALD)
  → Prioritized candidate report
```

## Supported Species

| Species | GEM | Reactions | FBA (h⁻¹) | Source |
|---------|-----|-----------|------------|--------|
| *S. cerevisiae* | Yeast-MetaTwin | 7,512 | 0.0895 | LiLab Tsinghua |
| *E. coli* K-12 | iML1515 | 2,712 | 0.877 | BiGG Models |
| *C. glutamicum* | iCW773 | 1,207 | 0.434 | BioModels |

GEM files are not included in this repository (see `09_configs/species/*.json` for download sources).

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Validate species configuration
python 08_runtime/species_profile.py --species yeast

# Run full workflow (dry-run)
python 08_runtime/cross_species_workflow.py --species yeast --dry-run

# Run with expression constraints
python 08_runtime/cross_species_workflow.py \
  --species yeast \
  --expression 01_databases/geo_yeast_expression_real.csv \
  --method gimme \
  --condition glucose_aerobic

# Encode enzyme sequences with ESM-2
python 08_runtime/esm2_encode.py --fasta 05_training/enzyme_subset.fasta --device cpu

# Train multi-task model
python 08_runtime/multitask_model.py train \
  --embeddings 03_models/esm2_embeddings/embeddings_matrix.npy \
  --index 03_models/esm2_embeddings/embeddings_index.csv \
  --labels-dir 05_training --epochs 50

# Active learning candidate selection
python 08_runtime/acquisition.py select \
  --embeddings 03_models/esm2_embeddings/embeddings_matrix.npy \
  --method ei --top-k 20
```

## Key Modules

| Module | Purpose |
|--------|---------|
| `08_runtime/species_profile.py` | Multi-species config loader with JSON Schema validation |
| `08_runtime/load_gem_multispecies.py` | Unified GEM loading, FBA verification, demand reaction injection |
| `08_runtime/esm2_encode.py` | ESM-2 650M protein sequence encoder with per-sequence caching |
| `08_runtime/multitask_model.py` | Joint EC/kcat/FBA prediction with uncertainty weighting |
| `08_runtime/omics_constrain.py` | GIMME + iMAT transcriptomics constraints, pseudo-GPR inference |
| `08_runtime/acquisition.py` | Deep Ensemble uncertainty + EI/BALD active learning |
| `08_runtime/cross_species_workflow.py` | Unified CLI orchestrating the full pipeline |
| `08_runtime/id_mapping_bridge.py` | BiGG ↔ MetaNetX ↔ KEGG cross-namespace resolution |

## Case Study: 10H2DA

10-hydroxy-trans-2-decenoic acid (royal jelly fatty acid) condition-specific FBA across 7 conditions:

| Rank | Condition | Weighted Score |
|------|-----------|---------------|
| 1 | stationary_phase | 0.1024 |
| 2 | galactose | 0.1002 |
| 3 | glucose_anaerobic | 0.0999 |
| 7 | ethanol | 0.0974 |

All conditions FBA-feasible; differentiation driven by pathway enzyme expression (YLR284C isomerase varies 36-fold across conditions).

## Testing

```bash
python -m pytest tests/test_cross_species_platform.py -v
```

26 integration tests covering species profiles, ESM-2 encoding, multi-task model, omics constraints, acquisition functions, ID mapping, and workflow orchestration.

## Folder Layout

| Folder | Purpose |
|--------|---------|
| `00_docs` | Design documents, execution reports, environment policies |
| `01_databases` | External databases, GEO expression matrices |
| `02_id_mapping` | Cross-database ID mapping, structure normalization |
| `03_models` | GEMs (excluded), trained models, ESM-2 embeddings, ensemble |
| `04_prediction_plugins` | CLEAN, DLKcat, UniKP, DeepECtransformer adapters |
| `05_training` | Training data, split definitions, enzyme FASTA, labels |
| `06_evaluation` | Leakage checks, validation matrices, evidence scores |
| `07_reports` | Generated reports (Markdown, Word, PNG) |
| `08_runtime` | All pipeline scripts |
| `09_configs` | Deployment config, species profiles, workflow schemas |
| `10_generic_target_workflow` | Target-agnostic CLI workflow engine |
| `tests` | Pytest integration tests |

## Requirements

- Python ≥ 3.11
- COBRApy 0.31+, PyTorch 2.x, fair-esm 2.0
- GLPK solver (via swiglpk)
- See `constraints.txt` for pinned versions

## Scientific Limitations

This is a computational prediction platform. All outputs are prioritization evidence, not biochemical validation. No 10H2DA terminal reaction currently reaches evidence tier A (curated enzyme). Pseudo-GPR inference for underground reactions uses co-expression correlation and is marked as `inferred`, not curated. Predictions require experimental confirmation.

## Origin

Built on Yeast-MetaTwin (LiLab, Tsinghua University; bioRxiv 2024.09.02.610684). Platform integration and cross-species extension by the project team.

## License

Research use only.
