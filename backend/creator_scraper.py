"""
Scrape / agregasi bahan konten untuk niche creator.
Menggunakan Google News RSS + query dari teks niche (tanpa browser headless).
"""

import re
import urllib.parse

import feedparser

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={q}&hl=id&gl=ID&ceid=ID:id"


def _strip_markdown_noise(text: str) -> str:
    t = re.sub(r"#{1,6}\s*", " ", text)
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"[*_`]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _build_search_queries(
    niche_text: str,
    agent_name: str,
    max_queries: int = 3,
    extra_keywords: list[str] | None = None,
) -> list[str]:
    """Bangun 1–3 query pencarian berita dari keyword tersimpan, niche, dan nama agen."""
    out_from_kw: list[str] = []
    if extra_keywords:
        seen_kw: set[str] = set()
        for w in extra_keywords:
            s = (w or "").strip()
            if not s or len(s) > 80:
                continue
            key = s.lower()
            if key in seen_kw:
                continue
            seen_kw.add(key)
            out_from_kw.append(f"{s} Indonesia")
        out_from_kw = out_from_kw[:4]

    base = _strip_markdown_noise(niche_text[:1200])
    words = re.findall(r"[\w]{3,}", base, re.UNICODE)
    # Kata-kata khas Indonesia / teknologi
    stop = {
        "dan", "yang", "untuk", "dengan", "dari", "ini", "itu", "atau", "adalah", "akan", "telah",
        "the", "and", "for", "with", "from", "niche", "rekomendasi", "content", "creator",
    }
    keywords = [w for w in words if w.lower() not in stop][:12]

    queries: list[str] = []
    name_clean = agent_name.strip()
    if name_clean and len(name_clean) < 60:
        queries.append(f"{name_clean} Indonesia konten")

    if keywords:
        chunk = " ".join(keywords[:8])
        queries.append(f"{chunk} Indonesia")

    # Ringkas: ambil baris berisi "NICHE" atau judul kandidat
    for line in base.split("\n")[:20]:
        line = line.strip()
        if 15 < len(line) < 200 and re.search(r"[a-zA-Z0-9\u00c0-\u024f]{4,}", line):
            queries.append(line[:120])
            break

    # Dedupe
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        if q and q not in seen:
            seen.add(q)
            out.append(q)
        if len(out) >= max_queries:
            break
    if not out:
        out = ["teknologi AI konten kreator Indonesia"]

    # Prioritas: query dari keyword tersimpan agen dulu, lalu hasil auto
    merged: list[str] = []
    seen_m: set[str] = set()
    for q in out_from_kw + out:
        if q and q not in seen_m:
            seen_m.add(q)
            merged.append(q)
    limit = 5 if out_from_kw else max_queries
    return merged[: min(6, max(limit, 3))]


def _fetch_rss_query(query: str, limit: int = 8) -> list[dict]:
    q = urllib.parse.quote_plus(query)
    url = GOOGLE_NEWS_RSS.format(q=q)
    try:
        feed = feedparser.parse(url)
    except Exception as e:
        print(f"[creator_scraper] feedparse error: {e}")
        return []

    items = []
    for entry in feed.entries[:limit]:
        summary = re.sub(r"<[^>]+>", "", entry.get("summary", "")).strip()
        if len(summary) > 300:
            summary = summary[:300] + "..."
        items.append({
            "source_label": "Google News",
            "title": entry.get("title", "")[:500],
            "summary": summary,
            "url": entry.get("link", "")[:2000],
        })
    return items


def scrape_for_niche(
    niche_text: str,
    agent_name: str = "",
    per_query: int = 6,
    max_total: int = 25,
    extra_keywords: list[str] | None = None,
) -> list[dict]:
    """
    Kumpulkan artikel relevan dari beberapa query RSS.
    Return list dict dengan title, summary, url, source_label.
    extra_keywords: keyword tersimpan per agen; memprioritaskan pencarian berita.
    """
    nq = 3
    if extra_keywords and len([k for k in extra_keywords if (k or "").strip()]):
        nq = 5
    queries = _build_search_queries(
        niche_text, agent_name, max_queries=nq, extra_keywords=extra_keywords
    )
    seen_urls: set[str] = set()
    all_items: list[dict] = []

    for q in queries:
        batch = _fetch_rss_query(q, limit=per_query)
        for it in batch:
            u = it.get("url", "")
            if not u or u in seen_urls:
                continue
            seen_urls.add(u)
            all_items.append(it)
            if len(all_items) >= max_total:
                return all_items
    return all_items
