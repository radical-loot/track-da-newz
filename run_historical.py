"""
run_historical.py — One-time historical backfill (collection only)

Collects articles from 2019-01-01 → today and stores them in the DB.
Does NOT run any LLM processing — run `run_process.py` separately for that.

Crash-safe: GDELT results are saved to DB after each query term completes,
not after all 19 finish. If the process is killed, previously completed
queries are not re-fetched (INSERT OR IGNORE skips known URLs).

Sources:
  - GDELT DOC API     (free, full archive back to 2015)
  - GDELT BigQuery    (deeper historical sweep — needs Google Cloud auth)
  - Google News RSS   (catches recent articles GDELT may have missed)
  - Direct RSS feeds  (Indian news sites, no auth)

Usage:
  uv run python run_historical.py
  uv run python run_historical.py --from 2022-01-01
  uv run python run_historical.py --skip-bigquery        # if Google Cloud not set up yet
  uv run python run_historical.py --from 2019-01-01 --to 2021-12-31  # date range

Then, separately:
  uv run python run_process.py --batch-size 600 --num-batches 6

BigQuery one-time setup:
  gcloud auth application-default login
"""

import argparse
import logging
from datetime import datetime

import db
from collectors import gdelt_api, gdelt_bigquery, google_news_rss
from collectors import rss_direct
from config import GDELT_CHUNK_DAYS
from processors import extractor, deduplicator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Historical backfill — collects and stores candidates, no LLM"
    )
    p.add_argument(
        "--from", dest="start_date", default="2019-01-01",
        metavar="YYYY-MM-DD", help="Start date (default: 2019-01-01)",
    )
    p.add_argument(
        "--to", dest="end_date", default=None,
        metavar="YYYY-MM-DD", help="End date (default: today)",
    )
    p.add_argument(
        "--extraction-batch-size", type=int, default=100,
        help="Articles to fetch full text for per run (default: 100)",
    )
    p.add_argument(
        "--skip-bigquery", action="store_true",
        help="Skip GDELT BigQuery (use if Google Cloud auth not yet configured)",
    )
    p.add_argument(
        "--skip-rss", action="store_true",
        help="Skip all RSS collection (GDELT only)",
    )
    p.add_argument(
        "--skip-extraction", action="store_true",
        help="Skip text extraction — just collect URLs into DB",
    )
    p.add_argument(
        "--start-query", type=int, default=1, metavar="N",
        help="Start GDELT collection at query N (1-based). Use to resume after interruption. "
             "Example: --start-query 3 skips 'transgender' and 'trans woman'.",
    )
    return p.parse_args()


def _store(candidates: list[dict]) -> int:
    """Deduplicate and insert candidates into the DB. Returns count inserted."""
    seen: set[str] = set()
    new = deduplicator.filter_new(candidates, seen)
    inserted = db.insert_candidates(new)
    log.info(
        "Stored %d new  |  %d collected  |  %d duplicates dropped",
        inserted, len(candidates), len(candidates) - len(new),
    )
    return inserted


def main():
    args  = _parse_args()
    start = datetime.strptime(args.start_date, "%Y-%m-%d")
    end   = datetime.strptime(args.end_date, "%Y-%m-%d") if args.end_date else datetime.now()

    log.info("Historical backfill: %s → %s", start.date(), end.date())

    # Init DB first — so we can save incrementally and survive kills
    db.init_db()

    # ── GDELT DOC API — saved per query term ──────────────────────────────
    # Each of the 19 trans-term queries is collected and saved individually.
    # If this process is killed, completed queries are already in the DB and
    # won't be re-inserted (INSERT OR IGNORE on the unique URL column).

    log.info("── Collecting: GDELT DOC API ──")
    windows = list(gdelt_api._date_windows(start, end))
    total_requests = len(gdelt_api.QUERIES) * len(windows)
    log.info(
        "GDELT DOC API: %d queries × %d windows = %d requests (~%.0f min at %.0fs/req)",
        len(gdelt_api.QUERIES), len(windows), total_requests,
        total_requests * gdelt_api.REQUEST_DELAY / 60, gdelt_api.REQUEST_DELAY,
    )

    start_idx = args.start_query - 1  # convert to 0-based
    if start_idx > 0:
        log.info("Resuming from query %d — skipping first %d queries", args.start_query, start_idx)

    for i, query in enumerate(gdelt_api.QUERIES, 1):
        if i < args.start_query:
            log.info("[%d/%d] Skipping (already collected): %s", i, len(gdelt_api.QUERIES), query)
            continue
        log.info("[%d/%d] GDELT query: %s", i, len(gdelt_api.QUERIES), query)
        candidates = gdelt_api.collect_query(query, start, end)
        _store(candidates)

    log.info("GDELT DOC API complete. DB stats so far: %s", db.stats())

    # ── GDELT BigQuery ────────────────────────────────────────────────────

    if not args.skip_bigquery:
        log.info("── Collecting: GDELT BigQuery ──")
        candidates = gdelt_bigquery.collect(start, end)
        _store(candidates)
    else:
        log.info("── Skipping GDELT BigQuery (--skip-bigquery) ──")

    # ── RSS feeds ─────────────────────────────────────────────────────────

    if not args.skip_rss:
        log.info("── Collecting: Google News RSS ──")
        candidates = google_news_rss.collect()
        _store(candidates)

        log.info("── Collecting: Direct RSS feeds ──")
        candidates = rss_direct.collect()
        _store(candidates)
    else:
        log.info("── Skipping RSS collection (--skip-rss) ──")

    # ── Text extraction ───────────────────────────────────────────────────

    if not args.skip_extraction:
        log.info("── Extracting full text ──")
        extractor.run(batch_size=args.extraction_batch_size)
    else:
        log.info("── Skipping text extraction (--skip-extraction) ──")

    log.info("Done. Final DB stats: %s", db.stats())
    log.info("Next: uv run python run_process.py --batch-size 600 --num-batches 6")


if __name__ == "__main__":
    main()
