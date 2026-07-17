from __future__ import annotations

import json
import sys
from pathlib import Path

import cobra
import pytest


RUNTIME = Path(__file__).resolve().parents[1]
ROOT = RUNTIME.parent
sys.path.insert(0, str(RUNTIME))

import test_10h2da_candidate_extension_fba as extension
import validate_10h2da_candidate_extension_fba as full_validation


def test_primary_and_reference_chemistry_are_identical() -> None:
    compatibility = json.loads((ROOT / "09_configs" / "target_workflow_10h2da.json").read_text(encoding="utf-8"))
    canonical_path = (ROOT / "09_configs" / compatibility["compatibility_reference"]).resolve()
    primary = json.loads(canonical_path.read_text(encoding="utf-8"))
    reference = json.loads((ROOT / "10_generic_target_workflow" / "examples" / "target_workflow_10h2da_reference.json").read_text(encoding="utf-8"))
    assert canonical_path == (ROOT / "10_generic_target_workflow" / "examples" / "target_workflow_10h2da_reference.json").resolve()
    primary_compounds = {row["compound_id"]: (row["formula"], row["charge"]) for row in primary["compounds"]}
    reference_compounds = {row["compound_id"]: (row["formula"], row["charge"]) for row in reference["compounds"]}
    assert primary_compounds == reference_compounds
    assert primary_compounds["10h2da"] == ("C10H17O3", -1)
    assert primary_compounds["10h2da_coa"] == ("C31H48N7O18P3S", -4)
    assert primary["candidate_reactions"] == reference["candidate_reactions"]


def test_all_candidate_reactions_are_mass_and_charge_balanced() -> None:
    deployment = extension.load_config()
    config = extension.load_target_config()
    model = cobra.io.load_yaml_model(deployment["models"]["yeast_metatwin"])
    extension.add_combined_route(model, config)
    for row in config["candidate_reactions"]:
        assert model.reactions.get_by_id(row["reaction_id"]).check_mass_balance() == {}


def test_biomass_is_inferred_from_single_model_objective() -> None:
    model = cobra.Model("objective-test")
    reaction = cobra.Reaction("biomass_from_objective")
    model.add_reactions([reaction])
    model.objective = reaction
    assert extension.resolve_biomass_reaction(model).id == "biomass_from_objective"


def test_biomass_override_is_validated() -> None:
    model = cobra.Model("override-test")
    reaction = cobra.Reaction("configured_biomass")
    model.add_reactions([reaction])
    assert extension.resolve_biomass_reaction(model, "configured_biomass") is reaction
    with pytest.raises(ValueError, match="absent"):
        extension.resolve_biomass_reaction(model, "missing")


def test_full_fba_validation_passes() -> None:
    result = full_validation.run_validation()
    assert result["passed"], result["failures"]
