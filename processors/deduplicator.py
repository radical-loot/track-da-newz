"""
processors/deduplicator.py — URL normalisation and duplicate filtering

Two levels of deduplication:
  1. URL-level: strip tracking params, normalise scheme/www/trailing slashes
  2. Content-level: SHA256 of first 1500 chars (catches cross-posted articles)

Call filter_new() before inserting candidates into the DB.
"""

import hashlib
import re
from urllib.parse import urlencode, urlparse, urlunparse, parse_qs

# Query string parameters that carry no semantic meaning for the article
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "ref", "referrer", "source", "_ga", "mc_cid", "mc_eid",
}


def normalize_url(url: str) -> str:
    """
    Strip tracking params, lowercase the host, remove www., drop fragments.
    Returns a stable canonical URL string for deduplication.
    """
    try:
        parsed     = urlparse(url.strip())
        clean_qs   = {
            k: v for k, v in parse_qs(parsed.query, keep_blank_values=False).items()
            if k.lower() not in _TRACKING_PARAMS
        }
        return urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower().removeprefix("www."),
            parsed.path.rstrip("/"),
            parsed.params,
            urlencode(clean_qs, doseq=True),
            "",   # drop fragment
        ))
    except Exception:
        return url


def content_hash(text: str) -> str:
    """SHA256 of the first 1500 characters (normalised whitespace)."""
    normalised = re.sub(r"\s+", " ", text[:1500].strip().lower())
    return hashlib.sha256(normalised.encode()).hexdigest()


def filter_new(candidates: list[dict], seen_urls: set[str]) -> list[dict]:
    """
    Return only candidates whose normalised URL is not already in seen_urls.
    Adds normalised URLs to seen_urls in place (so callers can accumulate across batches).
    Also attaches 'url_normalized' to each passing candidate dict.
    """
    new = []
    for c in candidates:
        norm = normalize_url(c.get("url", ""))
        c["url_normalized"] = norm
        if norm and norm not in seen_urls:
            seen_urls.add(norm)
            new.append(c)
    return new
