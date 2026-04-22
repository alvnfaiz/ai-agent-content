"""
Agent module — dua backend tersedia:
  1. OllamaBackend  : cepat, jalankan model via Ollama (Gemma3, Llama3, dll)
  2. AirLLMBackend  : jalankan model HuggingFace 70B di GPU 4GB (layer-by-layer)

Pilih backend via BackendManager.set_backend().
"""

import threading
from typing import Generator

import ollama

# ─────────────────────────────────────────────
# PROMPT TEMPLATES
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """Kamu adalah asisten content creator spesialis teknologi & AI untuk platform TikTok, Instagram Reels, dan YouTube Shorts.

Tugasmu membantu membuat konten video pendek yang viral dan engaging berdasarkan berita teknologi terbaru.

Aturan penting:
- Selalu gunakan Bahasa Indonesia yang natural, gaul (tapi tidak berlebihan), dan mudah dipahami
- Konten harus cocok untuk audiens muda Indonesia (18-30 tahun) yang melek teknologi
- Gunakan gaya bercerita yang dramatis, memancing rasa penasaran, dan mudah dicerna
- Hindari istilah teknis yang terlalu rumit, tapi jangan terlalu menyederhanakan
- Setiap output harus langsung bisa digunakan tanpa perlu banyak edit"""

PLATFORM_NOTES = {
    "tiktok": "TikTok: gaya casual, energetik, pakai trending sounds reference, durasi 30-60 detik, hook super kuat di 3 detik pertama",
    "instagram": "Instagram Reels: estetis, informatif, bisa sedikit lebih formal dari TikTok, durasi 30-90 detik",
    "youtube": "YouTube Shorts: bisa lebih detail dan edukatif, durasi 45-60 detik, judul menarik penting",
}


def _build_user_prompt(news_title: str, news_summary: str, platform: str, output_types: list[str]) -> str:
    platform_note = PLATFORM_NOTES.get(platform, PLATFORM_NOTES["tiktok"])

    requested_outputs = []
    if "ideas" in output_types:
        requested_outputs.append(
            "## 💡 IDE KONTEN\n"
            "Berikan 3 angle/sudut pandang berbeda untuk membawakan berita ini sebagai konten video. "
            "Format: nomor + judul angle + 1 kalimat penjelasan singkat."
        )
    if "hook" in output_types:
        requested_outputs.append(
            "## 🎣 HOOK PEMBUKA (3-5 detik pertama)\n"
            "Berikan 3 variasi hook yang bikin penonton langsung stop scroll. "
            "Bisa berupa pertanyaan mengejutkan, fakta menggelitik, atau statement kontroversial."
        )
    if "script" in output_types:
        requested_outputs.append(
            "## 📝 SCRIPT VIDEO\n"
            "Tulis script lengkap untuk video 30-60 detik. Format:\n"
            "- [HOOK] kalimat pembuka\n"
            "- [KONTEN] isi utama (3-4 poin singkat)\n"
            "- [CTA] call to action penutup\n"
            "Tandai jeda/nafas dengan | dan emosi/ekspresi dengan (emosi)"
        )
    if "caption" in output_types:
        requested_outputs.append(
            "## 📱 CAPTION + HASHTAG\n"
            "Tulis caption yang menarik (2-3 kalimat) + 15-20 hashtag relevan. "
            "Campurkan hashtag besar dan niche. Sertakan hashtag Indonesia dan Inggris."
        )

    outputs_section = "\n\n".join(requested_outputs)

    return f"""Berikut adalah berita teknologi/AI terbaru yang akan dijadikan konten:

JUDUL BERITA: {news_title}

RINGKASAN: {news_summary}

PLATFORM TARGET: {platform_note}

Tolong buatkan konten berikut:

{outputs_section}

Pastikan semua output langsung bisa digunakan dan sesuai karakter platform {platform.upper()}."""


# ─────────────────────────────────────────────
# BACKEND 1: OLLAMA
# ─────────────────────────────────────────────

class OllamaBackend:
    """Backend menggunakan Ollama (lokal, cepat, model: gemma3/llama3/dll)."""

    def __init__(self, model: str = "gemma3"):
        self.model = model

    def generate_stream(
        self,
        news_title: str,
        news_summary: str,
        platform: str,
        output_types: list[str],
    ) -> Generator[str, None, None]:
        user_prompt = _build_user_prompt(news_title, news_summary, platform, output_types)
        try:
            stream = ollama.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                stream=True,
            )
            for chunk in stream:
                content = chunk.get("message", {}).get("content", "")
                if content:
                    yield content
        except Exception as e:
            yield f"\n\n**[ERROR Ollama]** `{str(e)}`\n\n"
            yield "Pastikan Ollama sudah berjalan: `ollama serve`\n"

    def check_status(self) -> dict:
        try:
            models = ollama.list()
            model_names = [m.model for m in models.models]
            return {
                "connected": True,
                "models": model_names,
                "active_model": self.model,
                "gemma_available": any("gemma" in n for n in model_names),
            }
        except Exception as e:
            return {
                "connected": False,
                "models": [],
                "active_model": self.model,
                "error": str(e),
            }


# ─────────────────────────────────────────────
# BACKEND 2: AIRLLM
# ─────────────────────────────────────────────

# Model-model yang bisa dipakai dengan AirLLM (HuggingFace repo ID)
AIRLLM_PRESETS = {
    "llama3-70b": {
        "repo_id": "meta-llama/Meta-Llama-3-70B-Instruct",
        "description": "Llama3 70B Instruct — kualitas tertinggi, ~140GB disk",
        "vram_required": "4GB GPU",
    },
    "llama3-8b": {
        "repo_id": "meta-llama/Meta-Llama-3-8B-Instruct",
        "description": "Llama3 8B Instruct — cepat, ~16GB disk",
        "vram_required": "4GB GPU",
    },
    "mistral-7b": {
        "repo_id": "mistralai/Mistral-7B-Instruct-v0.2",
        "description": "Mistral 7B Instruct v0.2 — balanced quality & speed",
        "vram_required": "4GB GPU",
    },
    "qwen2.5-72b": {
        "repo_id": "Qwen/Qwen2.5-72B-Instruct",
        "description": "Qwen2.5 72B Instruct — sangat powerful untuk bahasa Asia",
        "vram_required": "4GB GPU",
    },
    "qwen2.5-7b": {
        "repo_id": "Qwen/Qwen2.5-7B-Instruct",
        "description": "Qwen2.5 7B — ringan, bagus untuk bahasa Indonesia",
        "vram_required": "4GB GPU",
    },
}


def _format_llama3_prompt(system: str, user: str) -> str:
    """Format chat prompt sesuai Llama3 chat template."""
    return (
        f"<|begin_of_text|>"
        f"<|start_header_id|>system<|end_header_id|>\n\n{system}<|eot_id|>"
        f"<|start_header_id|>user<|end_header_id|>\n\n{user}<|eot_id|>"
        f"<|start_header_id|>assistant<|end_header_id|>\n\n"
    )


def _format_mistral_prompt(system: str, user: str) -> str:
    """Format chat prompt sesuai Mistral/Gemma instruct template."""
    return f"[INST] {system}\n\n{user} [/INST]"


def _format_qwen_prompt(system: str, user: str) -> str:
    """Format chat prompt sesuai Qwen chat template."""
    return (
        f"<|im_start|>system\n{system}<|im_end|>\n"
        f"<|im_start|>user\n{user}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )


class AirLLMBackend:
    """
    Backend menggunakan AirLLM — jalankan model 70B di GPU 4GB.
    Model di-load layer per layer dari disk, lebih lambat tapi hemat VRAM.
    Model pertama kali di-download dari HuggingFace dan di-split otomatis.
    """

    def __init__(
        self,
        preset: str = "llama3-8b",
        compression: str = "4bit",
        hf_token: str = "",
        max_new_tokens: int = 1024,
    ):
        if preset not in AIRLLM_PRESETS:
            raise ValueError(f"Preset tidak dikenal: {preset}. Pilih dari: {list(AIRLLM_PRESETS.keys())}")

        self.preset = preset
        self.preset_info = AIRLLM_PRESETS[preset]
        self.model_id = self.preset_info["repo_id"]
        self.compression = compression
        self.hf_token = hf_token
        self.max_new_tokens = max_new_tokens
        self._model = None
        self._loading = False
        self._load_error: str = ""

    def _get_prompt(self, user_prompt: str) -> str:
        mid = self.model_id.lower()
        if "llama" in mid:
            return _format_llama3_prompt(SYSTEM_PROMPT, user_prompt)
        elif "qwen" in mid:
            return _format_qwen_prompt(SYSTEM_PROMPT, user_prompt)
        else:
            return _format_mistral_prompt(SYSTEM_PROMPT, user_prompt)

    def load_model(self) -> bool:
        """Load / inisialisasi model AirLLM. Return True jika berhasil."""
        if self._model is not None:
            return True
        if self._loading:
            return False

        self._loading = True
        self._load_error = ""
        try:
            from airllm import AutoModel

            init_kwargs = {
                "pretrained_model_name_or_path": self.model_id,
            }
            if self.compression:
                init_kwargs["compression"] = self.compression
            if self.hf_token:
                init_kwargs["hf_token"] = self.hf_token

            print(f"[AirLLM] Loading model: {self.model_id} (compression={self.compression})...")
            self._model = AutoModel.from_pretrained(**init_kwargs)
            print(f"[AirLLM] Model siap!")
            return True
        except ImportError:
            self._load_error = "airllm tidak terinstall. Jalankan: pip install airllm transformers"
        except Exception as e:
            self._load_error = str(e)
            print(f"[AirLLM] Error loading model: {e}")
        finally:
            self._loading = False
        return False

    def generate_stream(
        self,
        news_title: str,
        news_summary: str,
        platform: str,
        output_types: list[str],
    ) -> Generator[str, None, None]:
        if self._load_error:
            yield f"\n\n**[ERROR AirLLM]** `{self._load_error}`\n\n"
            return

        if not self.load_model():
            yield "\n\n**[AirLLM]** Model sedang loading atau gagal. Cek log server.\n\n"
            if self._load_error:
                yield f"Error: `{self._load_error}`\n"
            return

        user_prompt = _build_user_prompt(news_title, news_summary, platform, output_types)
        full_prompt = self._get_prompt(user_prompt)

        try:
            import torch
            from transformers import TextIteratorStreamer

            tokenizer = self._model.tokenizer
            inputs = tokenizer(
                full_prompt,
                return_tensors="pt",
                return_attention_mask=False,
                truncation=True,
                max_length=2048,
                padding=False,
            )

            # Streaming via TextIteratorStreamer + thread
            streamer = TextIteratorStreamer(
                tokenizer,
                skip_special_tokens=True,
                skip_prompt=True,
                timeout=300,
            )

            input_ids = inputs["input_ids"]
            if torch.cuda.is_available():
                input_ids = input_ids.cuda()

            gen_kwargs = {
                "input_ids": input_ids,
                "max_new_tokens": self.max_new_tokens,
                "streamer": streamer,
                "use_cache": True,
                "return_dict_in_generate": True,
                "temperature": 0.8,
                "do_sample": True,
            }

            thread = threading.Thread(target=self._model.generate, kwargs=gen_kwargs, daemon=True)
            thread.start()

            for token_text in streamer:
                if token_text:
                    yield token_text

            thread.join(timeout=600)

        except Exception as e:
            yield f"\n\n**[ERROR AirLLM Generate]** `{str(e)}`\n"

    def check_status(self) -> dict:
        try:
            import torch
            cuda_available = torch.cuda.is_available()
            gpu_name = torch.cuda.get_device_name(0) if cuda_available else "CPU only"
            vram_total = round(torch.cuda.get_device_properties(0).total_memory / 1e9, 1) if cuda_available else 0
        except ImportError:
            cuda_available = False
            gpu_name = "torch tidak terinstall"
            vram_total = 0

        try:
            import airllm  # noqa
            airllm_installed = True
        except ImportError:
            airllm_installed = False

        return {
            "connected": airllm_installed and (self._model is not None),
            "airllm_installed": airllm_installed,
            "model_loaded": self._model is not None,
            "loading": self._loading,
            "load_error": self._load_error,
            "active_model": self.model_id,
            "preset": self.preset,
            "compression": self.compression,
            "cuda_available": cuda_available,
            "gpu_name": gpu_name,
            "vram_gb": vram_total,
        }


# ─────────────────────────────────────────────
# BACKEND MANAGER
# ─────────────────────────────────────────────

class BackendManager:
    """
    Singleton manager untuk switch antara backend Ollama dan AirLLM.
    Gunakan BackendManager.instance() untuk akses global.
    """

    _instance: "BackendManager | None" = None

    def __init__(self):
        self._backend_type: str = "ollama"
        self._ollama = OllamaBackend(model="gemma3")
        self._airllm: AirLLMBackend | None = None

    @classmethod
    def instance(cls) -> "BackendManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def active_backend_type(self) -> str:
        return self._backend_type

    def get_backend(self) -> OllamaBackend | AirLLMBackend:
        if self._backend_type == "airllm" and self._airllm:
            return self._airllm
        return self._ollama

    def set_ollama(self, model: str = "gemma3") -> dict:
        self._ollama = OllamaBackend(model=model)
        self._backend_type = "ollama"
        return {"backend": "ollama", "model": model}

    def set_airllm(
        self,
        preset: str = "llama3-8b",
        compression: str = "4bit",
        hf_token: str = "",
        max_new_tokens: int = 1024,
    ) -> dict:
        # Ganti model jika preset berbeda atau belum ada
        if self._airllm is None or self._airllm.preset != preset or self._airllm.compression != compression:
            self._airllm = AirLLMBackend(
                preset=preset,
                compression=compression,
                hf_token=hf_token,
                max_new_tokens=max_new_tokens,
            )
        self._backend_type = "airllm"
        return {
            "backend": "airllm",
            "preset": preset,
            "model": AIRLLM_PRESETS[preset]["repo_id"],
            "compression": compression,
        }

    def get_status(self) -> dict:
        ollama_status = self._ollama.check_status()
        airllm_status = self._airllm.check_status() if self._airllm else {
            "connected": False,
            "model_loaded": False,
            "airllm_installed": _check_airllm_installed(),
        }
        return {
            "active": self._backend_type,
            "ollama": ollama_status,
            "airllm": airllm_status,
            "presets": AIRLLM_PRESETS,
        }


def _check_airllm_installed() -> bool:
    try:
        import airllm  # noqa
        return True
    except ImportError:
        return False


# ─────────────────────────────────────────────
# PUBLIC API (dipanggil dari main.py)
# ─────────────────────────────────────────────

def generate_content_stream(
    news_title: str,
    news_summary: str,
    platform: str,
    output_types: list[str],
) -> Generator[str, None, None]:
    """Generate konten menggunakan backend yang sedang aktif."""
    backend = BackendManager.instance().get_backend()
    yield from backend.generate_stream(news_title, news_summary, platform, output_types)


def check_ollama_status() -> dict:
    """Untuk kompatibilitas backward — return status backend aktif."""
    return BackendManager.instance()._ollama.check_status()


def get_full_status() -> dict:
    return BackendManager.instance().get_status()
