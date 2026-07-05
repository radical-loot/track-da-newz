"""
collectors/gnews.py — GNews API

Free tier: 100 requests/day, 10 articles per request.
Use conservatively — 19 trans terms × 1 request each = 19 of your 100 daily calls.
Set GNEWS_API_KEY in .env.
"""

import logging

import httpx

from config import GNEWS_API_KEY, HTTP_TIMEOUT, TRANS_TERMS

log = logging.getLogger(__name__)

_API_URL = "https://gnews.io/api/v4/search"


def _fetch(query: str) -> list[dict]:
    params = {
        "token":   GNEWS_API_KEY,
        "q":       query,
        "country": "in",
        "lang":    "en",
        "max":     10,
    }
    try:
        r = httpx.get(_API_URL, params=params, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        return r.json().get("articles", [])
    except Exception as e:
        log.warning("GNews error | query=%r | %s", query, e)
        return []


def _parse_article(item: dict, query: str) -> dict:
    return {
        "url":              item.get("url", ""),
        "title":            item.get("title"),
        "published_date":   (item.get("publishedAt") or "")[:10],
        "source_name":      (item.get("source") or {}).get("name"),
        "source_domain":    (item.get("source") or {}).get("url"),
        "discovery_source": f"gnews:{query}",
        "excerpt":          item.get("description"),
    }


def collect() -> list[dict]:
    """Search GNews for each trans term (one request per term)."""
    if not GNEWS_API_KEY:
        log.warning("GNEWS_API_KEY not set — skipping GNews")
        return []

    candidates = []
    for term in TRANS_TERMS:
        # No "india" — country=in param already restricts to Indian sources
        query    = f"{term} violence"
        articles = _fetch(query)
        for item in articles:
            candidates.append(_parse_article(item, query))

    log.info("GNews: %d raw candidates", len(candidates))
    return candidates
