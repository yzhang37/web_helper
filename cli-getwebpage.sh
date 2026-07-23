#!/usr/bin/env bash
# webhelper — 抓页。开发用法: webhelper <url> | grep ...   ← 直接管道,别落盘
#   stdout = 清洗后的页面内容;stderr = [AccessMode] StatusCode FromCache <err>
#   整页几百 KB:管道只让 grep 的结果进调用方上下文;存成文件既多余又留垃圾。
#   同一 URL 想 grep 几次就调几次 —— 自带磁盘缓存,重抓秒回。
#
# 程序化用法(crawler worker):加 --json,stdout 变成完整 WebHelperResult 的 JSON
#   (StatusCode / AccessMode / FinalURL / ResponseHeaders / Content / FromCache / Error_Message),
#   调用方就不用去解析那行 stderr 了。
#
#   --json                     stdout 输出完整结果 JSON(默认只输出 Content)
#   --method M                 HTTP method(默认 GET)
#   --body B                   请求体;`@-` = 从 stdin 读
#   --header 'K: V'            可重复
#   --access-mode http|browser 钉死访问模式,不做自动升级(会绕过缓存)
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

[[ -n "$PY" && -x "$PY" ]] || { echo "webhelper: 找不到 Python; 设置 WEB_HELPER_PYTHON 或创建 .venv" >&2; exit 3; }
"$PY" - <<'PY' >/dev/null 2>&1 || {
import bs4, diskcache, rjsmin, w3lib
PY
  echo "webhelper: $PY 缺 Python dependencies; 运行 python -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 3
}

# 程序装进变量走 -c(不走 stdin)—— 这样 stdin 空着,`--body @-` 才读得到调用方的管道。
PROG="$(cat <<'PY'
import argparse
import json
import sys

import web_helper

p = argparse.ArgumentParser(prog="webhelper", description="抓一个 URL(curl 起手,按需升级 browser)")
p.add_argument("url")
p.add_argument("--json", action="store_true", dest="as_json",
               help="stdout 输出完整 WebHelperResult JSON(默认只输出 Content)")
p.add_argument("--method", help="HTTP method(默认 GET)")
p.add_argument("--body", help="请求体;`@-` = 从 stdin 读")
p.add_argument("--header", action="append", default=[], metavar="'K: V'", help="可重复")
p.add_argument("--access-mode", dest="access_mode", choices=["http", "browser"],
               help="钉死访问模式,不做自动升级(会绕过缓存)")
a = p.parse_args()

body = sys.stdin.read() if a.body == "@-" else a.body

headers = []
for h in a.header:
    name, sep, value = h.partition(":")
    if not sep:
        sys.exit(f"webhelper: --header 需要 'K: V' 形式,收到 {h!r}")
    headers.append((name.strip(), value.strip()))

r = web_helper.GetWebpage(
    a.url,
    method=a.method,
    request_body=body,
    request_headers=headers or None,
    force_access_mode=a.access_mode,
)

err = r.get("Error_Message")
# 这行诊断两种模式都打,方便人看;--json 只改 stdout。
line = "[%s] %s FromCache=%s" % (r["AccessMode"], r["StatusCode"], r["FromCache"])
sys.stderr.write(line + ("  ERROR: " + str(err) if err else "") + "\n")
sys.stdout.write(json.dumps(r, ensure_ascii=False) if a.as_json else (r.get("Content") or ""))
sys.exit(1 if err else 0)
PY
)"

cd "$HERE"                       # 让 import web_helper/config/common_fetch 解析得到
exec "$PY" -c "$PROG" "$@"
