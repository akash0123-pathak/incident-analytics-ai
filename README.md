# Incident Analytics AI

Ask incident-management questions in plain English and get accurate,
intent-led answers — no predefined reports or technical queries required.
It uses a local DuckDB warehouse, governed semantic layer, LangGraph workflow,
and an MCP server for compatible AI clients.

This implements "Use Case 2: Natural Language Incident Analytics and
Reporting" from the Incident Management use-cases deck: a conversational
layer over operational incident data.

The query workflow is intent-first: it classifies a lookup, search, trend,
report, or relationship-analysis request before choosing retrieval and answer
composition. Legacy roles remain only for backwards-compatible UI sessions;
they do not determine the answer path.

Two modes, same UI:

- **Dataset mode (default, no API key, no local LLM)** — a transparent
  rule-based engine parses the question (time range, severity, application,
  status, etc.) and answers straight from the incident dataset with pandas.
  Answers are also shaped by the selected **role** (engineer / manager /
  executive), so this mode alone is genuinely useful, not just a fallback.
- **AI mode (optional, only when an API key is present)** — the same
  rule-based filter retrieves the relevant rows, then a LangChain-driven
  LLM (NVIDIA NIM, OpenAI, or Anthropic) writes the fullest, best-composed
  answer from that data. The key can be typed into the frontend (stored
  only in that browser) or configured once on the server ("background"
  mode) so every user gets AI answers automatically.

See `ARCHITECTURE.md` for full technical detail.

---

## 1. Requirements

- Python 3.10+
- Node.js 18+ and npm

## 2. Backend setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# optional: reset the local DuckDB demo warehouse with fresh synthetic data
python -m app.dataset_generator

# run the API
uvicorn app.main:app --reload --port 8081
```

The API is now at `http://127.0.0.1:8081`. Interactive docs (Swagger UI) at
`http://127.0.0.1:8081/docs`.

### Data architecture and MCP

DuckDB is the local source of truth. On first use, the application generates
the synthetic demo incidents in memory and stores them directly in
`backend/app/warehouse/incident_analytics.duckdb`; no CSV dataset is needed.
`POST /api/dataset/reload` regenerates that local demo warehouse. Application
and AI access go through the `semantic_incidents` view, which provides typed
timestamps and the canonical incident fields. The semantic catalog and
business metrics are available at `/api/semantic/catalog` and
`/api/semantic/metrics`.

To expose the same governed layer to an MCP client, import
`backend/mcp.json` into that client's MCP configuration, or run:

```bash
cd backend
python -m app.mcp_server
```

The MCP server uses stdio and offers a catalog, headline metrics, approved
dimension breakdowns, dashboard data, and natural-language incident analytics.
It never gives clients direct access to the raw warehouse table. The local
FastAPI app is also an MCP client: normal no-key web requests follow
`React -> FastAPI -> local MCP client -> MCP server -> DuckDB`. Requests with
an explicitly configured AI-provider key retain the optional LLM path.

### Enabling AI mode in the background (no key needed in the browser)

Copy `backend/.env.example` to `backend/.env` and set one of:

```bash
NVIDIA_API_KEY=nvapi-...     # get a free key at https://build.nvidia.com
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

Restart the backend. `/api/config` will now report `server_key_configured: true`
and every question is answered in AI mode automatically, unless a user
  overrides it with their own key in the frontend Settings panel.

### Embedded knowledge graph (free, no separate installation)

The project uses an in-process NetworkX relationship graph derived from
DuckDB. It needs no Neo4j server, Docker, Desktop, or cloud account. Invoke
`POST /api/knowledge-graph/sync` after data changes; relationship questions
such as recurring causes and blast radius use the rebuilt graph automatically.

## 3. Frontend setup

```bash
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. In dev, Vite proxies `/api/*` to the backend
on port 8081 (see `vite.config.js`), so no CORS configuration is needed.

### Using your own key from the browser

Open the **Settings** panel in the sidebar, pick a provider (NVIDIA NIM by
default), paste an API key, and click **Use this key**. It's saved to
`localStorage` in your browser only and sent with each request — it is
never written to disk on the server. Click **Clear** to fall back to
dataset-only mode (or to the server's background key, if one is set).

## 4. Production build

```bash
cd frontend
npm run build     # outputs static files to frontend/dist
```

Serve `frontend/dist` with any static host / reverse proxy, and route
`/api/*` on the same origin to the FastAPI backend (e.g. with nginx, or by
mounting `frontend/dist` as static files inside the FastAPI app).

## 5. Try it

With the dataset engine alone (no key needed), ask things like:

- "What incidents were reported yesterday?"
- "Show all critical incidents from the last 90 days."
- "Provide details of the AWS outage reported last month."
- "Which applications generated the most incidents this quarter?"
- "Identify recurring incidents and their root causes."

Switch roles in the sidebar (Engineer / Manager / Executive) and ask the
same question again — the columns shown and level of detail change.

## 6. Project layout

```
incident-analytics-ai/
├── backend/            FastAPI + LangChain backend (see ARCHITECTURE.md)
│   └── app/
│       ├── main.py             API routes
│       ├── roles.py            role → permission/detail mapping
│       ├── config.py           server-side ("background") API key handling
│       ├── dataset_generator.py synthetic dataset generator
│       ├── warehouse.py         DuckDB source of truth / auto-bootstrap
│       ├── semantic_layer.py    governed metrics and dimensions
│       ├── nlp.py               transparent intent/entity processing
│       └── mcp_server.py        MCP stdio server for governed access
│       ├── data/incidents.csv  the dataset
│       └── engines/
│           ├── dataset_engine.py   NLP + semantic-view, no-API-key engine
│           ├── llm_engine.py       LangChain AI-powered engine
│           └── query_router.py     picks dataset vs AI per request
├── frontend/            React (Vite) chat UI
│   └── src/
│       ├── App.jsx
│       ├── api.js
│       └── components/
├── README.md            you are here
├── backend/mcp.json      MCP client configuration example
└── ARCHITECTURE.md       full technical/architecture reference
```

## 7. Troubleshooting

- **"Could not reach the backend API"** in the sidebar — the backend isn't
  running on port 8000, or you're opening `index.html` directly instead of
  via `npm run dev`.
- **AI mode call fails** — the app automatically falls back to dataset mode
  and prefixes the answer with the error, instead of failing the request.
  Check the key/provider pairing (an NVIDIA key won't work with `provider:
  openai`, etc.).
- **Want fresh demo data** — call `POST /api/dataset/reload`, or run
  `python -m app.dataset_generator`. This recreates the local DuckDB data.
