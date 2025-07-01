"""Content parsing utilities for pyoutlook-db library.

This module provides functionality to parse and convert HTML/XML email content
to clean text and Markdown formats suitable for LLM processing.
"""

import html
import re

import structlog
from bs4 import BeautifulSoup
from markdownify import markdownify

logger = structlog.get_logger(__name__)


class ContentParser:
    """Parses and converts email content from various formats.

    This class handles the conversion of HTML/XML email content to clean text
    and Markdown formats, with special handling for Outlook's specific HTML
    structure and embedded XML.
    """

    def __init__(self) -> None:
        """Initialize the content parser."""
        self.soup_parser = "html.parser"
        logger.debug("Initialized ContentParser")

    def parse_email_content(self, raw_content: str) -> dict[str, str]:
        """Parse email content and return multiple formats.

        Args:
            raw_content: Raw email content (HTML, XML, or plain text)

        Returns:
            Dictionary with 'html', 'text', and 'markdown' keys
        """
        if not raw_content or not raw_content.strip():
            return {"html": "", "text": "", "markdown": ""}

        try:
            # First, try to extract HTML from XML if present
            html_content = self._extract_html_from_xml(raw_content)

            # If no HTML found, treat as plain text
            if not html_content:
                html_content = raw_content

            # Clean and parse the HTML
            cleaned_html = self._clean_html(html_content)

            # Convert to text and markdown
            text_content = self._html_to_text(cleaned_html)
            markdown_content = self._html_to_markdown(cleaned_html)

            return {
                "html": cleaned_html,
                "text": text_content,
                "markdown": markdown_content,
            }

        except Exception as e:
            logger.error("Failed to parse email content", error=str(e))
            # Return raw content as fallback
            return {
                "html": raw_content,
                "text": self._strip_html_tags(raw_content),
                "markdown": self._strip_html_tags(raw_content),
            }

    def _extract_html_from_xml(self, content: str) -> str:
        """Extract HTML content from XML wrapper if present.

        Outlook sometimes wraps HTML content in XML structures.

        Args:
            content: Raw content that may contain XML-wrapped HTML

        Returns:
            Extracted HTML content or original content if no XML found
        """
        try:
            # Look for common XML patterns that wrap HTML
            xml_patterns = [
                r"<html[^>]*>(.*?)</html>",
                r"<body[^>]*>(.*?)</body>",
                r'<div[^>]*class="[^"]*WordSection[^"]*"[^>]*>(.*?)</div>',
            ]

            for pattern in xml_patterns:
                match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
                if match:
                    extracted = match.group(1)
                    logger.debug("Extracted HTML from XML wrapper")
                    return extracted

            # If no XML wrapper found, return original content
            return content

        except Exception as e:
            logger.warning("Failed to extract HTML from XML", error=str(e))
            return content

    def _clean_html(self, html_content: str) -> str:
        """Clean and normalize HTML content.

        Args:
            html_content: Raw HTML content

        Returns:
            Cleaned HTML content
        """
        try:
            # Parse with BeautifulSoup
            soup = BeautifulSoup(html_content, self.soup_parser)

            # Remove script and style elements
            for element in soup(["script", "style"]):
                element.decompose()

            # Remove Outlook-specific elements that don't add value
            outlook_selectors = [
                "[class*='MsoNormal']",
                "[class*='WordSection']",
                "o:p",
                "v:*",  # VML elements
            ]

            for selector in outlook_selectors:
                try:
                    for element in soup.select(selector):
                        element.unwrap()
                except Exception:
                    continue

            # Clean up empty paragraphs and divs
            for tag in soup.find_all(["p", "div"]):
                if not tag.get_text(strip=True):
                    tag.decompose()

            # Convert back to string
            cleaned = str(soup)

            # Additional text cleaning
            cleaned = self._clean_whitespace(cleaned)

            return cleaned

        except Exception as e:
            logger.warning("Failed to clean HTML", error=str(e))
            return html_content

    def _html_to_text(self, html_content: str) -> str:
        """Convert HTML to clean plain text.

        Args:
            html_content: HTML content to convert

        Returns:
            Plain text content
        """
        try:
            soup = BeautifulSoup(html_content, self.soup_parser)

            # Get text content
            text = soup.get_text()

            # Clean up whitespace
            text = self._clean_whitespace(text)

            # Decode HTML entities
            text = html.unescape(text)

            return text.strip()

        except Exception as e:
            logger.warning("Failed to convert HTML to text", error=str(e))
            return self._strip_html_tags(html_content)

    def _html_to_markdown(self, html_content: str) -> str:
        """Convert HTML to Markdown format.

        Args:
            html_content: HTML content to convert

        Returns:
            Markdown formatted content
        """
        try:
            # Use markdownify with custom settings
            markdown = markdownify(
                html_content,
                heading_style="ATX",  # Use # for headings
                bullets="-",  # Use - for bullet points
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

            # Clean up the markdown
            markdown = self._clean_markdown(markdown)

            return markdown.strip()

        except Exception as e:
            logger.warning("Failed to convert HTML to Markdown", error=str(e))
            # Fallback to plain text
            return self._html_to_text(html_content)

    def _clean_whitespace(self, text: str) -> str:
        """Clean up excessive whitespace in text.

        Args:
            text: Text to clean

        Returns:
            Cleaned text
        """
        # Replace multiple whitespace with single space
        text = re.sub(r"\s+", " ", text)

        # Replace multiple newlines with double newline
        text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)

        # Remove leading/trailing whitespace from each line
        lines = [line.strip() for line in text.split("\n")]
        text = "\n".join(lines)

        return text

    def _clean_markdown(self, markdown: str) -> str:
        """Clean up markdown formatting issues.

        Args:
            markdown: Raw markdown text

        Returns:
            Cleaned markdown text
        """
        # Remove excessive blank lines
        markdown = re.sub(r"\n\s*\n\s*\n+", "\n\n", markdown)

        # Fix spacing around headers
        markdown = re.sub(r"\n(#{1,6})\s*([^\n]+)\n", r"\n\n\1 \2\n\n", markdown)

        # Clean up list formatting
        markdown = re.sub(r"\n\s*[-*+]\s*\n", "\n", markdown)  # Remove empty list items

        # Remove trailing spaces
        lines = [line.rstrip() for line in markdown.split("\n")]
        markdown = "\n".join(lines)

        return markdown

    def _strip_html_tags(self, text: str) -> str:
        """Simple HTML tag removal as fallback.

        Args:
            text: Text with HTML tags

        Returns:
            Text with HTML tags removed
        """
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", "", text)

        # Decode HTML entities
        text = html.unescape(text)

        # Clean whitespace
        text = self._clean_whitespace(text)

        return text.strip()

    def extract_links(self, html_content: str) -> list[dict[str, str]]:
        """Extract all links from HTML content.

        Args:
            html_content: HTML content to parse

        Returns:
            List of dictionaries with 'url' and 'text' keys
        """
        links = []

        try:
            soup = BeautifulSoup(html_content, self.soup_parser)

            for link in soup.find_all("a", href=True):
                url = link["href"]
                text = link.get_text(strip=True)

                if url and url.startswith(("http://", "https://", "mailto:")):
                    links.append({"url": url, "text": text or url})

        except Exception as e:
            logger.warning("Failed to extract links", error=str(e))

        return links

    def extract_images(self, html_content: str) -> list[dict[str, str]]:
        """Extract image information from HTML content.

        Args:
            html_content: HTML content to parse

        Returns:
            List of dictionaries with image information
        """
        images = []

        try:
            soup = BeautifulSoup(html_content, self.soup_parser)

            for img in soup.find_all("img"):
                src = img.get("src", "")
                alt = img.get("alt", "")
                title = img.get("title", "")

                if src:
                    images.append({"src": src, "alt": alt, "title": title})

        except Exception as e:
            logger.warning("Failed to extract images", error=str(e))

        return images


# Global parser instance for reuse
_parser_instance: ContentParser | None = None


def get_content_parser() -> ContentParser:
    """Get a shared content parser instance.

    Returns:
        ContentParser instance
    """
    global _parser_instance

    if _parser_instance is None:
        _parser_instance = ContentParser()

    return _parser_instance
