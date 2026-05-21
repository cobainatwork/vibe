#!/usr/bin/env bash
set -euo pipefail
IMG_DIR="${IMG_DIR:-images}"
for f in "$IMG_DIR"/*.tar; do
    [ -e "$f" ] || continue
    echo "Loading $f ..."
    docker load < "$f"
done
echo "Done."
