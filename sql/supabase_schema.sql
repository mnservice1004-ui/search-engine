create table if not exists public.tasks (
  id text primary key,
  name text not null,
  representative text,
  department text,
  team text,
  floor text,
  place text,
  route text,
  question text,
  caution text,
  script text,
  priority integer not null default 0,
  status text,
  source text,
  note text,
  location_condition text,
  contact_name text,
  contact_role text,
  phone text,
  contact_verified_at date,
  active boolean not null default true,
  updated_at timestamptz not null default now()
);

create table if not exists public.aliases (
  id bigint generated always as identity primary key,
  task_id text not null references public.tasks(id) on delete cascade,
  text text not null,
  weight integer not null default 1,
  type text,
  unique(task_id, text)
);

create table if not exists public.event_logs (
  id bigint generated always as identity primary key,
  event_type text not null,
  task_id text references public.tasks(id) on delete set null,
  result_count integer,
  created_at timestamptz not null default now()
);

alter table public.tasks enable row level security;
alter table public.aliases enable row level security;
alter table public.event_logs enable row level security;

-- 이 설계에서는 브라우저가 Supabase를 직접 호출하지 않는다.
-- Flask·Streamlit의 서버용 키만 접근하도록 anon 정책을 만들지 않는다.

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists tasks_set_updated_at on public.tasks;
create trigger tasks_set_updated_at
before update on public.tasks
for each row execute function public.set_updated_at();
