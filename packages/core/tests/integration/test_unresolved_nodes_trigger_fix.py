"""Integration test for unresolved nodes triggering interactive resolution.

This test reproduces the bug where workflows with unresolved nodes
don't trigger fix_resolution() because ResolutionResult.has_issues
doesn't check for unresolved nodes.

Bug: https://github.com/anthropics/comfydock/issues/XXX
"""

import json
from pathlib import Path


def test_unresolved_nodes_should_trigger_interactive_resolution(test_env):
    """Test that unresolved nodes trigger fix_resolution() via has_issues property.

    Scenario:
    - Workflow has nodes that can't be resolved (not in global table, no properties)
    - Expected: has_issues should be True when nodes_unresolved is non-empty
    - Bug: has_issues returns False because it only checks models, not nodes

    This reproduces the bug where `workflow resolve` says "✅ Resolution complete!"
    but nodes remain unresolved and no interactive prompts appear.
    """
    # Arrange: Create workflow with unknown custom nodes
    workflow_content = {
        "nodes": [
            {
                "id": "1",
                "type": "UnknownCustomNode1",  # Not in global table
                "pos": [100, 100],
                "size": [200, 100],
                "flags": {},
                "order": 0,
                "mode": 0,
                "inputs": [],
                "outputs": [],
                "properties": {},  # No cnr_id
                "widgets_values": []
            },
            {
                "id": "2",
                "type": "UnknownCustomNode2",  # Also not in global table
                "pos": [400, 100],
                "size": [200, 100],
                "flags": {},
                "order": 1,
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

    # Create workflow file
    workflow_name = "test_unresolved"
    workflow_path = test_env.comfyui_path / "user" / "default" / "workflows" / f"{workflow_name}.json"
    workflow_path.parent.mkdir(parents=True, exist_ok=True)

    with open(workflow_path, 'w') as f:
        json.dump(workflow_content, f, indent=2)

    # Act: Analyze workflow
    from comfydock_core.models.workflow import WorkflowDependencies
    analysis: WorkflowDependencies = test_env.workflow_manager.analyze_workflow(workflow_name)

    # Act: Resolve workflow
    from comfydock_core.models.workflow import ResolutionResult
    resolution: ResolutionResult = test_env.workflow_manager.resolve_workflow(analysis)

    # Assert: Check that we have unresolved nodes
    assert len(resolution.nodes_unresolved) == 2, (
        f"Should have 2 unresolved nodes, got {len(resolution.nodes_unresolved)}"
    )

    # Assert: No model issues (focusing on nodes-only bug)
    assert len(resolution.models_unresolved) == 0, "Should have no model issues"
    assert len(resolution.models_ambiguous) == 0, "Should have no ambiguous models"

    # THE BUG: has_issues should be True when nodes_unresolved is non-empty
    # Currently returns False because it only checks models
    assert resolution.has_issues, (
        "ResolutionResult.has_issues should be True when nodes_unresolved is non-empty. "
        f"Got: nodes_unresolved={len(resolution.nodes_unresolved)}, "
        f"nodes_ambiguous={len(resolution.nodes_ambiguous)}, "
        f"models_unresolved={len(resolution.models_unresolved)}, "
        f"models_ambiguous={len(resolution.models_ambiguous)}, "
        f"has_issues={resolution.has_issues}"
    )
