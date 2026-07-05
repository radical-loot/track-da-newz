"""
config.py — ALL configuration lives here.
Change values here; nothing else needs to be edited for basic tuning.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────────

ROOT     = Path(__file__).parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH    = DATA_DIR / "articles.db"
EXPORT_DIR = ROOT / "docs" / "data"

# ── API Keys ───────────────────────────────────────────────────────────────────

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
NEWSDATA_API_KEY   = os.getenv("NEWSDATA_API_KEY", "")
GNEWS_API_KEY      = os.getenv("GNEWS_API_KEY", "")

# ── LLM Models (via OpenRouter) ───────────────────────────────────────────────

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

PASS1_MODEL       = "deepseek/deepseek-v4-flash"  # binary YES/NO filter
PASS2_MODEL       = "openai/gpt-5.4-nano"         # structured extraction

# Max concurrent LLM calls within a single batch (stay within rate limits)
PASS1_CONCURRENCY = 10
PASS2_CONCURRENCY = 5

# ── Search Terms ───────────────────────────────────────────────────────────────

# All terms used in India to refer to trans/third-gender people
TRANS_TERMS = [
    "transgender",
    "trans woman",
    "trans man",
    "hijra",
    "hijda",
    "hijira",
    "kinnar",
    "kinnara",
    "aravani",
    "aruvani",
    "thirunangai",
    "thirunamba",
    "third gender",
    "eunuch",
    "chakka",
    "koti",
    "shiv-shakti",
    "jogta",
    "jogappa",
]

VIOLENCE_TERMS = [
    "killed",
    "murder",
    "murdered",
    "attack",
    "attacked",
    "assault",
    "assaulted",
    "beaten",
    "rape",
    "raped",
    "gang rape",
    "molested",
    "stabbed",
    "shot",
    "lynched",
    "mob attack",
    "hate crime",
    "violence",
    "brutality",
    "tortured",
    "kidnapped",
    "acid attack",
    "thrashed",
    "stripped",
    "burnt alive",
]

# GDELT GKG theme codes for violence (used in BigQuery queries)
GDELT_VIOLENCE_THEMES = [
    "KILL",
    "ASSAULT",
    "RAPE",
    "VIOLENCE",
    "MURDER",
    "CRISISLEX_T11_PERSONAL_VIOLENCE",
    "CRISISLEX_C09_CRIME_VIOLENCE",
]

# ── Indian News Sources ────────────────────────────────────────────────────────

# Known Indian English news domains — used to filter GDELT BigQuery results
INDIAN_NEWS_DOMAINS = [
    "thewire.in",
    "scroll.in",
    "ndtv.com",
    "thehindu.com",
    "hindustantimes.com",
    "indianexpress.com",
    "timesofindia.indiatimes.com",
    "theprint.in",
    "thequint.com",
    "indiatoday.in",
    "news18.com",
    "deccanherald.com",
    "outlookindia.com",
    "livemint.com",
    "business-standard.com",
    "sabrangindia.in",
    "twocircles.net",
    "feminisminindia.com",
    "behanbox.com",
    "thelallantop.com",
    "firstpost.com",
    "caravanmagazine.in",
    "newslaundry.com",
    "theleaflet.in",
    "telegraphindia.com",
    "thestatesman.com",
    "newindianexpress.com",
    "downtoearth.org.in",
    "thesouthfirst.com",
]

# Direct RSS feeds — fetched without any API key
INDIAN_NEWS_RSS_FEEDS = {
    "The Wire":          "https://thewire.in/rss",
    "Scroll.in":         "https://scroll.in/rss",
    "NDTV":              "https://feeds.feedburner.com/ndtvnews-latest",
    "The Hindu":         "https://www.thehindu.com/feeder/default.rss",
    "Hindustan Times":   "https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml",
    "The Quint":         "https://www.thequint.com/rss",
    "Indian Express":    "https://indianexpress.com/feed/",
    "Times of India":    "https://timesofindia.indiatimes.com/rssfeedmostrecent.cms",
    "Deccan Herald":     "https://www.deccanherald.com/rss",
    "The Print":         "https://theprint.in/feed/",
    "Outlook India":     "https://www.outlookindia.com/rss",
    "India Today":       "https://www.indiatoday.in/rss",
    "News18":            "https://www.news18.com/rss/india.xml",
    "Feminism in India": "https://feminisminindia.com/feed/",
    "BehanBox":          "https://behanbox.com/feed/",
    "SabrangIndia":      "https://sabrangindia.in/rss.xml",
    "TwoCircles.net":    "https://twocircles.net/feed/",
    "The Lallantop":     "https://www.thelallantop.com/feed/",
    "The Leaflet":       "https://theleaflet.in/feed/",
    "NewsLaundry":       "https://www.newslaundry.com/feed",
    "Caravan Magazine":  "https://caravanmagazine.in/feed",
    "The South First":   "https://thesouthfirst.com/feed/",
}

# ── GDELT DOC API ──────────────────────────────────────────────────────────────

GDELT_DOC_API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_MAX_RECORDS = 250   # API hard maximum per request
GDELT_CHUNK_DAYS  = 30    # monthly windows: 19 queries × ~90 months = ~1710 requests

# ── HTTP ───────────────────────────────────────────────────────────────────────

HTTP_TIMEOUT    = 30
HTTP_USER_AGENT = "TrackDaNewzBot/1.0 (academic research)"
HTTP_MAX_RETRIES = 3
