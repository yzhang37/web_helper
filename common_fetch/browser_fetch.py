import json
import os
import subprocess
from typing import *

from config import CHROME_UA, ACCEPT_LANGUAGE, REFERER, UA_METADATA
from web_helper_tools.types import FetchPayload, FetchResult


def _get_base_dir() -> str:
    from os import path
    base_dir = path.dirname(path.abspath(__file__))
    base_dir = path.join(base_dir, "..")
    return path.abspath(base_dir)


def BrowserFetch(
        payload: FetchPayload,
) -> tuple[FetchResult, Optional[Exception]]:
    result: FetchResult = {
        "StatusCode": None,
        "StatusCodeText": "",
        "FinalURL": payload.get("url") or "", # 初始化最终 FinalURL，如果不存在则为默认 URL
        "ResponseHeaders": [],
        "ContentType": "",
        "Content": "",
        "storageState": None,
    }

    base_dir = _get_base_dir()
    runtime_runner = os.path.join(base_dir, "scripts", "internal", "run-with-runtime.sh")
    browser_leg = os.path.join(base_dir, "common_fetch", "browser_fetch.mjs")

    # Cross-language指纹传递(Option A):config.py 是 Python,.mjs 是 Node 进不了。
    # 把同一份指纹序列化成 JSON,经环境变量喂给 .mjs,浏览器腿 spawn 时读取。
    fingerprint = json.dumps({
        "ua": CHROME_UA,
        "accept_language": ACCEPT_LANGUAGE,
        "referer": REFERER,
        "ua_metadata": UA_METADATA,
    })
    env = {**os.environ, "WEB_HELPER_FINGERPRINT": fingerprint}

    # payload 要经 argv 以 JSON 交给 node —— 这是**本腿自己的**约束,不该漏进共享 payload。
    # 所以 bytes→str 的转换只在这里做;curl 腿仍拿到字节原样。
    wire_payload = dict(payload)
    body = wire_payload.get("body")
    if isinstance(body, (bytes, bytearray)):
        wire_payload["body"] = bytes(body).decode("utf-8", "replace")

    try:
        proc = subprocess.run(
            ["bash", runtime_runner, "node", browser_leg,
             json.dumps(wire_payload, ensure_ascii=False)],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=180,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return result, TimeoutError("browser leg timed out after 180s")
    except Exception as exc:  # 起不来(bash/脚本缺失等),别让 GetWebpage 崩。
        return result, RuntimeError(f"failed to launch browser leg: {exc}")

    # browser_fetch.mjs 已处理的错误也走 exit 0,并把结果打到 stdout(一个 JSON 对象)。
    stdout = (proc.stdout or "").strip()
    try:
        data = json.loads(stdout)  # JSONDecodeError 是 ValueError 的子类
    except ValueError:
        detail = (proc.stderr or "").strip() or stdout or f"exit code {proc.returncode}"
        return result, RuntimeError(
            f"browser leg produced no valid JSON (exit {proc.returncode}): {detail[:500]}"
        )

    if not isinstance(data, dict):
        return result, ValueError(
            f"browser leg returned unexpected JSON type: {type(data).__name__}"
        )
    # 单独处理 result["error"]，如果不为空则是 mjs 中单独 throw 的错误
    if data.get("error"):
        return result, RuntimeError(data.get("error"))

    result["StatusCode"] = data.get("StatusCode")
    result["StatusCodeText"] = data.get("StatusCodeText") or ""
    result["FinalURL"] = data.get("FinalURL") or result["FinalURL"]
    result["ResponseHeaders"] = data.get("ResponseHeaders") or []
    result["ContentType"] = data.get("ContentType") or ""
    result["Content"] = data.get("Content") or ""
    result["storageState"] = data.get("storageState")
    return result, None
