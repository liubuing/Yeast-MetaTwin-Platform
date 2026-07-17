# Phase 2 Mapping Enrichment

Generated: 2026-07-16T20:56:57

## Compound Enrichment

| Metric | Value |
|---|---:|
| Rows | 3301 |
| Mapped by model metabolite ID | 2806 |
| SMILES non-empty | 2124 |
| InChIKey non-empty | 2124 |
| KEGG ID non-empty | 1725 |
| ChEBI ID non-empty | 2399 |
| MetaNetX ID non-empty | 2250 |

## Enzyme Evidence Enrichment

| Metric | Value |
|---|---:|
| Rows | 160739 |
| Unique ORFs | 2057 |
| Mapped rows by ORF | 160723 |
| Mapped unique ORFs | 2047 |
| EC non-empty rows | 103187 |

## Outputs

- `02_id_mapping\model_compound_seed_enriched.csv`
- `02_id_mapping\model_enzyme_evidence_seed_enriched.csv`

## Notes

Compound mapping currently uses model metabolite IDs from `yeast-GEM-final.csv`; this covers model metabolites with existing curated mappings. Enzyme mapping currently uses ORF matches from the local yeast UniProt TSV. The next step is cross-database structure mapping for unmapped compounds and curated reaction cross-references.
