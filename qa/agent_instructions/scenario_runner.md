# Scenario Runner Instructions

You will be given a scenario file in YAML format. Your job is to execute it step by step.

## Scenario Format

Scenarios have this structure:

```yaml
name: Scenario name
description: What this scenario tests
category: workflow|node|model|collaboration|export

# Optional: Setup commands to prepare environment
setup:
  - command: cg init --name test-workspace
    description: Create a test workspace

# Main test steps
steps:
  - action: describe what you're doing
    command: cg env create production
    expect: Environment created successfully

  - action: another step
    command: cg node add comfyui-manager
    expect: Node installed
    on_failure: investigate  # or: skip, abort

# Optional: Cleanup
cleanup:
  - command: rm -rf /workspace/*
```

## How to Execute

1. **Read the entire scenario first** - understand the goal
2. **Execute setup commands** - prepare the environment
3. **Run each step in order:**
   - Run the command exactly as specified
   - Compare output to expected result
   - If `on_failure: investigate` - dig deeper before continuing
   - If `on_failure: skip` - note the failure and continue
   - If `on_failure: abort` - stop and report
4. **Run cleanup** - reset for next test
5. **Write report** - follow report format in base_system.md

## Decision Points

If a step says `explore:` instead of `command:`, you have freedom to:
- Run multiple commands to investigate
- Try variations to find edge cases
- Document what you tried and found

Example:
```yaml
- action: explore node conflict handling
  explore: |
    Try adding two nodes that provide the same functionality.
    Try adding incompatible version constraints.
    See how conflicts are reported and resolved.
```

## Error Handling

When you encounter an error:

1. **Capture the full error** - including traceback
2. **Check if it's expected** - does the scenario expect this?
3. **Try to determine root cause:**
   - Is it a bug in ComfyGit?
   - Is it a setup issue?
   - Is it a test design issue?
4. **Document your investigation** - what you tried to diagnose

## Timing

Note timing for operations that seem slow (>5 seconds):
```markdown
**Timing:** Command took 12.3 seconds (seems slow for this operation)
```

## State Verification

After important steps, verify state:
```bash
# After workspace creation
ls -la /workspace/
cat /workspace/.comfygit/config.json

# After node install
cg status

# After workflow sync
cg workflow list
```

## Starting a Scenario

When you begin, announce:
```
Starting scenario: {name}
Description: {description}
Timestamp: {datetime}
```

When complete:
```
Scenario complete: {name}
Status: {PASS/FAIL/PARTIAL}
Bugs found: {count}
Report: /reports/{filename}.md
```
