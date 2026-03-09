"""AI Classifier module using Google Gemini for intelligent update classification."""
import json
from typing import Optional

from app.database import get_setting
from app.utils.logger import logger
from app.utils.text_cleaner import extract_keywords, extract_credit_info


async def classify_update(detection_data: dict) -> dict:
    """Classify a detected update using Gemini AI, with rule-based fallback."""
    gemini_key = await get_setting("gemini_api_key")

    if gemini_key:
        try:
            result = await _classify_with_gemini(detection_data, gemini_key)
            if result:
                return result
        except Exception as e:
            logger.error(f"Gemini classification failed: {e}")

    return _classify_rule_based(detection_data)


async def _classify_with_gemini(detection_data: dict, api_key: str) -> Optional[dict]:
    """Classify using Google Gemini API."""
    import httpx

    prompt = f"""You are an AI assistant that classifies updates from the Manus AI platform.

Analyze the following update and classify it:

Source: {detection_data.get('source', 'Unknown')}
Title: {detection_data.get('title', 'No title')}
Type: {detection_data.get('detection_type', 'update')}
Content: {detection_data.get('content', '')[:2000]}
Changes: {detection_data.get('changes_summary', 'N/A')}

Classify into ONE of these priority levels:
- CRITICAL: New event or campaign with credits, Pro access, or limited-time offers
- HIGH: Date changed, registration opened, new challenge, or important announcement
- MEDIUM: Blog post update, help doc update, or moderate content changes
- LOW: Minor text changes, formatting, or insignificant updates

Respond with ONLY a valid JSON object (no markdown):
{{
    "priority": "CRITICAL|HIGH|MEDIUM|LOW",
    "summary": "1-2 sentence summary of the update",
    "action": "Recommended action (e.g., join event / monitor / ignore)",
    "detected_rewards": "Any detected rewards (credits, access, etc.) or empty string"
}}"""

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}",
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.1,
                        "maxOutputTokens": 500
                    }
                }
            )
            if response.status_code == 200:
                data = response.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                text = text.strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                    text = text.rsplit("```", 1)[0] if "```" in text else text
                    text = text.strip()
                result = json.loads(text)
                if result.get("priority") in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
                    return result
                logger.warning(f"Invalid Gemini response format: {text[:200]}")
                return None
            else:
                logger.error(f"Gemini API error {response.status_code}: {response.text[:200]}")
                return None
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Gemini response: {e}")
        return None
    except Exception as e:
        logger.error(f"Gemini API exception: {e}")
        return None


def _classify_rule_based(detection_data: dict) -> dict:
    """Rule-based classification fallback."""
    content = detection_data.get("content", "").lower()
    title = detection_data.get("title", "").lower()
    detection_type = detection_data.get("detection_type", "")
    changes_summary = detection_data.get("changes_summary", "").lower()
    combined_text = f"{title} {content} {changes_summary}"

    keywords = extract_keywords(combined_text)
    credits = extract_credit_info(combined_text)

    priority = "LOW"
    summary = "Minor update detected"
    action = "Monitor"
    detected_rewards = ""

    # CRITICAL: new events/campaigns with credits
    critical_signals = ["event", "credits", "campaign", "pro access", "launch"]
    high_signals = ["registration", "challenge", "hackathon", "workshop", "deadline", "limited slots"]
    medium_signals = ["update", "announcement", "new feature", "blog"]

    has_critical = any(s in combined_text for s in critical_signals)
    has_high = any(s in combined_text for s in high_signals)
    has_medium = any(s in combined_text for s in medium_signals)

    if credits:
        detected_rewards = ", ".join(credits)

    if detection_type in ("new_item", "new_event") or "new" in changes_summary:
        if has_critical or credits:
            priority = "CRITICAL"
            summary = f"New item detected with potential rewards: {title[:100]}"
            action = "Join event / Register immediately"
        elif has_high:
            priority = "HIGH"
            summary = f"New important update: {title[:100]}"
            action = "Review and consider participating"
        else:
            priority = "MEDIUM"
            summary = f"New content detected: {title[:100]}"
            action = "Review at convenience"
    elif detection_type == "changed_item":
        if credits or has_critical:
            priority = "HIGH"
            summary = f"Important change detected in: {title[:100]}"
            action = "Review changes - may include new rewards"
        elif has_high:
            priority = "MEDIUM"
            summary = f"Content updated: {title[:100]}"
            action = "Monitor for further changes"
        else:
            priority = "LOW"
            summary = f"Minor changes in: {title[:100]}"
            action = "No action needed"
    elif detection_type == "text_change":
        if has_critical or credits:
            priority = "HIGH"
            summary = f"Significant text change with keywords: {', '.join(keywords[:3])}"
            action = "Review changes"
        elif has_high or has_medium:
            priority = "MEDIUM"
            summary = f"Text update detected: {title[:100]}"
            action = "Monitor"
        else:
            priority = "LOW"
            summary = f"Minor text change on {detection_data.get('source', 'unknown source')}"
            action = "No action needed"
    else:
        if has_critical:
            priority = "HIGH"
        elif has_high or has_medium:
            priority = "MEDIUM"

        summary = f"Update from {detection_data.get('source', 'unknown')}: {title[:100]}"
        action = "Review"

    return {
        "priority": priority,
        "summary": summary,
        "action": action,
        "detected_rewards": detected_rewards
    }
