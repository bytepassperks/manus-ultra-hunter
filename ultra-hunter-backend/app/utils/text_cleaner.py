"""Text cleaning utilities for scraped content."""
import re


def clean_html_text(text: str) -> str:
    """Remove HTML tags and normalize whitespace."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_keywords(text: str) -> list[str]:
    """Extract relevant keywords from text."""
    keywords = [
        "event", "credits", "pro access", "launch", "workshop",
        "hackathon", "challenge", "campaign", "registration",
        "limited slots", "free", "bonus", "invite", "beta",
        "new feature", "update", "announcement", "live",
        "deadline", "expires", "open now", "sign up"
    ]
    text_lower = text.lower()
    return [kw for kw in keywords if kw in text_lower]


def extract_dates(text: str) -> list[str]:
    """Extract date-like patterns from text."""
    patterns = [
        r"\d{4}-\d{2}-\d{2}",
        r"\d{1,2}/\d{1,2}/\d{2,4}",
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s*\d{2,4}",
        r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{2,4}",
    ]
    dates = []
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        dates.extend(matches)
    return dates


def extract_credit_info(text: str) -> list[str]:
    """Extract credit/reward information from text."""
    patterns = [
        r"\d+\s*credits?",
        r"\$\d+[\d,.]*",
        r"pro\s+access",
        r"free\s+(?:tier|plan|credits?|access)",
        r"\d+\s*(?:day|week|month|year)s?\s+(?:free|trial)",
    ]
    rewards = []
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        rewards.extend(matches)
    return rewards
