# Permission Handling in Docker Containers

> **Note**: These features are available in ComfyDock Docker images v1.1.0 and later.

ComfyDock now includes automatic permission checking and fixing tools to help resolve common file access issues when using Docker containers.

## Automatic Permission Checking

When a ComfyDock container starts, it automatically checks for permission issues on:

- Bind-mounted volumes
- ComfyUI directories (models, custom_nodes, input, output, etc.)

The check runs as the `comfy` user (UID 1000 by default) to ensure all necessary files are accessible.

### Permission Check Results

After the check completes, you'll see one of these messages:

- **✅ No permission issues found** - Everything is accessible
- **⚠️ Permission issues detected!** - Some files/directories need fixing

## Using the Fix-Permissions Tool

If permission issues are detected, you can use the built-in `fix-permissions` command:

1. **Access the container:**
    ```
    comfydock dev exec
    # Select running container from the list
    ```

2. **Run the fix command:**
    ```
    fix-permissions
    ```

3. **Review and confirm:**

    - The tool will show all affected files and directories
    - Current ownership will be displayed
    - You'll be asked to confirm before any changes are made

### What the Tool Does

- Changes ownership of problematic files to the `comfy` user (UID:GID 1000:1000)
- Creates an audit log of all changes
- Verifies the fixes were successful
- Only affects files with permission issues (not your entire filesystem)

### Example Output

```
=== ComfyDock Permission Fix Tool ===
This tool will fix permission issues for the comfy user (UID=1000, GID=1000)

⚠️  Permission issues found:
   - Directories: 2
   - Files: 15

The following items will have their ownership changed to comfy:comfy (1000:1000):

Directories:
  📁 /app/ComfyUI/models/checkpoints (current: 501:501)
  📁 /app/ComfyUI/custom_nodes/ComfyUI-Impact-Pack (current: 0:0)

Files:
  📄 /app/ComfyUI/models/checkpoints/sd_xl_base.safetensors (current: 501:501)
  ... and 14 more files

⚠️  WARNING: This will change ownership of the above files and directories!
Do you want to proceed? (yes/no): yes
```

## Environment Variables

You can control permission handling behavior using these environment variables:

### PERMISSION_CHECK_MODE
Controls when permission checks run:

- `startup` - Check on every container start
- `once`  (default) - Check only on first startup
- `never` - Disable permission checking

### SKIP_OWNERSHIP_FIX
- Set to `true` to skip automatic ownership changes when remapping UID/GID
- Useful if you want to handle permissions manually

### STRICT_PERMISSIONS
- Set to `true` to prevent container startup if permission issues are found
- Forces you to fix permissions before the container can run

### WANTED_UID / WANTED_GID
- Remap the comfy user to different UID/GID values
- Useful for matching your host user ID
- Example: `WANTED_UID=1001 WANTED_GID=1001`

## Common Permission Scenarios

### WSL Users
The default UID/GID (1000:1000) matches the first user created in most WSL distributions, so permissions should work automatically.

### Non-Standard User IDs
If your host user has a different UID/GID:
1. Set `WANTED_UID` and `WANTED_GID` when creating the environment
2. The container will remap the comfy user on startup
3. Use `fix-permissions` if needed after remapping

### Shared Model Directories
When multiple users share model directories:
1. Consider using group permissions on the host
2. Or use `fix-permissions` to standardize ownership
3. The audit log tracks all changes for accountability

## Troubleshooting Tips

1. **Permission denied errors persist:**

    - Check if the files are on a network drive or special filesystem
    - Ensure Docker has proper access to the host directories
    - Try running `fix-permissions` again

2. **Fix-permissions requires sudo:**

    - The command must run as root to change file ownership
    - This is normal and expected behavior

3. **Checking takes too long:**

    - Set `PERMISSION_CHECK_MODE=once` after initial setup
    - Or use `PERMISSION_CHECK_MODE=never` if you manage permissions manually

4. **Need to see what was changed:**

    - Check the audit log at `/var/log/comfydock/permission-fixes-*.log`
    - Download it with: `docker cp <container_name>:/var/log/comfydock/permission-fixes-*.log ./`