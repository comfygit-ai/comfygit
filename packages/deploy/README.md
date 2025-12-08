# ComfyGit Deploy

Remote deployment and worker management CLI for ComfyGit.

## Installation

```bash
pip install comfygit-deploy
# or
uv tool install comfygit-deploy
```

## Usage

```bash
# Configure RunPod
cg-deploy runpod config --api-key <your-key>

# Deploy to RunPod
cg-deploy runpod deploy <git-url> --gpu "RTX 4090"

# Manage instances
cg-deploy instances
cg-deploy stop <instance-id>
cg-deploy terminate <instance-id>
```

See the [documentation](../../docs/comfygit-docs/) for full usage information.
