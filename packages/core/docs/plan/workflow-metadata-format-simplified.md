# Workflow Metadata Format Specification (Simplified)

## Overview
This document describes the simplified metadata format injected into ComfyUI workflows for model resolution and reproducibility.

## Core Principle
**Current state is the only state**. The metadata reflects what models the workflow currently uses and whether we can resolve them. No historical tracking.

## Location
Metadata MUST be stored in `workflow["extra"]["_comfydock_metadata"]`:
- ComfyUI preserves the `"extra"` field across save/load cycles
- Any data outside `"extra"` is deleted when ComfyUI saves
- The underscore prefix `_comfydock_metadata` minimizes collision risk

## Root Structure

```json
{
  "extra": {
    "_comfydock_metadata": {
      "version": "0.1.0",
      "last_updated": "2024-01-20T10:30:00Z",
      "models": {}
    }
  }
}
```

## Field Definitions

### version (string, required)
The metadata format version for forward compatibility.
- Format: Semantic versioning (MAJOR.MINOR.PATCH)
- Current: "0.1.0"

### last_updated (string, required)
ISO 8601 timestamp of last metadata update.
- Format: "YYYY-MM-DDTHH:MM:SSZ"
- Updated when: Track, sync, or model resolution changes

### models (object, required)
Maps node IDs to their model references. The core data structure.

```json
"models": {
  "16": {
    "node_type": "CheckpointLoaderSimple",
    "refs": [
      {
        "widget_index": 0,
        "path": "SD1.5/photon_v1.safetensors",
        "hash": "abc123def456",
        "sha256": null,
        "blake3": null,
        "sources": ["URL:https://my.custom.url/to_model.safetensors"]
      }
    ]
  },
  "23": {
    "node_type": "ttN tinyLoader",
    "refs": [
      {
        "widget_index": 0,
        "path": "FLUX/flux1-dev-fp8.safetensors",
        "hash": "def789ghi012",
        "hash": "jk123055",
        "sha256": null,
        "blake3": null,
        "sources": ["civitai:1234567"]
      },
      {
        "widget_index": 5,
        "path": "vae/ltx-video-vae.safetensors",
        "hash": "jafa1929",
        "sha256": null,
        "blake3": null,
        "sources": []
      }
    ]
  },
  "45": {
    "node_type": "CustomLoader",
    "refs": [
      {
        "widget_index": 2,
        "path": "models/unknown.pt",
        "hash": null,
        "sha256": null,
        "blake3": null,
        "sources": []
      }
    ]
  }
}
```

### Model Structure

#### models[node_id] Object:
- `node_type` (string): The ComfyUI node class name
- `refs` (array): List of model references from this node

#### Model Reference (refs array item):
- `widget_index` (integer): Position in widgets_values array
- `path` (string): Current path in the workflow widget (what's being used)
- `hash` (string|null): Model hash if resolved, null if unresolved
- `sha256` (string|null): SHA256 hash if previously computed for model, else null 
- `blake3` (string|null): BLAKE3 hash if previously computed for model, else null 
- `sources` (list[string]): Where model can be obtained: (empty list if no source info available, local only)
  - `"civitai:MODEL_ID"`: CivitAI model ID
  - `"huggingface:REPO/FILE"`: HuggingFace path
  - `"URL:<custom url>"`: suggested path to model file in custom repo

## Resolution States

### 1. Resolved Model
Model found in local index:
```json
{
  "widget_index": 0,
  "path": "checkpoints/model.safetensors",
  "hash": "abc123",
  "sha256": null,
  "blake3": null,
  "sources": []
}
```
We should also be tracking this model in our pyproject.toml for reproduction.

### 2. Unresolved Model
Model not found locally:
```json
{
  "widget_index": 0,
  "path": "missing/model.safetensors",
  "hash": null,
  "sha256": null,
  "blake3": null,
  "sources": []
}
```
Model is missing, and we should prompt the user on track/sync if they'd like to substitute/skip.

### 3. Resolved with Known Source
Model found locally with download source:
```json
{
  "widget_index": 0,
  "path": "checkpoints/model.safetensors",
  "hash": "abc123",
  "sha256": null,
  "blake3": null,
  "sources": ["civitai:12345"]
}
```

### 4. Unresolved and Skipped
Model not found locally, and user chose to skip model in prompt.
(will not ask user to resolve model on next sync unless model/node changes)
```json
{
  "widget_index": 0,
  "path": "checkpoints/model.safetensors",
  "hash": null,
  "sha256": null,
  "blake3": null,
  "sources": []
}
```
We should be tracking this model in our pyproject.toml, and ensure the given source matches our index, else update the source.

## Workflow Lifecycle

### 1. Initial Tracking
User tracks workflow with one resolved, one unresolved model:
CLI should warn user about unresolved models (no substitution in MVP).

```json
{
  "version": "0.1.0",
  "last_updated": "2024-01-20T10:00:00Z",
  "models": {
    "4": {
      "node_type": "CheckpointLoaderSimple",
      "refs": [
        {
          "widget_index": 0,
          "path": "checkpoints/sd15.ckpt",
          "hash": "abc123",
          "sha256": null,
          "blake3": null,
          "sources": []
        }
      ]
    },
    "7": {
      "node_type": "VAELoader",
      "refs": [
        {
          "widget_index": 0,
          "path": "missing_vae.safetensors",
          "hash": null,
          "sha256": null,
          "blake3": null,
          "sources": []
        }
      ]
    }
  }
}
```

### 2. On Next Sync
System sees both models resolved, no prompting needed. If user manually changed a model in ComfyUI:

```json
{
  "version": "0.1.0",
  "last_updated": "2024-01-20T15:00:00Z",
  "models": {
    "4": {
      "node_type": "CheckpointLoaderSimple",
      "refs": [
        {
          "widget_index": 0,
          "path": "checkpoints/new_checkpoint.safetensors",
          "hash": "gh12834",
          "sha256": null,
          "blake3": null,
          "sources": []
        }
      ]
    },
    "7": {
      "node_type": "VAELoader",
      "refs": [
        {
          "widget_index": 0,
          "path": "vae/good_vae.safetensors",
          "hash": "23565",
          "sha256": null,
          "blake3": null,
          "sources": []
        }
      ]
    }
  }
}
```

## Key Simplifications

### What We DON'T Track:
1. **Original values** - Current state is what matters
2. **Creation time** - Only last update matters
3. **Attempted paths** - Not needed for MVP

### What We DO Track:
1. **Current model paths** - What's in the workflow now
2. **Resolution status** - Hash present = resolved
3. **Widget positions** - For accurate updates
4. **Node types** - For context
5. **Sources** - For sharing/downloading

## Implementation Notes

### Reading Metadata
```python
def extract_metadata(workflow: dict) -> dict | None:
    return workflow.get("extra", {}).get("_comfydock_metadata")
```

### Checking Resolution Status
```python
def get_unresolved_models(metadata: dict) -> list:
    unresolved = []
    for node_id, node_data in metadata["models"].items():
        for ref in node_data["refs"]:
            if ref["hash"] is None:
                unresolved.append({
                    "node_id": node_id,
                    "node_type": node_data["node_type"],
                    "widget_index": ref["widget_index"],
                    "path": ref["path"]
                })
    return unresolved
```

## Migration Strategy

This simplified format is easier to migrate:

### Future 0.2.0
Might add:
- `size`: File size for validation
- `confidence`: How sure we are about resolution

```python
def migrate_0_1_to_0_2(metadata):
    metadata["version"] = "0.2.0"

    for node_data in metadata["models"].values():
        for ref in node_data["refs"]:
            ref.setdefault("size", None)

    return metadata
```

## Benefits of Simplified Format

1. **Smaller size** - Less data in workflow files
2. **Simpler logic** - No complex state tracking
3. **Clear semantics** - Current state only
4. **Easy debugging** - What you see is what you get
5. **Fast operations** - No history to maintain

## Example: Multi-Model Workflow

```json
{
  "extra": {
    "_comfydock_metadata": {
      "version": "0.1.0",
      "last_updated": "2024-01-20T16:30:00Z",
      "models": {
        "1": {
          "node_type": "CheckpointLoader",
          "refs": [
            {
              "widget_index": 0,
              "path": "checkpoints/v1-5-pruned.ckpt",
              "hash": "abc123",
              "source": "local"
            },
            {
              "widget_index": 1,
              "path": "configs/v1-inference.yaml",
              "hash": null,
              "source": null
            }
          ]
        },
        "8": {
          "node_type": "LoraLoader",
          "refs": [
            {
              "widget_index": 0,
              "path": "loras/style_lora.safetensors",
              "hash": "def456",
              "source": "civitai:78901"
            }
          ]
        },
        "15": {
          "node_type": "VAELoader",
          "refs": [
            {
              "widget_index": 0,
              "path": "vae/vae-ft-mse.safetensors",
              "hash": "ghi789",
              "source": "local"
            }
          ]
        }
      }
    }
  }
}
```

Note: The config file (index 1 of CheckpointLoader) has null hash because it's not tracked in model index.