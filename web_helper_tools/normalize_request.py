import hashlib
import json
from typing import *

from w3lib.url import canonicalize_url

from .types import RequestBody, RequestHeaders, NormalizedHTTPRequestType



def NormalizeHTTPRequest(
        url: str,
        method: Optional[str] = None,
        request_body: Optional[RequestBody] = None,
        request_headers: Optional[RequestHeaders] = None,
) -> Tuple[NormalizedHTTPRequestType, Optional[Exception]]:
    """
    NormalizeHTTPRequest

    规范化请求输入，并组装为 payload
    - method 为空时默认 GET。
    - RequestHeaders 保留调用方传入的 header，不擅自丢弃。
    - RequestBody 原样参与请求和 cache key。
    - URL、method、body、headers 中影响响应的部分一起决定 cache key。

    返回 { url, method, headers, body & cache_key }
    """

    result: NormalizedHTTPRequestType = {
        "url": "",
        "method": "",
        "headers": [],
        "body": None,
        "cache_key": "",
    }

    # 1. 归一化 url
    url = canonicalize_url(url.strip(), keep_fragments=False)
    if not url.startswith(("http://", "https://")):
        return result, ValueError(f"unsupported url: {url}")
    result["url"] = url

    # 2. method
    method = (method or "GET").strip().upper()
    result["method"] = method

    # 3. headers
    headers: List[Tuple[str, str]] = []
    if request_headers:
        items = request_headers.items() if hasattr(request_headers, "items") else request_headers
        for k, v in items:
            k = str(k).strip().lower()
            v = str(v)
            if not k or "\n" in k or "\r" in k or "\n" in v or "\r" in v:
                return result, ValueError(f"invalid header ({str(k)}:{str(v)})")
            headers.append((k, v))
        headers.sort()
    result["headers"] = headers

    # 4. body
    if request_body is None:
        body = None
    elif isinstance(request_body, bytes):
        body = request_body
    elif isinstance(request_body, bytearray):
        body = bytes(request_body)
    elif isinstance(request_body, str):
        body = request_body.encode("utf-8")
    else:
        body = json.dumps(request_body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    result["body"] = body

    # 5. cache_key
    body_hash = hashlib.sha256(body or b"").hexdigest()
    material = json.dumps({
        "v": 1,
        "u": url,
        "m": method,
        "h": headers,
        "bp": body is not None,
        "bh": body_hash,
    }, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    cache_key = hashlib.sha256(material).hexdigest()
    result["cache_key"] = cache_key

    return result, None
