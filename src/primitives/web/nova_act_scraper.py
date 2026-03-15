"""Nova Act Scraper - Web content extraction using AWS Nova Act.

Uses AWS Nova Act multimodal model to extract structured data from web pages,
especially effective for JavaScript-rendered sites that traditional scrapers
can't handle (e.g., HackerNews, X, React apps).

Can use actual screenshot + DOM analysis OR HTML content for simpler sites.

Example:
    >>> from src.primitives.web.nova_act_scraper import NovaActScraper
    >>> scraper = NovaActScraper()
    >>> result = await scraper.execute(
    ...     url="https://news.ycombinator.com",
    ...     extract_query="Get the top 5 stories with their titles, URLs, and vote counts"
    ... )
"""

import json
import base64
import re
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
import asyncio

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

try:
    from playwright.async_api import async_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

from src.primitives.base_primitive import BasePrimitive, PrimitiveResult, register_primitive
from src.utils.aws_sts import get_bedrock_client
from src.utils.config import get_config
from src.utils.logger import get_logger

logger = get_logger()


class ScrapeMethod(str, Enum):
    """Available scraping methods."""
    NOVA_ACT = "nova_act"  # Use Nova Act multimodal (most capable)
    HTML = "html"          # Use simple HTML extraction (fallback)
    AUTO = "auto"          # Try Nova Act first, fallback to HTML


@dataclass
class ExtractedData:
    """Extracted data from a web page."""
    source_url: str
    method_used: str
    extracted_content: Any
    timestamp: str


class NovaActScraper(BasePrimitive):
    """Scrape web content using AWS Nova Act or HTML extraction.
    
    Nova Act method:
    - Sends page URL (optionally with screenshot)
    - Uses Nova Act multimodal model to understand structure
    - Extracts structured data based on natural language query
    - Best for: JavaScript-rendered sites, complex UIs
    
    HTML method:
    - Fetches raw HTML
    - Uses BeautifulSoup for extraction
    - Faster but limited to static content
    - Best for: Static sites, simple HTML
    """

    MAX_NOVA_ACT_SOURCE_CHARS = 16000
    MAX_NOVA_ACT_IMAGE_SOURCE_CHARS = 8000
    
    def __init__(self) -> None:
        """Initialize Nova Act Scraper."""
        super().__init__()
        self._bedrock_client = None
        self._config = get_config()
    
    def _get_bedrock_client(self):
        """Get or create Bedrock client."""
        if self._bedrock_client is None:
            self._bedrock_client = get_bedrock_client()
        return self._bedrock_client
    
    @property
    def name(self) -> str:
        return "web_scrape"
    
    @property
    def description(self) -> str:
        return (
            "Extract structured data from web pages. "
            "Uses AWS Nova Act for JavaScript-rendered sites, "
            "with HTML extraction fallback for static sites. "
            "Provide a URL and describe what to extract."
        )
    
    @property
    def parameters(self) -> Dict[str, Dict[str, Any]]:
        return {
            "url": {
                "type": "string",
                "description": "URL of the web page to scrape",
                "required": True
            },
            "extract_query": {
                "type": "string",
                "description": "What to extract (e.g., 'Get article titles and URLs')",
                "required": True
            },
            "method": {
                "type": "string",
                "description": "Scraping method: nova_act, html, or auto",
                "required": False,
                "default": "auto",
                "enum": [m.value for m in ScrapeMethod]
            },
            "include_html": {
                "type": "boolean",
                "description": "Include raw HTML in output",
                "required": False,
                "default": False
            },
            "timeout": {
                "type": "integer",
                "description": "Request timeout in seconds",
                "required": False,
                "default": 30
            }
        }
    
    async def execute(self, **kwargs) -> PrimitiveResult:
        """Execute web scraping.
        
        Args:
            url: URL to scrape
            extract_query: Natural language description of what to extract
            method: Scraping method (nova_act, html, auto)
            include_html: Whether to include raw HTML
            timeout: Request timeout
            
        Returns:
            PrimitiveResult with extracted data
        """
        url = kwargs.get("url", "").strip()
        extract_query = kwargs.get("extract_query", "").strip()
        method_str = kwargs.get("method", "auto")
        include_html = kwargs.get("include_html", False)
        timeout = kwargs.get("timeout", 30)
        
        if not url:
            return PrimitiveResult(
                success=False,
                data=None,
                message="URL is required",
                error="MissingURL"
            )
        
        if not extract_query:
            return PrimitiveResult(
                success=False,
                data=None,
                message="Extract query is required",
                error="MissingExtractQuery"
            )
        
        try:
            method = ScrapeMethod(method_str)
        except ValueError:
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Invalid method: {method_str}",
                error="InvalidMethod"
            )
        
        # Ensure URL has scheme
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        try:
            result_data = None
            method_used = None
            html_content = None
            errors = []
            
            # Determine method
            methods_to_try = []
            if method == ScrapeMethod.AUTO:
                methods_to_try = [ScrapeMethod.NOVA_ACT, ScrapeMethod.HTML]
            else:
                methods_to_try = [method]
            
            # Try each method
            for m in methods_to_try:
                try:
                    if m == ScrapeMethod.NOVA_ACT:
                        result_data = await self._scrape_with_nova_act(
                            url, extract_query, timeout
                        )
                        method_used = "nova_act"
                        
                    elif m == ScrapeMethod.HTML:
                        result_data, html_content = await self._scrape_with_html(
                            url, extract_query, timeout
                        )
                        method_used = "html"
                    
                    if result_data:
                        break  # Success!
                        
                except Exception as e:
                    error_msg = f"{m.value} failed: {str(e)}"
                    logger.warning(error_msg)
                    errors.append(error_msg)
                    continue
            
            if not result_data:
                return PrimitiveResult(
                    success=False,
                    data=None,
                    message=f"All scraping methods failed. Errors: {'; '.join(errors)}",
                    error="AllMethodsFailed"
                )
            
            # Build response
            response_data = {
                "url": url,
                "method_used": method_used,
                "extract_query": extract_query,
                "extracted_data": result_data
            }
            
            if include_html and html_content:
                response_data["html_preview"] = html_content[:5000]  # First 5KB
            
            return PrimitiveResult(
                success=True,
                data=response_data,
                message=f"Successfully extracted data using {method_used}",
                metadata={
                    "methods_attempted": [m.value for m in methods_to_try],
                    "errors": errors if errors else None
                }
            )
            
        except Exception as e:
            logger.error(f"Scraping error: {e}")
            return PrimitiveResult(
                success=False,
                data=None,
                message=f"Scraping failed: {e}",
                error=str(e)
            )
    
    async def _scrape_with_nova_act(
        self,
        url: str,
        extract_query: str,
        timeout: int
    ) -> Optional[Dict[str, Any]]:
        """Scrape using Nova Act multimodal model.
        
        Uses Playwright to render JS and Bedrock to analyze the content.
        """
        html_content = ""
        page_text = ""
        screenshot_b64 = None
        
        if HAS_PLAYWRIGHT:
            logger.info(f"Using Playwright to render {url}")
            try:
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True)
                    page = await browser.new_page()
                    await page.goto(url, wait_until="networkidle", timeout=timeout*1000)
                    
                    # Get rendered HTML
                    html_content = await page.content()
                    page_text = await page.evaluate("() => document.body?.innerText || ''")
                    page_title = await page.title()
                    if page_title:
                        page_text = f"{page_title}\n{page_text}".strip()
                    
                    # Take screenshot for multimodal analysis (Nova Act specialty)
                    screenshot_bytes = await page.screenshot(type="jpeg", quality=80, full_page=False)
                    screenshot_b64 = screenshot_bytes # Keep as bytes for Bedrock Converse
                    
                    await browser.close()
            except Exception as e:
                logger.warning(f"Playwright failed, falling back to httpx: {e}")
        
        if not html_content:
            logger.info(f"Using httpx for {url}")
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.get(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                )
                response.raise_for_status()
                html_content = response.text
                page_text = response.text
        
        # Truncate if too large using config
        truncated = False
        if len(html_content) > self._config.web.max_html_size:
            html_content = html_content[:self._config.web.max_html_size]
            truncated = True

        source_snapshot, source_label, source_truncated = self._prepare_nova_act_source(
            page_text or html_content,
            extract_query,
        )
        truncated = truncated or source_truncated
        signal_lines = self._extract_signal_lines(source_snapshot, extract_query)

        # Use Bedrock to extract structured data
        client = self._get_bedrock_client()
        model_id = self._config.web.nova_act_model
        
        prompt = f"""
You are a web scraping assistant. Given a condensed page snapshot and optional screenshot, extract the requested information.

URL: {url}
EXTRACTION REQUEST: {extract_query}

{source_label} (may be truncated):
```text
{source_snapshot}
```

HIGH-SIGNAL LINES:
```text
{signal_lines or 'No high-signal lines detected'}
```

Please extract the requested information and return it as JSON. Be precise and extract exactly what was asked for.

Return your response in this format:
```json
{{
    "extracted_items": [
        // Array of extracted items
    ],
    "count": 0,
    "notes": "Any additional notes about the extraction"
}}
```
"""
        # Prepare content items for Bedrock Converse
        content_items = [{"text": prompt}]
        
        # Add image if available
        if screenshot_b64 and len(source_snapshot) <= self.MAX_NOVA_ACT_IMAGE_SOURCE_CHARS:
            content_items.append({
                "image": {
                    "format": "jpeg",
                    "source": {"bytes": screenshot_b64}
                }
            })
        
        response = client.converse(
            modelId=model_id,
            messages=[
                {
                    "role": "user",
                    "content": content_items
                }
            ],
            inferenceConfig={
                "maxTokens": 2000,
                "temperature": 0.1
            }
        )
        
        # Parse response
        output_text = response['output']['message']['content'][0]['text']
        
        # Try to extract JSON
        try:
            # Look for JSON block
            if "```json" in output_text:
                json_start = output_text.find("```json") + 7
                json_end = output_text.find("```", json_start)
                json_str = output_text[json_start:json_end].strip()
            elif "```" in output_text:
                json_start = output_text.find("```") + 3
                json_end = output_text.find("```", json_start)
                json_str = output_text[json_start:json_end].strip()
            else:
                json_str = output_text
            
            extracted = json.loads(json_str)
            extracted["_truncated_html"] = truncated
            return extracted
            
        except json.JSONDecodeError:
            # Return raw text if JSON parsing fails
            return {
                "extracted_text": output_text,
                "_format": "raw",
                "_truncated_html": truncated
            }

    def _prepare_nova_act_source(self, source_text: str, extract_query: str) -> tuple[str, str, bool]:
        """Build a compact text snapshot suitable for model input limits."""
        if HAS_BS4 and "<" in source_text and ">" in source_text:
            soup = BeautifulSoup(source_text, 'lxml')
            for tag in soup(["script", "style", "noscript", "svg"]):
                tag.decompose()
            source = soup.get_text(" ", strip=True)
            label = "VISIBLE PAGE TEXT"
        else:
            source = "\n".join(line.strip() for line in source_text.splitlines() if line.strip())
            label = "RENDERED PAGE TEXT"

        source = self._prioritize_relevant_lines(source, extract_query)

        truncated = len(source) > self.MAX_NOVA_ACT_SOURCE_CHARS
        if truncated:
            source = source[:self.MAX_NOVA_ACT_SOURCE_CHARS]

        return source, label, truncated

    def _prioritize_relevant_lines(self, source: str, extract_query: str) -> str:
        """Move lines likely relevant to the extract query toward the top of the snapshot."""
        lines = [line.strip() for line in source.splitlines() if line.strip()]
        if not lines:
            return source

        keywords = {
            token.lower()
            for token in re.findall(r"[a-zA-Z0-9$]+", extract_query)
            if len(token) > 2
        }
        boosted = []
        remainder = []

        for line in lines:
            lowered = line.lower()
            score = sum(1 for keyword in keywords if keyword in lowered)
            if "$" in line or "usd" in lowered or "price" in lowered:
                score += 2
            if score > 0:
                boosted.append((score, line))
            else:
                remainder.append(line)

        boosted.sort(key=lambda item: item[0], reverse=True)
        prioritized = [line for _, line in boosted[:40]] + remainder[:120]
        return "\n".join(prioritized)

    def _extract_signal_lines(self, source_snapshot: str, extract_query: str) -> str:
        """Extract a compact subset of price-like or query-matching lines for the model."""
        keywords = {
            token.lower()
            for token in re.findall(r"[a-zA-Z0-9$]+", extract_query)
            if len(token) > 2
        }
        lines = []
        for raw_line in source_snapshot.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            lowered = line.lower()
            if any(keyword in lowered for keyword in keywords) or re.search(r"\$\s?\d", line) or "usd" in lowered:
                lines.append(line)
            if len(lines) >= 20:
                break
        return "\n".join(lines)
    
    async def _scrape_with_html(
        self,
        url: str,
        extract_query: str,
        timeout: int
    ) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Scrape using simple HTML extraction.
        
        Returns tuple of (extracted_data, html_content)
        """
        if not HAS_HTTPX:
            raise ImportError("httpx is required")
        
        if not HAS_BS4:
            raise ImportError("beautifulsoup4 is required")
        
        # Fetch HTML
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
            )
            response.raise_for_status()
            html_content = response.text
        
        # Parse with BeautifulSoup
        soup = BeautifulSoup(html_content, 'lxml')
        
        # Remove script and style elements
        for script in soup(["script", "style", "nav", "footer"]):
            script.decompose()
        
        # Extract common elements
        data = {
            "title": soup.title.string if soup.title else None,
            "headings": [],
            "links": [],
            "paragraphs": [],
            "tables": []
        }
        
        # Get headings
        for h in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            data["headings"].append({
                "level": h.name,
                "text": h.get_text(strip=True)
            })
        
        # Get links
        for a in soup.find_all('a', href=True):
            data["links"].append({
                "text": a.get_text(strip=True)[:100],
                "url": a['href']
            })
        
        # Get paragraphs
        for p in soup.find_all('p'):
            text = p.get_text(strip=True)
            if len(text) > 20:
                data["paragraphs"].append(text[:500])
        
        # Get tables (simplified)
        for table in soup.find_all('table'):
            rows = []
            for tr in table.find_all('tr'):
                row = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
                if row:
                    rows.append(row)
            if rows:
                data["tables"].append(rows[:10])  # First 10 rows
        
        # Limit data sizes
        data["links"] = data["links"][:50]
        data["paragraphs"] = data["paragraphs"][:20]
        
        return data, html_content


def register_all() -> None:
    """Register Nova Act scraper primitive."""
    register_primitive(NovaActScraper())
