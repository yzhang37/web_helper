import unittest

from web_helper_tools.process_content import HtmlContentProcessor, ProcessContent


class HtmlContentProcessorEventRoutingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.processor = HtmlContentProcessor()

    def test_preserves_literal_detail_route(self) -> None:
        result = self.processor.process('<a onclick="view(\'360\');">Role</a>')
        self.assertIn('onclick="view(\'360\');"', result)

    def test_removes_executable_dom_handler(self) -> None:
        result = self.processor.process(
            '<a onclick="document.getElementById(\'content\').focus(); return false">Skip</a>'
        )
        self.assertNotIn("onclick", result)

    def test_removes_non_click_event_even_when_simple(self) -> None:
        result = self.processor.process('<body onload="boot(1)">Page</body>')
        self.assertNotIn("onload", result)


class ContentProcessorRoutingTest(unittest.TestCase):
    def test_standard_xhtml_media_type_uses_html_processor(self) -> None:
        result = ProcessContent(
            "<style>main { color: red; }</style><main>Jobs</main>",
            "application/xhtml+xml; charset=utf-8",
        )

        self.assertEqual(result.content_type, "application/xhtml+xml")
        self.assertNotIn("<style>", result.content)
        self.assertIn("<main>Jobs</main>", result.content)


if __name__ == "__main__":
    unittest.main()
