# Architecture & Project Reference

This file is meant to answer any question a person (or another AI) could
have about this project: what it is, how it's built, why it's built that
way, and how the pieces fit together.

## 1. What this project is

A natural-language analytics assistant over IT incident data, implementing
"Use Case 2: Natural Language Incident Analytics and Reporting":

> Operational data exists in multiple repositories, but users struggle to
> retrieve meaningful insights without predefined reports or technical
> queries. A conversational layer sits on top of operational datasets and
> allows users to query incident data using natural language, dynamically
> generating the required data queries and presenting accurate results.

Two things distinguish this build from "just wire up an LLM":

1. **It works with zero API keys and no local LLM.** A deterministic,
   role-aware rule engine answers questions directly from the dataset.
   This is the default and the primary supported path.
2. **AI is opt-in, additive, and pluggable.** If (and only if) an API key
   is available — from the browser, or from a server-side "background"
   key — the exact same retrieved data is handed to an LLM (via LangChain)
   to produce a fuller, better-written answer. AI is a quality upgrade on
   top of the dataset engine, not a replacement for it, and the app never
   silently fails if a key is missing or a provider call errors.

## 2. High-level architecture

```
┌──────────────────────────┐        HTTP (JSON)        ┌───────────────────────────────┐
│   React frontend (Vite)  │  ───────────────────────▶  │   FastAPI backend (Python)    │
│                           │                             │                                │
│  - Chat UI                │                             │  /api/query  → query_router   │
│  - Role selector           │  ◀───────────────────────  │  /api/roles                   │
│  - Settings (API key,      │        answer + data        │  /api/config                  │
│    provider, browser vs    │                             │  /api/incidents                │
│    background key)         │                             │  /api/dataset/reload           │
└──────────────────────────┘                             └───────────────┬───────────────┘
                                                                            │
                                                          ┌─────────────────┴──────────────────┐
                                                          │           query_router.py            │
                                                          │  has an API key (request or server)? │
                                                          └───────┬───────────────────┬──────────┘
                                                                  │ no                 │ yes
                                                                  ▼                    ▼
                                               ┌────────────────────────┐   ┌───────────────────────────┐
                                               │   dataset_engine.py     │   │      llm_engine.py         │
                                               │  keyword/regex intent   │──▶│  same retrieval, then a    │
                                               │  detection + pandas     │   │  LangChain chat model      │
                                               │  filtering over the     │   │  (NVIDIA NIM / OpenAI /    │
                                               │  CSV dataset, shaped    │   │  Anthropic) composes the   │
                                               │  by the selected role   │   │  final answer from it      │
                                               └────────────┬─────────────┘   └───────────────┬─────────┘
                                                             │                                  │
                                                             ▼                                  ▼
                                               ┌───────────────────────────────────────────────────────┐
                                               │        backend/app/data/incidents.csv (dataset)         │
                                               └───────────────────────────────────────────────────────┘
```

## 3. Tech stack and why

| Layer               | Choice                              | Why |
|---------------------|--------------------------------------|-----|
| Backend framework   | FastAPI                              | Async, typed, auto-generates OpenAPI docs at `/docs`, minimal boilerplate. |
| Data warehouse       | DuckDB                                | The local source of truth; it persists automatically generated demo incidents in a durable, columnar incident table. |
| Semantic data layer  | `semantic_incidents` view + governed metrics | Canonical typed fields and approved business metrics/dimensions. API, NLP and MCP clients use this contract rather than raw tables. |
| Data handling        | pandas                               | Used by the compatibility query engine after retrieval from the DuckDB semantic view. |
| MCP data access      | MCP Python SDK / stdio server          | Exposes catalog, metric, breakdown and natural-language tools to MCP clients while keeping raw tables private. |
| Orchestration (AI)   | LangChain (`langchain-core`, `langchain-openai`, `langchain-anthropic`) | Provides one consistent chat-model interface across providers, so swapping NVIDIA NIM / OpenAI / Anthropic is a config change, not a rewrite. |
| AI providers         | NVIDIA NIM (default), OpenAI, Anthropic | NVIDIA NIM and OpenAI both expose an OpenAI-compatible Chat Completions API, so both go through `langchain_openai.ChatOpenAI` with a different `base_url`/model. Anthropic goes through `langchain_anthropic.ChatAnthropic`. |
| "ML" in dataset mode | Python stdlib `difflib.get_close_matches` only | Used purely to tolerate typos in application names. There is no trained model, no embeddings, and no vector database — intentionally, per the brief's "ML should be as little as possible." |
| Frontend framework   | React 18 + Vite                      | Fast dev server, simple build, no framework lock-in. |
| HTTP client          | axios                                | Small, promise-based, easy error handling. |
| Styling              | Hand-written CSS (`src/styles.css`) | No UI kit dependency; keeps the bundle small and the look intentional rather than templated. |

DuckDB is the local source of truth. On first use the application generates
the demo incidents in memory, writes them directly to DuckDB, and exposes
them through the `semantic_incidents` view. The initial semantic layer is small
and code-defined: it exposes approved business metrics and dimensions rather
than allowing arbitrary client SQL.

## 4. Backend module reference

```
backend/app/
├── main.py                FastAPI app + all HTTP routes
├── models.py               Pydantic request/response schemas
├── roles.py                 Role definitions (permissions/detail level)
├── config.py                 Reads background/server-side API keys from env
├── dataset_generator.py       Builds the synthetic incidents.csv
├── data/incidents.csv          The dataset itself (generated, checked in)
└── engines/
    ├── dataset_engine.py        No-API-key rule-based query engine
    ├── llm_engine.py             AI-powered engine (LangChain)
    └── query_router.py           Chooses dataset vs AI per request
```

### `roles.py` — role-based behaviour

Three roles ship out of the box: `engineer`, `manager`, `executive`. Each
`Role` defines:

- `visible_columns` — which dataset columns are included in the response
  (e.g. executives never see `reporter` or `root_cause` detail).
- `show_reporter` — whether the individual who reported the incident is
  ever exposed.
- `detail_level` — `raw` | `summary` | `executive`, used both to trim
  columns (dataset mode) and as an instruction to the LLM (AI mode) about
  how much detail and what tone to use.

Add a new role by adding an entry to the `ROLES` dict — nothing else needs
to change; both engines and the frontend role selector read from it via
`/api/roles`.

### `dataset_engine.py` — the default, key-free engine

Pipeline for `answer_question(question, role)`:

1. **Anchor "now"** to the most recent `reported_at` timestamp in the
   dataset (so relative-time questions like "yesterday" work against demo
   data that doesn't move with the real calendar).
2. **Extract structured filters** from the question with small regex/
   keyword matchers: time range (`today`, `last week`, `last month`,
   `this quarter`, …), severity, status, application (exact match, then
   substring, then `difflib` fuzzy match), category, team.
3. **Detect an aggregation intent**: "which applications generated the
   most incidents" → group-by count; "recurring incidents / root causes"
   → group-by root cause; "how many" → a count.
4. **Default (list) path**: if no aggregation intent matched, filter the
   DataFrame by the structured filters, then also score remaining rows by
   free-text keyword overlap against title/description/root_cause (e.g.
   "AWS outage" surfaces the specific AWS incident even though "AWS" isn't
   a modeled application/severity/status value) and sort by that score.
5. **Package the result** through the role: trims columns to
   `role.visible_columns`, returns the answer text, the matched count, and
   up to 25 sample rows as JSON records.

This is intentionally readable top-to-bottom in one file — the goal is
that anyone can see exactly why the system gave the answer it gave, with
no black box.

### `llm_engine.py` — the optional AI-powered engine

Only invoked when an API key is available. It does **not** re-implement
retrieval: it calls `dataset_engine.answer_question()` first to get the
same role-filtered rows, formats them as compact `key=value` lines, and
sends them to the LLM as context alongside the question and a system
prompt that:

- Forbids inventing incident IDs/dates/root causes not present in context.
- Adjusts tone/detail via `AUDIENCE_HINTS[role.detail_level]`.

`_build_llm(provider, api_key, model)` returns a LangChain chat model:

- `provider="nvidia"` → `ChatOpenAI(base_url="https://integrate.api.nvidia.com/v1", model="meta/llama-3.1-70b-instruct", ...)`
- `provider="openai"` → `ChatOpenAI(model="gpt-4o-mini", ...)`
- `provider="anthropic"` → `ChatAnthropic(model="claude-sonnet-4-6", ...)`

If the call throws (bad key, network error, rate limit, etc.), the
exception propagates to `query_router.py`, which catches it and falls back
to the dataset answer rather than failing the request — the user always
gets an answer, and sees a one-line note that the AI call failed.

### `query_router.py` — mode selection per request

Priority order for which API key (if any) is used:

1. `api_key` on the incoming `POST /api/query` request — i.e. a key the
   user pasted into the frontend Settings panel for this call.
2. A server-side "background" key from `config.get_server_key()`, read
   from environment variables (`NVIDIA_API_KEY` / `OPENAI_API_KEY` /
   `ANTHROPIC_API_KEY`, see `backend/.env.example`).
3. Neither present → dataset-only mode.

This is what implements "if someone puts an API key in the frontend it
should answer from that" *and* "there should be an option to also put it
in the background": both paths exist, and a frontend key always wins for
that specific request (so one user's key never affects another's, and a
user experimenting with their own key doesn't need the server restarted).

### `config.py` — background key management

Reads `NVIDIA_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` (and
optional `*_MODEL` overrides, plus `DEFAULT_AI_PROVIDER`) from the process
environment / a `.env` file (via `python-dotenv`, if installed). Exposes:

- `get_server_key(preferred_provider)` → `(provider, api_key)` or `(None, None)`.
- `any_server_key_configured()` → used by `/api/config` so the frontend
  can show whether background AI mode is available without ever exposing
  the key itself to the browser.

### API surface (`main.py`)

| Method | Path                  | Purpose |
|--------|------------------------|---------|
| GET    | `/api/health`          | Liveness check. |
| GET    | `/api/roles`            | List available roles for the role selector. |
| GET    | `/api/config`            | Whether a background key is configured, which provider, total incident count. Never returns the key itself. |
| POST   | `/api/query`              | Main endpoint: `{question, role, api_key?, provider?}` → `{answer, mode_used, provider, matched_count, data, intent}`. |
| GET    | `/api/incidents`          | Raw (role-filtered) incident listing, for building a table/dashboard view outside the chat. |
| POST   | `/api/dataset/reload`      | Regenerates the local DuckDB demo-data warehouse without restarting the process. |

Full interactive schema is always available at `/docs` (Swagger UI) once
the backend is running.

## 5. Frontend module reference

```
frontend/src/
├── main.jsx               React root
├── App.jsx                  Top-level state: role, API key, provider, messages
├── api.js                    Thin axios wrapper around the backend endpoints
├── styles.css                 All styling (CSS variables/tokens at the top)
└── components/
    ├── RoleSelector.jsx        Engineer / Manager / Executive picker
    ├── SettingsPanel.jsx        Provider + API key entry, browser vs background
    ├── ChatWindow.jsx            Message list, sample-question chips, input box
    └── ResultsTable.jsx           Renders the `data` rows returned alongside an answer
```

State of note in `App.jsx`:

- `apiKey` / `provider` are persisted to `localStorage` (`incident-ai-key`,
  `incident-ai-provider`) so a pasted key survives a page refresh but never
  leaves the browser except as a field in the `POST /api/query` body.
- `keySource` (`"browser" | "background" | "none"`) drives the status pill
  in the Settings panel purely from `/api/config`'s `server_key_configured`
  flag plus whether a browser key is set — the browser never needs to know
  what the background key's value is, only that one exists.

`vite.config.js` proxies `/api/*` to `http://127.0.0.1:8000` in dev, so the
frontend code always calls relative paths and needs no environment-specific
base URL or CORS setup locally. In production, deploy `frontend/dist`
behind the same reverse-proxy origin as the API (or update `api.js`'s
`baseURL` to point at the deployed backend origin).

## 6. The dataset

`backend/app/dataset_generator.py` generates ~320 synthetic incidents with
a fixed random seed (deterministic across machines) covering:

`incident_id, title, description, application, environment, region,
severity, status, category, assigned_team, reporter, root_cause,
reported_at, resolved_at, resolution_hours`

Severity and status are weighted to look realistic (most incidents are
Medium/Low severity and already Closed; Critical is rare). A specific
"AWS us-east-1 outage impacting PaymentGateway" incident is seeded 27 days
before the dataset's anchor date so the sample question "Provide details
of the AWS outage reported last month" always resolves to something
concrete — useful for demos and for verifying the keyword-boost logic in
`dataset_engine.py`.

Regenerate or resize it with:

```bash
python -m app.dataset_generator
```

(Edit `generate_incidents(n=...)` in that file to change the row count, or
edit the constant lists at the top — `APPLICATIONS`, `TEAMS`,
`ROOT_CAUSES`, etc. — to change the vocabulary.)

## 7. Design decisions worth knowing

- **Why rule-based instead of embeddings/RAG for the free tier?** The
  brief explicitly asked for minimal ML and no required API key/local LLM.
  A small, fully-inspectable rule engine meets the actual use-case's
  sample questions (time ranges, severity, application, root cause,
  aggregation) without a vector store or model weights to manage.
- **Why is AI mode retrieval-then-generate rather than sending the whole
  dataset to the model?** Keeps token usage small and answers grounded —
  the LLM only ever sees the rows the deterministic filter already judged
  relevant, so it can't "hallucinate" incidents that don't exist in that
  context, and the system prompt explicitly forbids inventing IDs/dates.
- **Why NVIDIA NIM as the default AI provider?** It was the explicitly
  requested "future" provider slot, and NIM's OpenAI-compatible API means
  supporting it added no new SDK — it reuses `langchain_openai.ChatOpenAI`
  with a different `base_url`.
- **Why does a failed AI call fall back instead of erroring?** The product
  goal is "give the best answer possible" — a bad/expired key or a
  transient provider outage should degrade to the dataset answer, not
  break the chat.

## 8. Extending this project

- **Swap the CSV for a real warehouse/lake** (matching the "Data
  Warehouse/Data Lake" key technology in the source use-case deck): replace
  `dataset_engine.load_data()` with a query against your warehouse (e.g.
  via SQLAlchemy or a warehouse-specific connector), keeping the same
  DataFrame-shaped return so the rest of the engine is unchanged.
- **Add MCP/API integrations** (also named in the source deck): expose
  additional LangChain tools to `llm_engine.py` (e.g. a live ticketing
  system lookup) using LangChain's tool-calling agent instead of the
  current single-shot `invoke()` call.
- **Add more roles**: extend `ROLES` in `roles.py`.
- **Add more providers**: extend `PROVIDER_*` maps in `config.py` and the
  `if provider == ...` branch in `llm_engine._build_llm`.
- **Persist chat history server-side**: currently chat history lives only
  in React state (lost on refresh) — add a session store keyed by a
  browser-generated session id if that's needed.
