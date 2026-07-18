# WebHelper 抓取指纹和项目内目录的单一来源。
# curl 腿与浏览器腿都从这里取指纹,别再各写一份。
import os
from pathlib import Path

CHROME_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
)
ACCEPT_LANGUAGE = "en-US,en;q=0.9"
REFERER = "https://www.google.com/"

# 浏览器腿专用:client-hints 元数据。用 CDP override 才能让 sec-ch-ua 和
# navigator.userAgentData 都跟 UA 一致(否则默认露 HeadlessChrome)。curl 用不到。
UA_METADATA = {
    "brands": [
        {"brand": "Google Chrome", "version": "149"},
        {"brand": "Chromium", "version": "149"},
        {"brand": "Not)A;Brand", "version": "24"},
    ],
    "fullVersion": "149.0.0.0",
    "platform": "macOS",
    "platformVersion": "10_15_7",
    "architecture": "x86",
    "model": "",
    "mobile": False,
}

WEB_HELPER_ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = Path(os.environ.get("WEB_HELPER_RUNTIME_DIR", WEB_HELPER_ROOT / ".runtime")).resolve()
STATE_DIR = Path(os.environ.get("WEB_HELPER_STATE_DIR", RUNTIME_DIR / "state")).resolve()
CACHE_DEFAULT_TTL = 3600  # 1 小时
CACHE_DEFAULT_DIR = str(
    Path(os.environ.get("WEB_HELPER_CACHE_DIR", RUNTIME_DIR / "cache" / "webhelper")).resolve()
)
