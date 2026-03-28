# VS Code Linux Tarball Auto-Updater

![Assisted_by-Gemini-blueviolet?logo=googlegemini](https://img.shields.io/badge/Assisted_by-Gemini-blueviolet?logo=googlegemini) 

This project provides a robust, background-capable auto-updater for Linux installations of VS Code that use the portable `.tar.gz` format (tarballs). It strictly replicates the clever side-by-side atomic update architecture used natively by VS Code on Windows.

## The Problem: Why doesn't Linux natively self-update?

If you use the official `.deb` or `.rpm` packages, your system's package manager handles updates perfectly. However, if you download the generic Linux `.tar.gz` archive (tarball), **VS Code does not auto-update natively**. When an update is found, clicking the "Download" button in VS Code merely invokes `openExternal()` to pass the download URL to your system's default web browser. You are expected to extract the new `.tar.gz` manually over the old files.

Why didn't the VS Code team implement native auto-updating for tarballs like they did for Windows or macOS?

1. **The Permission Problem:**
   On Windows, installers can trigger UAC prompts. On macOS, dragging to `/Applications` is standard. On Linux, users typically extract the tarball to root-owned system directories like `/opt/vscode` or `/usr/local/bin`. VS Code runs as a standard user. Prompting for root access cross-distribution (using `pkexec`, `kdesu`, or `gksudo`) from within an Electron app is fragmented and unreliable.
2. **File Locking and In-Memory Crashes:**
   While Linux *does* allow you to delete or overwrite an open file (unlike Windows, which violently locks executing `.exe` files), overwriting the files of a running Electron application (especially shared `.so` libraries or `.asar` archives) is extremely dangerous. If Electron tries to page memory from disk and finds half of an `.asar` overwritten, it will instantly crash with a segmentation fault.
3. **The Linux Ecosystem Standard:**
   The standard philosophy on Linux is that the **System Package Manager** should handle updates, not individual applications. The tarball is explicitly treated as a "portable" or "manual" fallback.

## The Solution: How VS Code updates on Windows (and how we copy it)

On Windows, VS Code manages to gracefully update itself while running without triggering "File in use" errors by utilizing a custom updater tool (`inno_updater.exe`) and an architecture called the **Versioned Resources Folder**.

Instead of extracting the massive bulk of the application's code directly over the old files, the Windows background update process extracts the new version into a completely separate, uniquely named sub-folder right next to the current one (e.g., named after the Git commit hash of that release). When you restart VS Code, the main launcher executable is quickly swapped, and it simply points to the new versioned folder.

**Because Linux handles file systems differently, this architecture is actually easier to implement on Linux using symlinks.**

## How this script works

This bash script perfectly translates the Windows "Versioned Resources Folder" trick to Linux:

1. **User Setup:** It extracts the tarballs to a directory you own (e.g., `~/.local/share/vscode-versions`). Because you own this directory, the script never needs `sudo`.
2. **Side-by-Side Versioning:** It fetches the latest payload URL from the VS Code update API and extracts the new update into a uniquely named folder based on the version (e.g., `vscode-1.86.0`).
3. **Atomic Swapping via Symlinks:** Instead of swapping an executable, the script creates a symbolic link (e.g., `~/.local/bin/code-stable`) that points to the latest version folder. The update is applied by doing an atomic swap of the symlink target.
4. **Zero Downtime:** Because the new files go into a new folder and the symlink is swapped instantly, the instance of VS Code you are actively typing in will not crash. It is still physically running from the old folder. The next time you launch the app, the symlink routes you to the new version seamlessly.
5. **Resumable Downloads:** The script utilizes `curl -C -` to make downloads strictly resumable. If your network drops or your laptop hibernates halfway through downloading the 100MB+ payload, the script will pick up right where it left off on the next run.
6. **Safe Extraction:** The archive is downloaded to a permanent location, extracted into a temporary hidden folder on the same filesystem, and then atomically `mv`'d into place. This guarantees you never end up with a half-extracted, broken application folder if the script is killed midway through.
7. **Garbage Collection:** Old versioned folders are silently cleaned up, keeping only the two most recent versions to prevent your disk from filling up over time.

## Usage

### 1. Initial Setup
Run the script to fetch and install the latest version:
```bash
./update-vscode.sh
```

### 2. Configure your Path
The script will create an executable symlink at `~/.local/bin/code-stable`.
Ensure `~/.local/bin` is in your system `$PATH`, or configure your desktop shortcut (`.desktop` file) to point to `~/.local/bin/code-stable/bin/code`.

### 3. Automate the Background Update
To make it function like a true background auto-updater, run the script periodically using `cron` or a `systemd` user timer.

Example crontab entry (runs daily at 2:00 AM):
```cron
0 2 * * * /path/to/vscode-tarball-updater/update-vscode.sh > /dev/null 2>&1
```

## Requirements
- `curl`
- `tar`
- `grep` (with perl-compatible regex support, standard on most Linux distros)
