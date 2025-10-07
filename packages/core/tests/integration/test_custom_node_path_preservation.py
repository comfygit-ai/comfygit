"""Test custom node path preservation during workflow commit.

This test suite verifies the fix for the custom node path stripping bug where
comfydock incorrectly modified model paths for custom nodes, breaking workflow
validation.

Bug context:
- Custom nodes like DownloadAndLoadDepthAnythingV2Model bypass extra_paths.yaml
- They scan ComfyUI/models/ directly and validate against discovered paths
- Adding subdirectory prefixes breaks their validation

Expected behavior:
- Builtin nodes: Strip base directory (e.g., "checkpoints/sd15/model.ckpt" → "sd15/model.ckpt")
- Custom nodes: Preserve original widget value (e.g., "model.safetensors" → "model.safetensors")
"""

import json
import sys
from pathlib import Path

import pytest

# Import test helpers
sys.path.insert(0, str(Path(__file__).parent.parent))
from conftest import load_workflow_fixture, simulate_comfyui_save_workflow


class TestCustomNodePathPreservation:
    """Test that custom nodes preserve original widget values during commit."""

    def test_custom_node_model_path_not_modified(self, test_env, test_models, workflow_fixtures):
        """
        Regression test for custom node path stripping bug.

        Context:
        - Custom nodes like DownloadAndLoadDepthAnythingV2Model bypass extra_paths.yaml
        - They scan ComfyUI/models/ directly and validate against discovered paths
        - Adding subdirectory prefixes breaks validation

        Bug scenario:
        - Original: "depth_anything_v2_vits_fp16.safetensors"
        - After commit (BUG): "depthanything/depth_anything_v2_vits_fp16.safetensors"
        - Result: Node validation fails

        Expected with fix:
        - Original: "depth_anything_v2_vits_fp16.safetensors"
        - After commit: "depth_anything_v2_vits_fp16.safetensors" (unchanged)
        - Result: Node validation passes
        """
        # ARRANGE: Load custom node workflow
        workflow_data = load_workflow_fixture(workflow_fixtures, "with_custom_node")
        simulate_comfyui_save_workflow(test_env, "custom_node_test", workflow_data)

        # Verify original widget value
        workflow_path = test_env.workflow_manager.comfyui_workflows / "custom_node_test.json"
        with open(workflow_path) as f:
            original_data = json.load(f)

        original_node = next(n for n in original_data["nodes"] if n["id"] == 86)
        original_widget_value = original_node["widgets_values"][0]
        assert original_widget_value == "depth_anything_v2_vits_fp16.safetensors"

        # ACT: Commit workflow (triggers model resolution and path update)
        workflow_status = test_env.workflow_manager.get_workflow_status()
        test_env.execute_commit(workflow_status, message="Test custom node commit")

        # ASSERT: Widget value should be UNCHANGED
        with open(workflow_path) as f:
            committed_data = json.load(f)

        committed_node = next(n for n in committed_data["nodes"] if n["id"] == 86)
        widget_value = committed_node["widgets_values"][0]

        # Should NOT have subdirectory added
        assert widget_value == "depth_anything_v2_vits_fp16.safetensors", \
            f"Custom node path should be preserved unchanged, got: {widget_value}"

        assert "/" not in widget_value, \
            f"Custom node path should not contain subdirectory separator, got: {widget_value}"

    def test_builtin_node_path_still_stripped(self, test_env, test_models):
        """
        Ensure builtin nodes still get proper base directory stripping.

        Builtin nodes like CheckpointLoaderSimple MUST have base directory stripped
        because they automatically prepend "checkpoints/" during loading.
        """
        # ARRANGE: Create workflow with builtin node
        workflow_data = {
            "nodes": [
                {
                    "id": 4,
                    "type": "CheckpointLoaderSimple",
                    "pos": [0, 0],
                    "widgets_values": ["checkpoints/sd15_v1.safetensors"]
                }
            ],
            "links": [],
            "groups": [],
            "config": {},
            "version": 0.4
        }

        simulate_comfyui_save_workflow(test_env, "builtin_test", workflow_data)

        # ACT: Commit
        workflow_status = test_env.workflow_manager.get_workflow_status()
        test_env.execute_commit(workflow_status, message="Test builtin commit")

        # ASSERT: Base directory should be STRIPPED
        committed_workflow_path = test_env.workflow_manager.comfyui_workflows / "builtin_test.json"
        with open(committed_workflow_path) as f:
            committed_data = json.load(f)

        node_4 = next(n for n in committed_data["nodes"] if n["id"] == 4)
        widget_value = node_4["widgets_values"][0]

        # Should have "checkpoints/" stripped
        assert widget_value == "sd15_v1.safetensors", \
            f"Builtin node should have base directory stripped, got: {widget_value}"

        assert not widget_value.startswith("checkpoints/"), \
            f"Widget value should not start with 'checkpoints/', got: {widget_value}"

    def test_mixed_builtin_and_custom_nodes(self, test_env, test_models):
        """
        Test workflow containing both builtin and custom nodes.

        Builtin nodes should be stripped, custom nodes should be preserved.
        """
        # ARRANGE: Create workflow with both types
        workflow_data = {
            "nodes": [
                {
                    "id": 1,
                    "type": "CheckpointLoaderSimple",
                    "pos": [0, 0],
                    "widgets_values": ["checkpoints/sd15_v1.safetensors"]
                },
                {
                    "id": 2,
                    "type": "DownloadAndLoadDepthAnythingV2Model",
                    "pos": [0, 100],
                    "widgets_values": ["depth_anything_v2_vits_fp16.safetensors"],
                    "properties": {
                        "Node name for S&R": "DownloadAndLoadDepthAnythingV2Model"
                    }
                },
                {
                    "id": 3,
                    "type": "LoraLoader",
                    "pos": [0, 200],
                    "widgets_values": ["loras/style_v1.safetensors", 1.0, 1.0]
                }
            ],
            "links": [],
            "groups": [],
            "config": {},
            "version": 0.4
        }

        simulate_comfyui_save_workflow(test_env, "mixed_test", workflow_data)

        # ACT: Commit
        workflow_status = test_env.workflow_manager.get_workflow_status()
        test_env.execute_commit(workflow_status, message="Test mixed commit")

        # ASSERT: Check each node
        committed_workflow_path = test_env.workflow_manager.comfyui_workflows / "mixed_test.json"
        with open(committed_workflow_path) as f:
            committed_data = json.load(f)

        nodes_by_id = {n["id"]: n for n in committed_data["nodes"]}

        # Builtin nodes: stripped
        checkpoint_value = nodes_by_id[1]["widgets_values"][0]
        assert checkpoint_value == "sd15_v1.safetensors", \
            f"CheckpointLoaderSimple should be stripped, got: {checkpoint_value}"

        lora_value = nodes_by_id[3]["widgets_values"][0]  # LoraLoader has model at index 0
        assert lora_value == "style_v1.safetensors", \
            f"LoraLoader should be stripped, got: {lora_value}"

        # Custom node: preserved
        custom_value = nodes_by_id[2]["widgets_values"][0]
        assert custom_value == "depth_anything_v2_vits_fp16.safetensors", \
            f"Custom node should be preserved, got: {custom_value}"

    def test_custom_node_with_subdirectory_preserved(self, test_env, test_models):
        """
        Custom node with subdirectory in widget value should be preserved as-is.

        Some custom nodes may already have subdirectory paths in widget values.
        These should be preserved exactly as they are.
        """
        # ARRANGE: Custom node with subdirectory path
        workflow_data = {
            "nodes": [
                {
                    "id": 10,
                    "type": "SomeCustomNode",
                    "pos": [0, 0],
                    "widgets_values": ["custom/subdir/model.safetensors"]
                }
            ],
            "links": [],
            "groups": [],
            "config": {},
            "version": 0.4
        }

        simulate_comfyui_save_workflow(test_env, "custom_subdir_test", workflow_data)

        # ACT: Commit
        workflow_status = test_env.workflow_manager.get_workflow_status()
        test_env.execute_commit(workflow_status, message="Test custom with subdir")

        # ASSERT: Path preserved exactly
        committed_workflow_path = test_env.workflow_manager.comfyui_workflows / "custom_subdir_test.json"
        with open(committed_workflow_path) as f:
            committed_data = json.load(f)

        node = committed_data["nodes"][0]
        widget_value = node["widgets_values"][0]

        assert widget_value == "custom/subdir/model.safetensors", \
            f"Custom node subdirectory path should be preserved exactly, got: {widget_value}"
