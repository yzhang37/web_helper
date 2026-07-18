import html
import re
from typing import *

from .types import ContentVerdict


# 「挑战」= 页面自己明说**这个客户端看不到内容**。措辞两大类、结论同一个:curl 拿到的没用,得上真浏览器。
#   反爬:    「我怀疑你是机器人」(Cloudflare / PerimeterX)
#   浏览器门:「你渲染不了 JS,换个浏览器」(SPA 空壳)
# 所以它们都判 BLOCKED,不分家。**分成两组是因为误判风险不同,不是因为下游要区别对待。**
_CHALLENGE_MARKERS = (
    "just a moment",
    "checking your browser before",
    "attention required! | cloudflare",
    "verify you are human",
    "enable javascript and cookies to continue",
)

# 浏览器门文案。这组只在短提示页上可信** —— 大量正常页面在 HTML 里塞了隐藏的 legacy-browser
# 横幅(只对 IE 显示),正文照样全在;不加长度闸就会把一片 curl 本来抓得到的页误升级成 browser。
# 2026-07-16 教训:UltiPro 的 JobBoard 返回 200 + 144KB,剥完只剩 203 个字,而那 203 个字就是
# "You are using an unsupported browser. To use this site, please use a supported browser."
# —— 页面把话说得明明白白,分类器却因为「有字」判了 ok、不升级。羊拿着一份零岗位的空壳,
# 以为这站爬不出来,跑去啃 JS bundle 啃了 100 轮(单家 $0.06)。
_BROWSER_GATE_MARKERS = (
    "unsupported browser",
    "use a supported browser",
    "browser is not supported",
    "browser you are using is not supported",
    "this browser is no longer supported",
)

_RAW_CHALLENGE_MARKERS = (
    "_cf_chl_opt",
    "cf-browser-verification",
    "px-captcha",
)

_SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script\s*>", re.IGNORECASE | re.DOTALL)
_STYLE_RE = re.compile(r"<style\b[^>]*>.*?</style\s*>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_BLOCK_STATUSES = {403, 406, 429, 503}

# 浏览器门只信短提示页:UltiPro 那张剥完 203 字,真有内容的页剥完几千上万字(实测 7,659 / 32,487)。
# 1000 离 203 还有 5 倍余量,误判窗口又比 2000 小 2 倍。
# 下界兜住 marker 自身长度:闸要是比 marker 还短,那条 marker 永远匹配不上、等于白写。
_BROWSER_GATE_MAX_TEXT = max(1000, *[len(x) for x in _BROWSER_GATE_MARKERS])


def _looks_like_html(content: str, content_type: Optional[str]) -> bool:
    c = (content_type or "").lower()
    if "text/html" in c or "application/xhtml" in c:
        return True
    start = content.lstrip()[:256].lower()
    return start.startswith(("<!doctype html", "<html", "<head", "<body"))


def ContentClassify(
        content: Optional[str],
        status_code: Optional[int],
        content_type: Optional[str],
) -> ContentVerdict:
    """判断响应内容是否真实可用。

    返回 'ok' | 'blocked' | 'no_content'。上游(web_helper)对 blocked 和 no_content 一视同仁:
    都升级成 browser 重取。所以这里分得清楚是为了**标签诚实**,不是为了让上游走不同的路。
    """
    # 拦截状态码优先。放最前面:否则「503 + 纯脚本挑战页」会先撞上下面的 no_content 提前返回,
    # 被贴成 no_content(行为一样,但标签是错的)。
    if status_code in _BLOCK_STATUSES:
        return ContentVerdict.BLOCKED

    raw = (content or "").strip()
    if not raw:
        return ContentVerdict.NO_CONTENT

    # 检测原始响应中的 challenge 固定标记(含 <script>、属性等不可见处)。
    raw_lower = raw.lower()
    if any(marker in raw_lower for marker in _RAW_CHALLENGE_MARKERS):
        return ContentVerdict.BLOCKED

    # 剥掉 JavaScript / CSS / 标签,只留可见正文。
    if _looks_like_html(raw, content_type):
        visible = _SCRIPT_RE.sub(" ", raw)
        visible = _STYLE_RE.sub(" ", visible)
        visible = _TAG_RE.sub(" ", visible)
        visible = html.unescape(visible)
        visible = _WS_RE.sub(" ", visible).strip()
    else:
        # JSON、纯文本等非 HTML 响应直接使用原始正文。
        visible = raw

    if not visible:
        return ContentVerdict.NO_CONTENT

    searchable = visible.lower()

    # 检测可见正文中的 blocking 字样(此处 <script> 已被剥掉)。
    if any(marker in searchable for marker in _CHALLENGE_MARKERS):
        return ContentVerdict.BLOCKED

    # 浏览器门文案较泛,只允许它判定短提示页 —— 长页面里出现这句话,多半是隐藏的
    # legacy-browser 横幅,正文其实好好的,不能因此把整页判死。
    if (
            len(visible) <= _BROWSER_GATE_MAX_TEXT
            and any(marker in searchable for marker in _BROWSER_GATE_MARKERS)
    ):
        return ContentVerdict.BLOCKED

    return ContentVerdict.OK
