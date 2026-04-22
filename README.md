# 🤖 AI Content Agent

Agent AI lokal untuk membantu content creator TikTok, Instagram Reels, dan YouTube Shorts membuat konten teknologi & AI secara otomatis.

**Powered by:** Ollama + Gemma3 **atau** AirLLM (70B di GPU 4GB) — pilih sesuai kebutuhan.

---

## Fitur

- **📰 Berita Terkini** — Ambil headline AI/tech terbaru dari 5 sumber RSS otomatis (TechCrunch, The Verge, Wired, MIT Tech Review, Google News)
- **💡 Ide Konten** — 3 angle/sudut pandang berbeda untuk setiap berita
- **🎣 Hook Pembuka** — 3 variasi hook yang bikin penonton stop scroll
- **📝 Script Video** — Script lengkap siap pakai untuk video 30-60 detik
- **📱 Caption + Hashtag** — Caption + 15-20 hashtag relevan campuran Indonesia & Inggris
- **🔄 Regenerate** — Minta variasi berbeda kapanpun
- **🗄 Database SQLite** — Semua berita yang di-scrape dan konten yang di-generate tersimpan otomatis
- **🗂 Riwayat Generate** — Lihat, salin, pakai ulang, atau hapus konten yang pernah dibuat
- **🚀 Dual Backend** — Switch antara Ollama (cepat) dan AirLLM (70B, kualitas tinggi) tanpa restart

---

## Prasyarat

1. **Python 3.10+** — [python.org](https://python.org)
2. **Salah satu backend AI:**
   - **Ollama** (direkomendasikan untuk pemula) — [ollama.com](https://ollama.com)
   - **AirLLM** (untuk model 70B di GPU 4GB) — install via pip

---

## Cara Setup & Menjalankan

### 1. Clone Repository

```bash
git clone https://github.com/alvnfaiz/ai-agent-content.git
cd ai-agent-content
```

### 2. Install Dependensi Python

```bash
cd backend
pip install -r requirements.txt
```

> Untuk AirLLM (opsional), install tambahan:
> ```bash
> pip install airllm transformers torch bitsandbytes
> ```

### 3. Setup Backend AI

#### Opsi A — Ollama (cepat, mudah)

```bash
# Install Ollama dari https://ollama.com/download
ollama pull gemma3
ollama serve
```

#### Opsi B — AirLLM (70B model, GPU 4GB)

Tidak perlu Ollama. Model akan di-download otomatis dari HuggingFace saat pertama kali generate. Pastikan sudah install dependensi di langkah 2.

### 4. Jalankan Backend

```bash
# Di dalam folder backend/
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Database SQLite akan dibuat otomatis di `data/content_agent.db` saat server pertama kali dijalankan.

### 5. Buka Browser

Buka: **http://localhost:8000**

---

## Struktur Project

```
ai-content-agent/
├── backend/
│   ├── main.py          # FastAPI server & semua routes
│   ├── agent.py         # OllamaBackend, AirLLMBackend, BackendManager
│   ├── database.py      # SQLite init, CRUD news & generated contents
│   ├── news_fetcher.py  # RSS aggregator + cache 30 menit + simpan ke DB
│   └── requirements.txt
├── frontend/
│   └── index.html       # Web UI (Tailwind CSS + Alpine.js)
├── data/
│   └── content_agent.db # SQLite database (auto-created)
└── README.md
```

---

## Cara Pakai

1. **Pilih Berita** — Di tab "📰 Berita", klik berita yang menarik dan klik tombol "Pilih". Berita otomatis tersimpan ke database.
2. **Atau Tulis Manual** — Di tab "✨ Generate", ketik judul dan ringkasan berita sendiri
3. **Pilih Platform** — TikTok, Instagram, atau YouTube Shorts
4. **Pilih Output** — Ide Konten, Hook, Script, Caption (bisa kombinasi)
5. **Pilih Backend** — Klik badge backend di header untuk switch Ollama/AirLLM
6. **Klik Generate** — Hasil otomatis tersimpan ke database setelah selesai
7. **Lihat Riwayat** — Tab "🗂 Riwayat" untuk akses semua konten yang pernah dibuat

---

## Backend: Ollama vs AirLLM

| | Ollama + Gemma3 | AirLLM (70B) |
|---|---|---|
| **Setup** | `ollama pull gemma3` | `pip install airllm` |
| **Kecepatan** | 10-30 detik | 1-5 menit |
| **Kualitas** | Bagus | Jauh lebih baik |
| **VRAM** | Tidak butuh GPU | GPU 4GB cukup |
| **Disk** | ~2-5 GB | 15-140 GB |
| **Model pilihan** | gemma3, llama3, dll | Llama3-70B, Qwen2.5-72B, dll |

### Model AirLLM yang Tersedia

| Preset | Model | Disk | Keterangan |
|---|---|---|---|
| `llama3-8b` | Meta Llama3 8B Instruct | ~16 GB | Ringan, cepat |
| `llama3-70b` | Meta Llama3 70B Instruct | ~140 GB | Kualitas tertinggi |
| `mistral-7b` | Mistral 7B Instruct v0.2 | ~14 GB | Balanced |
| `qwen2.5-7b` | Qwen2.5 7B Instruct | ~15 GB | Bagus untuk bahasa Indonesia |
| `qwen2.5-72b` | Qwen2.5 72B Instruct | ~145 GB | Sangat powerful |

> Model Llama3 membutuhkan HuggingFace token (model gated). Buat di [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens).

---

## API Endpoints

| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| GET | `/api/status` | Status backend, cache, dan statistik DB |
| GET | `/api/news?refresh=false` | Fetch berita dari RSS + simpan ke DB |
| GET | `/api/news/saved` | Ambil berita dari database (filter + search) |
| POST | `/api/generate` | Generate konten + simpan ke DB |
| GET | `/api/history` | Riwayat konten yang di-generate |
| GET | `/api/history/{id}` | Detail satu item riwayat |
| DELETE | `/api/history/{id}` | Hapus item riwayat |
| GET | `/api/backend` | Status semua backend |
| POST | `/api/backend/ollama` | Switch ke backend Ollama |
| POST | `/api/backend/airllm` | Switch ke backend AirLLM |
| POST | `/api/backend/airllm/preload` | Preload model AirLLM |

---

## Database

Data disimpan otomatis di `data/content_agent.db` (SQLite). Dua tabel utama:

**`news_articles`** — hasil scraping RSS:
- source, title, summary, url (unique), published, fetched_at

**`generated_contents`** — hasil generate konten:
- news_title, news_summary, news_url, platform, output_types, result, created_at

---

## Troubleshooting

**Ollama Offline (merah di header)**
- Pastikan Ollama sudah diinstall dan jalankan `ollama serve`

**AirLLM: model tidak ter-load**
- Pastikan sudah install: `pip install airllm transformers torch`
- Untuk 4bit quantization: `pip install bitsandbytes`
- Cek log terminal untuk error detail

**Berita tidak muncul**
- Pastikan koneksi internet aktif dan klik "Refresh"
- Beberapa RSS feed mungkin diblokir oleh jaringan tertentu

**Generate lambat (AirLLM)**
- Normal — AirLLM load layer per layer dari disk
- Model 70B bisa butuh 2-5 menit per generate
- Gunakan compression `4bit` untuk 3x lebih cepat

---

## Sumber Berita RSS

| Sumber | URL |
|--------|-----|
| TechCrunch AI | techcrunch.com/category/artificial-intelligence |
| The Verge AI | theverge.com/ai-artificial-intelligence |
| MIT Technology Review | technologyreview.com |
| Wired AI | wired.com/tag/ai |
| Google News AI (ID) | news.google.com (bahasa Indonesia) |
