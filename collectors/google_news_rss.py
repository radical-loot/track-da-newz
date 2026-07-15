"""
collectors/google_news_rss.py — Google News RSS feeds

Free, no API key, no rate limits.
Builds one RSS URL per (trans_term × violence_term) combination (~340 queries).
Each feed returns up to ~100 recent results.

Good for:
  - Ongoing daily monitoring
  - Catching articles that GDELT might have missed

Also provides collect_term_historical() — a historical backfill mode using
Google News RSS's after:/before: date operators, paginated in monthly windows
to work around the ~100-item-per-feed cap. This is a separate index from
GDELT, so it isn't affected by GDELT's rate limiting.
"""

import logging
import time
from datetime import datetime, timedelta
from itertools import product

import feedparser

from config import HTTP_USER_AGENT, TRANS_TERMS, VIOLENCE_TERMS

log = logging.getLogger(__name__)

# Historical mode: one query per TRANS_TERM (not paired with VIOLENCE_TERMS —
# violence filtering is left to Pass 1, same strategy as gdelt_api.py) paginated
# across date windows to surface results beyond the ~100-item feed cap.
HISTORICAL_CHUNK_DAYS   = 30
HISTORICAL_REQUEST_DELAY = 2.0  # seconds between requests — separate index from GDELT

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


def _format_published(entry) -> str:
    """
    feedparser exposes a parsed struct_time in published_parsed — use it to
    build a real YYYYMMDD date. Slicing entry['published'] (an RFC822 string
    like "Wed, 31 Jul 2024 12:00:00 GMT") to [:10] truncates to garbage like
    "Wed, 31 Ju" — do not do that.
    """
    parsed = entry.get("published_parsed")
    if parsed:
        return time.strftime("%Y%m%d", parsed)
    return ""


def _parse_entry(entry, query: str) -> dict:
    return {
        "url":              entry.get("link", ""),
        "title":            entry.get("title"),
        "published_date":   _format_published(entry),
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


# ── Historical backfill (date-paginated) ───────────────────────────────────────

def _date_windows(start: datetime, end: datetime, chunk_days: int = HISTORICAL_CHUNK_DAYS):
    """Yield (window_start, window_end) tuples covering [start, end]."""
    current = start
    while current < end:
        window_end = min(current + timedelta(days=chunk_days), end)
        yield current, window_end
        current = window_end


def _build_historical_url(term: str, start: datetime, end: datetime) -> tuple[str, str]:
    query = f'"{term}" after:{start.strftime("%Y-%m-%d")} before:{end.strftime("%Y-%m-%d")}'
    url   = _RSS_BASE.format(query=query.replace(" ", "+"))
    return query, url


def collect_term_historical(
    term: str, start: datetime, end: datetime, chunk_days: int = HISTORICAL_CHUNK_DAYS,
    request_delay: float = HISTORICAL_REQUEST_DELAY,
) -> list[dict]:
    """
    Collect all date-window results for a single TRANS_TERM across [start, end].
    Call this in a loop (one term at a time) so callers can save to DB
    incrementally — mirrors gdelt_api.collect_query()'s crash-safety pattern.
    """
    windows = list(_date_windows(start, end, chunk_days))
    candidates = []
    for window_start, window_end in windows:
        query, url = _build_historical_url(term, window_start, window_end)
        try:
            feed = feedparser.parse(url, request_headers={"User-Agent": HTTP_USER_AGENT})
            for entry in feed.entries:
                candidates.append(_parse_entry(entry, query))
        except Exception as e:
            log.warning(
                "Google News RSS historical error | query=%r window=%s–%s | %s",
                query, window_start.date(), window_end.date(), e,
            )
        time.sleep(request_delay)
    log.info("Google News RSS historical %r: %d raw candidates", term, len(candidates))
    return candidates


def collect_historical(
    start: datetime, end: datetime, chunk_days: int = HISTORICAL_CHUNK_DAYS,
    request_delay: float = HISTORICAL_REQUEST_DELAY,
) -> list[dict]:
    """
    Historical backfill via Google News RSS using after:/before: date operators,
    one TRANS_TERM at a time (not paired with VIOLENCE_TERMS — violence filtering
    is left to Pass 1). Prefer calling collect_term_historical() in a loop for
    incremental DB saves on long runs.
    """
    windows = list(_date_windows(start, end, chunk_days))
    total = len(TRANS_TERMS) * len(windows)
    log.info(
        "Google News RSS historical: %d terms × %d windows = %d requests (~%.0f min at %.1fs/req)",
        len(TRANS_TERMS), len(windows), total, total * request_delay / 60, request_delay,
    )

    candidates = []
    for term in TRANS_TERMS:
        candidates.extend(collect_term_historical(term, start, end, chunk_days, request_delay))

    log.info("Google News RSS historical: %d raw candidates collected", len(candidates))
    return candidates
