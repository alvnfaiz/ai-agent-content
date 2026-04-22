# AI Content Agent

Agent AI lokal untuk membantu kreator (TikTok, Instagram Reels, YouTube Shorts) membuat konten teknologi & AI, dengan alur **Berita → Generate**, **Analisa Niche**, **Creator (agen)**, **Agency**, dan **Ide konten** (`/content`).

**Backend AI:** Ollama + Gemma (atau model lain) **atau** AirLLM (model besar di GPU 4GB) — dipilih lewat panel di header.

---

## Fitur

### Utama (halaman Beranda `/`)
- **Berita terkini** — Headline AI/tech dari beberapa sumber RSS (dengan filter kata kunci opsional)
- **Generate** — Dari berita pilih atau input manual: ide, hook, script, caption (multi platform)
- **Riwayat** — Konten yang tersimpan di database
- **Dual backend** — Beralih Ollama / AirLLM tanpa restart server

### Alur Niche & Creator
- **Analisa Niche** (`/niche.html`) — Kuesioner & analisis tren; hasil bisa diarahkan ke Creator
- **Creator Studio** (`/creator.html`) — Agen dengan teks niche, **keyword pencarian berita per agen** (tersimpan di DB, dipakai saat *Cari bahan konten*), scrape Google News RSS, lalu generate konten
- **Agency** (`/agency.html` atau `/agency`) — Daftar kreator/agen; pintasan ke ide konten per agen
- **Ide konten** (`/content` atau `/content.html`) — Generate hanya fokus ide, selaras niche agen (opsional memakai satu artikel scrape)

### Antarmuka
- **Header konsisten** di semua halaman: ringkasan statistik (md+), pemilihan **model (Ollama / AirLLM)**, **toggle terang/gelap**
- Aset bersama: `frontend/site-chrome.css`, `frontend/site-header.js` (disajikan lewat `/static/...`)

### Penyimpanan
- **SQLite** — Berita, konten tersimpan, agen creator, arsip niche, artikel hasil scrape per agen

---

## Prasyarat

1. **Python 3.10+** — [python.org](https://python.org)
2. **Salah satu backend AI:**
   - **Ollama** (praktis untuk sehari-hari) — [ollama.com](https://ollama.com)
   - **AirLLM** (model besar di GPU 4GB) — via pip (lihat bawah)

---

## Setup & menjalankan

### 1. Clone & dependensi

```bash
git clone <url-repo-anda> ai-content-agent
cd ai-content-agent/backend
pip install -r requirements.txt
```

Opsional (AirLLM):

```bash
pip install airllm transformers torch bitsandbytes
```

### 2. Ollama (opsi A)

```bash
ollama pull gemma3
ollama serve
```

### 3. Jalankan server

```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Database SQLite dibuat di `data/content_agent.db` (folder relatif ke root project). Kolom/migrasi tambahan diterapkan otomatis saat startup.

### 4. Buka browser

**http://localhost:8000** — Beranda. Gunakan header untuk ke **Niche**, **Creator**, **Agency**, **/content**.

---

## Struktur project

```
ai-content-agent/
├── backend/
│   ├── main.py            # FastAPI, route HTML & API
│   ├── agent.py           # Ollama / AirLLM, generate stream
│   ├── database.py      # SQLite, agen, niche, history
│   ├── news_fetcher.py  # RSS agregator & cache
│   ├── creator_scraper.py
│   ├── niche_analyzer.py
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── niche.html
│   ├── creator.html
│   ├── agency.html
│   ├── content.html
│   ├── site-chrome.css   # gaya header/panel (dipakai semua halaman)
│   └── site-header.js    # state backend + tema (mixin Alpine)
├── data/
│   └── content_agent.db  # dibuat otomatis
└── README.md
```

`main.py` memuat folder `frontend` sebagai static + route untuk setiap `*.html` utama.

---

## Cara pakai (ringkas)

| Halaman     | Tujuan |
|------------|--------|
| **Beranda** | Tab Berita / Generate / Riwayat; filter keyword; pilih backend di header |
| **Niche**  | Temukan niche, tren, arsimpan; handoff ke Creator |
| **Creator** | Buat/pilih **agen** → atur **keyword berita (simpan ke DB)** → *Cari bahan konten* → pilih artikel → generate |
| **Agency** | Lihat agen, buka `/content?agent=ID` untuk ide |
| **/content** | Pilih kreator, platform, lalu *Generate ide konten* |

- Keyword di Creator: isi lalu **Simpan**, atau lanjut **Cari bahan** — perubahan yang belum tersimpan akan disinkronkan otomatis sebelum scrape.
- **Tutup detail** di kartu agen mengembalikan tampilan ke daftar (form agen manual bisa muncul lagi jika belum ada draf Niche).

---

## Backend: Ollama vs AirLLM

| | Ollama | AirLLM (contoh 70B) |
|---|---|---|
| **Setup** | `ollama pull <model>` | `pip install airllm` + dependensi |
| **Kecepatan** | Cenderung lebih cepat | Bisa 1–5+ menit per proses |
| **VRAM** | Fleksibel | GPU 4GB memakai kuantisasi 4bit |
| **Pilihan** | Lewat panel: model Ollama | Preset + kompresi + token HF |

Model AirLLM yang tersedia dan ukuran disk mengikuti konfigurasi di `agent.py` / panel (preset contoh: Llama3, Qwen, Mistral, dll). Model *gated* membutuhkan token Hugging Face.

---

## API (referensi)

### Status & backend

| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| GET | `/api/status` | Ollama, cache, statistik DB, info backend aktif |
| GET | `/api/backend` | Detail backend |
| POST | `/api/backend/ollama` | Pindah ke Ollama (`model` di body) |
| POST | `/api/backend/airllm` | Pindah ke AirLLM (preset, compression, `hf_token` opsional) |
| POST | `/api/backend/airllm/preload` | Preload model AirLLM |

### Berita & generate

| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| GET | `/api/news` | Berita dari RSS (query: `refresh`, `source`, dll.) |
| GET | `/api/news/saved` | Berita dari DB |
| POST | `/api/generate` | Stream generate konten (boleh sertakan `creator_agent_id`) |
| POST | `/api/assist` | Endpoint bantuan (jika diaktifkan di UI) |
| GET | `/api/history` | Riwayat generate (`creator_agent_id` opsional) |
| GET | `/api/history/{id}` | Satu entri |
| DELETE | `/api/history/{id}` | Hapus |

### Niche

| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| GET | `/api/niche/questions` | Pertanyaan wizard |
| GET | `/api/niche/trending` | Topik tren |
| POST | `/api/niche/analyze` | Analisis stream (Q&A) |
| POST | `/api/niche/trend-analyze` | Analisis tren (stream) |
| POST | `/api/niche/saved` | Simpan hasil ke arsip |
| GET | `/api/niche/saved` | Daftar arsip |
| GET | `/api/niche/saved/{id}` | Satu item |
| DELETE | `/api/niche/saved/{id}` | Hapus |

### Creator (agen)

| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| POST | `/api/creator/agents` | Buat agen: `name`, `niche_text`, `source_type`, opsional `scrape_keywords` |
| GET | `/api/creator/agents` | Daftar agen |
| GET | `/api/creator/agents/{id}` | Detail (termasuk `scrape_keywords` sebagai array) |
| PATCH | `/api/creator/agents/{id}/keywords` | Simpan hanya keyword: body `{"scrape_keywords": ["..."]}` |
| DELETE | `/api/creator/agents/{id}` | Hapus agen |
| POST | `/api/creator/agents/{id}/scrape` | Ambil artikel (Google News RSS) memakai niche + keyword agen |
| GET | `/api/creator/agents/{id}/scrapes` | Artikel tersimpan untuk agen |
| GET | `/api/creator/agents/{id}/generations` | Riwayat generate untuk agen |

---

## Database (gambaran)

Tabel utama di `data/content_agent.db`:

- **`news_articles`** — Artikel dari RSS
- **`generated_contents`** — Hasil generate (kolom `creator_agent_id` opsional, menaut ke agen)
- **`creator_agents`** — `name`, `niche_text`, `source_type`, **`scrape_keywords`** (JSON array string), `created_at`
- **`creator_scrapes`** — Bahan berita per `agent_id`
- **`saved_niches`** — Arsip hasil analisa niche

---

## Troubleshooting

**Ollama offline (indikator di header merah / abu)**  
Pastikan Ollama terpasang dan proses `ollama serve` berjalan (jika memilih backend Ollama).

**AirLLM: model tidak termuat**  
Periksa instalasi `airllm`, `transformers`, `torch`, dan untuk kuantisasi: `bitsandbytes`. Cek log terminal.

**Berita tidak muncul**  
Cek jaringan; gunakan *Refresh* di tab Berita. Beberapa jaringan memblokir feed RSS.

**Generate lama (AirLLM)**  
Wajar untuk model besar; pertimbangkan preset lebih kecil atau Ollama untuk iterasi cepat.

**Keyword Creator tidak memengaruhi pencarian**  
Pastikan keyword sudah tersimpan (tombol Simpan, atau *Cari bahan* setelah edit — sinkronisasi dijalankan sebelum scrape).

---

## Sumber RSS (Beranda)

Mencakup antara lain: TechCrunch, The Verge, MIT Technology Review, Wired, Google News (konfigurasi di `news_fetcher` / backend).

---

## Lisensi

Sesuai repositori (tambahkan file LICENSE jika belum).
