"""
processors/pass2_extract.py — Pass 2: Structured incident extraction

Model : openai/gpt-5.4-nano (via OpenRouter)
Input : full article text (first 3,000 chars)
Output: JSON with violence_type, location, date, perpetrator, outcome, summary

Only runs on articles that passed Pass 1 (result = 'YES').

Batching: same pattern as pass1_filter — batch_size × num_batches.

Cost estimate: ~$0.20/M input + $1.25/M output (GPT-5.4 Nano)
  → 10,000 articles × 1,500 tokens input + 300 tokens output ≈ $6.75 total
"""

import asyncio
import json
import logging

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
from tqdm import tqdm

import db
from config import (
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    PASS2_CONCURRENCY,
    PASS2_MODEL,
)

log = logging.getLogger(__name__)

_client = AsyncOpenAI(base_url=OPENROUTER_BASE_URL, api_key=OPENROUTER_API_KEY)

_SYSTEM = "You extract structured information from news articles. Return only valid JSON."

_PROMPT = """\
Extract incident details from this Indian news article about violence in which \
the VICTIM is a transgender/hijra/kinnar/third-gender person.

Important: only describe violence committed AGAINST the trans/third-gender \
person. If the article does not report such an incident (e.g. the trans person \
is the perpetrator, or the piece is opinion/biography/legal analysis with no \
specific incident), set every field to null except "summary", and set \
"summary" to exactly "NOT_A_VICTIM_INCIDENT".

Article:
{text}

Return a JSON object with exactly these fields:
{{
  "violence_type":     "murder | sexual_assault | physical_assault | police_brutality | mob_violence | institutional | other",
  "incident_date":     "YYYY-MM-DD or null",
  "state":             "Indian state name or null",
  "city":              "city or district name or null",
  "victim_count":      <integer>,
  "perpetrator_type":  "individual | police | mob | family | unknown",
  "outcome":           "victim_survived | victim_died | unknown",
  "summary":           "<one sentence describing the incident>"
}}

Return ONLY the JSON object, no other text."""


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30))
async def _extract_one(
    article: dict, semaphore: asyncio.Semaphore
) -> tuple[int, dict | None, str | None]:
    """Extract structured data from one article. Returns (article_id, data, raw_json)."""
    async with semaphore:
        text   = (article.get("full_text") or "")[:3000]
        prompt = _PROMPT.format(text=text)
        try:
            resp = await _client.chat.completions.create(
                model=PASS2_MODEL,
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user",   "content": prompt},
                ],
                max_tokens=300,
                temperature=0,
                response_format={"type": "json_object"},
            )
            raw_json = resp.choices[0].message.content.strip()
            data     = json.loads(raw_json)
            return article["id"], data, raw_json
        except json.JSONDecodeError as e:
            log.warning("Pass 2 JSON parse error for article %d: %s", article["id"], e)
            return article["id"], None, None
        except Exception as e:
            log.warning("Pass 2 API error for article %d: %s", article["id"], e)
            return article["id"], None, None


async def _process_batch(batch: list[dict]) -> list[tuple]:
    """Extract all articles in a batch concurrently (bounded by PASS2_CONCURRENCY)."""
    semaphore = asyncio.Semaphore(PASS2_CONCURRENCY)
    return await asyncio.gather(*[_extract_one(a, semaphore) for a in batch])


def _chunk(lst: list, size: int) -> list[list]:
    return [lst[i : i + size] for i in range(0, len(lst), size)]


async def run(batch_size: int = 100, num_batches: int | None = None):
    """
    Run Pass 2 on all articles that passed Pass 1.

    Args:
        batch_size  : Articles per batch.  Example: 200
        num_batches : Max batches to run.  None = run all pending.

    Example — run 6 batches of 200:
        await pass2_extract.run(batch_size=200, num_batches=6)
    """
    pending = db.get_pending_pass2()
    batches = _chunk(pending, batch_size)
    if num_batches is not None:
        batches = batches[:num_batches]

    total = sum(len(b) for b in batches)
    log.info(
        "Pass 2 | %d batch(es) × up to %d articles = %d total | model: %s",
        len(batches), batch_size, total, PASS2_MODEL,
    )

    done_total = 0
    for i, batch in enumerate(tqdm(batches, desc="Pass 2 batches"), start=1):
        results = await _process_batch(batch)

        done_count = 0
        for article_id, data, raw_json in results:
            if data and raw_json:
                db.save_pass2_result(article_id, data, raw_json, PASS2_MODEL)
                done_count += 1

        done_total += done_count
        log.info(
            "  Batch %d/%d → %d extracted / %d total",
            i, len(batches), done_count, len(batch),
        )

    log.info("Pass 2 complete | %d incidents extracted out of %d processed", done_total, total)
