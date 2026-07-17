# 10H2DA UniKP Kinetic Prioritization and Terminal Evidence Matrix

Generated: 2026-07-17T11:22:32
Python: `3.10.20 (main, Jun 23 2026, 15:19:56) [MSC v.1944 64 bit (AMD64)]`
Executable: `C:\ymt\unikp_sklearn12\Scripts\python.exe`

## Scope

This run scores S. cerevisiae endogenous terminal enzyme candidates against the four 10H2DA terminal candidate reactions. UniKP values are model predictions for prioritization only; they are not curated kinetic measurements and do not validate reaction chemistry.

## Outputs

- `06_evaluation/10h2da_unikp_terminal_predictions.csv`
- `06_evaluation/10h2da_terminal_enzyme_evidence_matrix.csv`
- `06_evaluation/10h2da_unikp_terminal_prediction_manifest.json`

## Substrates

| Key | Name | SMILES source |
|---|---|---|
| trans_2_decenoic_acid | trans-2-decenoic acid | PubChem CID 5282724 isomeric SMILES |
| trans_dec_2_enoyl_coa | trans-dec-2-enoyl-CoA | PubChem CID 24883423 isomeric SMILES |
| 10h2da_coa | 10-hydroxy-trans-2-decenoyl-CoA | derived from PubChem trans-dec-2-enoyl-CoA by omega hydroxyl substitution; no direct PubChem hit found |

## Top Candidates By Reaction

### CAND_T2DEC_THIOESTERASE_P

| ORF | Entry | Protein | log10 kcat | log10 Km | log10 kcat/Km | External tier | Local verdict |
|---|---|---|---:|---:|---:|---|---|
| YPL072W | Q02863 | Ubiquitin carboxyl-terminal hydrolase 16 (EC 3.4.19.12) (Deubiquitinating enzyme | 0.211 | -1.428 | 1.924 | C_near_substrate_enzyme_family | enzyme_class_support_only |
| YFL044C | P43558 | Ubiquitin thioesterase OTU1 (EC 3.4.19.12) (OTU domain-containing protein 1) | 0.402 | -1.383 | 1.632 | C_near_substrate_enzyme_family | enzyme_class_support_only |
| YER144C | P39944 | Ubiquitin carboxyl-terminal hydrolase 5 (EC 3.4.19.12) (Deubiquitinating enzyme  | 0.167 | -1.669 | 1.629 | C_near_substrate_enzyme_family | enzyme_class_support_only |
| YBR026C | P38071 | Enoyl-[acyl-carrier-protein] reductase, mitochondrial (EC 1.3.1.104) (2-enoyl th | -0.086 | -1.418 | 1.629 | C_near_substrate_enzyme_family | enzyme_class_support_only |
| YDR069C | P32571 | Ubiquitin carboxyl-terminal hydrolase 4 (EC 3.4.19.12) (Deubiquitinating enzyme  | 0.275 | -1.573 | 1.587 | C_near_substrate_enzyme_family | enzyme_class_support_only |

### CAND_T2DEC_OMEGA_HYDROXYLASE_P

| ORF | Entry | Protein | log10 kcat | log10 Km | log10 kcat/Km | External tier | Local verdict |
|---|---|---|---:|---:|---:|---|---|
| YJR149W | P47177 | Putative nitronate monooxygenase (EC 1.13.12.16) (Nitroalkane oxidase) | 0.429 | -0.980 | 1.224 | B_exact_compound_context_no_enzyme_specificity | enzyme_class_support_only |
| YNR028W | P53728 | Peptidyl-prolyl cis-trans isomerase CYP8 (PPIase CYP8) (EC 5.2.1.8) (Rotamase CY | 0.310 | -1.110 | 1.174 | B_exact_compound_context_no_enzyme_specificity | enzyme_class_support_only |
| YGR255C | P53318 | Ubiquinone biosynthesis monooxygenase COQ6, mitochondrial (EC 1.14.13.-) (Ubiqui | 0.666 | -1.141 | 1.171 | B_exact_compound_context_no_enzyme_specificity | enzyme_class_support_only |
| YCR069W | P25334 | Peptidyl-prolyl cis-trans isomerase CPR4 (PPIase CPR4) (EC 5.2.1.8) (Rotamase) | 0.328 | -0.852 | 1.156 | B_exact_compound_context_no_enzyme_specificity | enzyme_class_support_only |
| YDR304C | P35176 | Peptidyl-prolyl cis-trans isomerase D (PPIase D) (EC 5.2.1.8) (Cyclophilin D) (C | 0.901 | -0.944 | 1.120 | B_exact_compound_context_no_enzyme_specificity | enzyme_class_support_only |

### CAND_T2DEC_COA_OMEGA_HYDROXYLASE_P

| ORF | Entry | Protein | log10 kcat | log10 Km | log10 kcat/Km | External tier | Local verdict |
|---|---|---|---:|---:|---:|---|---|
| YHR176W | P38866 | Thiol-specific monooxygenase (EC 1.14.13.-) (Flavin-dependent monooxygenase) | 0.682 | -1.530 | 1.750 | D_enzyme_family_only | enzyme_class_support_only |
| YJR032W | P47103 | Peptidyl-prolyl cis-trans isomerase CYP7 (PPIase CYP7) (EC 5.2.1.8) (Rotamase CY | 0.542 | -1.539 | 1.735 | D_enzyme_family_only | enzyme_class_support_only |
| YNR028W | P53728 | Peptidyl-prolyl cis-trans isomerase CYP8 (PPIase CYP8) (EC 5.2.1.8) (Rotamase CY | 0.204 | -1.371 | 1.734 | D_enzyme_family_only | enzyme_class_support_only |
| YMR272C | Q03529 | Ceramide very long chain fatty acid hydroxylase SCS7 (Ceramide VLCFA hydroxylase | 0.379 | -1.384 | 1.721 | D_enzyme_family_only | enzyme_class_support_only |
| YPL064C | Q02770 | Peptidyl-prolyl isomerase CWC27 (PPIase CWC27) (EC 5.2.1.8) (Complexed with CEF1 | 0.919 | -1.333 | 1.716 | D_enzyme_family_only | enzyme_class_support_only |

### CAND_10H2DA_COA_THIOESTERASE_P

| ORF | Entry | Protein | log10 kcat | log10 Km | log10 kcat/Km | External tier | Local verdict |
|---|---|---|---:|---:|---:|---|---|
| YPL072W | Q02863 | Ubiquitin carboxyl-terminal hydrolase 16 (EC 3.4.19.12) (Deubiquitinating enzyme | 0.190 | -1.395 | 2.072 | D_enzyme_family_only | enzyme_class_support_only |
| YBR026C | P38071 | Enoyl-[acyl-carrier-protein] reductase, mitochondrial (EC 1.3.1.104) (2-enoyl th | -0.130 | -1.434 | 1.742 | D_enzyme_family_only | enzyme_class_support_only |
| YFL044C | P43558 | Ubiquitin thioesterase OTU1 (EC 3.4.19.12) (OTU domain-containing protein 1) | 0.405 | -1.371 | 1.653 | D_enzyme_family_only | enzyme_class_support_only |
| YER144C | P39944 | Ubiquitin carboxyl-terminal hydrolase 5 (EC 3.4.19.12) (Deubiquitinating enzyme  | 0.101 | -1.555 | 1.638 | D_enzyme_family_only | enzyme_class_support_only |
| YKR098C | P36026 | Ubiquitin carboxyl-terminal hydrolase 11 (EC 3.4.19.12) (Deubiquitinating enzyme | 0.329 | -1.565 | 1.595 | D_enzyme_family_only | enzyme_class_support_only |

## Interpretation

The matrix should be read as a triage table. PU/FBA/UniKP/external evidence are separate evidence types. High UniKP scores increase follow-up priority for an enzyme-substrate pair, but exact terminal validation still requires biochemical or curated reaction evidence.
