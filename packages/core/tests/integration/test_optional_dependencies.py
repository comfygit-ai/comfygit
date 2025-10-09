"""Integration tests for Phase 2: Optional Dependency Support.

Tests the ability to mark models and nodes as "optional" to handle:
- Type 1: Unresolved optional models (custom node-managed, e.g., rife49.pth)
- Type 2: Nice-to-have optional models (in index but not required)
- Optional nodes (custom node types)

Following TDD approach - these tests should FAIL initially.
"""

import pytest
import json
from pathlib import Path
import sys

# Import helpers
sys.path.insert(0, str(Path(__file__).parent.parent))
from conftest import simulate_comfyui_save_workflow, load_workflow_fixture


class TestOptionalModels:
    """Tests for optional model support (Type 1 and Type 2)."""

    def test_type1_optional_model_unresolved(self, test_env, test_models, workflow_fixtures):
        """
        Test marking a missing model as Type 1 optional (unresolved).

        Expected behavior:
        - User can mark missing model as optional
        - Model stored in [tool.comfydock.models.optional] with filename key
        - Entry has {unresolved = true}
        - Workflow mapping uses filename as key
        - Workflow JSON NOT updated (preserves original filename)
        - Workflow resolution counts as complete (no blocking issues)
        """
        # ARRANGE - Load workflow with missing model
        workflow = load_workflow_fixture(workflow_fixtures, "with_missing_model")
        simulate_comfyui_save_workflow(test_env, "test_workflow", workflow)

        # Get initial status
        status = test_env.workflow_manager.get_workflow_status()
        assert len(status.analyzed_workflows) == 1
        workflow_status = status.analyzed_workflows[0]

        # Verify model is unresolved initially
        assert len(workflow_status.resolution.models_unresolved) > 0, \
            "Test fixture should have at least one missing model"

        # ACT - Simulate user marking model as optional (Type 1: unresolved)
        # Create a mock strategy that returns "optional_unresolved"
        from comfydock_core.models.protocols import ModelResolutionStrategy
        from comfydock_core.models.workflow import WorkflowNodeWidgetRef
        from comfydock_core.models.shared import ModelWithLocation
        from typing import List

        class MockOptionalStrategy(ModelResolutionStrategy):
            def handle_missing_model(self, reference: WorkflowNodeWidgetRef) -> tuple[str, str] | None:
                # User marks as Type 1 optional (unresolved)
                return ("optional_unresolved", "")

            def resolve_ambiguous_model(
                self, reference: WorkflowNodeWidgetRef, candidates: List[ModelWithLocation]
            ) -> ModelWithLocation | None:
                return None

        # Fix resolution with optional strategy
        resolution = test_env.workflow_manager.fix_resolution(
            resolution=workflow_status.resolution,
            model_strategy=MockOptionalStrategy()
        )

        # Apply resolution
        test_env.workflow_manager.apply_resolution(
            resolution=resolution,
            workflow_name="test_workflow",
            model_refs=workflow_status.dependencies.found_models
        )

        # ASSERT - Verify Type 1 optional model handling
        pyproject = test_env.pyproject

        # 1. Model should be in models.optional section
        optional_models = pyproject.models.get_category("optional")
        assert len(optional_models) > 0, \
            "Should have at least one optional model"

        # 2. Should be stored with filename as key (not hash)
        missing_model_filename = workflow_status.resolution.models_unresolved[0].widget_value
        assert missing_model_filename in optional_models, \
            f"Optional model '{missing_model_filename}' should use filename as key"

        # 3. Should have unresolved flag
        optional_entry = optional_models[missing_model_filename]
        assert optional_entry.get("unresolved") is True, \
            "Type 1 optional models should have unresolved=true"

        # 4. Should have minimal data (no size, no relative_path with substance)
        assert optional_entry.get("filename") == missing_model_filename

        # 5. Workflow mapping should use filename as key
        workflow_mappings = pyproject.workflows.get_model_resolutions("test_workflow")
        assert missing_model_filename in workflow_mappings, \
            "Workflow should reference optional model by filename"

        # 6. Workflow JSON should NOT be updated (preserve original)
        workflow_path = test_env.comfyui_path / "user/default/workflows/test_workflow.json"
        with open(workflow_path) as f:
            workflow_json = json.load(f)

        # Find the node with the missing model (workflows use list, need to find by id)
        ref = workflow_status.resolution.models_unresolved[0]
        node = next((n for n in workflow_json["nodes"] if n["id"] == int(ref.node_id)), None)
        assert node is not None, f"Node {ref.node_id} should exist in workflow"
        assert node["widgets_values"][ref.widget_index] == missing_model_filename, \
            "Workflow JSON should preserve original filename for Type 1 optional models"

        # 7. Resolution should be complete (no unresolved issues)
        assert len(resolution.models_unresolved) == 0, \
            "After marking as optional, should have no unresolved models"

    def test_type2_optional_model_nice_to_have(self, test_env, test_models, workflow_fixtures):
        """
        Test marking an ambiguous model as Type 2 optional (nice-to-have).

        Expected behavior:
        - User can mark ambiguous model selection as optional
        - Model stored in [tool.comfydock.models.optional] with hash key
        - Entry has full metadata (size, relative_path, etc.)
        - Workflow mapping uses hash as key
        - Workflow JSON IS updated with resolved path
        - Workflow resolution counts as complete
        """
        # ARRANGE - Create workflow with ambiguous model reference
        # (This will require creating a fixture or modifying existing one)
        workflow = load_workflow_fixture(workflow_fixtures, "simple_txt2img")

        # Modify to have a more generic filename that might match multiple models
        # For testing, we'll create a scenario where we have multiple candidates
        workflow_json = workflow.copy()

        # Change model reference to something that might be ambiguous
        for node in workflow_json["nodes"]:
            if node["type"] == "CheckpointLoaderSimple":
                node["widgets_values"][0] = "test_model.safetensors"  # Generic name
                break

        simulate_comfyui_save_workflow(test_env, "test_workflow", workflow_json)

        # Get status
        status = test_env.workflow_manager.get_workflow_status()
        workflow_status = status.analyzed_workflows[0]

        # Skip test if no ambiguous models (test setup issue)
        if len(workflow_status.resolution.models_ambiguous) == 0:
            pytest.skip("Test requires ambiguous model scenario")

        # ACT - Simulate user selecting model and marking as Type 2 optional
        from comfydock_core.models.protocols import ModelResolutionStrategy
        from comfydock_core.models.workflow import WorkflowNodeWidgetRef
        from comfydock_core.models.shared import ModelWithLocation
        from typing import List

        class MockOptionalNiceToHaveStrategy(ModelResolutionStrategy):
            def handle_missing_model(self, reference: WorkflowNodeWidgetRef) -> tuple[str, str] | None:
                return None

            def resolve_ambiguous_model(
                self, reference: WorkflowNodeWidgetRef, candidates: List[ModelWithLocation]
            ) -> ModelWithLocation | None:
                # User selects first candidate and marks as optional (Type 2)
                selected = candidates[0]
                selected._mark_as_optional = True
                return selected

        resolution = test_env.workflow_manager.fix_resolution(
            resolution=workflow_status.resolution,
            model_strategy=MockOptionalNiceToHaveStrategy()
        )

        test_env.workflow_manager.apply_resolution(
            resolution=resolution,
            workflow_name="test_workflow",
            model_refs=workflow_status.dependencies.found_models
        )

        # ASSERT - Verify Type 2 optional model handling
        pyproject = test_env.pyproject

        # 1. Model should be in models.optional section (not required)
        optional_models = pyproject.models.get_category("optional")
        assert len(optional_models) > 0, \
            "Should have at least one optional model"

        # 2. Should be stored with hash as key (like required models)
        model_hashes = list(optional_models.keys())
        assert len(model_hashes[0]) > 10, \
            "Type 2 optional models should use hash as key (not filename)"

        # 3. Should have full metadata
        optional_entry = optional_models[model_hashes[0]]
        assert "filename" in optional_entry
        assert "size" in optional_entry
        assert optional_entry.get("size", 0) > 0, \
            "Type 2 optional models should have file size"

        # 4. Should NOT have unresolved flag
        assert optional_entry.get("unresolved") is not True, \
            "Type 2 optional models should not be marked as unresolved"

        # 5. Workflow mapping should use hash as key
        workflow_mappings = pyproject.workflows.get_model_resolutions("test_workflow")
        assert model_hashes[0] in workflow_mappings, \
            "Workflow should reference optional model by hash"

        # 6. Workflow JSON SHOULD be updated with resolved path
        workflow_path = test_env.comfyui_path / "user/default/workflows/test_workflow.json"
        with open(workflow_path) as f:
            workflow_json_after = json.load(f)

        # Verify path was updated (not the original generic name)
        for node in workflow_json_after["nodes"]:
            if node["type"] == "CheckpointLoaderSimple":
                resolved_path = node["widgets_values"][0]
                assert resolved_path != "test_model.safetensors", \
                    "Workflow JSON should be updated with resolved path for Type 2 optional"
                break

    def test_optional_and_required_models_coexist(self, test_env, test_models, workflow_fixtures):
        """
        Test that optional and required models can coexist in same workflow.

        Expected behavior:
        - Workflow can have both required and optional models
        - Both are stored in appropriate sections
        - Resolution completes successfully
        - Commit succeeds
        """
        # ARRANGE - Create workflow with both required and optional models
        workflow = load_workflow_fixture(workflow_fixtures, "simple_txt2img")

        # Add a second node with a missing model (will be marked optional)
        workflow_json = workflow.copy()
        max_node_id = max(node["id"] for node in workflow_json["nodes"])

        # Add a custom node with missing model
        workflow_json["nodes"].append({
            "id": max_node_id + 1,
            "type": "CustomModelLoader",  # Non-builtin
            "widgets_values": ["missing_custom_model.pth"],
        })

        simulate_comfyui_save_workflow(test_env, "test_workflow", workflow_json)

        # Get status
        status = test_env.workflow_manager.get_workflow_status()
        workflow_status = status.analyzed_workflows[0]

        # ACT - Mark custom model as optional, let other resolve normally
        from comfydock_core.models.protocols import ModelResolutionStrategy
        from comfydock_core.models.workflow import WorkflowNodeWidgetRef
        from comfydock_core.models.shared import ModelWithLocation
        from typing import List

        class MixedStrategy(ModelResolutionStrategy):
            def handle_missing_model(self, reference: WorkflowNodeWidgetRef) -> tuple[str, str] | None:
                # Mark missing models as optional
                return ("optional_unresolved", "")

            def resolve_ambiguous_model(
                self, reference: WorkflowNodeWidgetRef, candidates: List[ModelWithLocation]
            ) -> ModelWithLocation | None:
                # Select first candidate as required
                return candidates[0] if candidates else None

        resolution = test_env.workflow_manager.fix_resolution(
            resolution=workflow_status.resolution,
            model_strategy=MixedStrategy()
        )

        test_env.workflow_manager.apply_resolution(
            resolution=resolution,
            workflow_name="test_workflow",
            model_refs=workflow_status.dependencies.found_models
        )

        # ASSERT - Verify both sections populated
        pyproject = test_env.pyproject

        required_models = pyproject.models.get_category("required")
        optional_models = pyproject.models.get_category("optional")

        # Should have at least one in each section (depending on test fixture)
        total_models = len(required_models) + len(optional_models)
        assert total_models > 0, \
            "Should have resolved at least one model"

        # Workflow should reference both
        workflow_mappings = pyproject.workflows.get_model_resolutions("test_workflow")
        assert len(workflow_mappings) > 0, \
            "Workflow should have model mappings"

    def test_optional_model_enables_commit(self, test_env, test_models, workflow_fixtures):
        """
        Test that marking models as optional allows commit to succeed.

        Expected behavior:
        - Workflow with only optional models can be committed
        - is_commit_safe returns True
        - Commit succeeds without --allow-issues
        """
        # ARRANGE - Workflow with missing model
        workflow = load_workflow_fixture(workflow_fixtures, "with_missing_model")
        simulate_comfyui_save_workflow(test_env, "test_workflow", workflow)

        # Get status - should have unresolved issues initially
        status_before = test_env.workflow_manager.get_workflow_status()
        assert not status_before.is_commit_safe, \
            "Should not be commit-safe with unresolved models"

        # ACT - Mark as optional
        from comfydock_core.models.protocols import ModelResolutionStrategy
        from comfydock_core.models.workflow import WorkflowNodeWidgetRef
        from comfydock_core.models.shared import ModelWithLocation
        from typing import List

        class OptionalStrategy(ModelResolutionStrategy):
            def handle_missing_model(self, reference: WorkflowNodeWidgetRef) -> tuple[str, str] | None:
                return ("optional_unresolved", "")

            def resolve_ambiguous_model(
                self, reference: WorkflowNodeWidgetRef, candidates: List[ModelWithLocation]
            ) -> ModelWithLocation | None:
                return None

        workflow_status = status_before.analyzed_workflows[0]
        resolution = test_env.workflow_manager.fix_resolution(
            resolution=workflow_status.resolution,
            model_strategy=OptionalStrategy()
        )

        test_env.workflow_manager.apply_resolution(
            resolution=resolution,
            workflow_name="test_workflow",
            model_refs=workflow_status.dependencies.found_models
        )

        # ASSERT - Commit should now be safe
        status_after = test_env.workflow_manager.get_workflow_status()
        assert status_after.is_commit_safe, \
            "Should be commit-safe after marking models as optional"

        # Commit should succeed
        test_env.execute_commit(status_after, message="Test commit with optional models")

        # Verify committed
        cec_workflow = test_env.cec_path / "workflows/test_workflow.json"
        assert cec_workflow.exists(), \
            "Workflow should be committed to .cec"


class TestOptionalNodes:
    """Tests for optional node support."""

    def test_optional_node_mapping(self, test_env, test_models, workflow_fixtures):
        """
        Test marking a node as optional using node_mappings with false value.

        Expected behavior:
        - User can mark unknown node as optional
        - Node stored in [tool.comfydock.node_mappings] with false value
        - Resolution counts as complete
        - Workflow can be committed
        """
        # ARRANGE - Create workflow with ONLY unknown custom node (no models to avoid resolution issues)
        workflow = load_workflow_fixture(workflow_fixtures, "simple_txt2img")
        workflow_json = workflow.copy()

        # Remove the model-loading node to avoid model resolution issues
        workflow_json["nodes"] = [n for n in workflow_json["nodes"] if n["type"] != "CheckpointLoaderSimple"]

        # Add unknown custom node (workflows use list of nodes, not dict)
        max_node_id = max(node["id"] for node in workflow_json["nodes"])
        workflow_json["nodes"].append({
            "id": max_node_id + 1,
            "type": "UnknownOptionalNode",
            "widgets_values": [],
        })

        simulate_comfyui_save_workflow(test_env, "test_workflow", workflow_json)

        # Get status - should have unresolved node
        status = test_env.workflow_manager.get_workflow_status()
        workflow_status = status.analyzed_workflows[0]

        assert len(workflow_status.resolution.nodes_unresolved) > 0, \
            "Should have at least one unresolved node"

        # ACT - Mark node as optional by adding to node_mappings with false value
        pyproject = test_env.pyproject
        pyproject.node_mappings.add_mapping("UnknownOptionalNode", False)

        # Re-resolve workflow
        dependencies = test_env.workflow_manager.analyze_workflow("test_workflow")
        resolution = test_env.workflow_manager.resolve_workflow(dependencies)

        # ASSERT - Node should be resolved (skipped via false mapping)
        # The false value should cause GlobalNodeResolver to skip this node
        # Check that it's not in unresolved list anymore
        node_types_unresolved = [n.type for n in resolution.nodes_unresolved]
        assert "UnknownOptionalNode" not in node_types_unresolved, \
            "Optional node should not be in unresolved list"

        # Verify mapping exists with false value
        mapping = pyproject.node_mappings.get_mapping("UnknownOptionalNode")
        assert mapping is False, \
            "Optional node should have false value in node_mappings"

        # Workflow should be commit-safe now (no models, node marked optional)
        status_after = test_env.workflow_manager.get_workflow_status()
        assert status_after.is_commit_safe, \
            "Should be commit-safe after marking node as optional"


class TestInteractiveStrategyOptionalSupport:
    """Tests for interactive strategy updates to support optional dependencies."""

    def test_interactive_model_strategy_offers_optional(self):
        """
        Test that InteractiveModelStrategy offers [o] option for missing models.

        This is a unit test for the strategy itself.
        Will test the actual user interaction flow separately.
        """
        from comfydock_cli.strategies.interactive import InteractiveModelStrategy
        from comfydock_core.models.workflow import WorkflowNodeWidgetRef

        # This test will verify the strategy protocol is properly implemented
        # For now, we'll just verify the class exists and has the right methods
        strategy = InteractiveModelStrategy()

        assert hasattr(strategy, 'handle_missing_model'), \
            "Strategy should have handle_missing_model method"
        assert hasattr(strategy, 'resolve_ambiguous_model'), \
            "Strategy should have resolve_ambiguous_model method"

        # TODO: Once implementation is done, test that:
        # - handle_missing_model returns ("optional_unresolved", "") when user selects 'o'
        # - resolve_ambiguous_model sets _mark_as_optional when user selects 'o'


class TestOptionalModelCommitBugFix:
    """
    BUG FIX: Test that optional models don't appear in both required and optional sections.

    Reproduces the issue where marking a model as optional during interactive resolve
    causes it to be added to BOTH models.required and models.optional after commit.

    Root cause: _try_pyproject_resolution() checks workflow mappings before checking
    optional section, and workflow mappings with no 'hash' field fall through to
    being treated as required models.
    """

    def test_optional_model_not_duplicated_in_required_section_after_commit(
        self, test_env, test_models, workflow_fixtures
    ):
        """
        REPRODUCES BUG: Optional model appears in both required and optional sections.

        Steps to reproduce:
        1. User runs workflow resolve and marks model as optional
        2. Model correctly added to models.optional with unresolved=true
        3. Workflow mapping created with filename as key (no hash field)
        4. User runs commit
        5. apply_all_resolution() calls resolve_workflow() again
        6. _try_pyproject_resolution() finds workflow mapping
        7. mapping.get('hash') returns None (no hash field)
        8. Falls through to model index search → not found
        9. Gets treated as NEW required model
        10. Added to models.required with fake data (size=0, relative_path="")

        Expected behavior:
        - Optional model should ONLY appear in models.optional
        - Should NOT appear in models.required
        - After commit, pyproject.toml should be clean
        """
        # ARRANGE - Create workflow with missing model
        workflow = load_workflow_fixture(workflow_fixtures, "with_missing_model")
        simulate_comfyui_save_workflow(test_env, "test_workflow", workflow)

        # Get initial status
        status = test_env.workflow_manager.get_workflow_status()
        workflow_status = status.analyzed_workflows[0]

        # Verify we have a missing model to work with
        assert len(workflow_status.resolution.models_unresolved) > 0, \
            "Test fixture should have at least one missing model"

        missing_model_filename = workflow_status.resolution.models_unresolved[0].widget_value

        # ACT PART 1: Interactive resolve - mark model as optional
        from comfydock_core.models.protocols import ModelResolutionStrategy
        from comfydock_core.models.workflow import WorkflowNodeWidgetRef
        from comfydock_core.models.shared import ModelWithLocation
        from typing import List

        class MockOptionalStrategy(ModelResolutionStrategy):
            def handle_missing_model(self, reference: WorkflowNodeWidgetRef) -> tuple[str, str] | None:
                return ("optional_unresolved", "")

            def resolve_ambiguous_model(
                self, reference: WorkflowNodeWidgetRef, candidates: List[ModelWithLocation]
            ) -> ModelWithLocation | None:
                return None

        # Fix resolution with optional strategy
        resolution = test_env.workflow_manager.fix_resolution(
            resolution=workflow_status.resolution,
            model_strategy=MockOptionalStrategy()
        )

        # Apply resolution (simulates what happens during interactive resolve)
        test_env.workflow_manager.apply_resolution(
            resolution=resolution,
            workflow_name="test_workflow",
            model_refs=workflow_status.dependencies.found_models
        )

        # VERIFY INTERMEDIATE STATE: Model should be in optional section only
        pyproject = test_env.pyproject

        optional_models_before = pyproject.models.get_category("optional")
        required_models_before = pyproject.models.get_category("required")

        assert missing_model_filename in optional_models_before, \
            "After interactive resolve, model should be in optional section"
        assert optional_models_before[missing_model_filename].get("unresolved") is True, \
            "Optional model should have unresolved=true"
        assert missing_model_filename not in required_models_before, \
            "After interactive resolve, model should NOT be in required section"

        # ACT PART 2: Commit (this triggers the bug)
        # During commit, apply_all_resolution() is called which re-resolves workflows
        status_for_commit = test_env.workflow_manager.get_workflow_status()
        test_env.execute_commit(status_for_commit, message="Test commit with optional model")

        # ASSERT: Model should STILL only be in optional section (BUG: it's in both!)
        optional_models_after = pyproject.models.get_category("optional")
        required_models_after = pyproject.models.get_category("required")

        # The core assertion: model should NOT be duplicated in required section
        assert missing_model_filename in optional_models_after, \
            "After commit, model should still be in optional section"

        # THIS IS THE BUG - this assertion will FAIL until we fix it
        assert missing_model_filename not in required_models_after, \
            f"BUG: Optional model '{missing_model_filename}' should NOT appear in required section after commit. " \
            f"Found in required: {required_models_after.get(missing_model_filename)}"

        # Additional verification: check the entries are correct
        # Optional section should have unresolved=true
        assert optional_models_after[missing_model_filename].get("unresolved") is True, \
            "Optional section should still have unresolved=true"

        # Required section should NOT have a fake entry with size=0
        if missing_model_filename in required_models_after:
            # If bug exists, this will show the problematic fake entry
            fake_entry = required_models_after[missing_model_filename]
            pytest.fail(
                f"BUG DETECTED: Optional model was duplicated in required section.\n"
                f"Optional entry: {optional_models_after[missing_model_filename]}\n"
                f"Required entry (fake): {fake_entry}\n"
                f"This happens because _try_pyproject_resolution() checks workflow mappings "
                f"before checking optional section, and mappings without 'hash' field fall through."
            )
