import json
import rjsmin


class ScriptCompressor:
    """无损压缩 <script> 内容:按 type/language 分流,只去空白/注释,拿不准一律原样留。
    绝不 optimize/mangle/dead-code —— 否则会剪掉 lsd / fb_dtsg / csrf / graphql endpoint /
    __NEXT_DATA__ / JobPosting 这些精确值。"""

    _JSON_TYPES = {
        "application/ld+json",
        "application/json",
        "importmap",
        "speculationrules",
    }
    _JS_TYPES = {
        "",
        "text/javascript",
        "application/javascript",
        "text/ecmascript",
        "module",
    }

    def compress(self, node) -> None:
        """就地压缩一个 <script> 节点(只改文本,不动属性/结构;有 src 的空标签自然跳过)。"""
        text = node.string
        if not text or not text.strip():
            return
        stype = (node.get("type") or "").strip().lower()
        language = (node.get("language") or "").strip().lower()
        out = self._compress(text, stype, language)
        if out and len(out) < len(text):
            node.string = out

    def _compress(self, text: str, stype: str, language: str) -> str | None:
        if stype in self._JSON_TYPES:
            return self._minify_json(text)
        if "vbscript" in stype or "vbscript" in language:
            return None                       # 老脚本语言,原样
        if stype in self._JS_TYPES:
            return self._minify_js(text)
        return None                           # 未知 type(text/template 等),保守原样

    @staticmethod
    def _minify_json(text: str) -> str | None:
        try:
            return json.dumps(json.loads(text), separators=(",", ":"), ensure_ascii=False)
        except Exception:
            return None                       # parse 不过 → 原样(不删字段)

    @staticmethod
    def _minify_js(text: str) -> str | None:
        try:
            return rjsmin.jsmin(text)         # 只去空白/注释,不 optimize
        except Exception:
            return None                       # 失败 → 原样
