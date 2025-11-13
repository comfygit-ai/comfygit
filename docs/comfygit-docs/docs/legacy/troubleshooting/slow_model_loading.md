# Slow Model Loading (Windows Users)

- If you have your model checkpoints currently saved on a windows drive (C:\, D:\, etc.), you may notice increased loading times when using the environment manager. This is due to the container running in WSL and needing to transfer data from Windows to Linux during read operations.
- You can greatly speed up model loading times by creating a ComfyUI installation inside of WSL (you can have the manager perform this [automatically for you](../usage.md#creating-a-new-environment) during environment creation), and then moving or copying models from Windows to the WSL install location.
- You can navigate to a WSL location from Windows File Explorer by using the prefix path: `\\wsl.localhost\<distro name>\<path>\<to>\<directory>`
    - e.g. `\\wsl.localhost\Ubuntu\home\akatz\ComfyUI\models`
    - If you don’t know which distro you have installed, start by pasting `\\wsl.localhost` into your file explorer path bar and navigating using the GUI from there.