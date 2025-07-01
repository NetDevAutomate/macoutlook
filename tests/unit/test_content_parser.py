"""
Unit tests for ContentParser class.
"""

from pyoutlook_db.parsers.content import ContentParser


class TestContentParser:
    """Test cases for ContentParser class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.parser = ContentParser()

    def test_parse_empty_content(self):
        """Test parsing empty content."""
        result = self.parser.parse_email_content("")

        assert result["html"] == ""
        assert result["text"] == ""
        assert result["markdown"] == ""

    def test_parse_plain_text(self):
        """Test parsing plain text content."""
        content = "This is plain text content."
        result = self.parser.parse_email_content(content)

        assert result["text"] == content
        assert result["markdown"] == content

    def test_parse_simple_html(self):
        """Test parsing simple HTML content."""
        html_content = "<p>This is <strong>bold</strong> text.</p>"
        result = self.parser.parse_email_content(html_content)

        assert "bold" in result["text"]
        assert "**bold**" in result["markdown"]

    def test_clean_whitespace(self):
        """Test whitespace cleaning."""
        text_with_whitespace = "This   has    multiple   spaces\n\n\n\nand newlines"
        result = self.parser._clean_whitespace(text_with_whitespace)

        assert "   " not in result
        assert "\n\n\n" not in result

    def test_strip_html_tags(self):
        """Test HTML tag stripping."""
        html_content = "<p>This is <strong>bold</strong> text.</p>"
        result = self.parser._strip_html_tags(html_content)

        assert "<p>" not in result
        assert "<strong>" not in result
        assert "This is bold text." in result

    def test_extract_links(self):
        """Test link extraction from HTML."""
        html_content = '''
        <p>Visit <a href="https://example.com">our website</a> or 
        <a href="mailto:test@example.com">email us</a>.</p>
        '''

        links = self.parser.extract_links(html_content)

        assert len(links) == 2
        assert any(link["url"] == "https://example.com" for link in links)
        assert any(link["url"] == "mailto:test@example.com" for link in links)

    def test_extract_images(self):
        """Test image extraction from HTML."""
        html_content = '''
        <p>Here's an image: <img src="image.jpg" alt="Test Image" title="A test image"></p>
        '''

        images = self.parser.extract_images(html_content)

        assert len(images) == 1
        assert images[0]["src"] == "image.jpg"
        assert images[0]["alt"] == "Test Image"
        assert images[0]["title"] == "A test image"

    def test_parse_outlook_xml_wrapper(self):
        """Test parsing HTML wrapped in XML (common in Outlook)."""
        xml_content = '''
        <html>
        <body>
        <div class="WordSection1">
        <p>This is content wrapped in XML.</p>
        </div>
        </body>
        </html>
        '''

        result = self.parser.parse_email_content(xml_content)

        assert "This is content wrapped in XML." in result["text"]

    def test_error_handling(self):
        """Test error handling with malformed content."""
        malformed_content = "<p>Unclosed tag <strong>bold text"

        # Should not raise an exception
        result = self.parser.parse_email_content(malformed_content)

        assert isinstance(result, dict)
        assert "html" in result
        assert "text" in result
        assert "markdown" in result
