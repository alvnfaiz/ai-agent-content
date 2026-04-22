import asyncio
import feedparser
import re
import time
from datetime import datetime
from typing import Optional

RSS_FEEDS = {
    "TechCrunch AI": "https://techcrunch.com/category/artificial-intelligence/feed/",
    "The Verge AI": "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml",
    "MIT Technology Review": "https://www.technologyreview.com/feed/",
    "Wired AI": "https://www.wired.com/feed/tag/ai/latest/rss",
    "Google News AI": "https://news.google.com/rss/search?q=artificial+intelligence&hl=id&gl=ID&ceid=ID:id",
}

_cache: dict = {"data": [], "timestamp": 0}
CACHE_TTL = 30 * 60  # 30 menit


def _parse_date(entry) -> str:
    try:
        t = entry.get("published_parsed") or entry.get("updated_parsed")
        if t:
            return datetime(*t[:6]).strftime("%d %b %Y, %H:%M")
    except Exception:
        pass
    return ""


def _fetch_feed(source_name: str, url: str) -> list[dict]:
    try:
        feed = feedparser.parse(url)
        articles = []
        for entry in feed.entries[:8]:
            summary = entry.get("summary", "")
            summary = re.sub(r"<[^>]+>", "", summary).strip()
            summary = summary[:300] + "..." if len(summary) > 300 else summary

            articles.append({
                "source": source_name,
                "title": entry.get("title", ""),
                "summary": summary,
                "url": entry.get("link", ""),
                "published": _parse_date(entry),
            })
        return articles
    except Exception as e:
        print(f"[news_fetcher] Error fetching {source_name}: {e}")
        return []


def get_news(force_refresh: bool = False) -> list[dict]:
    global _cache
    now = time.time()

    if not force_refresh and _cache["data"] and (now - _cache["timestamp"]) < CACHE_TTL:
        return _cache["data"]

    all_articles = []
    for source_name, url in RSS_FEEDS.items():
        articles = _fetch_feed(source_name, url)
        all_articles.extend(articles)

    _cache["data"] = all_articles
    _cache["timestamp"] = now
    return all_articles


async def get_news_and_save(force_refresh: bool = False) -> list[dict]:
    """Fetch berita dan simpan artikel baru ke database."""
    from database import save_articles

    articles = get_news(force_refresh=force_refresh)
    if articles:
        saved = await save_articles(articles)
        if saved:
            print(f"[news_fetcher] {saved} artikel baru disimpan ke DB")
    return articles


def get_cache_age_minutes() -> Optional[float]:
    if _cache["timestamp"] == 0:
        return None
    return round((time.time() - _cache["timestamp"]) / 60, 1)
