from enum import StrEnum
from typing import *

RequestHeaders = Mapping[str, str] | Sequence[tuple[str, str]]
RequestBody = str | bytes | bytearray | Mapping[str, Any] | Sequence[Any]
ResponseHeaders = list[list[str]]


class FetchPayload(TypedDict, total=False):
    url: str
    method: str
    body: RequestBody
    headers: dict[str, str] | list[list[str]]
    storageState: dict[str, Any]
    timeoutMs: int


class FetchResult(TypedDict):
    StatusCode: Optional[int]
    StatusCodeText: str
    FinalURL: str
    ResponseHeaders: ResponseHeaders
    ContentType: str
    Content: str
    storageState: dict[str, Any] | None


class ContentVerdict(StrEnum):
    """Classify 的粗判结果:内容拿到了 / 被挡 / 空。

    不含 'error' —— 传输失败(连不上/超时)由抓取腿单独标,不是 classify 的结论。
    """
    OK = "ok"
    BLOCKED = "blocked"
    NO_CONTENT = "no_content"


class WebHelperResult(TypedDict):
    StatusCode: int | None
    StatusCodeText: str
    AccessMode: str
    FinalURL: str
    ResponseHeaders: ResponseHeaders
    Content: str
    FromCache: bool
    Error_Message: str | None


class NormalizedHTTPRequestType(TypedDict):
    url: str
    method: str
    headers: List[Tuple[str, str]]
    body: Optional[bytes]


__all__ = [
    "RequestHeaders",
    "RequestBody",
    "ResponseHeaders",
    "FetchPayload",
    "FetchResult",
    "ContentVerdict",
    "WebHelperResult",
    "NormalizedHTTPRequestType",
]
