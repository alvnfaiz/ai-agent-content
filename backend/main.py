from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager
import asyncio
import concurrent.futures
import os
from typing import Optional

from news_fetcher import get_news_and_save, get_cache_age_minutes, get_all_source_names
from agent import generate_content_stream, generate_assist, get_full_status, BackendManager, AIRLLM_PRESETS
from niche_analyzer import (
    QUESTIONS as NICHE_QUESTIONS,
    get_trending_topics,
    generate_niche_analysis_stream,
    generate_trending_analysis_stream,
)
from creator_scraper import scrape_for_niche
import database as db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    yield


app = FastAPI(title="AI Content Agent", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


# ─────────────────────────────────────────────
# FRONTEND
# ─────────────────────────────────────────────

@app.get("/")
async def serve_frontend():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "AI Content Agent API is running"}


@app.get("/niche.html")
async def serve_niche():
    niche_path = os.path.join(FRONTEND_DIR, "niche.html")
    if os.path.exists(niche_path):
        return FileResponse(niche_path)
    return {"message": "niche.html not found"}


@app.get("/creator.html")
async def serve_creator():
    creator_path = os.path.join(FRONTEND_DIR, "creator.html")
    if os.path.exists(creator_path):
        return FileResponse(creator_path)
    return {"message": "creator.html not found"}


def _file_if_exists(name: str):
    p = os.path.join(FRONTEND_DIR, name)
    if os.path.exists(p):
        return FileResponse(p)
    return {"message": f"{name} not found"}


@app.get("/agency")
@app.get("/agency.html")
async def serve_agency():
    return _file_if_exists("agency.html")


@app.get("/content")
@app.get("/content.html")
async def serve_content_page():
    return _file_if_exists("content.html")


# ─────────────────────────────────────────────
# STATUS
# ─────────────────────────────────────────────

@app.get("/api/status")
async def get_status():
    backend_status = get_full_status()
    news_stats = await db.get_news_stats()
    gen_stats = await db.get_generate_stats()
    return {
        "ollama": backend_status["ollama"],
        "backend": backend_status,
        "cache_age_minutes": get_cache_age_minutes(),
        "db": {
            "news": news_stats,
            "generated": gen_stats,
        },
    }


# ─────────────────────────────────────────────
# BACKEND CONFIG
# ─────────────────────────────────────────────

@app.get("/api/backend")
async def get_backend_status():
    """Ambil status lengkap semua backend dan backend aktif."""
    status = get_full_status()
    return status


class SetOllamaRequest(BaseModel):
    model: str = "gemma4:latest"


class SetAirLLMRequest(BaseModel):
    preset: str = "llama3-8b"
    compression: str = "4bit"
    hf_token: str = ""
    max_new_tokens: int = 1024


@app.post("/api/backend/ollama")
async def set_backend_ollama(req: SetOllamaRequest):
    """Switch ke backend Ollama."""
    result = BackendManager.instance().set_ollama(model=req.model)
    return {"success": True, **result}


@app.post("/api/backend/airllm")
async def set_backend_airllm(req: SetAirLLMRequest):
    """
    Switch ke backend AirLLM.
    Model akan di-load pertama kali saat generate dipanggil (bisa butuh beberapa menit).
    """
    if req.preset not in AIRLLM_PRESETS:
        raise HTTPException(
            status_code=400,
            detail=f"Preset tidak valid. Pilihan: {list(AIRLLM_PRESETS.keys())}",
        )
    result = BackendManager.instance().set_airllm(
        preset=req.preset,
        compression=req.compression,
        hf_token=req.hf_token,
        max_new_tokens=req.max_new_tokens,
    )
    preset_info = AIRLLM_PRESETS[req.preset]
    return {
        "success": True,
        **result,
        "info": preset_info,
        "note": "Model akan di-download & di-load saat pertama kali generate. Bisa butuh beberapa menit.",
    }


@app.post("/api/backend/airllm/preload")
async def preload_airllm_model():
    """
    Trigger load model AirLLM di background tanpa harus generate dulu.
    Berguna untuk warm-up sebelum dipakai.
    """
    manager = BackendManager.instance()
    if manager.active_backend_type != "airllm" or manager._airllm is None:
        raise HTTPException(status_code=400, detail="Backend AirLLM belum diset. Panggil POST /api/backend/airllm dulu.")

    airllm_backend = manager._airllm

    def _load():
        return airllm_backend.load_model()

    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        success = await loop.run_in_executor(pool, _load)

    return {
        "success": success,
        "model_loaded": airllm_backend._model is not None,
        "error": airllm_backend._load_error or None,
    }


# ─────────────────────────────────────────────
# NEWS
# ─────────────────────────────────────────────

@app.get("/api/news")
async def fetch_news(
    refresh: bool = Query(default=False),
    source: Optional[str] = Query(default=None),
):
    """
    Ambil berita dari RSS feeds.
    - source kosong → semua sumber, 6 per sumber
    - source diisi  → satu sumber, 30 artikel terbaru
    """
    articles = await get_news_and_save(source=source, force_refresh=refresh)
    return {
        "articles": articles,
        "total": len(articles),
        "cache_age_minutes": get_cache_age_minutes(source=source),
        "source": source,
        "all_sources": get_all_source_names(),
    }


@app.get("/api/news/saved")
async def get_saved_news(
    limit: int = Query(default=100, le=500),
    source: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
):
    articles = await db.get_saved_news(limit=limit, source=source, search=search)
    sources = await db.get_news_sources()
    return {"articles": articles, "total": len(articles), "sources": sources}


# ─────────────────────────────────────────────
# GENERATE
# ─────────────────────────────────────────────

class GenerateRequest(BaseModel):
    news_title: str
    news_summary: str
    news_url: str = ""
    platforms: list[str] = ["tiktok"]
    output_types: list[str] = ["ideas", "hook", "script", "caption"]
    creator_agent_id: Optional[int] = None


@app.post("/api/generate")
async def generate_content(req: GenerateRequest):
    """
    Generate konten dari berita menggunakan backend aktif (Ollama atau AirLLM).
    Mendukung multiple platform sekaligus.
    Hasil streaming dikirim ke client, lalu disimpan ke DB setelah selesai.
    """
    active_backend = BackendManager.instance().active_backend_type
    platforms = req.platforms if req.platforms else ["tiktok"]

    async def event_stream():
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            chunks = await loop.run_in_executor(
                pool,
                lambda: list(
                    generate_content_stream(
                        req.news_title,
                        req.news_summary,
                        platforms,
                        req.output_types,
                    )
                ),
            )

        full_result = "".join(chunks)

        try:
            saved_id = await db.save_generated_content(
                news_title=req.news_title,
                news_summary=req.news_summary,
                platform=",".join(platforms),
                output_types=req.output_types,
                result=full_result,
                news_url=req.news_url,
                creator_agent_id=req.creator_agent_id,
            )
            print(f"[DB] Content saved: id={saved_id}, platforms={platforms}, backend={active_backend}")
        except Exception as e:
            print(f"[DB] Error saving: {e}")

        for chunk in chunks:
            yield chunk
            await asyncio.sleep(0)

    return StreamingResponse(event_stream(), media_type="text/plain; charset=utf-8")


# ─────────────────────────────────────────────
# ASSIST (AI-assisted writing)
# ─────────────────────────────────────────────

class AssistRequest(BaseModel):
    news_title: str
    news_summary: str


@app.post("/api/assist")
async def assist_writing(req: AssistRequest):
    """
    Tulis ulang judul dan ringkasan menggunakan AI.
    Return: {"title": str, "summary": str}
    """
    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        result = await loop.run_in_executor(
            pool,
            lambda: generate_assist(req.news_title, req.news_summary),
        )
    return result


# ─────────────────────────────────────────────
# HISTORY
# ─────────────────────────────────────────────

@app.get("/api/history")
async def get_history(
    limit: int = Query(default=50, le=200),
    platform: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    creator_agent_id: Optional[int] = Query(default=None),
):
    items = await db.get_history(
        limit=limit, platform=platform, search=search, creator_agent_id=creator_agent_id
    )
    return {"items": items, "total": len(items)}


@app.get("/api/history/{item_id}")
async def get_history_item(item_id: int):
    item = await db.get_history_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item tidak ditemukan")
    return item


@app.delete("/api/history/{item_id}")
async def delete_history_item(item_id: int):
    deleted = await db.delete_history_item(item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Item tidak ditemukan")
    return {"message": "Berhasil dihapus", "id": item_id}


# ─────────────────────────────────────────────
# NICHE ANALYZER
# ─────────────────────────────────────────────

class NicheAnalyzeRequest(BaseModel):
    answers: dict  # {question_id: list[str] | str}


class NicheTrendAnalyzeRequest(BaseModel):
    topics: list[str]
    category: str = ""


@app.get("/api/niche/questions")
async def get_niche_questions():
    return {"questions": NICHE_QUESTIONS}


@app.get("/api/niche/trending")
async def niche_trending(
    category: Optional[str] = Query(default=None),
    limit: int = Query(default=10, le=30),
):
    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        data = await loop.run_in_executor(
            pool,
            lambda: get_trending_topics(category=category, limit=limit),
        )
    return data


@app.post("/api/niche/analyze")
async def niche_analyze(req: NicheAnalyzeRequest):
    """Stream rekomendasi niche berdasarkan jawaban Q&A."""
    async def event_stream():
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            chunks = await loop.run_in_executor(
                pool,
                lambda: list(generate_niche_analysis_stream(req.answers)),
            )
        for chunk in chunks:
            yield chunk
            await asyncio.sleep(0)

    return StreamingResponse(event_stream(), media_type="text/plain; charset=utf-8")


@app.post("/api/niche/trend-analyze")
async def niche_trend_analyze(req: NicheTrendAnalyzeRequest):
    """Stream analisis peluang niche dari topik trending yang dipilih."""
    async def event_stream():
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            chunks = await loop.run_in_executor(
                pool,
                lambda: list(generate_trending_analysis_stream(req.topics, req.category)),
            )
        for chunk in chunks:
            yield chunk
            await asyncio.sleep(0)

    return StreamingResponse(event_stream(), media_type="text/plain; charset=utf-8")


class SaveNicheRequest(BaseModel):
    niche_text: str
    source_type: str = "qa"
    label: str = ""


@app.post("/api/niche/saved")
async def save_niche_item(req: SaveNicheRequest):
    """Simpan hasil analisis niche ke arsip."""
    if not req.niche_text.strip():
        raise HTTPException(status_code=400, detail="niche_text tidak boleh kosong")
    st = req.source_type if req.source_type in ("qa", "trend") else "qa"
    niche_id = await db.save_niche(
        niche_text=req.niche_text.strip(),
        source_type=st,
        label=req.label.strip() or None,
    )
    return {"id": niche_id, "message": "Tersimpan"}


@app.get("/api/niche/saved")
async def list_saved_niches(limit: int = Query(default=100, le=200)):
    items = await db.list_saved_niches(limit=limit)
    total = await db.count_saved_niches()
    return {"items": items, "total": total}


@app.get("/api/niche/saved/{item_id}")
async def get_saved_niche_item(item_id: int):
    item = await db.get_saved_niche(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Tidak ditemukan")
    return item


@app.delete("/api/niche/saved/{item_id}")
async def delete_saved_niche_item(item_id: int):
    if not await db.delete_saved_niche(item_id):
        raise HTTPException(status_code=404, detail="Tidak ditemukan")
    return {"ok": True, "id": item_id}


# ─────────────────────────────────────────────
# CREATOR (agent dari niche + scrape + generate)
# ─────────────────────────────────────────────

class CreateCreatorAgentRequest(BaseModel):
    name: str
    niche_text: str
    source_type: str = "qa"
    scrape_keywords: Optional[list] = None


class UpdateCreatorScrapeKeywordsRequest(BaseModel):
    scrape_keywords: list = Field(default_factory=list)


@app.post("/api/creator/agents")
async def create_agent(req: CreateCreatorAgentRequest):
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="Nama wajib diisi")
    if not req.niche_text.strip():
        raise HTTPException(status_code=400, detail="Teks niche wajib diisi")
    st = req.source_type if req.source_type in ("qa", "trend") else "qa"
    agent_id = await db.create_creator_agent(
        name=req.name,
        niche_text=req.niche_text,
        source_type=st,
        scrape_keywords=req.scrape_keywords,
    )
    return {"id": agent_id, "name": req.name.strip(), "source_type": st}


@app.get("/api/creator/agents")
async def list_agents():
    return {"items": await db.list_creator_agents()}


@app.get("/api/creator/agents/{agent_id}")
async def get_agent(agent_id: int):
    agent = await db.get_creator_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent tidak ditemukan")
    agent["scrape_count"] = await db.count_scrapes_for_agent(agent_id)
    return agent


@app.patch("/api/creator/agents/{agent_id}/keywords")
async def update_agent_keywords(agent_id: int, req: UpdateCreatorScrapeKeywordsRequest):
    """Simpan keyword pencarian berita per agen (tersimpan di DB, dipakai saat Cari bahan)."""
    a = await db.get_creator_agent(agent_id)
    if not a:
        raise HTTPException(status_code=404, detail="Agent tidak ditemukan")
    ok = await db.update_creator_scrape_keywords(agent_id, req.scrape_keywords or [])
    if not ok:
        raise HTTPException(status_code=500, detail="Gagal menyimpan keyword")
    fresh = await db.get_creator_agent(agent_id)
    if fresh:
        fresh["scrape_count"] = await db.count_scrapes_for_agent(agent_id)
    return fresh


@app.delete("/api/creator/agents/{agent_id}")
async def remove_agent(agent_id: int):
    if not await db.delete_creator_agent(agent_id):
        raise HTTPException(status_code=404, detail="Agent tidak ditemukan")
    return {"ok": True, "id": agent_id}


@app.post("/api/creator/agents/{agent_id}/scrape")
async def run_scrape(agent_id: int):
    """Ambil bahan konten dari Google News (RSS) berdasarkan teks niche."""
    agent = await db.get_creator_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent tidak ditemukan")

    sk = agent.get("scrape_keywords") or []
    if not isinstance(sk, list):
        sk = []

    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        items = await loop.run_in_executor(
            pool,
            lambda: scrape_for_niche(
                agent["niche_text"],
                agent_name=agent["name"],
                extra_keywords=sk,
            ),
        )

    saved = await db.save_creator_scrapes(agent_id, items)
    return {
        "agent_id": agent_id,
        "fetched": len(items),
        "new_saved": saved,
    }


@app.get("/api/creator/agents/{agent_id}/scrapes")
async def list_scrapes(agent_id: int, limit: int = Query(default=50, le=200)):
    agent = await db.get_creator_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent tidak ditemukan")
    return {
        "items": await db.get_creator_scrapes(agent_id, limit=limit),
    }


@app.get("/api/creator/agents/{agent_id}/generations")
async def list_agent_generations(
    agent_id: int, limit: int = Query(default=30, le=100)
):
    """Riwayat konten yang di-generate untuk agent ini."""
    agent = await db.get_creator_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent tidak ditemukan")
    items = await db.get_history(limit=limit, creator_agent_id=agent_id)
    return {"items": items, "total": len(items)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
