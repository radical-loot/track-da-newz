"""
collectors/google_news_rss.py — Google News RSS feeds

Free, no API key, no rate limits.
Builds one RSS URL per (trans_term × violence_term) combination (~340 queries).
Each feed returns up to ~100 recent results.

Good for:
  - Ongoing daily monitoring
  - Catching articles that GDELT might have missed
"""

import logging
from itertools import product

import feedparser

from config import HTTP_USER_AGENT, TRANS_TERMS, VIOLENCE_TERMS

log = logging.getLogger(__name__)

_RSS_BASE = (
    "https://news.google.com/rss/search"
    "?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
)


def _build_rss_url(trans_term: str, violence_term: str) -> tuple[str, str]:
    # No "india" in the query — the RSS URL already uses gl=IN (geo: India)
    # and ceid=IN:en (content: India, English). Appending "india" would exclude
    # the many Indian articles that don't name their own country.
    query = f'"{trans_term}" "{violence_term}"'
    url   = _RSS_BASE.format(query=query.replace(" ", "+"))
    return query, url


def _parse_entry(entry, query: str) -> dict:
    return {
        "url":              entry.get("link", ""),
        "title":            entry.get("title"),
        "published_date":   (entry.get("published") or "")[:10],
        "source_name":      (entry.get("source") or {}).get("title"),
        "source_domain":    None,
        "discovery_source": f"google_news_rss:{query}",
        "excerpt":          entry.get("summary"),
    }


def collect() -> list[dict]:
    """
    Fetch Google News RSS for all (trans × violence) query combinations.
    Returns a flat list of article candidates.
    """
    combinations = list(product(TRANS_TERMS, VIOLENCE_TERMS))
    log.info("Google News RSS: %d query combinations", len(combinations))

    candidates = []
    for trans_term, violence_term in combinations:
        query, url = _build_rss_url(trans_term, violence_term)
        feed = feedparser.parse(url, request_headers={"User-Agent": HTTP_USER_AGENT})
        for entry in feed.entries:
            candidates.append(_parse_entry(entry, query))

    log.info("Google News RSS: %d raw candidates", len(candidates))
    return candidates
