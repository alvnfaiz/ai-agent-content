import asyncio
import feedparser
import re
import time
from datetime import datetime
from typing import Optional

# ─────────────────────────────────────────────
# Daftar sumber RSS — dikelompokkan per kategori
# ─────────────────────────────────────────────

RSS_FEEDS: dict[str, str] = {
    # ── Global AI / Tech ──
    "TechCrunch AI":        "https://techcrunch.com/category/artificial-intelligence/feed/",
    "The Verge AI":         "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml",
    "Wired AI":             "https://www.wired.com/feed/tag/ai/latest/rss",
    "MIT Technology Review":"https://www.technologyreview.com/feed/",
    "Ars Technica":         "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "VentureBeat AI":       "https://venturebeat.com/category/ai/feed/",
    "ZDNet AI":             "https://www.zdnet.com/topic/artificial-intelligence/rss.xml",
    "CNET AI":              "https://www.cnet.com/rss/ai/",

    # ── AI Labs / Companies ──
    "OpenAI Blog":          "https://openai.com/news/rss.xml",
    "Google DeepMind":      "https://deepmind.google/blog/rss.xml",
    "Microsoft AI Blog":    "https://blogs.microsoft.com/ai/feed/",
    "NVIDIA Blog":          "https://blogs.nvidia.com/feed/",
    "Hugging Face Blog":    "https://huggingface.co/blog/feed.xml",
    "Google AI Blog":       "https://blog.research.google/feeds/posts/default",

    # ── Dev / Data Science ──
    "Towards Data Science": "https://towardsdatascience.com/feed",
    "IEEE Spectrum AI":     "https://spectrum.ieee.org/feeds/topic/artificial-intelligence.rss",

    # ── Google News (berbagai topik) ──
    "Google News AI":       "https://news.google.com/rss/search?q=artificial+intelligence&hl=id&gl=ID&ceid=ID:id",
    "Google News LLM":      "https://news.google.com/rss/search?q=large+language+model&hl=id&gl=ID&ceid=ID:id",
    "Google News AI ID":    "https://news.google.com/rss/search?q=kecerdasan+buatan+AI&hl=id&gl=ID&ceid=ID:id",
    "Google News ChatGPT":  "https://news.google.com/rss/search?q=ChatGPT+Gemini+Claude&hl=id&gl=ID&ceid=ID:id",

    # ── Media Indonesia ──
    "Detik Inet":           "https://rss.detik.com/inet",
    "Kompas Tekno":         "https://rss.kompas.com/tekno",
    "Tempo Tekno":          "https://rss.tempo.co/tekno",
    "CNN Indonesia Tekno":  "https://www.cnnindonesia.com/teknologi/rss",
}

# ── Jumlah artikel per kondisi ──
LIMIT_ALL    = 6   # per sumber saat semua sumber diminta
LIMIT_SINGLE = 30  # saat satu sumber spesifik dipilih

# ── Cache: key "all" untuk semua sumber, atau nama sumber untuk spesifik ──
_cache: dict[str, dict] = {}
CACHE_TTL = 30 * 60  # 30 menit


def _parse_date(entry) -> str:
    try:
        t = entry.get("published_parsed") or entry.get("updated_parsed")
        if t:
            return datetime(*t[:6]).strftime("%d %b %Y, %H:%M")
    except Exception:
        pass
    return ""


def _fetch_feed(source_name: str, url: str, limit: int = LIMIT_ALL) -> list[dict]:
    try:
        feed = feedparser.parse(url)
        articles = []
        for entry in feed.entries[:limit]:
            summary = entry.get("summary", "")
            summary = re.sub(r"<[^>]+>", "", summary).strip()
            summary = summary[:300] + "..." if len(summary) > 300 else summary

            articles.append({
                "source":    source_name,
                "title":     entry.get("title", ""),
                "summary":   summary,
                "url":       entry.get("link", ""),
                "published": _parse_date(entry),
            })
        return articles
    except Exception as e:
        print(f"[news_fetcher] Error fetching {source_name}: {e}")
        return []


def _is_cached(key: str) -> bool:
    entry = _cache.get(key)
    if not entry or not entry.get("data"):
        return False
    return (time.time() - entry["timestamp"]) < CACHE_TTL


def _set_cache(key: str, data: list[dict]) -> None:
    _cache[key] = {"data": data, "timestamp": time.time()}


def get_news(source: Optional[str] = None, force_refresh: bool = False) -> list[dict]:
    """
    Ambil berita dari RSS.
    - source=None  → semua sumber, masing-masing LIMIT_ALL artikel, cache key="all"
    - source=nama  → satu sumber saja, LIMIT_SINGLE artikel, cache key=nama sumber
    """
    if source and source not in RSS_FEEDS:
        return []

    cache_key = source if source else "all"

    if not force_refresh and _is_cached(cache_key):
        return _cache[cache_key]["data"]

    if source:
        # Fetch satu sumber saja, 30 artikel
        articles = _fetch_feed(source, RSS_FEEDS[source], limit=LIMIT_SINGLE)
    else:
        # Fetch semua sumber, 6 artikel per sumber
        articles = []
        for source_name, url in RSS_FEEDS.items():
            articles.extend(_fetch_feed(source_name, url, limit=LIMIT_ALL))

    _set_cache(cache_key, articles)
    return articles


async def get_news_and_save(
    source: Optional[str] = None,
    force_refresh: bool = False,
) -> list[dict]:
    """Fetch berita dan simpan artikel baru ke database."""
    from database import save_articles

    articles = get_news(source=source, force_refresh=force_refresh)
    if articles:
        saved = await save_articles(articles)
        if saved:
            print(f"[news_fetcher] {saved} artikel baru disimpan ke DB")
    return articles


def get_all_source_names() -> list[str]:
    return list(RSS_FEEDS.keys())


def get_cache_age_minutes(source: Optional[str] = None) -> Optional[float]:
    key = source if source else "all"
    entry = _cache.get(key)
    if not entry or not entry.get("timestamp"):
        return None
    return round((time.time() - entry["timestamp"]) / 60, 1)
