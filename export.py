"""
export.py — SQLite → JSON for GitHub Pages

Reads all validated articles from the DB and writes static JSON files
into docs/data/. The GitHub Pages site will fetch these files directly.

Output structure:
  docs/data/
    articles.json          all validated articles, newest first
    stats.json             aggregate counts (for dashboard/charts)
    states-index.json      sorted list of states that have incidents
    by-state/<state>.json  articles grouped by state
    by-year/<year>.json    articles grouped by publication year
"""

import json
import logging
import re
import shutil
from collections import defaultdict
from pathlib import Path

import db
from config import EXPORT_DIR

log = logging.getLogger(__name__)


def _write_json(path: Path, data: object):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.debug("Wrote %s (%d items)", path.name, len(data) if isinstance(data, list) else 1)


def run():
    """
    Export all validated articles to JSON files under docs/data/.
    Safe to run repeatedly — overwrites previous export.
    """
    articles = db.get_validated_articles()
    if not articles:
        log.warning("No validated articles to export yet — run the pipeline first.")
        return

    log.info("Exporting %d articles to %s", len(articles), EXPORT_DIR)

    # Clear grouped subdirectories first — a state/year that had articles in a
    # previous export but has none now (e.g. after a data correction) would
    # otherwise leave a stale, orphaned JSON file behind.
    for subdir in ("by-state", "by-year"):
        shutil.rmtree(EXPORT_DIR / subdir, ignore_errors=True)

    # ── All articles (newest first) ────────────────────────────────────────
    _write_json(EXPORT_DIR / "articles.json", articles)

    # ── By state ──────────────────────────────────────────────────────────
    by_state: dict[str, list] = defaultdict(list)
    for a in articles:
        state = (a.get("state") or "unknown").strip().title()
        by_state[state].append(a)

    for state, items in by_state.items():
        safe = state.lower().replace(" ", "-")
        _write_json(EXPORT_DIR / "by-state" / f"{safe}.json", items)

    _write_json(EXPORT_DIR / "states-index.json", sorted(by_state.keys()))

    # ── By year ───────────────────────────────────────────────────────────
    by_year: dict[str, list] = defaultdict(list)
    for a in articles:
        date = a.get("published_date") or a.get("incident_date") or ""
        match = re.match(r"^(\d{4})", date)
        year = match.group(1) if match else "unknown"
        by_year[year].append(a)

    for year, items in by_year.items():
        _write_json(EXPORT_DIR / "by-year" / f"{year}.json", items)

    # ── Stats (for dashboard charts) ──────────────────────────────────────
    violence_counts:    dict[str, int] = defaultdict(int)
    outcome_counts:     dict[str, int] = defaultdict(int)
    perpetrator_counts: dict[str, int] = defaultdict(int)

    for a in articles:
        violence_counts[a.get("violence_type") or "unknown"]       += 1
        outcome_counts[a.get("outcome") or "unknown"]              += 1
        perpetrator_counts[a.get("perpetrator_type") or "unknown"] += 1

    stats = {
        "total_incidents":   len(articles),
        "by_violence_type":  dict(violence_counts),
        "by_outcome":        dict(outcome_counts),
        "by_perpetrator":    dict(perpetrator_counts),
        "by_year":           {yr: len(items) for yr, items in sorted(by_year.items())},
        "by_state":          {st: len(items) for st, items in sorted(by_state.items())},
        "pipeline_stats":    db.stats(),
    }
    _write_json(EXPORT_DIR / "stats.json", stats)

    log.info("Export complete.")
