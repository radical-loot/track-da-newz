"""
collectors/rss_direct.py — Direct RSS feeds from Indian English news sites

No API key. No rate limits. Covers 22 Indian news sources.
Returns all recent articles from each feed — Pass 1 does the relevance filtering.
"""

import logging

import feedparser

from config import HTTP_USER_AGENT, INDIAN_NEWS_RSS_FEEDS

log = logging.getLogger(__name__)


def _fetch_feed(name: str, url: str) -> list[dict]:
    feed = feedparser.parse(url, request_headers={"User-Agent": HTTP_USER_AGENT})
    candidates = []
    for entry in feed.entries:
        candidates.append({
            "url":              entry.get("link", ""),
            "title":            entry.get("title"),
            "published_date":   (entry.get("published") or "")[:10],
            "source_name":      name,
            "source_domain":    None,
            "discovery_source": f"rss_direct:{name}",
            "excerpt":          entry.get("summary"),
        })
    return candidates


def collect() -> list[dict]:
    """Fetch all configured Indian news RSS feeds and return a flat candidate list."""
    candidates = []
    for name, url in INDIAN_NEWS_RSS_FEEDS.items():
        items = _fetch_feed(name, url)
        log.debug("  %s: %d entries", name, len(items))
        candidates.extend(items)

    log.info(
        "Direct RSS: %d raw candidates from %d feeds",
        len(candidates), len(INDIAN_NEWS_RSS_FEEDS),
    )
    return candidates
