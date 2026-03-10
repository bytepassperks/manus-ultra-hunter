"""Advanced diff engine for detecting changes between content snapshots."""
import json
from typing import Optional
from Levenshtein import distance as levenshtein_distance

from app.utils.hashing import compute_hash, compute_dom_hash
from app.utils.text_cleaner import extract_keywords, extract_credit_info
from app.utils.logger import logger


class DiffResult:
    """Represents the result of a diff operation."""

    def __init__(self):
        self.new_items: list[dict] = []
        self.removed_items: list[dict] = []
        self.changed_items: list[dict] = []
        self.text_changes: list[dict] = []
        self.has_changes: bool = False
        self.change_severity: str = "LOW"
        self.summary: str = ""

    def to_dict(self) -> dict:
        return {
            "new_items": self.new_items,
            "removed_items": self.removed_items,
            "changed_items": self.changed_items,
            "text_changes": self.text_changes,
            "has_changes": self.has_changes,
            "change_severity": self.change_severity,
            "summary": self.summary,
        }


def compute_content_diff(old_content: Optional[str], new_content: str,
                         old_items_json: Optional[str] = None,
                         new_items: Optional[list] = None) -> DiffResult:
    """Compare old and new content, returning structured diff results."""
    result = DiffResult()

    if old_content is None:
        # First scan: establish baseline, do NOT treat everything as new
        # This prevents spamming notifications with every element on the page
        result.has_changes = False
        result.change_severity = "LOW"
        result.summary = "First scan - baseline established (no notifications)"
        return result

    old_hash = compute_dom_hash(old_content)
    new_hash = compute_dom_hash(new_content)

    if old_hash == new_hash:
        result.has_changes = False
        result.summary = "No changes detected"
        return result

    result.has_changes = True

    # Field-level diffing for structured items
    if old_items_json and new_items:
        try:
            old_items = json.loads(old_items_json) if isinstance(old_items_json, str) else old_items_json
        except json.JSONDecodeError:
            old_items = []

        result = _diff_items(old_items, new_items, result)

    # Text-level changes
    text_changes = _diff_text(old_content, new_content)
    if text_changes:
        result.text_changes = text_changes

    # Determine severity
    result.change_severity = _calculate_severity(result)
    result.summary = _generate_summary(result)

    return result


def _diff_items(old_items: list, new_items: list, result: DiffResult) -> DiffResult:
    """Diff structured items (event cards, etc.)."""
    old_titles = {item.get("title", ""): item for item in old_items}
    new_titles = {item.get("title", ""): item for item in new_items}

    # Find new items
    for title, item in new_titles.items():
        if title not in old_titles:
            result.new_items.append(item)
        else:
            # Check if existing item changed
            old_item = old_titles[title]
            if _item_changed(old_item, item):
                result.changed_items.append({
                    "old": old_item,
                    "new": item,
                    "title": title
                })

    # Find removed items
    for title, item in old_titles.items():
        if title not in new_titles:
            result.removed_items.append(item)

    return result


def _item_changed(old_item: dict, new_item: dict) -> bool:
    """Check if an item has meaningfully changed."""
    old_text = old_item.get("text", "")
    new_text = new_item.get("text", "")

    if not old_text or not new_text:
        return False

    dist = levenshtein_distance(old_text[:500], new_text[:500])
    max_len = max(len(old_text[:500]), len(new_text[:500]), 1)
    similarity = 1 - (dist / max_len)

    return similarity < 0.95


def _diff_text(old_text: str, new_text: str) -> list[dict]:
    """Find significant text changes between two content versions."""
    changes = []

    old_lines = set(old_text.split("\n"))
    new_lines = set(new_text.split("\n"))

    added_lines = new_lines - old_lines
    removed_lines = old_lines - new_lines

    # Filter to only significant lines
    important_keywords = [
        "credit", "pro access", "event", "campaign", "challenge",
        "registration", "limited", "free", "launch", "workshop",
        "hackathon", "deadline", "expires", "slots"
    ]

    for line in added_lines:
        line_lower = line.lower().strip()
        if len(line_lower) > 10:
            is_important = any(kw in line_lower for kw in important_keywords)
            if is_important:
                changes.append({
                    "type": "added",
                    "text": line.strip()[:300],
                    "important": True,
                    "keywords": extract_keywords(line)
                })
            elif len(line_lower) > 30:
                changes.append({
                    "type": "added",
                    "text": line.strip()[:300],
                    "important": False,
                    "keywords": extract_keywords(line)
                })

    for line in removed_lines:
        line_lower = line.lower().strip()
        if len(line_lower) > 10:
            is_important = any(kw in line_lower for kw in important_keywords)
            if is_important:
                changes.append({
                    "type": "removed",
                    "text": line.strip()[:300],
                    "important": True,
                    "keywords": extract_keywords(line)
                })

    return changes[:20]


def _calculate_severity(result: DiffResult) -> str:
    """Calculate the overall severity of detected changes."""
    if result.new_items:
        for item in result.new_items:
            text = item.get("text", "").lower()
            credits = extract_credit_info(text)
            if credits or "event" in text or "campaign" in text:
                return "CRITICAL"
        return "HIGH"

    if result.changed_items:
        for change in result.changed_items:
            new_text = change.get("new", {}).get("text", "").lower()
            credits = extract_credit_info(new_text)
            if credits:
                return "HIGH"
        return "MEDIUM"

    important_text_changes = [c for c in result.text_changes if c.get("important")]
    if important_text_changes:
        return "HIGH"

    if result.text_changes:
        return "MEDIUM"

    if result.removed_items:
        return "MEDIUM"

    return "LOW"


def _generate_summary(result: DiffResult) -> str:
    """Generate a human-readable summary of changes."""
    parts = []

    if result.new_items:
        parts.append(f"{len(result.new_items)} new item(s) detected")
    if result.removed_items:
        parts.append(f"{len(result.removed_items)} item(s) removed")
    if result.changed_items:
        parts.append(f"{len(result.changed_items)} item(s) changed")
    if result.text_changes:
        important = sum(1 for c in result.text_changes if c.get("important"))
        if important:
            parts.append(f"{important} important text change(s)")
        minor = len(result.text_changes) - important
        if minor:
            parts.append(f"{minor} minor text change(s)")

    return "; ".join(parts) if parts else "Changes detected"
