# Deploy (WIN 9.5)

Two services: the **FastAPI agent** on Render (Docker) and the **Next.js frontend**
on Vercel, both talking to the existing **Supabase** project (Postgres + auth +
pgvector). Do it in this order.

## 0. Prerequisites
- Supabase project (URL, publishable key, secret key, session-pooler DB URL).
- API keys: OpenAI, SerpAPI, OpenWeather. Optional: LangSmith.
- GitHub repo connected to Render and Vercel.

## 1. Supabase — apply migrations
The API auto-creates the LangGraph **checkpointer** tables on boot (`saver.setup()`),
but the app tables are ours. Apply them once against the project (session-pooler DSN):

```bash
for f in supabase/migrations/*.sql; do
  psql "$DATABASE_POOLED_URL" -f "$f"
done
```

This creates `conversations`, `shared_itineraries`, `query_cache` (+ the `vector`
extension) with RLS. Idempotent (`if not exists` / `drop policy if exists`).

## 2. Backend — Render (Docker)
1. **New + → Blueprint**, point at this repo. Render reads `render.yaml` and creates
   the `travel-planner-api` web service (Dockerfile, health check `/readyz`).
2. Set the secret env vars (marked `sync: false`) in the Render dashboard:
   - `OPENAI_API_KEY`, `SERPAPI_API_KEY`, `OPENWEATHER_API_KEY`
   - `SUPABASE_URL`, `SUPABASE_SECRET_KEY`
   - `DATABASE_POOLED_URL` — the **session pooler** URL
     (`aws-0-<region>.pooler.supabase.com:5432`), *not* the direct `db.<ref>` host
     (that one is IPv6-only and won't resolve on Render).
   - `LANGSMITH_API_KEY` (optional)
   - `CORS_ALLOW_ORIGINS` — leave blank for now; set it in step 4.
3. Deploy. Confirm `https://<service>.onrender.com/readyz` returns `{"status":"ready"}`.

## 3. Frontend — Vercel (Next.js)
1. **Add New → Project**, import this repo.
2. **Root Directory = `frontend`** (the Next app lives in a subfolder). Framework
   auto-detects as Next.js; build = `next build`, install = `pnpm install`.
3. Environment variables:
   - `NEXT_PUBLIC_SUPABASE_URL`
   - `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`
   - `API_URL` = the Render backend URL (e.g. `https://travel-planner-api.onrender.com`).
     Server-only; used by the chat/share/locations proxy routes and the public `/i`
     page. (`NEXT_PUBLIC_API_URL` also works but isn't needed — calls are same-origin
     through the proxy routes.)
4. Deploy. Note the Vercel URL (e.g. `https://trip-planner.vercel.app`).

## 4. Wire CORS + Supabase redirect
- **Render** → set `CORS_ALLOW_ORIGINS` to the Vercel URL
  (`https://trip-planner.vercel.app`) and redeploy. Direct browser calls need this;
  the same-origin proxy routes don't, but the public `/i` OG fetch and any direct
  call do — set it regardless.
- **Supabase** → Auth → URL Configuration: add the Vercel URL to **Site URL** /
  **Redirect URLs** so email/password auth cookies work on the deployed origin.

## 5. Smoke test
1. Open the Vercel URL → sign up / sign in.
2. Use the trip form (city autocomplete) → plan a trip → itinerary streams with
   ₹ prices, links, weather, budget verdict.
3. **Share** → open the `/i/<code>` link in an incognito window (no login) → renders.
4. Re-plan the same trip → served from the semantic cache with fresh prices
   (Render logs: `Semantic cache HIT`).

## Notes
- **Migrations on schema change**: re-run step 1 for any new `supabase/migrations/*`.
- **Render free tier** sleeps on idle; first request after idle is slow (cold start).
- **Scaling**: the app is async with a per-process connection pool; scale by adding
  Render instances (each opens its own pool). The session pooler handles the fan-in.
- **CI** (`.github/workflows/ci.yml`) runs the network-free backend tests +
  frontend typecheck/lint on every PR.
