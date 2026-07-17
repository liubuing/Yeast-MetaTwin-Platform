# Phase 2 Database Asset Scan

Generated: 2026-07-16T20:55:32
Source project: `C:\biological\Metabolic model prediction\Yeast-MetaTwin`

## Summary By Database Guess

| Database | Files | Total size MB |
|---|---:|---:|
| ChEBI | 3 | 252.71 |
| KEGG | 1 | 2.48 |
| MetaNetX | 9 | 1274.98 |
| Model | 3 | 1.29 |
| Other | 14 | 6.72 |
| Retrosynthesis | 1020895 | 8483.55 |
| UniProt | 2 | 264.79 |
| YMDB | 6 | 10.55 |

## Outputs

- `01_databases/phase2_database_asset_inventory.csv`
- `06_evaluation/phase2_database_asset_scan.json`

## Notes

This scan is intentionally lightweight. Large retrosynthesis JSON files are recorded but not deeply parsed. Phase 2 normalization should next build compound and reaction mapping tables using the schemas in `02_id_mapping`.
