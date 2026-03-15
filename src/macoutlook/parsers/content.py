"""Content parsing utilities for macoutlook library.

Converts HTML/XML email content to clean text and Markdown formats.
"""

import html
import logging
import re

from bs4 import BeautifulSoup
from markdownify import markdownify

logger = logging.getLogger(__name__)


class ContentParser:
    """Parses and converts email content from various formats.

    Handles conversion of HTML/XML email content to clean text and Markdown,
    with special handling for Outlook's specific HTML structure.
    """

    def __init__(self) -> None:
        self.soup_parser = "html.parser"

    def parse_email_content(self, raw_content: str) -> dict[str, str]:
        """Parse email content and return multiple formats.

        Returns:
            Dictionary with 'html', 'text', and 'markdown' keys.
        """
        if not raw_content or not raw_content.strip():
            return {"html": "", "text": "", "markdown": ""}

        try:
            html_content = self._extract_html_from_xml(raw_content)
            if not html_content:
                html_content = raw_content

            # Parse HTML once, reuse the soup object for cleaning and text extraction
            soup = BeautifulSoup(html_content, self.soup_parser)
            self._clean_soup(soup)

            # Extract text directly from the already-parsed soup (avoids re-parsing)
            text_content = self._text_from_soup(soup)

            # Serialize to string only for HTML output and markdown conversion
            cleaned_html = self._serialize_soup(soup)
            markdown_content = self._html_to_markdown(cleaned_html)

            return {
                "html": cleaned_html,
                "text": text_content,
                "markdown": markdown_content,
            }

        except Exception as e:
            logger.error("Failed to parse email content: %s", e)
            return {
                "html": raw_content,
                "text": self._strip_html_tags(raw_content),
                "markdown": self._strip_html_tags(raw_content),
            }

    def _extract_html_from_xml(self, content: str) -> str:
        """Extract HTML content from XML wrapper if present."""
        try:
            xml_patterns = [
                r"<html[^>]*>(.*?)</html>",
                r"<body[^>]*>(.*?)</body>",
                r'<div[^>]*class="[^"]*WordSection[^"]*"[^>]*>(.*?)</div>',
            ]

            for pattern in xml_patterns:
                match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
                if match:
                    return match.group(1)

            return content

        except Exception as e:
            logger.warning("Failed to extract HTML from XML: %s", e)
            return content

    def _clean_html(self, html_content: str) -> str:
        """Clean and normalize HTML content.

        Convenience wrapper that parses, cleans, and serializes in one call.
        Prefer _clean_soup() + _serialize_soup() when you already have a soup object.
        """
        try:
            soup = BeautifulSoup(html_content, self.soup_parser)
            self._clean_soup(soup)
            return self._serialize_soup(soup)

        except Exception as e:
            logger.warning("Failed to clean HTML: %s", e)
            return html_content

    def _clean_soup(self, soup: BeautifulSoup) -> None:
        """Clean and normalize a BeautifulSoup object in place.

        Removes scripts, styles, empty tags, and unwraps Outlook-specific markup.
        Modifies the soup object directly rather than returning a new one.
        """
        for element in soup(["script", "style"]):
            element.decompose()

        outlook_selectors = [
            "[class*='MsoNormal']",
            "[class*='WordSection']",
            "o:p",
        ]

        for selector in outlook_selectors:
            try:
                for element in soup.select(selector):
                    element.unwrap()
            except Exception:  # noqa: S112  # nosec B112
                continue

        for tag in soup.find_all(["p", "div"]):
            if not tag.get_text(strip=True):
                tag.decompose()

    def _serialize_soup(self, soup: BeautifulSoup) -> str:
        """Serialize a BeautifulSoup object to a cleaned HTML string."""
        cleaned = str(soup)
        cleaned = self._clean_whitespace(cleaned)
        return cleaned

    def _text_from_soup(self, soup: BeautifulSoup) -> str:
        """Extract clean plain text from an already-parsed BeautifulSoup object."""
        try:
            text = soup.get_text()
            text = self._clean_whitespace(text)
            text = html.unescape(text)
            return text.strip()

        except Exception as e:
            logger.warning("Failed to extract text from soup: %s", e)
            return self._strip_html_tags(str(soup))

    def _html_to_text(self, html_content: str) -> str:
        """Convert HTML to clean plain text.

        Convenience wrapper that parses and extracts text in one call.
        Prefer _text_from_soup() when you already have a soup object.
        """
        try:
            soup = BeautifulSoup(html_content, self.soup_parser)
            text = soup.get_text()
            text = self._clean_whitespace(text)
            text = html.unescape(text)
            return text.strip()

        except Exception as e:
            logger.warning("Failed to convert HTML to text: %s", e)
            return self._strip_html_tags(html_content)

    def _html_to_markdown(self, html_content: str) -> str:
        """Convert HTML to Markdown format."""
        try:
            markdown = markdownify(
                html_content,
                heading_style="ATX",
                bullets="-",
                convert=[
                    "b",
                    "strong",
                    "i",
                    "em",
                    "u",
                    "a",
                    "p",
                    "br",
                    "h1",
                    "h2",
                    "h3",
                    "h4",
                    "h5",
                    "h6",
                    "ul",
                    "ol",
                    "li",
                    "blockquote",
                ],
            )
            markdown = self._clean_markdown(markdown)
            return markdown.strip()

        except Exception as e:
            logger.warning("Failed to convert HTML to Markdown: %s", e)
            return self._html_to_text(html_content)

    def _clean_whitespace(self, text: str) -> str:
        """Clean up excessive whitespace."""
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
        lines = [line.strip() for line in text.split("\n")]
        return "\n".join(lines)

    def _clean_markdown(self, markdown: str) -> str:
        """Clean up markdown formatting issues."""
        markdown = re.sub(r"\n\s*\n\s*\n+", "\n\n", markdown)
        markdown = re.sub(r"\n(#{1,6})\s*([^\n]+)\n", r"\n\n\1 \2\n\n", markdown)
        markdown = re.sub(r"\n\s*[-*+]\s*\n", "\n", markdown)
        lines = [line.rstrip() for line in markdown.split("\n")]
        return "\n".join(lines)

    def _strip_html_tags(self, text: str) -> str:
        """Simple HTML tag removal as fallback."""
        text = re.sub(r"<[^>]+>", "", text)
        text = html.unescape(text)
        text = self._clean_whitespace(text)
        return text.strip()
