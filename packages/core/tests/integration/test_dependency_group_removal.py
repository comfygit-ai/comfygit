"""Test dependency group removal functionality.

Tests for removing entire dependency groups and removing individual packages
from dependency groups in pyproject.toml.
"""

import pytest


class TestDependencyGroupRemoval:
    """Test removing dependency groups and packages from groups."""

    def test_remove_entire_dependency_group(self, test_env):
        """Should remove an entire dependency group from pyproject.toml."""
        # ARRANGE: Add a dependency group
        config = test_env.pyproject.load()
        config.setdefault("dependency-groups", {})
        config["dependency-groups"]["optional-cuda"] = ["sageattention>=2.2.0", "torch-cuda>=2.0"]
        config["dependency-groups"]["optional-rocm"] = ["torch-rocm>=2.0"]
        test_env.pyproject.save(config)

        # Verify group exists
        groups = test_env.pyproject.dependencies.get_groups()
        assert "optional-cuda" in groups
        assert "optional-rocm" in groups

        # ACT: Remove the optional-cuda group
        test_env.pyproject.dependencies.remove_group("optional-cuda")

        # ASSERT: Group should be gone
        groups = test_env.pyproject.dependencies.get_groups()
        assert "optional-cuda" not in groups
        assert "optional-rocm" in groups  # Other groups unaffected

    def test_remove_nonexistent_group_raises_error(self, test_env):
        """Should raise ValueError when removing a group that doesn't exist."""
        # ARRANGE: No dependency groups
        config = test_env.pyproject.load()
        config.pop("dependency-groups", None)
        test_env.pyproject.save(config)

        # ACT & ASSERT: Should raise error
        with pytest.raises(ValueError, match="No dependency groups found"):
            test_env.pyproject.dependencies.remove_group("nonexistent")

    def test_remove_packages_from_group(self, test_env):
        """Should remove specific packages from a dependency group."""
        # ARRANGE: Add a dependency group with multiple packages
        config = test_env.pyproject.load()
        config.setdefault("dependency-groups", {})
        config["dependency-groups"]["optional-extras"] = [
            "pillow>=9.0.0",
            "pyyaml>=5.0",
            "requests>=2.0.0"
        ]
        test_env.pyproject.save(config)

        # ACT: Remove one package from the group
        test_env.pyproject.dependencies.remove_from_group("optional-extras", ["pyyaml"])

        # ASSERT: Package should be removed, others remain
        groups = test_env.pyproject.dependencies.get_groups()
        assert "optional-extras" in groups
        assert "pillow>=9.0.0" in groups["optional-extras"]
        assert "requests>=2.0.0" in groups["optional-extras"]
        assert "pyyaml>=5.0" not in groups["optional-extras"]
        assert len(groups["optional-extras"]) == 2

    def test_remove_multiple_packages_from_group(self, test_env):
        """Should remove multiple packages from a dependency group at once."""
        # ARRANGE
        config = test_env.pyproject.load()
        config.setdefault("dependency-groups", {})
        config["dependency-groups"]["optional-ml"] = [
            "numpy>=1.20.0",
            "scipy>=1.7.0",
            "pandas>=1.3.0",
            "scikit-learn>=1.0.0"
        ]
        test_env.pyproject.save(config)

        # ACT: Remove multiple packages
        test_env.pyproject.dependencies.remove_from_group("optional-ml", ["scipy", "pandas"])

        # ASSERT
        groups = test_env.pyproject.dependencies.get_groups()
        assert "optional-ml" in groups
        assert "numpy>=1.20.0" in groups["optional-ml"]
        assert "scikit-learn>=1.0.0" in groups["optional-ml"]
        assert "scipy>=1.7.0" not in groups["optional-ml"]
        assert "pandas>=1.3.0" not in groups["optional-ml"]
        assert len(groups["optional-ml"]) == 2

    def test_remove_from_group_handles_nonexistent_packages(self, test_env):
        """Should silently skip packages that don't exist in the group."""
        # ARRANGE
        config = test_env.pyproject.load()
        config.setdefault("dependency-groups", {})
        config["dependency-groups"]["optional-test"] = ["pytest>=7.0.0", "coverage>=6.0"]
        test_env.pyproject.save(config)

        # ACT: Try to remove mix of existent and non-existent packages
        result = test_env.pyproject.dependencies.remove_from_group(
            "optional-test",
            ["pytest", "nonexistent-package", "another-fake"]
        )

        # ASSERT: Should remove what exists, skip what doesn't
        groups = test_env.pyproject.dependencies.get_groups()
        assert "optional-test" in groups
        assert "pytest>=7.0.0" not in groups["optional-test"]
        assert "coverage>=6.0" in groups["optional-test"]
        assert result["removed"] == ["pytest"]
        assert set(result["skipped"]) == {"nonexistent-package", "another-fake"}

    def test_remove_from_nonexistent_group_raises_error(self, test_env):
        """Should raise ValueError when removing from a group that doesn't exist."""
        # ARRANGE
        config = test_env.pyproject.load()
        config.pop("dependency-groups", None)
        test_env.pyproject.save(config)

        # ACT & ASSERT
        with pytest.raises(ValueError, match="No dependency groups found"):
            test_env.pyproject.dependencies.remove_from_group("nonexistent", ["some-package"])

    def test_remove_all_packages_from_group_deletes_group(self, test_env):
        """Should delete the group entirely if all packages are removed."""
        # ARRANGE
        config = test_env.pyproject.load()
        config.setdefault("dependency-groups", {})
        config["dependency-groups"]["optional-small"] = ["pillow>=9.0.0", "pyyaml>=5.0"]
        test_env.pyproject.save(config)

        # ACT: Remove all packages
        test_env.pyproject.dependencies.remove_from_group("optional-small", ["pillow", "pyyaml"])

        # ASSERT: Group should be deleted entirely
        groups = test_env.pyproject.dependencies.get_groups()
        assert "optional-small" not in groups

    def test_remove_packages_case_insensitive_matching(self, test_env):
        """Should match package names case-insensitively (PyPI convention)."""
        # ARRANGE
        config = test_env.pyproject.load()
        config.setdefault("dependency-groups", {})
        config["dependency-groups"]["optional-test"] = ["PyYAML>=5.0", "Pillow>=9.0.0"]
        test_env.pyproject.save(config)

        # ACT: Remove using lowercase names
        test_env.pyproject.dependencies.remove_from_group("optional-test", ["pyyaml", "pillow"])

        # ASSERT: Should match and remove despite case difference
        groups = test_env.pyproject.dependencies.get_groups()
        assert "optional-test" not in groups  # Should be deleted (empty)

    def test_remove_packages_with_markers(self, test_env):
        """Should handle removing packages that have environment markers."""
        # ARRANGE: Add packages with markers
        config = test_env.pyproject.load()
        config.setdefault("dependency-groups", {})
        config["dependency-groups"]["optional-platform"] = [
            "torch-cuda ; sys_platform == 'linux'",
            "torch-rocm ; sys_platform == 'linux'",
            "pillow>=9.0.0"
        ]
        test_env.pyproject.save(config)

        # ACT: Remove package by base name (without marker)
        test_env.pyproject.dependencies.remove_from_group("optional-platform", ["torch-cuda"])

        # ASSERT: Should match and remove package with marker
        groups = test_env.pyproject.dependencies.get_groups()
        assert "optional-platform" in groups
        assert len(groups["optional-platform"]) == 2
        # Check that torch-cuda entry is gone
        assert not any("torch-cuda" in pkg for pkg in groups["optional-platform"])
        assert "pillow>=9.0.0" in groups["optional-platform"]

    def test_node_removal_still_cleans_up_dependency_group(self, test_env):
        """Existing node removal behavior should continue to work (regression test)."""
        # ARRANGE: Simulate a node with a dependency group
        from comfygit_core.models.shared import NodeInfo

        node_info = NodeInfo(
            name="ComfyUI-TestNode",
            repository="https://github.com/test/ComfyUI-TestNode",
            version="abc123",
            source="registry"
        )

        # Add node (creates dependency group automatically)
        test_env.pyproject.nodes.add(node_info, "test-node")

        # Add dependencies to the auto-generated group
        config = test_env.pyproject.load()
        group_name = test_env.pyproject.nodes.generate_group_name(node_info, "test-node")
        config.setdefault("dependency-groups", {})
        config["dependency-groups"][group_name] = ["numpy>=1.20.0"]
        test_env.pyproject.save(config)

        # Verify setup
        groups = test_env.pyproject.dependencies.get_groups()
        assert group_name in groups

        # ACT: Remove the node
        removed = test_env.pyproject.nodes.remove("test-node")

        # ASSERT: Node's dependency group should be removed
        assert removed
        groups = test_env.pyproject.dependencies.get_groups()
        assert group_name not in groups
