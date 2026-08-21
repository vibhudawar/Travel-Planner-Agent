-- WIN 9.2: slot-aware semantic response cache on pgvector. Stores the STABLE
-- itinerary skeleton (destination knowledge, attractions, day plan, seasonal
-- weather, tips) keyed by a canonical slot tuple (hard-matched) + an embedding of
-- the soft intent. Volatile facts (flight/hotel prices) are never cached here —
-- they are always re-fetched on a hit — so a cache hit can't serve a stale price,
-- and the budget_band in the slot key stops a "$2000 plan for a $5000 request".
-- Only the service-role API touches this table (RLS on, no anon/user policies).

create extension if not exists vector;

create table if not exists public.query_cache (
  id                bigserial primary key,
  slot_key          text not null,
  intent            text,
  intent_embedding  vector(1536) not null,
  response_skeleton jsonb not null,
  created_at        timestamptz not null default now(),
  ttl_hours         double precision not null default 72,
  hit_count         integer not null default 0
);

create index if not exists query_cache_slot_idx
  on public.query_cache (slot_key, created_at desc);

create index if not exists query_cache_embed_idx
  on public.query_cache using hnsw (intent_embedding vector_cosine_ops);

alter table public.query_cache enable row level security;
