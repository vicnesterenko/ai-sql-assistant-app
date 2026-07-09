# AI SQL Assistant

Deployed on Render (DB and site):
- Frontend: https://ai-sql-assistant-app.onrender.com/
- Endpoints (API docs): https://ai-sql-assistant-db.onrender.com/docs

Deployment is running on the project's [test branch](https://github.com/vicnesterenko/ai-sql-assistant-app/tree/test).

Internal analytics tool that lets non-technical staff ask questions in plain language and get safe, validated SQL results — with automatic risk assessment and human approval for anything expensive or sensitive.

## 1. Project overview

- Users ask analytics questions in natural language via a chat UI.
- The system resolves intent, generates PostgreSQL SQL, statically validates it, and assesses risk.
- `LOW`/`MEDIUM` risk queries execute immediately. `HIGH` risk queries (broad scans, sensitive tables, no `LIMIT`) are routed to a human approval queue before execution.
- Every attempt — successful, blocked, or rejected — is written to an audit log.
- A schema explorer lets users see what data is available before asking.

## 2. Architecture

**Main flow:**

```
user question
  → parse_intent
  → generate_sql
  → validate_sql (syntax, schema, forbidden ops; retries on failure)
  → assess_risk
      ├─ LOW / MEDIUM → execute_query
      └─ HIGH          → request_approval → await_approval → execute_query (if approved)
  → format_result
  → audit (written throughout, not just at the end)
```

## 3. Environment variables

Config is read from a single `.env` file at the repo root (used by `docker-compose.yml` and by the backend directly). Copy the template and fill in what you need:

```bash
cp .env.example .env
```

```dotenv
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
USE_MOCK_LLM=true

DATABASE_URL=postgresql://postgres:postgres@postgres:5432/ai_sql_assistant
QUERY_TIMEOUT_SECONDS=30
MAX_RESULT_ROWS=1000
APPROVAL_TIMEOUT_MINUTES=60
REQUEST_RATE_LIMIT_PER_MINUTE=20

CORS_ORIGINS=http://localhost:5173
VITE_API_BASE=http://localhost:8000
```

Notes:
- `USE_MOCK_LLM=true` runs deterministic mock SQL templates — no OpenAI credits required, good for local testing/demo.
- `USE_MOCK_LLM=false` calls the real OpenAI API and requires a valid `OPENAI_API_KEY`.
- For Docker, `DATABASE_URL` must use host `postgres` (the compose service name), not `localhost`.
- Never commit `.env` with a real `OPENAI_API_KEY` — it's git-ignored on purpose.

## 4. How to run with Docker

```bash
docker compose up --build -d
docker compose exec backend python run_seed.py
```

Then open:
- Frontend: http://localhost:5173
- Backend API docs (Swagger): http://localhost:8000/docs
- Health check: http://localhost:8000/health

## 5. How to stop/reset

```bash
docker compose down
```

Full reset, including the database volume:

```bash
docker compose down -v
```

## 6. Demo questions

Valid against the actual schema (`users`, `transactions`, `loan_applications`):

- How many new users signed up in April 2025, broken down by acquisition channel?
- Show me the top 20 merchants by transaction volume last quarter, excluding internal test accounts.
- What's the average loan approval time for applications submitted in Q1?
- Give me everything from the users table.
- Delete all test users from the database.

Expected behavior:
- The first three are normal aggregate queries — they execute immediately (`LOW`/`MEDIUM` risk).
- "Give me everything from the users table" is a broad, unbounded scan of a sensitive table → classified `HIGH` risk → routed to the approval queue.
- "Delete..." is a mutating statement → blocked at static validation, never reaches execution or approval.

## 7. User roles

Auth is simplified via headers (no OAuth):

- `X-User-Email` — free-text identity
- `X-User-Role` — `analyst` or `approver`

In the frontend, set email/role in the top bar:
- **analyst** — can ask questions and see their own chat/history.
- **approver** — additionally sees the Approval panel and can act on pending requests.

## 8. Approval flow

1. A `HIGH` risk query is saved to the approval queue with status `pending`.
2. The requester sees a "pending approval" state in chat instead of results.
3. An approver can:
   - **Approve** — original SQL runs as-is.
   - **Approve with changes** — approver edits the SQL, then it runs.
   - **Reject** — with a required reason.
4. The requester's session resumes automatically (polling) and shows the final result or rejection reason.
5. If no approver acts within `APPROVAL_TIMEOUT_MINUTES` (default 60), the request is marked expired the next time an approval endpoint is polled (`GET /api/approvals` or `GET /api/approvals/{id}`) — there is no background scheduler. In practice this happens when an approver's Approval panel is open and polling the queue; the requester's own session polling does not trigger it. Once expired, the requester's session picks up the "expired" result on its next poll.

### 8.1 Graph persistence trade-off

`compiled_graph` and `compiled_resume_graph` (`backend/app/graph/workflow.py`) are both compiled with LangGraph's
`MemorySaver()`, which keeps checkpoints in the process's memory only — they do not survive a process restart.

In practice, resumability across the approval boundary does **not** depend on `MemorySaver`. Every node write is
also persisted to the `graph_state_snapshots` table via `save_state`/`load_state`
(`backend/app/services/state_store.py`), and `resume_after_approval()` rebuilds the LangGraph state from that table
(falling back to `sql_approval_queue` + `sql_query_audit` when several pending requests exist in the same
session/thread — see `_rebuild_state_from_approval_row`). This is what actually lets a request survive a backend
restart while waiting on an approver.

The trade-off: this works today, but it's a bespoke persistence layer sitting next to LangGraph's own checkpointing
rather than using it, which is what the assignment asks for ("Use LangGraph's built-in checkpointing"). A production
fix would swap `MemorySaver()` for `langgraph-checkpoint-postgres`'s `AsyncPostgresSaver` (backed by the same
Postgres instance), and let `resume_after_approval()` resume the thread directly from the checkpointer instead of
reconstructing `SQLAssistantState` by hand. That's a bigger change — a new dependency, checkpointer-owned tables,
and a migration of the resume path — so it was left as a documented gap rather than done under this task's scope.

## 9. Safety features

- Only `SELECT` statements are ever executed.
- Forbidden operations (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `TRUNCATE`, `ALTER`, `GRANT`, `REVOKE`, `EXEC`, `CALL`, `CREATE`) are blocked at static validation, before execution or approval.
- SQL is parsed and validated with `sqlglot` (syntax + schema compliance).
- Referenced tables/columns are checked against the allowed schema — unknown references are rejected.
- Large-table scans without `WHERE`, `SELECT *`, sensitive tables/columns, and multi-join/subquery queries raise the risk score.
- Results are capped at `MAX_RESULT_ROWS` (truncation flagged to the user).
- Query execution is time-boxed by `QUERY_TIMEOUT_SECONDS` and cancelled on timeout.
- Every request — including blocked, rejected, and failed ones — produces an audit row.
- Raw query results are never carried into LLM conversation context, only summaries.

## 10. Mock LLM mode

- Default mode (`USE_MOCK_LLM=true`) — for local testing and demos without OpenAI billing.
- Uses deterministic, keyword-matched SQL templates (`backend/app/resources/mock_sql_query.py`) covering the demo questions above, including follow-ups.
- Risk assessment and validation run identically in both modes — they don't depend on the LLM.
- Switch to the real LLM with `USE_MOCK_LLM=false` and a valid `OPENAI_API_KEY`.
- If OpenAI is unavailable, the service logs the error and falls back to deterministic mock SQL templates.

## 11. Project structure

```
backend/
  app/
    api/        # FastAPI routers (sessions, approvals, history, schema, health)
    core/       # settings, logging, security, rate limiting
    db/         # connection pool, schema.sql, seed script
    graph/      # LangGraph nodes, workflow, state
    models/     # Pydantic request/response/state models
    resources/  # SQL query constants, prompts, mock SQL templates
    services/   # business logic (sessions, approvals, audit, execution, LLM)
  pyproject.toml / poetry.lock
  Dockerfile
frontend/
  src/
    components/ # ChatPanel, ApprovalPanel, HistoryPanel, SchemaExplorer, ResultTable
    lib/        # API client
  Dockerfile
docker-compose.yml
.env.example
README.md
```
