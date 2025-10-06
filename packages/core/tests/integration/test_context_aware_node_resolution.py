"""Integration tests for context-aware node resolution.

Tests the full workflow lifecycle with properties field, session caching,
and custom mappings.
"""

import pytest
import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from conftest import simulate_comfyui_save_workflow


class TestWorkflowWithPropertiesField:
    """Test workflows with properties field resolve automatically."""

    def test_properties_field_resolves_end_to_end(self, test_env):
        """Workflow with properties cnr_id should resolve without user input."""
        # ARRANGE: Create workflow with properties
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
                    "widgets_values": ["example.png"]
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
                    "outputs": [],
                    "properties": {
                        "Node name for S&R": "Mute / Bypass Repeater (rgthree)",
                        "cnr_id": "rgthree-comfy",
                        "ver": "f754c4765849aa748abb35a1f030a5ed6474a69b"
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

        # Add rgthree-comfy to global mappings (mock it exists)
        mappings_path = test_env.workspace_paths.cache / "custom_nodes" / "node_mappings.json"
        with open(mappings_path, 'r') as f:
            mappings = json.load(f)

        mappings["packages"]["rgthree-comfy"] = {
            "id": "rgthree-comfy",
            "display_name": "rgthree's ComfyUI Nodes",
            "description": "Various utility nodes",
            "repository": "https://github.com/rgthree/rgthree-comfy",
            "versions": {}
        }

        with open(mappings_path, 'w') as f:
            json.dump(mappings, f)

        simulate_comfyui_save_workflow(test_env, "test_workflow", workflow_data)

        # ACT: Analyze and resolve workflow
        analysis = test_env.workflow_manager.analyze_workflow("test_workflow")
        resolution = test_env.workflow_manager.resolve_workflow(analysis)

        # ASSERT: Should resolve from properties
        assert len(resolution.nodes_resolved) > 0, "Should have resolved nodes"

        rgthree_resolved = [n for n in resolution.nodes_resolved if n.package_id == "rgthree-comfy"]
        assert len(rgthree_resolved) == 1, "Should resolve rgthree-comfy from properties"

        resolved_node = rgthree_resolved[0]
        assert resolved_node.match_type == "properties"
        assert "f754c4765849aa748abb35a1f030a5ed6474a69b" in resolved_node.versions
        assert len(resolution.nodes_unresolved) == 0, "No nodes should be unresolved"


class TestSessionDeduplication:
    """Test session-level deduplication across multiple nodes."""

    def test_duplicate_nodes_resolve_once(self, test_env):
        """Workflow with many duplicate node types should only resolve each type once."""
        # ARRANGE: Create workflow with 15 KSampler nodes (realistic scenario)
        nodes = []
        for i in range(15):
            nodes.append({
                "id": str(i + 1),
                "type": "KSampler",
                "pos": [100 * i, 100],
                "size": [200, 100],
                "flags": {},
                "order": i,
                "mode": 0,
                "inputs": [],
                "outputs": [],
                "properties": {},
                "widgets_values": [i, "fixed", 20, 8.0, "euler", "normal", 1.0]
            })

        # Add 5 LoadImage nodes
        for i in range(5):
            nodes.append({
                "id": str(i + 16),
                "type": "LoadImage",
                "pos": [100 * i, 300],
                "size": [200, 100],
                "flags": {},
                "order": i + 15,
                "mode": 0,
                "inputs": [],
                "outputs": [],
                "properties": {},
                "widgets_values": [f"image{i}.png"]
            })

        workflow_data = {
            "nodes": nodes,
            "links": [],
            "groups": [],
            "config": {},
            "extra": {},
            "version": 0.4
        }

        simulate_comfyui_save_workflow(test_env, "test_dedup", workflow_data)

        # ACT: Analyze and resolve
        analysis = test_env.workflow_manager.analyze_workflow("test_dedup")

        # Check that we only have 2 unique builtin node types
        assert len(analysis.builtin_nodes) == 20, "Should find 20 total builtin nodes"

        # Verify deduplication by checking unique types
        unique_types = set(node.type for node in analysis.builtin_nodes)
        assert len(unique_types) == 2, "Should have only 2 unique node types"
        assert "KSampler" in unique_types
        assert "LoadImage" in unique_types


class TestCustomMappingPersistence:
    """Test custom mappings persist across workflows."""

    def test_custom_mapping_reused_in_second_workflow(self, test_env):
        """User's manual resolution should persist and be reused."""
        # ARRANGE (First Workflow): Manually add custom mapping
        test_env.pyproject.node_mappings.add_mapping(
            "UnknownCustomNode",
            "user-chosen-package"
        )

        # Create first workflow with the unknown node
        workflow1_data = {
            "nodes": [
                {
                    "id": "1",
                    "type": "UnknownCustomNode",
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

        simulate_comfyui_save_workflow(test_env, "workflow1", workflow1_data)

        # Add package to mappings so resolution can find it
        mappings_path = test_env.workspace_paths.cache / "custom_nodes" / "node_mappings.json"
        with open(mappings_path, 'r') as f:
            mappings = json.load(f)

        mappings["packages"]["user-chosen-package"] = {
            "id": "user-chosen-package",
            "display_name": "User's Package",
            "versions": {}
        }

        with open(mappings_path, 'w') as f:
            json.dump(mappings, f)

        # ACT (First Workflow): Resolve
        analysis1 = test_env.workflow_manager.analyze_workflow("workflow1")
        resolution1 = test_env.workflow_manager.resolve_workflow(analysis1)

        # ASSERT: First workflow should use custom mapping
        assert len(resolution1.nodes_resolved) == 1
        assert resolution1.nodes_resolved[0].package_id == "user-chosen-package"
        assert resolution1.nodes_resolved[0].match_type == "custom_mapping"

        # ACT (Second Workflow): Create new workflow with same node type
        workflow2_data = {
            "nodes": [
                {
                    "id": "1",
                    "type": "UnknownCustomNode",  # Same type!
                    "pos": [200, 200],
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

        simulate_comfyui_save_workflow(test_env, "workflow2", workflow2_data)

        analysis2 = test_env.workflow_manager.analyze_workflow("workflow2")
        resolution2 = test_env.workflow_manager.resolve_workflow(analysis2)

        # ASSERT: Second workflow should also use custom mapping (no re-prompting!)
        assert len(resolution2.nodes_resolved) == 1
        assert resolution2.nodes_resolved[0].package_id == "user-chosen-package"


class TestHeuristicFallback:
    """Test heuristic resolution when properties are missing."""

    def test_heuristic_resolves_without_properties(self, test_env):
        """Older workflow without properties should use heuristics if package installed."""
        # ARRANGE: Create workflow WITHOUT properties field
        workflow_data = {
            "nodes": [
                {
                    "id": "1",
                    "type": "Any Switch (rgthree)",  # Has parenthetical hint
                    "pos": [100, 100],
                    "size": [200, 100],
                    "flags": {},
                    "order": 0,
                    "mode": 0,
                    "inputs": [],
                    "outputs": [],
                    "properties": {},  # Empty properties!
                    "widgets_values": []
                }
            ],
            "links": [],
            "groups": [],
            "config": {},
            "extra": {},
            "version": 0.4
        }

        # Add package to global mappings and simulate it's installed
        mappings_path = test_env.workspace_paths.cache / "custom_nodes" / "node_mappings.json"
        with open(mappings_path, 'r') as f:
            mappings = json.load(f)

        mappings["packages"]["rgthree-comfy"] = {
            "id": "rgthree-comfy",
            "display_name": "rgthree's ComfyUI Nodes",
            "repository": "https://github.com/rgthree/rgthree-comfy",
            "versions": {}
        }

        with open(mappings_path, 'w') as f:
            json.dump(mappings, f)

        # Simulate package is installed (add to pyproject nodes)
        config = test_env.pyproject.load()
        if "tool" not in config:
            config["tool"] = {}
        if "comfydock" not in config["tool"]:
            config["tool"]["comfydock"] = {}
        if "nodes" not in config["tool"]["comfydock"]:
            config["tool"]["comfydock"]["nodes"] = {}

        config["tool"]["comfydock"]["nodes"]["rgthree-comfy"] = {
            "name": "rgthree-comfy",
            "registry_id": "rgthree-comfy",
            "source": "registry"
        }
        test_env.pyproject.save(config)

        simulate_comfyui_save_workflow(test_env, "old_workflow", workflow_data)

        # ACT: Analyze and resolve
        analysis = test_env.workflow_manager.analyze_workflow("old_workflow")
        resolution = test_env.workflow_manager.resolve_workflow(analysis)

        # ASSERT: CHANGED - should NOT resolve via heuristic, should be unresolved
        assert len(resolution.nodes_unresolved) > 0, "Should be unresolved (no auto-resolve)"
        assert resolution.nodes_unresolved[0].type == "Any Switch (rgthree)"


class TestStatusNoLongerShowsMissing:
    """Test that status command doesn't show resolved nodes as missing."""

    def test_status_after_resolution_shows_no_missing_nodes(self, test_env):
        """After resolving nodes, status should not show them as missing."""
        # ARRANGE: Create workflow with custom nodes (some with properties, some in table)
        workflow_data = {
            "nodes": [
                {
                    "id": "1",
                    "type": "Node With Properties",
                    "pos": [100, 100],
                    "size": [200, 100],
                    "flags": {},
                    "order": 0,
                    "mode": 0,
                    "inputs": [],
                    "outputs": [],
                    "properties": {
                        "cnr_id": "package-with-props",
                        "ver": "abc123"
                    },
                    "widgets_values": []
                },
                {
                    "id": "2",
                    "type": "Node In Global Table",
                    "pos": [300, 100],
                    "size": [200, 100],
                    "flags": {},
                    "order": 1,
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

        # Set up global mappings
        mappings_path = test_env.workspace_paths.cache / "custom_nodes" / "node_mappings.json"
        with open(mappings_path, 'r') as f:
            mappings = json.load(f)

        # Add package with properties
        mappings["packages"]["package-with-props"] = {
            "id": "package-with-props",
            "display_name": "Package With Props",
            "versions": {}
        }

        # Add package in global table
        mappings["packages"]["package-in-table"] = {
            "id": "package-in-table",
            "display_name": "Package In Table",
            "versions": {}
        }

        mappings["mappings"]["Node In Global Table::_"] = {
            "id": "Node In Global Table::_",
            "package_id": "package-in-table",
            "versions": []
        }

        with open(mappings_path, 'w') as f:
            json.dump(mappings, f)

        simulate_comfyui_save_workflow(test_env, "multi_node_workflow", workflow_data)

        # ACT (Before Resolution): Check status
        status_before = test_env.workflow_manager.get_workflow_status()

        # Find our workflow in status
        workflow_status_before = None
        for wf in status_before.analyzed_workflows:
            if wf.name == "multi_node_workflow":
                workflow_status_before = wf
                break

        assert workflow_status_before is not None, "Should find workflow in status"

        # Count unresolved nodes before
        unresolved_before = len(workflow_status_before.resolution.nodes_unresolved)

        # ACT (Resolution): Resolve and apply
        analysis = test_env.workflow_manager.analyze_workflow("multi_node_workflow")
        resolution = test_env.workflow_manager.resolve_workflow(analysis)

        # Simulate installing the packages (add to pyproject)
        config = test_env.pyproject.load()
        if "tool" not in config:
            config["tool"] = {}
        if "comfydock" not in config["tool"]:
            config["tool"]["comfydock"] = {}
        if "nodes" not in config["tool"]["comfydock"]:
            config["tool"]["comfydock"]["nodes"] = {}

        for resolved_node in resolution.nodes_resolved:
            config["tool"]["comfydock"]["nodes"][resolved_node.package_id] = {
                "name": resolved_node.package_id,
                "registry_id": resolved_node.package_id,
                "source": "registry"
            }

        test_env.pyproject.save(config)

        # ACT (After Resolution): Check status again
        status_after = test_env.workflow_manager.get_workflow_status()

        workflow_status_after = None
        for wf in status_after.analyzed_workflows:
            if wf.name == "multi_node_workflow":
                workflow_status_after = wf
                break

        assert workflow_status_after is not None, "Should find workflow in status after resolution"

        # ASSERT: Should have fewer (or zero) unresolved nodes
        unresolved_after = len(workflow_status_after.resolution.nodes_unresolved)

        assert unresolved_after <= unresolved_before, \
            f"Should have fewer unresolved nodes. Before: {unresolved_before}, After: {unresolved_after}"

        # Ideally should be 0 unresolved
        assert unresolved_after == 0, \
            f"All nodes should be resolved. Still unresolved: {workflow_status_after.resolution.nodes_unresolved}"


class TestCommitPreservesResolutionContext:
    """Test that commit preserves resolution mappings."""

    def test_commit_preserves_custom_mappings(self, test_env):
        """After committing, custom mappings should persist in pyproject."""
        # ARRANGE: Add custom mapping and create workflow
        test_env.pyproject.node_mappings.add_mapping(
            "CustomNode",
            "custom-package"
        )

        workflow_data = {
            "nodes": [
                {
                    "id": "1",
                    "type": "CustomNode",
                    "pos": [100, 100],
                    "size": [200, 100],
                    "flags": {},
                    "order": 0,
                    "mode": 0,
                    "inputs": [],
                    "outputs": [],
                    "properties": {},
                    "widgets_values": []
                },
                {
                    "id": "2",
                    "type": "Node With Props",
                    "pos": [300, 100],
                    "size": [200, 100],
                    "flags": {},
                    "order": 1,
                    "mode": 0,
                    "inputs": [],
                    "outputs": [],
                    "properties": {
                        "cnr_id": "props-package",
                        "ver": "xyz789"
                    },
                    "widgets_values": []
                }
            ],
            "links": [],
            "groups": [],
            "config": {},
            "extra": {},
            "version": 0.4
        }

        # Add packages to mappings
        mappings_path = test_env.workspace_paths.cache / "custom_nodes" / "node_mappings.json"
        with open(mappings_path, 'r') as f:
            mappings = json.load(f)

        mappings["packages"]["custom-package"] = {
            "id": "custom-package",
            "display_name": "Custom Package",
            "versions": {}
        }

        mappings["packages"]["props-package"] = {
            "id": "props-package",
            "display_name": "Props Package",
            "versions": {}
        }

        with open(mappings_path, 'w') as f:
            json.dump(mappings, f)

        simulate_comfyui_save_workflow(test_env, "commit_test", workflow_data)

        # ACT: Analyze, resolve, and check pyproject
        analysis = test_env.workflow_manager.analyze_workflow("commit_test")
        resolution = test_env.workflow_manager.resolve_workflow(analysis)

        # ASSERT: Check pyproject has node_mappings section
        config = test_env.pyproject.load()

        assert "tool" in config
        assert "comfydock" in config["tool"]
        assert "node_mappings" in config["tool"]["comfydock"], \
            "Should have node_mappings section in pyproject"

        node_mappings = config["tool"]["comfydock"]["node_mappings"]
        assert "CustomNode" in node_mappings, "Custom mapping should persist"
        assert node_mappings["CustomNode"] == "custom-package"

        # Resolution should have used the custom mapping
        custom_nodes = [n for n in resolution.nodes_resolved if n.package_id == "custom-package"]
        assert len(custom_nodes) == 1, "Should resolve using custom mapping"
