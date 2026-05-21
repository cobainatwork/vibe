#!/usr/bin/env bash
# Run all linters + type checker + tests. Exit non-zero if any fail.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "=== ruff (lint) ==="
uv run ruff check src/ tests/

echo ""
echo "=== bandit (security) ==="
uv run bandit -r src/ -ll

echo ""
echo "=== mypy (types) ==="
uv run mypy src/ --ignore-missing-imports

echo ""
echo "=== pytest (unit + integration, excluding e2e) ==="
uv run pytest tests/ --ignore=tests/e2e -q

echo ""
echo "✅ All checks passed."
