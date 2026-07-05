"""
run_export.py — Export validated articles to JSON for GitHub Pages

Reads all articles that completed both LLM passes from the DB
and writes static JSON files to docs/data/.

Safe to run at any time — overwrites previous export with latest data.

Usage:
  uv run python run_export.py
"""

import logging
import pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)

if __name__ == "__main__":
    pipeline.run_export()
