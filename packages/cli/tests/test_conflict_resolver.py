"""Tests for conflict resolution strategies."""

from unittest.mock import MagicMock, patch

import pytest
from comfygit_core.models.ref_diff import (
    DependencyChanges,
    NodeConflict,
    RefDiff,
    WorkflowConflict,
)

from comfygit_cli.strategies.conflict_resolver import (
    AutoConflictResolver,
    InteractiveConflictResolver,
)


class TestAutoConflictResolver:
    """Tests for AutoConflictResolver."""

    def test_mine_strategy_returns_take_base(self):
        """Auto-resolve with 'mine' should return take_base."""
        resolver = AutoConflictResolver("mine")

        conflict = WorkflowConflict(
            identifier="test-workflow",
            conflict_type="both_modified",
            base_hash="abc123",
            target_hash="def456",
        )

        result = resolver.resolve_workflow(conflict)
        assert result == "take_base"

    def test_theirs_strategy_returns_take_target(self):
        """Auto-resolve with 'theirs' should return take_target."""
        resolver = AutoConflictResolver("theirs")

        conflict = NodeConflict(
            identifier="test-node",
            conflict_type="both_modified",
            base_version="1.0.0",
            target_version="2.0.0",
        )

        result = resolver.resolve_node(conflict)
        assert result == "take_target"

    def test_resolve_all_updates_all_conflicts(self):
        """resolve_all should update all unresolved conflicts."""
        resolver = AutoConflictResolver("theirs")

        diff = RefDiff(
            base_ref="HEAD",
            target_ref="origin/main",
            merge_base="abc123",
            node_changes=[],
            model_changes=[],
            workflow_changes=[],
            dependency_changes=DependencyChanges(),
        )

        # Add conflicts directly for testing
        wf_conflict = WorkflowConflict(
            identifier="wf1",
            conflict_type="both_modified",
        )
        node_conflict = NodeConflict(
            identifier="node1",
            conflict_type="both_modified",
        )

        # Mock the all_conflicts property
        diff.workflow_changes.append(
            MagicMock(conflict=wf_conflict, change_type="modified")
        )
        diff.node_changes.append(
            MagicMock(conflict=node_conflict, change_type="version_changed")
        )

        resolutions = resolver.resolve_all(diff)

        assert len(resolutions) == 2
        assert resolutions["wf1"] == "take_target"
        assert resolutions["node1"] == "take_target"
        assert wf_conflict.resolution == "take_target"
        assert node_conflict.resolution == "take_target"


class TestInteractiveConflictResolver:
    """Tests for InteractiveConflictResolver."""

    def test_resolve_workflow_mine_choice(self):
        """User choosing 'm' should return take_base."""
        resolver = InteractiveConflictResolver()

        conflict = WorkflowConflict(
            identifier="test-workflow",
            conflict_type="both_modified",
            base_hash="abc123",
            target_hash="def456",
        )

        with patch("builtins.input", return_value="m"):
            with patch("builtins.print"):
                result = resolver.resolve_workflow(conflict)

        assert result == "take_base"

    def test_resolve_workflow_theirs_choice(self):
        """User choosing 't' should return take_target."""
        resolver = InteractiveConflictResolver()

        conflict = WorkflowConflict(
            identifier="test-workflow",
            conflict_type="both_modified",
        )

        with patch("builtins.input", return_value="t"):
            with patch("builtins.print"):
                result = resolver.resolve_workflow(conflict)

        assert result == "take_target"

    def test_resolve_workflow_skip_choice(self):
        """User choosing 's' should return skip."""
        resolver = InteractiveConflictResolver()

        conflict = WorkflowConflict(
            identifier="test-workflow",
            conflict_type="both_modified",
        )

        with patch("builtins.input", return_value="s"):
            with patch("builtins.print"):
                result = resolver.resolve_workflow(conflict)

        assert result == "skip"

    def test_resolve_node_delete_modify_conflict(self):
        """Should handle delete-modify conflicts correctly."""
        resolver = InteractiveConflictResolver()

        conflict = NodeConflict(
            identifier="test-node",
            conflict_type="delete_modify",
            base_version="1.0.0",
            target_deleted=True,
        )

        with patch("builtins.input", return_value="m"):
            with patch("builtins.print"):
                result = resolver.resolve_node(conflict)

        assert result == "take_base"

    def test_resolve_all_skipped_conflicts_not_mutated(self):
        """Skipped conflicts should not have resolution updated."""
        resolver = InteractiveConflictResolver()

        conflict = WorkflowConflict(
            identifier="test-wf",
            conflict_type="both_modified",
        )

        diff = RefDiff(
            base_ref="HEAD",
            target_ref="origin/main",
            merge_base="abc123",
            node_changes=[],
            model_changes=[],
            workflow_changes=[MagicMock(conflict=conflict, change_type="modified")],
            dependency_changes=DependencyChanges(),
        )

        with patch("builtins.input", return_value="s"):
            with patch("builtins.print"):
                resolutions = resolver.resolve_all(diff)

        assert resolutions["test-wf"] == "skip"
        # Skipped conflicts should stay unresolved
        assert conflict.resolution == "unresolved"
