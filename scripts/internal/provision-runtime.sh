#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck source=../../toolchain.lock.env
source "$ROOT/toolchain.lock.env"

fail() {
  printf '%s\n' "WebHelper provision: $*" >&2
  exit 1
}

[[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]] || \
  fail "this locked toolchain currently supports only Darwin arm64"

SYSTEM_CURL=/usr/bin/curl
[[ -x "$SYSTEM_CURL" ]] || fail "system curl is missing: $SYSTEM_CURL"
"$SYSTEM_CURL" --version >/dev/null || fail "system curl did not run: $SYSTEM_CURL"

RUNTIME="$ROOT/.runtime"
DOWNLOADS="$RUNTIME/downloads"
NODE_HOME="$RUNTIME/node/v$WEB_HELPER_NODE_VERSION"
mkdir -p "$DOWNLOADS" "$RUNTIME/state" "$RUNTIME/cache/webhelper" "$RUNTIME/npm-cache" "$RUNTIME/playwright-browsers"

sha256_check() {
  local expected="$1"
  local path="$2"
  local actual
  actual="$(shasum -a 256 "$path" | awk '{print $1}')"
  [[ "$actual" == "$expected" ]] || fail "SHA-256 mismatch for $(basename "$path")"
}

download_once() {
  local url="$1"
  local path="$2"
  if [[ ! -s "$path" ]]; then
    "$SYSTEM_CURL" --fail --location --retry 2 --retry-delay 2 --output "$path.partial" "$url"
    mv "$path.partial" "$path"
  fi
}

node_archive="$DOWNLOADS/$WEB_HELPER_NODE_ARCHIVE"
download_once "$WEB_HELPER_NODE_URL" "$node_archive"
sha256_check "$WEB_HELPER_NODE_SHA256" "$node_archive"
if [[ ! -x "$NODE_HOME/bin/node" ]]; then
  rm -rf "$NODE_HOME"
  mkdir -p "$(dirname "$NODE_HOME")"
  tar -xf "$node_archive" -C "$(dirname "$NODE_HOME")"
  mv "$(dirname "$NODE_HOME")/node-v$WEB_HELPER_NODE_VERSION-$WEB_HELPER_NODE_PLATFORM" "$NODE_HOME"
fi

source "$SCRIPT_DIR/runtime-env.sh"
[[ "$(node --version)" == "v$WEB_HELPER_NODE_VERSION" ]] || fail "private Node did not install at the pinned version"
[[ "$(npm --version)" == "$WEB_HELPER_NPM_VERSION" ]] || fail "private npm version mismatch"

if [[ -f "$ROOT/package-lock.json" ]]; then
  npm ci --ignore-scripts
else
  npm install --package-lock-only --ignore-scripts
  npm ci --ignore-scripts
fi

env -u PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD "$ROOT/node_modules/.bin/playwright" install chromium
