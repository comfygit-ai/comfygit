"""Integration tests for removing model sources from pyproject and SQLite index."""
from helpers.model_index_builder import ModelIndexBuilder


class TestModelSourceRemoval:
    """Test removing download sources from models."""

    def test_remove_source_from_model_in_both_stores(self, test_env, test_workspace):
        """Removing source should update both pyproject.toml and SQLite index."""
        # ARRANGE - Create and index a model
        builder = ModelIndexBuilder(test_workspace)
        builder.add_model(
            filename="sd15.safetensors",
            relative_path="checkpoints/sd15.safetensors",
            size_mb=4,
            category="checkpoints"
        )
        builder.index_all()

        # Get the actual hash from indexed model
        indexed_models = test_workspace.model_repository.get_all_models()
        indexed_model = next((m for m in indexed_models if m.filename == "sd15.safetensors"), None)
        assert indexed_model is not None, "Model should be indexed"
        model_hash = indexed_model.hash

        # Add model to pyproject
        from comfygit_core.models.manifest import ManifestModel
        manifest_model = ManifestModel(
            hash=model_hash,
            filename="sd15.safetensors",
            size=indexed_model.file_size,
            relative_path="checkpoints/sd15.safetensors",
            category="checkpoints",
            sources=[]
        )
        test_env.pyproject.models.add_model(manifest_model)

        # Add sources to both stores
        url1 = "https://civitai.com/api/download/models/12345"
        url2 = "https://huggingface.co/models/sd15.safetensors"
        test_env.add_model_source(model_hash, url1)
        test_env.add_model_source(model_hash, url2)

        # Verify sources exist in both stores
        model_before = test_env.pyproject.models.get_by_hash(model_hash)
        assert url1 in model_before.sources
        assert url2 in model_before.sources

        sources_before = test_workspace.model_repository.get_sources(model_hash)
        assert len(sources_before) == 2
        assert any(s['url'] == url1 for s in sources_before)
        assert any(s['url'] == url2 for s in sources_before)

        # ACT - Remove one source via repository API (currently doesn't exist - should fail)
        result = test_workspace.model_repository.remove_source(model_hash, url1)

        # ASSERT - Source removed from SQLite
        assert result is True, "remove_source should succeed"

        sources_after = test_workspace.model_repository.get_sources(model_hash)
        assert len(sources_after) == 1, f"Should have 1 source left, got {len(sources_after)}"
        assert not any(s['url'] == url1 for s in sources_after), "url1 should be removed"
        assert any(s['url'] == url2 for s in sources_after), "url2 should remain"

    def test_remove_nonexistent_source_returns_false(self, test_env, test_workspace):
        """Removing a source that doesn't exist should return False."""
        # ARRANGE - Create and index a model with one source
        builder = ModelIndexBuilder(test_workspace)
        builder.add_model(
            filename="model.safetensors",
            relative_path="checkpoints/model.safetensors",
            size_mb=4
        )
        builder.index_all()

        indexed_models = test_workspace.model_repository.get_all_models()
        model_hash = indexed_models[0].hash

        # Add one source
        test_workspace.model_repository.add_source(
            model_hash,
            "civitai",
            "https://civitai.com/api/download/models/123"
        )

        # ACT - Try to remove a source that doesn't exist
        result = test_workspace.model_repository.remove_source(
            model_hash,
            "https://nonexistent.com/model.safetensors"
        )

        # ASSERT - Should return False
        assert result is False, "Removing nonexistent source should return False"

        # Original source should still exist
        sources = test_workspace.model_repository.get_sources(model_hash)
        assert len(sources) == 1

    def test_remove_all_sources_from_model(self, test_env, test_workspace):
        """Removing all sources should leave model with empty sources list."""
        # ARRANGE - Create model with 3 sources
        builder = ModelIndexBuilder(test_workspace)
        builder.add_model(
            filename="model.safetensors",
            relative_path="checkpoints/model.safetensors",
            size_mb=4
        )
        builder.index_all()

        indexed_models = test_workspace.model_repository.get_all_models()
        model_hash = indexed_models[0].hash

        urls = [
            "https://civitai.com/api/download/models/1",
            "https://huggingface.co/models/model1.safetensors",
            "https://example.com/model.safetensors"
        ]

        for url in urls:
            test_workspace.model_repository.add_source(model_hash, "custom", url)

        # Verify 3 sources exist
        sources_before = test_workspace.model_repository.get_sources(model_hash)
        assert len(sources_before) == 3

        # ACT - Remove all sources one by one
        for url in urls:
            result = test_workspace.model_repository.remove_source(model_hash, url)
            assert result is True, f"Should successfully remove {url}"

        # ASSERT - No sources left
        sources_after = test_workspace.model_repository.get_sources(model_hash)
        assert len(sources_after) == 0, "All sources should be removed"

    def test_remove_source_by_hash_not_url(self, test_env, test_workspace):
        """Cannot remove source without specifying URL (need both hash and URL)."""
        # ARRANGE
        builder = ModelIndexBuilder(test_workspace)
        builder.add_model(
            filename="model.safetensors",
            relative_path="checkpoints/model.safetensors",
            size_mb=4
        )
        builder.index_all()

        indexed_models = test_workspace.model_repository.get_all_models()
        model_hash = indexed_models[0].hash

        # Add sources
        url1 = "https://civitai.com/api/download/models/1"
        url2 = "https://civitai.com/api/download/models/2"
        test_workspace.model_repository.add_source(model_hash, "civitai", url1)
        test_workspace.model_repository.add_source(model_hash, "civitai", url2)

        # Verify both exist
        sources = test_workspace.model_repository.get_sources(model_hash)
        assert len(sources) == 2

        # ACT - Remove specific URL only
        result = test_workspace.model_repository.remove_source(model_hash, url1)

        # ASSERT - Only url1 removed, url2 remains
        assert result is True
        sources_after = test_workspace.model_repository.get_sources(model_hash)
        assert len(sources_after) == 1
        assert sources_after[0]['url'] == url2

    def test_remove_source_preserves_other_model_sources(self, test_env, test_workspace):
        """Removing source from one model shouldn't affect other models."""
        # ARRANGE - Create two models with sources
        builder = ModelIndexBuilder(test_workspace)
        builder.add_model(
            filename="model1.safetensors",
            relative_path="checkpoints/model1.safetensors",
            size_mb=4
        )
        builder.add_model(
            filename="model2.safetensors",
            relative_path="checkpoints/model2.safetensors",
            size_mb=4
        )
        builder.index_all()

        indexed_models = test_workspace.model_repository.get_all_models()
        hash1 = next(m.hash for m in indexed_models if m.filename == "model1.safetensors")
        hash2 = next(m.hash for m in indexed_models if m.filename == "model2.safetensors")

        # Add sources to both models (same URL for both)
        same_url = "https://civitai.com/api/download/models/shared"
        test_workspace.model_repository.add_source(hash1, "civitai", same_url)
        test_workspace.model_repository.add_source(hash2, "civitai", same_url)

        # ACT - Remove source from model1 only
        result = test_workspace.model_repository.remove_source(hash1, same_url)

        # ASSERT - model1 has no sources, model2 still has source
        assert result is True
        sources1 = test_workspace.model_repository.get_sources(hash1)
        sources2 = test_workspace.model_repository.get_sources(hash2)

        assert len(sources1) == 0, "model1 sources should be removed"
        assert len(sources2) == 1, "model2 sources should remain"
        assert sources2[0]['url'] == same_url


class TestEnvironmentRemoveModelSource:
    """Test high-level Environment API for removing model sources."""

    def test_remove_source_via_environment_api(self, test_env, test_workspace):
        """Environment.remove_model_source() should update both stores."""
        # ARRANGE - Create and index a model
        builder = ModelIndexBuilder(test_workspace)
        builder.add_model(
            filename="model.safetensors",
            relative_path="checkpoints/model.safetensors",
            size_mb=4
        )
        builder.index_all()

        indexed_models = test_workspace.model_repository.get_all_models()
        model_hash = indexed_models[0].hash

        # Add model to pyproject
        from comfygit_core.models.manifest import ManifestModel
        manifest_model = ManifestModel(
            hash=model_hash,
            filename="model.safetensors",
            size=indexed_models[0].file_size,
            relative_path="checkpoints/model.safetensors",
            category="checkpoints",
            sources=[]
        )
        test_env.pyproject.models.add_model(manifest_model)

        # Add sources
        url1 = "https://civitai.com/api/download/models/1"
        url2 = "https://huggingface.co/models/model.safetensors"
        test_env.add_model_source(model_hash, url1)
        test_env.add_model_source(model_hash, url2)

        # ACT - Remove one source via environment API
        result = test_env.remove_model_source(model_hash, url1)

        # ASSERT - Success
        assert result.success, f"Should succeed: {result.error}"
        assert result.model_hash == model_hash
        assert result.url == url1

        # Check both stores updated
        model_after = test_env.pyproject.models.get_by_hash(model_hash)
        assert url1 not in model_after.sources, "url1 should be removed from pyproject"
        assert url2 in model_after.sources, "url2 should remain in pyproject"

        sources_after = test_workspace.model_repository.get_sources(model_hash)
        assert len(sources_after) == 1
        assert sources_after[0]['url'] == url2

    def test_remove_source_by_filename(self, test_env, test_workspace):
        """Should be able to remove source using filename instead of hash."""
        # ARRANGE
        builder = ModelIndexBuilder(test_workspace)
        builder.add_model(
            filename="unique_model.safetensors",
            relative_path="checkpoints/unique_model.safetensors",
            size_mb=4
        )
        builder.index_all()

        indexed_models = test_workspace.model_repository.get_all_models()
        model_hash = indexed_models[0].hash

        # Add to pyproject and add source
        from comfygit_core.models.manifest import ManifestModel
        manifest_model = ManifestModel(
            hash=model_hash,
            filename="unique_model.safetensors",
            size=indexed_models[0].file_size,
            relative_path="checkpoints/unique_model.safetensors",
            category="checkpoints",
            sources=[]
        )
        test_env.pyproject.models.add_model(manifest_model)

        test_url = "https://example.com/unique_model.safetensors"
        test_env.add_model_source(model_hash, test_url)

        # ACT - Remove using filename
        result = test_env.remove_model_source("unique_model.safetensors", test_url)

        # ASSERT
        assert result.success
        assert result.model_hash == model_hash

        model_after = test_env.pyproject.models.get_by_hash(model_hash)
        assert test_url not in model_after.sources

    def test_remove_nonexistent_url_returns_error(self, test_env, test_workspace):
        """Removing URL that doesn't exist should return error."""
        # ARRANGE
        builder = ModelIndexBuilder(test_workspace)
        builder.add_model(
            filename="model.safetensors",
            relative_path="checkpoints/model.safetensors",
            size_mb=4
        )
        builder.index_all()

        indexed_models = test_workspace.model_repository.get_all_models()
        model_hash = indexed_models[0].hash

        from comfygit_core.models.manifest import ManifestModel
        manifest_model = ManifestModel(
            hash=model_hash,
            filename="model.safetensors",
            size=indexed_models[0].file_size,
            relative_path="checkpoints/model.safetensors",
            category="checkpoints",
            sources=["https://civitai.com/api/download/models/1"]
        )
        test_env.pyproject.models.add_model(manifest_model)

        # ACT - Try to remove URL that doesn't exist
        result = test_env.remove_model_source(model_hash, "https://nonexistent.com/model.safetensors")

        # ASSERT
        assert not result.success
        assert result.error == "url_not_found"
        assert result.model_hash == model_hash

    def test_remove_from_nonexistent_model_returns_error(self, test_env):
        """Removing source from model that doesn't exist should return error."""
        # ACT
        result = test_env.remove_model_source("nonexistent_hash", "https://example.com/model.safetensors")

        # ASSERT
        assert not result.success
        assert result.error == "model_not_found"
