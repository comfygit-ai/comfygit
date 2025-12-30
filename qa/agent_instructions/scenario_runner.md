# Scenario Runner Instructions

You will be given a scenario file in YAML format. Your job is to execute it step by step.

## Scenario Format

Scenarios have this structure:

```yaml
name: Scenario name
description: What this scenario tests
category: workspace|workflow|node|model|collaboration|export
priority: critical|high|medium|low

# Requirements (informational - verify before running)
requirements:
  comfygit: ">=0.3.0"
  disk_space: "500MB"
  network: true

# Setup - runs before main steps
setup:
  - command: rm -rf /workspace/*
    description: Clean workspace
    ignore_errors: true  # Don't fail if cleanup fails

# Main test steps
steps:
  - action: What you're testing
    command: cg env create production
    expect: Should create environment successfully
    on_failure: investigate  # or: skip, abort, document
    timeout: 60  # seconds
    verify:  # Commands to run after step
      - "ls -la /workspace/"
      - "cg status"

  - action: Explore edge cases
    explore: |
      Try variations:
      1. What if name has spaces?
      2. What if already exists?

# Cleanup - runs after steps complete
cleanup:
  - command: rm -rf /workspace/*
    ignore_errors: true
```

## Execution Protocol

### 1. Announce the Scenario

When you begin, output:
```
=== Starting Scenario ===
Name: {scenario_name}
Description: {description}
Category: {category}
Priority: {priority}
Steps: {count}
Timestamp: {current datetime}
```

### 2. Run Setup Steps

Execute each setup command in order. These prepare the environment:
- Commands with `ignore_errors: true` continue on failure
- Commands without it will abort if they fail
- Note any warnings but don't include in main report

### 3. Execute Main Steps

For each step:

1. **Announce the step:**
   ```
   --- Step {n}: {action} ---
   ```

2. **Run the command** (if `command:` specified):
   - Execute exactly as written
   - Capture full stdout and stderr
   - Note exit code
   - Time the operation

3. **Execute exploration** (if `explore:` specified):
   - Read the exploration prompt
   - Devise 3-5 specific tests
   - Execute each and document results
   - Focus on finding real bugs, not just checking boxes

4. **Run verification commands** (if `verify:` specified):
   - Execute each verification command
   - Document outputs
   - Use to confirm step succeeded

5. **Handle failures** based on `on_failure`:
   - `investigate`: Dig deeper, run diagnostic commands, then continue
   - `skip`: Note failure, move to next step
   - `abort`: Stop scenario, generate partial report
   - `document`: Expected failure, just record it

6. **Determine status:**
   - **PASS**: Command succeeded, output matches expectations
   - **FAIL**: Command failed or output wrong
   - **INVESTIGATE**: Unclear result, needs human review

### 4. Run Cleanup

Execute cleanup commands to reset state. Always run cleanup even if main steps failed.

### 5. Generate Report

Create the markdown report at the path specified in your prompt. Include:
- All step results
- All findings (bugs, UX issues)
- Test recommendations

## Decision Points

### When to PASS a step:
- Exit code 0 (or appropriate for the operation)
- Output is reasonable (doesn't have to exactly match `expect:`)
- No unexpected errors or warnings

### When to FAIL a step:
- Non-zero exit code when success expected
- Traceback or crash
- Output contradicts expectations
- Data corruption or loss

### When to mark INVESTIGATE:
- Ambiguous output
- Step succeeded but behavior seems wrong
- Performance was unexpectedly slow
- Output different from expected but might be correct

## Handling Errors

When you encounter an error:

1. **Capture full error:**
   ```bash
   # Run command and capture everything
   command_here 2>&1
   echo "Exit code: $?"
   ```

2. **Check if expected:**
   - Does scenario say `on_failure: document`?
   - Is this testing error handling?

3. **Investigate if warranted:**
   - Run `cg status` to see current state
   - Check logs: `cat ~/.comfygit/logs/latest.log 2>/dev/null`
   - Try simpler version of command

4. **Document findings:**
   - What command failed
   - Full error output
   - What you tried to diagnose
   - Your assessment (bug vs. expected vs. user error)

## Timing Guidelines

Note timing for operations and flag if unusual:

| Operation | Expected | Flag If |
|-----------|----------|---------|
| `cg init` | <2s | >10s |
| `cg env create` | 30-120s | >300s |
| `cg node add` | 10-60s | >180s |
| `cg status` | <5s | >30s |
| `cg workflow sync` | 10-60s | >180s |

Example timing note:
```markdown
**Timing:** 45.2s (normal for environment creation)
```
or
```markdown
**Timing:** 312.5s - SLOW (expected <120s for env create)
```

## Example Step Execution

```markdown
--- Step 3: Create production environment ---

**Command:**
```bash
cg env create production
```

**Expected:** Environment should be created with ComfyUI installed

**Actual:**
```
Creating environment 'production'...
Cloning ComfyUI from https://github.com/comfyanonymous/ComfyUI...
Cloning into '/workspace/.comfygit/environments/production/ComfyUI'...
Installing dependencies...
Environment 'production' created successfully.
```

**Exit code:** 0
**Duration:** 67.3s

**Verification:**
```bash
$ ls -la /workspace/.comfygit/environments/
total 12
drwxr-xr-x 3 root root 4096 Dec 30 15:32 .
drwxr-xr-x 3 root root 4096 Dec 30 15:31 ..
drwxr-xr-x 4 root root 4096 Dec 30 15:32 production

$ cg env list
Environments:
  production (active)
```

**Status:** PASS
```

## Scenario Completion

When done:

```
=== Scenario Complete ===
Name: {scenario_name}
Status: PASS | FAIL | PARTIAL
Steps: {passed}/{total} passed
Bugs found: {count}
Report: {report_path}
Duration: {total_time}s
```

Then:
1. Save your report to the specified path
2. Verify it was written: `ls -la {report_path}`
3. If cleanup wasn't run, clean up manually: `rm -rf /workspace/*`
