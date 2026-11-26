-- Adaptive Voice-First Performance Companion
-- Initial schema: relational core + pgvector memory + RLS
-- Single-user first; multi-tenant-ready via user_id + policies

create extension if not exists "pgcrypto";
create extension if not exists "vector";

-- ---------------------------------------------------------------------------
-- Helpers
-- ---------------------------------------------------------------------------
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ---------------------------------------------------------------------------
-- Profile & goals
-- ---------------------------------------------------------------------------
create table public.user_profile (
  id uuid primary key references auth.users (id) on delete cascade,
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

create trigger user_profile_updated_at
  before update on public.user_profile
  for each row execute function public.set_updated_at();

create table public.goal_state (
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

create trigger goal_state_updated_at
  before update on public.goal_state
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- Biometrics & body
-- ---------------------------------------------------------------------------
create table public.health_daily (
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

create index health_daily_user_day_desc_idx
  on public.health_daily (user_id, day desc);

create table public.body_metrics (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.user_profile (id) on delete cascade,
  measured_at timestamptz not null default now(),
  weight_kg numeric(5,2),
  weight_ewma numeric(5,2),
  waist_cm numeric(5,2),
  photo_path text,
  notes text
);

create index body_metrics_user_measured_idx
  on public.body_metrics (user_id, measured_at desc);

-- ---------------------------------------------------------------------------
-- Mood, meals, training
-- ---------------------------------------------------------------------------
create table public.mood_checkins (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.user_profile (id) on delete cascade,
  logged_at timestamptz not null default now(),
  valence smallint not null check (valence between 1 and 5),
  energy smallint not null check (energy between 1 and 5),
  stress smallint not null check (stress between 1 and 5),
  trigger_text text,
  source text not null check (source in ('voice', 'tap', 'watch'))
);

create index mood_checkins_user_logged_idx
  on public.mood_checkins (user_id, logged_at desc);

create table public.meals (
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

create index meals_user_logged_idx
  on public.meals (user_id, logged_at desc);

create table public.workouts (
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

create index workouts_user_started_idx
  on public.workouts (user_id, started_at desc);

create table public.exercise_sets (
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

create index exercise_sets_workout_idx
  on public.exercise_sets (workout_id, sort_order);

-- ---------------------------------------------------------------------------
-- Study programme catalog + progress
-- ---------------------------------------------------------------------------
create table public.study_modules (
  id uuid primary key default gen_random_uuid(),
  ordinal int not null unique,
  title text not null,
  description text
);

create table public.study_topics (
  id uuid primary key default gen_random_uuid(),
  module_id uuid not null references public.study_modules (id) on delete cascade,
  ordinal int not null,
  title text not null,
  difficulty text check (difficulty in ('easy', 'medium', 'hard')),
  concept_summary text,
  unique (module_id, ordinal)
);

create table public.study_progress (
  user_id uuid not null references public.user_profile (id) on delete cascade,
  topic_id uuid not null references public.study_topics (id) on delete cascade,
  mastery numeric(4,3) not null default 0 check (mastery between 0 and 1),
  status text not null default 'not_started'
    check (status in ('not_started', 'learning', 'review', 'mastered')),
  last_practiced_at timestamptz,
  primary key (user_id, topic_id)
);

create table public.problem_attempts (
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

create index problem_attempts_user_idx
  on public.problem_attempts (user_id, attempted_at desc);

create index problem_attempts_bug_tags_idx
  on public.problem_attempts using gin (bug_tags);

-- ---------------------------------------------------------------------------
-- Daily plans
-- ---------------------------------------------------------------------------
create table public.daily_plans (
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

create table public.micro_tasks (
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

create index micro_tasks_plan_idx
  on public.micro_tasks (plan_id, sort_order);

create table public.plan_adjustments (
  id uuid primary key default gen_random_uuid(),
  plan_id uuid not null references public.daily_plans (id) on delete cascade,
  user_id uuid not null references public.user_profile (id) on delete cascade,
  from_state text,
  to_state text not null,
  reason text not null,
  diff jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Conversations (30-day raw retention)
-- ---------------------------------------------------------------------------
create table public.conversations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.user_profile (id) on delete cascade,
  started_at timestamptz not null default now(),
  ended_at timestamptz,
  channel text not null default 'text' check (channel in ('text', 'voice'))
);

create table public.messages (
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

create index messages_conversation_idx
  on public.messages (conversation_id, created_at);

create index messages_user_created_idx
  on public.messages (user_id, created_at desc);

-- ---------------------------------------------------------------------------
-- Vector memory
-- ---------------------------------------------------------------------------
create table public.memory_chunks (
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

create index memory_chunks_embedding_hnsw_idx
  on public.memory_chunks
  using hnsw (embedding vector_cosine_ops);

create index memory_chunks_tsv_idx
  on public.memory_chunks using gin (content_tsv);

create index memory_chunks_user_kind_created_idx
  on public.memory_chunks (user_id, kind, created_at desc);

create index memory_chunks_metadata_gin_idx
  on public.memory_chunks using gin (metadata jsonb_path_ops);

create table public.curriculum_chunks (
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

create index curriculum_chunks_embedding_hnsw_idx
  on public.curriculum_chunks
  using hnsw (embedding vector_cosine_ops);

create index curriculum_chunks_tsv_idx
  on public.curriculum_chunks using gin (content_tsv);

create index curriculum_chunks_topic_idx
  on public.curriculum_chunks (topic_id);

-- ---------------------------------------------------------------------------
-- Streaks (showing-up metric, not perfection)
-- ---------------------------------------------------------------------------
create table public.daily_streaks (
  user_id uuid not null references public.user_profile (id) on delete cascade,
  day date not null,
  showed_up boolean not null default false,
  tasks_completed int not null default 0,
  day_state text,
  primary key (user_id, day)
);

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
alter table public.user_profile enable row level security;
alter table public.goal_state enable row level security;
alter table public.health_daily enable row level security;
alter table public.body_metrics enable row level security;
alter table public.mood_checkins enable row level security;
alter table public.meals enable row level security;
alter table public.workouts enable row level security;
alter table public.exercise_sets enable row level security;
alter table public.study_progress enable row level security;
alter table public.problem_attempts enable row level security;
alter table public.daily_plans enable row level security;
alter table public.micro_tasks enable row level security;
alter table public.plan_adjustments enable row level security;
alter table public.conversations enable row level security;
alter table public.messages enable row level security;
alter table public.memory_chunks enable row level security;
alter table public.daily_streaks enable row level security;

-- Shared catalog: readable by any authenticated user; writes via service role only
alter table public.study_modules enable row level security;
alter table public.study_topics enable row level security;
alter table public.curriculum_chunks enable row level security;

-- Owner policies (user_id = auth.uid())
create policy user_profile_own on public.user_profile
  for all using (auth.uid() = id) with check (auth.uid() = id);

create policy goal_state_own on public.goal_state
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy health_daily_own on public.health_daily
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy body_metrics_own on public.body_metrics
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy mood_checkins_own on public.mood_checkins
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy meals_own on public.meals
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy workouts_own on public.workouts
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy exercise_sets_own on public.exercise_sets
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy study_progress_own on public.study_progress
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy problem_attempts_own on public.problem_attempts
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy daily_plans_own on public.daily_plans
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy micro_tasks_own on public.micro_tasks
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy plan_adjustments_own on public.plan_adjustments
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy conversations_own on public.conversations
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy messages_own on public.messages
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy memory_chunks_own on public.memory_chunks
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy daily_streaks_own on public.daily_streaks
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- Catalog read policies
create policy study_modules_read on public.study_modules
  for select to authenticated using (true);

create policy study_topics_read on public.study_topics
  for select to authenticated using (true);

create policy curriculum_chunks_read on public.curriculum_chunks
  for select to authenticated using (true);

-- ---------------------------------------------------------------------------
-- Seed: Study module placeholders (replace with real syllabus in Phase 3)
-- ---------------------------------------------------------------------------
insert into public.study_modules (ordinal, title, description) values
  (1, 'DSA Foundations', 'Arrays, strings, hashing, basic complexity'),
  (2, 'Recursion & Backtracking', 'Recursion trees, subsets, permutations'),
  (3, 'Linked Lists & Stacks/Queues', 'Pointer patterns, monotonic stacks'),
  (4, 'Trees & BSTs', 'Traversals, LCA, BST invariants'),
  (5, 'Heaps & Greedy', 'Priority queues, interval scheduling'),
  (6, 'Graphs', 'BFS/DFS, shortest paths, Union-Find'),
  (7, 'Dynamic Programming', '1D/2D DP, knapsack family, LIS'),
  (8, 'System Design & Interview Prep', 'HLD basics, mocks, behavioral');
