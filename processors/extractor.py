"""
processors/extractor.py — Full article text extraction

Uses trafilatura to fetch and extract clean article text from URLs.
Detects paywalled articles so they are flagged but not discarded
(title + excerpt are still useful for Pass 1).

Run after collection, before LLM passes.
"""

import logging

import trafilatura

import db
from config import HTTP_USER_AGENT

log = logging.getLogger(__name__)

# Phrases that indicate a paywall rather than actual article content
_PAYWALL_SIGNALS = [
    "subscribe to read",
    "subscribers only",
    "sign in to read",
    "create an account",
    "premium content",
    "subscribe now to continue",
    "this article is for subscribers",
    "to continue reading",
]

_TRAFILATURA_CONFIG = trafilatura.settings.use_config()
_TRAFILATURA_CONFIG.set("DEFAULT", "TIMEOUT", "30")
_TRAFILATURA_CONFIG.set("DEFAULT", "USER_AGENT", HTTP_USER_AGENT)


def _is_paywalled(raw_html: str | None, extracted_text: str | None) -> bool:
    for source in (raw_html or "")[:3000], (extracted_text or ""):
        if any(signal in source.lower() for signal in _PAYWALL_SIGNALS):
            return True
    return False


def _fetch_and_extract(url: str) -> tuple[str | None, bool]:
    """
    Download and extract the article at url.
    Returns (text, is_paywalled). Returns (None, False) on network/parse failure.
    """
    try:
        raw_html = trafilatura.fetch_url(url, config=_TRAFILATURA_CONFIG)
        if not raw_html:
            return None, False

        text = trafilatura.extract(
            raw_html,
            config=_TRAFILATURA_CONFIG,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
        )

        paywalled = _is_paywalled(raw_html, text)
        return text, paywalled

    except Exception as e:
        log.debug("Extraction failed for %s: %s", url, e)
        return None, False


def run(batch_size: int = 100):
    """
    Fetch and extract full text for all articles pending extraction.
    Processes up to batch_size articles per call.
    """
    from tqdm import tqdm

    pending = db.get_pending_extraction(limit=batch_size)
    if not pending:
        log.info("Extractor: nothing pending")
        return

    log.info("Extractor: %d articles to process", len(pending))

    success = failed = paywalled = 0
    for article in tqdm(pending, desc="Extracting text"):
        text, is_pw = _fetch_and_extract(article["url"])
        if text:
            db.save_extracted_text(article["id"], text, is_pw)
            success += 1
            if is_pw:
                paywalled += 1
        else:
            db.mark_extraction_failed(article["id"])
            failed += 1

    log.info(
        "Extractor done: %d extracted (%d paywalled), %d failed",
        success, paywalled, failed,
    )
