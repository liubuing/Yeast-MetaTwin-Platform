from __future__ import annotations

"""Integration tests for the cross-species metabolic prediction platform.

Tests cover:
- Species profile loading and validation
- GEM loading (mock if actual files unavailable)
- ESM-2 encoder interface
- Multi-task model architecture
- Omics constraint algorithms
- Active learning acquisition functions
- Cross-species workflow orchestration
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# Ensure runtime scripts are importable
RUNTIME_DIR = Path(__file__).resolve().parents[1] / "08_runtime"
sys.path.insert(0, str(RUNTIME_DIR))


# ---------------------------------------------------------------------------
# Species Profile Tests
# ---------------------------------------------------------------------------

class TestSpeciesProfile:
    def test_list_species(self):
        from species_profile import list_species
        species = list_species()
        assert "yeast" in species
        assert "ecoli" in species
        assert "cglutamicum" in species

    def test_load_yeast_profile(self):
        from species_profile import load_species_profile
        profile = load_species_profile("yeast")
        assert profile["species_id"] == "yeast"
        assert profile["taxonomy_id"] == 559292
        assert profile["biomass_reaction"] == "r_2111"
        assert profile["gem"]["format"] == "yml"
        assert "path_resolved" in profile["gem"]

    def test_load_ecoli_profile(self):
        from species_profile import load_species_profile
        profile = load_species_profile("ecoli")
        assert profile["species_id"] == "ecoli"
        assert profile["taxonomy_id"] == 511145
        assert profile["codon_table"] == 11

    def test_invalid_species_raises(self):
        from species_profile import SpeciesProfileError, load_species_profile
        with pytest.raises(SpeciesProfileError, match="not found"):
            load_species_profile("nonexistent_species")

    def test_cofactor_set(self):
        from species_profile import get_cofactor_set, load_species_profile
        profile = load_species_profile("yeast")
        cofactors = get_cofactor_set(profile)
        assert "MNXM3" in cofactors
        assert len(cofactors) > 10


# ---------------------------------------------------------------------------
# ESM-2 Encoder Tests
# ---------------------------------------------------------------------------

class TestESM2Encoder:
    def test_parse_fasta(self, tmp_path):
        from esm2_encode import _parse_fasta
        fasta = tmp_path / "test.fasta"
        fasta.write_text(">seq1 description\nMKVLWA\n>seq2\nACDEFG\n")
        seqs = _parse_fasta(fasta)
        assert len(seqs) == 2
        assert seqs[0] == ("seq1", "MKVLWA")
        assert seqs[1] == ("seq2", "ACDEFG")

    def test_parse_fasta_multiline(self, tmp_path):
        from esm2_encode import _parse_fasta
        fasta = tmp_path / "multi.fasta"
        fasta.write_text(">seq1\nMKVL\nWALL\n>seq2\nACDE\n")
        seqs = _parse_fasta(fasta)
        assert seqs[0] == ("seq1", "MKVLWALL")

    def test_write_index_csv(self, tmp_path):
        from esm2_encode import _write_index_csv
        index = [
            {"seq_id": "a", "seq_hash": "abc", "seq_length": "10", "cache_file": "a.npy"},
            {"seq_id": "b", "seq_hash": "def", "seq_length": "20", "cache_file": "b.npy"},
        ]
        out = tmp_path / "index.csv"
        _write_index_csv(out, index)
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "seq_id" in content
        assert "a" in content

    def test_get_cached_embeddings_missing(self, tmp_path):
        from esm2_encode import get_cached_embeddings
        result = get_cached_embeddings(tmp_path)
        assert result is None

    def test_get_cached_embeddings_exists(self, tmp_path):
        from esm2_encode import get_cached_embeddings
        matrix = np.random.randn(5, 1280).astype(np.float32)
        np.save(tmp_path / "embeddings_matrix.npy", matrix)
        (tmp_path / "embeddings_index.csv").write_text(
            "seq_id,seq_hash,seq_length,cache_file\n"
            "s1,aaa,100,s1.npy\ns2,bbb,200,s2.npy\n"
            "s3,ccc,150,s3.npy\ns4,ddd,180,s4.npy\ns5,eee,120,s5.npy\n",
            encoding="utf-8",
        )
        result = get_cached_embeddings(tmp_path)
        assert result is not None
        loaded_matrix, index = result
        assert loaded_matrix.shape == (5, 1280)
        assert len(index) == 5


# ---------------------------------------------------------------------------
# Multi-task Model Tests
# ---------------------------------------------------------------------------

class TestMultiTaskModel:
    def test_build_model_architecture(self):
        from multitask_model import build_multitask_model
        model = build_multitask_model(ec_classes=100, hidden_dim=256)
        # Check model has expected components
        assert hasattr(model, "shared")
        assert hasattr(model, "ec_head")
        assert hasattr(model, "kcat_head")
        assert hasattr(model, "fba_head")
        assert hasattr(model, "log_sigma_ec")

    def test_model_forward(self):
        import torch
        from multitask_model import build_multitask_model
        model = build_multitask_model(ec_classes=50, hidden_dim=128)
        x = torch.randn(4, 1280)
        outputs = model(x)
        assert outputs["ec_logits"].shape == (4, 50)
        assert outputs["kcat_pred"].shape == (4,)
        assert outputs["fba_logits"].shape == (4,)

    def test_model_loss_computation(self):
        import torch
        from multitask_model import build_multitask_model
        model = build_multitask_model(ec_classes=10, hidden_dim=64)
        x = torch.randn(8, 1280)
        outputs = model(x)
        targets = {
            "ec": torch.randint(0, 10, (8,)),
            "kcat": torch.randn(8),
            "fba": torch.randint(0, 2, (8,)).float(),
        }
        masks = {
            "ec": torch.ones(8, dtype=torch.bool),
            "kcat": torch.ones(8, dtype=torch.bool),
            "fba": torch.ones(8, dtype=torch.bool),
        }
        loss = model.compute_loss(outputs, targets, masks)
        assert loss.item() > 0
        assert not torch.isnan(loss)

    def test_partial_masks(self):
        import torch
        from multitask_model import build_multitask_model
        model = build_multitask_model(ec_classes=10, hidden_dim=64)
        x = torch.randn(8, 1280)
        outputs = model(x)
        targets = {
            "ec": torch.randint(0, 10, (8,)),
            "kcat": torch.randn(8),
            "fba": torch.randint(0, 2, (8,)).float(),
        }
        # Only EC has labels
        masks = {
            "ec": torch.ones(8, dtype=torch.bool),
            "kcat": torch.zeros(8, dtype=torch.bool),
            "fba": torch.zeros(8, dtype=torch.bool),
        }
        loss = model.compute_loss(outputs, targets, masks)
        assert loss.item() > 0


# ---------------------------------------------------------------------------
# Omics Constraint Tests
# ---------------------------------------------------------------------------

class TestOmicsConstraint:
    def test_load_expression_matrix(self, tmp_path):
        from omics_constrain import load_expression_matrix
        csv_path = tmp_path / "expr.csv"
        csv_path.write_text(
            "gene_id,glucose,ethanol,nitrogen_starvation\n"
            "YAL001C,10.5,2.3,5.1\n"
            "YAL002W,8.2,4.1,3.7\n"
            "YBL003C,1.0,12.5,7.8\n",
            encoding="utf-8",
        )
        gene_ids, conditions, matrix = load_expression_matrix(csv_path)
        assert gene_ids == ["YAL001C", "YAL002W", "YBL003C"]
        assert conditions == ["glucose", "ethanol", "nitrogen_starvation"]
        assert matrix.shape == (3, 3)
        assert matrix[0, 0] == pytest.approx(10.5)

    def test_load_expression_missing_file(self, tmp_path):
        from omics_constrain import OmicsConstraintError, load_expression_matrix
        with pytest.raises(OmicsConstraintError, match="not found"):
            load_expression_matrix(tmp_path / "nonexistent.csv")

    def test_pseudo_gpr_inference_interface(self):
        """Test that pseudo-GPR inference handles edge cases."""
        from omics_constrain import infer_pseudo_gpr
        # Mock model with no genes
        mock_model = MagicMock()
        mock_model.genes = []
        mock_model.reactions = []
        result = infer_pseudo_gpr(mock_model, np.array([]), [])
        assert result == {}


# ---------------------------------------------------------------------------
# Acquisition Tests
# ---------------------------------------------------------------------------

class TestAcquisition:
    def test_expected_improvement(self):
        from acquisition import acquisition_expected_improvement
        mean = np.array([0.8, 0.5, 0.3, 0.9])
        std = np.array([0.1, 0.3, 0.2, 0.05])
        ei = acquisition_expected_improvement(mean, std, best_so_far=0.7)
        assert ei.shape == (4,)
        # High mean + high std should have higher EI than low mean + low std
        assert ei[0] > ei[2]  # 0.8+0.1 > 0.3+0.2
        # Below-best with zero uncertainty should have ~zero EI
        mean_below = np.array([0.5, 0.5])
        std_zero = np.array([0.0, 0.3])
        ei_below = acquisition_expected_improvement(mean_below, std_zero, best_so_far=0.7)
        assert ei_below[0] == pytest.approx(0.0, abs=1e-6)
        # Uncertainty adds exploration value even below best
        assert ei_below[1] > ei_below[0]

    def test_bald_scores(self):
        from acquisition import acquisition_bald
        scores = np.array([0.5, 0.1, 0.9, 0.3])
        result = acquisition_bald(scores)
        np.testing.assert_array_equal(result, scores)

    def test_select_candidates(self):
        from acquisition import select_candidates
        ensemble_results = {
            "fba_prob_mean": np.array([0.9, 0.7, 0.5, 0.3, 0.8]),
            "fba_prob_std": np.array([0.05, 0.2, 0.15, 0.1, 0.1]),
            "kcat_pred_mean": np.array([2.0, 1.5, 1.0, 0.5, 1.8]),
            "kcat_pred_std": np.array([0.1, 0.2, 0.3, 0.1, 0.15]),
            "ec_entropy": np.array([1.0, 2.0, 1.5, 0.5, 1.2]),
            "bald_scores": np.array([0.1, 0.5, 0.3, 0.2, 0.4]),
        }
        candidates = select_candidates(ensemble_results, method="ei", top_k=3)
        assert len(candidates) == 3
        assert candidates[0]["rank"] == 1
        assert all(c["index"] >= 0 for c in candidates)
        # Scores should be descending
        scores = [c["acquisition_score"] for c in candidates]
        assert scores == sorted(scores, reverse=True)

    def test_select_candidates_with_exclusion(self):
        from acquisition import select_candidates
        ensemble_results = {
            "fba_prob_mean": np.array([0.9, 0.8, 0.7]),
            "fba_prob_std": np.array([0.1, 0.1, 0.1]),
            "kcat_pred_mean": np.array([1.0, 1.0, 1.0]),
            "kcat_pred_std": np.array([0.1, 0.1, 0.1]),
            "ec_entropy": np.array([1.0, 1.0, 1.0]),
            "bald_scores": np.array([0.1, 0.2, 0.3]),
        }
        # Exclude index 0 (highest score)
        candidates = select_candidates(
            ensemble_results, method="ei", top_k=2, exclude_indices={0}
        )
        assert all(c["index"] != 0 for c in candidates)


# ---------------------------------------------------------------------------
# ID Mapping Tests
# ---------------------------------------------------------------------------

class TestIDMapping:
    def test_resolve_same_namespace(self):
        from id_mapping_bridge import resolve_compound
        result = resolve_compound("MNXM123", "metanetx", "metanetx")
        assert result == "MNXM123"

    def test_build_bigg_index_structure(self):
        from id_mapping_bridge import build_bigg_to_metanx_index
        # With empty mapping
        index = build_bigg_to_metanx_index({})
        assert isinstance(index, dict)
        assert len(index) == 0


# ---------------------------------------------------------------------------
# Workflow Integration Tests
# ---------------------------------------------------------------------------

class TestWorkflow:
    def test_dry_run_yeast(self):
        from cross_species_workflow import run_workflow
        result = run_workflow(species="yeast", dry_run=True)
        assert result["dry_run"] is True
        assert result["species"] == "yeast"
        assert "plan" in result["stages"]
        assert "load_gem" in result["stages"]["plan"]

    def test_invalid_species_raises(self):
        from cross_species_workflow import WorkflowError, run_workflow
        with pytest.raises(WorkflowError, match="Unknown species"):
            run_workflow(species="invalid_organism", dry_run=True)

    def test_dry_run_with_all_options(self):
        from cross_species_workflow import run_workflow
        result = run_workflow(
            species="ecoli",
            target_metabolite="atp_c",
            expression_path=Path("fake_expr.csv"),
            constraint_method="imat",
            acquisition_method="bald",
            fasta_path=Path("fake.fasta"),
            ensemble_dir=Path("fake_ensemble"),
            dry_run=True,
        )
        assert result["species"] == "ecoli"
        assert "omics_constrain" in result["stages"]["plan"]
        assert "acquisition" in result["stages"]["plan"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
