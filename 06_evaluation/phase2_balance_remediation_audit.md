# Phase 2 Balance Remediation Audit

Generated: 2026-07-16T21:28:46

## Reaction-Level Categories

| Category | Reactions |
|---|---:|
| exclude_from_structure_sensitive_training_or_apply_curated_carrier_rules | 1700 |
| training_ready_mass_charge_balanced | 4728 |
| requires_manual_balance_review | 1001 |
| requires_external_structure_mapping | 87 |

## Metabolite Issue Categories

| Category | Metabolites | Occurrences |
|---|---:|---:|
| generic_r_group_or_polymer_formula | 173 | 317 |
| macromolecule_or_redox_carrier_formula | 5 | 8 |
| missing_formula_no_local_mapping | 124 | 152 |
| underground_template_metabolite_missing_formula | 393 | 1903 |

## Interpretation

Most missing formulas come from `sn_*` underground/template metabolites. These should not be guessed into mass-balanced training labels without source structures. Many unparsable formulas contain generic R-groups or macromolecular redox carriers, which should be excluded from structure-sensitive training features or handled with curated carrier rules.

## Outputs

- `06_evaluation/phase2_balance_remediation_reaction_flags.csv`
- `06_evaluation/phase2_balance_remediation_metabolite_issues.csv`
- `06_evaluation/phase2_balance_remediation_audit.json`
