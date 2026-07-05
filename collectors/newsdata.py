"""
collectors/newsdata.py — NewsData.io API

Free tier: 200 credits/day (each credit = 10 articles → 2,000 articles/day).
Good India coverage with state-level filtering.
Set NEWSDATA_API_KEY in .env.
"""

import logging

import httpx

from config import HTTP_TIMEOUT, NEWSDATA_API_KEY, TRANS_TERMS

log = logging.getLogger(__name__)

_API_URL = "https://newsdata.io/api/1/news"


def _fetch_page(query: str, page_token: str | None = None) -> dict:
    params = {
        "apikey":   NEWSDATA_API_KEY,
        "q":        query,
        "country":  "in",
        "language": "en",
    }
    if page_token:
        params["page"] = page_token

    try:
        r = httpx.get(_API_URL, params=params, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning("NewsData.io error | query=%r | %s", query, e)
        return {}


def _parse_item(item: dict, query: str) -> dict:
    return {
        "url":              item.get("link", ""),
        "title":            item.get("title"),
        "published_date":   (item.get("pubDate") or "")[:10],
        "source_name":      item.get("source_id"),
        "source_domain":    item.get("source_url"),
        "discovery_source": f"newsdata:{query}",
        "excerpt":          item.get("description"),
    }


def collect(max_pages_per_query: int = 3) -> list[dict]:
    """
    Search NewsData.io for each trans term.
    Paginates up to max_pages_per_query per term.

    Keep max_pages_per_query low on free tier to preserve daily credits.
    """
    if not NEWSDATA_API_KEY:
        log.warning("NEWSDATA_API_KEY not set — skipping NewsData.io")
        return []

    candidates = []
    for term in TRANS_TERMS:
        # No "india" — country=in param already restricts to Indian sources
        query      = f"{term} violence"
        page_token = None

        for _ in range(max_pages_per_query):
            data    = _fetch_page(query, page_token)
            results = data.get("results", [])
            for item in results:
                candidates.append(_parse_item(item, query))

            page_token = data.get("nextPage")
            if not page_token:
                break

    log.info("NewsData.io: %d raw candidates", len(candidates))
    return candidates
