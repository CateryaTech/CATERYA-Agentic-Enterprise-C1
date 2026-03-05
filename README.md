# ⬡ CATERYA Enterprise

**Author:** Ary HH — CATERYA Tech  
**Contact:** cateryatech@proton.me  
**License:** Apache 2.0  
**Stack:** Python 3.11+ · LangGraph · Streamlit · FastAPI · PostgreSQL · Redis

---

## Overview

CATERYA Enterprise adalah platform AI agentik multi-tenant yang dibangun di atas LangGraph, dengan evaluasi etika bawaan menggunakan **Composite Overall Score (COS)**. Framework CATERYA disertakan langsung di `src/caterya/` — tidak perlu `pip install caterya`.

**Dua mode pipeline tersedia:**

| Mode | Deskripsi | Jumlah Agent |
|---|---|---|
| 🔍 **Analyse** | Riset mendalam + strategi bisnis lengkap | 7 agent |
| 🏗️ **Build SaaS** | Menghasilkan kode SaaS siap pakai | 7 agent |

---

## Arsitektur Sistem

```
caterya-agentic-enterprise/
│
├── dashboard/
│   └── app.py                    # Streamlit dashboard (635 baris)
│                                 # Mode Analyse + Build SaaS
│                                 # Export: PDF · HTML · Markdown · JSON
│
├── workflows/
│   └── langgraph_workflow.py     # LangGraph workflow (946 baris)
│                                 # 10 agent nodes + mode routing
│                                 # 6 LLM providers
│
├── src/caterya/                  # ← Framework standalone
│   ├── core/
│   │   ├── evaluator.py          # CATERYAEvaluator — COS engine
│   │   └── guardrail.py          # CATERYAGuardrail — filter per-agent
│   ├── pillars/
│   │   ├── bias_fairness.py      # Symmetry Index
│   │   ├── transparency.py       # Provenance Score
│   │   ├── safety.py             # Harm detection
│   │   ├── accountability.py     # Audit trail linkage
│   │   └── privacy.py            # PII detection
│   ├── blockchain/
│   │   └── provenance_chain.py   # Cryptographic audit chain
│   ├── agents/
│   │   └── base_agent.py         # BaseAgent ABC
│   ├── quantum/
│   │   └── quantum_utils.py      # Quantum-inspired entropy scoring
│   └── utils/
│       ├── export.py             # PDF/HTML/Markdown/JSON export
│       └── llm_clients.py        # Native LLM clients (Gemini/Ollama/OpenAI)
│
├── api/
│   └── main.py                   # FastAPI REST server
│
├── auth/
│   ├── jwt_handler.py            # JWT access + refresh tokens
│   └── oauth.py                  # Supabase / Auth0 integration
│
├── tenancy/
│   ├── isolation.py              # PostgreSQL schema-per-tenant
│   └── models.py                 # Tenant data models
│
├── tests/
│   └── test_all.py               # 24 unit tests, COS baseline 0.9411
│
├── migrations/init.sql           # Database schema init
├── .env.example                  # Template environment variables
├── docker-compose.yml            # Postgres + Redis + App
├── Dockerfile                    # Production container
└── requirements.txt              # All dependencies
```

**Total: ~3,962 baris kode**

---

## Pipeline Agents

### Mode 🔍 Analyse (7 agent aktif)

```
research → analysis → writer ──► marketing → sales → finance → evaluate
```

| # | Agent | Tugas |
|---|---|---|
| 1 | 🔍 **Research Agent** | Riset fakta, konteks, referensi, benchmarks |
| 2 | 🧠 **Analysis Agent** | Critical thinking, identifikasi pola, SWOT |
| 3 | ✍️ **Writer Agent** | Sintesis akhir, laporan naratif |
| 4 | 📣 **Marketing Agent** | Target audience, messaging, GTM strategy |
| 5 | 💼 **Sales Agent** | ICP, sales funnel, outreach script, pricing |
| 6 | 💰 **Finance Agent** | P&L projection, CAC/LTV, break-even, funding |
| 7 | ⚖️ **Ethics Evaluator** | COS score: Bias + Transparency + Safety + ... |

### Mode 🏗️ Build SaaS (7 agent aktif)

```
research → analysis → writer ──► architect → backend_coder → frontend_coder → evaluate
```

| # | Agent | Output |
|---|---|---|
| 1 | 🔍 **Research Agent** | Tech stack benchmarks, library comparison |
| 2 | 🧠 **Analysis Agent** | Requirements analysis, feature breakdown |
| 3 | ✍️ **Writer Agent** | Technical specification document |
| 4 | 🏗️ **Architect Agent** | System design, DB schema SQL, API design, dir tree |
| 5 | ⚙️ **Backend Engineer** | FastAPI + SQLAlchemy + JWT + Docker — kode lengkap |
| 6 | 🎨 **Frontend Engineer** | Next.js 14 + TypeScript + Tailwind + docker-compose |
| 7 | ⚖️ **Ethics Evaluator** | COS ethical evaluation |

> **Tip Build mode:** Gunakan model lebih besar untuk kode terbaik — `llama-3.3-70b-versatile` (Groq) atau `gemini-2.0-flash` (Gemini).

---

## LLM Providers

### Provider yang didukung

| Provider | Key Env | Model Default | Catatan |
|---|---|---|---|
| **Ollama** | `OLLAMA_BASE_URL` | `qwen3.5` | Self-hosted, gratis |
| **Gemini** | `GEMINI_API_KEY` | `gemini-2.0-flash` | Google AI Studio, free tier |
| **Groq** | `GROQ_API_KEY` | `llama-3.1-8b-instant` | Tercepat, free tier |
| **OpenRouter** | `OPENROUTER_API_KEY` | `meta-llama/llama-3.1-8b-instruct:free` | 100+ model |
| **Together AI** | `TOGETHER_API_KEY` | `meta-llama/Llama-3-8b-chat-hf` | |
| **Fireworks AI** | `FIREWORKS_API_KEY` | `accounts/fireworks/models/llama-v3-8b-instruct` | |

---

### 1. Ollama — Primary (qwen3.5 + qwen3-vl)

CATERYA menggunakan Ollama SDK dengan pattern ini:

```python
from ollama import chat

# Text — qwen3.5 (primary model)
response = chat(
    model='qwen3.5',
    messages=[{'role': 'user', 'content': 'Hello!'}],
)
print(response.message.content)

# Vision-Language — qwen3-vl
response = chat(
    model='qwen3-vl',
    messages=[{'role': 'user', 'content': 'Hello!'}],
)
print(response.message.content)
```

**Fallback chain otomatis:**
1. Native `ollama.chat()` SDK
2. Ollama OpenAI Codec (`/v1` endpoint via `openai` package)
3. Raw HTTP ke `/api/chat`

```bash
# Setup Ollama
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3.5
ollama pull qwen3-vl
ollama serve
```

```toml
# Streamlit Secrets
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL    = "qwen3.5"
OLLAMA_API_KEY  = ""   # kosong = no auth
```

---

### 2. Google Gemini

CATERYA menggunakan **native REST endpoint** yang sama persis dengan curl ini:

```bash
curl "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent" \
  -H 'Content-Type: application/json' \
  -H 'X-goog-api-key: YOUR_KEY' \
  -X POST \
  -d '{"contents": [{"parts": [{"text": "Explain how AI works"}]}]}'
```

**Models free tier:**
- `gemini-2.0-flash` — default, 1500 req/hari gratis
- `gemini-flash-latest` — alias latest
- `gemini-1.5-pro-latest` — paling capable, 50 req/hari

```toml
# Streamlit Secrets
GEMINI_API_KEY = "AIza..."   # aistudio.google.com/app/apikey
```

---

### 3. Groq

```toml
GROQ_API_KEY = "gsk_..."   # console.groq.com — gratis
```

Models: `llama-3.1-8b-instant` · `llama-3.3-70b-versatile` · `mixtral-8x7b-32768`

---

### 4. OpenRouter, Together, Fireworks

```toml
OPENROUTER_API_KEY = "sk-or-..."
TOGETHER_API_KEY   = "..."
FIREWORKS_API_KEY  = "fw_..."
```

---

## Ethical AI — COS Framework

Setiap output agent dievaluasi otomatis terhadap 5 pilar etika:

| Pilar | Bobot | Metrik |
|---|---|---|
| ⚖️ Bias & Fairness | 25% | Symmetry Index (keseimbangan gender/rasial/linguistik) |
| 🔍 Transparency | 25% | Provenance Score (traceability, interpretability) |
| 🛡️ Safety | 20% | Harm detection, konten berbahaya |
| 📋 Accountability | 15% | Audit trail linkage, record completeness |
| 🔒 Privacy | 15% | PII detection, data minimization |

```
COS = Σ(pillar_score × weight)
PASS: COS ≥ 0.70  (configurable)
```

**Standalone Evaluator** tersedia di tab 🔬 dashboard — evaluasi teks apapun tanpa menjalankan pipeline.

---

## Export Results

| Format | Cara Download | Use Case |
|---|---|---|
| 📝 Markdown | `st.download_button` | Notion, Obsidian, GitHub |
| 🌐 HTML | `st.download_button` | Buka di browser, dark theme |
| 📄 PDF | Base64 HTML `<a>` link | Semua PDF viewer (binary-safe) |
| {} JSON | `st.download_button` | Integrasi API, data pipeline |

> **PDF:** Download via base64 HTML link (bukan `st.download_button`) karena Streamlit Cloud dapat mengkorrupsi binary data saat serialisasi. Semua emoji diganti ASCII sebelum render ke ReportLab (font Latin-1).

---

## Setup

### A. Streamlit Cloud

```
1. Push repo ke GitHub
2. share.streamlit.io → New app → dashboard/app.py
3. Settings → Secrets → tambahkan minimal satu LLM key
```

```toml
# Minimal config — pilih satu provider:
GROQ_API_KEY    = "gsk_..."
# atau
GEMINI_API_KEY  = "AIza..."
# atau
OLLAMA_BASE_URL = "https://your-ollama.example.com"
```

### B. Local

```bash
git clone https://github.com/your-username/caterya-agentic-enterprise.git
cd caterya-agentic-enterprise

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # isi LLM key

streamlit run dashboard/app.py
# Dashboard: http://localhost:8501

# (Opsional) API server
uvicorn api.main:app --reload --port 8000
```

### C. Docker Compose

```bash
cp .env.example .env
docker-compose up -d
# Dashboard: http://localhost:8501
# API Docs:  http://localhost:8000/docs
```

---

## Native LLM Clients

`src/caterya/utils/llm_clients.py` tersedia sebagai standalone client:

```python
# Gemini native REST
from src.caterya.utils.llm_clients import GeminiNativeClient
gemini = GeminiNativeClient(model="gemini-2.0-flash")
r = gemini.invoke("Explain AI in 3 sentences")
print(r.content)

# Ollama native SDK
from src.caterya.utils.llm_clients import OllamaNativeClient
ollama = OllamaNativeClient(model="qwen3.5")
r = ollama.invoke("Hello!")
print(r.content)

# OpenAI / OpenAI-compatible (Groq, OpenRouter, dll)
from src.caterya.utils.llm_clients import OpenAIClient
client = OpenAIClient(
    model="llama-3.1-8b-instant",
    api_key="gsk_...",
    base_url="https://api.groq.com/openai/v1"
)
r = client.invoke("Hello!")
print(r.content)
```

---

## Tests

```bash
pytest tests/ -v --tb=short
# 24 passed — COS baseline: 0.9411
```

---

## Changelog

| Versi | Perubahan |
|---|---|
| **v1.0** | 3 agent (research, analysis, writer) + COS evaluate |
| **v2.0** | +3 business agents: marketing, sales, finance |
| **v3.0** | Dual-mode: Analyse + Build SaaS (architect, backend, frontend code gen) |
| **v3.1** | Gemini native REST · Ollama qwen3.5/qwen3-vl · PDF base64 fix · Export engine |
| **v3.2** | LLM clients refactor · GeminiNativeClient · OllamaNativeClient · fallback chain |

---

## Lisensi

Apache 2.0 — bebas digunakan untuk komersial, modifikasi, dan distribusi.

---

*⬡ CATERYA Enterprise · cateryatech@proton.me · Built with ❤️ in Indonesia*
