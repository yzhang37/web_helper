#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$SCRIPT_DIR"
INTERNAL_DIR="$ROOT/scripts/internal"

fail() {
  printf '%s\n' "WebHelper bootstrap: $*" >&2
  exit 1
}

python_bin="${WEB_HELPER_PYTHON:-}"
if [[ -z "$python_bin" ]]; then
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    python_bin="$ROOT/.venv/bin/python"
  else
    python_bin="$(command -v python3 || true)"
  fi
fi

[[ -n "$python_bin" && -x "$python_bin" ]] || fail "Python not found; set WEB_HELPER_PYTHON or install python3"

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  "$python_bin" -m venv "$ROOT/.venv"
fi

"$ROOT/.venv/bin/python" -m pip install -r "$ROOT/requirements.txt"
bash "$INTERNAL_DIR/provision-runtime.sh"
bash "$ROOT/verify.sh"

printf '%s\n' "WebHelper runtime is ready."
