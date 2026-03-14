"""Source registry for managing monitoring targets."""
import json
from datetime import datetime
from typing import Optional

from app.database import (
    get_all_sources, get_source, get_source_by_name,
    upsert_source, update_source_check, get_latest_snapshot,
    save_snapshot, add_detection, delete_source,
    get_all_sources,
)
from app.firecrawl_client import scrape_with_fallback, parse_scraped_data
from app.diff_engine import compute_content_diff
from app.ai_classifier import classify_update
from app.utils.hashing import compute_hash
from app.utils.text_cleaner import extract_keywords, extract_credit_info
from app.utils.logger import logger


async def check_source(source_id: int) -> dict:
    """Check a single source for updates."""
    source = await get_source(source_id)
    if not source:
        return {"error": "Source not found"}

    source_name = source["name"]
    source_url = source["url"]
    logger.info(f"Checking source: {source_name} ({source_url})")

    try:
        scraped = await scrape_with_fallback(source_url)
        if not scraped:
            await update_source_check(source_id, "", error="Failed to scrape")
            return {"error": "Failed to scrape", "source": source_name}

        parsed = parse_scraped_data(scraped, source_name, source_url)
        content = parsed.get("content", "")
        items = parsed.get("detected_fields", {}).get("items", [])
        content_hash = compute_hash(content)

        # Get previous snapshot
        prev_snapshot = await get_latest_snapshot(source_id)
        old_content = prev_snapshot["content"] if prev_snapshot else None
        old_items_json = prev_snapshot["items_json"] if prev_snapshot else None

        # Compute diff
        diff_result = compute_content_diff(
            old_content, content,
            old_items_json, items
        )

        # Save new snapshot
        await save_snapshot(source_id, content_hash, content, json.dumps(items))
        await update_source_check(source_id, content_hash, content)

        detections = []

        if diff_result.has_changes:
            logger.info(f"Changes detected for {source_name}: {diff_result.summary}")

            # Process new items
            for item in diff_result.new_items:
                detection_data = {
                    "source": source_name,
                    "title": item.get("title", "New item"),
                    "content": item.get("text", ""),
                    "detection_type": "new_item",
                    "changes_summary": "New item appeared"
                }
                classification = await classify_update(detection_data)

                det_id = await add_detection(
                    source_id=source_id,
                    detection_type="new_item",
                    title=item.get("title", "New item")[:200],
                    url=item.get("url") or source_url,
                    content=item.get("text", "")[:5000],
                    raw_text=item.get("text", ""),
                    detected_fields=item,
                    priority=classification["priority"],
                    summary=classification["summary"],
                    action=classification["action"],
                    detected_rewards=classification["detected_rewards"]
                )
                detections.append({
                    "id": det_id,
                    "type": "new_item",
                    "priority": classification["priority"],
                    "title": item.get("title", "")[:100]
                })

            # Process changed items
            for change in diff_result.changed_items:
                new_text = change.get("new", {}).get("text", "")
                old_text = change.get("old", {}).get("text", "")
                detection_data = {
                    "source": source_name,
                    "title": change.get("title", "Changed item"),
                    "content": new_text,
                    "detection_type": "changed_item",
                    "changes_summary": f"Item changed: {change.get('title', '')}"
                }
                classification = await classify_update(detection_data)

                # Build human-readable content instead of raw JSON
                readable_content = new_text[:2000]
                if old_text and new_text and old_text != new_text:
                    readable_content = f"Updated content: {new_text[:1500]}"

                det_id = await add_detection(
                    source_id=source_id,
                    detection_type="changed_item",
                    title=change.get("title", "Changed item")[:200],
                    url=change.get("new", {}).get("url") or source_url,
                    content=readable_content[:5000],
                    raw_text=new_text,
                    detected_fields=change,
                    priority=classification["priority"],
                    summary=classification["summary"],
                    action=classification["action"],
                    detected_rewards=classification["detected_rewards"]
                )
                detections.append({
                    "id": det_id,
                    "type": "changed_item",
                    "priority": classification["priority"],
                    "title": change.get("title", "")[:100]
                })

            # Process significant text changes — only if truly important
            important_text_changes = [c for c in diff_result.text_changes if c.get("important")]
            if important_text_changes and not diff_result.new_items and not diff_result.changed_items:
                combined_text = "\n".join(c["text"] for c in important_text_changes)

                # Skip if the combined text is too short or looks like nav noise
                if len(combined_text.strip()) < 50:
                    logger.info(f"Skipping text_change for {source_name}: combined text too short ({len(combined_text)} chars)")
                else:
                    detection_data = {
                        "source": source_name,
                        "title": f"Text changes on {source_name}",
                        "content": combined_text,
                        "detection_type": "text_change",
                        "changes_summary": diff_result.summary
                    }
                    classification = await classify_update(detection_data)

                    # Only create detection if classifier says MEDIUM or above
                    if classification["priority"] in ("CRITICAL", "HIGH", "MEDIUM"):
                        det_id = await add_detection(
                            source_id=source_id,
                            detection_type="text_change",
                            title=f"Text changes on {source_name}",
                            url=source_url,
                            content=combined_text[:5000],
                            raw_text=combined_text,
                            detected_fields={"changes": important_text_changes},
                            priority=classification["priority"],
                            summary=classification["summary"],
                            action=classification["action"],
                            detected_rewards=classification["detected_rewards"]
                        )
                        detections.append({
                            "id": det_id,
                            "type": "text_change",
                            "priority": classification["priority"]
                        })
                    else:
                        logger.info(f"Skipping LOW text_change for {source_name}: not worth notifying")

        # Auto-discover and register new live event / campaign subpages
        discovered_links = parsed.get("detected_fields", {}).get("discovered_links", [])
        if discovered_links:
            await _auto_register_discovered_sources(discovered_links, source_name)

        return {
            "source": source_name,
            "has_changes": diff_result.has_changes,
            "change_severity": diff_result.change_severity,
            "summary": diff_result.summary,
            "detections": detections,
            "method": parsed.get("method", "unknown")
        }

    except Exception as e:
        logger.error(f"Error checking source {source_name}: {e}", exc_info=True)
        await update_source_check(source_id, "", error=str(e))
        return {"error": str(e), "source": source_name}


async def _auto_register_discovered_sources(discovered_links: list, parent_source: str):
    """Auto-register newly discovered live event / campaign URLs as sources."""
    existing_sources = await get_all_sources()
    existing_urls = {s["url"].rstrip("/") for s in existing_sources}

    for link in discovered_links:
        url = link["url"].rstrip("/")
        if url in existing_urls:
            continue  # Already monitoring this URL

        path = link.get("path", "")
        link_text = link.get("text", "")

        # Generate a name for the source
        if "/live-events/" in path:
            slug = path.split("/live-events/")[-1]
            name = f"Live Event: {link_text or slug}"
        elif "/campaign/" in path:
            slug = path.split("/campaign/")[-1]
            name = f"Campaign: {link_text or slug}"
        elif "/events/" in path:
            slug = path.split("/events/")[-1]
            name = f"Event: {link_text or slug}"
        else:
            name = f"Discovered: {link_text or url}"

        name = name[:200]
        logger.info(f"Auto-registering discovered source: {name} -> {url} (found via {parent_source})")

        try:
            await upsert_source(
                name=name,
                url=url,
                source_type="webpage",
                check_interval=30,  # Check live events frequently
                is_active=True,
            )
            logger.info(f"Successfully registered new source: {name}")
        except Exception as e:
            logger.error(f"Failed to register discovered source {url}: {e}")
