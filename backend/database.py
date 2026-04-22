"""
Database module - SQLite via aiosqlite.
Auto-create DB dan tabel jika belum exist.

Tables:
  news_articles      - hasil scraping RSS feeds
  generated_contents - hasil generate (kolom opsional creator_agent_id)
  creator_agents     - agen dari analisis niche
  creator_scrapes    - bahan konten (RSS) per agen
  saved_niches       - hasil analisis niche yang disimpan pengguna
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

# Tabel alur Creator (dari Niche)
CREATE_CREATOR_TABLES = """
CREATE TABLE IF NOT EXISTS creator_agents (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT    NOT NULL,
    niche_text       TEXT    NOT NULL,
    source_type      TEXT    NOT NULL DEFAULT 'qa',
    scrape_keywords  TEXT    NOT NULL DEFAULT '[]',
    created_at       TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS creator_scrapes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id     INTEGER NOT NULL REFERENCES creator_agents(id) ON DELETE CASCADE,
    source_label TEXT    NOT NULL DEFAULT 'Google News',
    title        TEXT    NOT NULL,
    summary      TEXT,
    url          TEXT    NOT NULL,
    fetched_at   TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_creator_scrapes_agent ON creator_scrapes(agent_id, fetched_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_creator_scrape_agent_url ON creator_scrapes(agent_id, url);
"""

CREATE_SAVED_NICHES_SQL = """
CREATE TABLE IF NOT EXISTS saved_niches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    label        TEXT,
    niche_text   TEXT    NOT NULL,
    source_type  TEXT    NOT NULL DEFAULT 'qa',
    created_at   TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_saved_niches_created ON saved_niches(created_at DESC);
"""


async def _migrate_add_creator_column() -> None:
    """Tambah kolom creator_agent_id ke tabel lama bila belum ada."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("PRAGMA table_info(generated_contents)")
        cols = [row[1] for row in await cursor.fetchall()]
        if "creator_agent_id" not in cols:
            await db.execute(
                "ALTER TABLE generated_contents ADD COLUMN creator_agent_id INTEGER"
            )
            await db.commit()
            print("[DB] Migration: added generated_contents.creator_agent_id")


async def _migrate_add_scrape_keywords() -> None:
    """Tambah kolom scrape_keywords (JSON array) per agen creator."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("PRAGMA table_info(creator_agents)")
        cols = [row[1] for row in await cursor.fetchall()]
        if cols and "scrape_keywords" not in cols:
            await db.execute(
                "ALTER TABLE creator_agents ADD COLUMN scrape_keywords TEXT NOT NULL DEFAULT '[]'"
            )
            await db.commit()
            print("[DB] Migration: added creator_agents.scrape_keywords")


async def init_db() -> None:
    """Buat folder data/ dan inisialisasi database + tabel."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(CREATE_TABLES_SQL)
        await db.executescript(CREATE_CREATOR_TABLES)
        await db.executescript(CREATE_SAVED_NICHES_SQL)
        await db.commit()
    await _migrate_add_creator_column()
    await _migrate_add_scrape_keywords()
    # Index pada kolom baru (bila tabel lama: kolom mungkin baru ditambah)
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_gen_creator_agent "
                "ON generated_contents(creator_agent_id)"
            )
            await db.commit()
        except Exception:
            pass
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
    creator_agent_id: Optional[int] = None,
) -> int:
    """Simpan hasil generate ke DB. Return id baris baru."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO generated_contents
                (news_title, news_summary, news_url, platform, output_types, result, creator_agent_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                news_title,
                news_summary,
                news_url,
                platform,
                json.dumps(output_types, ensure_ascii=False),
                result,
                creator_agent_id,
            ),
        )
        await db.commit()
        return cursor.lastrowid


async def get_history(
    limit: int = 50,
    platform: Optional[str] = None,
    search: Optional[str] = None,
    creator_agent_id: Optional[int] = None,
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
    if creator_agent_id is not None:
        conditions.append("creator_agent_id = ?")
        params.append(creator_agent_id)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            f"""
            SELECT id, news_title, news_summary, news_url, platform,
                   output_types, result, created_at, creator_agent_id
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


# ─────────────────────────────────────────────
# CREATOR AGENTS (alur Niche → Agent)
# ─────────────────────────────────────────────

def _normalize_scrape_keywords(raw) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, str):
        try:
            j = json.loads(raw)
            if isinstance(j, list):
                return [str(x).strip() for x in j if str(x).strip()]
        except Exception:
            return []
    return []


def _agent_dict(row: dict) -> dict:
    d = dict(row)
    d["scrape_keywords"] = _normalize_scrape_keywords(d.get("scrape_keywords"))
    return d


async def create_creator_agent(
    name: str,
    niche_text: str,
    source_type: str = "qa",
    scrape_keywords: Optional[list] = None,
) -> int:
    sk = _normalize_scrape_keywords(scrape_keywords)
    sk_json = json.dumps(sk, ensure_ascii=False)
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO creator_agents (name, niche_text, source_type, scrape_keywords)
            VALUES (?, ?, ?, ?)
            """,
            (name.strip(), niche_text, source_type, sk_json),
        )
        await db.commit()
        return cursor.lastrowid


async def list_creator_agents(limit: int = 100) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT id, name, niche_text, source_type, created_at, scrape_keywords
            FROM creator_agents
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [_agent_dict(dict(r)) for r in await cur.fetchall()]


async def get_creator_agent(agent_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM creator_agents WHERE id = ?", (agent_id,)
        )
        row = await cur.fetchone()
        return _agent_dict(dict(row)) if row else None


async def update_creator_scrape_keywords(agent_id: int, keywords: list[str]) -> bool:
    sk = _normalize_scrape_keywords(keywords)
    sk_json = json.dumps(sk, ensure_ascii=False)
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "UPDATE creator_agents SET scrape_keywords = ? WHERE id = ?",
            (sk_json, agent_id),
        )
        await db.commit()
        return (getattr(cur, "rowcount", None) or 0) > 0


async def delete_creator_agent(agent_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE generated_contents SET creator_agent_id = NULL WHERE creator_agent_id = ?",
            (agent_id,),
        )
        cur = await db.execute("DELETE FROM creator_agents WHERE id = ?", (agent_id,))
        await db.commit()
        return (getattr(cur, "rowcount", None) or 0) > 0


async def save_creator_scrapes(agent_id: int, items: list[dict]) -> int:
    """Simpan hasil scrape; skip duplikat URL per agent (UNIQUE)."""
    if not items:
        return 0
    saved = 0
    async with aiosqlite.connect(DB_PATH) as db:
        for it in items:
            try:
                cur = await db.execute(
                    """
                    INSERT OR IGNORE INTO creator_scrapes
                        (agent_id, source_label, title, summary, url)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        agent_id,
                        it.get("source_label", "Google News"),
                        it.get("title", ""),
                        it.get("summary", ""),
                        it.get("url", ""),
                    ),
                )
                if getattr(cur, "rowcount", None) and cur.rowcount > 0:
                    saved += cur.rowcount
            except Exception as e:
                print(f"[DB] save_creator_scrapes: {e}")
        await db.commit()
    return saved


async def get_creator_scrapes(agent_id: int, limit: int = 50) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT id, agent_id, source_label, title, summary, url, fetched_at
            FROM creator_scrapes
            WHERE agent_id = ?
            ORDER BY fetched_at DESC
            LIMIT ?
            """,
            (agent_id, limit),
        )
        return [dict(r) for r in await cur.fetchall()]


async def count_scrapes_for_agent(agent_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM creator_scrapes WHERE agent_id = ?",
            (agent_id,),
        )
        return (await cur.fetchone())[0]


# ─────────────────────────────────────────────
# SAVED NICHES (arsip hasil analisis)
# ─────────────────────────────────────────────

async def save_niche(
    niche_text: str,
    source_type: str = "qa",
    label: Optional[str] = None,
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO saved_niches (label, niche_text, source_type)
            VALUES (?, ?, ?)
            """,
            (label or "", niche_text, source_type if source_type in ("qa", "trend") else "qa"),
        )
        await db.commit()
        return cursor.lastrowid


async def list_saved_niches(limit: int = 100) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT id, label, niche_text, source_type, created_at
            FROM saved_niches
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(r) for r in await cur.fetchall()]


async def get_saved_niche(niche_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM saved_niches WHERE id = ?", (niche_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def delete_saved_niche(niche_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("DELETE FROM saved_niches WHERE id = ?", (niche_id,))
        await db.commit()
        return (getattr(cur, "rowcount", None) or 0) > 0


async def count_saved_niches() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM saved_niches")
        return (await cur.fetchone())[0]
