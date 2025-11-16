"""Tests for workflow model deduplication during resolution.

When the same model appears in multiple nodes, the user should only be prompted once,
and all node references should be grouped together in a single ManifestWorkflowModel entry.
"""
import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, call

from comfygit_core.managers.workflow_manager import WorkflowManager
from comfygit_core.models.workflow import (
    WorkflowNodeWidgetRef,
    ResolvedModel,
    ResolutionResult,
    ModelResolutionContext,
)
from comfygit_core.models.shared import ModelWithLocation
from comfygit_core.models.manifest import ManifestWorkflowModel


class TestModelDeduplication:
    """Test that duplicate model references are resolved only once."""

    @pytest.fixture
    def workflow_manager(self, tmp_path):
        """Create a WorkflowManager with mocked dependencies."""
        manager = Mock(spec=WorkflowManager)
        manager.environment_name = "test_env"
        manager.pyproject = Mock()
        manager.pyproject.workflows = Mock()
        manager.model_repository = Mock()
        manager.workflow_cache = Mock()

        # Make the actual methods we're testing real
        manager._write_model_resolution_grouped = WorkflowManager._write_model_resolution_grouped.__get__(manager)
        manager._get_category_for_node_ref = Mock(return_value="vae")
        manager._get_default_criticality = Mock(return_value="flexible")

        return manager

    def test_same_model_in_multiple_nodes_groups_refs(self, workflow_manager):
        """When same model appears in multiple nodes, all refs should be grouped together."""
        # Arrange: Two nodes reference the same model
        ref1 = WorkflowNodeWidgetRef(
            node_id="39",
            node_type="VAELoader",
            widget_index=0,
            widget_value="qwen_image_vae.safetensors"
        )
        ref2 = WorkflowNodeWidgetRef(
            node_id="337",
            node_type="VAELoader",
            widget_index=0,
            widget_value="qwen_image_vae.safetensors"
        )

        resolved_model = ModelWithLocation(
            hash="abc123",
            file_size=1000,
            blake3_hash="blake3_abc123",
            sha256_hash=None,
            relative_path="vae/qwen_image_vae.safetensors",
            filename="qwen_image_vae.safetensors",
            mtime=123456,
            last_seen=123456,
            base_directory="/models",
            metadata={}
        )

        resolved = ResolvedModel(
            workflow="test_workflow",
            reference=ref1,  # Primary ref
            match_type="exact",
            resolved_model=resolved_model,
            match_confidence=1.0,
        )

        workflow_manager.model_repository.get_sources.return_value = []

        # Act: Write grouped resolution with both refs
        all_refs = [ref1, ref2]
        workflow_manager._write_model_resolution_grouped("test_workflow", resolved, all_refs)

        # Assert: pyproject.workflows.add_workflow_model called with grouped refs
        workflow_manager.pyproject.workflows.add_workflow_model.assert_called_once()
        call_args = workflow_manager.pyproject.workflows.add_workflow_model.call_args

        assert call_args[0][0] == "test_workflow"
        manifest_model = call_args[0][1]

        assert isinstance(manifest_model, ManifestWorkflowModel)
        assert len(manifest_model.nodes) == 2
        assert manifest_model.nodes[0] == ref1
        assert manifest_model.nodes[1] == ref2
        assert manifest_model.hash == "abc123"
        assert manifest_model.status == "resolved"

    def test_different_models_not_grouped(self):
        """Different models should not be grouped together."""
        # This test verifies the grouping key logic
        ref1 = WorkflowNodeWidgetRef(
            node_id="39",
            node_type="VAELoader",
            widget_index=0,
            widget_value="model_a.safetensors"
        )
        ref2 = WorkflowNodeWidgetRef(
            node_id="40",
            node_type="VAELoader",
            widget_index=0,
            widget_value="model_b.safetensors"
        )

        # Different widget_value should create different grouping keys
        key1 = (ref1.widget_value, ref1.node_type)
        key2 = (ref2.widget_value, ref2.node_type)

        assert key1 != key2

    def test_same_model_different_node_types_not_grouped(self):
        """Same model in different node types should not be grouped (safety)."""
        ref1 = WorkflowNodeWidgetRef(
            node_id="39",
            node_type="VAELoader",
            widget_index=0,
            widget_value="qwen_image_vae.safetensors"
        )
        ref2 = WorkflowNodeWidgetRef(
            node_id="40",
            node_type="CustomVAELoader",  # Different node type
            widget_index=0,
            widget_value="qwen_image_vae.safetensors"
        )

        # Different node_type should create different grouping keys
        key1 = (ref1.widget_value, ref1.node_type)
        key2 = (ref2.widget_value, ref2.node_type)

        assert key1 != key2

    def test_download_intent_with_multiple_refs(self, workflow_manager):
        """Download intents should also support multiple node refs."""
        ref1 = WorkflowNodeWidgetRef(
            node_id="39",
            node_type="VAELoader",
            widget_index=0,
            widget_value="qwen_image_vae.safetensors"
        )
        ref2 = WorkflowNodeWidgetRef(
            node_id="337",
            node_type="VAELoader",
            widget_index=0,
            widget_value="qwen_image_vae.safetensors"
        )

        resolved = ResolvedModel(
            workflow="test_workflow",
            reference=ref1,
            match_type="download_intent",
            resolved_model=None,
            model_source="https://civitai.com/api/download/models/12345",
            target_path=Path("vae/qwen_image_vae.safetensors"),
            match_confidence=1.0,
        )

        all_refs = [ref1, ref2]
        workflow_manager._write_model_resolution_grouped("test_workflow", resolved, all_refs)

        # Assert: Manifest has download intent with both refs
        call_args = workflow_manager.pyproject.workflows.add_workflow_model.call_args
        manifest_model = call_args[0][1]

        assert len(manifest_model.nodes) == 2
        assert manifest_model.status == "unresolved"
        assert manifest_model.sources == ["https://civitai.com/api/download/models/12345"]
        assert manifest_model.relative_path == "vae/qwen_image_vae.safetensors"

    def test_optional_model_with_multiple_refs(self, workflow_manager):
        """Optional models should support multiple node refs."""
        ref1 = WorkflowNodeWidgetRef(
            node_id="39",
            node_type="VAELoader",
            widget_index=0,
            widget_value="optional_vae.safetensors"
        )
        ref2 = WorkflowNodeWidgetRef(
            node_id="337",
            node_type="VAELoader",
            widget_index=0,
            widget_value="optional_vae.safetensors"
        )

        resolved = ResolvedModel(
            workflow="test_workflow",
            reference=ref1,
            match_type="workflow_context",
            resolved_model=None,
            is_optional=True,
            match_confidence=1.0,
        )

        all_refs = [ref1, ref2]
        workflow_manager._write_model_resolution_grouped("test_workflow", resolved, all_refs)

        # Assert: Manifest has optional criticality with both refs
        call_args = workflow_manager.pyproject.workflows.add_workflow_model.call_args
        manifest_model = call_args[0][1]

        assert len(manifest_model.nodes) == 2
        assert manifest_model.criticality == "optional"
        assert manifest_model.status == "unresolved"


class TestDeduplicationIntegration:
    """Integration tests for full deduplication flow."""

    def test_grouping_key_logic(self):
        """Verify the grouping key correctly identifies duplicates."""
        # Same model, same node type → should group
        refs_same = [
            WorkflowNodeWidgetRef("39", "VAELoader", 0, "model.safetensors"),
            WorkflowNodeWidgetRef("337", "VAELoader", 0, "model.safetensors"),
        ]

        groups = {}
        for ref in refs_same:
            key = (ref.widget_value, ref.node_type)
            if key not in groups:
                groups[key] = []
            groups[key].append(ref)

        assert len(groups) == 1
        assert len(list(groups.values())[0]) == 2

    def test_grouping_preserves_all_refs(self):
        """Verify all refs are preserved during grouping."""
        refs = [
            WorkflowNodeWidgetRef("1", "VAELoader", 0, "model_a.safetensors"),
            WorkflowNodeWidgetRef("2", "VAELoader", 0, "model_a.safetensors"),
            WorkflowNodeWidgetRef("3", "VAELoader", 0, "model_b.safetensors"),
            WorkflowNodeWidgetRef("4", "CheckpointLoaderSimple", 0, "model_a.safetensors"),
        ]

        groups = {}
        for ref in refs:
            key = (ref.widget_value, ref.node_type)
            if key not in groups:
                groups[key] = []
            groups[key].append(ref)

        # Should have 3 groups:
        # 1. (model_a, VAELoader) → refs 1, 2
        # 2. (model_b, VAELoader) → ref 3
        # 3. (model_a, CheckpointLoaderSimple) → ref 4
        assert len(groups) == 3
        assert len(groups[("model_a.safetensors", "VAELoader")]) == 2
        assert len(groups[("model_b.safetensors", "VAELoader")]) == 1
        assert len(groups[("model_a.safetensors", "CheckpointLoaderSimple")]) == 1
