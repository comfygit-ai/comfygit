"""Tests for rollback safety with uncommitted changes."""
import json
import pytest
from comfydock_core.models.exceptions import CDEnvironmentError


class TestRollbackSafety:
    """Test that rollback protects uncommitted work."""

    def test_rollback_blocks_with_uncommitted_changes(self, test_env, test_models):
        """Rollback should error when there are uncommitted changes (no --force)."""
        # ARRANGE: Create v1
        workflow_path = test_env.comfyui_path / "user/default/workflows/test_wf.json"
        workflow_path.parent.mkdir(parents=True, exist_ok=True)
        workflow_path.write_text(json.dumps({"nodes": [], "links": [], "extra": {}}))
        test_env.workflow_manager.copy_all_workflows()
        test_env.commit("v1: Initial")

        # Create v2
        workflow_path.write_text(json.dumps({"nodes": [], "links": [], "extra": {"v2": True}}))
        test_env.workflow_manager.copy_all_workflows()
        test_env.commit("v2: Update")

        # Make uncommitted change in .cec/ (git tracked)
        cec_workflow_path = test_env.cec_path / "workflows/test_wf.json"
        with open(cec_workflow_path) as f:
            workflow = json.load(f)
        workflow["extra"]["uncommitted"] = True
        with open(cec_workflow_path, 'w') as f:
            json.dump(workflow, f)

        # ACT & ASSERT: Rollback should raise error
        with pytest.raises(CDEnvironmentError, match="uncommitted changes"):
            test_env.rollback("v1")

        # Verify data not lost
        with open(cec_workflow_path) as f:
            workflow = json.load(f)
        assert workflow["extra"]["uncommitted"] is True

    def test_rollback_with_force_discards_changes(self, test_env, test_models):
        """Rollback with force=True should discard uncommitted changes."""
        # ARRANGE: Create v1
        workflow_path = test_env.comfyui_path / "user/default/workflows/test_wf.json"
        workflow_path.parent.mkdir(parents=True, exist_ok=True)
        workflow_path.write_text(json.dumps({"nodes": [], "links": [], "extra": {}}))
        test_env.workflow_manager.copy_all_workflows()
        test_env.commit("v1: Initial")

        # Create v2
        workflow_path.write_text(json.dumps({"nodes": [], "links": [], "extra": {"v2": True}}))
        test_env.workflow_manager.copy_all_workflows()
        test_env.commit("v2: Update")

        # Make uncommitted change in .cec/ (git tracked)
        cec_workflow_path = test_env.cec_path / "workflows/test_wf.json"
        with open(cec_workflow_path) as f:
            workflow = json.load(f)
        workflow["extra"]["will_be_lost"] = True
        with open(cec_workflow_path, 'w') as f:
            json.dump(workflow, f)

        # ACT: Rollback with force
        test_env.rollback("v1", force=True)

        # ASSERT: Changes discarded, back to v1 state
        # Rollback restores workflows to ComfyUI, check there
        if workflow_path.exists():
            with open(workflow_path) as f:
                workflow = json.load(f)
            assert "will_be_lost" not in workflow.get("extra", {})
            assert "v2" not in workflow.get("extra", {})

    def test_rollback_without_uncommitted_changes_works(self, test_env, test_models):
        """Rollback works normally when no uncommitted changes."""
        # ARRANGE: Create v1 and v2
        workflow_path = test_env.comfyui_path / "user/default/workflows/test_wf.json"
        workflow_path.parent.mkdir(parents=True, exist_ok=True)
        workflow_path.write_text(json.dumps({"nodes": [], "links": [], "extra": {}}))
        test_env.workflow_manager.copy_all_workflows()
        test_env.commit("v1: Initial")

        workflow_path.write_text(json.dumps({"nodes": [], "links": [], "extra": {"v2": True}}))
        test_env.workflow_manager.copy_all_workflows()
        test_env.commit("v2: Update")

        # ACT: Rollback (no uncommitted changes, should succeed)
        test_env.rollback("v1")

        # ASSERT: Rollback completed without error (implicit pass if no exception)
