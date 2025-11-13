# How to Grant WSL More RAM or Processors by Editing `.wslconfig`

If you're running resource-heavy tasks in WSL (Windows Subsystem for Linux) and want to improve performance by granting it more RAM or processors, follow these simple steps:

---

### **Step 1: Locate Your Home Directory**

1. Open **File Explorer** on your Windows computer.
2. In the address bar, type:
    
    ```
    %USERPROFILE%
    ```
    
3. Press **Enter** to go to your home directory.

---

### **Step 2: Create or Edit the `.wslconfig` File**

1. Check if you already have a file named `.wslconfig` in your home directory.
    - If it exists, open it with a text editor like **Notepad**.
    - If it doesn’t exist:
        - Right-click and select **New > Text Document**.
        - Name the file `.wslconfig` (make sure it doesn’t have `.txt` at the end).

---

### **Step 3: Add Resource Settings**

Add the following lines to configure WSL resources:

```
[wsl2]
memory=4GB        # Limits WSL to 4GB of RAM (adjust as needed)
processors=4       # Grants WSL 4 CPU cores (adjust as needed)
```

- **`memory=4GB`**: Replace `4GB` with the amount of RAM you want to allocate (e.g., `8GB`, `64GB`).
- **`processors=4`**: Replace `4` with the number of CPU cores you want to allocate (e.g., `2`, `6`).

---

### **Step 4: Save the File**

- Save your changes and close the editor.

---

### **Step 5: Restart WSL**

1. Open **Command Prompt** or **PowerShell**.
2. Restart WSL with the following command:
    
    ```
    wsl --shutdown
    ```
    
3. Start your WSL distribution again by opening it or running:
    
    ```
    wsl
    ```
    

---

### **Step 6: Verify the Changes**

- Open your WSL terminal.
- Run the following command to verify the allocated resources:or
    
    ```
    htop
    ```
    
    ```
    cat /proc/meminfo
    ```
    

You should see the updated memory and CPU limits applied to your WSL environment.

---

That's it! You’ve successfully updated WSL to use more RAM or processors, boosting its performance for resource-intensive tasks. 🎉