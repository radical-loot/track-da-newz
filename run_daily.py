"""
run_daily.py — Daily collection run (collection only)

Collects new articles from all real-time sources and stores them in the DB.
Does NOT run any LLM processing — run `run_process.py` separately for that.

Sources:
  - GDELT DOC API    (last N days, free)
  - Google News RSS  (all trans × violence query combinations)
  - Direct RSS feeds (22 Indian news sites)
  - NewsData.io      (free tier: 2,000 articles/day)
  - GNews            (free tier: 100 requests/day)

Usage:
  uv run python run_daily.py
  uv run python run_daily.py --days-back 3

Schedule this daily (Windows Task Scheduler or cron).
Then run LLM processing when ready:
  uv run python run_process.py --batch-size 200
"""

import argparse
import logging
from datetime import datetime, timedelta

from collectors import gdelt_api, gnews, google_news_rss, newsdata, rss_direct
import pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Daily collection — stores candidates, no LLM"
    )
    p.add_argument(
        "--days-back", type=int, default=7,
        help="How many days back to collect from (default: 7)",
    )
    p.add_argument(
        "--extraction-batch-size", type=int, default=100,
        help="Articles to fetch full text for per run (default: 100)",
    )
    return p.parse_args()


def main():
    args  = _parse_args()
    end   = datetime.now()
    start = end - timedelta(days=args.days_back)

    log.info("Daily collection: %s → %s", start.date(), end.date())

    # ── Collect ───────────────────────────────────────────────────────────

    log.info("── Collecting: GDELT DOC API ──")
    candidates = gdelt_api.collect(start, end)

    log.info("── Collecting: Google News RSS ──")
    candidates += google_news_rss.collect()

    log.info("── Collecting: Direct RSS feeds ──")
    candidates += rss_direct.collect()

    log.info("── Collecting: NewsData.io ──")
    candidates += newsdata.collect(max_pages_per_query=1)

    log.info("── Collecting: GNews ──")
    candidates += gnews.collect()

    log.info("Total raw candidates: %d", len(candidates))

    # ── Store + extract text (no LLM) ─────────────────────────────────────

    pipeline.run_collection_pipeline(
        raw_candidates=candidates,
        extraction_batch_size=args.extraction_batch_size,
    )

    log.info("Done. Run 'uv run python run_process.py' to process with LLM.")


if __name__ == "__main__":
    main()
