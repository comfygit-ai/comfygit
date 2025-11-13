# Other Issues

### Default+ Mode Fails To Install All Custom Nodes

- Due to environmental and OS differences, using Default+ mode when creating a new ComfyUI environment may not always correctly install all custom nodes in an existing install location.
- My current recommendation is to instead try creating a new Default environment, load up the workflows that you normally use, and re-install missing custom nodes through the manager. Once you have a solid working environment, you can clone it whenever making updates or installing new nodes, and if this breaks things you can always delete & clone another from the original environment.

### Unknown runtime specified nvidia

- docker: Error response from daemon: Unknown runtime specified nvidia.:
    - need to install nvidia-container-toolkit in linux:
    - [nvidia-container-toolkit install guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)