#!/usr/bin/env bash
# Source this file. It deliberately does not fall back to user-global Node,
# npm cache, or Playwright browser locations. curl is an explicit host
# dependency, not a WebHelper-managed runtime.

set -euo pipefail

WEB_HELPER_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=../../toolchain.lock.env
source "$WEB_HELPER_ROOT/toolchain.lock.env"

export WEB_HELPER_ROOT
export WEB_HELPER_RUNTIME_DIR="$WEB_HELPER_ROOT/.runtime"
export WEB_HELPER_NODE_HOME="$WEB_HELPER_RUNTIME_DIR/node/v$WEB_HELPER_NODE_VERSION"
export WEB_HELPER_SYSTEM_CURL=/usr/bin/curl
export WEB_HELPER_STATE_DIR="$WEB_HELPER_RUNTIME_DIR/state"
export WEB_HELPER_CACHE_DIR="$WEB_HELPER_RUNTIME_DIR/cache/webhelper"
export PLAYWRIGHT_BROWSERS_PATH="$WEB_HELPER_RUNTIME_DIR/playwright-browsers"
export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
export npm_config_cache="$WEB_HELPER_RUNTIME_DIR/npm-cache"
export npm_config_audit=false
export npm_config_fund=false
export npm_config_update_notifier=false
export XDG_CACHE_HOME="$WEB_HELPER_RUNTIME_DIR/cache"
export PATH="$WEB_HELPER_NODE_HOME/bin:$PATH"
