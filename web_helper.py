from typing import *

import web_helper_tools
from common_fetch import BrowserFetch, CurlFetch
from web_helper_tools.types import *


def GetWebpage(
        url: str,
        method: Optional[str] = None,
        request_body: Optional[RequestBody] = None,
        request_headers: Optional[RequestHeaders] = None,
) -> WebHelperResult:
    """
    GetWebpage

    调用者只需要关心“拿到这个 URL 的可读内容”，不关心底层到底是系统 curl, 或者升级为 browser。
    """

    result: WebHelperResult = {
        "StatusCode": None,  # HTTP 原始状态码；完全无 HTTP 响应时为 0 或 None。
        "StatusCodeText": "",
        "AccessMode": "curl",  # 实际成功路径，只能是 curl 或 browser。
        "FinalURL": url,  # 重定向后的最终 URL。
        "ResponseHeaders": [],  # 完整响应头，保留顺序和重复项。
        "Content": "",  # curl body 或 browser 渲染后的 DOM/content,经过 step 6 处理。
        "FromCache": False,  # 是否命中 WebHelper 自己的缓存。
        "Error_Message": None  # 只放 curl/browser 的真实错误信息。
    }

    # 1. 规范化请求输入，并组装为 payload
    normalized_request, err = web_helper_tools.NormalizeHTTPRequest(url, method, request_body, request_headers)
    if err is not None:
        result["Error_Message"] = f"failed to normalize http request: ({str(err)})"
        return result
    payload: FetchPayload = {"url": normalized_request["url"]}
    if method:
        payload["method"] = method
    if request_body is not None:
        if isinstance(request_body, (bytes, bytearray)):
            payload["body"] = bytes(request_body).decode("utf-8", "replace")
        else:
            payload["body"] = request_body
    if request_headers is not None:
        if hasattr(request_headers, "items"):
            payload["headers"] = {str(k): str(v) for k, v in request_headers.items()}
        else:
            payload["headers"] = [[str(k), str(v)] for k, v in request_headers]

    # 2. TODO: 读取网站级 settings。
    #    - 根据 url 推导 website/scope。
    #    - 合并该 website 已保存的 cookies、session、默认 headers 等状态。
    #    - 这些状态后续由 SetWebsiteSettings / FreeWebsiteSettings 管。

    # 3. TODO: 先查 WebHelper 自己的缓存。
    #    - 命中且未失效：直接返回 FromCache=True。
    #    - 没命中或 settings revision 变化：继续真实请求。
    #    - FromCache 只表示 WebHelper 自己的缓存，不猜浏览器/HTTP 内部缓存。

    cache_key = web_helper_tools.use_local_cache(normalized_request)
    if len(cache_key) > 0:
        # TODO: not implemented yet!
        pass

    # 4. curl 腿
    data, err = CurlFetch(
        normalized_request["url"], method, request_body, request_headers
    )
    access_mode = "curl"

    # 4.1 判断 curl 是否被 block，是的话执行 5 升级为 Browser
    if err is not None:
        access_mode = "browser"
    else:
        content_verdict = web_helper_tools.ContentClassify(
            data.get("Content") or "",
            data.get("StatusCode"),
            data.get("ContentType"),
        )
        if content_verdict in (
            web_helper_tools.ContentVerdict.BLOCKED,
            web_helper_tools.ContentVerdict.NO_CONTENT,
        ):
            access_mode = "browser"
    # update AccessMode in the final result
    result["AccessMode"] = access_mode

    # 5. Browser with playwright 腿
    if access_mode == "browser":
        browser_data, err = BrowserFetch(payload)
        if err is not None:
            result["Error_Message"] = str(err)
            return result

        data = browser_data

    # 6. 处理 Content(按 Content-Type 分流)
    #    HTML → 走 HtmlContentProcessor 壳
    #    其他 → 默认 Handler,原样返回。
    processed_content = web_helper_tools.ProcessContent(
        data.get("Content") or "",
        data.get("ContentType"),
    )

    # 7. 保存结果和状态。
    #    - 成功结果写入页面缓存。
    #    - cookies/session 变化写入 website settings，并让相关缓存按规则失效。
    #    - 不写死页面数量；调用几次由羊的任务决定，WebHelper 只管单次请求。
    # TODO: 只有以下情况才写入/更新 cache
    if len(cache_key) > 0:
        # TODO: 1. result == 200
        # TODO: 2. 跳过 Cache-Control: no-store
        # TODO: 3. 跳过 Cache-Control: private
        # TODO: 4. 跳过 Set-Cookie: ...
        pass

    # 8. 返回值
    # - StatusCode：HTTP 原始状态码；完全无 HTTP 响应时为 0 或 None。
    # - AccessMode：实际成功路径，只能是 curl 或 browser。
    # - FinalURL：重定向后的最终 URL。
    # - ResponseHeaders：完整响应头，保留顺序和重复项。
    # - Content：curl body 或 browser 渲染后的 DOM/content,经过 step 6 处理。
    # - FromCache：是否命中 WebHelper 自己的缓存。
    # - Error_Message：只放 curl/browser 的真实错误信息。
    result["StatusCode"] = data.get("StatusCode")
    result["StatusCodeText"] = data.get("StatusCodeText")
    result["FinalURL"] = data.get("FinalURL") or url
    result["ResponseHeaders"] = data.get("ResponseHeaders") or []
    result["Content"] = processed_content.content
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
