# Incident Analytics AI

> **Current implementation reference:** This project now uses DuckDB as its historical source of truth. CSV-centered descriptions below are legacy notes and must not be used to understand the active runtime path.

## Current Architecture

```text
React/Vite frontend
    |
    | HTTP JSON + Bearer session token
    v
FastAPI backend
    |
    +-- auth.py: role sessions and PIN authorization
    +-- intent_graph.py: LangGraph workflow
    +-- dataset_engine.py: deterministic retrieval
    +-- llm_engine.py: optional answer composition
    +-- knowledge_graph.py: NetworkX relationships
    +-- live_incidents.py: read-only Jira connector
    +-- mcp_client.py -> mcp_server.py: governed tools
    |
    v
DuckDB warehouse
  raw_incidents table
  semantic_incidents view
```

The normal historical query path is:

```text
React -> FastAPI -> MCP semantic tools -> semantic_incidents -> response
```

The optional AI path is retrieval-then-generation:

```text
question -> intent classification -> DuckDB retrieval -> role filtering -> LLM composition
```

The LLM never owns retrieval. DuckDB and the deterministic engine remain authoritative.

## Current Technology

| Area | Technology | Role |
|---|---|---|
| UI | React 18, Vite, Axios | Chat, dashboards, reports, live feed |
| API | Python, FastAPI, Uvicorn | REST endpoints and orchestration |
| Storage | DuckDB | Durable local incident warehouse |
| Processing | Pandas | Filtering and aggregation after governed retrieval |
| Semantic contract | `semantic_incidents` view | Canonical fields and approved business access |
| Workflow | LangGraph | Intent-first routing for retrieval and reports |
| NLP | Python regex, keywords, `difflib` | Transparent intent and entity extraction |
| Optional AI | NVIDIA, Gemini, Groq, OpenAI, Anthropic | Narrative composition only |
| AI adapter | LangChain | Consistent provider interface |
| Graph | NetworkX | Root-cause, application, and team relationships |
| Agent protocol | MCP over stdio | Governed access for compatible clients |
| Live source | Jira Service Management REST API | Explicit read-only external feed |

## DuckDB Source of Truth

The active database is `backend/app/warehouse/incident_analytics.duckdb`. On first use, `warehouse.py` generates demonstration incidents in memory, stores them in `raw_incidents`, and creates the `semantic_incidents` view. Application code reads the view, not the raw table and not a CSV file.

The view exposes incident ID, title, application, environment, region, severity, status, category, assigned team, reporter, root cause, reported/resolved timestamps, and resolution hours. Read-only warehouse queries accept only `SELECT` or `WITH` statements.

Use `POST /api/dataset/reload` to regenerate the local DuckDB demonstration data. Run `POST /api/knowledge-graph/sync` afterward to rebuild graph relationships.

## Query Lifecycle

1. The browser sends `POST /api/query` with a question and role.
2. FastAPI validates the Bearer session and role.
3. LangGraph classifies the request as retrieval, report, or relationship analysis.
4. NLP extracts time, severity, status, application, category, team, root cause, incident ID, and resolution/SLA constraints.
5. The deterministic engine retrieves and aggregates data from DuckDB.
6. The role removes fields the user is not allowed to see.
7. NetworkX contributes evidence for relationship questions.
8. If a key exists, LangChain composes a grounded answer from the same retrieved rows.
9. If AI fails, the router returns the deterministic dataset answer.

Supported question patterns include incident lookup, counts, rankings, trends, recurring causes, team workload, resolution-time limits, SLA breaches, and reports.

## AI Key Priority

1. Key supplied in the browser request.
2. Server-side key from `backend/.env`.
3. Dataset-only mode.

Supported providers are NVIDIA NIM, Gemini, Groq, OpenAI, and Anthropic. Provider failures do not make historical analytics unavailable.

## Roles and Data Visibility

- **IT Support Engineer:** full troubleshooting fields, including reporter and root cause.
- **Engineering Manager:** operational ownership and workload fields; reporter identity is hidden.
- **Executive:** high-level incident, application, severity, status, and date information.

Engineer access opens automatically in the local UI. Manager and Executive access uses configured PINs. Sessions are held in memory and expire after eight hours; backend restart clears them.

## Analytics and Knowledge Graph

`GET /api/analytics` returns totals, open/critical/resolved counts, average resolution time, daily/weekly/monthly trends, application/severity/status/team distributions, SLA breach trends, recurring root causes, and graph summary data.

NetworkX derives relationships from DuckDB:

```text
Incident -> AFFECTS -> Application
Incident -> OWNED_BY -> Team
Incident -> HAS_ROOT_CAUSE -> Root Cause
Incident -> OCCURRED_IN -> Environment/Region
```

It runs in process and requires no Neo4j, Docker, or external graph service.

## MCP

`mcp_server.py` exposes the governed semantic catalog, metric summary, approved dimension breakdowns, natural-language analytics, dashboard data, role-filtered incidents, and warehouse regeneration. The MCP server uses stdio and does not expose unrestricted raw-table access. Configuration is in `backend/mcp.json`.

## Live Jira Incidents

The live view is intentionally separate:

```text
LiveIncidents.jsx -> /api/live-incidents -> Jira Service Management REST API
```

It is read-only, engineer-only, fetched on demand, and never inserted into DuckDB. Live analysis additionally requires a server-side AI provider.

The current connector's main issue is authentication: it sends `ATLASSIAN_API_TOKEN` as a Bearer token but does not use `ATLASSIAN_EMAIL`. Jira Cloud API tokens normally require HTTP Basic authentication with the Atlassian email and API token. This can produce `401 Unauthorized`. Also verify token permissions, service-desk JQL, site URL, backend restart after `.env` changes, and engineer session authorization.

Live endpoints:

- `GET /api/live-incidents/status`
- `GET /api/live-incidents`
- `POST /api/live-incidents/analyze`

## Current API Surface

`GET /api/health`, `POST /api/auth/login`, `GET /api/roles`, `GET /api/config`, `POST /api/query`, `GET /api/incidents`, `GET /api/analytics`, `POST /api/dataset/reload`, the semantic endpoints, knowledge-graph endpoints, and live-Jira endpoints are implemented in `backend/app/main.py`.

Interactive API documentation is available at `http://127.0.0.1:8081/docs`.

## Local Runtime

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8081
```

In a second terminal:

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/api` to port `8081`. The frontend build is `npm.cmd run build` and outputs `frontend/dist`.

## Security

The local `.env` contains exposed provider keys, a Jira token, an email address, and role PINs. Revoke and regenerate every exposed credential immediately. Do not commit `.env`, include secrets in documentation, expose server keys to the browser, or use wildcard CORS in production. Use read-only Jira permissions and a production identity system instead of local PINs.

---

## Legacy Notes

## 1. Project Overview

Incident Analytics AI is a conversational incident-management analytics platform. Users ask questions in plain English and receive incident records, trend analysis, root-cause insights, workload analysis, downloadable reports, and role-specific answers.

The system works without an AI API key through a deterministic dataset engine. Optional AI providers improve answer composition while using the same retrieved incident data.

## 2. Technology Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite, Axios |
| Backend | Python, FastAPI, Uvicorn |
| Data | DuckDB, Pandas, synthetic incident dataset |
| AI orchestration | LangChain, LangGraph |
| AI providers | NVIDIA NIM, OpenAI, Anthropic, and configured compatible providers |
| Knowledge graph | NetworkX |
| Integration | MCP server and MCP client |
| Styling | Hand-written CSS |

## 3. Architecture

```text
React Frontend
    |
    | HTTP / JSON
    v
FastAPI Backend
    |
    +-- Authentication and roles
    +-- Query router
    +-- Dataset engine
    +-- Optional LLM engine
    +-- Analytics services
    +-- Knowledge graph
    +-- MCP client/server
    |
    v
DuckDB Incident Warehouse
```

The frontend communicates with the backend through REST APIs. The backend identifies query intent, extracts filters, retrieves incident data, applies role-specific visibility rules, and optionally sends the filtered results to an AI provider for narrative composition.

## 4. Query Processing

1. Receive a natural-language question.
2. Identify the selected user role.
3. Detect intent: lookup, search, trend, report, or relationship analysis.
4. Extract date, severity, status, application, category, and team filters.
5. Query the governed incident data.
6. Apply role-specific visibility rules.
7. Return structured records and a natural-language answer.
8. Optionally use an AI provider to improve the answer wording.

Dataset mode is the fallback when no API key is configured or an AI provider fails.

## 5. User Roles

### IT Support Engineer

Receives detailed technical information, including incident identifiers, root causes, applications, assigned teams, reporter information, and resolution details.

### Engineering Manager

Receives operational information including team workload, trends, application impact, severity, and status. Reporter identity is restricted.

### Executive

Receives high-level business and risk information such as critical incidents, affected applications, status, and major trends. Technical and reporter-level details are reduced.

## 6. Frontend Structure

```text
frontend/
├── index.html
├── package.json
├── vite.config.js
└── src/
    ├── main.jsx
    ├── App.jsx
    ├── api.js
    ├── styles.css
    └── components/
        ├── AnalyticsDashboard.jsx
        ├── ChatHistory.jsx
        ├── ChatWindow.jsx
        ├── DatasetPanel.jsx
        ├── KnowledgeGraph.jsx
        ├── LiveIncidents.jsx
        ├── LoginGate.jsx
        ├── MarkdownView.jsx
        ├── ReportDownload.jsx
        ├── ResultsTable.jsx
        ├── RoleSelector.jsx
        └── SettingsPanel.jsx
```

`App.jsx` manages application state, sessions, roles, analytics, authentication, and views. `ChatWindow.jsx` provides the conversational interface. `AnalyticsDashboard.jsx` presents metrics and charts. `styles.css` contains the visual design system and responsive layout rules.

## 7. Backend Structure

```text
backend/
├── mcp.json
├── requirements.txt
└── app/
    ├── main.py
    ├── auth.py
    ├── config.py
    ├── dataset_generator.py
    ├── knowledge_graph.py
    ├── live_incidents.py
    ├── mcp_client.py
    ├── mcp_server.py
    ├── models.py
    ├── nlp.py
    ├── roles.py
    ├── semantic_layer.py
    ├── warehouse.py
    ├── engines/
    │   ├── dataset_engine.py
    │   ├── intent_graph.py
    │   ├── llm_engine.py
    │   └── query_router.py
    └── warehouse/
        └── incident_analytics.duckdb
```

## 8. Important Backend Modules


## 9. API Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Backend health check |
| `GET /api/roles` | Available roles |
| `GET /api/config` | Configuration and dataset status |
| `GET /api/analytics` | Dashboard analytics |
| `GET /api/incidents` | Incident listing |
| `POST /api/query` | Natural-language query |
| `POST /api/dataset/reload` | Reload or regenerate data |
| `GET /api/knowledge-graph/topology` | Knowledge graph data |
| `POST /api/knowledge-graph/sync` | Rebuild relationships |
| `GET /docs` | FastAPI Swagger documentation |

## 10. Local Setup

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8081
```

Backend URL: `http://127.0.0.1:8081`

API documentation: `http://127.0.0.1:8081/docs`

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Frontend URL: `http://127.0.0.1:5173`

The Vite development server proxies `/api` requests to the backend on port `8081`.

## 11. Optional AI Configuration

Dataset mode requires no API key. For AI mode, configure one provider in `backend/.env`:

```env
NVIDIA_API_KEY=replace-with-new-key
NVIDIA_MODEL=replace-with-model
DEFAULT_AI_PROVIDER=nvidia
```

Never include real keys in documentation, screenshots, commits, or chat messages. Any credentials previously exposed in `.env` should be revoked and regenerated.

## 12. Example Queries

```text
What incidents were reported yesterday?
Show all critical incidents from the last 90 days.
Which applications generated the most incidents this quarter?
Which team has the highest open incident workload?
Identify recurring incidents and their root causes.
Show high-severity PaymentGateway incidents in production.
Generate a report on critical incidents from the last 90 days.
```

## 13. Security and Operations Notes


## 14. Project Purpose

The project provides an accessible incident analytics experience for technical and business users. Its main design principle is grounded analysis: deterministic retrieval and governed data remain the source of truth, while optional AI improves explanation and presentation.
