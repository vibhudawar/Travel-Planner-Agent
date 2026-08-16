-- WIN 9.1: conversation ↔ user mapping (message state lives in the LangGraph
-- checkpointer tables). RLS is defense-in-depth on top of the app-level ownership
-- checks; the API connects with the service role and enforces user_id in queries.

create table if not exists public.conversations (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references auth.users (id) on delete cascade,
  title      text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists conversations_user_updated_idx
  on public.conversations (user_id, updated_at desc);

alter table public.conversations enable row level security;

drop policy if exists own_conversations on public.conversations;
create policy own_conversations on public.conversations
  for all to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);
