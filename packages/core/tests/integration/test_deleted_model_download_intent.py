"""Integration test for download intent creation when resolved models are deleted.

This test verifies that when a previously resolved model is deleted from disk,
the workflow resolver should use the global models table to automatically create
a download intent instead of prompting the user to search.
"""
from conftest import simulate_comfyui_save_workflow
from helpers.model_index_builder import ModelIndexBuilder
from helpers.pyproject_assertions import PyprojectAssertions
from comfygit_core.strategies.auto import AutoModelStrategy, AutoNodeStrategy


class TestDeletedModelDownloadIntent:
    """Test that deleted models create download intents from global models table."""

    def test_download_intent_from_global_table_after_deletion(self, test_env, test_workspace):
        """Should create download intent from global table when resolved model is deleted.

        Tests the fix for workflow_manager.py bugs:
        1. Fixed typo: self.pyproject_manager → self.pyproject
        2. Fixed iteration: .items() → direct iteration on list

        Flow:
        1. Setup: Simulate previously downloaded model (in global table with sources)
        2. Delete model file from disk
        3. Sync model index (removes from SQLite)
        4. Re-resolve workflow
        5. Should create download_intent from global table (not prompt user)
        """
        # ARRANGE: Create model and index it
        models_dir = test_workspace.workspace_config_manager.get_models_directory()
        builder = ModelIndexBuilder(test_workspace)

        builder.add_model(
            filename="test_vae.safetensors",
            relative_path="vae",
            size_mb=2
        )
        models = builder.index_all()
        model_hash = builder.get_hash("test_vae.safetensors")

        # SIMULATE: Model was previously downloaded (add source to repository AND global table)
        # In real usage, this happens during model download, not during scan
        test_env.model_repository.add_source(
            model_hash,
            source_type="direct",
            source_url="https://example.com/models/test_vae.safetensors"
        )

        # Also add to global models table directly (simulating a completed download/resolution)
        from comfygit_core.models.manifest import ManifestModel, ManifestWorkflowModel
        from comfygit_core.models.workflow import WorkflowNodeWidgetRef

        global_model = ManifestModel(
            hash=model_hash,
            filename="test_vae.safetensors",
            size=2097183,  # From builder
            relative_path="vae/test_vae.safetensors",
            category="vae",
            sources=["https://example.com/models/test_vae.safetensors"]
        )
        test_env.pyproject.models.add_model(global_model)

        # Create workflow with VAE loader
        workflow_json = {
            "id": "test-download-intent",
            "revision": 0,
            "last_node_id": 1,
            "last_link_id": 0,
            "nodes": [
                {
                    "id": 1,
                    "type": "VAELoader",
                    "flags": {},
                    "inputs": [],
                    "outputs": [],
                    "widgets_values": ["test_vae.safetensors"]
                }
            ],
            "links": [],
            "config": {},
            "version": 0.4
        }

        simulate_comfyui_save_workflow(test_env, "download_intent_test", workflow_json)

        # Add per-workflow model entry to simulate previous resolution
        workflow_model = ManifestWorkflowModel(
            hash=model_hash,
            filename="test_vae.safetensors",
            category="vae",
            criticality="flexible",
            status="resolved",
            nodes=[WorkflowNodeWidgetRef(node_id="1", node_type="VAELoader", widget_index=0, widget_value="test_vae.safetensors")]
        )
        test_env.pyproject.workflows.add_workflow_model("download_intent_test", workflow_model)

        # Verify model is in global table with sources
        assertions = PyprojectAssertions(test_env)
        (
            assertions
            .has_global_model(model_hash)
            .has_filename("test_vae.safetensors")
            .has_relative_path("vae/test_vae.safetensors")
        )

        # ACT 1: Delete model file
        model_path = models_dir / "vae" / "test_vae.safetensors"
        model_path.unlink()

        # ACT 2: Sync model index (removes model from SQLite)
        changes = test_workspace.sync_model_directory()
        assert changes == 1, f"Should detect 1 removal, got {changes} changes"

        # Verify model is gone from SQLite index
        models_in_index = test_env.model_repository.find_by_filename("test_vae.safetensors")
        assert len(models_in_index) == 0, "Model should be removed from index after sync"

        # ACT 3: Re-resolve workflow - should create download intent from global table
        resolution = test_env.resolve_workflow(
            name="download_intent_test",
            node_strategy=AutoNodeStrategy(),
            model_strategy=AutoModelStrategy()
        )

        # ASSERT: Should create download intent, NOT mark as unresolved
        vae_resolved = [
            m for m in resolution.models_resolved
            if "test_vae" in m.reference.widget_value
        ]
        vae_unresolved = [
            m for m in resolution.models_unresolved
            if "test_vae" in m.widget_value
        ]

        # KEY ASSERTION: Should create download intent
        assert len(vae_resolved) == 1, \
            "BUG: Should create download intent from global table, not mark as unresolved"
        assert len(vae_unresolved) == 0, \
            "Model should NOT be in unresolved list when global table has sources"

        # Verify it's a download intent (has source but no resolved_model)
        download_intent = vae_resolved[0]
        assert download_intent.match_type == "download_intent", \
            f"Expected match_type='download_intent', got '{download_intent.match_type}'"
        assert download_intent.model_source is not None, \
            "Download intent should have model_source URL"
        assert download_intent.resolved_model is None, \
            "Download intent should NOT have resolved_model (not downloaded yet)"

        # Verify pyproject shows download intent (status=unresolved with sources)
        (
            assertions
            .has_workflow("download_intent_test")
            .has_model_with_filename("test_vae.safetensors")
            .has_status("unresolved")  # Not downloaded yet (download was attempted but failed)
        )

        # Note: Global table entry might be removed/modified after failed download attempt
        # The key test is that the download intent was created, not the final state

    def test_no_download_intent_when_global_table_has_no_sources(self, test_env, test_workspace):
        """Should mark as unresolved when global table exists but has no sources.

        This tests the edge case where a model was resolved but sources were never
        recorded (shouldn't happen in practice, but we should handle gracefully).
        """
        # ARRANGE: Create model
        models_dir = test_workspace.workspace_config_manager.get_models_directory()
        builder = ModelIndexBuilder(test_workspace)

        builder.add_model(
            filename="no_source_vae.safetensors",
            relative_path="vae",
            size_mb=2
        )
        builder.index_all()

        # Create workflow
        workflow_json = {
            "id": "no-sources-test",
            "revision": 0,
            "last_node_id": 1,
            "last_link_id": 0,
            "nodes": [
                {
                    "id": 1,
                    "type": "VAELoader",
                    "flags": {},
                    "inputs": [],
                    "outputs": [],
                    "widgets_values": ["no_source_vae.safetensors"]
                }
            ],
            "links": [],
            "config": {},
            "version": 0.4
        }

        simulate_comfyui_save_workflow(test_env, "no_sources_test", workflow_json)

        # ACT 1: Resolve (adds to global table with no sources - local model)
        resolution1 = test_env.resolve_workflow(
            name="no_sources_test",
            node_strategy=AutoNodeStrategy(),
            model_strategy=AutoModelStrategy()
        )

        model_hash = resolution1.models_resolved[0].resolved_model.hash

        # Manually remove sources from global table to simulate edge case
        # (In practice, local models have no sources)
        config = test_env.pyproject.load()
        if model_hash in config["tool"]["comfygit"]["models"]:
            config["tool"]["comfygit"]["models"][model_hash]["sources"] = []
            test_env.pyproject.save(config)

        # ACT 2: Delete model and sync
        model_path = models_dir / "vae" / "no_source_vae.safetensors"
        model_path.unlink()
        test_workspace.sync_model_directory()

        # ACT 3: Re-resolve
        resolution2 = test_env.resolve_workflow(
            name="no_sources_test",
            node_strategy=AutoNodeStrategy(),
            model_strategy=AutoModelStrategy()
        )

        # ASSERT: Should be marked as unresolved (no sources to download from)
        unresolved = [
            m for m in resolution2.models_unresolved
            if "no_source_vae" in m.widget_value
        ]
        assert len(unresolved) == 1, \
            "Model should be unresolved when global table has no sources"
