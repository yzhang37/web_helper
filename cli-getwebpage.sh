#!/usr/bin/env bash
# webhelper — 开发时抓页。用法: webhelper <url> | grep ...   ← 直接管道,别落盘
#   stdout = 清洗后的页面内容;stderr = [AccessMode] StatusCode FromCache <err>
#   整页几百 KB:管道只让 grep 的结果进调用方上下文;存成文件既多余又留垃圾。
#   同一 URL 想 grep 几次就调几次 —— 自带磁盘缓存,重抓秒回。
set -euo pipefail

# 获取当前地址
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${WEB_HELPER_PYTHON:-}"
if [[ -z "$PY" ]]; then
  if [[ -x "$HERE/.venv/bin/python" ]]; then
    PY="$HERE/.venv/bin/python"
  else
    PY="$(command -v python3 || true)"
  fi
fi

[[ $# -ge 1 ]] || { echo "usage: webhelper <url>" >&2; exit 2; }
[[ -n "$PY" && -x "$PY" ]] || { echo "webhelper: 找不到 Python; 设置 WEB_HELPER_PYTHON 或创建 .venv" >&2; exit 3; }
"$PY" - <<'PY' >/dev/null 2>&1 || {
import bs4, diskcache, rjsmin, w3lib
PY
  echo "webhelper: $PY 缺 Python dependencies; 运行 python -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 3
}

cd "$HERE"                       # 让 import web_helper/config/common_fetch 解析得到
exec "$PY" - "$1" <<'PY'
import sys, web_helper
r = web_helper.GetWebpage(sys.argv[1])
err = r.get("Error_Message")
line = "[%s] %s FromCache=%s" % (r["AccessMode"], r["StatusCode"], r["FromCache"])
sys.stderr.write(line + ("  ERROR: " + str(err) if err else "") + "\n")
sys.stdout.write(r.get("Content") or "")
sys.exit(1 if err else 0)
PY
