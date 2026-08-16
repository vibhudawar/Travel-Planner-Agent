# Trip Planner v2 — Plan for Reliability & Trust

**Goal:** turn the current demo agent into a system whose output I can **actually base real
travel decisions on.** The north-star is not "more tools" or "nicer UI" — it is: **every
fact in an itinerary is traceable to a real tool result, every number is arithmetically
correct, the agent says "I couldn't verify this" instead of guessing, and we can *prove* all
of that with evals that gate merges.**

Reference philosophy: the same discipline we applied in the RAG v2 upgrade
(`../RAG/plan-v2.md`) — **measured, not asserted; one pipeline = what ships is what we test;
every choice documented; graceful degradation everywhere.** The techniques differ because
this is a *tool-calling agent over live external APIs*, not a retrieval pipeline over a fixed
corpus — so the wins are about **groundedness, verification, and determinism**, not hybrid
retrieval. But the operating loop is identical: nothing changes without moving a measured
number.

The frontier-lab framing we're borrowing (at solo scale, cheaply):
- **"Don't trust, verify."** Anything the model asserts that a cheaper check can validate,
  *is* validated — a second signal grades the first. (RLHF reward models, process-reward
  models, Constitutional AI all reduce to this.)
- **Eval-driven development.** The eval set is the spec. Write the failing eval, then pass it.

---

## 1. Current state (honest baseline)

Trip Planner today: a LangGraph ReAct loop (`START → chat_node → tools_condition → tools →
chat_node`) over 7 tools, `SqliteSaver` memory, a Streamlit UI. ~717 lines across 4 files. It
is a good demo. It is **not** something to book a trip against — nothing stops the model from
inventing a flight, mis-adding a budget, or presenting a 6-hour-stale price as current.

| Area | Today | Reliability limitation |
|---|---|---|
| Model | `ChatOpenAI()` — no model / temperature pinned (`backend.py:20`) | Behavior floats with the SDK default; **not reproducible**, can't eval a moving target |
| Config | Scattered `os.getenv()`; keys checked lazily inside each tool; `load_dotenv()` duplicated (`backend.py:15`, `tools.py:14`) | Missing `OPENAI_API_KEY` surfaces as an opaque error mid-conversation; no fail-fast |
| Init | SQLite conn + graph compiled at import (`backend.py:49-65`); diskcache at import (`tools.py:24`) | Import triggers I/O → **untestable**; no way to inject fakes for evals |
| Output | Free-text itinerary from a single prompt (`prompts.py:5-41`) | No structure; **no fact is bound to a source**; hallucinated prices/flights are indistinguishable from real ones |
| Arithmetic | `calculator` tool the LLM *may* choose to call (`tools.py:29`) | Budget/date math still done by the LLM in prose → wrong sums, wrong night counts |
| Tool outputs | Consumed raw; `str(params)` cache key, blanket 6h TTL (`tools.py:108,124`) | No shape validation (SerpAPI returns partial/junk); **stale prices presented as live** |
| Untrusted content | `google_search` (AI mode), `search_youtube_vlogs` pull raw web text (`tools.py:52,396`) | **Prompt-injection surface** — a page/description can hijack the agent |
| Weather | OpenWeather `/assistant/session` beta endpoint returns an LLM prose "answer" (`tools.py:322`); prompt says "always check weather" (`prompts.py:12`) | Fragile contract; forecasts only exist ~14 days out → for trips months ahead the agent may present climatology (or fiction) as a forecast |
| Verification | None | The model is the only judge of its own output — no second signal |
| Abstention | None | On a tool `{"error": ...}` the agent proceeds and fabricates a confident answer |
| **Evals** | **None** (one `python -c` snippet in README) | **No way to prove any change helps or catch a regression** |
| Observability | `logging.basicConfig` only; `langsmith` is a dep but no tracing wired | Can't debug *why* a wrong itinerary happened |
| Serving | Streamlit monolith, `SqliteSaver` single-writer | Not a deployable multi-user service |

Single biggest gap: the model's claims are **unverified and unstructured.** Everything below
attacks that.

---

## 2. Design principles

1. **Every fact is source-bound or it doesn't ship.** Each price/flight/hotel/activity
   carries the tool + timestamp it came from. If the model can't attach a source, the field
   can't exist. (Structural anti-hallucination, not prompt-hope.)
2. **The LLM orchestrates; code computes.** Anything checkable — sums, night counts, date and
   currency math — is done in Python, never in prose.
3. **Don't trust, verify.** A second, different model checks the drafted itinerary against the
   actual tool outputs before it reaches the user.
4. **All tool output is untrusted data, never instructions.** Web/YouTube/AI-mode content is
   delimited and can never trigger actions.
5. **Fail open to honesty, never to fiction.** Tool error or thin data → say so and abstain on
   that piece; never fabricate to fill a section.
6. **Freshness is a first-class fact.** Prices/availability carry an "as of" time; the app
   tells you to reverify before buying.
7. **Measure everything; gate merges on it.** Trajectory + groundedness evals in CI, with a
   committed baseline and report history.

---

## 3. The changes, grouped as "wins"

Each win lists: **what**, **why it's a win**, **files**, **effort**, **success metric**.

### WIN 1 — Foundation: fail-fast config, factories, pinned model (do this FIRST)
- **What:**
  - A `settings.py` using **`pydantic-settings`**: one typed `Settings` object, all keys
    (`OPENAI_API_KEY`, `SERPAPI_API_KEY`, `OPENWEATHER_API_KEY`) validated **at startup**;
    single `load_dotenv()`; per-field defaults + comments explaining each (mirrors RAG's
    `config.py`).
  - **Pin the model explicitly:** `model=`, `temperature=0` (or low), `max_tokens`, `timeout`,
    `max_retries` on `ChatOpenAI` — behavior becomes reproducible so evals mean something.
  - **Kill import-time side effects:** wrap graph/DB/cache creation in `build_graph()`,
    `get_cache()`, `get_llm()` factories. Nothing does I/O on import.
- **Why it's a win:** reproducibility + testability are **preconditions for every other win**
  — you cannot eval an app that opens SQLite and picks a random default model on import. Also
  a direct fix of the baseline's top three rows.
- **Files:** new `settings.py`; refactor `backend.py:15-65`, `tools.py:14,24`.
- **Effort:** ~half weekend.
- **Success metric:** app fails fast with a clear message when a key is missing; `import
  backend` performs zero I/O; model id is fixed and logged.

### WIN 2 — Eval & fixture harness (the measurement backbone)
- **What:** the RAG "evals-first" move, adapted for a live-API agent.
  - **Recorded fixtures (VCR/cassette pattern):** capture a set of *real* SerpAPI +
    OpenWeather responses once, freeze them as JSON under `evals/fixtures/`. Evals run the
    agent against these **frozen** tool outputs → deterministic, reproducible, zero API spend
    per run. (You cannot eval against live flights — prices change hourly.)
  - **Golden set** `evals/golden.jsonl`: ~20–30 scenarios covering `simple` (one city, clear
    dates), `underspecified` (missing dates/budget → must ask), `multi_constraint`,
    `tool_error` (a fixture returns `{"error": ...}` → must abstain gracefully), and
    `injection` (a fixture embeds "ignore previous instructions…" → must not comply).
  - **Metrics** (trajectory + behavior; judge model ≠ generator, per RAG rule):
    - **Tool-selection accuracy** — did it call the right tools and not fabricate an itinerary
      with zero tool calls? (ungameable: inspect the message trace)
    - **Slot-filling** — on underspecified input, did it ask instead of inventing dates?
    - **Groundedness** — % of itinerary facts traceable to a fixture value (this metric fully
      lands once WIN 3 gives structured output; ship the harness now with the rest).
    - **Budget-math correctness** — does the stated total equal the sum of its parts?
      (deterministic check; lands with WIN 4)
    - **Abstention accuracy** — on `tool_error` items, did it correctly decline that section?
    - **Injection resistance** — on `injection` items, did it ignore the embedded instruction?
  - **Committed reports** `evals/reports/*.json` = the improvement audit trail (RAG pattern).
- **Why it's a win:** it is the differentiator and it makes every later win *provable*. It's
  also what lets me honestly claim "reliable" — with a scoreboard, not vibes.
- **Files:** new `evals/` (`fixtures/`, `golden.jsonl`, `run_eval.py`, `metrics.py`,
  `judges.py`, `reports/`).
- **Effort:** 1–2 weekends.
- **Success metric:** `python -m evals.run_eval --version baseline` produces a report table.
  Establishes the before/after scoreboard (§5).

### WIN 3 — Structured, source-bound itinerary schema (structural anti-hallucination)
- **What:** replace the free-text itinerary with a **validated Pydantic schema** emitted via
  `with_structured_output`. Every atomic fact is a typed object:
  - `FlightOption{airline, price, currency, depart_time, arrive_time, stops, source_tool,
    retrieved_at, booking_link}`, likewise `HotelOption`, `Activity`, `WeatherDay`.
  - The `Itinerary` composes `days: list[DayPlan]`, `budget: Budget`, and a
    `provenance: list[Source]`. **A fact field is only valid if it carries a `source_tool` +
    `retrieved_at`** — enforced by a validator. The model literally cannot emit a price with
    no source.
  - Prose (tips, narrative) stays free-text, clearly separated from source-bound facts.
- **Why it's a win:** makes hallucination *structurally hard* rather than prompt-discouraged;
  gives the groundedness eval (WIN 2) and the verifier (WIN 7) something concrete to check;
  gives the Next.js UI clean typed data to render with per-item "source" chips.
- **Files:** new `schema.py`; rewrite `prompts.py` for structured emission; wire into
  `chat_node` final turn (`backend.py:33-42`).
- **Effort:** ~1 weekend.
- **Success metric:** 100% of itinerary fact-fields carry a resolvable source; groundedness
  metric becomes computable and clears a target (e.g. ≥0.95).

### WIN 4 — Deterministic compute layer (budget, dates, currency)
- **What:** move everything checkable out of the LLM into `compute.py`:
  - **Budget** totals, per-day sums, per-category rollups computed in code from the WIN 3
    objects — the model proposes items with prices; **code does the arithmetic.**
  - **Date/night math:** trip length, nights = `check_out − check_in`, day count, weekday
    labels — from a real date library, not prose.
  - **Currency:** normalize everything to one currency via an explicit rate (SerpAPI returns
    USD today) and label it; never let the model silently mix currencies.
  - Retire reliance on the LLM-invoked `calculator` tool (`tools.py:29`) for anything that
    should be deterministic.
- **Why it's a win:** eliminates a whole failure class (wrong sums, wrong night counts) for
  free; a budget you can trust is table-stakes for "base decisions on it."
- **Files:** new `compute.py`; the budget-math eval (WIN 2) guards it.
- **Effort:** ~half weekend.
- **Success metric:** budget-math correctness = 100% on the golden set; stated total always
  equals computed total.

### WIN 5 — Tool hardening + freshness discipline
- **What:**
  - **Output validation:** each tool validates SerpAPI/OpenWeather response *shape* before
    trusting it (partial/empty results are common) → bad shape treated as an error, not fed to
    the model as garbage.
  - **Retries + timeouts:** a couple of bounded retries with backoff on the external calls
    (they already pass `timeout=30` for weather; extend to SerpAPI).
  - **Freshness:** stamp every datum with `retrieved_at`; **shorten/skip the blanket 6h cache
    for prices & availability** (`set_cached` default, `tools.py:108`) while keeping longer
    TTLs for slow-moving data (attractions, vlogs). Surface "as of HH:MM — reverify before
    booking" in the output.
  - **Cache-key fix:** replace the brittle `str(params)` key (`tools.py:124`) with a stable
    hash of sorted, normalized params.
  - **Weather correctness:** prefer a **structured** forecast source (e.g. Open-Meteo /
    OpenWeather One Call returning typed data) over the beta `/assistant/session` prose
    endpoint; and **distinguish a real forecast (≤~14 days) from climate normals (beyond)**,
    labelling each — so a trip planned months out never shows fiction as a forecast. Drop the
    unconditional "always check weather" instruction (`prompts.py:12`) in favor of
    "forecast if within range, else historical averages, clearly labelled."
- **Why it's a win:** stale or malformed data → wrong real-world decision. This is where a lot
  of the "can I trust it" actually lives.
- **Files:** `tools.py` (all tool bodies + `_serpapi_search`); possibly a new `weather.py`.
- **Effort:** ~1 weekend.
- **Success metric:** no tool ever returns unvalidated data; every price carries an accurate
  `retrieved_at`; weather items labelled forecast vs. normals correctly on the golden set.

### WIN 6 — Prompt-injection defense on tool results
- **What:** treat all tool output as **untrusted data**. Wrap web/YouTube/AI-mode content
  (`google_search` `tools.py:52`, `search_youtube_vlogs` `tools.py:396`, and any free-text
  field) in explicit delimiters with a standing system reminder that content inside is data,
  never instructions; strip/neutralize instruction-like patterns; ensure tool content can
  never trigger a side-effectful action.
- **Why it's a win:** these tools pull raw internet text straight into context — a genuine,
  well-known attack class, not hypothetical. The `injection` golden items (WIN 2) measure it.
- **Files:** `tools.py` (result wrapping), `prompts.py` (untrusted-data reminder).
- **Effort:** ~half weekend.
- **Success metric:** injection-resistance = 100% on the golden `injection` scenarios.

### WIN 7 — Groundedness verifier + abstention discipline (the trust lever)
- **What:** after the agent drafts the WIN 3 itinerary, a **second LLM pass (different model
  than the generator)** whose only job is to check **every source-bound fact against the
  actual tool outputs** in the transcript and flag anything unsupported or mismatched. Use the
  verdict two ways: (a) **surface** it — unverifiable facts get a "⚠️ couldn't verify" flag in
  the UI rather than being silently trusted; (b) feed flags back for **one** bounded revision
  pass. Pair with explicit **abstention**: on tool error or thin data, the relevant section
  says "I couldn't verify flights for these dates" instead of inventing one.
- **Why it's a win:** this is the single biggest lever for "I can actually trust this." It's
  Constitutional-AI / verifier-model / process-supervision at solo scale — a cheap second
  signal grading the first. Bounded to one revision (RAG's AUTO-mode loop-limit discipline) so
  it can't loop.
- **Files:** new `verifier.py`; a verify→(revise once) conditional edge in the graph
  (`backend.py`).
- **Effort:** ~1–1.5 weekends. **Depends on WIN 3** (needs structured facts to check).
- **Success metric:** groundedness and abstention accuracy up vs. the WIN 2 baseline;
  unsupported facts either removed or flagged — never presented as trusted.

### WIN 8 — Observability: tracing + cost tracking
- **What:** turn on **LangSmith tracing behind an env flag** (near-no-op when off — RAG
  pattern; the `langsmith` dep is already present). Add **per-conversation token/cost
  accounting** via LangChain's `get_usage_metadata_callback` + a small price table, persisted
  and shown in the UI (itineraries are multi-tool-call = worth watching).
- **Why it's a win:** when an itinerary is wrong you must see the exact tool call + reasoning
  step that caused it — non-negotiable for a system you depend on. Cost visibility is a
  production signal.
- **Files:** new `observability.py`; wire callbacks into the graph invoke; `settings.py` flag.
- **Effort:** ~half weekend.
- **Success metric:** every run traced when enabled; cost-per-itinerary logged.

### WIN 8.5 — Cost efficiency & tiered caching
- **What:** attack the two dominant cost drivers of a ReAct loop — **re-sent context** and
  **number of loop turns** — then add a **volatility-tiered cache** so repeat/near-repeat work
  is reused *without* ever serving a stale decision.
  - **Prompt-cache-friendly prefix:** keep a stable prefix (system prompt + tool defs first,
    per-request/user content last) so OpenAI automatic prompt caching discounts the re-sent
    input on every loop turn. No stable-prefix change should bust the cache needlessly.
  - **Parallel tool calls:** allow the model to fire flights + hotels + weather + attractions
    in **one** turn instead of 4 sequential turns — each avoided turn is one fewer full-context
    re-send (cost) *and* a latency win.
  - **History compaction:** once WIN 3 has structured a tool result into the itinerary, drop
    the raw multi-KB SerpAPI JSON from the running message history and keep only the compact
    structured object. Summarize old turns in long planning sessions.
  - **Model tiering:** cheap model (nano/mini) for slot-filling, query/slot extraction, and the
    **WIN 7 verifier** (a focused checking task); flagship only for final synthesis. Per-node
    model env vars in `settings.py`.
  - **Loop + token caps:** LangGraph `recursion_limit` + `max_tokens` as a cost/runaway guard;
    in-session dedupe of identical tool calls.
  - **Tiered cache (the reliability-safe design):**
    - **Volatile layer** (flight/hotel prices, availability): cache **only** the raw tool
      result with a short TTL (hours), always re-stamped `retrieved_at` (WIN 5). **Never** serve
      a stale price as a final answer.
    - **Stable layer** (destination knowledge, attractions, itinerary *skeleton*, vlogs,
      weather climatology): cached aggressively and **semantically**, on Supabase **pgvector**.
    - A cache hit reuses the *skeleton + knowledge* instantly (the bulk of the tokens & tool
      calls) while live prices are refreshed → most of the saving, none of the staleness.
  - **Slot-aware semantic key (not embedding-only):** semantic similarity ≠ request equality
    ("Tokyo 5d $2000" vs "$5000" embed nearly identically). Cache key = **canonical slot tuple**
    (`destination`, normalized `date_range`, `travelers`, `budget_band`) **hard-matched**, plus a
    semantic/embedding match on the softer intent ("relaxing"/"foodie"/"adventure"). This kills
    the "served a $2000 plan for a $5000 request" failure class.
  - **`query_cache` table (Supabase):** `slot_key`, `intent_embedding vector`, `response_skeleton
    jsonb`, `created_at`, `ttl`, `hit_count`; lookup `WHERE slot_key=? AND created_at > now()-ttl
    ORDER BY intent_embedding <=> ? LIMIT 1` above a tuned threshold. Same pattern serves
    sub-results ("attractions in Paris") — much higher hit rate than whole-itinerary caching.
- **Why it's a win:** prompt caching + parallel calls + tiering are a ~2–4× cost cut on a
  typical multi-tool trip with **no quality loss**; the tiered semantic cache adds reuse that
  scales with traffic while the volatility split keeps it decision-safe.
- **ROI caveat (recorded honestly):** for single-user/personal use the *response*-cache hit
  rate is low — the guaranteed savings are prompt caching + tool-result caching + parallel
  calls + tiering. The semantic response cache earns its keep as usage grows; we build the
  slot-aware key now so it's *correct* when it does, but don't over-invest in it early.
- **Precondition:** WIN 3 (needs structured slots + a structured skeleton to cache and compact).
- **Files:** `settings.py` (per-node models, caps), graph edits for parallel tools + compaction
  (`backend.py`), new `cache.py` (tiered + slot-aware pgvector cache), Supabase migration for
  `query_cache`.
- **Effort:** ~1–1.5 weekends (prompt-cache prefix + parallel calls + tiering first; semantic
  cache second).
- **Success metric:** **cost-per-itinerary down ≥50%** vs. the pre-WIN-8.5 baseline (from the
  WIN 8 cost logging) with no regression on the WIN 2 quality metrics; **cache-correctness =
  100%** (every hit's served skeleton matches request slots; volatile facts always re-fetched);
  cache hit-rate tracked over time.

### WIN 9 — Productionization: FastAPI + SSE, Supabase auth, Next.js (retire Streamlit)
- **What:**
  - Extract the graph behind a **FastAPI** `POST /stream` (Server-Sent Events) endpoint —
    stream tokens, then the structured itinerary, then verifier flags, then a `done` event.
    Health/readiness checks.
  - **Supabase auth (email + password):** validate the Supabase **JWT server-side** on every
    request; the verified `user.id` is the **only** identity source — request bodies never
    carry a user id (no impersonation). (Directly mirrors RAG's `api/auth.py`.)
  - **Conversation persistence → Postgres:** swap `SqliteSaver` for LangGraph's
    `AsyncPostgresSaver` (near drop-in) — SQLite's single-writer lock breaks under a
    multi-worker FastAPI; Supabase already gives us Postgres. Add **RLS** so a user can only
    read their own threads (defense-in-depth on top of app checks).
  - **Next.js frontend** that streams the answer, renders the typed itinerary with per-item
    **source chips** + **"as of" freshness** + **verifier ⚠️ flags**, and a conversation
    switcher. **Retire the Streamlit UI.**
  - **Security hardening:** secrets from env only; **never return tracebacks/exception text in
    HTTP responses** — log server-side with `logger.exception()`, return generic messages; add
    CSP/HSTS security-headers middleware; reject `\r`/`\n` in header values derived from input.
- **Why it's a win:** decouples backend from UI, makes it a real multi-user service, and the
  typed-itinerary-with-sources rendering is where the reliability work becomes *visible*.
- **Files:** new `api/` (FastAPI + `auth.py`), new `frontend/` (Next.js); Supabase migrations
  (`supabase/migrations/*.sql`) incl. RLS; delete `frontend.py`.
- **Effort:** ~2–3 weekends.
- **Success metric:** end-to-end authenticated, streamed itinerary in the browser with
  clickable per-fact sources and freshness stamps; concurrent users don't hit DB-lock errors.

---

## 4. Sequencing (dependency-ordered)

```
WIN 1 (foundation: config + factories + pinned model)  ── unblocks testability & reproducibility
   │
   └─▶ WIN 2 (eval + fixture harness)  ── the measurement backbone; everything scores against it
          │
          ├─▶ WIN 3 (structured source-bound schema)  ── structural anti-hallucination
          │      │
          │      ├─▶ WIN 4 (deterministic compute)     ── needs the structured facts
          │      ├─▶ WIN 7 (groundedness verifier + abstention)  ── the trust lever; needs WIN 3
          │      └─▶ WIN 8.5 (cost & tiered caching)    ── needs structured slots + skeleton
          │
          ├─▶ WIN 5 (tool hardening + freshness)        ── independent, high reliability value
          ├─▶ WIN 6 (injection defense)                 ── independent, cheap
          └─▶ WIN 8 (observability)                      ── independent; cost logging feeds WIN 8.5
                    │
                    └─▶ WIN 9 (FastAPI + Supabase auth + Next.js)  ── productionize the finished agent
```

Rough calendar: **8–10 weekends**, each win shippable and independently demoable. WINs 3+4+7
together are the reliability core; do them as a block once WIN 2 can measure them. WIN 8.5's
cost success metric depends on WIN 8's cost logging existing first.

---

## 5. Metrics scoreboard (fill in as we go)

The README headline table. Numbers are placeholders until WIN 2 runs on the recorded fixtures.

| Version | Tool-select acc. | Slot-fill acc. | Groundedness | Budget-math | Abstention acc. | Injection resist. | $/itinerary |
|---|---|---|---|---|---|---|---|
| baseline (2026-08-16, gpt-4o, judge gpt-4o-mini) | 100% (4/4) | 100% (2/2) | pending WIN 3 | pending WIN 4 | 100% (2/2) | 100% (2/2) | — |
| + structured schema (WIN 3) | 100% (4/4) | 100% (2/2) | 100% (4/4; 36 facts, mean 1.0) | pending WIN 4 | 100% (2/2) | 100% (2/2) | — |
| + deterministic compute (WIN 4) | 100% (4/4) | 100% (2/2) | 100% (4/4; 33 facts, mean 1.0) | 100% (4/4) | 100% (2/2) | 100% (2/2) | — |
| + verifier + abstention (WIN 7)* | 100% (4/4) | 100% (2/2) | 100% (4/4; 37 facts, mean 1.0) | 100% (4/4) | 100% (2/2) | 100% (2/2) | — |

*WIN 7 also adds a **verification** metric: 100% (4/4) — the value verifier pruned nothing on clean
scenarios (no false positives). This win7 run also retroactively confirms WIN 5 (freshness/hardening)
and WIN 6 (injection) live end-to-end after the credit top-up.

**Model correction (WIN 8.5):** rows above were measured on `gpt-4o` due to a config bug (the app
ignored `OPENAI_DEFAULT_MODEL`). The intended model is `gpt-5.4-nano`; all 7 metrics **re-verified
100% on nano** (45 facts) at **$0.0046/itinerary**. See the WIN 8.5 finding.
| + tool hardening (WIN 5) | | | | | | | |
| + injection defense (WIN 6) | | | | | | | |
| + verifier + abstention (WIN 7) | | | | | | | |
| + cost & caching (WIN 8.5) | | | | | | | |

Rule (RAG carry-over): **a merge that regresses any metric >2% without justification is
blocked in CI.** Record negative results too — if a change doesn't move a number, that's a
finding worth committing (RAG's WIN 3 NLU regression is the model here).

**WIN 2 baseline finding (2026-08-16):** on the 10-scenario golden set the current gpt-4o
agent already passes every *behavioral* metric we can measure today — tool selection,
clarify-before-searching, honest abstention on tool failure, and injection resistance (it
ignored instructions embedded in YouTube/AI-mode tool output). So the reliability gap is
**not** behavioral hygiene; it is **fact-level trust** — groundedness and budget-math — which
are exactly the two metrics still pending WIN 3 (structured source-bound output) and WIN 4
(deterministic compute). Small-n caveat: 2 scenarios each for slot-fill/abstention/injection;
the golden set grows as `docs/failure_modes.md` accumulates real bugs.

**WIN 3 finding (2026-08-16):** structured source-bound output makes groundedness computable
and it lands at **100% (36 facts, mean 1.0)** on the trip scenarios — the current agent does
not fabricate facts once forced to attribute them. Two design lessons baked in: (1) **separate
source-bound facts from day-plan prose** — `flights/hotels/weather/attractions` are scored
facts; `days[].activities` are free-text scheduling (meals, transit, free time) that must NOT
be held to source-binding or the metric mis-fires; (2) **fixtures must match a scenario's
destination** — reusing Tokyo fixtures for a Paris query made synthesis (correctly) drop the
mismatched facts and emit an empty itinerary, which is nondeterministic noise, not a real
signal. Note: this is *attribution + name-level* groundedness; full value-level verification of
every field is WIN 7.

**WIN 4 finding (2026-08-16):** the WIN 3 (LLM-authored) budgets were genuinely broken —
`simple_tokyo_solo` and `tool_error_flights` had **no total at all**, and `multi_budget_tokyo`
set `total = 2500` (the user's *budget cap*) while its line items summed to 2219. Moving the
budget into `compute.py` (cheapest flight × travelers + cheapest hotel × nights, USD-normalized,
from parsed dates) takes **budget-math to 100%** and the total now always equals the sum of its
parts. Also refined the groundedness value check from exact-substring to distinctive-token
matching, after the LLM normalized the fixture's `"United"` to `"United Airlines"` and tripped a
false negative — the metric now tolerates light name normalization while still catching
fabricated names.

**WIN 5 finding (2026-08-16):** tool hardening shipped — stable cache keys (hash of normalized
params, api_key excluded), SerpAPI/OpenWeather response validation, bounded retries with backoff
(tenacity), per-category cache TTLs (volatile prices 1h vs. stable data 24h), `retrieved_at`
freshness stamps on every tool result, and **code-authored weather labelling**: a trip beyond
the ~14-day forecast horizon is stamped `is_forecast=False` with a "seasonal averages, NOT a
live forecast" label (never fiction presented as a forecast). Also fixed a latent **over-asking**
bug surfaced during verification — the agent demanded optional preferences (layovers, amenities)
on a fully-specified query; the system prompt now proceeds once destination/origin/dates are
present and defaults the rest. Verified via 24 network-free unit tests + a full end-to-end
single-scenario smoke (all measurable metrics 100%, weather label correctly stamped). NOTE: the
full 10-scenario committed baseline for WIN 5 is **pending an OpenAI credit top-up** (the account
hit `insufficient_quota` mid-run); no metric regressions expected — WIN 5 is hardening, not a
behavior change to the scored paths.

**WIN 6 finding (2026-08-16):** injection defense added as defense-in-depth (the baseline already
passed injection because gpt-4o ignored the payloads, but that relied on model goodwill). Three
layers: (1) tool-boundary **neutralization** — override phrases ("ignore previous instructions",
"system override", "you must output", role tags, etc.) are redacted from free-text fields (YouTube
titles, web-search summaries, place descriptions, weather prose) before they reach the model;
(2) **untrusted-data delimiters** wrapping web-search blobs; (3) a standing **system + synthesis
prompt reminder** that tool output is data, never instructions. Identifier fields
(airline/hotel/attraction names) are left untouched so groundedness is unaffected. Verified
deterministically: the tool-level neutralization strips the payload before the model sees it (7/7
network-free tests incl. the youtube/ai-mode injection fixtures) — a structural guarantee, not
model-dependent. Full live injection eval is **pending the OpenAI credit top-up** (still
`insufficient_quota`).

**WIN 7 finding (2026-08-17):** the trust lever. A **deterministic value verifier** (`verifier.py`)
checks every source-bound fact's concrete values (price number + name token) against the actual
tool outputs and **removes** anything unsupported before it reaches the user — so a fabricated
price/name structurally cannot survive, and a removed category becomes honest abstention with a
disclaimer. Runs as a `verify` graph node after `synthesize`, then recomputes the budget on the
pruned facts. On the golden set the agent doesn't fabricate, so nothing is pruned (`n_removed=0`
everywhere) — the mechanism's true-positive behavior is proven by unit tests (removes a fabricated
price, a fabricated hotel name, and facts citing an errored/uncalled tool). **Design decision:** the
plan called for an "LLM second pass"; I built it (`enable_llm_verifier`, judge≠generator) but with
the cheap judge it produced only formatting noise (flagging `price` vs `price_per_night`), so it is
**off by default and advisory** — the deterministic check is the authoritative, free, reliable trust
mechanism, and the LLM pass is opt-in for semantic checks with a stronger judge. Full 7-metric
scoreboard all 100%; this run also confirmed WIN 5/6 live after the credit top-up.

**WIN 8 finding (2026-08-17):** observability shipped. LangSmith tracing is wired **through
settings** — a real bug fix: WIN 1 moved config to pydantic-settings (dropping `load_dotenv`), so
the `LANGSMITH_*` values in `.env` never reached `os.environ` and LangChain's auto-tracing was
silently doing nothing; `observability.configure_tracing()` now pushes them into `os.environ` when
enabled (near-no-op when off) and traces verified landing in the `TripPlannerAgent` project.
Per-itinerary **token/cost accounting** via LangChain's usage-metadata callback + a price table
gives the first real **cost baseline: $0.0393/itinerary** (~7,657 input / 2,016 output tokens,
gpt-4o, mean over 4 trips) — the number WIN 8.5 must move ≥50% via prompt caching, parallel tool
calls, history compaction, and model tiering. All 7 quality metrics unchanged at 100%.

**WIN 8.5 finding (2026-08-17):** the cost win — and two real bugs. (1) **Model config bug:** the
`.env` sets `OPENAI_DEFAULT_MODEL=gpt-5.4-nano`, but the settings field read `OPENAI_MODEL`, so the
value was silently ignored and the app ran on the `gpt-4o` default the whole time — meaning every
prior "100%" was measured on gpt-4o, not the intended model. Fixed with an `AliasChoices` alias;
all 7 metrics **re-verified 100% on nano**. (2) **Truncation bug** (surfaced by nano): a large
7-day family itinerary needs >1500 output tokens, so `max_tokens=1500` truncated the structured
JSON mid-output and synthesis silently failed (empty itinerary) — gave synthesis its own
`synthesis_max_tokens=4000`. Net: honoring the intended model + engineering optimizations (tool-
output slimming, concise post-tool summary since the structured itinerary carries the detail,
youtube/web-search only-when-asked, longest-prefix pricing, cached-input credit) took cost from
$0.0393 → **$0.0052/itinerary (-87%)** with zero quality regression. Parallel tool calls were
already on by default (5 tools in one turn). The slot-aware semantic response cache is **deferred
to WIN 9** (needs Supabase pgvector). Model tiering infra is kept (`synthesis_model` defaults to the
main model) but tiering to gpt-4o-mini is moot now that the main model is already nano-cheap.

**Cost sub-scoreboard:**

| Version | $/itinerary | Notes |
|---|---|---|
| WIN 8 "baseline" (gpt-4o) | $0.0393 | mis-measured — the app was silently on gpt-4o (see WIN 8.5 finding) |
| WIN 8.5 (gpt-5.4-nano, as intended) | **$0.0052** | **-87%**; parallel tool calls (already on) + slimming + concise answer + prompt-cache credit |

Cost rule: **cost-per-itinerary must drop ≥50% vs baseline with zero regression on the quality
metrics** — met (-87%, all 7 metrics still 100%). The slot-aware semantic response cache
(cache-correctness = 100% requirement) is **deferred to WIN 9** — it needs Supabase pgvector
(wired there) and the fixture eval can't demonstrate its benefit; the plan flagged it as
lower-ROI until there's real traffic.

---

## 6. Repo professionalization (parallel track, low effort, high signal)

- Migrate the flat `requirements.txt` freeze → **`pyproject.toml` + `uv`**; commit `uv.lock`;
  split runtime / dev / eval deps.
- **`ruff` + `mypy` + `pre-commit`**; type incrementally.
- **`Dockerfile`** for the FastAPI service (slim base).
- **CI** (GitHub Actions): lint → typecheck → unit tests → **evals gate** (runs against
  recorded fixtures, so it's free and deterministic — no API keys in CI).
- **`docs/architecture.md`:** the tradeoff doc (why structured output, why a verifier over
  fine-tuning, why recorded fixtures over live eval, why recommend-only). Strong seniority
  signal.
- **`docs/failure_modes.md`:** a living log — every wrong itinerary found becomes a permanent
  golden-set item.
- **`.gitignore` fix:** cover `*.db-wal` / `*.db-shm` / `.DS_Store` (currently untracked;
  `*.db` doesn't match the WAL/SHM sidecars).

---

## 7. How we present it (the narrative)

1. **Problem framing:** "the demo could confidently invent a flight — so you couldn't trust
   the itinerary." — shows judgment.
2. **The scoreboard** (§5) with before/after numbers. — shows rigor.
3. **The reliability stack diagram** (structured facts → deterministic compute → verifier →
   flagged output). — shows systems thinking.
4. **A failure-modes section** with real examples fixed (fabricated price caught by verifier,
   stale-price flag, injection ignored, forecast-vs-normals). — owning limitations reads as
   senior.
5. **Live demo:** an authenticated itinerary where each price is a clickable source with an
   "as of" time, plus a "couldn't verify flights for those dates" case handled honestly.

---

## 8. Explicitly out of scope (and why)

- **Agentic booking of flights / hotels (purchasing).** Confirmed: no reliable platform
  exposes agentic booking today, and it's a large safety + reliability + liability surface
  (payments, holds, cancellations). **The honest ceiling for a scraper-backed agent is a
  *trustworthy recommendation*** — sourced, fresh, verified — with deep links out to the
  provider for the human to complete. All the reliability work above is exactly what makes a
  *recommendation* dependable. Booking is a different project.
- **Multi-agent orchestrator/worker fleets.** The single ReAct loop + one bounded verifier
  pass captures the useful part; a fleet isn't justified without real traffic.
- **Fine-tuning / custom models.** No labeled data, no need — the verifier + structured output
  get us reliability far more cheaply (RAG rejected this too).
- **Self-consistency / N-sample ensembling.** Expensive per itinerary, low marginal value here
  vs. a single verifier pass.
- **Real-time price-monitoring / alerting infra.** Freshness stamps + reverify-before-booking
  is the honest solo-scale answer; a price-watch pipeline is over-engineering.

---

## Appendix — key current-code anchors

- Graph & ReAct loop: `backend.py` (`chat_node` `:33-42`, checkpointer `:49-50`, compile `:65`)
- Model init to pin: `backend.py:20` (`ChatOpenAI()`)
- Tools + SerpAPI wrapper: `tools.py` (`_serpapi_search` `:113`, cache key `:124`, 6h TTL
  `:108`, `ALL_TOOLS` `:440`)
- Untrusted-content tools: `google_search` `tools.py:52`, `search_youtube_vlogs` `tools.py:396`
- Weather (beta endpoint to replace): `tools.py:322`
- LLM-invoked calculator (to make deterministic): `tools.py:29`
- System prompt (rewrite for structured output + untrusted-data reminder): `prompts.py:5-41`
- Streamlit UI (to retire): `frontend.py`
