"""
pipeline.py — Two independent pipelines: collection and processing

COLLECTION PIPELINE  (run_historical.py / run_daily.py)
  Step 1: collect_and_store  — deduplicate + insert candidates into DB
  Step 2: extract_text       — fetch full article text for every stored URL

PROCESSING PIPELINE  (run_process.py)
  Step 3: filter_pass1       — DeepSeek V4 Flash binary YES/NO
  Step 4: extract_pass2      — GPT-5.4 Nano structured extraction (YES-only)

EXPORT  (run_export.py)
  Step 5: export_to_json     — write docs/data/ JSON files for GitHub Pages

Keeping collection and processing separate means:
  - You can collect daily without triggering LLM costs
  - You can run LLM processing on your own schedule with full batch control
  - Re-running collection never re-processes already-validated articles
    (the DB tracks status for every article at every stage)
"""

import asyncio
import logging

import db
import export
from processors import deduplicator, extractor, pass1_filter, pass2_extract

log = logging.getLogger(__name__)


# ── Shared step (used by both pipelines) ──────────────────────────────────────

def collect_and_store(raw_candidates: list[dict]) -> int:
    """
    Step 1: Deduplicate raw candidates from all collectors,
    then insert genuinely new ones into the DB.
    Returns the count of newly inserted articles.
    Already-seen URLs are silently skipped — safe to call repeatedly.
    """
    seen_urls: set[str] = set()
    new_candidates = deduplicator.filter_new(raw_candidates, seen_urls)
    inserted = db.insert_candidates(new_candidates)
    log.info(
        "Stored %d new articles  |  %d collected  |  %d duplicates dropped",
        inserted, len(raw_candidates), len(raw_candidates) - len(new_candidates),
    )
    return inserted


# ── Collection pipeline ────────────────────────────────────────────────────────

def run_collection_pipeline(raw_candidates: list[dict], extraction_batch_size: int = 100):
    """
    Steps 1–2: Store candidates and fetch their full text.
    No LLM calls. Safe to run as often as you collect.

    Args:
        raw_candidates        : Flat list of dicts from one or more collectors.
        extraction_batch_size : How many articles to fetch text for in one run.
    """
    db.init_db()

    log.info("═══ Collection pipeline start | %d raw candidates ═══", len(raw_candidates))

    log.info("── Step 1: Storing candidates ────────────────────────────────")
    collect_and_store(raw_candidates)

    log.info("── Step 2: Extracting full text ──────────────────────────────")
    extractor.run(batch_size=extraction_batch_size)

    log.info("═══ Collection done | DB stats: %s ═══", db.stats())


# ── Processing pipeline ────────────────────────────────────────────────────────

async def run_processing_pipeline(
    llm_batch_size: int = 100,
    llm_num_batches: int | None = None,
    only_pass1: bool = False,
    only_pass2: bool = False,
):
    """
    Steps 3–4: Run LLM passes on collected articles.
    Reads from DB — does not re-collect anything.

    Args:
        llm_batch_size  : Articles per batch for both LLM passes. Example: 600
        llm_num_batches : Max batches to run per pass. Example: 6
                          None = run until all pending articles are processed.
                          Example: llm_batch_size=600, llm_num_batches=6
                          → processes up to 3,600 articles per pass per run.
        only_pass1      : Run Pass 1 only (skip Pass 2).
        only_pass2      : Run Pass 2 only (skip Pass 1 — for resuming after failures).
    """
    db.init_db()

    log.info(
        "═══ Processing pipeline start | batch_size=%d num_batches=%s ═══",
        llm_batch_size, llm_num_batches,
    )

    if not only_pass2:
        log.info("── Step 3: Pass 1 — Binary filter (DeepSeek V4 Flash) ────────")
        await pass1_filter.run(batch_size=llm_batch_size, num_batches=llm_num_batches)

    if not only_pass1:
        log.info("── Step 4: Pass 2 — Structured extraction (GPT-5.4 Nano) ─────")
        await pass2_extract.run(batch_size=llm_batch_size, num_batches=llm_num_batches)

    log.info("═══ Processing done | DB stats: %s ═══", db.stats())


# ── Export ────────────────────────────────────────────────────────────────────

def run_export():
    """Step 5: Write validated articles to docs/data/ for GitHub Pages."""
    db.init_db()
    log.info("── Exporting to JSON ─────────────────────────────────────────")
    export.run()
