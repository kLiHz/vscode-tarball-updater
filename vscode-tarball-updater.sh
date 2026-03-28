#!/bin/bash

# Define where you want to keep your VS Code installations
BASE_DIR="$HOME/.local/share/vscode-versions"
SYMLINK_PATH="$HOME/.local/bin/code-stable"

mkdir -p "$BASE_DIR"

echo "Checking for the latest VS Code version..."
# Fetch the latest download URL from the VS Code API
API_URL="https://update.code.visualstudio.com/api/update/linux-x64/stable/VERSION"
PAYLOAD=$(curl -s "$API_URL")
DOWNLOAD_URL=$(echo "$PAYLOAD" | grep -oP '"url":"\K[^"]+')
VERSION=$(echo "$PAYLOAD" | grep -oP '"productVersion":"\K[^"]+')

if [ -z "$DOWNLOAD_URL" ] || [ -z "$VERSION" ]; then
    echo "Failed to find the latest update URL."
    exit 1
fi

TARGET_DIR="$BASE_DIR/vscode-$VERSION"

# Check if we already have this version installed
if [ -d "$TARGET_DIR" ]; then
    echo "VS Code version $VERSION is already installed."
    exit 0
fi

echo "Downloading VS Code $VERSION..."
TMP_TAR="/tmp/vscode-$VERSION.tar.gz"
wget -q --show-progress -O "$TMP_TAR" "$DOWNLOAD_URL"

echo "Extracting to versioned folder..."
# Extract to a temporary folder first
TMP_EXTRACT="/tmp/vscode-extract-$VERSION"
mkdir -p "$TMP_EXTRACT"
tar -xzf "$TMP_TAR" -C "$TMP_EXTRACT"

# The tarball extracts to "VSCode-linux-x64". Move it to our versioned target directory.
mv "$TMP_EXTRACT/VSCode-linux-x64" "$TARGET_DIR"

echo "Updating symlink..."
# Atomically update the symlink to point to the new version.
# ln -sfn does an atomic swap, so if VS Code is launching at this exact millisecond, it won't fail.
ln -sfn "$TARGET_DIR" "$SYMLINK_PATH"

# Cleanup
rm -rf "$TMP_TAR" "$TMP_EXTRACT"

echo "Update complete! The new version will be used the next time you launch VS Code."

# Optional Garbage Collection: Keep only the 2 most recent versions
cd "$BASE_DIR" || exit
ls -dt vscode-* | tail -n +3 | xargs -I {} rm -rf "{}" 2>/dev/null
