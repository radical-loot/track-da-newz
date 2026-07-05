"""
collectors/gdelt_bigquery.py — GDELT via Google BigQuery (historical backfill)

Use this for a thorough one-time sweep of 2019 → present.
Free tier: 1 TB of queries per month — this query should use < 100 GB.

Auth setup (one of):
  Option A: gcloud auth application-default login   (recommended for local use)
  Option B: set GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json

The query filters the GDELT GKG table to:
  - Known Indian English news domains only
  - Articles with at least one violence-related GDELT theme code
Then the LLM passes filter down to trans-related violence.
"""

import logging
from datetime import datetime

from config import GDELT_VIOLENCE_THEMES, INDIAN_NEWS_DOMAINS

log = logging.getLogger(__name__)


def _build_query(start: datetime, end: datetime) -> str:
    start_int = int(start.strftime("%Y%m%d%H%M%S"))
    end_int   = int(end.strftime("%Y%m%d%H%M%S"))

    domains_sql = ", ".join(f"'{d}'" for d in INDIAN_NEWS_DOMAINS)
    themes_sql  = " OR ".join(
        f"V2Themes LIKE '%{t}%'" for t in GDELT_VIOLENCE_THEMES
    )

    return f"""
        SELECT
            DATE                AS raw_date,
            DocumentIdentifier  AS url,
            SourceCommonName    AS source_domain,
            V2Themes            AS themes,
            V2Locations         AS locations
        FROM `gdelt-bq.gdeltv2.gkg`
        WHERE _PARTITIONTIME BETWEEN TIMESTAMP('{start.date()}') AND TIMESTAMP('{end.date()}')
          AND DATE BETWEEN {start_int} AND {end_int}
          AND SourceCommonName IN ({domains_sql})
          AND ({themes_sql})
    """


def _estimate_scan(client, query: str) -> float:
    """Dry-run the query and return GB that will be scanned."""
    from google.cloud import bigquery
    job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    job = client.query(query, job_config=job_config)
    return job.total_bytes_processed / 1e9


def collect(start: datetime, end: datetime) -> list[dict]:
    """
    Query GDELT BigQuery GKG for articles from known Indian news domains
    that contain violence-related themes.

    Returns a list of candidate dicts. Requires Google Cloud auth.
    """
    try:
        from google.cloud import bigquery
    except ImportError:
        log.error("google-cloud-bigquery not installed. Run: uv add google-cloud-bigquery")
        return []

    client = bigquery.Client()
    query  = _build_query(start, end)

    try:
        gb = _estimate_scan(client, query)
        log.info("BigQuery dry run: %.2f GB will be scanned (free tier: 1000 GB/month)", gb)
    except Exception as e:
        log.warning("Dry run estimate failed (proceeding anyway): %s", e)

    log.info("BigQuery: running query for %s → %s", start.date(), end.date())
    try:
        rows = list(client.query(query).result())
    except Exception as e:
        log.error("BigQuery query failed: %s", e)
        return []

    candidates = []
    for row in rows:
        date_str = str(row.raw_date)[:8]   # YYYYMMDDHHMMSS → YYYYMMDD
        candidates.append({
            "url":              row.url,
            "title":            None,
            "published_date":   date_str,
            "source_name":      row.source_domain,
            "source_domain":    row.source_domain,
            "discovery_source": "gdelt_bigquery",
            "excerpt":          None,
        })

    log.info("BigQuery: %d candidates found", len(candidates))
    return candidates
