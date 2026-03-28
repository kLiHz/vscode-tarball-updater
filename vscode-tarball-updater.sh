#!/bin/bash

# Define where you want to keep your VS Code installations
BASE_DIR="$HOME/.local/share/vscode-versions"
SYMLINK_PATH="$HOME/.local/bin/code-stable"

mkdir -p "$BASE_DIR"

echo "Checking for the latest VS Code version..."
# Fetch the latest download URL from the VS Code API
API_URL="https://update.code.visualstudio.com/api/update/linux-x64/stable/VERSION"
PAYLOAD=$(curl -s "$API_URL")

# Extract the URL and Version using grep and perl-compatible regular expressions
DOWNLOAD_URL=$(echo "$PAYLOAD" | grep -oP '"url":"\K[^"]+')
VERSION=$(echo "$PAYLOAD" | grep -oP '"productVersion":"\K[^"]+')

if [ -z "$DOWNLOAD_URL" ] || [ -z "$VERSION" ]; then
    echo "Failed to find the latest update URL from the API."
    exit 1
fi

TARGET_DIR="$BASE_DIR/vscode-$VERSION"

# Check if we already have this version installed
if [ -d "$TARGET_DIR" ]; then
    echo "VS Code version $VERSION is already installed."
    exit 0
fi

echo "Downloading VS Code $VERSION..."
# Store the file in a permanent temp location so it survives reboots/network drops
DOWNLOAD_DIR="$HOME/.local/share/vscode-downloads"
mkdir -p "$DOWNLOAD_DIR"
TAR_FILE="$DOWNLOAD_DIR/vscode-$VERSION.tar.gz"

# Use curl with -C - to automatically resume the download if it was interrupted.
# -L follows redirects (which Microsoft's CDN uses)
# -o specifies the output file
# --progress-bar shows a nice visual progress indicator without getting messy
curl -L -C - --progress-bar -o "$TAR_FILE" "$DOWNLOAD_URL"

# We must check the exit status of curl. 
# If it fails (e.g., connection lost during a retry), we should abort, 
# but the partial file remains on disk for the next time the script runs.
if [ $? -ne 0 ]; then
    echo "Download interrupted. It will resume next time the script runs."
    exit 1
fi

echo "Extracting to versioned folder..."
# Extract to a temporary folder next to the final destination to ensure they are on the same filesystem
TMP_EXTRACT="$BASE_DIR/.extract-$VERSION"
rm -rf "$TMP_EXTRACT" # Clean up just in case a previous extraction failed halfway
mkdir -p "$TMP_EXTRACT"

# Extract the archive. If this fails, the archive might be corrupt.
if ! tar -xzf "$TAR_FILE" -C "$TMP_EXTRACT"; then
    echo "Extraction failed. The download might be corrupted."
    echo "Deleting corrupted file..."
    rm -f "$TAR_FILE"
    rm -rf "$TMP_EXTRACT"
    exit 1
fi

# The tarball extracts to "VSCode-linux-x64". Move it to our versioned target directory.
# 'mv' is atomic if it's on the same filesystem.
mv "$TMP_EXTRACT/VSCode-linux-x64" "$TARGET_DIR"
rm -rf "$TMP_EXTRACT" # Clean up the empty extract folder

echo "Updating symlink..."
# Atomically update the symlink to point to the new version.
# ln -sfn does an atomic swap, so if VS Code is launching at this exact millisecond, it won't fail.
ln -sfn "$TARGET_DIR" "$SYMLINK_PATH"

# Cleanup the downloaded archive now that extraction is successful
rm -f "$TAR_FILE"

echo "Update complete! The new version will be used the next time you launch VS Code."

# Optional Garbage Collection: Keep only the 2 most recent versions
cd "$BASE_DIR" || exit
# List directories matching vscode-*, sort by time (newest first), skip the first 2, and delete the rest
ls -dt vscode-* 2>/dev/null | tail -n +3 | xargs -I {} rm -rf "{}"
