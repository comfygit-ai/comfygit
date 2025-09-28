#!/usr/bin/env python3
"""Example usage of CivitAI client with workspace config integration."""

from pathlib import Path

from comfydock_core.clients.civitai_client import CivitAIClient
from comfydock_core.models.civitai import ModelType, SearchParams, SortOrder
from comfydock_core.repositories.workspace_config_repository import (
    WorkspaceConfigRepository,
)


def main():
    """Demonstrate CivitAI client usage."""

    # Example 1: Using client with workspace config, get path to this script's config file
    workspace_config = WorkspaceConfigRepository(
        config_file=Path(__file__).parent.parent.parent.parent / ".comfydock_workspace/.metadata/workspace.json"
    )

    # Set API token (would typically be done via CLI)
    # workspace_config.set_civitai_token("your-api-key-here")

    # Initialize client with workspace config
    client = CivitAIClient(workspace_config=workspace_config)

    # Example 2: Search for models
    print("Searching for anime LORA models...")
    search_params = SearchParams(
        query="anime",
        types=[ModelType.LORA],
        sort=SortOrder.MOST_DOWNLOADED,
        limit=5,
        nsfw=False,
    )

    response = client.search_models(search_params)
    for model in response.items:
        print(f"  - {model.name} (ID: {model.id}, Downloads: {model.download_count})")

    # Example 3: Get specific model details
    if response.items:
        # Use first search result for demo
        first_model_id = response.items[0].id
        model = client.get_model(first_model_id)
        if model:
            print(f"\nDetailed info for: {model.name}")
            print(f"Type: {model.type}")
            print(f"Creator: {model.creator.username if model.creator else 'Unknown'}")
            print(f"Tags: {', '.join(model.tags[:5]) if model.tags else 'None'}")

            # Get latest version info
            latest = model.get_latest_version()
            if latest:
                print(f"Latest Version: {latest.name}")
                # Don't show actual download URL with token
                print(f"Has download URL: {'Yes' if latest.download_url else 'No'}")

    # Example 4: Search by hash (useful for identifying already downloaded models)
    file_hash = "4ed40ee948a3df809b98a52f0c9d31f5103242e9185d4b45fd50141c381bc362"  # Example SHA256
    version = client.get_model_by_hash(file_hash)
    if version:
        print(f"\nFound model version by hash: {version.name}")
        if version.model:
            print(f"Model name: {version.model.name}, type: {version.model.type}")
        # Try get download url:
        download_url = client.get_download_url(version.id)
        print(f"Download URL: {download_url}")

    # Example 5: Iterator for large result sets
    print("\nIterating through all anime checkpoints...")
    count = 0
    for model in client.search_models_iter(
        types=[ModelType.CHECKPOINT], query="anime"
    ):
        print(f"  {count + 1}. {model.name}")
        count += 1
        if count >= 10:  # Limit for example
            break


if __name__ == "__main__":
    main()