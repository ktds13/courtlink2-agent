# CourtLink2 Agent

An AI assistant for the CourtLink2 video visitation management system. Built with FastAPI, LangChain, and Azure OpenAI, it gives operators and developers a natural-language interface to manage meetings, devices, and calls — and lets developers search and edit the CourtLink2 source code through chat.

## Features

- **Live system control** — create, update, and delete meetings; schedule, start, pause, resume, end, and cancel calls; assign meetings to devices
- **Device management** — list and inspect device status, control room PC power (on/off/reboot via SNMP)
- **Documentation search** — semantic RAG over CourtLink2 markdown docs (architecture, REST API, MQTT topics, troubleshooting)
- **Code search** — semantic search across indexed C#/XAML/JSON source code chunks
- **File discovery** — LLM-generated per-file descriptions let the agent navigate the codebase by intent
- **Code editing** — read files, propose diffs, apply edits, and commit to a branch — all through chat
- **Persistent memory** — per-session conversation history stored in PostgreSQL

## Architecture

```
static/index.html          Chat web UI (dark theme)
app/
  main.py                  FastAPI server  (POST /chat, DELETE /chat/{id}, GET /health)
  agent.py                 LangChain Azure OpenAI agent + PostgreSQL session memory
  vectorstore.py           pgvector similarity search helpers
  tools/
    api_client.py          Shared mTLS httpx client for CourtLink2 Management API
    meetings.py            list / get / create / update / delete / assign meeting tools
    devices.py             list_devices, get_device
    calls.py               schedule / start / pause / resume / end / cancel call tools
    device_power.py        control_device_power (SNMP)
    system_configs.py      list_system_configs
    docs.py                search_courtlink_docs (pgvector RAG)
    file_search.py         search_file_descriptions (pgvector)
    code_search.py         search_code (pgvector)
    code_edit.py           read_file, propose_edit, edit_file, git_commit
scripts/
  setup.sql                PostgreSQL schema (tables + HNSW indexes)
  ingest_docs.py           Vectorize markdown docs → documents table
  ingest_code.py           Vectorize source code → code_chunks table
  ingest_file_descriptions.py  LLM-generate per-file descriptions → file_descriptions table
docs/                      CourtLink2 documentation (CCM, SmartClient, Management, SystemDesign)
certificates/              mTLS client certificate (gitignored)
```

## Prerequisites

- Python 3.11+
- Docker (for PostgreSQL + pgvector)
- An Azure OpenAI deployment (GPT-4.x for chat, `text-embedding-ada-002` for embeddings)
- Access to a running CourtLink2 Management API with an mTLS client certificate

## Setup

### 1. Clone and configure

```bash
git clone https://github.com/ktds13/courtlink2-agent.git
cd courtlink2-agent
cp .env.example .env
```

Edit `.env` and fill in your values:

| Variable | Description |
|---|---|
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI resource endpoint |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI API key |
| `AZURE_OPENAI_API_VERSION` | API version, e.g. `2024-10-01-preview` |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Chat deployment name, e.g. `gpt-4.1-mini` |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | Embedding deployment, e.g. `text-embedding-ada-002` |
| `DATABASE_URL` | PostgreSQL connection string |
| `COURTLINK_API_URL` | CourtLink2 Management API base URL |
| `COURTLINK_CERT_PATH` | Path to mTLS client certificate (PFX or PEM) |
| `COURTLINK_CERT_PASSWORD` | PFX password (leave empty for PEM) |
| `COURTLINK_SSL_VERIFY` | Set `false` to skip TLS verification (dev only) |

### 2. Start PostgreSQL

```bash
docker compose up -d
```

This starts a `pgvector/pgvector:pg16` container on port `5433` and runs `scripts/setup.sql` automatically on first start, creating all tables and HNSW indexes.

### 3. Install dependencies

```bash
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # Linux/macOS
pip install -r requirements.txt
```

### 4. Ingest documentation and source code

Run these once (or re-run after content changes):

```bash
# Vectorize the markdown docs in docs/
python scripts/ingest_docs.py

# Vectorize CourtLink2 source code (point --repo at your local checkout)
python scripts/ingest_code.py --repo /path/to/CourtLink2

# Generate per-file descriptions for the file discovery tool
python scripts/ingest_file_descriptions.py --repo /path/to/CourtLink2
```

### 5. Start the server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open `http://localhost:8000` in a browser to use the chat UI.

## API

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Chat web UI |
| `POST` | `/chat` | Send a message, receive an agent reply |
| `DELETE` | `/chat/{session_id}` | Clear conversation history for a session |
| `GET` | `/health` | Health check (PostgreSQL connectivity) |

**POST /chat** request body:

```json
{
  "message": "Show me all available devices",
  "session_id": ""
}
```

Pass the `session_id` returned in the response to maintain conversation context across requests. Omit it (or pass an empty string) to start a new session.

## Certificates

The agent authenticates to CourtLink2 Management using mTLS. Place your client certificate in `certificates/` (this directory is gitignored) and set `COURTLINK_CERT_PATH` in `.env`:

```
# PFX file
COURTLINK_CERT_PATH=certificates/ccm1.pfx
COURTLINK_CERT_PASSWORD=yourpassword

# Separate PEM files
COURTLINK_CERT_PATH=certificates/client.crt
COURTLINK_KEY_PATH=certificates/client.key
```

## Database schema

| Table | Purpose |
|---|---|
| `documents` | Chunked CourtLink2 markdown docs with embeddings (RAG) |
| `code_chunks` | CourtLink2 source code chunks with embeddings (code search) |
| `file_descriptions` | One LLM-generated description per source file (file discovery) |
| `chat_sessions` | Per-session conversation history (JSONB) |

All vector columns use `vector(1536)` with HNSW cosine indexes for fast nearest-neighbour search.
