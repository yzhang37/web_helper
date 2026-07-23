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
    # 传输层出口(如 http://user:pass@host:8080 / socks5://host:1080)。两条腿共用同一个值,
    # 所以 curl 升级 browser 时出口不会掉。**不参与缓存键** —— 它是传输层,不是请求语义。
    proxy: str


class FetchResult(TypedDict):
    StatusCode: Optional[int]
    StatusCodeText: str
    FinalURL: str
    ResponseHeaders: ResponseHeaders
    ContentType: str
    Content: str
    storageState: dict[str, Any] | None


class ContentVerdict(StrEnum):
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
