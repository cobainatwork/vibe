#!/usr/bin/env bash
set -euo pipefail

UPSTREAM_REF="${UPSTREAM_REF:-main}"
TARGET="${TARGET:-vibevoice_src}"

if [ -d "$TARGET" ]; then
    echo "$TARGET already exists, skipping clone"
    exit 0
fi

echo "Cloning microsoft/VibeVoice @ $UPSTREAM_REF into $TARGET ..."
git clone --depth=1 --branch "$UPSTREAM_REF" https://github.com/microsoft/VibeVoice "$TARGET"
echo "Done. Upstream sha: $(cd $TARGET && git rev-parse HEAD)"
