import re
from dataclasses import dataclass
from typing import Protocol

from bs4 import BeautifulSoup, Comment, NavigableString

from .script_compressor import ScriptCompressor



@dataclass(frozen=True)
class ContentProcessingResult:
    raw_content: str
    content: str
    content_type: str


class ContentProcessor(Protocol):
    def process(self, content: str) -> str:
        ...


class DefaultContentProcessor:
    def process(self, content: str) -> str:
        return content


class HtmlContentProcessor:
    _TEXT_WS_RE = re.compile(r"\s+")
    # Exact-text islands: tokens/templates/code may depend on their original spacing.
    _PRESERVE_TEXT_TAGS = {
        "script",
        "pre",
        "textarea",
        "code",
        "kbd",
        "samp",
        "template",
    }

    _EVENT_ATTRIBUTES = {
        "onclick",
        "onload",
        "onerror",
        "onchange",
        "onsubmit",
        "oninput",
        "onmouseover",
        "onmouseout",
        "onkeydown",
        "onkeyup",
        "onfocus",
        "onblur",
    }

    _ANALYTICS_ATTRIBUTES = {
        "data-ga-event",
        "data-gtm-click",
    }

    _scripts = ScriptCompressor()

    def process(self, content: str) -> str:
        # 过滤掉 LLM 爬虫肯定用不到的信息，按下列列表
        # 1. <style></style>
        # 2. SVG，以及 SVG 的 d/坐标/滤镜
        # 3. HTML 注释
        # 4. 内联 style=""；
        # 5. base64 图片正文
        # 6. event handler, onclick / onload 等事件属性；
        # 7. analytics 属性；
        # 8. 删掉噪音 <link> (head 里的资源/关系声明)
        # 9. 压缩 <script> 的无用空白
        # 10. HTML 普通文本连续 whitespace 压缩

        soup = BeautifulSoup(content, "html.parser")
        # 1. 删除所有 <style>
        # 2. 删除所有 SVG
        for node in soup.select("style, svg"):
            node.decompose()

        # 8. 删掉噪音 <link> (head 里的资源/关系声明)
        #    (stylesheet/icon/preload/preconnect/dns-prefetch/manifest…),
        #    保留 rel=canonical/alternate(URL 归一/多语言,有价值)。
        for node in soup.find_all("link"):
            rels = {r.lower() for r in (node.get("rel") or [])}
            if not (rels & {"canonical", "alternate"}):
                node.decompose()

        # 4–7. 删除无用属性和 base64 图片正文。
        for node in soup.find_all(True):
            for name, value in list(node.attrs.items()):
                lower_name = name.lower()

                # 4. 内联 style=""；
                if lower_name == "style":
                    del node.attrs[name]
                    continue

                # 6. event handler, onclick / onload 等事件属性；
                if lower_name in self._EVENT_ATTRIBUTES:
                    del node.attrs[name]

                # 7. analytics 属性；
                if lower_name in self._ANALYTICS_ATTRIBUTES:
                    del node.attrs[name]

                # 5. base64 图片正文
                if isinstance(value, str):
                    marker = ";base64,"
                    index = value.lower().find(marker)
                    if value.lower().startswith("data:") and index >= 0:
                        node.attrs[name] = value[:index + len(marker)] + "[REDACTED_BASE64]"

        # 3. 删除 HTML 注释。
        for comment in soup.find_all(string=lambda v: isinstance(v, Comment)):
            comment.decompose()

        # 9. 压缩 <script> 内容(无损:JSON minify / JS 去空白;拿不准原样)。分流在 ScriptCompressor,语义/token 不动。
        for node in soup.find_all("script"):
            self._scripts.compress(node)

        # 10. HTML 普通文本连续 whitespace 渲染等价于一个空格; 保真文本节点不动。
        self._collapse_text_whitespace(soup)

        return str(soup)

    def _collapse_text_whitespace(self, soup: BeautifulSoup) -> None:
        # Collapse ordinary rendered text; leave script/pre/template-like data exact.
        for node in list(soup.find_all(string=True)):
            if isinstance(node, Comment):
                continue
            if self._is_preserved_text(node):
                continue

            original = str(node)
            collapsed = self._TEXT_WS_RE.sub(" ", original)
            if collapsed != original:
                node.replace_with(NavigableString(collapsed))

        # Keep one separator so adjacent inline tags do not serialize as one word.
        soup.smooth()

    def _is_preserved_text(self, node: NavigableString) -> bool:
        for parent in node.parents:
            name = getattr(parent, "name", None)
            if name and name.lower() in self._PRESERVE_TEXT_TAGS:
                return True
        return False


_HTML_PROCESSOR = HtmlContentProcessor()
_DEFAULT_PROCESSOR = DefaultContentProcessor()

_PROCESSORS: dict[str, ContentProcessor] = {
    "text/html": _HTML_PROCESSOR,
    "application/xhtml": _HTML_PROCESSOR,
}


def ProcessContent(content: str, content_type: str | None) -> ContentProcessingResult:
    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    processor = _PROCESSORS.get(media_type, _DEFAULT_PROCESSOR)
    return ContentProcessingResult(
        raw_content=content,
        content=processor.process(content),
        content_type=media_type,
    )
