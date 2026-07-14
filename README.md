# AI SQL Assistant

Internal analytics tool that converts natural-language questions into safe PostgreSQL `SELECT` queries, validates them, assigns a risk level, and routes high-risk requests to a human approver.

## 1. Deployment

- Frontend: https://ai-sql-assistant-app.onrender.com/
- API docs: https://ai-sql-assistant-db.onrender.com/docs
- Repository: https://github.com/vicnesterenko/ai-sql-assistant-app
- Branch described in this README: `main` — verify Render is deployed from `main` before a demo.

## 2. Run locally

```bash
cp .env.example .env         # set USE_MOCK_LLM=true to skip OpenAI credits
docker compose up --build -d
docker compose exec backend python run_seed.py
```

- Frontend: http://localhost:5173 · Swagger: http://localhost:8000/docs
- Logs: `docker compose logs -f backend|frontend`
- Reset DB: `docker compose down -v && docker compose up --build -d && docker compose exec backend python run_seed.py`

Auth is simplified via headers: `X-User-Email`, `X-User-Role` (`analyst` | `approver`).

## 3. Workflow

```text
user question → parse_intent → generate_sql → validate_sql
    ├─ invalid, retries left → generate_sql (retry loop)
    └─ valid → assess_risk
        ├─ LOW / MEDIUM → execute_query → format_result
        └─ HIGH → request_approval → await_approval → (graph stops)

approval decision → load saved state → await_approval
    ├─ approved → execute_query → format_result
    └─ rejected / expired → format_result
```

`main` does **not** use LangGraph's native `interrupt()` / `Command(resume=...)`. Instead, `request_approval_node()` writes an approval row, the graph ends at `await_approval`, state is persisted via a custom `state_store` service, and `resume_after_approval()` reloads/rebuilds state to drive a separate `compiled_resume_graph`. It works, but it's a custom resume mechanism, not LangGraph's built-in checkpointing pattern.

**Risk thresholds** (deterministic, no LLM involved): `HIGH` score ≥ 4, `MEDIUM` score ≥ 2 or validation warnings present, else `LOW`. Signals: broad `SELECT *`/`table.*`, unfiltered large tables, missing `LIMIT`, sensitive columns/tables, multiple joins, subqueries. `COUNT(*)` is correctly excluded from the "broad projection" signal.

**SQL safety**: single-statement, read-only expressions only; `sqlglot` AST validation; schema-compliance check; mutating/admin statements blocked (`INSERT/UPDATE/DELETE/DROP/TRUNCATE/ALTER/CREATE/GRANT/REVOKE/CALL/EXEC/SELECT...FOR UPDATE`); read-only DB transaction with timeout and row cap; approver-modified SQL is revalidated before execution. The LLM is never the security boundary — validation and DB permissions are.

**Context**: only recent safe chat history and the last successful SQL (not raw rows) are fed back into the intent parser, so follow-ups work without leaking result data into the LLM context window.

## 4. Compliance with the assignment

Full spec: [`ai-sql-assistant-assignment.md`](ai-sql-assistant-assignment.md).

### ✅ Done

- Natural-language → SQL via explicit LangGraph nodes with conditional routing (parse_intent, generate_sql, validate_sql, assess_risk, request_approval, await_approval, execute_query, format_result, handle_error).
- LLM and deterministic mock modes.
- AST-based static validation, schema compliance, forbidden-operation blocking, 3 correction retries.
- Deterministic LOW/MEDIUM/HIGH classification with documented heuristics.
- Approval queue for HIGH: approve, approve-with-modified-SQL (diff shown), reject-with-reason; modified SQL is revalidated.
- Read-only execution, query timeout, row cap + truncation notice, execution-error retry back into `generate_sql`.
- Audit persistence for every attempt, including blocked/failed ones.
- Session history, follow-up context resolution, raw rows excluded from LLM context.
- Frontend: chat panel with SQL block, risk badge + tooltip, sortable/paginated result table, CSV export; approval panel; history panel; schema explorer.
- Per-session in-memory rate limiting (429 on breach).
- Docker Compose local startup with seed data.

### ⚠️ Deviates from spec

| Area | Spec expects | Current behavior |
|---|---|---|
| MEDIUM flow | warn → wait for requester ack → execute | executes immediately, warning shown after the fact |
| Persistence | LangGraph built-in checkpointing (`interrupt()`/`Command(resume=...)`) with `AsyncPostgresSaver` | `MemorySaver()` (lost on restart) + custom `state_store` PostgreSQL persistence and manual resume graph |
| Chat response | SSE streaming preferred, typed `AssistantResponse` | plain JSON (`{"response": ...}`), no `response_model` on `POST /messages`, no streaming |
| Approval expiry | timeout policy enforced | lazy: only evaluated when an approval endpoint is polled, no background scheduler |
| Auth | none required beyond header roles, but production-ready session ownership implied | headers only, no session-ownership check — fine for the assignment, not for production |
| Rate limiting | per-session limit | in-memory only, not shared across processes/workers |

### ❌ Not done

- Automated tests / CI (no `tests/`, no GitHub Actions workflow).

## 5. Priorities to close the gaps

1. **P0** — MEDIUM acknowledgment step; tests for LOW/MEDIUM/HIGH flows, approval resume after restart, and execution-error retry after approval.
2. **P1** — Replace `MemorySaver` + custom resume with `AsyncPostgresSaver` and native `interrupt()`/`Command(resume=...)`; add a scheduler for approval expiry; typed response models + SSE streaming on `POST /messages`; session ownership checks.
3. **P2** — Redis-backed rate limiting; CI (lint/type/test/build); dedicated least-privilege read-only DB role; request correlation IDs; `EXPLAIN (FORMAT JSON)`-based risk estimation; schema introspection instead of static metadata.

## 6. API overview

| Group | Endpoints |
|---|---|
| Sessions | `POST /api/sessions` · `POST/GET /api/sessions/{id}/messages` · `DELETE /api/sessions/{id}` |
| Approvals | `GET /api/approvals?status=pending` · `GET /api/approvals/{id}` · `POST /api/approvals/{id}/approve` · `POST /api/approvals/{id}/reject` |
| History & schema | `GET /api/history` · `GET /api/history/{audit_id}` · `GET /api/schema` |

## 7. Project structure

```text
backend/app/
  api/          FastAPI routers
  core/         settings, logging, security, rate limiting
  db/           asyncpg pool, schema, seed data
  graph/        LangGraph state, nodes, workflow
  models/       Pydantic API and domain models
  resources/    prompts and mock SQL templates
  services/     LLM, validation, risk, execution, approvals, audit, state store
frontend/src/
  components/   chat, approval, history, result, SQL, schema UI
  lib/          API client and TypeScript types
docker-compose.yml · .env.example · ai-sql-assistant-assignment.md
```
