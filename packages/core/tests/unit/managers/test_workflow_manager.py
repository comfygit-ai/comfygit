"""Tests for WorkflowManager normalization logic."""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from comfydock_core.managers.workflow_manager import WorkflowManager


@pytest.fixture
def workflow_manager():
    """Create a minimal WorkflowManager for testing normalization."""
    with patch('comfydock_core.managers.workflow_manager.GlobalNodeResolver'):
        with patch('comfydock_core.managers.workflow_manager.ModelResolver'):
            manager = WorkflowManager(
                comfyui_path=Path("/tmp/comfyui"),
                cec_path=Path("/tmp/cec"),
                pyproject=Mock(),
                model_repository=Mock(),
                registry_data_manager=Mock()
            )
            return manager


def test_normalize_workflow_removes_volatile_fields(workflow_manager):
    """Test that workflow normalization removes volatile metadata fields."""

    workflow = {
        "id": "test-workflow",
        "revision": 5,
        "nodes": [],
        "links": [],
        "extra": {
            "ds": {"scale": 1.0, "offset": [0, 0]},
            "frontendVersion": "1.25.11",
            "someOtherField": "preserved"
        }
    }

    normalized = workflow_manager._normalize_workflow_for_comparison(workflow)

    # Check volatile fields removed
    assert "revision" not in normalized
    assert "ds" not in normalized.get("extra", {})
    assert "frontendVersion" not in normalized.get("extra", {})

    # Check other fields preserved
    assert normalized["id"] == "test-workflow"
    assert normalized["extra"]["someOtherField"] == "preserved"


def test_normalize_workflow_handles_randomize_seeds(workflow_manager):
    """Test that auto-generated seeds with 'randomize' mode are normalized."""

    workflow = {
        "nodes": [
            {
                "id": "3",
                "type": "KSampler",
                "widgets_values": [609167611557182, "randomize", 20, 8, "euler", "normal", 1],
                "api_widget_values": [609167611557182, "randomize", 20, 8, "euler", "normal", 1]
            }
        ]
    }

    normalized = workflow_manager._normalize_workflow_for_comparison(workflow)

    # Seed should be normalized to 0 when control is "randomize"
    assert normalized["nodes"][0]["widgets_values"][0] == 0
    assert normalized["nodes"][0]["api_widget_values"][0] == 0

    # Other values should be preserved
    assert normalized["nodes"][0]["widgets_values"][2] == 20  # steps
    assert normalized["nodes"][0]["widgets_values"][3] == 8  # cfg


def test_normalize_workflow_preserves_fixed_seeds(workflow_manager):
    """Test that user-set fixed seeds are NOT normalized."""

    workflow = {
        "nodes": [
            {
                "id": "3",
                "type": "KSampler",
                "widgets_values": [12345, "fixed", 20, 8, "euler", "normal", 1],
                "api_widget_values": [12345, "fixed", 20, 8, "euler", "normal", 1]
            }
        ]
    }

    normalized = workflow_manager._normalize_workflow_for_comparison(workflow)

    # Fixed seed should be preserved
    assert normalized["nodes"][0]["widgets_values"][0] == 12345
    assert normalized["nodes"][0]["api_widget_values"][0] == 12345


def test_workflows_differ_detects_real_changes():
    """Test that _workflows_differ detects actual workflow changes."""
    # This would require more setup with actual files
    # Skipping for now as it's integration-level
    pass