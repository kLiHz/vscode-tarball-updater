# VS Code Linux Tarball Auto-Updater

![Assisted_by-Gemini-blueviolet?logo=googlegemini](https://img.shields.io/badge/Assisted_by-Gemini-blueviolet?logo=googlegemini) 

This project contains a robust, background-capable auto-updater for Linux installations of VS Code that use the portable `.tar.gz` format (tarballs), replicating the side-by-side atomic update architecture used by VS Code on Windows.

## Why this exists?

By default, if you install VS Code on Linux using the generic `.tar.gz` archive, it **does not auto-update natively**. When an update is available, clicking the "Download" button in VS Code merely opens your web browser to download the new `.tar.gz` file for you to extract manually.

Implementing native self-updating for tarballs in Linux is difficult for a few reasons:
1. **Permissions:** Extracted folders might reside in `/opt` or other root-owned directories.
2. **File Locking:** While Linux allows deleting running files, replacing shared `.so` libraries or `.asar` bundles while Electron is running can cause immediate segmentation faults.
3. **Ecosystem Standards:** On Linux, updates are generally meant to be handled by system package managers (`apt`, `rpm`, `snap`), not self-mutating applications.

## How it works (The Windows Approach on Linux)

This script solves the above problems by mimicking how VS Code's `updateService.win32.ts` manages background updates on Windows without triggering "File in use" errors:

1. **Versioned Resources Folder:** Instead of extracting files *over* your existing installation, it extracts the new version into a completely separate, uniquely named directory (e.g., `~/.local/share/vscode-versions/vscode-1.85.1`).
2. **Atomic Symlink Swapping:** A single symlink (`~/.local/bin/code-stable`) points to the currently active version. The update is applied atomically by just changing where the symlink points.
3. **Graceful Restart:** The active instance of VS Code continues running undisturbed from the old directory. The next time you restart the application, the symlink routes you to the new version automatically.
4. **Resumable Downloads:** The script utilizes `curl -C -` to natively resume interrupted downloads. If your network drops or your PC sleeps, the script seamlessly picks up where it left off on the next run.
5. **Garbage Collection:** Old version folders are automatically cleaned up, keeping only the two most recent versions to save disk space.

## Usage

1. Run the script:
   ```bash
   ./update-vscode.sh
   ```
2. The script will create:
   - A versions directory: `~/.local/share/vscode-versions/`
   - An executable symlink: `~/.local/bin/code-stable`
3. Add `~/.local/bin` to your system `$PATH` or point your application `.desktop` launcher to the symlink.
4. (Optional) Put the script in a `cron` job or `systemd` timer for true background updating.
   Example crontab (runs daily at 2:00 AM):
   ```cron
   0 2 * * * /path/to/vscode-tarball-updater/update-vscode.sh > /dev/null 2>&1
   ```

## Requirements
- `curl`
- `tar`
- `grep`
