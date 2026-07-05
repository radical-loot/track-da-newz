"""
db.py — All database operations in one place.
Uses SQLite with WAL mode for safe concurrent reads during long pipeline runs.
"""

import hashlib
import logging
import sqlite3
from config import DB_PATH

log = logging.getLogger(__name__)


# ── Connection ─────────────────────────────────────────────────────────────────

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row   # rows accessible as dicts
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ── Schema ─────────────────────────────────────────────────────────────────────

def init_db():
    """Create all tables. Safe to call multiple times (IF NOT EXISTS)."""
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS articles (
                id                INTEGER PRIMARY KEY,
                url               TEXT UNIQUE NOT NULL,
                url_normalized    TEXT,
                title             TEXT,
                source_name       TEXT,
                source_domain     TEXT,
                published_date    TEXT,
                scraped_at        TEXT DEFAULT (datetime('now')),
                discovery_source  TEXT,
                full_text         TEXT,
                excerpt           TEXT,
                content_hash      TEXT,
                is_paywalled      INTEGER DEFAULT 0,
                extraction_status TEXT    DEFAULT 'pending'
            );

            CREATE TABLE IF NOT EXISTS pass1_results (
                article_id   INTEGER PRIMARY KEY REFERENCES articles(id),
                result       TEXT,
                model        TEXT,
                validated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS pass2_results (
                article_id       INTEGER PRIMARY KEY REFERENCES articles(id),
                violence_type    TEXT,
                incident_date    TEXT,
                state            TEXT,
                city             TEXT,
                victim_count     INTEGER,
                perpetrator_type TEXT,
                outcome          TEXT,
                summary          TEXT,
                raw_json         TEXT,
                model            TEXT,
                extracted_at     TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_url_norm      ON articles(url_normalized);
            CREATE INDEX IF NOT EXISTS idx_extraction    ON articles(extraction_status);
            CREATE INDEX IF NOT EXISTS idx_pub_date      ON articles(published_date);
        """)
    log.debug("Database initialised at %s", DB_PATH)


# ── Writes ─────────────────────────────────────────────────────────────────────

def insert_candidates(candidates: list[dict]) -> int:
    """
    Insert new article candidates, skipping any URL already in the DB.
    Returns the count of newly inserted rows.
    """
    inserted = 0
    with get_connection() as conn:
        for c in candidates:
            try:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO articles
                        (url, url_normalized, title, source_name, source_domain,
                         published_date, discovery_source, excerpt)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        c["url"],
                        c.get("url_normalized", c["url"]),
                        c.get("title"),
                        c.get("source_name"),
                        c.get("source_domain"),
                        c.get("published_date"),
                        c.get("discovery_source"),
                        c.get("excerpt"),
                    ),
                )
                if conn.execute("SELECT changes()").fetchone()[0]:
                    inserted += 1
            except sqlite3.Error as e:
                log.debug("Insert skipped: %s", e)
    return inserted


def save_extracted_text(article_id: int, full_text: str, is_paywalled: bool):
    content_hash = hashlib.sha256(full_text[:2000].encode()).hexdigest()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE articles
               SET full_text = ?, content_hash = ?, is_paywalled = ?,
                   extraction_status = 'done'
             WHERE id = ?
            """,
            (full_text, content_hash, int(is_paywalled), article_id),
        )


def mark_extraction_failed(article_id: int):
    with get_connection() as conn:
        conn.execute(
            "UPDATE articles SET extraction_status = 'failed' WHERE id = ?",
            (article_id,),
        )


def save_pass1_result(article_id: int, result: str, model: str):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO pass1_results (article_id, result, model)
            VALUES (?, ?, ?)
            """,
            (article_id, result, model),
        )


def save_pass2_result(article_id: int, data: dict, raw_json: str, model: str):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO pass2_results
                (article_id, violence_type, incident_date, state, city,
                 victim_count, perpetrator_type, outcome, summary, raw_json, model)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                article_id,
                data.get("violence_type"),
                data.get("incident_date"),
                data.get("state"),
                data.get("city"),
                data.get("victim_count"),
                data.get("perpetrator_type"),
                data.get("outcome"),
                data.get("summary"),
                raw_json,
                model,
            ),
        )


# ── Reads ──────────────────────────────────────────────────────────────────────

def get_pending_extraction(limit: int = 1000) -> list[dict]:
    """Articles that have been collected but whose full text hasn't been fetched yet."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, url, title, source_name
              FROM articles
             WHERE extraction_status = 'pending'
             LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_pending_pass1(limit: int | None = None) -> list[dict]:
    """Articles with full text but no Pass 1 result yet."""
    sql = """
        SELECT a.id, a.title, a.excerpt, a.full_text, a.source_name, a.published_date
          FROM articles a
     LEFT JOIN pass1_results p1 ON a.id = p1.article_id
         WHERE a.extraction_status = 'done'
           AND p1.result IS NULL
    """
    if limit:
        sql += f" LIMIT {limit}"
    with get_connection() as conn:
        rows = conn.execute(sql).fetchall()
    return [dict(r) for r in rows]


def get_pending_pass2(limit: int | None = None) -> list[dict]:
    """Articles that passed Pass 1 (YES) but haven't been structurally extracted yet."""
    sql = """
        SELECT a.id, a.title, a.full_text, a.source_name, a.published_date
          FROM articles a
          JOIN pass1_results p1 ON a.id = p1.article_id
     LEFT JOIN pass2_results p2 ON a.id = p2.article_id
         WHERE p1.result = 'YES'
           AND p2.article_id IS NULL
    """
    if limit:
        sql += f" LIMIT {limit}"
    with get_connection() as conn:
        rows = conn.execute(sql).fetchall()
    return [dict(r) for r in rows]


def get_validated_articles() -> list[dict]:
    """All articles that passed both LLM passes — used for the JSON export."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT a.url, a.title, a.source_name, a.source_domain,
                   a.published_date, a.excerpt,
                   p2.violence_type, p2.incident_date, p2.state, p2.city,
                   p2.victim_count, p2.perpetrator_type, p2.outcome, p2.summary
              FROM articles a
              JOIN pass1_results p1 ON a.id = p1.article_id
              JOIN pass2_results p2 ON a.id = p2.article_id
             WHERE p1.result = 'YES'
             ORDER BY a.published_date DESC
            """
        ).fetchall()
    return [dict(r) for r in rows]


def url_exists(url_normalized: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM articles WHERE url_normalized = ?", (url_normalized,)
        ).fetchone()
    return row is not None


def stats() -> dict:
    with get_connection() as conn:
        total      = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        extracted  = conn.execute("SELECT COUNT(*) FROM articles WHERE extraction_status='done'").fetchone()[0]
        failed     = conn.execute("SELECT COUNT(*) FROM articles WHERE extraction_status='failed'").fetchone()[0]
        pass1_yes  = conn.execute("SELECT COUNT(*) FROM pass1_results WHERE result='YES'").fetchone()[0]
        pass1_no   = conn.execute("SELECT COUNT(*) FROM pass1_results WHERE result='NO'").fetchone()[0]
        pass2_done = conn.execute("SELECT COUNT(*) FROM pass2_results").fetchone()[0]
    return {
        "total_collected":  total,
        "extracted":        extracted,
        "extraction_failed": failed,
        "pass1_yes":        pass1_yes,
        "pass1_no":         pass1_no,
        "pass2_done":       pass2_done,
    }
