# Architecture

A LangGraph trip-planning agent behind a FastAPI SSE API, with a Next.js frontend
and Supabase (Postgres + auth + pgvector). The through-line is **reliability**:
every price/flight/hotel shows its source and freshness, unverifiable facts are
dropped, and anything checkable (budget, currency, weather labelling, airport codes)
is computed in code — never trusted from the LLM.

```
Browser (Next.js on Vercel)
  │  Supabase email/password auth (cookies); same-origin /api/* proxy routes
  ▼
FastAPI (Render, Docker)  ── Supabase JWT verified server-side (no impersonation)
  │
  ├─ POST /chat/stream ── semantic cache check ──▶ HIT: reuse skeleton + live prices
  │                        │ MISS
  │                        ▼
  │                   LangGraph agent:  chat_node ⇄ tools → synthesize → verify
  │                        │
  │                        ├─ tools: flights/hotels (SerpAPI), weather (OpenWeather +
  │                        │         Open-Meteo), attractions/maps, web, youtube
  │                        ├─ synthesize: structured source-bound Itinerary (schema.py)
  │                        └─ verify: prune unsupported facts + recompute budget
  │
  ├─ GET /shared/{code} ── public frozen itinerary snapshot
  └─ GET /locations ── airport autocomplete (offline airportsdata)
  │
  ▼
Supabase Postgres
  ├─ LangGraph checkpointer tables (conversation state)
  ├─ conversations (user↔thread, RLS)
  ├─ shared_itineraries (public snapshots by short code, RLS)
  └─ query_cache (pgvector: slot-aware semantic response cache)
```

## Reliability layers (plan-v2.md WINs)
- **Structured, source-bound itinerary** (WIN 3): every fact declares its `source_tool`.
- **Deterministic compute** (WIN 4): budget = cheapest flight × travelers + cheapest
  hotel × nights, in code; currency stamped USD, shown in the user's currency via a
  live FX rate.
- **Tool hardening + freshness** (WIN 5): validated tool output, retries, per-category
  TTLs, `retrieved_at` stamps, forecast-vs-seasonal weather labelling.
- **Injection defense** (WIN 6): tool text is neutralized/fenced before the model.
- **Value verifier + abstention** (WIN 7): a fact whose price/name isn't in the tool
  output is removed; a removed category becomes an honest disclaimer.
- **Observability** (WIN 8): LangSmith tracing + per-turn token/cost accounting.
- **Cost & caching** (WIN 8.5 / 9.2): slimmed tools, prompt-cache-friendly prefix,
  parallel tool calls, and a slot-aware semantic response cache on pgvector (prices
  always re-fetched, so a hit is never stale).

## Frontend
Next.js App Router. Server components read the Supabase session (cookies) for
auth-gated data; the browser calls the backend through **same-origin proxy routes**
(`/api/chat/stream`, `/api/share`, `/api/locations`) that inject the token
server-side — no client token, no CORS. The `ItineraryView` is the trust surface:
per-fact source chips, "as of" freshness, ₹+$ budget with an over/under verdict,
booking/map links, and verifier disclaimers. Public shares render read-only at
`/i/[shortCode]` (ISR, login-free, OG preview).

## Key files
| Area | Files |
|---|---|
| Agent graph | `backend.py`, `prompts.py`, `tools.py` |
| Reliability | `schema.py`, `compute.py`, `verifier.py`, `enrich.py`, `fx.py`, `locations.py`, `cache.py` |
| API | `api/main.py`, `api/streaming.py`, `api/auth.py`, `api/db.py`, `api/schemas.py` |
| DB | `supabase/migrations/*.sql` |
| Frontend | `frontend/app/*`, `frontend/components/*`, `frontend/lib/*` |
| Deploy | `Dockerfile`, `render.yaml`, `.github/workflows/ci.yml`, `docs/deploy.md` |
