from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from contextlib import asynccontextmanager
import asyncio
import concurrent.futures
import os
from typing import Optional

from news_fetcher import get_news_and_save, get_cache_age_minutes
from agent import generate_content_stream, get_full_status, BackendManager, AIRLLM_PRESETS
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
    model: str = "gemma3"


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
async def fetch_news(refresh: bool = Query(default=False)):
    articles = await get_news_and_save(force_refresh=refresh)
    return {
        "articles": articles,
        "total": len(articles),
        "cache_age_minutes": get_cache_age_minutes(),
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
    platform: str = "tiktok"
    output_types: list[str] = ["ideas", "hook", "script", "caption"]


@app.post("/api/generate")
async def generate_content(req: GenerateRequest):
    """
    Generate konten dari berita menggunakan backend aktif (Ollama atau AirLLM).
    Hasil streaming dikirim ke client, lalu disimpan ke DB setelah selesai.
    """
    active_backend = BackendManager.instance().active_backend_type

    async def event_stream():
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            chunks = await loop.run_in_executor(
                pool,
                lambda: list(
                    generate_content_stream(
                        req.news_title,
                        req.news_summary,
                        req.platform,
                        req.output_types,
                    )
                ),
            )

        full_result = "".join(chunks)

        try:
            saved_id = await db.save_generated_content(
                news_title=req.news_title,
                news_summary=req.news_summary,
                platform=req.platform,
                output_types=req.output_types,
                result=full_result,
                news_url=req.news_url,
            )
            print(f"[DB] Content saved: id={saved_id}, backend={active_backend}")
        except Exception as e:
            print(f"[DB] Error saving: {e}")

        for chunk in chunks:
            yield chunk
            await asyncio.sleep(0)

    return StreamingResponse(event_stream(), media_type="text/plain; charset=utf-8")


# ─────────────────────────────────────────────
# HISTORY
# ─────────────────────────────────────────────

@app.get("/api/history")
async def get_history(
    limit: int = Query(default=50, le=200),
    platform: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
):
    items = await db.get_history(limit=limit, platform=platform, search=search)
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
