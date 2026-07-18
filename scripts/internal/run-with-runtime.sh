#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=runtime-env.sh
source "$SCRIPT_DIR/runtime-env.sh"

fail() {
  printf '%s\n' "WebHelper runtime: $*" >&2
  exit 1
}

[[ $# -gt 0 ]] || fail "usage: scripts/internal/run-with-runtime.sh <command> [args...]"
[[ -x "$WEB_HELPER_NODE_HOME/bin/node" ]] || fail "private Node is missing; run bash setup.sh"
[[ -x "$WEB_HELPER_SYSTEM_CURL" ]] || fail "system curl is missing: $WEB_HELPER_SYSTEM_CURL"

[[ "$(node --version)" == "v$WEB_HELPER_NODE_VERSION" ]] || fail "private Node version mismatch"
"$WEB_HELPER_SYSTEM_CURL" --version >/dev/null || fail "system curl did not run: $WEB_HELPER_SYSTEM_CURL"

exec "$@"
