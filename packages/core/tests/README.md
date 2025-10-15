# ComfyDock Core Testing Infrastructure

Testing architecture reference for comfydock-core integration tests.

## Overview

**Goals:** Fast (~7s full suite), isolated (tmpdir per test), realistic (real file ops), simple (minimal setup)

**Test Types:**
```
tests/
├── unit/           # Fast, isolated, mocked
├── integration/    # Realistic end-to-end
└── fixtures/       # Shared test data
```

**Design Philosophy:** Test through Core API, not CLI. Use `test_env.execute_commit()` directly rather than subprocess CLI calls for faster execution, better errors, and testing actual business logic.

## Fixture Hierarchy

```
test_workspace → test_env → test_models → YOUR TEST
```

- **`test_workspace`**: Workspace with config, models directory, metadata
- **`test_env`**: Environment with minimal ComfyUI structure (no clone!), git repo in `.cec/`
- **`test_models`**: Creates/indexes 4MB stub model files from `fixtures/models/test_models.json`

Fixtures are **function-scoped** for complete test isolation.

## Core Fixtures

### `test_workspace`
Creates isolated workspace with WorkspaceFactory initialization, configured models directory, metadata files, clean git state.

```python
def test_something(test_workspace):
    assert test_workspace.paths.root.exists()
    env = test_workspace.create_environment("my-env")
```

**Structure:**
```
{tmp}/comfydock_workspace/
├── .metadata/workspace.json
├── environments/
├── comfydock_cache/
└── models/
```

### `test_env`
Creates minimal environment without cloning ComfyUI (10x faster: 7.6s vs 60s).

```python
def test_something(test_env):
    assert test_env.comfyui_path.exists()
    status = test_env.status()
```

**Structure:**
```
environments/test-env/
├── .cec/
│   ├── .git/
│   ├── pyproject.toml
│   └── workflows/              # Committed workflows
└── ComfyUI/
    └── user/default/workflows/ # Active workflows (ComfyUI saves)
```

### `test_models`
Creates indexed model stubs. Returns dict with model metadata.

```python
def test_something(test_env, test_models):
    assert "photon_v1.safetensors" in test_models
    model = test_models["photon_v1.safetensors"]
```

### `workflow_fixtures` / `model_fixtures`
Path references to `fixtures/workflows/` and `fixtures/models/`.

**Available workflows:**
- `simple_txt2img.json` - Valid workflow
- `with_missing_model.json` - Missing model scenario

## Helper Functions

### `simulate_comfyui_save_workflow(env, name, workflow_data)`
Mimics ComfyUI saving workflow JSON (real file I/O, no mocks).

```python
workflow = load_workflow_fixture(workflow_fixtures, "simple_txt2img")
simulate_comfyui_save_workflow(test_env, "my_workflow", workflow)
```

### `load_workflow_fixture(fixtures_dir, name)`
Loads workflow JSON from fixtures as dict.

## Adding Tests

**Choose fixtures by need:**
```python
def test_workspace_level(test_workspace):      # Create envs, scan models
def test_env_level(test_env):                  # Test commits, status
def test_with_models(test_env, test_models):   # Test model resolution
```

**Test structure (AAA pattern):**
```python
def test_descriptive_name(self, test_env, test_models):
    """Clear description of behavior being tested."""
    # ARRANGE
    workflow = load_workflow_fixture(workflow_fixtures, "simple_txt2img")
    simulate_comfyui_save_workflow(test_env, "test", workflow)

    # ACT
    result = test_env.some_operation()

    # ASSERT
    assert result.property == expected, "Clear failure message"
```

## Common Patterns

**Workflow Lifecycle:**
```python
workflow = load_workflow_fixture(workflow_fixtures, "simple_txt2img")
simulate_comfyui_save_workflow(test_env, "my_wf", workflow)
status = test_env.status()
assert "my_wf" in status.workflow.sync_status.new

workflow_status = test_env.workflow_manager.get_workflow_status()
test_env.execute_commit(workflow_status, message="Add workflow")
assert (test_env.cec_path / "workflows/my_wf.json").exists()
```

**State Transitions:**
```python
# Initial state
status = test_env.status()
assert status.is_synced

# After workflow save
simulate_comfyui_save_workflow(test_env, "test", workflow)
status = test_env.status()
assert not status.is_synced
assert "test" in status.workflow.sync_status.new

# After commit
test_env.execute_commit(workflow_status, message="Commit")
status = test_env.status()
assert status.is_synced
```

**Error Conditions:**
```python
workflow = load_workflow_fixture(workflow_fixtures, "with_missing_model")
simulate_comfyui_save_workflow(test_env, "test", workflow)
status = test_env.status()
assert status.workflow.total_issues > 0
assert len(status.workflow.workflows_with_issues[0].resolution.models_unresolved) > 0
```

## Best Practices

**DO:**
- ✅ Use fixtures for common setup
- ✅ Assert with clear messages: `assert path.exists(), f"Expected {path}"`
- ✅ Test one thing per test
- ✅ Document expected failures with BUG references
- ✅ Use descriptive variable names

**DON'T:**
- ❌ Create duplicate fixtures (use existing `test_env`)
- ❌ Use absolute paths (use fixture paths)
- ❌ Mock core operations in integration tests
- ❌ Test CLI parsing (test business logic directly)
- ❌ Share state between tests (use function-scoped fixtures)

## Extending Fixtures

**Add workflow fixture:**
```bash
$ cat > tests/fixtures/workflows/my_workflow.json
```
Use with: `load_workflow_fixture(workflow_fixtures, "my_workflow")`

**Add model fixture:**
Add to `fixtures/models/test_models.json`, automatically created by `test_models` fixture.

**Create new fixture:**
Only if reusable across tests, complex setup, or expensive operation. Mark expensive ops with `scope="session"`.

## Quick Reference

**Running Tests:**
```bash
uv run pytest tests/integration/ -v              # All tests
uv run pytest tests/integration/test_file.py -v  # Specific file
uv run pytest path::TestClass::test_name -v      # Specific test
uv run pytest tests/integration/ -x              # Stop on failure
```

**Key Paths:**
```python
test_workspace.paths.root
test_env.path
test_env.comfyui_path
test_env.comfyui_path / "user/default/workflows"  # Active workflows
test_env.cec_path                                  # .cec directory
test_env.cec_path / "workflows"                    # Committed workflows
```

## Architecture Rationale

- **No ComfyUI clone:** Create directory structure only (10x faster)
- **Function-scoped fixtures:** Complete isolation, no shared state
- **Real file operations:** Tests actual behavior, catches real errors
