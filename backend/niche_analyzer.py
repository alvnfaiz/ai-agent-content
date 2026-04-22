"""
Niche Analyzer — AI-powered niche recommendations untuk content creator Indonesia.

Dua mode:
  1. Q&A Wizard : jawab kuesioner → AI rekomendasikan niche paling cocok
  2. Tren Saat Ini : ambil topik trending dari RSS → AI analisa peluang niche
"""

import feedparser
import re
import time
from typing import Generator, Optional

import ollama

# ─────────────────────────────────────────────
# RSS FEEDS untuk riset tren per kategori
# ─────────────────────────────────────────────

NICHE_TREND_FEEDS: dict[str, str] = {
    "Teknologi & AI":    "https://news.google.com/rss/search?q=teknologi+AI+Indonesia&hl=id&gl=ID&ceid=ID:id",
    "Finance & Crypto":  "https://news.google.com/rss/search?q=investasi+saham+crypto+Indonesia&hl=id&gl=ID&ceid=ID:id",
    "Gaming & Esports":  "https://news.google.com/rss/search?q=gaming+esports+Indonesia+2025&hl=id&gl=ID&ceid=ID:id",
    "Lifestyle & Fashion":"https://news.google.com/rss/search?q=lifestyle+fashion+Indonesia+viral&hl=id&gl=ID&ceid=ID:id",
    "Health & Fitness":  "https://news.google.com/rss/search?q=kesehatan+fitness+wellness+Indonesia&hl=id&gl=ID&ceid=ID:id",
    "Food & Kuliner":    "https://news.google.com/rss/search?q=kuliner+makanan+viral+Indonesia&hl=id&gl=ID&ceid=ID:id",
    "Travel & Wisata":   "https://news.google.com/rss/search?q=wisata+travel+destinasi+Indonesia&hl=id&gl=ID&ceid=ID:id",
    "Bisnis & Startup":  "https://news.google.com/rss/search?q=startup+bisnis+UMKM+Indonesia&hl=id&gl=ID&ceid=ID:id",
    "Pendidikan":        "https://news.google.com/rss/search?q=edukasi+belajar+online+Indonesia&hl=id&gl=ID&ceid=ID:id",
    "Entertainment":     "https://news.google.com/rss/search?q=hiburan+viral+entertainment+Indonesia&hl=id&gl=ID&ceid=ID:id",
    "Otomotif":          "https://news.google.com/rss/search?q=otomotif+mobil+motor+Indonesia&hl=id&gl=ID&ceid=ID:id",
    "Parenting & Keluarga": "https://news.google.com/rss/search?q=parenting+keluarga+anak+Indonesia&hl=id&gl=ID&ceid=ID:id",
}

# ─────────────────────────────────────────────
# KUESIONER Q&A WIZARD
# ─────────────────────────────────────────────

QUESTIONS: list[dict] = [
    {
        "id": "interest",
        "step": 1,
        "title": "Apa yang paling kamu sukai atau minati?",
        "subtitle": "Pilih satu atau lebih — ini fondasi niche-mu",
        "type": "multi",
        "options": [
            "Teknologi & AI", "Gaming", "Lifestyle & Fashion", "Kesehatan & Fitness",
            "Finance & Investasi", "Travel", "Food & Kuliner", "Pendidikan & Tutorial",
            "Hiburan & Humor", "Musik & Seni", "Olahraga", "Parenting",
            "Otomotif", "Bisnis & Startup", "Politik & Sosial",
        ],
    },
    {
        "id": "skill",
        "step": 2,
        "title": "Apa kelebihan atau keahlianmu?",
        "subtitle": "Jujur dengan dirimu — ini penting untuk hasil yang akurat",
        "type": "multi",
        "options": [
            "Bisa berbicara & presentasi dengan baik",
            "Suka menulis & storytelling",
            "Jago edit video & visual",
            "Punya pengetahuan teknis mendalam di suatu bidang",
            "Bisa mengajar & menjelaskan hal kompleks",
            "Kreatif & estetik",
            "Analitis & suka riset",
            "Humor & menghibur orang",
            "Punya pengalaman kerja profesional di industri tertentu",
            "Koneksi & networking luas",
        ],
    },
    {
        "id": "time",
        "step": 3,
        "title": "Berapa waktu yang bisa kamu alokasikan per minggu?",
        "subtitle": "Untuk membuat konten, editing, dan promosi",
        "type": "single",
        "options": [
            "1–3 jam (sangat sambilan)",
            "4–7 jam (sambil kerja / kuliah)",
            "8–15 jam (semi-serius)",
            "16–30 jam (serius)",
            "30+ jam (full-time)",
        ],
    },
    {
        "id": "goal",
        "step": 4,
        "title": "Apa tujuan utamamu sebagai content creator?",
        "subtitle": "Boleh pilih lebih dari satu",
        "type": "multi",
        "options": [
            "Penghasilan dari brand deal / sponsorship",
            "Affiliate marketing (komisi dari produk)",
            "Jual produk atau kursus sendiri",
            "AdSense / TikTok Creator Fund",
            "Bangun personal brand untuk karir",
            "Grow komunitas yang loyal",
            "Sekadar hobi / ekspresi diri",
        ],
    },
    {
        "id": "platform",
        "step": 5,
        "title": "Platform mana yang ingin kamu fokuskan?",
        "subtitle": "Pilih yang paling ingin dikuasai",
        "type": "multi",
        "options": [
            "TikTok",
            "Instagram Reels",
            "YouTube Shorts",
            "YouTube (video panjang)",
            "Podcast",
            "Blog / Newsletter",
        ],
    },
    {
        "id": "style",
        "step": 6,
        "title": "Gaya konten yang paling natural buatmu?",
        "subtitle": "Pilih satu yang paling jujur mencerminkan dirimu",
        "type": "single",
        "options": [
            "Edukasi & tutorial (mengajarkan sesuatu step by step)",
            "Entertainment & humor (menghibur, relatable)",
            "Inspirasi & motivasi (membakar semangat)",
            "Review & rekomendasi (produk / tempat / film)",
            "News & update (bahas berita & tren terkini)",
            "Vlog & behind the scenes (kehidupan sehari-hari)",
            "Opini & diskusi (bahas isu dengan sudut pandangmu)",
        ],
    },
]


# ─────────────────────────────────────────────
# TRENDING FETCHER
# ─────────────────────────────────────────────

_trend_cache: dict[str, dict] = {}
TREND_CACHE_TTL = 20 * 60  # 20 menit


def _fetch_trend_feed(url: str, limit: int = 10) -> list[dict]:
    try:
        feed = feedparser.parse(url)
        articles = []
        for entry in feed.entries[:limit]:
            summary = re.sub(r"<[^>]+>", "", entry.get("summary", "")).strip()
            summary = summary[:200] + "..." if len(summary) > 200 else summary
            articles.append({
                "title":     entry.get("title", ""),
                "summary":   summary,
                "url":       entry.get("link", ""),
                "published": entry.get("published", ""),
            })
        return articles
    except Exception as e:
        print(f"[niche_analyzer] Error fetching feed: {e}")
        return []


def get_trending_topics(category: Optional[str] = None, limit: int = 10) -> dict:
    """
    Fetch artikel trending per kategori untuk riset niche.
    - category=None → semua kategori
    - category=nama  → satu kategori saja
    """
    if category and category in NICHE_TREND_FEEDS:
        feeds = {category: NICHE_TREND_FEEDS[category]}
    else:
        feeds = NICHE_TREND_FEEDS

    result: dict[str, list] = {}
    for cat, url in feeds.items():
        key = f"trend_{cat}"
        if key in _trend_cache and (time.time() - _trend_cache[key]["ts"]) < TREND_CACHE_TTL:
            result[cat] = _trend_cache[key]["data"]
            continue
        articles = _fetch_trend_feed(url, limit=limit)
        _trend_cache[key] = {"data": articles, "ts": time.time()}
        result[cat] = articles

    return result


# ─────────────────────────────────────────────
# PROMPT BUILDERS
# ─────────────────────────────────────────────

_Q_TITLES = {q["id"]: q["title"] for q in QUESTIONS}

NICHE_SYSTEM = (
    "Kamu adalah konsultan niche content creator berpengalaman yang fokus pada pasar Indonesia. "
    "Kamu memberikan rekomendasi yang spesifik, actionable, dan realistis. "
    "Gunakan Bahasa Indonesia yang natural dan engaging."
)


def _build_qa_prompt(answers: dict) -> str:
    lines = []
    for qid, qtitle in _Q_TITLES.items():
        val = answers.get(qid, [])
        val_str = ", ".join(val) if isinstance(val, list) else str(val)
        if val_str:
            lines.append(f"- {qtitle}: {val_str}")

    answers_block = "\n".join(lines) if lines else "(tidak ada jawaban)"

    return f"""Seorang calon content creator Indonesia mengisi kuesioner berikut:

{answers_block}

Berdasarkan data di atas, rekomendasikan **5 niche konten** yang paling cocok.

Format WAJIB untuk setiap niche:

## NICHE [N]: [Nama Niche Spesifik — bukan terlalu broad]

**Kenapa cocok:** [1-2 kalimat berdasarkan jawaban di atas]
**Tingkat kompetisi:** [Rendah / Sedang / Tinggi] — [konteks spesifik di Indonesia]
**Potensi monetisasi:** [Rendah / Sedang / Tinggi / Sangat Tinggi] — [cara konkret menghasilkan uang]
**Tren saat ini:** [apakah sedang naik / stabil / stagnan di Indonesia?]

**3 ide konten pertama yang bisa langsung dibuat:**
1. [judul video / konten konkret]
2. [judul video / konten konkret]
3. [judul video / konten konkret]

**Hashtag utama:** #xxx #xxx #xxx #xxx #xxx

---

[ulangi untuk NICHE 2 sampai 5]

Terakhir, tambahkan:

## REKOMENDASI UTAMA
Niche **[nama]** adalah pilihan terbaik karena [alasan singkat berdasarkan jawaban].
"""


def _build_trend_prompt(topics: list[str], category: str) -> str:
    topics_block = "\n".join(f"- {t}" for t in topics[:20])
    ctx = f" di kategori **{category}**" if category else ""

    return f"""Berikut topik-topik yang sedang trending{ctx} di Indonesia:

{topics_block}

Analisis tren ini dan identifikasi peluang niche untuk content creator Indonesia.

## ANALISIS TREN
[Apa pola atau tema besar yang terlihat? Apa yang sedang hot?]

## PELUANG NICHE

Untuk setiap niche yang kamu identifikasi (minimal 3, maksimal 5):

### NICHE: [Nama Niche]
**Mengapa peluang bagus sekarang:** [kaitkan langsung dengan topik trending di atas]
**Target audiens:** [deskripsi spesifik]
**Durasi tren:** [jangka pendek / menengah / panjang — berikan alasan]
**Ide konten dari tren ini:**
1. [konten konkret yang bisa dibuat sekarang]
2. [konten konkret]
3. [konten konkret]

---

## KESIMPULAN
Niche mana yang paling menjanjikan dan kenapa (kaitkan dengan kondisi konten kreator Indonesia saat ini).
"""


# ─────────────────────────────────────────────
# GENERATORS (streaming)
# ─────────────────────────────────────────────

def _stream_ollama(system: str, user: str, model: str) -> Generator[str, None, None]:
    try:
        stream = ollama.chat(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            stream=True,
        )
        for chunk in stream:
            content = chunk.get("message", {}).get("content", "")
            if content:
                yield content
    except Exception as e:
        yield f"\n\n**[ERROR Ollama]** `{str(e)}`\n"
        yield "Pastikan Ollama sudah berjalan: `ollama serve`\n"


def _stream_any_backend(system: str, user: str) -> Generator[str, None, None]:
    from agent import BackendManager
    manager = BackendManager.instance()

    if manager.active_backend_type == "ollama":
        yield from _stream_ollama(system, user, manager._ollama.model)
    else:
        backend = manager.get_backend()
        if hasattr(backend, "chat_simple"):
            text = backend.chat_simple(system, user)
            yield text or ""
        else:
            yield "Backend tidak tersedia."


def generate_niche_analysis_stream(answers: dict) -> Generator[str, None, None]:
    """Stream rekomendasi niche berdasarkan jawaban Q&A."""
    yield from _stream_any_backend(NICHE_SYSTEM, _build_qa_prompt(answers))


def generate_trending_analysis_stream(
    topics: list[str], category: str = ""
) -> Generator[str, None, None]:
    """Stream analisis peluang niche dari topik trending."""
    yield from _stream_any_backend(NICHE_SYSTEM, _build_trend_prompt(topics, category))
