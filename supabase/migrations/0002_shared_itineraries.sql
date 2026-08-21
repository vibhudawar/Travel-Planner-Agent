-- WIN 9.4: frozen, public, read-only itinerary snapshots. "Share" freezes the
-- itinerary JSON under an unguessable short code; the public /i/<code> page reads
-- it by code (no auth, no chat, no user data exposed). user_id is stored only for
-- ownership (deletion/auditing) and is never returned by the public endpoint.

create table if not exists public.shared_itineraries (
  short_code  text primary key,
  user_id     uuid references auth.users (id) on delete set null,
  destination text,
  itinerary   jsonb not null,
  created_at  timestamptz not null default now()
);

create index if not exists shared_itineraries_user_idx
  on public.shared_itineraries (user_id, created_at desc);

alter table public.shared_itineraries enable row level security;

-- Anyone with the short code can read a snapshot (the code is the capability).
-- Defense-in-depth: the API connects with the service role and reads by code.
drop policy if exists read_shared on public.shared_itineraries;
create policy read_shared on public.shared_itineraries
  for select to anon, authenticated
  using (true);

-- Only the authenticated owner may create or delete their snapshots.
drop policy if exists write_own_shared on public.shared_itineraries;
create policy write_own_shared on public.shared_itineraries
  for all to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);
