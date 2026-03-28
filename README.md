# VS Code Linux Tarball Auto-Updater

![Assisted_by-Gemini-blueviolet?logo=googlegemini](https://img.shields.io/badge/Assisted_by-Gemini-blueviolet?logo=googlegemini) 

This project provides a robust, zero-configuration auto-updater for Linux installations of VS Code that use the portable `.tar.gz` format (tarballs). It strictly replicates the clever side-by-side atomic update architecture used natively by VS Code on Windows, and runs entirely in Python.

## The Problem: Why doesn't Linux natively self-update?

If you use the official `.deb` or `.rpm` packages, your system's package manager handles updates perfectly. However, if you download the generic Linux `.tar.gz` archive (tarball), **VS Code does not auto-update natively**. When an update is found, clicking the "Download" button in VS Code merely opens your web browser to download the new `.tar.gz` file for you to extract manually.

Why didn't the VS Code team implement native auto-updating for tarballs like they did for Windows or macOS?

1. **The Permission Problem:** On Linux, users typically extract tarballs to root-owned system directories like `/opt`. Prompting for root access cross-distribution from an Electron app is fragmented and unreliable.
2. **File Locking and In-Memory Crashes:** Overwriting the shared `.so` libraries or `.asar` archives of a running Electron application is extremely dangerous on Linux. It will instantly crash the app with a segmentation fault.
3. **The Linux Ecosystem Standard:** The standard philosophy is that the System Package Manager should handle updates, not self-mutating applications.

## The Solution: The Windows Architecture (and how we copy it)

On Windows, VS Code manages to gracefully update itself while running without triggering "File in use" errors by utilizing a custom background updater and an architecture called the **Versioned Resources Folder**.

Instead of extracting new files directly over the old ones, the Windows background update process extracts the new version into a completely separate, uniquely named sub-folder next to the current one. When you restart VS Code, the tiny main launcher executable simply points to the new versioned folder.

## How this script works

This single Python script (`vscode_updater.py`) perfectly translates the Windows "Versioned Resources Folder" trick to Linux, acting as both the **Launcher** and the **Background Updater Daemon**. It is also fully portable.

1. **Portable Installation:** The script stores all installations and downloads inside its own directory (`./vscode-versions/`). You can place this folder anywhere on your machine (e.g., `~/tools/vscode-updater` or on a USB drive), and it won't clutter your home folder.
2. **The "Launcher + Daemon" Model:**
   When you run the script to launch VS Code, it does two things:
   - **Forks a Background Daemon:** It spawns a detached, silent copy of itself (`--background-daemon`) to check for and download updates while you work.
   - **Seamless Launching:** It instantly replaces its own process with the VS Code binary (`os.execv`). Your Window Manager sees the real Electron application start immediately. Grouping on your dock works perfectly.
3. **Smart API Checking:** It reads your currently installed commit hash and queries the Microsoft API. If you are already on the latest version, the API returns an `HTTP 204 No Content` and the script silently exits.
4. **Resumable Downloads (Proxy Aware):** The script calls `curl` under the hood. This guarantees flawless support for corporate `http_proxy`, `https_proxy`, and `all_proxy` (SOCKS5) environments. It natively resumes broken downloads if your network drops.
5. **Multi-Architecture Support:** Automatically detects your system's architecture (`x64`, `arm64`, or `armhf`) and pulls the correct native build. If you are on an unsupported architecture or want to force a specific build, you can override it using the `VSCODE_ARCH` environment variable (e.g., `VSCODE_ARCH=x64 ./vscode_updater.py`).
6. **Atomic Swapping via Symlinks:** Updates are applied by downloading a new folder and then instantly swapping a symbolic link (`./code-stable`). Your currently running editor is untouched.
7. **Garbage Collection:** Old version folders are silently cleaned up, keeping only the two most recent versions.

## Usage

### 1. Place the Directory
Move this `vscode-tarball-updater` directory to wherever you want your portable VS Code installation to live (e.g., `~/.local/share/vscode-updater`).

### 2. Initial Setup / Launch
Run the script for the first time. It will download the latest stable version and launch VS Code:
```bash
./vscode_updater.py
```

**Using the Insider Build:**
If you prefer the bleeding-edge "Insider" build, simply pass the `--insider` flag. The script will automatically maintain separate folders, downloads, and symlinks (`code-insider`) so you can run both Stable and Insider side-by-side without conflicts!
```bash
./vscode_updater.py --insider
```

### 3. Desktop Integration
To use it like a normal application, point your Desktop Environment to the launcher. 

For strict sandboxed environments (like Flatpak task managers) and proper Wayland/X11 dock grouping, you must install the icon into the standard Freedesktop `hicolor` theme directory and match the `StartupWMClass`.

**Install the icon using the official standard:**
```bash
xdg-icon-resource install --context apps --size 256 /path/to/vscode-tarball-updater/code-stable/resources/app/resources/linux/code.png code
```

**Create the desktop entry:**
Create a file at `~/.local/share/applications/code.desktop`:
```ini
[Desktop Entry]
Name=Visual Studio Code
Comment=Code Editing. Redefined.
Exec=/path/to/vscode-tarball-updater/vscode_updater.py %F
Icon=code
Type=Application
StartupNotify=false
StartupWMClass=Code
Categories=TextEditor;Development;IDE;
```

*(Note: The official `StartupWMClass` for the stable release of VS Code on Linux is `Code`.)*

### Manual Updating
If you prefer to force an update visibly instead of waiting for the background daemon, you can run:
```bash
./vscode_updater.py --update-now
```

## Requirements
- Python 3.6+
- `curl` (for download resumption and proxy support)
- `xdg-utils` (optional, for `xdg-icon-resource`)