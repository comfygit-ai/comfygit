"""Integration tests for unified search with user confirmation flow.

Tests the complete flow:
1. Node not in registry/properties → unified search
2. User sees ranked results
3. User confirms choice
4. Choice saved to custom mappings
5. Second workflow auto-resolves via mapping
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from comfydock_core.core.workspace import Workspace
from comfydock_core.factories.workspace_factory import WorkspaceFactory
from comfydock_core.models.shared import NodeInfo


def create_minimal_workflow(name: str, node_type: str, has_properties: bool = False):
    """Helper to create simple workflow JSON."""
    workflow = {
        "nodes": [
            {
                "id": "1",
                "type": node_type,
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

    if has_properties:
        workflow["nodes"][0]["properties"] = {
            "cnr_id": "test-package",
            "ver": "abc123"
        }

    return workflow


def simulate_comfyui_save_workflow(env, name: str, workflow_data: dict):
    """Simulate ComfyUI saving a workflow to disk."""
    workflows_dir = env.paths.comfyui_root / "user" / "default" / "workflows"
    workflows_dir.mkdir(parents=True, exist_ok=True)

    workflow_file = workflows_dir / f"{name}.json"
    with open(workflow_file, 'w') as f:
        json.dump(workflow_data, f, indent=2)


class TestUnifiedSearchTriggersInteractive:
    """Test that unified search is used when no auto-resolution possible."""

    def test_node_without_properties_triggers_search(self, tmp_path):
        """Node without properties/global table match should trigger search (return None)."""
        # ARRANGE: Create workspace and environment
        workspace_path = tmp_path / "workspace"
        factory = WorkspaceFactory(workspace_path)
        workspace = factory.create()

        env = workspace.create_environment("test", python_version="3.11")

        # Create global mappings with a package
        mappings_file = tmp_path / "node_mappings.json"
        global_data = {
            "version": "test",
            "generated_at": "2024-01-01",
            "stats": {},
            "mappings": {},  # Node NOT in mappings table
            "packages": {
                "test-package": {
                    "id": "test-package",
                    "display_name": "Test Package",
                    "description": "Test description",
                    "versions": {}
                }
            }
        }

        with open(mappings_file, 'w') as f:
            json.dump(global_data, f)

        # Override resolver to use test mappings
        from comfydock_core.resolvers.global_node_resolver import GlobalNodeResolver
        env.workflow_manager.global_node_resolver = GlobalNodeResolver(mappings_file)

        # Create workflow with node that has hint but no properties
        workflow_data = create_minimal_workflow(
            "test_workflow",
            "Custom Node (test)",  # Hint in name
            has_properties=False
        )
        simulate_comfyui_save_workflow(env, "test_workflow", workflow_data)

        # ACT: Analyze and resolve workflow
        analysis = env.workflow_manager.analyze_workflow("test_workflow")
        resolution = env.workflow_manager.resolve_workflow(analysis)

        # ASSERT: Should NOT auto-resolve via heuristic
        # Node should be in unresolved list (triggers interactive)
        assert len(resolution.nodes_unresolved) == 1, \
            "Node with hint should NOT auto-resolve, should be unresolved"
        assert resolution.nodes_unresolved[0].type == "Custom Node (test)"

    def test_search_packages_returns_ranked_results(self, tmp_path):
        """search_packages should return ranked results for interactive display."""
        # ARRANGE
        workspace_path = tmp_path / "workspace"
        factory = WorkspaceFactory(workspace_path)
        workspace = factory.create()
        env = workspace.create_environment("test", python_version="3.11")

        mappings_file = tmp_path / "node_mappings.json"
        global_data = {
            "version": "test",
            "generated_at": "2024-01-01",
            "stats": {},
            "mappings": {},
            "packages": {
                "target-package": {
                    "id": "target-package",
                    "display_name": "Target Package",
                    "description": "Matches the hint",
                    "versions": {}
                },
                "other-package": {
                    "id": "other-package",
                    "display_name": "Other Package",
                    "description": "Different package",
                    "versions": {}
                }
            }
        }

        with open(mappings_file, 'w') as f:
            json.dump(global_data, f)

        from comfydock_core.resolvers.global_node_resolver import GlobalNodeResolver
        resolver = GlobalNodeResolver(mappings_file)

        # ACT: Call search_packages directly
        results = resolver.search_packages(
            node_type="Some Node (target)",
            installed_packages=None,
            include_registry=True,
            limit=10
        )

        # ASSERT: Should return ranked results
        assert len(results) > 0, "Should find matches"
        assert results[0].package_id == "target-package", "Should rank hint match first"
        assert hasattr(results[0], 'score'), "Should have score attribute"
        assert hasattr(results[0], 'confidence'), "Should have confidence attribute"


class TestCustomMappingPersistence:
    """Test that user-confirmed choices persist to custom mappings."""

    def test_custom_mapping_created_after_user_choice(self, tmp_path):
        """After user confirms a package, it should save to custom mappings."""
        # ARRANGE
        workspace_path = tmp_path / "workspace"
        factory = WorkspaceFactory(workspace_path)
        workspace = factory.create()
        env = workspace.create_environment("test", python_version="3.11")

        # ACT: Manually create a custom mapping (simulating user confirmation)
        env.pyproject.node_mappings.add_mapping(
            node_type="Custom Node (hint)",
            package_id="chosen-package"
        )

        # ASSERT: Should be persisted in pyproject.toml
        all_mappings = env.pyproject.node_mappings.get_all_mappings()
        assert "Custom Node (hint)" in all_mappings
        assert all_mappings["Custom Node (hint)"] == "chosen-package"

    def test_custom_mapping_reused_in_second_workflow(self, tmp_path):
        """Second workflow with same node type should auto-resolve via custom mapping."""
        # ARRANGE
        workspace_path = tmp_path / "workspace"
        factory = WorkspaceFactory(workspace_path)
        workspace = factory.create()
        env = workspace.create_environment("test", python_version="3.11")

        # Create global mappings
        mappings_file = tmp_path / "node_mappings.json"
        global_data = {
            "version": "test",
            "generated_at": "2024-01-01",
            "stats": {},
            "mappings": {},
            "packages": {
                "custom-pkg": {
                    "id": "custom-pkg",
                    "display_name": "Custom Package",
                    "versions": {}
                }
            }
        }

        with open(mappings_file, 'w') as f:
            json.dump(global_data, f)

        from comfydock_core.resolvers.global_node_resolver import GlobalNodeResolver
        env.workflow_manager.global_node_resolver = GlobalNodeResolver(mappings_file)

        # Simulate user confirmed "Custom Node" → "custom-pkg" in first workflow
        env.pyproject.node_mappings.add_mapping(
            node_type="Custom Node",
            package_id="custom-pkg"
        )

        # Create second workflow with same node type
        workflow_data = create_minimal_workflow("workflow2", "Custom Node")
        simulate_comfyui_save_workflow(env, "workflow2", workflow_data)

        # ACT: Resolve second workflow
        analysis = env.workflow_manager.analyze_workflow("workflow2")
        resolution = env.workflow_manager.resolve_workflow(analysis)

        # ASSERT: Should auto-resolve via custom mapping (Priority 2)
        assert len(resolution.nodes_resolved) == 1, "Should auto-resolve via custom mapping"
        assert resolution.nodes_resolved[0].package_id == "custom-pkg"
        assert resolution.nodes_resolved[0].match_type == "custom_mapping"

    def test_skip_mapping_persists(self, tmp_path):
        """User choosing 'skip' should save skip mapping."""
        # ARRANGE
        workspace_path = tmp_path / "workspace"
        factory = WorkspaceFactory(workspace_path)
        workspace = factory.create()
        env = workspace.create_environment("test", python_version="3.11")

        # ACT: User chooses to skip this node
        env.pyproject.node_mappings.add_mapping(
            node_type="SkippedNode",
            package_id="skip"
        )

        # Create workflow with skipped node
        workflow_data = create_minimal_workflow("workflow_skip", "SkippedNode")
        simulate_comfyui_save_workflow(env, "workflow_skip", workflow_data)

        # Create minimal global mappings
        mappings_file = tmp_path / "node_mappings.json"
        global_data = {
            "version": "test",
            "generated_at": "2024-01-01",
            "stats": {},
            "mappings": {},
            "packages": {}
        }

        with open(mappings_file, 'w') as f:
            json.dump(global_data, f)

        from comfydock_core.resolvers.global_node_resolver import GlobalNodeResolver
        env.workflow_manager.global_node_resolver = GlobalNodeResolver(mappings_file)

        analysis = env.workflow_manager.analyze_workflow("workflow_skip")
        resolution = env.workflow_manager.resolve_workflow(analysis)

        # ASSERT: Should be skipped (not in resolved or unresolved)
        assert len(resolution.nodes_resolved) == 0, "Skipped nodes shouldn't be in resolved"
        assert len(resolution.nodes_unresolved) == 0, "Skipped nodes shouldn't be in unresolved"


class TestPrioritiesUnchanged:
    """Test that priorities 1-4 still work after refactor."""

    def test_priority_1_session_cache_still_works(self, tmp_path):
        """Session cache should still auto-resolve."""
        # ARRANGE
        workspace_path = tmp_path / "workspace"
        factory = WorkspaceFactory(workspace_path)
        workspace = factory.create()
        env = workspace.create_environment("test", python_version="3.11")

        mappings_file = tmp_path / "node_mappings.json"
        global_data = {
            "version": "test",
            "generated_at": "2024-01-01",
            "stats": {},
            "mappings": {
                "TestNode": ["test-package"]
            },
            "packages": {
                "test-package": {
                    "id": "test-package",
                    "display_name": "Test Package",
                    "versions": {}
                }
            }
        }

        with open(mappings_file, 'w') as f:
            json.dump(global_data, f)

        from comfydock_core.resolvers.global_node_resolver import GlobalNodeResolver
        env.workflow_manager.global_node_resolver = GlobalNodeResolver(mappings_file)

        # Create workflow with duplicate node types
        workflow_data = {
            "nodes": [
                {
                    "id": "1",
                    "type": "TestNode",
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
                    "type": "TestNode",  # Duplicate
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

        simulate_comfyui_save_workflow(env, "test_dedup", workflow_data)

        # ACT
        analysis = env.workflow_manager.analyze_workflow("test_dedup")
        resolution = env.workflow_manager.resolve_workflow(analysis)

        # ASSERT: Should resolve once (deduplication via session cache)
        assert len(resolution.nodes_resolved) == 1, "Should dedupe via session cache"

    def test_priority_3_properties_field_still_works(self, tmp_path):
        """Properties field should still auto-resolve."""
        # ARRANGE
        workspace_path = tmp_path / "workspace"
        factory = WorkspaceFactory(workspace_path)
        workspace = factory.create()
        env = workspace.create_environment("test", python_version="3.11")

        mappings_file = tmp_path / "node_mappings.json"
        global_data = {
            "version": "test",
            "generated_at": "2024-01-01",
            "stats": {},
            "mappings": {},
            "packages": {
                "rgthree-comfy": {
                    "id": "rgthree-comfy",
                    "display_name": "rgthree's Nodes",
                    "versions": {}
                }
            }
        }

        with open(mappings_file, 'w') as f:
            json.dump(global_data, f)

        from comfydock_core.resolvers.global_node_resolver import GlobalNodeResolver
        env.workflow_manager.global_node_resolver = GlobalNodeResolver(mappings_file)

        # Create workflow with properties field
        workflow_data = {
            "nodes": [
                {
                    "id": "1",
                    "type": "Mute / Bypass Repeater (rgthree)",
                    "pos": [100, 100],
                    "size": [200, 100],
                    "flags": {},
                    "order": 0,
                    "mode": 0,
                    "inputs": [],
                    "outputs": [],
                    "properties": {
                        "cnr_id": "rgthree-comfy",  # Properties field!
                        "ver": "abc123"
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

        simulate_comfyui_save_workflow(env, "test_properties", workflow_data)

        # ACT
        analysis = env.workflow_manager.analyze_workflow("test_properties")
        resolution = env.workflow_manager.resolve_workflow(analysis)

        # ASSERT: Should auto-resolve via properties
        assert len(resolution.nodes_resolved) == 1, "Should auto-resolve via properties"
        assert resolution.nodes_resolved[0].package_id == "rgthree-comfy"
        assert resolution.nodes_resolved[0].match_type == "properties"
