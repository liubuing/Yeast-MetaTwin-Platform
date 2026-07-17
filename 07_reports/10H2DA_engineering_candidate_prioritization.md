# 10H2DA Engineering Candidate Prioritization

Generated: 2026-07-17T11:38:37
Python: `3.10.20 (main, Jun 23 2026, 15:19:56) [MSC v.1944 64 bit (AMD64)]`
Executable: `C:\ymt\unikp_sklearn12\Scripts\python.exe`

## Scope

This report adds enzyme-family sanity filtering and external omega-hydroxylase candidates to the UniKP terminal evidence matrix. External enzyme candidates are engineering options, not native S. cerevisiae model evidence.

## Outputs

- `06_evaluation/10h2da_external_omega_hydroxylase_unikp_predictions.csv`
- `06_evaluation/10h2da_engineering_candidate_matrix.csv`
- `06_evaluation/10h2da_pathway_design_candidates.csv`

## Top Engineering Candidates By Reaction

### CAND_T2DEC_THIOESTERASE_P

| Entry | Origin | Organism | Family class | log10 kcat/Km | Priority | Protein |
|---|---|---|---|---:|---:|---|
| P41903 | endogenous_s_cerevisiae | Saccharomyces cerevisiae | preferred_acyl_coa_thioesterase | 1.487 | 12.885 | Peroxisomal acyl-coenzyme A thioester hydrolase 1 (EC 3.1.2.2) (Peroxi |
| P38256 | endogenous_s_cerevisiae | Saccharomyces cerevisiae | plausible_thioesterase | 1.544 | 10.941 | Probable thioesterase YBR096W (EC 2.3.1.-) |
| P53208 | endogenous_s_cerevisiae | Saccharomyces cerevisiae | plausible_thioesterase | 1.494 | 10.891 | Ethanol acetyltransferase 1 (EC 2.3.1.268) (Acetyl-CoA hydrolase) (EC  |
| Q12354 | endogenous_s_cerevisiae | Saccharomyces cerevisiae | plausible_thioesterase | 1.299 | 10.696 | Acyl-protein thioesterase 1 (EC 3.1.2.-) (Palmitoyl-protein hydrolase) |
| P07149 | endogenous_s_cerevisiae | Saccharomyces cerevisiae | generic_thioesterase | 1.326 | 8.723 | Fatty acid synthase subunit beta (EC 2.3.1.86) [Includes: 3-hydroxyacy |
| Q02863 | endogenous_s_cerevisiae | Saccharomyces cerevisiae | weak_ubiquitin_thioesterase | 1.924 | 5.321 | Ubiquitin carboxyl-terminal hydrolase 16 (EC 3.4.19.12) (Deubiquitinat |

### CAND_T2DEC_OMEGA_HYDROXYLASE_P

| Entry | Origin | Organism | Family class | log10 kcat/Km | Priority | Protein |
|---|---|---|---|---:|---:|---|
| P14581 | external_uniprot | Oryctolagus cuniculus | preferred_omega_hydroxylase | 0.900 | 13.289 | Cytochrome P450 4A7; CYPIVA7; Cytochrome P450-KA-2; Lauric acid omega- |
| P10611 | external_uniprot | Oryctolagus cuniculus | preferred_omega_hydroxylase | 0.883 | 13.272 | Cytochrome P450 4A4; CYPIVA4; Cytochrome P450-P-2; Prostaglandin omega |
| Q6NT55 | external_uniprot_curated_panel | Homo sapiens | preferred_omega_hydroxylase | 0.879 | 13.269 | Ultra-long-chain fatty acid omega-hydroxylase; Cytochrome P450 4F22 |
| P14580 | external_uniprot | Oryctolagus cuniculus | preferred_omega_hydroxylase | 0.859 | 13.248 | Cytochrome P450 4A6; CYPIVA6; Cytochrome P450-KA-1; Lauric acid omega- |
| Q5TCH4 | external_uniprot | Homo sapiens | preferred_omega_hydroxylase | 0.845 | 13.234 | Cytochrome P450 4A22; CYPIVA22; Fatty acid omega-hydroxylase; Lauric a |
| B8QHP1 | external_uniprot_curated_panel | Starmerella bombicola | preferred_omega_hydroxylase | 0.747 | 13.136 | Cytochrome P450 52-M1; fatty acid omega-hydroxylase |

### CAND_T2DEC_COA_OMEGA_HYDROXYLASE_P

| Entry | Origin | Organism | Family class | log10 kcat/Km | Priority | Protein |
|---|---|---|---|---:|---:|---|
| P14581 | external_uniprot | Oryctolagus cuniculus | preferred_omega_hydroxylase | 1.750 | 14.087 | Cytochrome P450 4A7; CYPIVA7; Cytochrome P450-KA-2; Lauric acid omega- |
| Q6NT55 | external_uniprot_curated_panel | Homo sapiens | preferred_omega_hydroxylase | 1.648 | 13.985 | Ultra-long-chain fatty acid omega-hydroxylase; Cytochrome P450 4F22 |
| P10611 | external_uniprot | Oryctolagus cuniculus | preferred_omega_hydroxylase | 1.574 | 13.911 | Cytochrome P450 4A4; CYPIVA4; Cytochrome P450-P-2; Prostaglandin omega |
| Q5TCH4 | external_uniprot | Homo sapiens | preferred_omega_hydroxylase | 1.517 | 13.855 | Cytochrome P450 4A22; CYPIVA22; Fatty acid omega-hydroxylase; Lauric a |
| P14580 | external_uniprot | Oryctolagus cuniculus | preferred_omega_hydroxylase | 1.490 | 13.828 | Cytochrome P450 4A6; CYPIVA6; Cytochrome P450-KA-1; Lauric acid omega- |
| B8QHP1 | external_uniprot_curated_panel | Starmerella bombicola | preferred_omega_hydroxylase | 1.110 | 13.447 | Cytochrome P450 52-M1; fatty acid omega-hydroxylase |

### CAND_10H2DA_COA_THIOESTERASE_P

| Entry | Origin | Organism | Family class | log10 kcat/Km | Priority | Protein |
|---|---|---|---|---:|---:|---|
| P41903 | endogenous_s_cerevisiae | Saccharomyces cerevisiae | preferred_acyl_coa_thioesterase | 1.561 | 12.806 | Peroxisomal acyl-coenzyme A thioester hydrolase 1 (EC 3.1.2.2) (Peroxi |
| P53208 | endogenous_s_cerevisiae | Saccharomyces cerevisiae | plausible_thioesterase | 1.484 | 10.728 | Ethanol acetyltransferase 1 (EC 2.3.1.268) (Acetyl-CoA hydrolase) (EC  |
| P38256 | endogenous_s_cerevisiae | Saccharomyces cerevisiae | plausible_thioesterase | 1.463 | 10.708 | Probable thioesterase YBR096W (EC 2.3.1.-) |
| Q12354 | endogenous_s_cerevisiae | Saccharomyces cerevisiae | plausible_thioesterase | 1.230 | 10.474 | Acyl-protein thioesterase 1 (EC 3.1.2.-) (Palmitoyl-protein hydrolase) |
| P07149 | endogenous_s_cerevisiae | Saccharomyces cerevisiae | generic_thioesterase | 1.280 | 8.525 | Fatty acid synthase subunit beta (EC 2.3.1.86) [Includes: 3-hydroxyacy |
| Q02863 | endogenous_s_cerevisiae | Saccharomyces cerevisiae | weak_ubiquitin_thioesterase | 2.072 | 5.316 | Ubiquitin carboxyl-terminal hydrolase 16 (EC 3.4.19.12) (Deubiquitinat |

## Top Pathway Designs

| Route | Step 1 | Step 2 | Mean priority | Risk note |
|---|---|---|---:|---|
| coa_bound_route | P14581 (preferred_omega_hydroxylase) | P41903 (preferred_acyl_coa_thioesterase) | 13.447 | external hydroxylase requires heterologous expression and redox partner handling |
| coa_bound_route | Q6NT55 (preferred_omega_hydroxylase) | P41903 (preferred_acyl_coa_thioesterase) | 13.396 | external hydroxylase requires heterologous expression and redox partner handling |
| coa_bound_route | P10611 (preferred_omega_hydroxylase) | P41903 (preferred_acyl_coa_thioesterase) | 13.359 | external hydroxylase requires heterologous expression and redox partner handling |
| coa_bound_route | Q5TCH4 (preferred_omega_hydroxylase) | P41903 (preferred_acyl_coa_thioesterase) | 13.330 | external hydroxylase requires heterologous expression and redox partner handling |
| coa_bound_route | P14580 (preferred_omega_hydroxylase) | P41903 (preferred_acyl_coa_thioesterase) | 13.317 | external hydroxylase requires heterologous expression and redox partner handling |
| free_acid_route | P41903 (preferred_acyl_coa_thioesterase) | P14581 (preferred_omega_hydroxylase) | 13.087 | external hydroxylase requires heterologous expression and redox partner handling |
| free_acid_route | P41903 (preferred_acyl_coa_thioesterase) | P10611 (preferred_omega_hydroxylase) | 13.078 | external hydroxylase requires heterologous expression and redox partner handling |
| free_acid_route | P41903 (preferred_acyl_coa_thioesterase) | Q6NT55 (preferred_omega_hydroxylase) | 13.077 | external hydroxylase requires heterologous expression and redox partner handling |
| free_acid_route | P41903 (preferred_acyl_coa_thioesterase) | P14580 (preferred_omega_hydroxylase) | 13.066 | external hydroxylase requires heterologous expression and redox partner handling |
| free_acid_route | P41903 (preferred_acyl_coa_thioesterase) | Q5TCH4 (preferred_omega_hydroxylase) | 13.060 | external hydroxylase requires heterologous expression and redox partner handling |

## Interpretation

The highest engineering-priority scores favor true fatty-acid omega-hydroxylase/P450 candidates over weak endogenous keyword hits. Endogenous thioesterases remain useful route components, but exact terminal chemistry still needs biochemical validation.
