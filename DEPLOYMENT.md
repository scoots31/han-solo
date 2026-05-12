# Han Solo — Deployment Reference

This document covers the infrastructure setup, configuration, and every challenge
encountered deploying the Han Solo stack to Render. Future deploys and maintainers
should read this before touching any of the services.

---

## Services

| Service | Render ID | URL | Notes |
|---|---|---|---|
| han-solo-db | `dpg-d81724vavr4c73b5afig-a` | Internal only | PostgreSQL 16, 5 GB, Oregon |
| han-solo-letta | `srv-d817ak77f7vs73dd1bp0` | `han-solo-letta.onrender.com` | Letta v0.16.7, image-based |
| han-solo-mcp | `srv-d81lla0sfn5c73fcr780` | `han-solo-mcp.onrender.com` | Git/Docker, `Dockerfile.mcp` |

**GitHub:** `scoots31/han-solo` (private)

---

## Letta Service Configuration

Environment vars set on `han-solo-letta`:

| Key | Value | Why |
|---|---|---|
| `PORT` | `8283` | Render injects `PORT=10000` by default — Letta's `startup.sh` picks it up. Set this to force the right port. |
| `LETTA_SERVER_PASSWORD` | (secret) | Bearer token for Letta's API. Han Solo MCP server sends this as `Authorization: Bearer`. |
| `LETTA_PG_URI` | `postgresql+pg8000://...` | Must use `pg8000` dialect prefix — that's the driver bundled in the Letta Docker image. Plain `postgresql://` fails. |
| `LETTA_SERVER_SECURE` | `true` | Enables HTTPS mode. |
| `LETTA_REDIS_HOST` | `localhost` | Skips external Redis — Letta falls back to noop client internally. |

**Image:** `letta/letta:0.16.7`
The correct Docker Hub org is `letta` (not `lettaai` — the old org, stuck at ~v0.5). This is an `env: image` service on Render, so the Dockerfile in this repo is NOT used. Image path is set via the Render API or dashboard.

**Ren agent:** `ren-v1` — created once, persists across deploys.
Agent ID: `agent-44d4a28a-9d66-4aea-b327-2f77b23359ef`

---

## MCP Service Configuration

Environment vars set on `han-solo-mcp`:

| Key | Value |
|---|---|
| `LETTA_URL` | `https://han-solo-letta.onrender.com` |
| `LETTA_API_KEY` | Letta server password (same as `LETTA_SERVER_PASSWORD` on the Letta service) |
| `REN_AGENT_NAME` | `ren-v1` |
| `USER_TOKEN_SCOTT` | Scott's bearer token |
| `USER_TOKEN_TED` | Ted's bearer token |

Dockerfile for this service: `Dockerfile.mcp` (not the root `Dockerfile`).
Render service type: `env: git`, `dockerfilePath: Dockerfile.mcp`.

---

## MCP Endpoint

```
https://han-solo-mcp.onrender.com/mcp
```

All tools are available at this endpoint over Streamable HTTP (MCP protocol).
Auth: `Authorization: Bearer <user_token>`.

Health check (no auth required):
```
https://han-solo-mcp.onrender.com/health
```

Returns `{"status": "ok", "ren_agent": "<id>"}` when fully warmed,
`{"status": "degraded", "ren_agent": "not_initialised"}` if Letta was sleeping at startup.
The degraded state self-heals on the first tool call (lazy init).

---

## Deployment Challenges Log

Every problem hit during the initial deploy, in the order they surfaced. Read these
before debugging anything in this stack.

---

### 1. Wrong Docker Hub org for Letta

**What happened:** Render pulled `lettaai/letta:latest` — the old org, frozen at ~v0.5.x.
**Fix:** Changed to `letta/letta:0.16.7`. The correct org is `letta`, not `lettaai`.
**How:** Render's `han-solo-letta` is an image-based service. The image path must be patched
via the Render API (`PATCH /v1/services/<id>` with `serviceDetails.imagePath`).

---

### 2. pg8000 doesn't accept `sslmode` in the URI

**What happened:** `LETTA_PG_URI=postgresql+pg8000://...?sslmode=disable` caused
`TypeError: connect() got an unexpected keyword argument 'sslmode'`.
**Fix:** Remove `?sslmode=disable` entirely. pg8000 doesn't support that parameter
(it's a psycopg2 convention). The plain URI works fine.

---

### 3. Schema incompatibility after Letta upgrade

**What happened:** After upgrading from lettaai to letta/letta:0.16.7, Letta's alembic
migrations crashed with `relation "agent_source_mapping" already exists`.
The old schema from the lettaai image was incompatible with v0.16.7 migrations.
**Fix:** Wiped and recreated the schema:
```sql
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO han_solo_user;
CREATE EXTENSION IF NOT EXISTS vector;
```
The pgvector extension must be recreated after the schema drop.

---

### 4. Letta bound to wrong port on Render

**What happened:** Render injects `PORT=10000` into all services. Letta's `startup.sh`
uses `PORT="${PORT:-8283}"` — so it picked up Render's value and bound to 10000 instead of 8283.
The health check was configured for 8283, so it always failed.
**Fix:** Set `PORT=8283` explicitly in the Render environment vars to override the injected value.

---

### 5. MCP service built the wrong Dockerfile

**What happened:** Render built the root `Dockerfile` (the Letta server Dockerfile) instead of
`Dockerfile.mcp` for the MCP service.
**Fix:** Set `dockerfilePath: Dockerfile.mcp` via the Render API:
```
PATCH /v1/services/<mcp-service-id>
{"envSpecificDetails": {"dockerfilePath": "Dockerfile.mcp"}}
```

---

### 6. Local `mcp/` package shadowed the MCP SDK

**What happened:** The project had a local directory named `mcp/` containing the tool modules.
Python resolved `import mcp` to the local directory first, so `from mcp.server.fastmcp import FastMCP`
failed with `ModuleNotFoundError: No module named 'mcp.server.fastmcp'`.
**Fix:** Renamed the local package from `mcp/` to `han_solo/` and updated all references.

---

### 7. Private FastMCP `_tool_manager` API

**What happened:** Original `server.py` used `server._tool_manager.add_tool(tool)` to register
tools from separate files. This private API doesn't exist in newer FastMCP versions.
**Fix:** Replaced with a `register(server: FastMCP)` pattern — each tool file wraps its tools
in a `register()` function that decorates them directly on the passed-in server instance.

---

### 8. Missing environment variables on MCP service

**What happened:** The Render MCP service had zero env vars set. `config.py` uses
`os.environ["LETTA_URL"]` (hard KeyError, not `.get()`), so the import crashed at startup
with a nonzero exit code on every deploy. The build succeeded but the deploy always failed.
**Fix:** Set all required env vars via the Render API:
`LETTA_URL`, `LETTA_API_KEY`, `REN_AGENT_NAME`, `USER_TOKEN_SCOTT`, `USER_TOKEN_TED`.

---

### 9. Letta API redirects with 307 (httpx doesn't follow by default)

**What happened:** Letta's API returns 307 redirects on all endpoints (trailing-slash normalization).
httpx's `AsyncClient` doesn't follow redirects by default, so `GET /v1/agents` silently
returned the redirect response instead of the agents list.
**Fix:** `httpx.AsyncClient(follow_redirects=True)` in the server lifespan.

---

### 10. Agent creation fails — `embedding_dim` required

**What happened:** Letta v0.16.7 requires `embedding_dim` in the embedding config. Our
`get_or_create_ren_agent()` payload omitted it. The Letta API returned 422, the exception
was caught, and the server started in degraded state every time.
**Fix:** Added `"embedding_dim": 1024` to the embedding config. Voyage-3 uses 1024 dimensions.
Note: `voyageai` is NOT a valid `embedding_endpoint_type` in this Letta version — use `anthropic`.

---

### 11. Letta sleeping on Render free tier causes startup failure

**What happened:** Render's free tier spins services down after inactivity. When the MCP server
started, Letta was asleep. The 30-second httpx timeout expired, the exception was caught,
and the server ran degraded permanently until the next deploy.
**Fix:** Lazy initialization — `ensure_ren_agent_id()` resolves the agent ID on the first tool
call instead of only at startup. The server stays up in degraded state, then self-heals on
the first request. Health reports degraded until first tool call; this is expected behavior.

---

### 12. `BaseHTTPMiddleware` breaks SSE streaming

**What happened:** The original `BearerAuthMiddleware` extended Starlette's `BaseHTTPMiddleware`.
That middleware buffers the entire response body before passing it through — which destroys
Server-Sent Events (SSE), the streaming transport MCP's Streamable HTTP mode uses.
The MCP client connected, sent the initialize message, and received "Session terminated".
**Fix:** Replaced with a raw ASGI middleware (`__call__(self, scope, receive, send)`) that
passes bytes through without buffering.

---

### 13. FastMCP session manager lifespan doesn't fire when mounted as sub-app

**What happened:** We mounted `server.streamable_http_app()` inside a parent Starlette app
via `Mount("/", ...)`. Starlette doesn't propagate lifespan events to mounted sub-apps,
so the FastMCP session manager's task group was never initialized. Every MCP request
returned 500: `RuntimeError: Task group is not initialized. Make sure to use run()`.
**Fix:** Get the FastMCP Starlette app via `server.streamable_http_app()`, inject our health
route directly into its router, then replace its lifespan with a combined context manager
that runs both our setup (httpx client + Letta agent) AND `server.session_manager.run()`.

---

### 14. FastMCP DNS rebinding protection blocks non-localhost hosts

**What happened:** FastMCP's default `TransportSecuritySettings` enables DNS rebinding
protection with only `localhost`, `127.0.0.1`, and `::1` in the allowed hosts list.
Every request from the Render domain returned `421 Misdirected Request` with body
`Invalid Host header`. This applies even with HTTP/1.1 (not just HTTP/2).
**Fix:** Pass `transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False)`
to the `FastMCP` constructor. Bearer token auth is the security boundary — DNS rebinding
protection is redundant when you have strong per-user auth.

---

## Architecture Notes

### Why the MCP endpoint is `/mcp` (not `/mcp/mcp`)

FastMCP's `streamable_http_app()` creates a Starlette app that routes to `/mcp` internally.
If you mount it at `Mount("/mcp", ...)` in a parent Starlette app, Starlette strips the `/mcp`
prefix, and the sub-app receives `/` — which it doesn't handle. The correct pattern is to
use the FastMCP Starlette app directly (not as a mounted sub-app) and inject any custom routes
into its router before exposing it.

### Why auth uses raw ASGI middleware

Starlette's `BaseHTTPMiddleware` buffers the entire response. SSE streams never complete
from the client's perspective — the first event never arrives. Any auth or observability
middleware on an SSE endpoint must be raw ASGI (implement `__call__(self, scope, receive, send)`
and pass through without buffering).

### Why Letta uses the `anthropic` embedding endpoint type

Letta v0.16.7 supports: `openai`, `anthropic`, `bedrock`, `google_ai`, `google_vertex`,
`azure`, `groq`, `ollama`, `webui`, `webui-legacy`, `lmstudio`, `lmstudio-legacy`,
`llamacpp`, `koboldcpp`, `vllm`, `hugging-face`, `mistral`, `together`, `pinecone`.
Voyage AI is accessed through the `anthropic` endpoint type (Anthropic partners with Voyage),
not as a standalone `voyageai` endpoint. Model: `voyage-3`, dim: `1024`.
