/**
 * State + metode bersama: tema, status API, panel backend (Ollama / AirLLM).
 * Pakai di setiap halaman: return { ...siteHeaderMixin(), ...dataKhususHalaman }
 */
function siteHeaderMixin() {
  return {
    ollamaStatus: { connected: false },
    dbStats: { news_total: 0, news_today: 0, gen_total: 0, gen_today: 0 },
    cacheAge: null,

    backendStatus: null,
    showBackendPanel: false,
    selectedBackendType: 'ollama',
    ollamaModelInput: 'gemma4:31b-cloud',
    airllmPreset: 'llama3-8b',
    airllmCompression: '4bit',
    airllmToken: '',
    airllmPresets: {},
    switchingBackend: false,
    backendSwitchMsg: '',

    darkMode: localStorage.getItem('theme') !== 'light',

    get headerModelSummary() {
      const b = this.backendStatus;
      if (!b) return 'Model';
      if (b.active === 'airllm') {
        const p = b.airllm?.preset || this.airllmPreset || '';
        return 'AirLLM — ' + p;
      }
      const m = b.ollama?.active_model || this.ollamaModelInput || 'Ollama';
      return 'Ollama — ' + m;
    },

    toggleMode() {
      this.darkMode = !this.darkMode;
      const mode = this.darkMode ? 'dark' : 'light';
      localStorage.setItem('theme', mode);
      document.documentElement.className = mode;
    },

    async checkStatus() {
      try {
        const res = await fetch('/api/status');
        const data = await res.json();
        this.ollamaStatus = data.ollama || { connected: false };
        this.cacheAge = data.cache_age_minutes;
        if (data.db) {
          this.dbStats = {
            news_total: data.db.news?.total || 0,
            news_today: data.db.news?.last_24h || 0,
            gen_total: data.db.generated?.total || 0,
            gen_today: data.db.generated?.last_24h || 0,
          };
        }
        if (data.backend) {
          this.backendStatus = data.backend;
          this.selectedBackendType = data.backend.active || 'ollama';
          this.airllmPresets = data.backend.presets || {};
        }
      } catch (e) {
        this.ollamaStatus = { connected: false };
      }
    },

    async loadBackendStatus() {
      try {
        const res = await fetch('/api/backend');
        const data = await res.json();
        this.backendStatus = data;
        this.selectedBackendType = data.active || 'ollama';
        this.airllmPresets = data.presets || {};
      } catch (e) {}
    },

    async switchToOllama() {
      this.switchingBackend = true;
      this.backendSwitchMsg = '';
      try {
        const res = await fetch('/api/backend/ollama', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ model: this.ollamaModelInput }),
        });
        const data = await res.json();
        this.backendSwitchMsg = data.success ? `✓ Beralih ke Ollama (${data.model})` : 'Gagal beralih';
        await this.checkStatus();
      } catch (e) {
        this.backendSwitchMsg = 'Error: ' + e.message;
      } finally {
        this.switchingBackend = false;
      }
    },

    async switchToAirLLM() {
      this.switchingBackend = true;
      this.backendSwitchMsg = '';
      try {
        const res = await fetch('/api/backend/airllm', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            preset: this.airllmPreset,
            compression: this.airllmCompression,
            hf_token: this.airllmToken,
          }),
        });
        const data = await res.json();
        this.backendSwitchMsg = data.success
          ? '✓ AirLLM aktif. Model dimuat saat generate pertama.'
          : 'Gagal beralih ke AirLLM';
        await this.checkStatus();
      } catch (e) {
        this.backendSwitchMsg = 'Error: ' + e.message;
      } finally {
        this.switchingBackend = false;
      }
    },

    async preloadAirLLM() {
      this.switchingBackend = true;
      this.backendSwitchMsg = 'Memuat model...';
      try {
        const res = await fetch('/api/backend/airllm/preload', { method: 'POST' });
        const data = await res.json();
        this.backendSwitchMsg =
          data.success && data.model_loaded ? '✓ Model siap digunakan' : `Gagal: ${data.error || 'Unknown'}`;
        await this.checkStatus();
      } catch (e) {
        this.backendSwitchMsg = 'Error: ' + e.message;
      } finally {
        this.switchingBackend = false;
      }
    },
  };
}
