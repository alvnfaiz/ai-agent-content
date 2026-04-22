"""
Database module - SQLite via aiosqlite.
Auto-create DB dan tabel jika belum exist.

Tables:
  news_articles      - hasil scraping RSS feeds
  generated_contents - hasil generate konten dari Ollama
"""

import aiosqlite
import json
import os
from datetime import datetime
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "content_agent.db")

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS news_articles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT    NOT NULL,
    title       TEXT    NOT NULL,
    summary     TEXT,
    url         TEXT    UNIQUE NOT NULL,
    published   TEXT,
    fetched_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS generated_contents (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    news_title   TEXT    NOT NULL,
    news_summary TEXT,
    news_url     TEXT,
    platform     TEXT    NOT NULL,
    output_types TEXT    NOT NULL,
    result       TEXT    NOT NULL,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_news_fetched   ON news_articles(fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_gen_created    ON generated_contents(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_gen_platform   ON generated_contents(platform);
"""


async def init_db() -> None:
    """Buat folder data/ dan inisialisasi database + tabel."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(CREATE_TABLES_SQL)
        await db.commit()
    print(f"[DB] Database siap: {DB_PATH}")


# ─────────────────────────────────────────────
# NEWS ARTICLES
# ─────────────────────────────────────────────

async def save_articles(articles: list[dict]) -> int:
    """
    Simpan list artikel ke DB. Skip duplikat berdasarkan URL.
    Return jumlah artikel baru yang berhasil disimpan.
    """
    if not articles:
        return 0

    saved = 0
    async with aiosqlite.connect(DB_PATH) as db:
        for article in articles:
            try:
                await db.execute(
                    """
                    INSERT OR IGNORE INTO news_articles (source, title, summary, url, published)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        article.get("source", ""),
                        article.get("title", ""),
                        article.get("summary", ""),
                        article.get("url", ""),
                        article.get("published", ""),
                    ),
                )
                if db.total_changes > saved:
                    saved = db.total_changes
            except Exception as e:
                print(f"[DB] Error saving article: {e}")
        await db.commit()

    return saved


async def get_saved_news(
    limit: int = 100,
    source: Optional[str] = None,
    search: Optional[str] = None,
) -> list[dict]:
    """Ambil berita dari DB dengan filter opsional."""
    conditions = []
    params = []

    if source:
        conditions.append("source = ?")
        params.append(source)
    if search:
        conditions.append("(title LIKE ? OR summary LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            f"""
            SELECT id, source, title, summary, url, published, fetched_at
            FROM news_articles
            {where}
            ORDER BY fetched_at DESC
            LIMIT ?
            """,
            params,
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_news_sources() -> list[str]:
    """Ambil daftar sumber berita unik dari DB."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT DISTINCT source FROM news_articles ORDER BY source"
        )
        rows = await cursor.fetchall()
        return [r[0] for r in rows]


async def get_news_stats() -> dict:
    """Statistik tabel news_articles."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM news_articles")
        total = (await cur.fetchone())[0]

        cur = await db.execute(
            "SELECT COUNT(*) FROM news_articles WHERE fetched_at >= datetime('now', '-1 day', 'localtime')"
        )
        today = (await cur.fetchone())[0]

        cur = await db.execute(
            "SELECT source, COUNT(*) as cnt FROM news_articles GROUP BY source ORDER BY cnt DESC"
        )
        by_source = [{"source": r[0], "count": r[1]} for r in await cur.fetchall()]

    return {"total": total, "last_24h": today, "by_source": by_source}


# ─────────────────────────────────────────────
# GENERATED CONTENTS
# ─────────────────────────────────────────────

async def save_generated_content(
    news_title: str,
    news_summary: str,
    platform: str,
    output_types: list[str],
    result: str,
    news_url: str = "",
) -> int:
    """Simpan hasil generate ke DB. Return id baris baru."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO generated_contents
                (news_title, news_summary, news_url, platform, output_types, result)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                news_title,
                news_summary,
                news_url,
                platform,
                json.dumps(output_types, ensure_ascii=False),
                result,
            ),
        )
        await db.commit()
        return cursor.lastrowid


async def get_history(
    limit: int = 50,
    platform: Optional[str] = None,
    search: Optional[str] = None,
) -> list[dict]:
    """Ambil riwayat generate dengan filter opsional."""
    conditions = []
    params = []

    if platform:
        conditions.append("platform = ?")
        params.append(platform)
    if search:
        conditions.append("(news_title LIKE ? OR result LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            f"""
            SELECT id, news_title, news_summary, news_url, platform,
                   output_types, result, created_at
            FROM generated_contents
            {where}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            params,
        )
        rows = await cursor.fetchall()
        result_list = []
        for r in rows:
            row = dict(r)
            try:
                row["output_types"] = json.loads(row["output_types"])
            except Exception:
                row["output_types"] = []
            result_list.append(row)
        return result_list


async def get_history_item(item_id: int) -> Optional[dict]:
    """Ambil satu item history berdasarkan ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM generated_contents WHERE id = ?", (item_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        data = dict(row)
        try:
            data["output_types"] = json.loads(data["output_types"])
        except Exception:
            data["output_types"] = []
        return data


async def delete_history_item(item_id: int) -> bool:
    """Hapus item history berdasarkan ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM generated_contents WHERE id = ?", (item_id,)
        )
        await db.commit()
        return db.total_changes > 0


async def get_generate_stats() -> dict:
    """Statistik tabel generated_contents."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM generated_contents")
        total = (await cur.fetchone())[0]

        cur = await db.execute(
            "SELECT COUNT(*) FROM generated_contents WHERE created_at >= datetime('now', '-1 day', 'localtime')"
        )
        today = (await cur.fetchone())[0]

        cur = await db.execute(
            "SELECT platform, COUNT(*) as cnt FROM generated_contents GROUP BY platform ORDER BY cnt DESC"
        )
        by_platform = [{"platform": r[0], "count": r[1]} for r in await cur.fetchall()]

    return {"total": total, "last_24h": today, "by_platform": by_platform}
