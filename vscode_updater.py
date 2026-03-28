#!/usr/bin/env python3
import os
import sys
import json
import shutil
import tarfile
import subprocess
import time

# ==========================================
# Configuration
# ==========================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.join(SCRIPT_DIR, "vscode-versions")
DOWNLOAD_DIR = os.path.join(SCRIPT_DIR, "vscode-downloads")
SYMLINK_PATH = os.path.join(SCRIPT_DIR, "code-stable")
LOCK_FILE = os.path.join(SCRIPT_DIR, ".vscode-updater.lock")

# ==========================================
# Helper: Resumable Downloader (via curl)
# ==========================================
def download_resumable(url, dest, silent=False):
    """Downloads a file using curl, resuming from the existing file size if it exists."""
    cmd = ["curl", "-L", "-C", "-", "-o", dest]
    if silent:
        cmd.append("-s")
    else:
        cmd.append("--progress-bar")
    cmd.append(url)
    
    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise Exception(f"curl exited with code {result.returncode}")

def fetch_api(url):
    """Fetches JSON from the API using curl and explicitly checks the HTTP status code."""
    # -w "%{http_code}" appends the status code to the end of the stdout
    cmd = ["curl", "-s", "-L", "-w", "%{http_code}", url]
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        raise Exception(f"curl failed with code {result.returncode}")
    
    # Extract the HTTP status code from the last 3 characters
    output = result.stdout
    if len(output) < 3:
        raise Exception("Invalid response from curl")
        
    status_code = output[-3:]
    body = output[:-3].strip()
    
    if status_code == "204":
        return None, 204
        
    if status_code != "200":
        raise Exception(f"API returned HTTP {status_code}")
        
    if not body:
        raise Exception("API returned 200 but body is empty")
        
    return json.loads(body), 200

# ==========================================
# Main Update Logic
# ==========================================
def run_update(silent=False):
    def log(msg):
        if not silent:
            print(msg)

    os.makedirs(BASE_DIR, exist_ok=True)
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    log("Checking for the latest VS Code version...")
    
    # 1. Read current commit hash (if installed)
    current_commit = "0000000000000000000000000000000000000000" # Bogus hash forces latest download
    product_json_path = os.path.join(SYMLINK_PATH, "resources", "app", "product.json")
    if os.path.exists(product_json_path):
        try:
            with open(product_json_path, "r") as f:
                product_data = json.load(f)
                current_commit = product_data.get("commit", current_commit)
        except Exception as e:
            log(f"Warning: Could not read current version from {product_json_path}: {e}")

    api_url = f"https://update.code.visualstudio.com/api/update/linux-x64/stable/{current_commit}"
    
    try:
        payload, status = fetch_api(api_url)
        if status == 204 or not payload:
            log("VS Code is already up to date.")
            return
    except Exception as e:
        log(f"Failed to fetch API: {e}")
        return

    download_url = payload.get("url")
    version = payload.get("productVersion")

    if not download_url or not version:
        log("Invalid API response.")
        return

    target_dir = os.path.join(BASE_DIR, f"vscode-{version}")

    if os.path.exists(target_dir):
        log(f"VS Code version {version} is already installed.")
        return

    tar_file = os.path.join(DOWNLOAD_DIR, f"vscode-{version}.tar.gz")
    
    log(f"Downloading VS Code {version}...")
    try:
        download_resumable(download_url, tar_file)
    except Exception as e:
        log(f"Download interrupted: {e}")
        return

    log("Extracting to versioned folder...")
    tmp_extract = os.path.join(BASE_DIR, f".extract-{version}")
    shutil.rmtree(tmp_extract, ignore_errors=True)
    os.makedirs(tmp_extract)

    try:
        with tarfile.open(tar_file, "r:gz") as tar:
            tar.extractall(path=tmp_extract)
    except Exception as e:
        log(f"Extraction failed (file might be corrupted): {e}")
        os.remove(tar_file)
        shutil.rmtree(tmp_extract, ignore_errors=True)
        return

    # Tarball contains a 'VSCode-linux-x64' folder. Move it to the target dir.
    source_extracted_dir = os.path.join(tmp_extract, "VSCode-linux-x64")
    os.rename(source_extracted_dir, target_dir)
    shutil.rmtree(tmp_extract, ignore_errors=True)

    log("Updating symlink...")
    # Atomic symlink swap
    temp_symlink = f"{SYMLINK_PATH}.tmp"
    os.symlink(target_dir, temp_symlink)
    os.rename(temp_symlink, SYMLINK_PATH)

    # Cleanup downloaded tar
    os.remove(tar_file)
    log("Update complete!")

    # Garbage Collection: Keep 2 most recent
    all_versions = sorted([d for d in os.listdir(BASE_DIR) if d.startswith("vscode-")], 
                          key=lambda d: os.path.getmtime(os.path.join(BASE_DIR, d)), 
                          reverse=True)
    
    for old_version in all_versions[2:]:
        old_path = os.path.join(BASE_DIR, old_version)
        shutil.rmtree(old_path, ignore_errors=True)

# ==========================================
# Entry Points
# ==========================================
if __name__ == "__main__":
    args = sys.argv[1:]

    # 1. MANUAL OVERRIDE MODE
    if "--update-now" in args:
        run_update(silent=False)
        sys.exit(0)

    # 2. BACKGROUND DAEMON MODE
    if "--background-daemon" in args:
        # Use fcntl to ensure only one daemon runs at a time (Linux/Unix only)
        try:
            import fcntl
            lock_fd = open(LOCK_FILE, 'w')
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (ImportError, OSError):
            sys.exit(0) # Lock acquired by someone else, or unsupported OS
        
        # Sleep to avoid slowing down the user's immediate application boot
        time.sleep(60)
        run_update(silent=True)
        sys.exit(0)

    # 3. LAUNCHER MODE (Default)
    # First time installation block
    if not os.path.exists(SYMLINK_PATH):
        print("First time setup: Installing VS Code...")
        run_update(silent=False)

    # Spawn the background updater completely detached
    subprocess.Popen(
        [sys.executable, sys.argv[0], "--background-daemon"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True # Detaches the process from the current terminal/launcher
    )

    # Launch the actual application and replace this Python process
    binary_path = os.path.join(SYMLINK_PATH, "bin", "code")
    if os.path.exists(binary_path):
        # os.execv replaces the current process. The Window Manager will 
        # see the Electron app taking over this PID, keeping WMClass intact.
        os.execv(binary_path, [binary_path] + args)
    else:
        print(f"Error: Could not find VS Code executable at {binary_path}", file=sys.stderr)
        sys.exit(1)