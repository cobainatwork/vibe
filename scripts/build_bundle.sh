#!/usr/bin/env bash
# Build a lightweight V-Client deployment bundle (online install).
# Output: dist/VibeVoice-Client-v<VERSION>.tar.gz
set -euo pipefail

VERSION="${VERSION:-0.1.0}"
BUNDLE_NAME="VibeVoice-Client-v${VERSION}"
DIST_DIR="dist"

cd "$(dirname "$0")/.."

# Stage to a clean temp dir
TMP="$(mktemp -d)"
STAGE="$TMP/$BUNDLE_NAME"
mkdir -p "$STAGE"

# Top-level deployment files
cp docker-compose.yml "$STAGE/"
cp Dockerfile.app "$STAGE/"
cp pyproject.toml "$STAGE/"
cp .env.example "$STAGE/"
cp docs/customer/README.md "$STAGE/README.md"
cp docs/customer/INSTALL.md "$STAGE/INSTALL.md"

# Config templates
mkdir -p "$STAGE/config"
cp config/api_keys.example.yaml "$STAGE/config/"

# Scripts (only customer-relevant; not lint_all.sh or load_images.sh)
mkdir -p "$STAGE/scripts"
cp scripts/clone_upstream.sh "$STAGE/scripts/"
cp scripts/preflight.sh "$STAGE/scripts/"
cp scripts/wait_for_ready.sh "$STAGE/scripts/"
cp scripts/smoke_test.sh "$STAGE/scripts/"
chmod +x "$STAGE/scripts/"*.sh

# Source code (no tests, no __pycache__, no egg-info)
cp -R src "$STAGE/"
find "$STAGE/src" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$STAGE/src" -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
find "$STAGE/src" -name "*.pyc" -delete 2>/dev/null || true
find "$STAGE/src" -name "*.pyo" -delete 2>/dev/null || true

# Empty current_model with .gitkeep (so mount target exists)
mkdir -p "$STAGE/current_model"
touch "$STAGE/current_model/.gitkeep"

# Output
mkdir -p "$DIST_DIR"
OUTPUT="$DIST_DIR/${BUNDLE_NAME}.tar.gz"
tar -czf "$OUTPUT" -C "$TMP" "$BUNDLE_NAME"

# SHA256 sidecar
shasum -a 256 "$OUTPUT" > "${OUTPUT}.sha256"

# Cleanup
rm -rf "$TMP"

echo ""
echo "✅ Built: $OUTPUT"
echo "Size:   $(du -h "$OUTPUT" | cut -f1)"
echo "SHA256: $(cat "${OUTPUT}.sha256")"
echo ""
ls -lh "$OUTPUT"
