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


async def send_telegram_message(text: str, parse_mode: str = "Markdown") -> bool:
    """Send a message via Telegram bot."""
    bot_token, chat_id = await get_telegram_config()
    if not bot_token or not chat_id:
        logger.warning("Telegram not configured - skipping notification")
        return False

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{TELEGRAM_API_BASE}{bot_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                    "disable_web_page_preview": False
                }
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    logger.info(f"Telegram message sent successfully")
                    return True
                logger.error(f"Telegram API returned ok=false: {data}")
                return False
            else:
                logger.error(f"Telegram API error {response.status_code}: {response.text[:200]}")
                return False
    except Exception as e:
        logger.error(f"Telegram send exception: {e}")
        return False


def format_alert_message(detection: dict) -> str:
    """Format a detection into a Telegram alert message."""
    priority = detection.get("priority", "LOW")

    priority_emoji = {
        "CRITICAL": "\U0001f6a8",
        "HIGH": "\u26a0\ufe0f",
        "MEDIUM": "\U0001f4cb",
        "LOW": "\U0001f4ac"
    }

    emoji = priority_emoji.get(priority, "\U0001f4ac")

    title = detection.get("title", "Unknown")
    det_type = detection.get("detection_type", "update")
    url = detection.get("url", "")
    summary = detection.get("summary", "No summary available")
    rewards = detection.get("detected_rewards", "")
    action = detection.get("action", "Monitor")
    source = detection.get("source_name", detection.get("source", "Unknown"))
    timestamp = detection.get("created_at", datetime.utcnow().isoformat())

    # Escape markdown special characters
    title = _escape_md(title[:200])
    summary = _escape_md(summary[:500])
    rewards = _escape_md(rewards) if rewards else "None detected"
    action = _escape_md(action)
    source = _escape_md(source)

    message = (
        f"{emoji} *{priority} MANUS UPDATE DETECTED*\n\n"
        f"*Title:* {title}\n"
        f"*Type:* {det_type}\n"
        f"*URL:* {url}\n"
        f"*Summary:* {summary}\n"
        f"*Rewards:* {rewards}\n"
        f"*Recommended Action:* {action}\n"
        f"*Source:* {source}\n"
        f"*Time:* {timestamp}"
    )
    return message


def _escape_md(text: str) -> str:
    """Escape Markdown special characters for Telegram."""
    chars_to_escape = ["_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"]
    for char in chars_to_escape:
        text = text.replace(char, f"\\{char}")
    return text


async def send_detection_alert(detection: dict) -> bool:
    """Send a single detection as a Telegram alert."""
    message = format_alert_message(detection)
    success = await send_telegram_message(message)
    if success and detection.get("id"):
        await mark_detection_notified(detection["id"])
    return success


async def process_notification_queue():
    """Process unnotified detections and send alerts."""
    # Send CRITICAL and HIGH immediately
    critical_detections = await get_unnotified_detections("CRITICAL")
    high_detections = await get_unnotified_detections("HIGH")

    for detection in critical_detections + high_detections:
        await send_detection_alert(detection)
        await asyncio.sleep(0.5)

    # Batch MEDIUM and LOW
    medium_detections = await get_unnotified_detections("MEDIUM")
    low_detections = await get_unnotified_detections("LOW")

    batch = medium_detections + low_detections
    if batch:
        if len(batch) <= 3:
            for detection in batch:
                await send_detection_alert(detection)
                await asyncio.sleep(0.5)
        else:
            summary = _create_batch_summary(batch)
            success = await send_telegram_message(summary)
            if success:
                for detection in batch:
                    if detection.get("id"):
                        await mark_detection_notified(detection["id"])

    total = len(critical_detections) + len(high_detections) + len(batch)
    if total > 0:
        logger.info(f"Processed {total} notifications ({len(critical_detections)} critical, {len(high_detections)} high, {len(batch)} other)")
    return total


def _create_batch_summary(detections: list) -> str:
    """Create a batched summary message for multiple low-priority updates."""
    message = "\U0001f4cb *MANUS UPDATE BATCH SUMMARY*\n\n"
    message += f"_{len(detections)} updates detected:_\n\n"

    for i, det in enumerate(detections[:10], 1):
        priority = det.get("priority", "LOW")
        title = _escape_md(det.get("title", "Unknown")[:100])
        source = _escape_md(det.get("source_name", "Unknown"))
        message += f"{i}\\. \\[{priority}\\] {title}\n   _Source: {source}_\n\n"

    if len(detections) > 10:
        message += f"_\\.\\.\\. and {len(detections) - 10} more updates_\n"

    return message


async def send_test_notification() -> bool:
    """Send a test notification to verify Telegram setup."""
    message = (
        "\U0001f9ea *MANUS ULTRA HUNTER TEST*\n\n"
        "This is a test notification\\.\n"
        "Your Telegram integration is working correctly\\!\n\n"
        f"_Sent at: {_escape_md(datetime.utcnow().isoformat())}_"
    )
    return await send_telegram_message(message)
