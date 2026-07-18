import re
from typing import *

from .types import ContentVerdict


# 挑战/人机验证页的特征串(命中即判 blocked)。
_CHALLENGE_MARKERS = (
    "just a moment",
    "cf-browser-verification",
    "checking your browser before",
    "attention required! | cloudflare",
    "verify you are human",
    "_cf_chl_opt",
    "px-captcha",
    "enable javascript and cookies to continue",
)

_SCRIPT_RE = re.compile(r"<script[\s\S]*?</script>", re.IGNORECASE)
_STYLE_RE = re.compile(r"<style[\s\S]*?</style>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _is_html_content_type(content_type: Optional[str]) -> bool:
    c = (content_type or "").lower()
    return "text/html" in c or "application/xhtml" in c


def ContentClassify(content: Optional[str], status_code: Optional[int], content_type: Optional[str]) -> ContentVerdict:
    """
    Classify

    判断本次调用是否是真实可用内容了,还是被挡住了（例如 Challenge 或者 Cloudflare block）
    根据简单的启发式规则，返回 'ok' | 'blocked' | 'no_content'。
    """
    raw = (content or "").strip()
    if not raw:
        return ContentVerdict.NO_CONTENT

    low = raw.lower()
    if any(marker in low for marker in _CHALLENGE_MARKERS):
        return ContentVerdict.BLOCKED

    if _is_html_content_type(content_type):
        visible = _SCRIPT_RE.sub(" ", raw)
        visible = _STYLE_RE.sub(" ", visible)
        visible = _TAG_RE.sub(" ", visible)
        visible = _WS_RE.sub(" ", visible).strip()
        if len(visible) == 0:
            return ContentVerdict.NO_CONTENT
        if status_code in (403, 406, 429, 503) and len(visible) < 200:
            return ContentVerdict.BLOCKED
    elif status_code in (403, 406, 429, 503):
        return ContentVerdict.BLOCKED

    return ContentVerdict.OK
