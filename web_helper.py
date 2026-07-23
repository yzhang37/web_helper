import re
from typing import *

from config import CACHE_DEFAULT_TTL
import web_helper_tools
from common_fetch import BrowserFetch, CurlFetch
from web_helper_tools.cache_driver import cache
from web_helper_tools.types import *

_MODE_HTTP = "http"
_MODE_BROWSER = "browser"

def _cache_ttl(headers) -> Optional[int]:
    """从响应头决定缓存 TTL(秒)。返回 None = 不该缓存。

    - Set-Cookie / Cache-Control: no-store|no-cache|private → 不缓存
    - Cache-Control: max-age=N → 用 N(N==0 也不缓存)
    - 都没有 → 默认 TTL(config.CACHE_DEFAULT_TTL)
    """
    max_age = None
    for name, value in headers or []:
        n = str(name).lower()
        v = str(value).lower()
        if n == "set-cookie":
            return None
        if n == "cache-control":
            if "no-store" in v or "no-cache" in v or "private" in v:
                return None
            m = re.search(r"max-age\s*=\s*(\d+)", v)
            if m:
                max_age = int(m.group(1))
    if max_age is not None:
        return max_age or None
    return CACHE_DEFAULT_TTL


def GetWebpage(
        url: str,
        method: Optional[str] = None,
        request_body: Optional[RequestBody] = None,
        request_headers: Optional[RequestHeaders] = None,
        force_access_mode: Optional[str]=None,
        proxy: Optional[str] = None,
) -> WebHelperResult:
    """
    GetWebpage

    调用者只需要关心“拿到这个 URL 的可读内容”，不关心底层到底是系统 curl (http), 或者升级为 browser。
    - force_access_mode: 强制访问模式。当设置为非空值后，会禁用缓存。（目前故意设计成这样，比较简单）
      支持的数值： 'http', 'browser'
    - proxy: 传输层出口，如 'http://user:pass@host:8080'、'socks5://host:1080'。两条腿共用同一个值，
      curl 升级 browser 时出口不会掉。**不参与缓存键**（只有 200 才写缓存，而 200 与出口无关）。
      不传 = 完全维持原行为。

    返回值
     - StatusCode：HTTP 原始状态码；完全无 HTTP 响应时为 0 或 None。
     - AccessMode：实际成功路径,只能是 http 或 browser。
     - FinalURL：重定向后的最终 URL。
     - ResponseHeaders：完整响应头,保留顺序和重复项。
     - Content：http body 或 browser 渲染后的 DOM/content,经过 step 6 处理。
     - FromCache：是否命中 WebHelper 自己的缓存。
     - Error_Message：只放 http/browser 的真实错误信息。
    """

    result: WebHelperResult = {
        "StatusCode": None,  # HTTP 原始状态码；完全无 HTTP 响应时为 0 或 None。
        "StatusCodeText": "",
        "AccessMode": _MODE_HTTP,  # 实际成功路径，只能是 http 或 browser。
        "FinalURL": url,  # 重定向后的最终 URL。
        "ResponseHeaders": [],  # 完整响应头，保留顺序和重复项。
        "Content": "",  # http body 或 browser 渲染后的 DOM/content,经过 step 6 处理。
        "FromCache": False,  # 是否命中 WebHelper 自己的缓存。
        "Error_Message": None  # 只放 http/browser 的真实错误信息。
    }

    # 1. 规范化请求输入，并组装为 payload
    normalized_request, err = web_helper_tools.NormalizeHTTPRequest(url, method, request_body, request_headers)
    if err is not None:
        result["Error_Message"] = f"failed to normalize http request: ({str(err)})"
        return result
    # payload 只从规范化结果搭一次,两条腿 + cache key 共用同一个来源 —— 否则会变成
    # "请求走原始值、缓存键走规范化值"的错位。body 原样带着(bytes 也行):JSON 化是 browser 腿的事。
    payload: FetchPayload = {
        "url": normalized_request["url"],
        "method": normalized_request["method"],
        "headers": [[k, v] for k, v in normalized_request["headers"]],
    }
    if normalized_request["body"] is not None:
        payload["body"] = normalized_request["body"]
    # proxy 是传输层,故意**不**走 NormalizeHTTPRequest —— 那份规范化结果是缓存键的来源,
    # 出口不该改变一个 URL 的身份(且只有 200 才写缓存,200 与走哪个出口无关)。
    if proxy:
        payload["proxy"] = proxy

    # 2. TODO: 读取网站级 settings。
    #    - 根据 url 推导 website/scope。
    #    - 合并该 website 已保存的 cookies、session、默认 headers 等状态。
    #    - 这些状态后续由 SetWebsiteSettings / FreeWebsiteSettings 管。

    # 3. 判断是否是 force_access_mode。这一步通常被 crawler worker 使用，因此为了方便，会简单禁用缓存
    skipping_cache = False
    if force_access_mode is not None:
        if force_access_mode.lower().strip() in (_MODE_HTTP, _MODE_BROWSER):
            skipping_cache = True
            force_access_mode = force_access_mode.lower().strip()
        else:
            result["Error_Message"] = f"force_access_mode must in {[_MODE_HTTP, _MODE_BROWSER]}"
            return result

    # 4. 缓存
    # - 命中且未失效：直接返回 FromCache=True。
    # - 没命中或 settings revision 变化：继续真实请求。
    # - FromCache 只表示 WebHelper 自己的缓存，不猜浏览器/HTTP 内部缓存。
    if skipping_cache: # 根据 3, 现在的设计是，如果 force_access_mode，跳过缓存，这样比较简单
        cache_key = ""
    else:
        cache_key = web_helper_tools.use_local_cache(normalized_request)
        if cache_key:
            hit = cache.get(cache_key)
            if hit is not None:
                hit = dict(hit)
                hit["FromCache"] = True
                return hit
    result["FromCache"] = False

    # 5. 顺序跑两条腿:http 腿 →(需要时)browser 腿。两条腿同签名(都吃 payload),各只有一个调用点。
    #    force_access_mode 只钉死"要不要升级"这个决定,不改变腿本身。
    mode = force_access_mode or _MODE_HTTP
    data = None

    # 5.1 http 腿(强制 browser 时整条跳过,不白打一次)
    if mode == _MODE_HTTP:
        result["AccessMode"] = _MODE_HTTP
        data, err = CurlFetch(payload)
        if err is not None:
            if force_access_mode == _MODE_HTTP:   # 强制 http:不升级,如实报错
                result["Error_Message"] = str(err)
                return result
            mode = _MODE_BROWSER                  # 自动模式:抓失败 → 升级
        elif force_access_mode is None:           # 只有自动模式才看内容判定要不要升级
            content_verdict = web_helper_tools.ContentClassify(
                data.get("Content") or "",
                data.get("StatusCode"),
                data.get("ContentType"),
            )
            if content_verdict in (web_helper_tools.ContentVerdict.BLOCKED, web_helper_tools.ContentVerdict.NO_CONTENT):
                mode = _MODE_BROWSER

    # 5.2 browser 腿
    if mode == _MODE_BROWSER:
        result["AccessMode"] = _MODE_BROWSER      # 先落,失败返回时调用方也知道是哪条腿死的
        data, err = BrowserFetch(payload)
        if err is not None:
            result["Error_Message"] = str(err)
            return result

    # 7. 处理 Content(按 Content-Type 分流)
    #    HTML → 走 HtmlContentProcessor 壳
    #    其他 → 默认 Handler,原样返回。
    processed_content = web_helper_tools.ProcessContent(
        data.get("Content") or "",
        data.get("ContentType"),
    )

    # 8. 组装返回值(从 data + 清洗后内容填入 result)
    result["StatusCode"] = data.get("StatusCode")
    result["StatusCodeText"] = data.get("StatusCodeText")
    result["FinalURL"] = data.get("FinalURL") or url
    result["ResponseHeaders"] = data.get("ResponseHeaders") or []
    result["Content"] = processed_content.content

    # 9. 写缓存:仅 200 且响应头允许(no-store/no-cache/private/Set-Cookie 不缓存);
    #    TTL 从 Cache-Control: max-age,没给用默认。放这儿是因为缓存的就是上面组装好的 result。
    #    (cookies/session 写入 website settings 仍是 TODO。)
    if cache_key and result["StatusCode"] == 200:
        ttl = _cache_ttl(result["ResponseHeaders"])
        if ttl is not None:
            cache.set(cache_key, dict(result), ttl=ttl)

    return result


def InvalidateWebPage(
        url: str,
        method: str | None = None,
        RequestBody: RequestBody | None = None,
        RequestHeaders: RequestHeaders | None = None,
) -> WebHelperResult:
    # 这里实现删除单个网页请求缓存。
    # cache key 应该和 GetWebpage 使用同一套规则，至少包含 URL、method、
    # request body、request headers 中会影响响应的部分。
    # 这个函数只影响一个页面/请求，不应该清空整个网站 cookies 或 session。
    raise NotImplementedError("InvalidateWebPage 目前只有函数签名，尚未实现")


def FreeWebsiteSettings(website: str) -> WebHelperResult:
    # 这里实现清空某个网站的本地状态。
    # 范围包括该网站的 cookies、browser session、缓存、以及后续 WebHelper
    # 为这个网站维护的其他 settings。
    # 这个函数是站点级清理，不是单页面缓存清理。
    raise NotImplementedError("FreeWebsiteSettings 目前只有函数签名，尚未实现")


def SaveWebsiteSettings(
        website: str,
        output_path: str | None = None,
) -> WebHelperResult:
    # 这里实现导出某个网站当前可复用的 settings。
    # 应该由工具自己打包 cookies/session/settings/cache metadata，
    # 并返回写出的文件名、位置、摘要和可恢复说明。
    # output_path 为空时，由 WebHelper 自己选择默认导出位置。
    raise NotImplementedError("SaveWebsiteSettings 目前只有函数签名，尚未实现")


def SetWebsiteSettings(
        website: str,
        settings_path: str | None = None,
        settings_blob: Mapping[str, Any] | None = None,
) -> WebHelperResult:
    # 这里实现恢复某个网站的 settings。
    # settings_path 用于从 SaveWebsiteSettings 产物恢复。
    # settings_blob 用于调用方直接传入已经解析好的 settings。
    # 恢复后应当让该网站相关缓存失效，避免旧缓存和新 cookies/session 混用。
    raise NotImplementedError("SetWebsiteSettings 目前只有函数签名，尚未实现")


def PeekWebsiteSettings(
        website: str,
        category: str | None = None,
        query: Mapping[str, Any] | None = None,
        limit: int | None = None,
) -> WebHelperResult:
    # 这里实现只读查看某个网站的 settings 摘要。
    # category 可以用于限制查看 cookies、session、cache、headers、metadata 等分类。
    # query 用于后续支持更细的筛选条件。
    # limit 用于避免一次返回过多内容，让 LLM 只看必要摘要。
    # 这个函数不应该暴露大段原始 cookies 或完整缓存内容。
    raise NotImplementedError("PeekWebsiteSettings 目前只有函数签名，尚未实现")


__all__ = [
    "GetWebpage",
    "InvalidateWebPage",
    "FreeWebsiteSettings",
    "SaveWebsiteSettings",
    "SetWebsiteSettings",
    "PeekWebsiteSettings",
]
