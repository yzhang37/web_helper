from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import *


RequestHeaders = Mapping[str, str] | Sequence[tuple[str, str]]
RequestBody = str | bytes | bytearray | Mapping[str, Any] | Sequence[Any]


class ContentVerdict(StrEnum):
    """Classify 的粗判结果:内容拿到了 / 被挡 / 空。

    不含 'error' —— 传输失败(连不上/超时)由抓取腿单独标,不是 classify 的结论。
    """
    OK = "ok"
    BLOCKED = "blocked"
    NO_CONTENT = "no_content"


class WebHelperResult(TypedDict):
    StatusCode: int | None
    AccessMode: str
    FinalURL: str
    ResponseHeaders: list[tuple[str, str]]
    Content: str
    FromCache: bool
    Error_Message: str | None


class NormalizedHTTPRequestType(TypedDict):
    url: str
    method: str
    headers: List[Tuple[str, str]]
    body: Optional[bytes]
    cache_key: str

__all__ = [
    "RequestHeaders",
    "RequestBody",
    "ContentVerdict",
    "WebHelperResult",
    "NormalizedHTTPRequestType",
]
