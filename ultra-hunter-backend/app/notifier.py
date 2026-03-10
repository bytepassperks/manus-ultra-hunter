"""Telegram notification system for sending alerts."""
import httpx
import asyncio
from datetime import datetime
from typing import Optional

from app.database import get_setting, mark_detection_notified, get_unnotified_detections
from app.utils.logger import logger

TELEGRAM_API_BASE = "https://api.telegram.org/bot"


async def get_telegram_config() -> tuple[Optional[str], Optional[str]]:
    """Get Telegram bot token and chat ID from settings."""
    bot_token = await get_setting("telegram_bot_token")
    chat_id = await get_setting("telegram_chat_id")
    return bot_token, chat_id


async def send_telegram_message(text: str, parse_mode: str = "HTML") -> bool:
    """Send a message via Telegram bot."""
    bot_token, chat_id = await get_telegram_config()
    if not bot_token or not chat_id:
        logger.warning(f"Telegram not configured - bot_token={'set' if bot_token else 'missing'}, chat_id={'set' if chat_id else 'missing'}")
        return False

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            payload = {
                "chat_id": chat_id,
                "text": text,
                "disable_web_page_preview": False
            }
            if parse_mode:
                payload["parse_mode"] = parse_mode
            response = await client.post(
                f"{TELEGRAM_API_BASE}{bot_token}/sendMessage",
                json=payload
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    logger.info("Telegram message sent successfully")
                    return True
                logger.error(f"Telegram API returned ok=false: {data}")
                # Retry without formatting if parse error
                if "parse" in str(data).lower():
                    return await _send_plain_text(bot_token, chat_id, text)
                return False
            else:
                logger.error(f"Telegram API error {response.status_code}: {response.text[:300]}")
                # Retry without formatting on 400 (likely parse error)
                if response.status_code == 400:
                    return await _send_plain_text(bot_token, chat_id, text)
                return False
    except Exception as e:
        logger.error(f"Telegram send exception: {type(e).__name__}: {e}")
        return False


async def _send_plain_text(bot_token: str, chat_id: str, text: str) -> bool:
    """Fallback: send message as plain text without formatting."""
    import re
    clean_text = re.sub(r'<[^>]+>', '', text)  # strip HTML tags
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{TELEGRAM_API_BASE}{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": clean_text}
            )
            if response.status_code == 200 and response.json().get("ok"):
                logger.info("Telegram message sent as plain text fallback")
                return True
            logger.error(f"Telegram plain text fallback also failed: {response.text[:200]}")
            return False
    except Exception as e:
        logger.error(f"Telegram plain text fallback exception: {e}")
        return False


def _escape_html(text: str) -> str:
    """Escape HTML special characters for Telegram."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_alert_message(detection: dict) -> str:
    """Format a detection into a Telegram alert message (HTML format)."""
    priority = detection.get("priority", "LOW")

    priority_emoji = {
        "CRITICAL": "\U0001f6a8",
        "HIGH": "\u26a0\ufe0f",
        "MEDIUM": "\U0001f4cb",
        "LOW": "\U0001f4ac"
    }

    emoji = priority_emoji.get(priority, "\U0001f4ac")

    title = _escape_html(detection.get("title", "Unknown")[:200])
    det_type = _escape_html(detection.get("detection_type", "update"))
    raw_url = detection.get("url", "") or ""
    summary = _escape_html(detection.get("summary", "No summary available")[:500])
    rewards = _escape_html(detection.get("detected_rewards", "")) if detection.get("detected_rewards") else "None detected"
    action = _escape_html(detection.get("action", "Monitor"))
    source = _escape_html(detection.get("source_name", detection.get("source", "Unknown")))
    timestamp = detection.get("created_at", datetime.utcnow().isoformat())

    # Build clickable URL - always show a link
    if raw_url and raw_url.startswith("http"):
        url_display = f'<a href="{_escape_html(raw_url)}">{_escape_html(raw_url)}</a>'
    else:
        url_display = "N/A"

    # Include content snippet if available
    content = detection.get("content", "") or detection.get("raw_text", "")
    content_snippet = ""
    if content and len(content) > 30:
        clean_content = _escape_html(content[:300].strip())
        if clean_content and clean_content != title:
            content_snippet = f"\n<b>Content:</b> {clean_content}..." if len(content) > 300 else f"\n<b>Content:</b> {clean_content}"

    message = (
        f"{emoji} <b>{priority} MANUS UPDATE DETECTED</b>\n\n"
        f"<b>Title:</b> {title}\n"
        f"<b>Type:</b> {det_type}\n"
        f"<b>URL:</b> {url_display}\n"
        f"<b>Summary:</b> {summary}\n"
        f"<b>Rewards:</b> {rewards}\n"
        f"<b>Recommended Action:</b> {action}{content_snippet}\n"
        f"<b>Source:</b> {source}\n"
        f"<b>Time:</b> {timestamp}"
    )
    return message


async def send_detection_alert(detection: dict) -> bool:
    """Send a single detection as a Telegram alert."""
    det_id = detection.get("id", "unknown")
    det_title = detection.get("title", "unknown")
    logger.info(f"Sending alert for detection #{det_id}: {det_title}")
    message = format_alert_message(detection)
    success = await send_telegram_message(message)
    if success and detection.get("id"):
        await mark_detection_notified(detection["id"])
        logger.info(f"Detection #{det_id} marked as notified")
    elif not success:
        logger.error(f"Failed to send alert for detection #{det_id}")
    return success


async def process_notification_queue():
    """Process unnotified detections and send alerts."""
    # Send CRITICAL and HIGH immediately
    critical_detections = await get_unnotified_detections("CRITICAL")
    high_detections = await get_unnotified_detections("HIGH")

    for detection in critical_detections + high_detections:
        await send_detection_alert(detection)
        await asyncio.sleep(0.5)

    # Send MEDIUM individually (they passed the quality filter)
    medium_detections = await get_unnotified_detections("MEDIUM")
    for detection in medium_detections:
        await send_detection_alert(detection)
        await asyncio.sleep(0.5)

    # LOW priority: only batch-summarize if 3+ items, otherwise silently mark notified
    low_detections = await get_unnotified_detections("LOW")
    if low_detections:
        if len(low_detections) >= 3:
            summary = _create_batch_summary(low_detections)
            success = await send_telegram_message(summary)
            if success:
                for detection in low_detections:
                    if detection.get("id"):
                        await mark_detection_notified(detection["id"])
        else:
            # Silently mark LOW detections as notified without sending
            for detection in low_detections:
                if detection.get("id"):
                    await mark_detection_notified(detection["id"])
                    logger.info(f"Silently marked LOW detection #{detection['id']} as notified (not worth sending)")

    total = len(critical_detections) + len(high_detections) + len(medium_detections) + len(low_detections)
    if total > 0:
        logger.info(f"Processed {total} notifications ({len(critical_detections)} critical, {len(high_detections)} high, {len(medium_detections)} medium, {len(low_detections)} low)")
    return total


def _create_batch_summary(detections: list) -> str:
    """Create a batched summary message for multiple low-priority updates (HTML format)."""
    message = "\U0001f4cb <b>MANUS UPDATE BATCH SUMMARY</b>\n\n"
    message += f"<i>{len(detections)} updates detected:</i>\n\n"

    for i, det in enumerate(detections[:10], 1):
        priority = det.get("priority", "LOW")
        title = _escape_html(det.get("title", "Unknown")[:100])
        source = _escape_html(det.get("source_name", "Unknown"))
        message += f"{i}. [{priority}] {title}\n   <i>Source: {source}</i>\n\n"

    if len(detections) > 10:
        message += f"<i>... and {len(detections) - 10} more updates</i>\n"

    return message


async def send_test_notification() -> bool:
    """Send a test notification to verify Telegram setup."""
    message = (
        "\U0001f9ea <b>MANUS ULTRA HUNTER TEST</b>\n\n"
        "This is a test notification.\n"
        "Your Telegram integration is working correctly!\n\n"
        f"<i>Sent at: {_escape_html(datetime.utcnow().isoformat())}</i>"
    )
    return await send_telegram_message(message)
