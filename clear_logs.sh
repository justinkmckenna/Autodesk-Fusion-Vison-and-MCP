#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$ROOT_DIR/logs"
CAPTURES_DIR="$LOG_DIR/captures"

if [ -d "$CAPTURES_DIR" ]; then
  rm -f "$CAPTURES_DIR"/*.png
fi

echo "Cleared logs: captures"
