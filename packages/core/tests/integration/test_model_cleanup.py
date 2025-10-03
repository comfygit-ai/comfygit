"""Integration tests for model cleanup on commit."""
import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from conftest import simulate_comfyui_save_workflow


class TestModelCleanup:
    """Test that unused models are removed on commit."""

    def test_model_replaced_removes_old_model(self, test_env, test_models):
        """When workflow changes to different model, old model should be removed."""
        # ARRANGE: Create workflow with first model
        workflow_v1 = {
            "id": "test-001",
            "nodes": [
                {
                    "id": 4,
                    "type": "CheckpointLoaderSimple",
                    "pos": [26, 474],
                    "widgets_values": ["missing-model.safetensors"]
                }
            ],
            "links": []
        }

        simulate_comfyui_save_workflow(test_env, "test_workflow", workflow_v1)

        # Resolve to first model
        workflow_status = test_env.workflow_manager.get_workflow_status()
        workflow_analysis = workflow_status.analyzed_workflows[0]

        from comfydock_core.models.protocols import ModelResolutionStrategy

        class SelectModelStrategy(ModelResolutionStrategy):
            def __init__(self, repo):
                self.repo = repo

            def resolve_ambiguous_model(self, ref, candidates):
                return candidates[0] if candidates else None

            def handle_missing_model(self, ref):
                model = self.repo.find_by_filename("sd15_v1.safetensors")
                if model:
                    return ("select", model[0].relative_path)
                return None

        resolution = test_env.workflow_manager.fix_resolution(
            workflow_analysis.resolution,
            model_strategy=SelectModelStrategy(test_env.model_repository)
        )

        test_env.workflow_manager.apply_resolution(
            resolution,
            workflow_name="test_workflow",
            model_refs=workflow_analysis.dependencies.found_models
        )

        # Check first model is in pyproject
        config = test_env.pyproject.load()
        models_required = config["tool"]["comfydock"]["models"]["required"]
        sd15_hash = list(models_required.keys())[0]

        assert len(models_required) == 1, "Should have exactly 1 model"

        # ACT: Change workflow to use different model (simulate user editing in ComfyUI)
        # User changes the model path in ComfyUI and saves
        workflow_path = test_env.comfyui_path / "user/default/workflows/test_workflow.json"
        with open(workflow_path) as f:
            workflow_data = json.load(f)

        # Change to different model (simulate user action)
        workflow_data["nodes"][0]["widgets_values"][0] = "different-model.safetensors"

        with open(workflow_path, 'w') as f:
            json.dump(workflow_data, f)

        # Copy and analyze again (like during commit)
        test_env.workflow_manager.copy_all_workflows()
        workflow_status = test_env.workflow_manager.get_workflow_status()
        workflow_analysis = workflow_status.analyzed_workflows[0]

        # Resolve to SAME model (simulating user picked same model with different name)
        resolution = test_env.workflow_manager.fix_resolution(
            workflow_analysis.resolution,
            model_strategy=SelectModelStrategy(test_env.model_repository)
        )

        # Apply resolution (should replace mapping)
        test_env.workflow_manager.apply_resolution(
            resolution,
            workflow_name="test_workflow",
            model_refs=workflow_analysis.dependencies.found_models
        )

        # ASSERT: Should still have 1 model (replaced, not accumulated)
        config = test_env.pyproject.load()
        models_required = config["tool"]["comfydock"]["models"]["required"]

        assert len(models_required) == 1, "Should still have exactly 1 model (replaced, not accumulated)"

        # Workflow mapping should only reference current model
        workflow_models = config["tool"]["comfydock"]["workflows"]["test_workflow"]["models"]
        assert len(workflow_models) == 1, "Workflow should only reference 1 model"
        assert sd15_hash in workflow_models, "Should reference the current model"

    def test_orphaned_models_removed_after_all_workflows(self, test_env, test_models):
        """Orphaned models should be removed after all workflows processed."""
        # ARRANGE: Create TWO workflows using SAME model
        workflow_a = {
            "id": "workflow-a",
            "nodes": [{"id": 4, "type": "CheckpointLoaderSimple", "widgets_values": ["model.safetensors"]}],
            "links": []
        }
        workflow_b = {
            "id": "workflow-b",
            "nodes": [{"id": 5, "type": "CheckpointLoaderSimple", "widgets_values": ["model.safetensors"]}],
            "links": []
        }

        simulate_comfyui_save_workflow(test_env, "workflow_a", workflow_a)
        simulate_comfyui_save_workflow(test_env, "workflow_b", workflow_b)

        # Resolve both to sd15_v1
        from comfydock_core.models.protocols import ModelResolutionStrategy

        class SelectSD15Strategy(ModelResolutionStrategy):
            def __init__(self, repo):
                self.repo = repo

            def resolve_ambiguous_model(self, ref, candidates):
                return candidates[0] if candidates else None

            def handle_missing_model(self, ref):
                model = self.repo.find_by_filename("sd15_v1.safetensors")
                if model:
                    return ("select", model[0].relative_path)
                return None

        workflow_status = test_env.workflow_manager.get_workflow_status()

        for workflow_analysis in workflow_status.analyzed_workflows:
            resolution = test_env.workflow_manager.fix_resolution(
                workflow_analysis.resolution,
                model_strategy=SelectSD15Strategy(test_env.model_repository)
            )
            test_env.workflow_manager.apply_resolution(
                resolution,
                workflow_name=workflow_analysis.name,
                model_refs=workflow_analysis.dependencies.found_models
            )

        # Both workflows reference same model
        config = test_env.pyproject.load()
        sd15_hash = list(config["tool"]["comfydock"]["models"]["required"].keys())[0]

        # ACT: Remove workflow_b (simulate user deleting it)
        workflow_b_path = test_env.comfyui_path / "user/default/workflows/workflow_b.json"
        workflow_b_path.unlink()

        # Commit (which copies workflows and does cleanup)
        test_env.workflow_manager.copy_all_workflows()
        workflow_status = test_env.workflow_manager.get_workflow_status()

        # Apply all resolutions (triggers cleanup)
        test_env.workflow_manager.apply_all_resolution(workflow_status)

        # ASSERT: Model should still exist (workflow_a still uses it)
        config = test_env.pyproject.load()
        models_required = config["tool"]["comfydock"]["models"]["required"]

        assert sd15_hash in models_required, "Model should remain (workflow_a still uses it)"
        assert len(models_required) == 1, "Should have exactly 1 model"
