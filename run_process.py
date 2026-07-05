"""
run_process.py — LLM processing (separate from collection)

Reads articles from the DB that need LLM validation and processes them
in configurable batches. Safe to run multiple times — already-processed
articles are skipped automatically (tracked in pass1_results / pass2_results).

Pass 1: DeepSeek V4 Flash — binary YES/NO relevance filter
  Reads : articles where extraction_status = 'done' and no pass1_results row
  Writes: pass1_results (result = 'YES' | 'NO' | 'ERROR')

Pass 2: GPT-5.4 Nano — structured incident extraction
  Reads : articles where pass1_results.result = 'YES' and no pass2_results row
  Writes: pass2_results (violence_type, state, city, date, outcome, summary, …)

Usage:
  # Process everything pending
  uv run python run_process.py

  # Process 6 batches of 600 articles per pass
  uv run python run_process.py --batch-size 600 --num-batches 6

  # Run only Pass 1 (useful when starting out, before running Pass 2)
  uv run python run_process.py --only-pass1 --batch-size 600 --num-batches 6

  # Run only Pass 2 (after Pass 1 is done, or to resume a failed Pass 2 run)
  uv run python run_process.py --only-pass2 --batch-size 200

  # Then export to JSON when ready
  uv run python run_export.py
"""

import argparse
import asyncio
import logging

import pipeline
from processors import extractor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="LLM processing — Pass 1 (filter) + Pass 2 (extraction)"
    )
    p.add_argument(
        "--batch-size", type=int, default=100,
        help=(
            "Articles per LLM batch (default: 100). "
            "Example: --batch-size 600 --num-batches 6 processes 3,600 articles per pass."
        ),
    )
    p.add_argument(
        "--num-batches", type=int, default=None,
        help=(
            "Max batches to run per pass (default: run until all pending are done). "
            "Use this to process in chunks and resume later."
        ),
    )
    p.add_argument(
        "--only-pass1", action="store_true",
        help="Run Pass 1 only (binary filter). Skip Pass 2.",
    )
    p.add_argument(
        "--only-pass2", action="store_true",
        help="Run Pass 2 only (structured extraction). Skip Pass 1.",
    )
    p.add_argument(
        "--extract", type=int, default=0, metavar="N",
        help=(
            "Fetch full text for N pending articles before running LLM passes. "
            "Example: --extract 2000 ensures articles have text ready for Pass 1."
        ),
    )
    return p.parse_args()


async def main():
    args = _parse_args()

    if args.only_pass1 and args.only_pass2:
        log.error("--only-pass1 and --only-pass2 are mutually exclusive.")
        return

    log.info(
        "Processing | extract=%d | batch_size=%d | num_batches=%s | pass1=%s | pass2=%s",
        args.extract,
        args.batch_size,
        args.num_batches or "all",
        "skip" if args.only_pass2 else "run",
        "skip" if args.only_pass1 else "run",
    )

    if args.extract:
        log.info("── Step 0: Extracting full text for up to %d articles ──", args.extract)
        extractor.run(batch_size=args.extract)

    await pipeline.run_processing_pipeline(
        llm_batch_size=args.batch_size,
        llm_num_batches=args.num_batches,
        only_pass1=args.only_pass1,
        only_pass2=args.only_pass2,
    )


if __name__ == "__main__":
    asyncio.run(main())
