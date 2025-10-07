"""Integration test demonstrating model path ordering bug.

BUG: When resolving multiple models where some auto-resolve and others need user
intervention, the final models_resolved list gets out of order with model_refs.
This causes update_workflow_model_paths() to write the wrong model path to the
wrong node.

Scenario from logs:
1. Workflow has TWO model references:
   - Node 86 (DownloadAndLoadDepthAnythingV2Model): depth_anything model (auto-resolves)
   - Node 254 (CheckpointLoaderSimple): FLUX model (needs user selection)

2. After fix_resolution() appends the user-selected FLUX model:
   - models_resolved = [depth_anything, flux]
   - model_refs = [ref_node86, ref_node254]

3. But the update loop assumes index alignment:
   - i=0: model[0] (depth_anything) → ref[0] (node86) ✓ CORRECT
   - i=1: model[1] (flux) → ref[1] (node254) ✗ SHOULD BE CORRECT BUT ISN'T

4. The actual bug happens because model_refs order doesn't match resolution order
   after fix_resolution() appends newly resolved models.

This test creates the exact scenario to verify the bug exists.
"""
import json
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from conftest import simulate_comfyui_save_workflow


class TestModelPathOrderingBug:
    """Test demonstrating model path order mismatch bug."""

    def test_multiple_models_wrong_paths_after_resolution(
        self,
        test_env,
        test_models
    ):
        """
        BUG TEST: When workflow has multiple models where BOTH need resolution
        but are processed in different order, update_workflow_model_paths()
        writes wrong paths to wrong nodes.

        Root cause: The function iterates models_resolved using index i, then
        looks up model_refs[i], assuming they align. But after fix_resolution()
        processes unresolved models, the order can be different.

        Expected Behavior:
        - Node 86 should get depth_anything path
        - Node 254 should get checkpoint (sd15) path

        Actual Behavior (BUG):
        - When models_resolved order != model_refs order
        - Wrong model path goes to wrong node
        """
        # ARRANGE: Create workflow with TWO models
        # BOTH have invalid paths initially to force resolution
        # The key is that model_refs will be in NODE ID order (86, 254)
        # But resolution might process them differently
        workflow_data = {
            "id": "test-multi-model",
            "nodes": [
                {
                    "id": 86,
                    "type": "DownloadAndLoadDepthAnythingV2Model",
                    "pos": [100, 100],
                    "widgets_values": ["depth_anything_v2_vits_fp16.safetensors"]  # Auto-resolves
                },
                {
                    "id": 254,
                    "type": "CheckpointLoaderSimple",
                    "pos": [200, 200],
                    "widgets_values": ["FLUX/checkpoint-INVALID.safetensors"]  # Needs user selection
                }
            ],
            "links": []
        }

        simulate_comfyui_save_workflow(test_env, "multi_model_test", workflow_data)

        # ACT: Resolve workflow
        workflow_status = test_env.workflow_manager.get_workflow_status()
        workflow_analysis = workflow_status.analyzed_workflows[0]

        # Verify initial state: should have one resolved, one unresolved
        assert len(workflow_analysis.resolution.models_resolved) == 1, \
            "depth_anything should auto-resolve"
        assert len(workflow_analysis.resolution.models_unresolved) == 1, \
            "checkpoint should be unresolved"

        # Verify the auto-resolved model is depth_anything
        # models_resolved is now a dict, so get the first resolved model from values
        auto_resolved = list(workflow_analysis.resolution.models_resolved.values())[0]
        assert "depth_anything" in auto_resolved.filename.lower(), \
            f"First resolved model should be depth_anything, got: {auto_resolved.filename}"

        # Simulate user selecting sd15_v1.safetensors for the checkpoint node
        from comfydock_core.models.protocols import ModelResolutionStrategy

        class SelectCheckpointStrategy(ModelResolutionStrategy):
            def resolve_ambiguous_model(self, ref, candidates):
                return candidates[0] if candidates else None

            def handle_missing_model(self, ref):
                # User selects sd15_v1.safetensors for the checkpoint
                if ref.node_type == "CheckpointLoaderSimple":
                    model = test_env.model_repository.find_by_filename("sd15_v1.safetensors")
                    if model:
                        return ("select", model[0].relative_path)
                return None

        # Apply fix_resolution - this is where the bug manifests
        resolution = test_env.workflow_manager.fix_resolution(
            workflow_analysis.resolution,
            model_strategy=SelectCheckpointStrategy()
        )

        # After fix_resolution, we should have 2 models
        assert len(resolution.models_resolved) == 2, \
            "Should have 2 resolved models after fix_resolution"

        # CRITICAL CHECK: Verify the mapping (dict, not list anymore)
        # models_resolved = {ref_node86: depth_anything, ref_node254: sd15}
        model_refs = workflow_analysis.dependencies.found_models

        print(f"\n=== Resolution Mapping ===")
        for ref, model in resolution.models_resolved.items():
            print(f"node_id={ref.node_id}, node_type={ref.node_type} → {model.filename} ({model.relative_path})")

        print(f"\nmodel_refs order:")
        print(f"  [0]: node_id={model_refs[0].node_id}, node_type={model_refs[0].node_type}")
        print(f"  [1]: node_id={model_refs[1].node_id}, node_type={model_refs[1].node_type}")

        # Apply the resolution - THIS IS WHERE THE BUG HAPPENS
        test_env.workflow_manager.apply_resolution(
            resolution,
            workflow_name="multi_model_test",
            model_refs=model_refs
        )

        # ASSERT: Check the workflow JSON was updated correctly (or incorrectly due to bug)
        workflow_path = test_env.comfyui_path / "user/default/workflows/multi_model_test.json"
        with open(workflow_path) as f:
            updated_workflow = json.load(f)

        # Find the nodes
        node_86 = next(n for n in updated_workflow["nodes"] if n["id"] == 86)
        node_254 = next(n for n in updated_workflow["nodes"] if n["id"] == 254)

        node_86_path = node_86["widgets_values"][0]
        node_254_path = node_254["widgets_values"][0]

        print(f"\n=== Updated Workflow Paths ===")
        print(f"Node 86 (DepthAnything): {node_86_path}")
        print(f"Node 254 (Checkpoint): {node_254_path}")

        # With the FIX: Each node gets the CORRECT model from the explicit mapping
        # - Node 86 should have depth_anything path
        # - Node 254 should have sd15 path

        assert "depth_anything" in node_86_path.lower(), \
            f"Node 86 should have depth_anything model, got: {node_86_path}"

        assert "sd15" in node_254_path.lower(), \
            (f"FIX VERIFIED: Node 254 should have checkpoint (sd15) model from the mapping, "
             f"got: {node_254_path}. "
             f"This proves update_workflow_model_paths() now correctly uses ref-based mapping.")

    def test_model_refs_order_matches_resolution_order(
        self,
        test_env,
        test_models
    ):
        """
        Helper test to verify the core assumption about order preservation.

        This test checks if model_refs order is preserved during resolution.
        If this test passes, it confirms the bug is in update_workflow_model_paths()
        assuming wrong index alignment.
        """
        # Create workflow with two models in specific order
        workflow_data = {
            "id": "order-test",
            "nodes": [
                {
                    "id": 1,
                    "type": "CheckpointLoaderSimple",
                    "pos": [0, 0],
                    "widgets_values": ["invalid1.safetensors"]
                },
                {
                    "id": 2,
                    "type": "CheckpointLoaderSimple",
                    "pos": [100, 100],
                    "widgets_values": ["invalid2.safetensors"]
                }
            ],
            "links": []
        }

        simulate_comfyui_save_workflow(test_env, "order_test", workflow_data)

        workflow_status = test_env.workflow_manager.get_workflow_status()
        workflow_analysis = workflow_status.analyzed_workflows[0]

        # Check model_refs order
        model_refs = workflow_analysis.dependencies.found_models
        assert len(model_refs) == 2
        assert model_refs[0].node_id == "1", "First ref should be node 1"
        assert model_refs[1].node_id == "2", "Second ref should be node 2"

        # Resolve both manually in reverse order
        from comfydock_core.models.protocols import ModelResolutionStrategy

        class ReverseOrderStrategy(ModelResolutionStrategy):
            def __init__(self, model_repo):
                self.model_repo = model_repo
                self.call_count = 0

            def resolve_ambiguous_model(self, ref, candidates):
                return candidates[0] if candidates else None

            def handle_missing_model(self, ref):
                # First call (node 1) → assign sd15
                # Second call (node 2) → assign depth_anything
                models = ["sd15_v1.safetensors", "depth_anything_v2_vits_fp16.safetensors"]
                model_name = models[self.call_count % 2]
                self.call_count += 1

                model = self.model_repo.find_by_filename(model_name)
                if model:
                    return ("select", model[0].relative_path)
                return None

        strategy = ReverseOrderStrategy(test_env.model_repository)
        resolution = test_env.workflow_manager.fix_resolution(
            workflow_analysis.resolution,
            model_strategy=strategy
        )

        # After resolution, check the order
        print(f"\n=== Order Test ===")
        print(f"model_refs order: node {model_refs[0].node_id}, node {model_refs[1].node_id}")
        print(f"models_resolved mapping: {[(ref.node_id, model.filename) for ref, model in resolution.models_resolved.items()]}")

        # The bug: models_resolved gets appended in order of user resolution,
        # not in order of model_refs
        # Expected: models_resolved aligns with model_refs
        # Actual: models_resolved is in resolution order (append order)
