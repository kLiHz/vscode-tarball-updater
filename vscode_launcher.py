#!/usr/bin/env python3
import os
import sys
import json
import shutil
import tarfile
import subprocess
import time
import platform
import hashlib

# ==========================================
# Help Message
# ==========================================
def print_help():
    binary_name = os.path.basename(sys.argv[0])
    print(f"VS Code Launcher & Updater Wrapper")
    print(f"Usage: {binary_name} [options] [args...]")
    print(f"\nOptions:")
    print(f"  --insider          Use VS Code Insiders edition")
    print(f"  --update-now       Force an immediate update check and install")
    print(f"  --help             Show this help message")
    print(f"\nAll other arguments are passed directly to the real VS Code binary.")

# ==========================================
# Configuration
# ==========================================
def get_config(quality):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return {
        "base_dir": os.path.join(script_dir, f"vscode-versions-{quality}"),
        "download_dir": os.path.join(script_dir, f"vscode-downloads-{quality}"),
        "symlink_path": os.path.join(script_dir, f"code-{quality}"),
        "lock_file": os.path.join(script_dir, f".vscode-updater-{quality}.lock"),
        "quality": quality
    }

# ==========================================
# Helper: Get Architecture
# ==========================================
def get_vscode_arch():
    """Maps Python's platform.machine() to VS Code's process.arch identifiers."""
    # Allow overriding via environment variable
    override = os.environ.get("VSCODE_ARCH")
    if override:
        return override

    machine = platform.machine().lower()
    if machine in ['x86_64', 'amd64']:
        return 'x64'
    elif machine in ['aarch64', 'arm64']:
        return 'arm64'
    elif machine.startswith('arm'):
        return 'armhf'
    else:
        raise Exception(f"Unsupported architecture: {machine}. Please explicitly set the VSCODE_ARCH environment variable (e.g. VSCODE_ARCH=x64).")

# ==========================================
# Helper: Resumable Downloader (via curl)
# ==========================================
def verify_sha256(file_path, expected_hash):
    """Calculates the SHA256 hash of a file and compares it to the expected hash."""
    if not expected_hash:
        return True # Skip verification if API didn't provide a hash
    
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        while True:
            data = f.read(65536)
            if not data:
                break
            sha256.update(data)
            
    return sha256.hexdigest() == expected_hash

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
def run_update(config, silent=False):
    def log(msg):
        if not silent:
            print(msg)

    base_dir = config["base_dir"]
    download_dir = config["download_dir"]
    symlink_path = config["symlink_path"]
    quality = config["quality"]

    os.makedirs(base_dir, exist_ok=True)
    os.makedirs(download_dir, exist_ok=True)

    log(f"Checking for the latest VS Code {quality} version...")
    
    # 1. Read current commit hash (if installed)
    current_commit = "0000000000000000000000000000000000000000" # Bogus hash forces latest download
    product_json_path = os.path.join(symlink_path, "resources", "app", "product.json")
    if os.path.exists(product_json_path):
        log(f"Reading current version from {product_json_path}")
        try:
            with open(product_json_path, "r") as f:
                product_data = json.load(f)
                current_commit = product_data.get("commit", current_commit)
                log(f"Current commit: {current_commit}")
        except Exception as e:
            log(f"Warning: Could not read current version from {product_json_path}: {e}")
    else:
        log(f"No existing installation found at {symlink_path}")

    try:
        arch = get_vscode_arch()
        log(f"Architecture: {arch}")
    except Exception as e:
        log(f"Error: {e}")
        return

    api_url = f"https://update.code.visualstudio.com/api/update/linux-{arch}/{quality}/{current_commit}"
    log(f"Querying update API: {api_url}")
    
    try:
        payload, status = fetch_api(api_url)
        log(f"API Response Status: {status}")
        if status == 204 or not payload:
            log("VS Code is already up to date (API returned 204 No Content).")
            return
    except Exception as e:
        log(f"Failed to fetch API: {e}")
        return

    download_url = payload.get("url")
    commit_hash = payload.get("version")
    product_version = payload.get("productVersion")
    expected_sha256 = payload.get("sha256hash")

    log(f"Update available! New version: {product_version} (commit: {commit_hash})")

    if not download_url or not commit_hash or not product_version:
        log(f"Invalid API response payload: {payload}")
        return

    # Use both product version and short commit hash for the directory name
    # to perfectly handle insider builds where product version rarely changes
    folder_name = f"vscode-{product_version}-{commit_hash[:8]}"
    target_dir = os.path.join(base_dir, folder_name)

    if os.path.exists(target_dir):
        log(f"VS Code version {folder_name} is already installed.")
        return

    tar_file = os.path.join(download_dir, f"{folder_name}.tar.gz")
    
    log(f"Downloading VS Code {quality} {product_version} ({commit_hash[:8]})...")
    try:
        download_resumable(download_url, tar_file, silent=silent)
    except Exception as e:
        log(f"Download interrupted: {e}")
        return

    log("Verifying checksum...")
    if not verify_sha256(tar_file, expected_sha256):
        log("Error: Checksum validation failed! The download is corrupted.")
        os.remove(tar_file) # Delete corrupted file so we start fresh next time
        return

    log("Extracting to versioned folder...")
    tmp_extract = os.path.join(base_dir, f".extract-{folder_name}")
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
    temp_symlink = f"{symlink_path}.tmp"
    
    # Use a relative path for the symlink so the entire launcher directory is completely portable
    relative_target = os.path.join(f"vscode-versions-{quality}", folder_name)
    os.symlink(relative_target, temp_symlink)
    
    os.rename(temp_symlink, symlink_path)

    # Cleanup downloaded tar
    os.remove(tar_file)
    log("Update complete!")

    # Garbage Collection: Keep 2 most recent
    all_versions = sorted([d for d in os.listdir(base_dir) if d.startswith("vscode-")], 
                          key=lambda d: os.path.getmtime(os.path.join(base_dir, d)), 
                          reverse=True)
    
    for old_version in all_versions[2:]:
        old_path = os.path.join(base_dir, old_version)
        shutil.rmtree(old_path, ignore_errors=True)

# ==========================================
# Entry Points
# ==========================================
if __name__ == "__main__":
    args = sys.argv[1:]
    is_insider = "--insider" in args
    quality = "insider" if is_insider else "stable"
    config = get_config(quality)
    
    # Remove our custom arguments so they don't get passed to the real VS Code process
    launch_args = [a for a in args if a not in ("--insider", "--update-now", "--background-daemon", "--help")]

    # 0. HELP MODE
    if "--help" in args:
        print_help()
        sys.exit(0)

    # 1. MANUAL OVERRIDE MODE
    if "--update-now" in args:
        run_update(config, silent=False)
        sys.exit(0)

    # 2. BACKGROUND DAEMON MODE
    if "--background-daemon" in args:
        # Use fcntl to ensure only one daemon runs at a time (Linux/Unix only)
        try:
            import fcntl
            lock_fd = open(config["lock_file"], 'w')
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (ImportError, OSError):
            sys.exit(0) # Lock acquired by someone else, or unsupported OS
        
        # Sleep to avoid slowing down the user's immediate application boot
        time.sleep(60)
        run_update(config, silent=True)
        sys.exit(0)

    # 3. LAUNCHER MODE (Default)
    # First time installation block
    if not os.path.exists(config["symlink_path"]):
        print("First time setup: Installing VS Code...")
        run_update(config, silent=False)

    # Spawn the background updater completely detached
    daemon_args = [sys.executable, sys.argv[0], "--background-daemon"]
    if is_insider:
        daemon_args.append("--insider")

    subprocess.Popen(
        daemon_args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True # Detaches the process from the current terminal/launcher
    )

    # Launch the actual application and replace this Python process
    binary_name = "code-insiders" if quality == "insider" else "code"
    binary_path = os.path.join(config["symlink_path"], "bin", binary_name)
    if os.path.exists(binary_path):
        # os.execv replaces the current process. The Window Manager will 
        # see the Electron app taking over this PID, keeping WMClass intact.
        os.execv(binary_path, [binary_path] + launch_args)
    else:
        print(f"Error: Could not find VS Code executable at {binary_path}", file=sys.stderr)
        sys.exit(1)
