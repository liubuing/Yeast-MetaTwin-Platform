# Target Workflow: 10-Hydroxy-trans-2-decenoic acid reference case

Target ID: `10h2da_reference`

## Generated Inputs

- `inputs/compounds.csv`
- `inputs/candidate_reactions.csv`
- `inputs/routes.csv`
- `inputs/prediction_pairs.csv`
- `inputs/enzyme_search_terms.json`

## Next Implementation Steps

1. Confirm compound identity, SMILES, formula, charge, and model metabolite IDs.
2. Implement target-specific candidate reaction FBA extension using `inputs/candidate_reactions.csv`.
3. Run balance checks before using reactions for structure-sensitive prediction.
4. Build enzyme candidate tables from endogenous FASTA and external sources.
5. Run UniKP only for rows with both valid substrate SMILES and protein sequence.
6. Keep FBA, ML, UniKP, external evidence, and engineering feasibility as separate columns.
