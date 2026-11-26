-- Local Docker variant of 0001_init.sql
-- Differences vs Supabase cloud:
--   * no auth.users FK (demo auth via X-User-Id)
--   * creates a standalone users stub not required

create extension if not exists "pgcrypto";
create extension if not exists "vector";

create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create table if not exists public.user_profile (
  id uuid primary key,
  display_name text,
  sex text,
  height_cm numeric(5,2),
  birth_year int,
  timezone text not null default 'Asia/Kolkata',
  hard_dislikes text[] not null default '{}',
  appetite_notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

drop trigger if exists user_profile_updated_at on public.user_profile;
create trigger user_profile_updated_at
  before update on public.user_profile
  for each row execute function public.set_updated_at();

create table if not exists public.goal_state (
  user_id uuid primary key references public.user_profile (id) on delete cascade,
  goal_type text not null check (goal_type in ('lean_bulk', 'recomp', 'cut', 'maintain')),
  target_weight_kg numeric(5,2),
  protein_floor_g_per_kg numeric(4,2) not null default 1.6,
  surplus_kcal int not null default 200,
  training_split text not null default 'full_body_3x',
  study_minutes_green int not null default 60,
  active_from date not null default current_date,
  notes text,
  updated_at timestamptz not null default now()
);

create table if not exists public.health_daily (
  user_id uuid not null references public.user_profile (id) on delete cascade,
  day date not null,
  sleep_start timestamptz,
  sleep_end timestamptz,
  sleep_hours numeric(4,2),
  sleep_efficiency numeric(4,3),
  sleep_stages jsonb not null default '{}'::jsonb,
  hrv_sdnn_ms numeric(6,2),
  rhr_bpm numeric(5,2),
  active_energy_kcal numeric(7,2),
  steps int,
  wake_detected_at timestamptz,
  hrv_baseline_14d numeric(6,2),
  rhr_baseline_14d numeric(5,2),
  readiness_score numeric(4,3),
  day_state text check (day_state in ('GREEN', 'AMBER', 'RED', 'DELOAD')),
  source text not null default 'healthkit',
  synced_at timestamptz not null default now(),
  primary key (user_id, day)
);

create table if not exists public.body_metrics (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.user_profile (id) on delete cascade,
  measured_at timestamptz not null default now(),
  weight_kg numeric(5,2),
  weight_ewma numeric(5,2),
  waist_cm numeric(5,2),
  photo_path text,
  notes text
);

create table if not exists public.mood_checkins (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.user_profile (id) on delete cascade,
  logged_at timestamptz not null default now(),
  valence smallint not null check (valence between 1 and 5),
  energy smallint not null check (energy between 1 and 5),
  stress smallint not null check (stress between 1 and 5),
  trigger_text text,
  source text not null check (source in ('voice', 'tap', 'watch'))
);

create table if not exists public.meals (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.user_profile (id) on delete cascade,
  logged_at timestamptz not null default now(),
  food_name text not null,
  protein_g_est numeric(6,2),
  calories_est numeric(7,2),
  satiety smallint check (satiety between 1 and 5),
  was_convenience_food boolean not null default false,
  effort text check (effort in ('none', 'low', 'cook')),
  texture text,
  liked boolean
);

create table if not exists public.workouts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.user_profile (id) on delete cascade,
  started_at timestamptz not null default now(),
  ended_at timestamptz,
  prescribed_minutes int,
  actual_minutes int,
  rpe numeric(3,1),
  volume_multiplier numeric(3,2) not null default 1.0,
  day_state text check (day_state in ('GREEN', 'AMBER', 'RED', 'DELOAD')),
  completed boolean not null default false,
  notes text
);

create table if not exists public.exercise_sets (
  id uuid primary key default gen_random_uuid(),
  workout_id uuid not null references public.workouts (id) on delete cascade,
  user_id uuid not null references public.user_profile (id) on delete cascade,
  exercise_name text not null,
  sort_order int not null default 0,
  prescribed_reps int,
  actual_reps int,
  load_kg numeric(6,2),
  rpe numeric(3,1)
);

create table if not exists public.study_modules (
  id uuid primary key default gen_random_uuid(),
  ordinal int not null unique,
  title text not null,
  description text
);

create table if not exists public.study_topics (
  id uuid primary key default gen_random_uuid(),
  module_id uuid not null references public.study_modules (id) on delete cascade,
  ordinal int not null,
  title text not null,
  difficulty text check (difficulty in ('easy', 'medium', 'hard')),
  concept_summary text,
  unique (module_id, ordinal)
);

create table if not exists public.study_progress (
  user_id uuid not null references public.user_profile (id) on delete cascade,
  topic_id uuid not null references public.study_topics (id) on delete cascade,
  mastery numeric(4,3) not null default 0 check (mastery between 0 and 1),
  status text not null default 'not_started'
    check (status in ('not_started', 'learning', 'review', 'mastered')),
  last_practiced_at timestamptz,
  primary key (user_id, topic_id)
);

create table if not exists public.problem_attempts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.user_profile (id) on delete cascade,
  topic_id uuid references public.study_topics (id) on delete set null,
  problem_ref text not null,
  difficulty text check (difficulty in ('easy', 'medium', 'hard')),
  outcome text not null check (outcome in ('solved', 'partial', 'stuck', 'skipped')),
  bug_tags text[] not null default '{}',
  minutes_spent int,
  hints_used int not null default 0,
  attempted_at timestamptz not null default now()
);

create table if not exists public.daily_plans (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.user_profile (id) on delete cascade,
  day date not null,
  day_state text not null check (day_state in ('GREEN', 'AMBER', 'RED', 'DELOAD')),
  wake_at timestamptz,
  tone text not null default 'neutral'
    check (tone in ('coaching', 'neutral', 'empathetic_no_guilt')),
  nutrition jsonb not null default '{}'::jsonb,
  workout jsonb not null default '{}'::jsonb,
  study jsonb not null default '{}'::jsonb,
  suppress_checkins_until timestamptz,
  created_at timestamptz not null default now(),
  unique (user_id, day)
);

create table if not exists public.micro_tasks (
  id uuid primary key default gen_random_uuid(),
  plan_id uuid not null references public.daily_plans (id) on delete cascade,
  user_id uuid not null references public.user_profile (id) on delete cascade,
  kind text not null check (kind in ('intake', 'movement', 'study', 'recovery', 'social')),
  title text not null,
  minutes int,
  counts_toward_streak boolean not null default true,
  sort_order int not null default 0,
  completed_at timestamptz
);

create table if not exists public.plan_adjustments (
  id uuid primary key default gen_random_uuid(),
  plan_id uuid not null references public.daily_plans (id) on delete cascade,
  user_id uuid not null references public.user_profile (id) on delete cascade,
  from_state text,
  to_state text not null,
  reason text not null,
  diff jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.conversations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.user_profile (id) on delete cascade,
  started_at timestamptz not null default now(),
  ended_at timestamptz,
  channel text not null default 'text' check (channel in ('text', 'voice'))
);

create table if not exists public.messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.conversations (id) on delete cascade,
  user_id uuid not null references public.user_profile (id) on delete cascade,
  role text not null check (role in ('user', 'assistant', 'system')),
  content text not null,
  turn_class text,
  model_tier text check (model_tier in ('flash', 'frontier', 'none')),
  token_counts jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.memory_chunks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.user_profile (id) on delete cascade,
  kind text not null check (kind in ('episodic', 'semantic', 'preference', 'trigger', 'bug_pattern')),
  source_id uuid,
  content text not null,
  embedding vector(768),
  metadata jsonb not null default '{}'::jsonb,
  salience real not null default 0.5 check (salience between 0 and 1),
  content_tsv tsvector generated always as (to_tsvector('english', coalesce(content, ''))) stored,
  last_accessed_at timestamptz,
  created_at timestamptz not null default now(),
  expires_at timestamptz
);

create index if not exists memory_chunks_embedding_hnsw_idx
  on public.memory_chunks using hnsw (embedding vector_cosine_ops);
create index if not exists memory_chunks_tsv_idx
  on public.memory_chunks using gin (content_tsv);
create index if not exists memory_chunks_user_kind_created_idx
  on public.memory_chunks (user_id, kind, created_at desc);

create table if not exists public.curriculum_chunks (
  id uuid primary key default gen_random_uuid(),
  module_id uuid references public.study_modules (id) on delete set null,
  topic_id uuid references public.study_topics (id) on delete set null,
  parent_doc_id uuid references public.curriculum_chunks (id) on delete cascade,
  content text not null,
  embedding vector(768),
  metadata jsonb not null default '{}'::jsonb,
  content_tsv tsvector generated always as (to_tsvector('english', coalesce(content, ''))) stored,
  created_at timestamptz not null default now()
);

create index if not exists curriculum_chunks_embedding_hnsw_idx
  on public.curriculum_chunks using hnsw (embedding vector_cosine_ops);

create table if not exists public.daily_streaks (
  user_id uuid not null references public.user_profile (id) on delete cascade,
  day date not null,
  showed_up boolean not null default false,
  tasks_completed int not null default 0,
  day_state text,
  primary key (user_id, day)
);

insert into public.study_modules (ordinal, title, description) values
  (1, 'DSA Foundations', 'Arrays, strings, hashing, basic complexity'),
  (2, 'Recursion & Backtracking', 'Recursion trees, subsets, permutations'),
  (3, 'Linked Lists & Stacks/Queues', 'Pointer patterns, monotonic stacks'),
  (4, 'Trees & BSTs', 'Traversals, LCA, BST invariants'),
  (5, 'Heaps & Greedy', 'Priority queues, interval scheduling'),
  (6, 'Graphs', 'BFS/DFS, shortest paths, Union-Find'),
  (7, 'Dynamic Programming', '1D/2D DP, knapsack family, LIS'),
  (8, 'System Design & Interview Prep', 'HLD basics, mocks, behavioral')
on conflict (ordinal) do nothing;
