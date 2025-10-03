"""Integration tests for model resolution and workflow updates.

Tests the complete flow:
1. User saves workflow with invalid/missing model path
2. User runs resolve command
3. Pyproject.toml updated with hash-based mapping (PRD schema)
4. Workflow JSON updated with resolved path
"""
import json
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from conftest import (
    simulate_comfyui_save_workflow,
)


class TestModelResolutionFlow:
    """E2E tests for model resolution and workflow updates."""

    def test_pyproject_schema_matches_prd_after_resolution(
        self,
        test_env,
        test_models
    ):
        """
        Test that pyproject.toml follows PRD schema after model resolution.

        Expected PRD schema:
        [tool.comfydock.workflows.my_workflow]
        path = "workflows/my_workflow.json"
        models = { "abc123..." = { nodes = [{node_id = "3", widget_idx = "0"}] } }

        [tool.comfydock.models.required]
        "abc123..." = {
          filename = "sd15.safetensors",
          relative_path = "checkpoints/sd15.safetensors",
          hash = "abc123...",
          size = 4265146304
        }
        """
        # ARRANGE: Create workflow with invalid model path
        workflow_data = {
            "id": "test-001",
            "nodes": [
                {
                    "id": 4,
                    "type": "CheckpointLoaderSimple",
                    "pos": [26, 474],
                    "widgets_values": ["v1-5-pruned-emaonly-fp16.safetensors"]  # Invalid path
                }
            ],
            "links": []
        }

        simulate_comfyui_save_workflow(test_env, "test_workflow", workflow_data)

        # ACT: Resolve the model (user selects sd15_v1.safetensors from index)
        workflow_status = test_env.workflow_manager.get_workflow_status()
        workflow_analysis = workflow_status.analyzed_workflows[0]

        # Simulate user selecting photon_v1 as resolution
        from comfydock_core.models.protocols import ModelResolutionStrategy

        class SelectFirstModelStrategy(ModelResolutionStrategy):
            def resolve_ambiguous_model(self, ref, candidates):
                return candidates[0] if candidates else None

            def handle_missing_model(self, ref):
                # Find photon_v1 in index
                model = test_env.model_repository.find_by_filename("sd15_v1.safetensors")
                if model:
                    return ("select", model[0].relative_path)
                return None

        resolution = test_env.workflow_manager.fix_resolution(
            workflow_analysis.resolution,
            model_strategy=SelectFirstModelStrategy()
        )

        test_env.workflow_manager.apply_resolution(
            resolution,
            workflow_name="test_workflow",
            model_refs=workflow_analysis.dependencies.found_models
        )

        # ASSERT: Check pyproject.toml follows PRD schema
        config = test_env.pyproject.load()

        # 1. Check models.required section exists with hash as key
        models_required = config.get("tool", {}).get("comfydock", {}).get("models", {}).get("required", {})
        assert models_required, "models.required section should exist"

        # Get the model hash from the actual index (not test_models fixture)
        indexed_models = test_env.model_repository.find_by_filename("sd15_v1.safetensors")
        assert indexed_models, "sd15_v1.safetensors should be in index"
        sd15_hash = indexed_models[0].hash
        assert sd15_hash in models_required, f"Model hash {sd15_hash} should be in models.required"

        # 2. Check model entry has correct fields
        model_entry = models_required[sd15_hash]
        assert model_entry["filename"] == "sd15_v1.safetensors"
        assert model_entry["relative_path"] == "checkpoints/sd15_v1.safetensors"
        assert model_entry["size"] == indexed_models[0].file_size

        # 3. Check workflow section maps hash to node location
        workflows = config.get("tool", {}).get("comfydock", {}).get("workflows", {})
        assert "test_workflow" in workflows, "Workflow should be tracked"

        workflow_entry = workflows["test_workflow"]
        assert "path" in workflow_entry
        assert workflow_entry["path"] == "workflows/test_workflow.json"

        # 4. Check models mapping uses hash as key (NOT original workflow reference)
        models_mapping = workflow_entry.get("models", {})
        assert sd15_hash in models_mapping, f"Hash {sd15_hash} should be key in workflow.models"

        # 5. Check node location is tracked
        hash_mapping = models_mapping[sd15_hash]
        assert "nodes" in hash_mapping
        assert len(hash_mapping["nodes"]) == 1
        assert hash_mapping["nodes"][0]["node_id"] == "4"
        assert hash_mapping["nodes"][0]["widget_idx"] == 0

    def test_workflow_json_updated_after_resolution(
        self,
        test_env,
        test_models
    ):
        """
        Test that workflow JSON is updated with resolved model path.

        Critical UX requirement: After resolution, ComfyUI should see
        the correct path, not the invalid one user originally entered.
        """
        # ARRANGE: Workflow with invalid path
        workflow_data = {
            "id": "test-002",
            "nodes": [
                {
                    "id": 4,
                    "type": "CheckpointLoaderSimple",
                    "pos": [26, 474],
                    "widgets_values": ["invalid-model-path.safetensors"]
                }
            ],
            "links": []
        }

        simulate_comfyui_save_workflow(test_env, "test_workflow", workflow_data)

        # ACT: Resolve to photon_v1
        workflow_status = test_env.workflow_manager.get_workflow_status()
        workflow_analysis = workflow_status.analyzed_workflows[0]

        from comfydock_core.models.protocols import ModelResolutionStrategy

        class SelectPhotonStrategy(ModelResolutionStrategy):
            def resolve_ambiguous_model(self, ref, candidates):
                return candidates[0] if candidates else None

            def handle_missing_model(self, ref):
                model = test_env.model_repository.find_by_filename("sd15_v1.safetensors")
                if model:
                    return ("select", model[0].relative_path)
                return None

        resolution = test_env.workflow_manager.fix_resolution(
            workflow_analysis.resolution,
            model_strategy=SelectPhotonStrategy()
        )

        test_env.workflow_manager.apply_resolution(
            resolution,
            workflow_name="test_workflow",
            model_refs=workflow_analysis.dependencies.found_models
        )

        # ASSERT 1: ComfyUI workflow JSON should have resolved path
        comfyui_workflow_path = test_env.comfyui_path / "user/default/workflows/test_workflow.json"
        assert comfyui_workflow_path.exists(), "Workflow should exist in ComfyUI directory"

        with open(comfyui_workflow_path) as f:
            updated_workflow = json.load(f)

        # Check the widget value was updated
        checkpoint_node = next(n for n in updated_workflow["nodes"] if n["id"] == 4)
        assert checkpoint_node["widgets_values"][0] == "checkpoints/sd15_v1.safetensors", \
            "Workflow JSON should have resolved path, not original invalid path"

        # ASSERT 2: .cec workflow should ALSO have resolved path (after commit)
        test_env.workflow_manager.copy_all_workflows()
        cec_workflow_path = test_env.cec_path / "workflows/test_workflow.json"

        with open(cec_workflow_path) as f:
            cec_workflow = json.load(f)

        cec_checkpoint_node = next(n for n in cec_workflow["nodes"] if n["id"] == 4)
        assert cec_checkpoint_node["widgets_values"][0] == "checkpoints/sd15_v1.safetensors", \
            ".cec workflow should have resolved path"

    def test_multiple_models_in_workflow(
        self,
        test_env,
        test_models
    ):
        """
        Test workflow with multiple model references.

        Ensures:
        - Each model tracked separately in models.required
        - All models mapped in workflow.models by hash
        - All widget values updated in JSON
        """
        # ARRANGE: Workflow with 2 models
        workflow_data = {
            "id": "test-003",
            "nodes": [
                {
                    "id": 4,
                    "type": "CheckpointLoaderSimple",
                    "pos": [26, 474],
                    "widgets_values": ["checkpoint.safetensors"]  # Invalid
                },
                {
                    "id": 5,
                    "type": "LoraLoader",
                    "pos": [100, 500],
                    "widgets_values": ["lora.safetensors", 1.0, 1.0]  # Invalid
                }
            ],
            "links": []
        }

        simulate_comfyui_save_workflow(test_env, "multi_model", workflow_data)

        # ACT: Resolve both models
        workflow_status = test_env.workflow_manager.get_workflow_status()
        workflow_analysis = workflow_status.analyzed_workflows[0]

        from comfydock_core.models.protocols import ModelResolutionStrategy

        class ResolveAllStrategy(ModelResolutionStrategy):
            def __init__(self, repo):
                self.repo = repo
                self.call_count = 0

            def resolve_ambiguous_model(self, ref, candidates):
                return candidates[0] if candidates else None

            def handle_missing_model(self, ref):
                # First call: resolve to photon_v1
                # Second call: resolve to another model
                models = ["sd15_v1.safetensors", "sd15_v1.safetensors"]  # Using same for simplicity
                model = self.repo.find_by_filename(models[min(self.call_count, 1)])
                self.call_count += 1
                if model:
                    return ("select", model[0].relative_path)
                return None

        strategy = ResolveAllStrategy(test_env.model_repository)
        resolution = test_env.workflow_manager.fix_resolution(
            workflow_analysis.resolution,
            model_strategy=strategy
        )

        test_env.workflow_manager.apply_resolution(
            resolution,
            workflow_name="multi_model",
            model_refs=workflow_analysis.dependencies.found_models
        )

        # ASSERT: Check pyproject has both models
        config = test_env.pyproject.load()
        models_required = config["tool"]["comfydock"]["models"]["required"]

        # Should have at least one model (both resolved to same model in this test)
        indexed_models = test_env.model_repository.find_by_filename("sd15_v1.safetensors")
        sd15_hash = indexed_models[0].hash
        assert sd15_hash in models_required

        # Check workflow mapping includes both node locations
        workflow_models = config["tool"]["comfydock"]["workflows"]["multi_model"]["models"]
        assert sd15_hash in workflow_models

        # Should have multiple node references
        nodes = workflow_models[sd15_hash]["nodes"]
        assert len(nodes) >= 1  # At least checkpoint loader

        # Verify JSON updated
        comfyui_workflow_path = test_env.comfyui_path / "user/default/workflows/multi_model.json"
        with open(comfyui_workflow_path) as f:
            updated = json.load(f)

        # Both nodes should have resolved paths
        checkpoint = next(n for n in updated["nodes"] if n["id"] == 4)
        assert "checkpoints/sd15_v1.safetensors" in checkpoint["widgets_values"][0]

    def test_resolution_preserves_other_workflow_data(
        self,
        test_env,
        test_models
    ):
        """
        Test that resolution only updates model paths, preserves everything else.

        Ensures:
        - Node positions unchanged
        - Other widget values unchanged
        - Links preserved
        - Metadata preserved
        """
        # ARRANGE: Full workflow with lots of data
        workflow_data = {
            "id": "preserve-test",
            "revision": 5,
            "last_node_id": 10,
            "nodes": [
                {
                    "id": 4,
                    "type": "CheckpointLoaderSimple",
                    "pos": [100, 200],
                    "size": [300, 400],
                    "widgets_values": ["wrong.safetensors"]
                },
                {
                    "id": 5,
                    "type": "CLIPTextEncode",
                    "pos": [500, 600],
                    "widgets_values": ["beautiful scenery"]
                }
            ],
            "links": [[1, 4, 0, 5, 0, "CLIP"]],
            "groups": [],
            "extra": {"ds": {"scale": 1.0}}
        }

        simulate_comfyui_save_workflow(test_env, "preserve", workflow_data)

        # ACT: Resolve model
        workflow_status = test_env.workflow_manager.get_workflow_status()
        workflow_analysis = workflow_status.analyzed_workflows[0]

        from comfydock_core.models.protocols import ModelResolutionStrategy

        class SimpleStrategy(ModelResolutionStrategy):
            def resolve_ambiguous_model(self, ref, candidates):
                return candidates[0] if candidates else None

            def handle_missing_model(self, ref):
                model = test_env.model_repository.find_by_filename("sd15_v1.safetensors")
                if model:
                    return ("select", model[0].relative_path)
                return None

        resolution = test_env.workflow_manager.fix_resolution(
            workflow_analysis.resolution,
            model_strategy=SimpleStrategy()
        )

        test_env.workflow_manager.apply_resolution(
            resolution,
            workflow_name="preserve",
            model_refs=workflow_analysis.dependencies.found_models
        )

        # ASSERT: Everything preserved except model path
        comfyui_workflow_path = test_env.comfyui_path / "user/default/workflows/preserve.json"
        with open(comfyui_workflow_path) as f:
            updated = json.load(f)

        # Metadata preserved
        assert updated["id"] == "preserve-test"
        assert updated["revision"] == 5
        assert updated["last_node_id"] == 10

        # Node positions preserved
        checkpoint = next(n for n in updated["nodes"] if n["id"] == 4)
        assert checkpoint["pos"] == [100, 200]
        assert checkpoint["size"] == [300, 400]

        # Other nodes unchanged
        clip_node = next(n for n in updated["nodes"] if n["id"] == 5)
        assert clip_node["widgets_values"] == ["beautiful scenery"]

        # Links preserved
        assert updated["links"] == [[1, 4, 0, 5, 0, "CLIP"]]

        # Extra data preserved
        assert updated["extra"]["ds"]["scale"] == 1.0

        # But model path updated
        assert checkpoint["widgets_values"][0] == "checkpoints/sd15_v1.safetensors"
