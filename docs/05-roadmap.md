# Implementation Roadmap (Phases 1–4)

Each phase has concrete tasks and a **measurable exit criterion**. Do not start the next phase until the exit criterion passes.

---

## Phase 1 — Minimal viable prototype

**Goal:** Automatic biometrics in, text companion out, readiness visibly changes the day plan. No vector memory, no voice yet.

### Tasks

1. Create Supabase project; apply [`0001_init.sql`](../supabase/migrations/0001_init.sql).
2. Seed `user_profile` + `goal_state` for the lean-bulk profile (see data model §6).
3. Scaffold FastAPI app with:
   - `POST /v1/health/sync`
   - `POST /v1/mood`
   - `POST /v1/chat` (Flash-tier, no RAG)
   - `GET /v1/plans/today`
4. Implement `readiness.classify_day` + `adapt_plan` (GREEN/AMBER/RED only; DELOAD can wait until week 2).
5. SwiftUI app:
   - Supabase Auth (magic link)
   - HealthKit permission + `HKObserverQuery` + anchored sync
   - Mood + weight logging screens
   - Text chat sheet
   - Today plan view showing `day_state`, micro-tasks, protein floor
6. Deploy API to Cloud Run (scale-to-zero) or run locally via tunnel for the first week.
7. Log every plan adjustment to `plan_adjustments` for debugging.

### Exit criteria

- [ ] **7 consecutive days** of automatic HealthKit ingestion into `health_daily` without manual CSV uploads.
- [ ] On a poor-sleep night, `GET /v1/plans/today` returns `day_state=RED` (or AMBER) with **reduced** study minutes and `nutrition.surface_calories=false`, visibly different from a GREEN day in the UI.

### Explicitly out of scope

Vector memory, voice, study tutor, Jira/Slack, neural TTS, Charts dashboard polish.

---

## Phase 2 — Vector memory & retention

**Goal:** The companion remembers food dislikes, emotional triggers, and recurring DSA bugs across weeks.

### Tasks

1. Wire Gemini `text-embedding-004` (768-d) in `memory/ingest.py`.
2. On each chat turn, write an `episodic` `memory_chunks` row.
3. Implement hybrid retrieve: HNSW + `tsvector`, RRF, MMR, salience/recency rerank, hard cap 8 chunks.
4. Inject retrieved memories into Flash-tier prompts.
5. Nightly consolidation job: episodic → `semantic` / `preference` / `trigger` / `bug_pattern`; delete/expire episodics; summarize and purge `messages` older than 30 days.
6. Preference write path: when user confirms a dislike/like, upsert `kind=preference` with high salience immediately (don't wait for nightly job).
7. Add basic eval notebook: 10 hand-written recall queries with expected chunk kinds.

### Exit criteria

- [ ] State a food dislike in week N; in week N+2 the meal suggestion path **excludes** it without being reminded in the same session.
- [ ] Log the same `bug_tag` on ≥3 `problem_attempts`; system surfaces a `bug_pattern` memory during a later tutor/chat turn.

---

## Phase 3 — Voice interface & study integration

**Goal:** Voice-first check-ins under the latency SLO; Socratic DSA help without dumping solutions; planner aware of work load.

### Tasks

**Voice**
1. AVAudioEngine capture + on-device `SFSpeechRecognizer` with partial transcript debounce (300 ms).
2. WebSocket `/v1/voice` with speculative retrieval on partials.
3. Sentence-level TTS streaming; default `AVSpeechSynthesizer`; optional ElevenLabs Flash for `morning_checkin` only.
4. Wake-time-relative local notifications + APNs enrichment.
5. Instrument `ttft_ms`, `retrieval_ms`, `tts_first_chunk_ms`.

**Study programme**
6. Ingest syllabus into `study_modules` / `study_topics` / `curriculum_chunks` (parent-document chunking). *Open item: source format of the syllabus export.*
7. DSA tutor tool with hard no-full-solution guardrail (policy reject + regenerate).
8. Study block selection respects `DayState` difficulty bias (see behavioral engine §8).

**Integrations**
9. Jira + Slack read-only OAuth hooks into planner inputs.
10. Optional macOS menu-bar agent for downtime detection.

### Exit criteria

- [ ] Full voice check-in: **first audio ≤ 1.2 s** after endpoint on a typical Wi-Fi network (median of 10 trials).
- [ ] Tutor guides a medium problem to completion across a session **without** emitting a working solution (manual review of transcript).

### Open items to resolve during this phase

- Syllabus export format (PDF / Notion / manual CSV).
- Which neural TTS voice you prefer (listen and pick; disable if cost spikes).

---

## Phase 4 — Production & progress visualization

**Goal:** Live dashboard, hardened multi-tenant readiness, TestFlight, cost/quality observability.

### Tasks

1. SwiftUI Charts dashboard: weight EWMA trend, readiness history, micro-task completion, curriculum velocity (topics/week).
2. RLS audit: every user table policy tested with a second synthetic user.
3. Observability: per-turn cost estimate, retrieval thumbs, Cloud Run logs → simple dashboard.
4. DELOAD enforcement after 3 consecutive RED days verified in integration tests.
5. TestFlight build; privacy nutrition labels; HealthKit usage strings.
6. Backup/restore runbook for Supabase; secret rotation notes.
7. Cost kill-switches in settings: disable neural TTS, frontier reviews biweekly.

### Exit criteria

- [ ] Dashboard shows ≥4 weeks of weight EWMA + readiness without manual spreadsheets.
- [ ] Second Auth user cannot read the first user's `health_daily` or `memory_chunks` (RLS proof).
- [ ] Steady-state infra+model spend remains **under $25/month** for 2 consecutive billing cycles (or documented kill-switch keeps it there).

---

## Suggested calendar (solo, evenings)

| Phase | Calendar stretch | Intensity |
|---|---|---|
| 1 | Weeks 1–3 | Highest — foundation |
| 2 | Weeks 4–5 | Medium |
| 3 | Weeks 6–9 | Highest — voice + tutor |
| 4 | Weeks 10–12 | Medium — polish & ship |

Adjust freely; **exit criteria matter more than dates**.

---

## Definition of done (product)

You open the app after a rough night and it:

1. Already knows sleep was bad (HealthKit).
2. Speaks one empathetic line (or shows it in text).
3. Asks for one small thing — not a full program.
4. Remembers you hate mass-gainers and that recursion base cases trip you up.
5. Counts today as a win when you show up for 15 minutes.

That is the product. Everything in this repo exists to make that loop reliable and cheap.
