"""Tests for interactive strategy optional dependency support (Phase 2)."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from comfydock_cli.strategies.interactive import InteractiveModelStrategy, InteractiveNodeStrategy
from comfydock_core.models.workflow import WorkflowNodeWidgetRef, ScoredMatch
from comfydock_core.models.shared import ModelWithLocation


class TestInteractiveModelStrategyOptional:
    """Test optional model resolution in interactive strategy."""

    def test_handle_missing_model_with_optional_choice(self):
        """Test that user can mark missing model as optional (Type 1)."""
        strategy = InteractiveModelStrategy()

        ref = WorkflowNodeWidgetRef(
            node_id="11",
            widget_index=0,
            widget_value="rife49.pth",
            node_type="RIFE VFI"
        )

        # Mock user input: 'o' for optional
        with patch('builtins.input', return_value='o'), \
             patch('builtins.print'):
            result = strategy.handle_missing_model(ref)

        # Should return optional_unresolved action
        assert result == ("optional_unresolved", "")

    def test_handle_missing_model_fuzzy_results_with_optional(self):
        """Test optional choice when fuzzy results are shown."""
        mock_search = Mock(return_value=[
            ScoredMatch(
                model=ModelWithLocation(
                    hash="abc123",
                    filename="similar.safetensors",
                    file_size=4194304,
                    relative_path="checkpoints/similar.safetensors",
                    mtime=1234567890.0,
                    last_seen=1234567890
                ),
                score=0.7,
                confidence="good"
            )
        ])

        strategy = InteractiveModelStrategy(search_fn=mock_search)

        ref = WorkflowNodeWidgetRef(
            node_id="5",
            widget_index=0,
            widget_value="missing.safetensors",
            node_type="CheckpointLoaderSimple"
        )

        # Mock user input: 'o' for optional (from fuzzy results)
        with patch('builtins.input', return_value='o'), \
             patch('builtins.print'):
            result = strategy.handle_missing_model(ref)

        assert result == ("optional_unresolved", "")

    def test_resolve_ambiguous_model_with_optional_choice(self):
        """Test marking ambiguous model as optional nice-to-have (Type 2)."""
        strategy = InteractiveModelStrategy()

        ref = WorkflowNodeWidgetRef(
            node_id="7",
            widget_index=1,
            widget_value="lora.safetensors",
            node_type="LoraLoader"
        )

        candidates = [
            ModelWithLocation(
                hash="def456",
                filename="lora_v1.safetensors",
                file_size=143000000,
                relative_path="loras/lora_v1.safetensors",
                mtime=1234567890.0,
                last_seen=1234567890
            ),
            ModelWithLocation(
                hash="ghi789",
                filename="lora_v2.safetensors",
                file_size=143000000,
                relative_path="loras/lora_v2.safetensors",
                mtime=1234567890.0,
                last_seen=1234567890
            )
        ]

        # Mock user input: 'o' then '1' to select first candidate
        with patch('builtins.input', side_effect=['o', '1']), \
             patch('builtins.print'):
            result = strategy.resolve_ambiguous_model(ref, candidates)

        # Should return selected model with optional marker
        assert result is not None
        assert result.filename == "lora_v1.safetensors"
        assert hasattr(result, '_mark_as_optional')
        assert result._mark_as_optional is True

    def test_resolve_ambiguous_model_required_choice(self):
        """Test that 'r' choice marks model as required (existing behavior)."""
        strategy = InteractiveModelStrategy()

        ref = WorkflowNodeWidgetRef(
            node_id="3",
            widget_index=0,
            widget_value="model.safetensors",
            node_type="CheckpointLoaderSimple"
        )

        candidates = [
            ModelWithLocation(
                hash="xyz123",
                filename="model.safetensors",
                file_size=4194304,
                relative_path="checkpoints/model.safetensors",
                mtime=1234567890.0,
                last_seen=1234567890
            )
        ]

        # Mock user input: just '1' (numeric choice defaults to required)
        with patch('builtins.input', return_value='1'), \
             patch('builtins.print'):
            result = strategy.resolve_ambiguous_model(ref, candidates)

        # Should return model without optional marker
        assert result is not None
        assert result.filename == "model.safetensors"
        assert not hasattr(result, '_mark_as_optional')

    def test_resolve_ambiguous_model_numeric_defaults_to_required(self):
        """Test that numeric choice (backwards compat) defaults to required."""
        strategy = InteractiveModelStrategy()

        ref = WorkflowNodeWidgetRef(
            node_id="3",
            widget_index=0,
            widget_value="model.safetensors",
            node_type="CheckpointLoaderSimple"
        )

        candidates = [
            ModelWithLocation(
                hash="xyz123",
                filename="model.safetensors",
                file_size=4194304,
                relative_path="checkpoints/model.safetensors",
                mtime=1234567890.0,
                last_seen=1234567890
            )
        ]

        # Mock user input: '1' directly (old behavior)
        with patch('builtins.input', return_value='1'), \
             patch('builtins.print'):
            result = strategy.resolve_ambiguous_model(ref, candidates)

        # Should return model without optional marker (backwards compatible)
        assert result is not None
        assert result.filename == "model.safetensors"
        assert not hasattr(result, '_mark_as_optional')


class TestInteractiveNodeStrategyOptional:
    """Test optional node resolution in interactive strategy."""

    def test_resolve_ambiguous_node_with_optional_choice(self):
        """Test that user can mark ambiguous node as optional."""
        from comfydock_core.models.workflow import ResolvedNodePackage

        strategy = InteractiveNodeStrategy()

        node_type = "JWIntegerDiv"
        possible = [
            ResolvedNodePackage(
                package_id="comfy-literals",
                package_data=None,
                node_type=node_type,
                versions=[],
                match_type="registry",
                match_confidence=0.9
            ),
            ResolvedNodePackage(
                package_id="comfyui-logic",
                package_data=None,
                node_type=node_type,
                versions=[],
                match_type="registry",
                match_confidence=0.8
            )
        ]

        # Mock user input: 'o' for optional
        with patch('builtins.input', return_value='o'), \
             patch('builtins.print'):
            result = strategy.resolve_unknown_node(node_type, possible)

        # Should return None (skip resolution - will be marked optional in pyproject)
        assert result is None

    def test_resolve_unknown_node_no_matches_with_optional(self):
        """Test that user can mark unknown node as optional when no matches found."""
        strategy = InteractiveNodeStrategy()

        node_type = "MyCustomNode"
        possible = []  # No matches

        # Mock user input: 'o' for optional
        with patch('builtins.input', return_value='o'), \
             patch('builtins.print'):
            result = strategy.resolve_unknown_node(node_type, possible)

        # Should return None (skip resolution)
        assert result is None

    def test_resolve_unknown_node_search_results_with_optional(self):
        """Test optional choice from search results."""
        from comfydock_core.models.workflow import ResolvedNodePackage

        mock_search = Mock(return_value=[
            ResolvedNodePackage(
                package_id="similar-package",
                package_data=None,
                node_type="SearchResult",
                versions=[],
                match_type="search",
                match_confidence=0.7
            )
        ])

        strategy = InteractiveNodeStrategy(search_fn=mock_search)

        node_type = "UnknownNode"
        possible = []  # No direct matches, will trigger search

        # Mock user input: 'o' for optional (from search results)
        with patch('builtins.input', return_value='o'), \
             patch('builtins.print'):
            result = strategy.resolve_unknown_node(node_type, possible)

        # Should return None (skip resolution)
        assert result is None
