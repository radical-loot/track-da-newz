"""
collectors/gdelt_api.py — GDELT DOC Full Text Search API

Free, no API key required. Covers the full GDELT 2.0 archive (Feb 2015 → now).
Searches article content (not just metadata) and supports country/language filters.

Strategy:
  - Build one query per TRANS_TERM (e.g. '"hijra"')
  - "india" is NOT added as a keyword — sourcecountry:IN and sourcelang:eng are
    embedded directly IN the query string (GDELT operators, not URL params —
    passing them as separate URL params is silently ignored by the API).
    Adding "india" as a keyword would exclude the majority of Indian articles
    that are written for an Indian audience and never mention the country by name.
  - Chunk the date range into GDELT_CHUNK_DAYS windows
  - Fetch up to 250 results per query × window combination
"""

import logging
import time
from datetime import datetime, timedelta

import httpx

from config import (
    GDELT_CHUNK_DAYS,
    GDELT_DOC_API_URL,
    GDELT_MAX_RECORDS,
    HTTP_TIMEOUT,
    HTTP_USER_AGENT,
    TRANS_TERMS,
)

log = logging.getLogger(__name__)

# One query per trans term — violence filtering is left to Pass 1.
# sourcecountry:IN and sourcelang:eng are GDELT in-query operators, appended
# to each query string (NOT URL params — see module docstring).
QUERIES = [f'"{term}" sourcecountry:IN sourcelang:eng' for term in TRANS_TERMS]

# GDELT enforces "1 request per 5 seconds" — we use 10s to stay safely under
# and avoid burning retry budget on a long historical run.
REQUEST_DELAY     = 10.0  # seconds between requests
RETRY_429_DELAY   = 20.0  # seconds to wait after a 429 before retrying
MAX_RETRIES       = 5     # max retries per window on 429


def _date_windows(start: datetime, end: datetime, chunk_days: int = GDELT_CHUNK_DAYS):
    """Yield (window_start, window_end) tuples covering [start, end]."""
    current = start
    while current < end:
        window_end = min(current + timedelta(days=chunk_days), end)
        yield current, window_end
        current = window_end


def _fetch_window(query: str, start: datetime, end: datetime) -> list[dict]:
    """
    Single API call for one query × one time window.
    Retries up to MAX_RETRIES times on 429 AND on transient errors (timeouts,
    DNS failures, connection resets, 5xx) — a tripped rate limit tends to
    surface as these rather than a clean 429. Returns empty list only after
    all retries are exhausted.
    """
    params = {
        "query":         query,
        "mode":          "artlist",
        "maxrecords":    GDELT_MAX_RECORDS,
        "startdatetime": start.strftime("%Y%m%d%H%M%S"),
        "enddatetime":   end.strftime("%Y%m%d%H%M%S"),
        "format":        "json",
    }
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = httpx.get(
                GDELT_DOC_API_URL,
                params=params,
                timeout=HTTP_TIMEOUT,
                headers={"User-Agent": HTTP_USER_AGENT},
                verify=False,  # GDELT cert expires periodically; data is public/non-sensitive
            )
            if r.status_code == 429 or r.status_code >= 500:
                log.warning(
                    "GDELT %d | attempt %d/%d | waiting %.0fs | %s %s–%s",
                    r.status_code, attempt, MAX_RETRIES, RETRY_429_DELAY,
                    query, start.date(), end.date(),
                )
                time.sleep(RETRY_429_DELAY)
                continue
            r.raise_for_status()
            return r.json().get("articles", [])
        except Exception as e:
            log.warning(
                "GDELT error (attempt %d/%d) | query=%r window=%s–%s | %s",
                attempt, MAX_RETRIES, query, start.date(), end.date(), e,
            )
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_429_DELAY)
                continue

    log.error("GDELT gave up after %d retries | query=%r window=%s–%s",
              MAX_RETRIES, query, start.date(), end.date())
    return []


def _to_candidate(raw: dict, query: str) -> dict:
    return {
        "url":            raw.get("url", ""),
        "title":          raw.get("title"),
        "published_date": (raw.get("seendate") or "")[:8],  # YYYYMMDD
        "source_name":    raw.get("domain"),
        "source_domain":  raw.get("domain"),
        "discovery_source": f"gdelt_api:{query}",
        "excerpt":        None,
    }


def collect_query(query: str, start: datetime, end: datetime) -> list[dict]:
    """
    Collect all time-window results for a single query string.
    Returns a flat list of candidate dicts for that query only.
    Call this in a loop (one query at a time) so callers can save to DB
    incrementally — avoids losing hours of work if the process is interrupted.
    """
    windows = list(_date_windows(start, end))
    candidates = []
    for window_start, window_end in windows:
        articles = _fetch_window(query, window_start, window_end)
        for raw in articles:
            candidates.append(_to_candidate(raw, query))
        time.sleep(REQUEST_DELAY)
    log.info("GDELT query %s: %d raw candidates", query, len(candidates))
    return candidates


def collect(start: datetime, end: datetime) -> list[dict]:
    """
    Collect article candidates from GDELT DOC API for a date range.
    Returns a single flat list after ALL queries complete.
    Prefer calling collect_query() in a loop for incremental DB saves.
    """
    windows = list(_date_windows(start, end))
    total_requests = len(QUERIES) * len(windows)
    log.info(
        "GDELT DOC API: %d queries × %d windows = %d requests (~%.0f min at %.0fs/req)",
        len(QUERIES), len(windows), total_requests,
        total_requests * REQUEST_DELAY / 60, REQUEST_DELAY,
    )

    candidates = []
    for query in QUERIES:
        candidates.extend(collect_query(query, start, end))

    log.info("GDELT DOC API: %d raw candidates collected", len(candidates))
    return candidates
