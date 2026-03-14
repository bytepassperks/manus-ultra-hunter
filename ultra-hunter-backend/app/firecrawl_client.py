"""Firecrawl + BeautifulSoup ingestion engine for scraping public sources."""
import httpx
import asyncio
import json
from datetime import datetime
from typing import Optional
from bs4 import BeautifulSoup

import re
from urllib.parse import urljoin, urlparse

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


# Patterns for discovering important subpage links (live events, campaigns, etc.)
LINK_DISCOVERY_PATTERNS = [
    r'/live-events/[A-Za-z0-9_-]+',
    r'/campaign/[A-Za-z0-9_-]+',
    r'/events/[A-Za-z0-9_%-]+',
]

# Localized path prefixes to skip (e.g., /fr/live-events/, /de/campaign/)
# We only want English (root) URLs, not /fr/, /de/, /es/, /ja/, etc.
_LOCALE_PREFIX_RE = re.compile(
    r'^/(ar|de|es|es-419|fr|hi|it|ja|ko|pt-br|pt-pt|th|tr|vi|zh-cn|zh-tw)/'
)


def _is_localized_url(path: str) -> bool:
    """Return True if the URL path starts with a locale prefix like /fr/ or /ja/."""
    return bool(_LOCALE_PREFIX_RE.match(path))


def extract_discovered_links(html: str, source_url: str) -> list[dict]:
    """Extract important subpage links from HTML that should be auto-monitored.
    
    This catches live event pages, campaign pages, etc. that appear as links
    on the homepage or other pages but aren't in the structured items.
    """
    discovered = []
    seen_urls = set()
    
    if not html:
        return discovered
    
    soup = BeautifulSoup(html, "html.parser")
    base_domain = urlparse(source_url).netloc  # e.g., manus.im
    
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if not href or href.startswith("#") or href.startswith("javascript:"):
            continue
        
        # Resolve relative URLs
        full_url = href if href.startswith("http") else urljoin(source_url, href)
        parsed = urlparse(full_url)
        
        # Only consider links on manus.im domain
        if "manus.im" not in parsed.netloc:
            continue
        
        path = parsed.path.rstrip("/")
        
        # Skip localized versions (e.g., /fr/live-events/, /ja/live-events/)
        if _is_localized_url(path):
            continue
        
        for pattern in LINK_DISCOVERY_PATTERNS:
            if re.search(pattern, path):
                if full_url not in seen_urls:
                    seen_urls.add(full_url)
                    link_text = a_tag.get_text(strip=True)[:200]
                    discovered.append({
                        "url": full_url.rstrip("/"),
                        "text": link_text,
                        "path": path,
                    })
                break
    
    # Also search in raw text for URLs (some are in onclick, data attrs, etc.)
    for pattern in LINK_DISCOVERY_PATTERNS:
        full_pattern = r'https?://[a-zA-Z0-9.-]*manus\.im' + pattern
        for match in re.finditer(full_pattern, html):
            url = match.group(0).rstrip('"\'/)')
            url_path = urlparse(url).path
            if _is_localized_url(url_path):
                continue
            if url not in seen_urls:
                seen_urls.add(url)
                discovered.append({
                    "url": url,
                    "text": "",
                    "path": url_path,
                })
    
    return discovered


async def probe_live_event_urls() -> list[dict]:
    """Proactively discover live event/campaign URLs that may not be linked in static HTML.
    
    Uses multiple strategies:
    1. Firecrawl map endpoint to crawl manus.im and find subpages
    2. Sitemap.xml parsing
    3. Direct HTTP check of known live-events listing page
    
    Returns list of discovered link dicts: [{url, text, path}, ...]
    """
    discovered = []
    seen_urls: set[str] = set()

    # Strategy 1: Use Firecrawl map endpoint to discover URLs under manus.im
    keys = await get_firecrawl_keys()
    for api_key in keys:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{FIRECRAWL_BASE_URL}/map",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "url": "https://manus.im",
                        "search": "live-events OR campaign OR events",
                        "limit": 100,
                    }
                )
                if response.status_code == 200:
                    data = response.json()
                    links = data.get("links", [])
                    logger.info(f"Firecrawl map returned {len(links)} URLs for manus.im")
                    for link_url in links:
                        if not isinstance(link_url, str):
                            continue
                        parsed = urlparse(link_url)
                        path = parsed.path.rstrip("/")
                        if _is_localized_url(path):
                            continue
                        for pattern in LINK_DISCOVERY_PATTERNS:
                            if re.search(pattern, path):
                                if link_url not in seen_urls:
                                    seen_urls.add(link_url)
                                    slug = path.split("/")[-1]
                                    discovered.append({
                                        "url": link_url.rstrip("/"),
                                        "text": slug,
                                        "path": path,
                                    })
                                break
                    if discovered:
                        break  # Got results, no need to try next key
                else:
                    logger.warning(f"Firecrawl map returned {response.status_code}: {response.text[:200]}")
        except Exception as e:
            logger.error(f"Firecrawl map probe error: {e}")

    # Strategy 2: Check sitemap.xml for live event URLs
    sitemap_urls = [
        "https://manus.im/sitemap.xml",
        "https://manus.im/sitemap-0.xml",
    ]
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            for sitemap_url in sitemap_urls:
                try:
                    resp = await client.get(sitemap_url)
                    if resp.status_code == 200 and resp.text:
                        # Parse XML sitemap for URLs matching our patterns
                        for pattern in LINK_DISCOVERY_PATTERNS:
                            full_pattern = r'https?://[a-zA-Z0-9.-]*manus\.im' + pattern
                            for match in re.finditer(full_pattern, resp.text):
                                url = match.group(0).rstrip('"\'/>')
                                parsed = urlparse(url)
                                url_path = parsed.path.rstrip("/")
                                if _is_localized_url(url_path):
                                    continue
                                if url not in seen_urls:
                                    seen_urls.add(url)
                                    slug = url_path.split("/")[-1]
                                    discovered.append({
                                        "url": url.rstrip("/"),
                                        "text": slug,
                                        "path": url_path,
                                    })
                        logger.info(f"Sitemap {sitemap_url}: found {len(discovered)} relevant URLs so far")
                except Exception as e:
                    logger.debug(f"Sitemap {sitemap_url} check failed: {e}")
    except Exception as e:
        logger.error(f"Sitemap probe error: {e}")

    # Strategy 3: Scrape the live-events listing page directly (it may work sometimes)
    try:
        listing_result = await scrape_with_fallback("https://manus.im/live-events/")
        if listing_result:
            html = listing_result.get("html", "")
            if html and len(html) > 500:  # Not a 404 page
                links_from_listing = extract_discovered_links(html, "https://manus.im/live-events/")
                for link in links_from_listing:
                    if link["url"] not in seen_urls:
                        seen_urls.add(link["url"])
                        discovered.append(link)
                logger.info(f"Live events listing page yielded {len(links_from_listing)} links")
    except Exception as e:
        logger.debug(f"Live events listing probe failed: {e}")

    logger.info(f"Proactive URL probe complete: discovered {len(discovered)} total URLs")
    return discovered


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

    # Discover important subpage links (live events, campaigns, etc.)
    discovered_links = extract_discovered_links(html, source_url)
    if discovered_links:
        logger.info(f"Discovered {len(discovered_links)} important links from {source_name}: {[l['url'] for l in discovered_links]}")

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
            "discovered_links": discovered_links,
        },
        "raw_text": markdown[:10000] if markdown else "",
        "method": scraped.get("method", "unknown")
    }
