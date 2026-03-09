"""Firecrawl + BeautifulSoup ingestion engine for scraping public sources."""
import httpx
import asyncio
import json
from datetime import datetime
from typing import Optional
from bs4 import BeautifulSoup

from app.utils.logger import logger
from app.database import get_setting

FIRECRAWL_BASE_URL = "https://api.firecrawl.dev/v1"


async def get_firecrawl_keys() -> list[str]:
    """Get active Firecrawl API keys from settings."""
    keys = []
    key1 = await get_setting("firecrawl_api_key_1")
    key2 = await get_setting("firecrawl_api_key_2")
    if key1:
        keys.append(key1)
    if key2:
        keys.append(key2)
    return keys


async def scrape_with_firecrawl(url: str, api_key: str) -> Optional[dict]:
    """Scrape a URL using Firecrawl API."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{FIRECRAWL_BASE_URL}/scrape",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "url": url,
                    "formats": ["html", "markdown"],
                    "onlyMainContent": False
                }
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    return data.get("data", {})
                logger.warning(f"Firecrawl returned success=false for {url}")
                return None
            elif response.status_code == 429:
                logger.warning(f"Firecrawl rate limited for {url}")
                return None
            else:
                logger.error(f"Firecrawl error {response.status_code} for {url}: {response.text[:200]}")
                return None
    except httpx.TimeoutException:
        logger.error(f"Firecrawl timeout for {url}")
        return None
    except Exception as e:
        logger.error(f"Firecrawl exception for {url}: {e}")
        return None


async def scrape_with_fallback(url: str) -> Optional[dict]:
    """Scrape using Firecrawl with key rotation, falling back to direct HTTP."""
    keys = await get_firecrawl_keys()

    for key in keys:
        result = await scrape_with_firecrawl(url, key)
        if result:
            return {
                "html": result.get("html", ""),
                "markdown": result.get("markdown", ""),
                "metadata": result.get("metadata", {}),
                "method": "firecrawl"
            }

    logger.info(f"Firecrawl failed, falling back to direct HTTP for {url}")
    return await scrape_direct(url)


async def scrape_direct(url: str) -> Optional[dict]:
    """Direct HTTP scraping fallback using BeautifulSoup."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            if response.status_code == 200:
                html = response.text
                soup = BeautifulSoup(html, "html.parser")

                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()

                text = soup.get_text(separator="\n", strip=True)
                return {
                    "html": html,
                    "markdown": text,
                    "metadata": {
                        "title": soup.title.string if soup.title else "",
                        "statusCode": response.status_code
                    },
                    "method": "direct"
                }
            else:
                logger.error(f"Direct scrape failed with {response.status_code} for {url}")
                return None
    except Exception as e:
        logger.error(f"Direct scrape exception for {url}: {e}")
        return None


def parse_scraped_data(scraped: dict, source_name: str, source_url: str) -> dict:
    """Parse scraped data into a standardized format."""
    html = scraped.get("html", "")
    markdown = scraped.get("markdown", "")
    metadata = scraped.get("metadata", {})

    soup = BeautifulSoup(html, "html.parser") if html else None

    items = []
    if soup:
        from urllib.parse import urljoin

        # Try to find event cards, articles, or list items
        selectors = [
            "article", ".event-card", ".campaign-card", ".challenge-card",
            ".post-card", ".blog-post", "[class*='event']", "[class*='card']",
            ".announcement", "section"
        ]
        for selector in selectors:
            elements = soup.select(selector)
            if elements and len(elements) > 0 and len(elements) < 50:
                for elem in elements:
                    item_text = elem.get_text(separator=" ", strip=True)
                    if len(item_text) > 20:
                        # Extract title from headings first, then links, then text
                        heading = elem.find(["h1", "h2", "h3", "h4", "h5"])
                        title = heading.get_text(strip=True) if heading else ""
                        if not title:
                            title_link = elem.find("a")
                            title = title_link.get_text(strip=True) if title_link else ""
                        if not title:
                            title = item_text[:150]

                        # Extract URL from links - try multiple approaches
                        item_url = ""
                        links = elem.find_all("a", href=True)
                        for link in links:
                            href = link["href"]
                            # Skip anchor-only or javascript links
                            if href and not href.startswith("#") and not href.startswith("javascript:"):
                                item_url = href
                                break
                        if item_url and not item_url.startswith("http"):
                            item_url = urljoin(source_url, item_url)
                        # Always fall back to source URL if no valid URL found
                        if not item_url:
                            item_url = source_url

                        items.append({
                            "title": title[:200],
                            "url": item_url,
                            "text": item_text[:2000],
                            "source_url": source_url
                        })
                break

        # If no items found from selectors, extract from page-level headings + links
        if not items:
            all_headings = soup.find_all(["h1", "h2", "h3"], limit=20)
            for heading in all_headings:
                heading_text = heading.get_text(strip=True)
                if heading_text and len(heading_text) > 5:
                    # Find the nearest link
                    heading_link = heading.find("a", href=True)
                    if not heading_link:
                        heading_link = heading.find_parent("a", href=True)
                    item_url = ""
                    if heading_link and heading_link.get("href"):
                        item_url = heading_link["href"]
                        if not item_url.startswith("http"):
                            item_url = urljoin(source_url, item_url)
                    if not item_url:
                        item_url = source_url

                    # Get surrounding context text
                    parent = heading.find_parent(["div", "section", "article"])
                    context_text = parent.get_text(separator=" ", strip=True)[:500] if parent else heading_text

                    items.append({
                        "title": heading_text[:200],
                        "url": item_url,
                        "text": context_text,
                        "source_url": source_url
                    })

    return {
        "source": source_name,
        "type": "update",
        "url": source_url,
        "title": metadata.get("title", source_name),
        "content": markdown[:5000] if markdown else "",
        "timestamp_scraped": datetime.utcnow().isoformat(),
        "detected_fields": {
            "items": items,
            "item_count": len(items),
        },
        "raw_text": markdown[:10000] if markdown else "",
        "method": scraped.get("method", "unknown")
    }
