# Phase 2 Reaction Cross-Reference Build

Generated: 2026-07-16T20:58:14

## Coverage

| Metric | Value |
|---|---:|
| Total model reactions | 7512 |
| Underground rxn* reactions | 3381 |
| MetaNetX cross-reference non-empty | 1675 |
| MetaNetX property match | 876 |
| KEGG reaction non-empty | 909 |
| KEGG pathway non-empty | 1891 |
| BiGG reaction non-empty | 1407 |
| SBO non-empty | 4131 |
| Underground rxn* without external cross-reference | 3381 |

## Output

- `02_id_mapping/model_reaction_crossrefs.csv`

## Notes

This cross-reference table uses existing model annotations first. Most underground `rxn*` reactions do not carry direct annotation and require a later RXNdb/retrosynthesis mapping pass using reaction signatures or provenance records.
