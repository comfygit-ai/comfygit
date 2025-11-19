# ComfyDock Scripts

Utility scripts for ComfyDock development and workflow management.

## sync-env-to-collection.sh

Sync your active ComfyDock environment to an examples collection repository.

### Purpose

When developing ComfyDock example environments, you want to:
1. Work in ComfyDock with full `comfydock` command support
2. Test workflows in actual ComfyUI
3. Publish finished examples to a collection repository
4. Preserve custom documentation (README.md) in the examples repo

This script bridges the gap between development and publishing.

### What It Syncs

**Whitelisted items** (copied from `.cec/` to examples repo):
- `workflows/` - All workflow JSON files
- `pyproject.toml` - Environment definition
- `.python-version` - Python version
- `.gitignore` - Git ignore rules
- `uv.lock` - Dependency lock file

**Preserved items** (NOT touched in examples repo):
- `README.md` - Documentation you write in the examples repo
- Any other custom files or directories

### Usage

```bash
# Basic sync (stages changes, doesn't commit)
sync-env-to-collection <path-to-examples-repo>

# Sync and commit with message
sync-env-to-collection <path-to-examples-repo> -m "feat: add new workflow"
```

### Installation

```bash
# Make script available globally
ln -s ~/path/to/comfydock/scripts/sync-env-to-collection.sh ~/bin/sync-env-to-collection
# Or add to PATH
export PATH="$PATH:~/path/to/comfydock/scripts"
```

### Workflow Example

```bash
# 1. Create and develop environment in ComfyDock
comfydock create txt2img
comfydock activate txt2img
comfydock node add ComfyUI-Manager
comfyui  # Create workflows in web interface
comfydock commit -m "feat: initial setup"

# 2. Sync to examples repo (without commit)
sync-env-to-collection ~/comfydock-examples

# 3. Add documentation in examples repo
cd ~/comfydock-examples/txt2img
cat > README.md << 'EOF'
# Text-to-Image Example

This environment demonstrates basic text-to-image generation.

## Workflows

- `basic.json` - Simple text-to-image
- `advanced.json` - Advanced with ControlNet

## Setup

Import with:
```
comfydock import https://github.com/you/comfydock-examples#txt2img -n my-txt2img
```
EOF

# 4. Commit everything
git add txt2img
git commit -m "feat: add txt2img example with documentation"
git push origin main

# 5. Later: Update workflows in ComfyDock
comfydock activate txt2img
# Edit workflows in ComfyUI
comfydock commit -m "feat: add ControlNet workflow"

# 6. Sync updates (README preserved!)
sync-env-to-collection ~/comfydock-examples -m "feat: add ControlNet workflow"
cd ~/comfydock-examples
git push origin main
```

### Requirements

- Bash 4.0+
- `jq` (optional, falls back to grep/sed if not installed)
- Git (for examples repo tracking)

### Environment Variables

- `COMFYGIT_HOME` - ComfyDock workspace location (default: `~/.comfydock`)

### How It Works

1. Reads `$COMFYGIT_HOME/.metadata/workspace.json` to get active environment
2. Validates environment exists at `$COMFYGIT_HOME/environments/<env>/.cec`
3. Checks for uncommitted changes in `.cec/` (warns but continues if user confirms)
4. Creates target directory `<examples-repo>/<env-name>` if needed
5. Syncs only whitelisted files/directories from `.cec/`
6. Shows git diff of changes
7. Optionally commits if `-m` provided

### Name-Based Mapping

The script uses **environment name** as the **directory name** in examples repo:

```
ComfyDock:           Examples Repo:
txt2img       →      txt2img/
img2img       →      img2img/
video-gen     →      video-gen/
```

For nested structures, modify `EXAMPLES_DIR` in the script or use subdirectories in your examples repo path.

### Edge Cases

**Q: What if I have uncommitted changes in `.cec`?**
A: Script warns and asks for confirmation. You can continue to preview changes or cancel to commit first.

**Q: What if the examples repo isn't a git repo?**
A: Sync still works, but you won't get git tracking or commit functionality.

**Q: Can I sync to a subdirectory like `examples/txt2img`?**
A: Yes, just pass the full path: `sync-env-to-collection ~/repo/examples`

**Q: What about files not in the whitelist?**
A: They're ignored during sync. Add them to `SYNC_ITEMS` array in the script if needed.

### Troubleshooting

**"No active environment set"**
```bash
comfydock activate <environment-name>
```

**"No workspace.json found"**
```bash
# Check COMFYGIT_HOME is correct
echo $COMFYGIT_HOME
ls $COMFYGIT_HOME/.metadata/workspace.json
```

**"jq not found" (not an error, just FYI)**
```bash
# Optional: Install jq for cleaner JSON parsing
# macOS: brew install jq
# Ubuntu: apt install jq
# Script works without it using fallback parsing
```

### Future Enhancements

Potential improvements (not yet implemented):

- `--dry-run` flag to preview changes
- `--target <subdir>` to override environment name mapping
- Store default examples repo path in workspace config
- Pre-sync validation hooks
- Reverse sync (examples → .cec)

# Example Workflow: Creating a ComfyDock Examples Collection

Complete walkthrough of creating and maintaining a collection of ComfyDock example environments.

## Initial Setup

### 1. Create Examples Repository

```bash
# Create and initialize examples repository
mkdir ~/comfydock-examples
cd ~/comfydock-examples

git init
git remote add origin git@github.com:yourusername/comfydock-examples.git

# Create main README
cat > README.md << 'EOF'
# ComfyDock Examples

Collection of ready-to-use ComfyUI environment examples.

## Available Examples

- [txt2img](txt2img/) - Text-to-image generation workflows
- [img2img](img2img/) - Image-to-image transformation
- [video-gen](video-gen/) - Video generation with AnimateDiff

## Usage

Import any example with:

```bash
comfydock import https://github.com/yourusername/comfydock-examples#<example-name> -n my-env
```

For example:
```bash
comfydock import https://github.com/yourusername/comfydock-examples#txt2img -n my-txt2img
```
EOF

git add README.md
git commit -m "docs: initial README"
git push -u origin main
```

### 2. Install Sync Script

```bash
# Make script globally available
ln -s ~/projects/comfydock/scripts/sync-env-to-collection.sh ~/bin/sync-env-to-collection
chmod +x ~/bin/sync-env-to-collection

# Test it's accessible
which sync-env-to-collection
```

## Creating Your First Example

### Step 1: Develop in ComfyDock

```bash
# Create environment
comfydock create txt2img
comfydock activate txt2img

# Add nodes you need
comfydock node add ComfyUI-Manager
comfydock node add https://github.com/pythongosssss/ComfyUI-Custom-Scripts

# Download models
comfydock model download "sd_xl_base_1.0.safetensors"

# Test in ComfyUI
comfyui
# Create and test your workflows in the web interface
# Save workflows in ComfyUI (they auto-save to .cec/workflows/)

# Commit your work
comfydock commit -m "feat: initial txt2img setup"
```

### Step 2: Sync to Examples Repo

```bash
# Sync without committing (preview first)
sync-env-to-collection ~/comfydock-examples

# You'll see:
# ✓ Active environment: txt2img
# ✓ Content synced
# 📝 Changes detected:
#  ?? txt2img/
# ℹ️  Changes ready. To commit: ...
```

### Step 3: Add Documentation

```bash
# Go to examples repo
cd ~/comfydock-examples/txt2img

# Create README for this example
cat > README.md << 'EOF'
# Text-to-Image Example

Basic text-to-image generation using SDXL.

## Included Workflows

### basic-txt2img.json
Simple text-to-image generation with minimal settings.

**Usage:**
1. Load workflow in ComfyUI
2. Edit the positive prompt
3. Queue prompt

### advanced-txt2img.json
Advanced workflow with:
- Multiple samplers comparison
- ControlNet integration
- Upscaling post-processing

## Requirements

- SDXL base model (auto-downloaded on import)
- 8GB+ VRAM recommended

## Import

```bash
comfydock import \
  https://github.com/yourusername/comfydock-examples#txt2img \
  -n my-txt2img
```

## Nodes Used

- ComfyUI-Manager - Node management
- ComfyUI-Custom-Scripts - Quality of life improvements

All nodes automatically installed on import.
EOF

# Check what we have
ls -la
# Output:
# .gitignore
# .python-version
# pyproject.toml
# README.md  (your documentation)
# uv.lock
# workflows/
```

### Step 4: Commit and Push

```bash
# Back to repo root
cd ~/comfydock-examples

# Review all changes
git status
git diff txt2img

# Commit everything
git add txt2img
git commit -m "feat: add txt2img example with documentation"
git push origin main

# Now users can import your example!
```

## Adding More Examples

### Create Second Example

```bash
# Create in ComfyDock
comfydock create img2img
comfydock activate img2img

# Set it up
comfydock node add ComfyUI-Advanced-ControlNet
# ... develop workflows ...
comfydock commit -m "feat: img2img setup"

# Sync and commit in one step
sync-env-to-collection ~/comfydock-examples -m "feat: add img2img example"

# Add README
cd ~/comfydock-examples/img2img
vim README.md

# Update main index
cd ~/comfydock-examples
# (README.md already lists img2img)
git add .
git commit -m "docs: add img2img README"
git push origin main
```

## Updating Existing Examples

### Scenario: Add New Workflow to txt2img

```bash
# Switch to environment
comfydock activate txt2img

# Create new workflow in ComfyUI
comfyui
# ... create advanced-controlnet.json workflow ...

# Commit in ComfyDock
comfydock commit -m "feat: add ControlNet workflow"

# Sync to examples (README preserved!)
sync-env-to-collection ~/comfydock-examples -m "feat: add ControlNet workflow to txt2img"

# Optionally update README
cd ~/comfydock-examples/txt2img
# Edit README.md to document new workflow
vim README.md

cd ~/comfydock-examples
git add txt2img/README.md
git commit -m "docs: document ControlNet workflow"
git push origin main
```

### Scenario: Update Dependencies

```bash
comfydock activate txt2img

# Add new node
comfydock node add https://github.com/new/node

# Update pyproject.toml
comfydock commit -m "feat: add new node dependency"

# Sync (pyproject.toml updated, README preserved)
sync-env-to-collection ~/comfydock-examples -m "feat: add new node to txt2img"

cd ~/comfydock-examples
git push origin main
```

## Repository Structure

After creating several examples:

```
comfydock-examples/
├── README.md                      # Main index
├── txt2img/
│   ├── README.md                  # Example docs (you write this)
│   ├── pyproject.toml             # Synced from .cec
│   ├── .python-version            # Synced from .cec
│   ├── .gitignore                 # Synced from .cec
│   ├── uv.lock                    # Synced from .cec
│   └── workflows/                 # Synced from .cec
│       ├── basic.json
│       └── advanced.json
├── img2img/
│   ├── README.md
│   ├── pyproject.toml
│   └── workflows/
└── video-gen/
    ├── README.md
    ├── pyproject.toml
    └── workflows/
```

## Daily Workflow Summary

```bash
# Morning: Start working on example
comfydock activate txt2img
comfyui  # Develop workflows

# Throughout day: Make commits
comfydock commit -m "wip: testing new approach"
comfydock commit -m "feat: add advanced workflow"

# End of day: Publish when ready
sync-env-to-collection ~/comfydock-examples -m "feat: add advanced workflow"
cd ~/comfydock-examples
git push origin main
```

## Tips

1. **Commit often in ComfyDock** - Your local `.cec` history is separate from examples repo
2. **README is sacred** - Script never overwrites your documentation
3. **Preview first** - Run sync without `-m` to see what changes before committing
4. **Keep examples focused** - One environment = one clear use case
5. **Document workflows** - Explain what each workflow does in README
6. **Test imports** - Occasionally import your own examples to verify they work

## What Users See

When users import your example:

```bash
comfydock import \
  https://github.com/yourusername/comfydock-examples#txt2img \
  -n my-txt2img
```

They get:
- ✅ ComfyUI installed
- ✅ All nodes from pyproject.toml
- ✅ Python environment set up
- ✅ Workflows ready to use
- ✅ Models auto-resolved (if sources in pyproject.toml)

They DON'T get:
- ❌ Your local `.cec/.git` history
- ❌ Your development commits
- ❌ Models (unless configured in pyproject.toml)

Fresh, clean environment ready to use!
