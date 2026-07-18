import json
import os
import subprocess
from collections.abc import Mapping
from typing import *

import web_helper_tools
from web_helper_tools import NormalizedHTTPRequestType
from web_helper_tools.types import RequestBody, RequestHeaders, WebHelperResult


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

    # 预先定义返回的固定字段，不扩展。
    result: WebHelperResult = {
        "StatusCode": None,       # HTTP 原始状态码；完全无 HTTP 响应时为 0 或 None。
        "AccessMode": "browser",  # TODO: 实际成功路径，只能是 curl 或 browser。
        "FinalURL": url,          # 重定向后的最终 URL。
        "ResponseHeaders": [],    # 完整响应头，保留顺序和重复项。
        "Content": "",            # curl body 或 browser 渲染后的 DOM/content,经过 step 6 处理。
        "FromCache": False,       # 是否命中 WebHelper 自己的缓存。
        "Error_Message": None     # 只放 curl/browser 的真实错误信息。
    }

    # 1. 规范化请求输入，并组装为 payload
    normalized_request, err = web_helper_tools.NormalizeHTTPRequest(url, method, request_body, request_headers)
    if err is not None:
        result["Error_Message"] = f"failed to normalize http request: ({str(err)})"
        return result
    # TODO: headers 交给浏览器腿,不经 NormalizeRequest, 也不查缓存。
    payload: dict[str, Any] = {"url": normalized_request["url"]}
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

    if useLocalCache(normalized_request):
        raise NotImplementedError() # Yet!

    # 4. curl 腿(系统 /usr/bin/curl + 默认 Chrome 头 + 你传的 method/body/headers)
    #    - curl 是第一路径，因为便宜、快、CPU 消耗低。
    #    - 要跟随重定向，记录 FinalURL。
    #    - 要保留完整 ResponseHeaders，包括重复 header。
    #    - 要捕获 transport error，例如 DNS/TLS/timeout/connect failed。
    #    拿到结果后【代码确定性判,不是 LLM 判】:
    #       200 + 正文够          → 用 curl 结果,去 ④,AccessMode=curl
    #       403/406/429/503        ┐
    #       cf-browser-verification├→ 升级浏览器(③)
    #       正文空 / 过小(疑似SPA)┘
    #       404                    → StatusCode=404,不升级(页面真没有,别浪费 Chromium)
    #       连不上 / 超时          → 升级浏览器再试一次;还不行 → Error_Message=unreachable,返回
    #     成本护栏:浏览器比 curl 贵 10–100×,只在上面这些明确信号下才升。
    #
    # 4.1 判断 curl 结果是否足够。
    #    - 如果 HTTP 响应和 Content 已经可用，AccessMode='curl'。
    #    - 如果只有空壳、JS challenge、必须执行脚本才能出现内容、
    #      或 curl transport 失败但 browser 可能拿到内容，再进入 browser。
    #    - 这个判断是内部控制流，不新增返回字段，不让羊处理复杂 verdict。
    #
    data = {} # not implemented yet
    # 4.1 判定内容是否可用
    #     verdict ∈ ok / blocked / no_content。传输失败(连不上/超时)已在上面 err 分支拦掉,不进这里。
    #     消费者(还没接线):curl→browser 升级判据;以及 blocked/no_content 是否落 Error_Message(issue4,先不动)。
    content_verdict = web_helper_tools.ContentClassify(
        data.get("Content") or "",
        data.get("StatusCode"),
        data.get("ContentType"),
        )

    # 5. 浏览器腿(playwright+chromium,同一套头),AccessMode=browser (记住最后返回 AccessMode = Browser)
    #    - browser helper 只做 Crawlee/Playwright fallback，不承载六函数主逻辑。
    #    - 它使用 WebHelper 私有 Node/Playwright/Chromium。
    #    - 要带上同一 website 的 cookies/session，并把新 cookies/session 交回
    #      Python 主控保存。
    #    按 Content-Type 拿对的那份:
    #      HTML     → 渲染后的 DOM(JS 跑完的)
    #      JSON/XML → 原始 body(不是被浏览器包过的)
    #    升级后仍空 / 仍被挡 → 返回 blocked / no_content(交 LLM 判 park)
    data, err = _run_browser_leg(payload)
    if err is not None:
        result["Error_Message"] = str(err)
        return result


    # 6. 处理 Content(按 Content-Type 分流)
    #    HTML → 走 HtmlContentProcessor 壳;具体轻清洗规则后面再填。
    #           清洗要保守,不能删 header/footer/nav、联系方式、link/form/input/meta/data-*、
    #           hidden token、JSON bootstrap script、Meta LSD 这类模板可能依赖的内容。
    #    其他 → 默认处理器,原样返回。
    #    raw_content 先留在 processed_content,等 step 7 缓存实现时再落地。
    processed_content = web_helper_tools.ProcessContent(
        data.get("Content") or "",
        data.get("ContentType"),
    )

    # 7. 保存结果和状态。
    #    - 成功结果写入页面缓存。
    #    - cookies/session 变化写入 website settings，并让相关缓存按规则失效。
    #    - 不写死页面数量；调用几次由羊的任务决定，WebHelper 只管单次请求。
    # TODO: 只有以下情况才写入/更新 cache
    # 1. result == 200
    # 2. 跳过 Cache-Control: no-store
    # 3. 跳过 Cache-Control: private
    # 4. 跳过 Set-Cookie: ...


    # 8. 返回固定字段，不扩展。
    #    - StatusCode：HTTP 原始状态码；完全无 HTTP 响应时为 0 或 None。
    #    - AccessMode：实际成功路径，只能是 curl 或 browser。
    #    - FinalURL：重定向后的最终 URL。
    #    - ResponseHeaders：完整响应头，保留顺序和重复项。
    #    - Content：curl body 或 browser 渲染后的 DOM/content,经过 step 6 处理。
    #    - FromCache：是否命中 WebHelper 自己的缓存。
    #    - Error_Message：只放 curl/browser 的真实错误信息。
    #
    # 把浏览器腿输出映射到固定返回字段。
    #    StatusCode/FinalURL/ResponseHeaders/Content/Error_Message 来自浏览器腿;
    #    AccessMode 恒 "browser",FromCache 恒 False(上面已设,不再改)。
    #    (storageState 本步先忽略。)
    result["StatusCode"] = data.get("StatusCode")
    result["FinalURL"] = data.get("FinalURL") or url
    result["ResponseHeaders"] = data.get("ResponseHeaders") or []
    result["Content"] = processed_content.content
    result["Error_Message"] = data.get("error")
    return result


def useLocalCache(request: NormalizedHTTPRequestType) -> bool:
    # 非常简单的启发式判断，只有以下三个都满足才是 True
    # 1. method == GET
    # 2. request body is None (一般只被 POST 等用到)
    # 3. 不包含自定义 request headers
    if request["method"] != "GET": return False
    elif request["body"] is not None: return False
    elif request["headers"] is not None: return False

    return True


def _run_browser_leg(
        payload: dict[str, Any],
) -> Tuple[Dict[str, Any], Optional[Exception]]: # 返回 data, error (if has)
    # ---- step 5:浏览器腿(本版唯一接通的路径)-------------------------------
    # 经私有运行时 scripts/run-with-runtime.sh 调 browser/browser_fetch.mjs。
    # 路径按本模块所在目录推导,不依赖当前 cwd。
    base_dir = os.path.dirname(os.path.abspath(__file__))
    runtime_runner = os.path.join(base_dir, "scripts", "run-with-runtime.sh")
    browser_leg = os.path.join(base_dir, "browser", "browser_fetch.mjs")

    try:
        proc = subprocess.run(
            ["bash", runtime_runner, "node", browser_leg,
             json.dumps(payload, ensure_ascii=False)],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        return {}, TimeoutError("browser leg timed out after 180s")
    except Exception as exc:  # 起不来(bash/脚本缺失等),别让 GetWebpage 崩。
        return {}, RuntimeError(f"failed to launch browser leg: {exc}")

    # browser_fetch.mjs 已处理的错误也走 exit 0,并把结果打到 stdout(一个 JSON 对象)。
    stdout = (proc.stdout or "").strip()
    try:
        data = json.loads(stdout)  # JSONDecodeError 是 ValueError 的子类
    except ValueError:
        detail = (proc.stderr or "").strip() or stdout or f"exit code {proc.returncode}"
        return {}, RuntimeError(
            f"browser leg produced no valid JSON (exit {proc.returncode}): {detail[:500]}"
        )

    if not isinstance(data, dict):
        return {}, ValueError(
            f"browser leg returned unexpected JSON type: {type(data).__name__}"
        )

    return data, None


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
