# 🤖 AI Content Agent

Agent AI lokal untuk membantu content creator TikTok, Instagram Reels, dan YouTube Shorts membuat konten teknologi & AI secara otomatis.

**Powered by:** Ollama + Gemma3 (lokal, gratis, privat)

---

## Fitur

- **📰 Berita Terkini** — Ambil headline AI/tech terbaru dari 5 sumber RSS otomatis (TechCrunch, The Verge, Wired, MIT Tech Review, Google News)
- **💡 Ide Konten** — 3 angle/sudut pandang berbeda untuk setiap berita
- **🎣 Hook Pembuka** — 3 variasi hook yang bikin penonton stop scroll
- **📝 Script Video** — Script lengkap siap pakai untuk video 30-60 detik
- **📱 Caption + Hashtag** — Caption + 15-20 hashtag relevan campuran Indonesia & Inggris
- **🔄 Regenerate** — Minta variasi berbeda kapanpun
- **Cache berita** — Data berita di-cache 30 menit, hemat bandwidth

---

## Prasyarat

1. **Python 3.10+** — [python.org](https://python.org)
2. **Ollama** — [ollama.com](https://ollama.com) (download & install)
3. **Model Gemma3** — Pull via Ollama

---

## Cara Setup & Menjalankan

### 1. Install Ollama & Download Model

```bash
# Install Ollama dari https://ollama.com/download
# Lalu pull model gemma3:
ollama pull gemma3
```

> Gemma3 ukurannya sekitar 3-5 GB tergantung varian. Untuk PC dengan RAM 8GB+ sudah cukup.

### 2. Clone / Download Project

```bash
cd ai-content-agent
```

### 3. Install Dependensi Python

```bash
cd backend
pip install -r requirements.txt
```

### 4. Jalankan Ollama (jika belum berjalan)

```bash
ollama serve
```

### 5. Jalankan Backend

```bash
# Di dalam folder backend/
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 6. Buka Browser

Buka: **http://localhost:8000**

---

## Struktur Project

```
ai-content-agent/
├── backend/
│   ├── main.py          # FastAPI server & routes
│   ├── agent.py         # Ollama integration + prompt templates
│   ├── news_fetcher.py  # RSS aggregator dengan cache 30 menit
│   └── requirements.txt
├── frontend/
│   └── index.html       # Web UI (Tailwind CSS + Alpine.js)
└── README.md
```

---

## Cara Pakai

1. **Pilih Berita** — Di tab "Berita", klik berita yang menarik dan klik tombol "Pilih"
2. **Atau Tulis Manual** — Di tab "Generate", ketik judul dan ringkasan berita sendiri
3. **Pilih Platform** — TikTok, Instagram, atau YouTube Shorts
4. **Pilih Output** — Centang kombinasi: Ide Konten, Hook, Script, Caption
5. **Klik Generate** — Tunggu 20-40 detik, Gemma3 akan membuat konten
6. **Salin & Gunakan** — Klik "Salin Semua" atau copy bagian tertentu

---

## API Endpoints

| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| GET | `/api/status` | Status koneksi Ollama & cache |
| GET | `/api/news?refresh=false` | Ambil berita (gunakan `refresh=true` untuk paksa refresh) |
| POST | `/api/generate` | Generate konten dari berita |

### Contoh Request Generate

```json
POST /api/generate
{
  "news_title": "OpenAI rilis GPT-5 dengan kemampuan reasoning baru",
  "news_summary": "OpenAI mengumumkan GPT-5 yang diklaim 10x lebih cerdas...",
  "platform": "tiktok",
  "output_types": ["ideas", "hook", "script", "caption"]
}
```

---

## Troubleshooting

**Ollama Offline (merah di header)**
- Pastikan Ollama sudah diinstall dan jalankan `ollama serve`

**Model tidak ditemukan**
- Jalankan `ollama pull gemma3`

**Berita tidak muncul**
- Pastikan koneksi internet aktif
- Klik tombol "Refresh"
- Beberapa RSS feed mungkin diblokir oleh jaringan tertentu

**Generate lambat**
- Normal untuk model lokal, butuh 20-60 detik tergantung spesifikasi PC
- CPU: mungkin butuh hingga 2-3 menit
- GPU (NVIDIA/AMD): jauh lebih cepat

---

## Sumber Berita RSS

| Sumber | URL |
|--------|-----|
| TechCrunch AI | techcrunch.com/category/artificial-intelligence |
| The Verge AI | theverge.com/ai-artificial-intelligence |
| MIT Technology Review | technologyreview.com |
| Wired AI | wired.com/tag/ai |
| Google News AI (ID) | news.google.com (bahasa Indonesia) |
