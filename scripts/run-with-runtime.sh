#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=runtime-env.sh
source "$SCRIPT_DIR/runtime-env.sh"

fail() {
  printf '%s\n' "cheap_pi WebHelper runtime: $*" >&2
  exit 1
}

[[ $# -gt 0 ]] || fail "usage: npm run with:runtime -- <command> [args...]"
[[ -x "$CHEAP_PI_NODE_HOME/bin/node" ]] || fail "private Node is missing; run npm run provision:runtime"
[[ -x "$CHEAP_PI_SYSTEM_CURL" ]] || fail "system curl is missing: $CHEAP_PI_SYSTEM_CURL"

[[ "$(node --version)" == "v$CHEAP_PI_NODE_VERSION" ]] || fail "private Node version mismatch"
"$CHEAP_PI_SYSTEM_CURL" --version >/dev/null || fail "system curl did not run: $CHEAP_PI_SYSTEM_CURL"

exec "$@"
