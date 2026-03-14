"""Unit tests for ContentParser class."""

from macoutlook.parsers.content import ContentParser


class TestContentParser:
    def setup_method(self):
        self.parser = ContentParser()

    def test_parse_empty_content(self):
        result = self.parser.parse_email_content("")
        assert result["html"] == ""
        assert result["text"] == ""
        assert result["markdown"] == ""

    def test_parse_plain_text(self):
        content = "This is plain text content."
        result = self.parser.parse_email_content(content)
        assert result["text"] == content
        assert result["markdown"] == content

    def test_parse_simple_html(self):
        html_content = "<p>This is <strong>bold</strong> text.</p>"
        result = self.parser.parse_email_content(html_content)
        assert "bold" in result["text"]
        assert "**bold**" in result["markdown"]

    def test_clean_whitespace(self):
        text = "This   has    multiple   spaces\n\n\n\nand newlines"
        result = self.parser._clean_whitespace(text)
        assert "   " not in result
        assert "\n\n\n" not in result

    def test_strip_html_tags(self):
        html_content = "<p>This is <strong>bold</strong> text.</p>"
        result = self.parser._strip_html_tags(html_content)
        assert "<p>" not in result
        assert "<strong>" not in result
        assert "This is bold text." in result

    def test_parse_outlook_xml_wrapper(self):
        xml_content = """
        <html>
        <body>
        <div class="WordSection1">
        <p>This is content wrapped in XML.</p>
        </div>
        </body>
        </html>
        """
        result = self.parser.parse_email_content(xml_content)
        assert "This is content wrapped in XML." in result["text"]

    def test_error_handling_malformed_html(self):
        malformed = "<p>Unclosed tag <strong>bold text"
        result = self.parser.parse_email_content(malformed)
        assert isinstance(result, dict)
        assert "html" in result
        assert "text" in result
        assert "markdown" in result
