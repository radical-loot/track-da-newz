"""
processors/pass1_filter.py — Pass 1: Binary relevance filter

Model : deepseek/deepseek-v4-flash (via OpenRouter)
Input : article title + first 800 chars of text/excerpt
Output: YES (relevant) or NO (irrelevant)

Batching:
  - Articles are split into batches of `batch_size`
  - Within each batch, up to PASS1_CONCURRENCY calls run concurrently
  - `num_batches` caps how many batches are processed (useful for resuming)

Cost estimate: ~$0.09 per million input tokens (DeepSeek V4 Flash)
  → 50,000 articles × 500 tokens ≈ $2.25 total
"""

import asyncio
import logging

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
from tqdm import tqdm

import db
from config import (
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    PASS1_CONCURRENCY,
    PASS1_MODEL,
)

log = logging.getLogger(__name__)

_client = AsyncOpenAI(base_url=OPENROUTER_BASE_URL, api_key=OPENROUTER_API_KEY)

_SYSTEM = "You classify Indian news articles. Answer only YES or NO — no explanation."

_PROMPT = """\
Does this article report or describe an act of physical, sexual, or deadly violence \
committed against a transgender, hijra, kinnar, aravani, thirunangai, or other \
third-gender person in India?

Title  : {title}
Excerpt: {excerpt}

Answer YES or NO only."""


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30))
async def _classify_one(article: dict, semaphore: asyncio.Semaphore) -> tuple[int, str]:
    """Classify a single article. Returns (article_id, 'YES' | 'NO' | 'ERROR')."""
    async with semaphore:
        text = (article.get("full_text") or article.get("excerpt") or "")[:800]
        prompt = _PROMPT.format(
            title=article.get("title") or "(no title)",
            excerpt=text,
        )
        try:
            resp = await _client.chat.completions.create(
                model=PASS1_MODEL,
                messages=[
                    {"role": "system",  "content": _SYSTEM},
                    {"role": "user",    "content": prompt},
                ],
                max_tokens=5,
                temperature=0,
            )
            answer = resp.choices[0].message.content.strip().upper()
            return article["id"], ("YES" if "YES" in answer else "NO")
        except Exception as e:
            log.warning("Pass 1 error for article %d: %s", article["id"], e)
            return article["id"], "ERROR"


async def _process_batch(batch: list[dict]) -> dict[int, str]:
    """Run all articles in a batch concurrently (bounded by PASS1_CONCURRENCY)."""
    semaphore = asyncio.Semaphore(PASS1_CONCURRENCY)
    pairs = await asyncio.gather(*[_classify_one(a, semaphore) for a in batch])
    return dict(pairs)


def _chunk(lst: list, size: int) -> list[list]:
    return [lst[i : i + size] for i in range(0, len(lst), size)]


async def run(batch_size: int = 100, num_batches: int | None = None):
    """
    Run Pass 1 on all articles pending validation.

    Args:
        batch_size  : Articles per batch.  Example: 600
        num_batches : Max batches to run.  Example: 6  (None = run all pending)

    Example — run 6 batches of 600 (= 3,600 articles):
        await pass1_filter.run(batch_size=600, num_batches=6)
    """
    pending = db.get_pending_pass1()
    batches = _chunk(pending, batch_size)
    if num_batches is not None:
        batches = batches[:num_batches]

    total = sum(len(b) for b in batches)
    log.info(
        "Pass 1 | %d batch(es) × up to %d articles = %d total | model: %s",
        len(batches), batch_size, total, PASS1_MODEL,
    )

    yes_total = 0
    for i, batch in enumerate(tqdm(batches, desc="Pass 1 batches"), start=1):
        results = await _process_batch(batch)

        for article_id, result in results.items():
            db.save_pass1_result(article_id, result, PASS1_MODEL)

        yes_count = sum(1 for r in results.values() if r == "YES")
        yes_total += yes_count
        log.info(
            "  Batch %d/%d → %d YES / %d total",
            i, len(batches), yes_count, len(batch),
        )

    log.info("Pass 1 complete | %d relevant out of %d processed", yes_total, total)
