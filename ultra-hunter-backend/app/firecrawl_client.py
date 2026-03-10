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
                    "onlyMainContent": True
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


# Boilerplate titles/text to ignore (nav items, cookie banners, generic UI elements)
BOILERPLATE_TITLES = {
    "product", "resources", "compare", "download", "business", "company",
    "pricing", "blog", "docs", "updates", "help center", "trust center",
    "api", "team plan", "startups", "playbook", "brand assets", "community",
    "events", "fellows", "cookie policy", "privacy policy", "terms of service",
    "sign in", "sign up", "log in", "log out", "menu", "navigation",
    "home", "about", "contact", "search", "close", "open", "toggle",
    "customize", "only essentials", "accept all", "reject all",
    "vs chatgpt", "vs lovable", "what can i do for you?",
}

BOILERPLATE_PATTERNS = [
    "we use cookies", "cookie policy", "privacy policy", "terms of service",
    "accept all", "only essentials", "customize", "sign in", "sign up",
    "© 20", "all rights reserved", "follow us", "subscribe",
    "toggle navigation", "skip to content", "back to top",
]


def _is_boilerplate(title: str, text: str) -> bool:
    """Check if an item is boilerplate (nav, cookie, footer, etc.)."""
    title_lower = title.lower().strip()
    text_lower = text.lower().strip()

    # Reject if title is a known boilerplate term
    if title_lower in BOILERPLATE_TITLES:
        return True

    # Reject very short titles that are likely nav items (single words)
    if len(title_lower) < 15 and " " not in title_lower and title_lower.isalpha():
        return True

    # Reject if text contains boilerplate patterns
    for pattern in BOILERPLATE_PATTERNS:
        if pattern in text_lower:
            return True

    # Reject items with very little meaningful text (< 50 chars after title)
    remaining_text = text_lower.replace(title_lower, "").strip()
    if len(remaining_text) < 30 and len(title_lower) < 50:
        return True

    return False


def parse_scraped_data(scraped: dict, source_name: str, source_url: str) -> dict:
    """Parse scraped data into a standardized format."""
    html = scraped.get("html", "")
    markdown = scraped.get("markdown", "")
    metadata = scraped.get("metadata", {})

    soup = BeautifulSoup(html, "html.parser") if html else None

    # Strip boilerplate elements from HTML before parsing
    if soup:
        for tag in soup(["nav", "footer", "header", "script", "style", "noscript"]):
            tag.decompose()
        # Remove cookie banners and overlays by common class/id patterns
        for pattern in ["cookie", "consent", "gdpr", "popup", "modal", "overlay",
                        "banner", "notification-bar", "announcement-bar"]:
            for elem in soup.find_all(class_=lambda c: c and pattern in str(c).lower()):
                elem.decompose()
            for elem in soup.find_all(id=lambda i: i and pattern in str(i).lower()):
                elem.decompose()

    items = []
    if soup:
        from urllib.parse import urljoin

        # Try to find event cards, articles, or meaningful content blocks
        # Removed overly broad selectors like "section" and "[class*='card']"
        selectors = [
            "article", ".event-card", ".campaign-card", ".challenge-card",
            ".post-card", ".blog-post", ".announcement",
            "[class*='event-item']", "[class*='campaign-item']",
            "[class*='challenge-item']",
        ]
        for selector in selectors:
            elements = soup.select(selector)
            if elements and len(elements) > 0 and len(elements) < 30:
                for elem in elements:
                    item_text = elem.get_text(separator=" ", strip=True)
                    if len(item_text) > 50:  # Minimum meaningful content length
                        heading = elem.find(["h1", "h2", "h3", "h4", "h5"])
                        title = heading.get_text(strip=True) if heading else ""
                        if not title:
                            title_link = elem.find("a")
                            title = title_link.get_text(strip=True) if title_link else ""
                        if not title:
                            title = item_text[:150]

                        # Skip boilerplate items
                        if _is_boilerplate(title, item_text):
                            continue

                        # Extract URL from links
                        item_url = ""
                        links = elem.find_all("a", href=True)
                        for link in links:
                            href = link["href"]
                            if href and not href.startswith("#") and not href.startswith("javascript:"):
                                item_url = href
                                break
                        if item_url and not item_url.startswith("http"):
                            item_url = urljoin(source_url, item_url)
                        if not item_url:
                            item_url = source_url

                        items.append({
                            "title": title[:200],
                            "url": item_url,
                            "text": item_text[:2000],
                            "source_url": source_url
                        })
                if items:  # Only break if we actually found meaningful items
                    break

        # Fallback: extract from headings that have substantial surrounding content
        if not items:
            main_content = soup.find("main") or soup.find("[role='main']") or soup
            all_headings = main_content.find_all(["h1", "h2", "h3"], limit=15)
            for heading in all_headings:
                heading_text = heading.get_text(strip=True)
                if not heading_text or len(heading_text) < 10:
                    continue

                # Get surrounding context
                parent = heading.find_parent(["div", "section", "article"])
                context_text = parent.get_text(separator=" ", strip=True)[:500] if parent else heading_text

                # Skip boilerplate
                if _is_boilerplate(heading_text, context_text):
                    continue

                # Must have substantial content beyond just the heading
                if len(context_text) < 80:
                    continue

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
