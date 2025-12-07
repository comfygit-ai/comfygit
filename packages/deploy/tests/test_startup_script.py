"""Tests for startup script generation.

TDD: These tests are written first.
"""


from comfygit_deploy.startup.scripts import (
    generate_deployment_id,
    generate_startup_script,
)


class TestDeploymentIdGeneration:
    """Tests for deployment ID generation."""

    def test_generates_unique_ids(self) -> None:
        """Each call should generate a unique ID."""
        id1 = generate_deployment_id("my-env")
        id2 = generate_deployment_id("my-env")
        assert id1 != id2

    def test_id_starts_with_deploy_prefix(self) -> None:
        """IDs should start with 'deploy-'."""
        deployment_id = generate_deployment_id("test-env")
        assert deployment_id.startswith("deploy-")

    def test_sanitizes_special_characters(self) -> None:
        """Special characters should be replaced with dashes."""
        deployment_id = generate_deployment_id("my env@test#123")
        assert "@" not in deployment_id
        assert "#" not in deployment_id
        assert " " not in deployment_id

    def test_handles_empty_name(self) -> None:
        """Empty name should result in default 'env'."""
        deployment_id = generate_deployment_id("")
        assert "deploy-env-" in deployment_id


class TestStartupScriptGeneration:
    """Tests for startup script generation."""

    def test_script_contains_deployment_id(self) -> None:
        """Script should reference the deployment ID."""
        script = generate_startup_script(
            deployment_id="deploy-test-123",
            import_source="https://github.com/user/env.git",
        )
        assert "deploy-test-123" in script

    def test_script_contains_import_source(self) -> None:
        """Script should contain the import source."""
        script = generate_startup_script(
            deployment_id="deploy-test",
            import_source="https://github.com/user/env.git",
        )
        assert "https://github.com/user/env.git" in script

    def test_script_includes_branch_flag(self) -> None:
        """Script should include branch flag if specified."""
        script = generate_startup_script(
            deployment_id="deploy-test",
            import_source="https://github.com/user/env.git",
            branch="main",
        )
        assert "-b main" in script

    def test_script_uses_custom_port(self) -> None:
        """Script should use custom ComfyUI port if specified."""
        script = generate_startup_script(
            deployment_id="deploy-test",
            import_source="https://github.com/user/env.git",
            comfyui_port=3000,
        )
        assert "--port 3000" in script
        assert "localhost:3000" in script

    def test_script_installs_uv(self) -> None:
        """Script should install uv if not present."""
        script = generate_startup_script(
            deployment_id="deploy-test",
            import_source="https://github.com/user/env.git",
        )
        assert "curl -LsSf https://astral.sh/uv/install.sh" in script

    def test_script_installs_comfygit(self) -> None:
        """Script should install comfygit CLI."""
        script = generate_startup_script(
            deployment_id="deploy-test",
            import_source="https://github.com/user/env.git",
        )
        assert "uv tool install comfygit" in script

    def test_script_sets_comfygit_home(self) -> None:
        """Script should set COMFYGIT_HOME."""
        script = generate_startup_script(
            deployment_id="deploy-test",
            import_source="https://github.com/user/env.git",
        )
        assert "COMFYGIT_HOME=/workspace/comfygit" in script

    def test_script_handles_restart_scenario(self) -> None:
        """Script should skip import if environment already exists."""
        script = generate_startup_script(
            deployment_id="deploy-test",
            import_source="https://github.com/user/env.git",
        )
        # Should check if environment exists before importing
        assert 'if [ -d "$ENV_PATH" ]' in script
        assert "Skipping import" in script

    def test_script_is_valid_bash(self) -> None:
        """Script should start with shebang."""
        script = generate_startup_script(
            deployment_id="deploy-test",
            import_source="https://github.com/user/env.git",
        )
        assert script.startswith("#!/bin/bash")
