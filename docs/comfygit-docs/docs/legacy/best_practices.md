# Best Practices

## Windows and WSL

ComfyDock is designed to work seamlessly with WSL (Windows Subsystem for Linux). This allows you to run Dockerized ComfyUI environments with better performance than you’d typically see when storing everything on a Windows drive. Below are some recommended steps and tips for setting up WSL, configuring it, and saving your models in WSL to reduce loading times.

### Setting up WSL

1. **Install WSL**

    - On Windows 10/11, open PowerShell as Administrator and run:

        ```
        wsl --install -d Ubuntu
        ```
    
    - Alternatively, open the **Microsoft Store**, search for “Ubuntu” (or your preferred distro), and click **Install**.
    
2. **Update WSL & Packages**

    - Once installed, open Ubuntu from the Start menu. Then run:

        ```
        sudo apt-get update && sudo apt-get upgrade -y
        ```

3. **Check Your WSL Version**

    - Ensure you’re using WSL2 for the best compatibility and performance:

        ```
        wsl --set-version <distro-name> 2
        ```
        Replace <distro-name> with the name of your distro (e.g. Ubuntu).

4. **Install Docker Desktop**

    - Install Docker Desktop for Windows, enable “Use the WSL 2 based engine” in the Docker settings, and integrate it with your Ubuntu distro.


### Configure WSL Config

If you plan on running resource-heavy tasks (e.g., large model inference) in WSL, it’s best to grant WSL more CPU cores and RAM. You can do this by creating or editing the .wslconfig file in your Windows home directory (%USERPROFILE%):

```
[wsl2]
memory=8GB       # Adjust as needed
processors=4     # Number of CPU cores to allocate
```

1. **Locate Home Directory**

    In File Explorer, go to ```%USERPROFILE%```.

2. **Check if .wslconfig Exists**

    - If it doesn’t, create a new text file named ```.wslconfig```.

3. **Restart WSL**

```
wsl --shutdown
wsl
```

3. **Verify Changes**

    Inside WSL:

```
htop
# or
cat /proc/meminfo
```
    
Confirm you see the updated RAM/CPU limits.


### Saving Models in WSL

- **Performance Gains**: Storing model checkpoints inside the WSL filesystem significantly reduces load times compared to storing them on a Windows (C:, D:, etc.) drive.

- **Folder Paths**: You might store your models at ```/home/<username>/ComfyUI/models.```

- **Access WSL from Windows Explorer:**

```
\\wsl.localhost\<distro-name>\home\<username>\ComfyUI\models
```
Replace ```<distro-name>``` with your actual distro name (e.g., Ubuntu).

**Why Do This?**

Reading large models from Windows drives can cause slowdowns due to file system translations. Keeping models in WSL’s native file system lets Docker containers access them much faster.

---

## Automatic Permission Handling

> **New in v1.1.0+**: ComfyDock Docker images now include automatic permission checking and fixing tools.

### How It Works

ComfyDock containers automatically check file permissions on startup to ensure the `comfy` user (UID 1000) can access all necessary files. This is especially helpful when:

- Using bind-mounted directories from your host system
- Sharing model directories between multiple users
- Working with files created by different users or processes

### Default Behavior

By default, ComfyDock containers:

1. Check permissions on all bind-mounted volumes and ComfyUI directories
2. Display a summary of any permission issues found
3. Suggest using the `fix-permissions` command if issues are detected
4. Continue running even if permission issues exist

### Quick Permission Fix

If you encounter permission issues:

```
# Access the running container
comfydock dev exec

# Run the permission fix tool
fix-permissions
```

The tool will:

- Show all files and directories with permission issues
- Ask for confirmation before making changes
- Create an audit log of all modifications
- Verify the fixes were successful

### Customizing Permission Behavior

You can control permission handling with environment variables:

- `PERMISSION_CHECK_MODE=once` - Only check permissions on first startup
- `PERMISSION_CHECK_MODE=never` - Disable automatic permission checking
- `STRICT_PERMISSIONS=true` - Prevent container startup if permission issues exist

For more details, see the [Permission Handling](troubleshooting/permission_handling.md) documentation.

---

## Editing Files in Containers

Sometimes you'll need to modify or update files that live inside your Dockerized ComfyUI environment. Since many files are not necessarily mounted to the Windows host filesystem, you may need to access them directly within the container.

### Where ComfyUI is stored

- By default, when using ComfyDock, ComfyUI is installed to ```/app/ComfyUI``` inside the container.

- If you created a WSL-based environment, you might also have a copy under ```/home/<username>/ComfyUI``` or wherever you specified during environment creation.

### How to Edit Files

1. **ComfyDock Dev Exec (Recommended)**

    The easiest way to access a running container is using the ComfyDock CLI:

    ```bash
    comfydock dev exec
    ```

    This will list all running containers and let you select which one to access. You'll enter as the **root user**.

    **⚠️ Important:** Files created or modified as root may become inaccessible to the container's `comfy` user. Always fix permissions after making changes:
    
    ```bash
    # For single files
    chown comfy:comfy /path/to/file
    
    # For directories
    chown -R comfy:comfy /path/to/directory
    ```

2. **Docker Desktop Exec**

    -  Go to **Docker Desktop** → find the container for your ComfyUI environment.

    - Click the container → **Exec** tab → open a shell.

    - You can now browse or edit files via command-line text editors like ```nano``` or ```vim```.

3. **VSCode Dev Containers**

    - Install the "Dev Containers" extension in VSCode.

    - Make sure your container is running, then press **F1** (Command Palette) → "Dev Containers: Attach to Running Container".

    - Select your container (not the ```…-frontend``` one).

    - Once attached, you can open a folder (```/app/ComfyUI```) in VSCode and edit files graphically.

### Install Custom Nodes

To install custom nodes inside the container:

1. **Access the Container**
    ```
    comfydock dev exec
    # Select your running container
    ```

2. **Navigate to Custom Nodes Directory**
    ```
    cd /app/ComfyUI/custom_nodes
    ```

3. **Clone the Node Repo**
```
git clone <custom_node_repo>
cd <custom_node_directory>
uv pip install -r requirements.txt
```
Replace ```<custom_node_repo>``` with the GitHub URL.

4. **Fix Permissions (Important!)**

    Since you cloned as root, fix the ownership:
    
    ```bash
    chown -R comfy:comfy /app/ComfyUI/custom_nodes/<custom_node_directory>
    ```

5. **(Optional) Reload ComfyUI**

    - If ComfyUI was running in the container and you have [HotReloadHack](https://github.com/logtd/ComfyUI-HotReloadHack) installed, it may automatically pick up the new custom node. Otherwise, restart ComfyUI.

### Developing in Containers

1. **Attach with VSCode**

    - This is the most convenient method for quickly editing and testing.

2. **HotReloadHack**

    - For faster iteration when writing or debugging custom nodes, consider installing the [HotReloadHack](https://github.com/logtd/ComfyUI-HotReloadHack). This lets ComfyUI detect changes without a full restart.

3. **Environment Duplication**

    - Before trying out new or experimental custom nodes, clone your environment via ComfyDock. If things break, you still have your original environment untouched.

4. **Permission Management**

    - With v1.1.0+ images, use the built-in fix-permissions command if you encounter issues after editing files as root.
    For detailed instructions on editing files in containers, see the Edit Files in Container documentation.

---

## Additional Recommendations

- **Keep WSL & Docker Updated**: Out-of-date packages can lead to weird issues or mounting troubles.

- **Watch Out for Permissions**: If you see “Permission denied” errors, make sure you own the files inside WSL by running:

```
sudo chown -R $USER:$USER /path/to/folder
chmod -R u+w /path/to/folder
```

- **Default+ Mode Issues**: If the “Default+” environment creation mode fails to install certain custom nodes, consider creating a plain “Default” environment, installing your nodes one by one, then cloning that environment in the future.

- **Sage-Attention Support**: ComfyDock images v1.1.1+ include build-essential packages, ensuring packages like sage-attention that require compilation will work properly. Add the ```--use-sage-attention``` command on environment creation to use sage attention.

---

