# Phase 2 Underground rxn* Provenance Mapping

Generated: 2026-07-16T20:58:17
RXNdb source: `C:\biological\Metabolic model prediction\Yeast-MetaTwin\Data_retrosynthesis\not_lipid\top50_0.3_add_no_ec_re\RXNdb_all_top50_0.3.json`

## Coverage

| Metric | Value |
|---|---:|
| Underground rxn* model reactions | 3381 |
| RXNdb direct matches | 3330 (98.49%) |
| Missing direct matches | 51 |
| RXNdb total records | 123661 |
| With template ID | 3330 |
| With rxn_smiles_basic | 3330 |
| With rxn_smiles_final | 3330 |
| With EC number | 2560 (75.72%) |

## Output

- `02_id_mapping/model_underground_rxn_provenance.csv`

## Interpretation

A direct match means the model `rxn*` ID exists as a top-level key in the selected RXNdb file. This provides retrosynthesis provenance fields such as template ID, EC number, reaction SMILES, and similarity scores. These are still prediction/provenance records, not curated biochemical validation.
