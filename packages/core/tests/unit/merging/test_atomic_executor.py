"""Unit tests for AtomicMergeExecutor.

Tests the atomic merge execution with rollback on failure.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from comfygit_core.merging.atomic_executor import AtomicMergeExecutor
from comfygit_core.models.merge_plan import MergePlan


class TestAtomicMergeExecutor:
    """Test AtomicMergeExecutor functionality."""

    def test_is_merge_in_progress_detects_merge(self, tmp_path):
        """Detects when a merge is in progress."""
        # Create a mock git repo with MERGE_HEAD
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "MERGE_HEAD").write_text("abc123")

        assert AtomicMergeExecutor.is_merge_in_progress(tmp_path)

    def test_is_merge_in_progress_false_when_clean(self, tmp_path):
        """Returns false when no merge in progress."""
        # Create a mock git repo without MERGE_HEAD
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        assert not AtomicMergeExecutor.is_merge_in_progress(tmp_path)

    def test_rollback_on_failure(self, tmp_path):
        """Merge rolls back on failure."""
        # Create a mock pyproject manager
        mock_pyproject = MagicMock()

        executor = AtomicMergeExecutor(
            repo_path=tmp_path,
            pyproject_manager=mock_pyproject,
        )

        plan = MergePlan(
            target_branch="feature",
            base_ref="HEAD",
            workflow_resolutions={},
            final_workflow_set=[],
        )

        # Mock _start_merge to fail
        with patch.object(executor, "_start_merge", side_effect=Exception("Merge conflict")):
            with patch.object(executor, "_abort_merge") as mock_abort:
                result = executor.execute(plan)

        assert not result.success
        assert "Merge conflict" in result.error
        mock_abort.assert_called_once()

    def test_successful_merge_returns_commit(self, tmp_path):
        """Successful merge returns commit hash."""
        mock_pyproject = MagicMock()

        executor = AtomicMergeExecutor(
            repo_path=tmp_path,
            pyproject_manager=mock_pyproject,
        )

        plan = MergePlan(
            target_branch="feature",
            base_ref="HEAD",
            workflow_resolutions={"wf1": "take_base"},
            final_workflow_set=["wf1"],
        )

        # Mock all the git operations
        with patch.object(executor, "_start_merge"):
            with patch.object(executor, "_resolve_workflow_files"):
                with patch.object(executor, "_build_merged_pyproject"):
                    with patch.object(executor, "_commit_merge", return_value="abc123"):
                        result = executor.execute(plan)

        assert result.success
        assert result.merge_commit == "abc123"
        assert result.workflows_merged == ["wf1"]
