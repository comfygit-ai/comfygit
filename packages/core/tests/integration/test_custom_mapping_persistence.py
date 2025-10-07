"""Test that interactive node resolution persists custom mappings to pyproject.toml.

This addresses the bug where users interactively resolve nodes (e.g., selecting
rgthree-comfy for "Mute / Bypass Repeater (rgthree)"), but running status again
still shows the same nodes as missing because the mapping wasn't saved.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from comfydock_core.models.workflow import ResolvedNodePackage
from comfydock_core.models.node_mapping import GlobalNodePackage

from conftest import simulate_comfyui_save_workflow


class TestInteractiveResolutionPersistence:
    """Test that interactive resolutions are saved to pyproject.toml node_mappings."""

    def test_interactive_resolution_saves_custom_mapping(self, test_env):
        """After interactive resolution, custom mapping should persist to pyproject.toml.

        Bug reproduction:
        1. User resolves "Mute / Bypass Repeater (rgthree)" → selects "rgthree-comfy"
        2. Resolution succeeds, node added to workflow
        3. Run status again → SAME NODE still shows as missing!
        4. Root cause: node_type → package_id mapping never saved
        """
        # ARRANGE: Create workflow with unresolved node (no properties, not in global table)
        workflow_data = {
            "nodes": [
                {
                    "id": "1",
                    "type": "LoadImage",
                    "pos": [100, 100],
                    "size": [200, 100],
                    "flags": {},
                    "order": 0,
                    "mode": 0,
                    "inputs": [],
                    "outputs": [{"name": "IMAGE", "type": "IMAGE", "links": [1]}],
                    "properties": {},
                    "widgets_values": ["test.png"]
                },
                {
                    "id": "2",
                    "type": "Mute / Bypass Repeater (rgthree)",
                    "pos": [400, 100],
                    "size": [200, 100],
                    "flags": {},
                    "order": 1,
                    "mode": 0,
                    "inputs": [{"name": "IMAGE", "type": "IMAGE", "link": 1}],
                    "outputs": [{"name": "IMAGE", "type": "IMAGE", "links": None}],
                    "properties": {
                        # No cnr_id! This is the bug case - old workflow
                        "ttNbgOverride": {"color": "#2a363b"}
                    },
                    "widgets_values": []
                }
            ],
            "links": [[1, 1, 0, 2, 0, "IMAGE"]],
            "groups": [],
            "config": {},
            "extra": {},
            "version": 0.4
        }

        simulate_comfyui_save_workflow(test_env, "rgthree_test", workflow_data)

        # ACT: First resolution - analyze and see it's unresolved
        analysis = test_env.workflow_manager.analyze_workflow("rgthree_test")
        resolution = test_env.workflow_manager.resolve_workflow(analysis)

        # Node should be unresolved (no properties, not in global table, no heuristic match)
        assert len(resolution.nodes_unresolved) == 1
        unresolved_node = resolution.nodes_unresolved[0]
        assert unresolved_node.type == "Mute / Bypass Repeater (rgthree)"

        # SIMULATE INTERACTIVE: User selects rgthree-comfy
        # This simulates what fix_resolution() does with InteractiveNodeStrategy
        mock_package = GlobalNodePackage(
            id="rgthree-comfy",
            display_name="rgthree-comfy",
            description="Making ComfyUI more comfortable.",
            author="rgthree",
            repository="https://github.com/rgthree/rgthree-comfy",
            downloads=None,
            github_stars=None,
            rating=None,
            license=None,
            category=None,
            tags=None,
            status=None,
            created_at=None,
            versions=None,
        )

        user_resolved = ResolvedNodePackage(
            package_id="rgthree-comfy",
            package_data=mock_package,
            node_type="Mute / Bypass Repeater (rgthree)",
            versions=[],
            match_type="user_confirmed",  # This is what InteractiveNodeStrategy actually uses
            match_confidence=1.0
        )

        # Add to resolution manually (simulating fix_resolution)
        resolution.nodes_resolved.append(user_resolved)
        resolution.nodes_unresolved.remove(unresolved_node)

        # Apply resolution (this is where the bug is - it doesn't save custom mapping)
        test_env.workflow_manager.apply_resolution(resolution, "rgthree_test")

        # ASSERT: Check if custom mapping was saved
        mappings = test_env.pyproject.node_mappings.get_all_mappings()

        # THIS WILL FAIL - demonstrating the bug
        assert "Mute / Bypass Repeater (rgthree)" in mappings, \
            "Custom mapping should be saved after interactive resolution"
        assert mappings["Mute / Bypass Repeater (rgthree)"] == "rgthree-comfy", \
            "Mapping should point to user's selected package"

    def test_second_resolution_reuses_custom_mapping(self, test_env):
        """After saving custom mapping, second workflow with same node auto-resolves.

        This is the desired behavior once the bug is fixed:
        1. User resolves node once → mapping saved
        2. Another workflow has same node type → auto-resolves from mapping
        3. No more prompts for the same node!
        """
        # ARRANGE: First manually add the custom mapping (simulating previous resolution)
        test_env.pyproject.node_mappings.add_mapping(
            "Fast Bypasser (rgthree)",
            "rgthree-comfy"
        )

        # Create workflow with the same node type
        workflow_data = {
            "nodes": [
                {
                    "id": "1",
                    "type": "Fast Bypasser (rgthree)",
                    "pos": [100, 100],
                    "size": [200, 100],
                    "flags": {},
                    "order": 0,
                    "mode": 0,
                    "inputs": [],
                    "outputs": [],
                    "properties": {},  # No cnr_id
                    "widgets_values": []
                }
            ],
            "links": [],
            "groups": [],
            "config": {},
            "extra": {},
            "version": 0.4
        }

        simulate_comfyui_save_workflow(test_env, "second_workflow", workflow_data)

        # ACT: Analyze and resolve
        analysis = test_env.workflow_manager.analyze_workflow("second_workflow")
        resolution = test_env.workflow_manager.resolve_workflow(analysis)

        # ASSERT: Should auto-resolve from custom mapping (Priority 2)
        assert len(resolution.nodes_resolved) == 1, "Should resolve from custom mapping"
        resolved = resolution.nodes_resolved[0]
        assert resolved.package_id == "rgthree-comfy"
        assert resolved.match_type == "custom_mapping"
        assert len(resolution.nodes_unresolved) == 0, "No interactive needed!"


class TestCustomMappingWithSkip:
    """Test that users can mark nodes to skip via custom mapping."""

    def test_skip_mapping_prevents_resolution(self, test_env):
        """User can map a node type to 'skip' to ignore it permanently."""
        # ARRANGE: Add skip mapping
        test_env.pyproject.node_mappings.add_mapping(
            "IgnoredNode",
            "skip"
        )

        workflow_data = {
            "nodes": [
                {
                    "id": "1",
                    "type": "IgnoredNode",
                    "pos": [100, 100],
                    "size": [200, 100],
                    "flags": {},
                    "order": 0,
                    "mode": 0,
                    "inputs": [],
                    "outputs": [],
                    "properties": {},
                    "widgets_values": []
                }
            ],
            "links": [],
            "groups": [],
            "config": {},
            "extra": {},
            "version": 0.4
        }

        simulate_comfyui_save_workflow(test_env, "skip_test", workflow_data)

        # ACT: Resolve
        analysis = test_env.workflow_manager.analyze_workflow("skip_test")
        resolution = test_env.workflow_manager.resolve_workflow(analysis)

        # ASSERT: Should return empty list (not unresolved, not resolved - skipped!)
        assert len(resolution.nodes_resolved) == 0, "Skipped nodes not in resolved"
        assert len(resolution.nodes_unresolved) == 0, "Skipped nodes not in unresolved"
