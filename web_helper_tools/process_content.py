from dataclasses import dataclass
from typing import Protocol


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
    def process(self, content: str) -> str:
        # TODO: 保守轻清洗 HTML,规则单独迭代。
        return content


_PROCESSORS: dict[str, ContentProcessor] = {
    "text/html": HtmlContentProcessor(),
}
_DEFAULT_PROCESSOR = DefaultContentProcessor()


def ProcessContent(content: str, content_type: str | None) -> ContentProcessingResult:
    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    processor = _PROCESSORS.get(media_type, _DEFAULT_PROCESSOR)
    return ContentProcessingResult(
        raw_content=content,
        content=processor.process(content),
        content_type=media_type,
    )
