"""Hashing utilities for content comparison."""
import hashlib


def compute_hash(content: str) -> str:
    """Compute SHA256 hash of content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def compute_dom_hash(html: str) -> str:
    """Compute hash of HTML content, ignoring whitespace variations."""
    normalized = " ".join(html.split())
    return compute_hash(normalized)
