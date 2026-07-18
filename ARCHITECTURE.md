# WebHelper

WebHelper is a standalone website observation helper. It should stay usable
from any caller that can invoke its Python API or command-line wrapper.

## WebHelper

`web_helper/` owns exactly one shared website state/cache model and exposes
these six public operations:

1. `GetWebpage`
2. `InvalidateWebPage`
3. `FreeWebsiteSettings`
4. `SaveWebsiteSettings`
5. `SetWebsiteSettings`
6. `PeekWebsiteSettings`

The current slice is only the Python-first API skeleton. It records the six
tool function signatures without implementing behavior yet.

## Boundaries

- WebHelper logic is Python-first. Node is reserved for the small browser
  fallback helper because Crawlee and Playwright are Node dependencies.
- Any future adapter must be thin and must call the Python WebHelper API;
  it must not become a second implementation.
- The WebHelper runtime is private to `web_helper/`: its managed Node,
  npm cache, Playwright browsers, state, and cache live under
  `web_helper/.runtime/`. They must not fall back to `~/.cache`, a global Node
  default, or a transient `npx` browser cache.
- Python virtual environments, `node_modules/`, Playwright browser binaries,
  npm caches, website state, and response caches are local rebuildable runtime
  artifacts. Do not copy them between workspaces; rebuild them from the checked-in
  lock/config files and scripts.
- `web_helper/.runtime/state/` is runtime-only local data. It must not become
  source, templates, company artifacts, or a second workspace.
- Template code remains network-free. This component is the website observation
  helper, not a template runtime capability.
- No page-count limit belongs to WebHelper. It operates on one caller-specified
  request at a time.

## Reproducible WebHelper runtime

The checked-in `web_helper/toolchain.lock.env`, `package.json`, and
`package-lock.json` are the authoritative version pins. On this canonical
arm64 macOS environment they pin Node `26.5.0` (including its bundled npm
`11.17.0`), `crawlee@3.17.0`, and `playwright@1.61.1`. Playwright pins the
project-local Chromium revision it installs under `.runtime/`.

Run this command from `web_helper/`:

```sh
bash setup.sh
```

`setup.sh` is the one-command restore path for a fresh checkout. It creates
`.venv/` when needed, installs `requirements.txt`, provisions the private
Node/npm/Playwright runtime, and runs verification. This shell entry point is
authoritative because npm is part of the runtime being restored, not a
bootstrap prerequisite.

The internal provision helper installs the exact Node distribution under
`.runtime/`, installs npm dependencies in this directory, and installs
Playwright Chromium into `.runtime/playwright-browsers/` using the local
Playwright CLI. It uses the host `/usr/bin/curl` only to retrieve the locked
Node archive. Node, npm, dependencies, browser binaries, state, and cache
remain private to `web_helper/`.

`verify.sh` performs no target-site request. It rejects a missing or wrong
private Node/browser, checks the pinned npm package versions and browser
executable path, verifies that curl is the host `/usr/bin/curl`, and launches
then closes the local Chromium binary.

`npm run setup`, `npm run verify`, and `npm run webhelper` are convenience
aliases only. The shell commands are the bootstrap-safe entry points because
they do not require npm to exist before the private runtime has been restored.

Curl is deliberately a host dependency, not a WebHelper-managed dependency.
The runtime requires `/usr/bin/curl` to exist and to run, but does not pin its
version, download it, place a copy under `.runtime/`, or claim that its version
is reproducible from this project.

Python is currently a host/runtime dependency with pinned packages in
`requirements.txt`. The developer CLI accepts `WEB_HELPER_PYTHON`; otherwise it
uses `.venv/bin/python` when present, then falls back to `python3`. `.venv/`
itself is intentionally not source and must be recreated locally.

## Current scaffold

This document records structure and the already-provisioned runtime contract
only; it does not authorize unrelated WebHelper behavior changes.
