# WIN 9 — Productionization scope (FastAPI + Supabase + Next.js)

> **Status: PLAN ONLY — do not implement until reviewed.**
> Sibling to `../plan-v2.md` WIN 9. Reuses the conventions from the Swarnika
> `SPEC.md` (anti-slop, server/client discipline, caching philosophy, perf
> targets, definition-of-done), adapted for a **conversational AI agent with a
> Python/LangGraph backend** — so most content is dynamic/user-specific, not
> ISR-cacheable like an e-commerce catalogue.

---

## 1. Goal

Turn the LangGraph agent (WINs 1–8.5, all metrics 100% on `gpt-5.4-nano`,
$0.0046/itinerary) into a real multi-user web service:

- **FastAPI + SSE** backend serving the agent (streamed answer + structured itinerary + verifier flags).
- **Supabase** for auth (email + password), Postgres conversation history (RLS), and pgvector (the deferred WIN 8.5 semantic cache).
- **Next.js + shadcn** frontend that renders the structured itinerary with source chips, freshness, verifier flags, and a budget breakdown — **retiring Streamlit**.
- A **cleanup pass** removing Streamlit, dead code, and AI slop.

The reliability work is the point of this UI: every price/flight/hotel shows **where it came from and how fresh it is**, and unverifiable facts are visibly flagged.

---

## 2. Architecture

```
┌────────────────────┐    Bearer JWT (Supabase)     ┌──────────────────────┐
│  Next.js frontend   │ ───────────────────────────▶ │  FastAPI backend      │
│  (Vercel)           │   POST /chat/stream (SSE)    │  (LangGraph agent)    │
│  @supabase/ssr auth │ ◀─────────────────────────── │  verifies JWT server- │
└─────────┬──────────┘   token/itinerary/done events │  side, user.id only   │
          │                                           └───────────┬──────────┘
          │ Supabase Auth (login/signup, session)                 │
          ▼                                                        ▼
   ┌─────────────────────────────── Supabase ───────────────────────────────┐
   │  Auth (email+password)  │  Postgres: LangGraph checkpointer +           │
   │                          │  conversations table (RLS) + query_cache      │
   │                          │  (pgvector, WIN 8.5 semantic cache)           │
   └───────────────────────────────────────────────────────────────────────┘
```

**Boundary decisions (rationale):**
- The **agent is Python/LangGraph**, so it stays behind **FastAPI** — not rewritten as Next.js API routes.
- **Next.js talks to Supabase only for auth** (get a session/JWT). All agent + conversation calls go to **FastAPI**, which owns the checkpointer schema. One clean seam.
- **Auth = Bearer JWT in the `Authorization` header** → per OX `python-csrf-prevention`, **no CSRF machinery needed** (browsers don't attach `Authorization` cross-origin).

---

## 3. Sub-phases (each a branch + PR, per the per-win workflow)

| Phase | Title | Deliverable |
|---|---|---|
| **9.0** | **Cleanup** (do first) | Retire Streamlit; remove dead code / AI slop / valueless comments; prune unused deps. Clean base to build on. |
| **9.1** | FastAPI + SSE + persistence + auth | `POST /chat/stream`, health checks, Supabase JWT verification (no-impersonation), `AsyncPostgresSaver` + `conversations` table + RLS. |
| **9.2** | Semantic cache (pgvector) | The deferred WIN 8.5 slot-aware, volatility-tiered response cache on Supabase pgvector, checked at FastAPI entry. Cache-correctness = 100%. |
| **9.3** | Next.js frontend | shadcn scaffold, auth UI, sidebar + chat, streamed **Itinerary View**, conversation switcher. Mirrors the RAG frontend layout. Retire `frontend.py`. |
| **9.4** | Shareable itineraries | "Share" → frozen public snapshot; ISR `/i/[shortCode]` page (chat-free, login-free) + OG preview + "copy as text". |
| **9.5** | Deploy + docs | Dockerfile (FastAPI → Render), Vercel config (Next.js), env docs, `docs/architecture.md`, CI wiring. |

Sequencing: 9.0 → 9.1 → (9.2 ∥ 9.3) → 9.4 → 9.5. 9.2 and 9.3 are independent once 9.1 lands.

---

## 4. Phase 9.0 — Cleanup (your requested step, done first)

Remove before building new UI, so we don't port slop forward.

**Streamlit retirement:**
- Delete `frontend.py` (the Streamlit UI).
- Remove `streamlit` and Streamlit-only deps from `requirements.txt` (audit: `altair`, `pydeck`, `narwhals`, `pyarrow`, `blinker`, `tornado` if only Streamlit pulled them).
- `backend.get_chatbot()` stays (the FastAPI layer uses it); only the Streamlit consumer goes.

**Dead code / decommissioned code:**
- `sqlite-vec` in `requirements.txt` — unused since WIN 1; remove (pgvector on Supabase is the vector store).
- The LLM-invoked `calculator` tool (`tools.py`) — budget is now deterministic (`compute.py`); confirm nothing depends on it, then remove from `ALL_TOOLS` and delete the tool.
- Old root `chatbot.db` (orphaned since the WIN 1 DB-path move) — remove from the working tree (already gitignored).
- Any remaining `booking_token`/fields the itinerary never surfaces — keep only what the UI/booking deep-links use.

**AI-slop sweep (apply the SPEC §9 rules to the existing Python too):**
- Delete unused imports/vars/functions across all modules (`ruff` + a dead-code pass).
- Remove section-header comments (`# ===== ... =====`) and comments that restate the code.
- Remove any commented-out code.
- Keep only WHY-comments and the docstrings that explain non-obvious rationale.

**Guardrail:** the full eval + all network-free tests must stay green after cleanup (no behavior change). Run `python -m evals.run_eval --version cleanup` to confirm all 7 metrics still 100%.

---

## 5. Phase 9.1 — FastAPI backend

### Endpoints
| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/chat/stream` | JWT | Send a message; stream the turn (SSE). |
| `GET` | `/conversations` | JWT | List the user's threads (id, title, updated_at). |
| `GET` | `/conversations/{thread_id}` | JWT | Load one thread's messages + latest itinerary (ownership-checked). |
| `POST` | `/conversations` | JWT | Start a new thread. |
| `GET` | `/healthz`, `/readyz` | none | Liveness / readiness. |

### SSE event protocol (`/chat/stream`)
Ordered events, one JSON payload each:
1. `token` — streamed assistant text chunks (the concise answer).
2. `tool` — tool-execution progress (name + status), for a live "researching…" indicator.
3. `itinerary` — the final structured `Itinerary` (facts + budget + provenance + verification).
4. `verification` — flags/disclaimers (or folded into `itinerary`).
5. `done` — turn complete (thread_id, cost/usage optional).
6. `error` — generic message only (details logged server-side).

Consumed by the frontend via `fetch()` + `ReadableStream` (not `EventSource`, which can't send an `Authorization` header or a POST body).

### Auth (Supabase JWT, no-impersonation)
- A FastAPI dependency verifies the Supabase JWT **server-side** (Supabase JWKS / `supabase-py`), extracts `user.id`.
- **`user.id` is the only identity source** — request bodies never carry a user id (RAG `api/auth.py` pattern).
- Thread access is authorized against the `conversations` table (`user_id` must match); a mismatch → 404 (not 403, to avoid leaking existence).

### Persistence (Supabase Postgres)
- **Message state:** LangGraph `AsyncPostgresSaver` (near drop-in for the current `SqliteSaver`) on the Supabase pooled connection — handles concurrency + survives restarts.
- **User ↔ thread mapping:** a `conversations` table (`id` = thread_id UUID, `user_id`, `title`, `created_at`, `updated_at`) with **RLS** (`user_id = auth.uid()`), as defense-in-depth on top of the app-level ownership check.
- Title: derived from the first user message (or the destination once known).

### Security (OX-aligned — see §10)
- No traceback/exception text in responses; `logger.exception()` server-side, generic client message (`python-sensitive-data-protection`).
- CSP + HSTS security-headers middleware; reject `\r`/`\n` in any header derived from input (`python-server-hardening`).
- Secrets from env only (already via `settings.py`); Supabase service key server-side only.
- Parameterized SQL for the `conversations`/`query_cache` tables (`python-sql-injection-prevention`).
- The existing tool SSRF surface (SerpAPI/OpenWeather are hardcoded/config hosts) is unchanged; no user-controlled outbound URLs.

---

## 6. Phase 9.2 — Semantic cache (pgvector) — deferred from WIN 8.5

- **Volatility tiering:** flight/hotel *prices* are never served from a stale response cache — only the **stable skeleton** (destination knowledge, attractions, day structure) is cached; live quotes are re-fetched (WIN 5 freshness).
- **Slot-aware key (not embedding-only):** hard-match the canonical tuple (`destination`, normalized `date_range`, `travelers`, `budget_band`) + semantic match on the softer intent — prevents serving a "$2000 plan" for a "$5000 request".
- **Backend:** Supabase **pgvector**; `query_cache(slot_key, intent_embedding vector, response_skeleton jsonb, created_at, ttl, hit_count)`; lookup on `slot_key` + `intent_embedding <=> ?` above a tuned threshold, within TTL.
- **Integration:** checked at FastAPI entry; a hit reuses the skeleton and re-fetches live quotes.
- **Success metric:** cache-correctness = **100%** (every hit's slots match the request; volatile facts always re-fetched) — a hit serving stale/mismatched data is build-blocking, not a tradeoff. Verified by unit tests + a repeat-query demo (cost → ~$0 on a hit).

---

## 7. Phase 9.3 — Next.js frontend

### Tech stack (locked — mirrors SPEC §3, trimmed to what a chat app needs)
- **Next.js 15** (App Router, Server Components by default), **TypeScript strict**, **Node 20+**, **pnpm**.
- **Tailwind CSS** + **shadcn/ui**, **Lucide** icons (import per-icon), **next/font**.
- **State:** Zustand (client UI: active-thread, streaming state) · TanStack Query (conversation list, mutations) · React Hook Form + Zod (auth forms).
- **Supabase:** `@supabase/ssr` (session cookies refreshed in `middleware.ts`).

### Scaffold command (RTL dropped per decision)
```bash
pnpm dlx shadcn@latest init --preset b1x9M8ZeJW --template next --pointer
```
The `b1x9M8ZeJW` preset carries the **color theme** (so no separate design system needed); `--pointer` sets the shadcn pointer style. `--rtl` removed (LTR only).

### Layout — mirror the RAG frontend (reference: `../../RAG/frontend`)
Reuse the proven structure from the RAG app almost verbatim:
- **App shell** (`app/(app)/layout.tsx`): shadcn **`Sidebar` (`collapsible="icon" variant="inset"`) + `SidebarInset`** main panel, with a floating `SidebarTrigger` — no top navbar. Sidebar holds logo, nav, **conversation history**, theme toggle, and user menu (see `RAG/frontend/components/layout/app-sidebar.tsx`).
- **Chat window on the right** inside `SidebarInset`.
- **Auth:** `@supabase/ssr` — `createClient()` server helper, `getUser()`/`getSession()`, redirect to `/login`; a `middleware.ts` (RAG's `proxy.ts`) refreshes the session and gates routes.
- **Backend calls:** one typed `lib/api.ts` (RAG pattern) — every call carries `Authorization: Bearer <token>`; the SSE reader parses `event:`/`data:` frames exactly as `RAG/frontend/lib/api.ts` `streamChat` does.
- **Libs (match RAG):** Base UI + shadcn, `next-themes` (light/dark), `sonner` (toasts), `react-markdown` + `remark-gfm` (render the assistant's prose). Zustand/TanStack Query only where genuinely needed (active-thread/streaming state; conversation-list refetch).
- **Mobile responsive (required):** the shadcn `Sidebar` collapses to a drawer on mobile; verify the chat + Itinerary View at 375px. (No PWA/offline.)

### Folder structure (adapted from SPEC §4)
```
frontend/
  src/
    app/
      (auth)/login, (auth)/signup
      (app)/chat, (app)/chat/[threadId], (app)/account
      layout.tsx, error.tsx, not-found.tsx
    components/
      ui/            # shadcn primitives
      chat/          # composer, message list, streaming bubble, tool-progress
      itinerary/     # ItineraryView + fact cards (signature element)
      shared/        # header, sidebar/thread switcher, skeletons
    lib/
      api/           # FastAPI client (SSE fetch), typed
      auth/          # supabase client, session helpers, guards
      validators/    # Zod schemas (mirror the Python itinerary schema)
      utils/         # cn(), formatters
    stores/          # Zustand
    types/           # shared TS types (Itinerary, etc.)
    config/          # env validation (Zod)
```

### The Itinerary View (signature element — analogous to SPEC's Spec Card)
Renders the structured `Itinerary` as the trust surface:
- **Fact cards** (flights / hotels / attractions / weather): each shows a **source chip** (`from search_flights`), a **freshness "as of" time**, and — for prices — a "reverify before booking" affordance.
- **Verifier flags:** any `verification.disclaimers` / removed-fact notes shown as a visible ⚠️ banner ("flights could not be verified and were omitted").
- **Weather:** the `is_forecast` label surfaced ("Seasonal averages — not a live forecast").
- **Budget breakdown:** the code-computed items + total (WIN 4), clearly "computed", not model-guessed.
- **Day-by-day plan:** the free-text `days[].activities` as an itinerary timeline.
- **Booking:** flight/hotel `link`s open the provider in a new tab (recommend-only; no in-app booking — plan §8).

### Server/Client discipline (SPEC §6)
- Default Server Components. The **chat stream + composer** is the client island (needs streaming state + event handlers); the **thread list / account / itinerary render** are Server Components fed by the FastAPI client. Push `'use client'` as far down as possible; the page is never `'use client'`.
- Read data in Server Components; mutate via server actions/route handlers proxying FastAPI. No `useEffect` data fetching for page-level data.

### Caching strategy (SPEC §7, adapted — this is a chat app)
| Surface | Strategy | Rationale |
|---|---|---|
| Landing page (if any, Q1) | Static / ISR 3600 | SEO, rarely changes |
| Auth pages | Static | No per-user data |
| Chat, thread, account | **Dynamic `no-store`** | User-specific, must be fresh |
| Streamed turn | SSE, uncached | Live |
| Conversation list (TanStack) | `staleTime` ~30s, `invalidateQueries` after new message | Cheap freshness |
| Shareable itinerary (if any, Q2) | ISR + `revalidateTag` on regen | Mostly static once made |

Honest note: the SPEC's ISR/catalogue caching mostly **doesn't apply** here — a chat app is dynamic by nature. The real caching win lives server-side in the **WIN 9.2 semantic cache**, not Next.js route caching.

### Performance standards (SPEC §8 — adopted as pass/fail)
LCP < 2.0s · CLS < 0.05 · initial JS < 150 KB gz · Lighthouse Perf ≥ 90 / A11y ≥ 95 · WebP/AVIF via `next/image` · skeletons not spinners · per-icon imports · `@next/bundle-analyzer` before merge · defer analytics with `next/script lazyOnload`. (A chat route is interactive, so the client island is unavoidable — keep it lean; the shell/history stays server-rendered.)

---

## 7b. Phase 9.4 — Shareable itineraries (privacy-safe)

Requirement: share a read-only itinerary over WhatsApp/Slack **without** exposing the private
chat and **without** the recipient logging into the app.

**Design — frozen snapshot + capability URL:**
- A **"Share"** action snapshots the current structured itinerary into
  `shared_itineraries(short_code, snapshot jsonb, title, owner_user_id, created_at, revoked)`.
  The snapshot is an **immutable copy** — it does not reference the chat/thread, so it can never
  surface conversation content.
- `short_code` is unguessable (`secrets.token_urlsafe`) — a **capability URL**, not enumerable.
- Public route **`/i/[shortCode]`** (Next.js **ISR**, no auth) fetches the snapshot via a public
  `GET /shared/{short_code}` (snapshot only; `410` if revoked) and renders the Itinerary View
  read-only. The recipient **never logs in and never sees anything but that one itinerary.**
- **Revoke:** owner can revoke (→ `revoked=true` → page 410); on-demand `revalidateTag` clears ISR.

**WhatsApp/Slack sharing — both modes:**
- **Rich link preview:** `/i/[shortCode]` sets OpenGraph/Twitter meta (title `"5-day Tokyo · $2,219"`,
  description, an OG image) so pasted links render a card.
- **Copy as text:** a button generates a WhatsApp-friendly plain-text itinerary (destination, dates,
  flight + price, hotel + rate, day-by-day, booking links) to paste directly — the "text with
  embedded links" format.

**Privacy guarantees (directly addressing the concern):** snapshot is chat-free and login-free;
capability URL is unguessable; revocable; frozen at share time so later chat edits never leak.

---

## 8. Code quality — anti-slop (SPEC §9, adopted verbatim)

Applies to **all** new code and the 9.0 cleanup: no dead code, no commented-out code, no `console.log`/stray `print`, no `any`, no premature abstraction, no single-use utils, WHY-not-WHAT comments, one component per file, `<Name>Props`, early returns, functions ≤ ~50 lines, files ≤ 300 lines / components ≤ 150, Tailwind-only + `cn()`, Zod as source of truth. Definition-of-done gate per SPEC §19 (adapted: `tsc --noEmit`, ESLint, `pnpm build`, Lighthouse ≥ 90 on the touched route, mobile at 375px).

---

## 9. Environment variables (additions)
```
# Frontend (Next.js)
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
NEXT_PUBLIC_API_URL=            # FastAPI origin (https in prod)

# Backend (FastAPI) — added to settings.py
SUPABASE_URL=
SUPABASE_SERVICE_KEY=           # server-only, RLS bypass for checkpointer
SUPABASE_JWT_SECRET=            # or JWKS URL, for server-side JWT verification
DATABASE_POOLED_URL=            # Supabase pooler (AsyncPostgresSaver)
CORS_ALLOW_ORIGINS=             # the Next.js origin(s)
```
All validated in `settings.py` (backend) / `config/env.ts` (frontend, Zod). Secrets never in `NEXT_PUBLIC_*`.

---

## 10. Security checklist (OX guideline IDs)
- `python-sensitive-data-protection` — no traceback/exception text in HTTP responses; generic messages, `logger.exception()` server-side; secrets from env.
- `python-server-hardening` — CSP/HSTS middleware; reject CRLF in header values; no hardcoded/seed credentials; no mass-assignment from request bodies.
- `python-csrf-prevention` — JWT-in-header → CSRF machinery **not** needed (documented, not layered on).
- `python-sql-injection-prevention` — parameterized SQL for `conversations`/`query_cache`.
- `python-ssrf-prevention` — outbound calls remain hardcoded/config hosts (SerpAPI/OpenWeather); no user-controlled URLs introduced.
- `python-https-security` — all external calls https, timeouts set (already true).
- Frontend XSS — render itinerary text as React children (auto-escaped); never `dangerouslySetInnerHTML` on tool/model content (compounds the WIN 6 injection defense).

---

## 11. Out of scope / deferred
- **Agentic booking / payments** — no reliable platform; recommend-only with deep-links out (plan §8). Firm.
- **Landing / marketing page** — app-only (login → chat). Dropped.
- **PWA / offline** — dropped. Web-only, but **mobile-responsive is required** (usable on phone; sidebar → drawer, verified at 375px).
- **RTL / i18n** — dropped (`--rtl` removed from the scaffold command); LTR English only.
- **Model tiering revisited** — moot on nano; `synthesis_model` override remains available.

---

## 12. Decisions (resolved 2026-08-17)

1. **Landing page** — no. App-only (login → chat).
2. **Shareable itineraries** — yes; privacy-safe snapshot design in §7b (Phase 9.4).
3. **RTL / i18n** — no. `--rtl` removed from the scaffold command.
4. **PWA / offline** — no. Web-only, but **mobile-responsive required**.
5. **Streamed prose + structured** — **keep BOTH** (recommended). Stream the concise prose reply
   (natural chat feel, handles clarifying questions + abstention + non-itinerary turns, gives
   streaming responsiveness) *and* render the structured **Itinerary View** card as the trustworthy
   deliverable. Structured-only can't handle clarifying-question turns (no itinerary) and reads
   cold; the "assistant message + rich card" pattern is standard and the SSE protocol already
   supports it (token events + itinerary event).
6. **Deploy** — Vercel (Next.js) + Render (FastAPI).
7. **Design** — the `b1x9M8ZeJW` preset provides the theme; sidebar + right-hand chat; mirror the
   RAG frontend (`../../RAG/frontend`) layout/components (see §7 "Layout"). Neutral, clean, dark/light.
```
