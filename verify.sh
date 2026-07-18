#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$SCRIPT_DIR"
exec bash "$ROOT/scripts/internal/run-with-runtime.sh" node "$ROOT/scripts/internal/verify-runtime.mjs"
