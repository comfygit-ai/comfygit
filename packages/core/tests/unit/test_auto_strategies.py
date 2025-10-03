"""Test auto resolution strategies."""
import pytest
from comfydock_core.strategies import AutoNodeStrategy, AutoModelStrategy
from comfydock_core.models.workflow import WorkflowNodeWidgetRef, ResolvedNodePackage
from comfydock_core.models.shared import ModelWithLocation
from comfydock_core.models.node_mapping import GlobalNodePackage


class TestAutoNodeStrategy:
    """Test automatic node resolution strategy."""

    def test_resolve_unknown_node_with_suggestions(self):
        """Should pick highest confidence suggestion."""
        strategy = AutoNodeStrategy()
        suggestions = [
            ResolvedNodePackage(
                package_id='node-b',
                package_data=GlobalNodePackage(
                    id='node-b', display_name='Node B', author=None, description=None,
                    repository=None, downloads=None, github_stars=None, rating=None,
                    license=None, category=None, tags=None, status=None, created_at=None, versions={}
                ),
                node_type='SomeNode',
                versions=[],
                match_type='exact',
                match_confidence=0.5
            ),
            ResolvedNodePackage(
                package_id='node-a',
                package_data=GlobalNodePackage(
                    id='node-a', display_name='Node A', author=None, description=None,
                    repository=None, downloads=None, github_stars=None, rating=None,
                    license=None, category=None, tags=None, status=None, created_at=None, versions={}
                ),
                node_type='SomeNode',
                versions=[],
                match_type='exact',
                match_confidence=0.9
            ),
            ResolvedNodePackage(
                package_id='node-c',
                package_data=GlobalNodePackage(
                    id='node-c', display_name='Node C', author=None, description=None,
                    repository=None, downloads=None, github_stars=None, rating=None,
                    license=None, category=None, tags=None, status=None, created_at=None, versions={}
                ),
                node_type='SomeNode',
                versions=[],
                match_type='exact',
                match_confidence=0.3
            ),
        ]

        result = strategy.resolve_unknown_node('SomeNode', suggestions)
        assert result.package_id == 'node-a'

    def test_resolve_unknown_node_with_tied_confidence(self):
        """Should pick first when confidence is tied."""
        strategy = AutoNodeStrategy()
        suggestions = [
            ResolvedNodePackage(
                package_id='node-a',
                package_data=GlobalNodePackage(
                    id='node-a', display_name='Node A', author=None, description=None,
                    repository=None, downloads=None, github_stars=None, rating=None,
                    license=None, category=None, tags=None, status=None, created_at=None, versions={}
                ),
                node_type='SomeNode',
                versions=[],
                match_type='exact',
                match_confidence=0.5
            ),
            ResolvedNodePackage(
                package_id='node-b',
                package_data=GlobalNodePackage(
                    id='node-b', display_name='Node B', author=None, description=None,
                    repository=None, downloads=None, github_stars=None, rating=None,
                    license=None, category=None, tags=None, status=None, created_at=None, versions={}
                ),
                node_type='SomeNode',
                versions=[],
                match_type='exact',
                match_confidence=0.5
            ),
        ]

        result = strategy.resolve_unknown_node('SomeNode', suggestions)
        assert result.package_id == 'node-a'

    def test_resolve_unknown_node_empty_suggestions(self):
        """Should return None for empty suggestions."""
        strategy = AutoNodeStrategy()
        result = strategy.resolve_unknown_node('SomeNode', [])
        assert result is None

    def test_confirm_node_install_always_true(self):
        """Should always confirm installation."""
        strategy = AutoNodeStrategy()
        pkg = ResolvedNodePackage(
            package_id='test',
            package_data=GlobalNodePackage(
                id='test', display_name='Test', author=None, description=None,
                repository=None, downloads=None, github_stars=None, rating=None,
                license=None, category=None, tags=None, status=None, created_at=None, versions={}
            ),
            node_type='TestNode',
            versions=[],
            match_type='exact',
            match_confidence=1.0
        )
        assert strategy.confirm_node_install(pkg) is True


class TestAutoModelStrategy:
    """Test automatic model resolution strategy."""

    def test_resolve_ambiguous_model_picks_first(self):
        """Should pick first candidate."""
        strategy = AutoModelStrategy()
        ref = WorkflowNodeWidgetRef(
            node_id='1',
            node_type='CheckpointLoader',
            widget_index=0,
            widget_value='model.safetensors'
        )

        candidates = [
            ModelWithLocation(
                hash='abc123',
                filename='model1.safetensors',
                file_size=1000,
                relative_path='checkpoints/model1.safetensors',
                mtime=1234567890.0,
                last_seen=1234567890
            ),
            ModelWithLocation(
                hash='def456',
                filename='model2.safetensors',
                file_size=2000,
                relative_path='checkpoints/model2.safetensors',
                mtime=1234567891.0,
                last_seen=1234567891
            ),
        ]

        result = strategy.resolve_ambiguous_model(ref, candidates)
        assert result == candidates[0]

    def test_resolve_ambiguous_model_empty_candidates(self):
        """Should return None for empty candidates."""
        strategy = AutoModelStrategy()
        ref = WorkflowNodeWidgetRef(
            node_id='1',
            node_type='CheckpointLoader',
            widget_index=0,
            widget_value='model.safetensors'
        )

        result = strategy.resolve_ambiguous_model(ref, [])
        assert result is None

    def test_handle_missing_model_returns_skip(self):
        """Should return skip action for missing models."""
        strategy = AutoModelStrategy()
        ref = WorkflowNodeWidgetRef(
            node_id='1',
            node_type='CheckpointLoader',
            widget_index=0,
            widget_value='missing.safetensors'
        )

        result = strategy.handle_missing_model(ref)
        assert result == ("skip", "")