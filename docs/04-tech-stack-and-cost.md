# Tech Stack Recommendation & Cost Optimization

Choices below optimize for **native HealthKit depth**, **voice latency**, and a **hard ceiling under $25/month**, while keeping a multi-tenant-ready data model.

---

## 1. Stack summary

| Layer | Choice | Why |
|---|---|---|
| Mobile | SwiftUI (iOS 17+) + watchOS companion | Best HealthKit background delivery, lowest audio latency, Watch quick-log |
| Offline cache | SwiftData | Simple, Apple-native, enough for plan + 7-day biometrics |
| STT | On-device `SFSpeechRecognizer` | Free, offline, no STT RTT; Groq Whisper as noisy-audio fallback only |
| TTS | `AVSpeechSynthesizer` default; ElevenLabs Flash for morning check-in only | Quality where it matters; $0 elsewhere |
| Backend | FastAPI on Cloud Run (scale-to-zero) | Cheap idle, Python ML/ecosystem, WebSocket support |
| DB + vectors | Supabase Postgres + `pgvector` | One system for joins between biometrics and embeddings; free tier |
| Auth | Supabase Auth | Magic link solo; ready for multi-user |
| Jobs | `pg_cron` → secured Cloud Run endpoints | Morning plan + nightly consolidation |
| Push | APNs + on-device local notifications | Local notifications survive cold backend |
| LLM routine | Gemini 2.x Flash class | Cheap TTFT for check-ins / hints |
| LLM planning | Frontier (Gemini Pro / equivalent) | 4–6 calls/month only |
| Embeddings | Gemini `text-embedding-004` (768-d) | Matches `vector(768)` |
| Orchestration | Thin in-house router | No LangChain tax; explicit turn_class dispatch |
| Charts | SwiftUI Charts | Zero extra SaaS |
| Optional integrations | Jira + Slack OAuth read; macOS menu-bar agent | Planner inputs only |

---

## 2. Rejected alternatives (and why)

| Alternative | Rejected because |
|---|---|
| React Native / Flutter as primary client | HealthKit background delivery and realtime audio need heavy native bridges; you already own Watch + want lowest voice latency |
| Pinecone / Qdrant / Chroma Cloud | Extra monthly bill; forces app-side joins between vectors and biometric metadata you filter on every turn |
| Firebase-only (Firestore + Functions) | Weaker relational querying for readiness baselines, streaks, curriculum joins; pgvector is a better fit |
| Realtime speech-to-speech everywhere (OpenAI Realtime / Gemini Live) | Beautiful UX, blows the $25 budget if used all day |
| LangChain / LlamaIndex as core | Useful patterns, but adds abstraction cost and opaque token spend for a solo system with a known tool set |
| Always-on Cloud Run min instances = 1 | Idle cost unnecessary; local notifications cover reliability |
| Strict calorie-tracking apps as the nutrition core | Contradicts user psychology; protein-floor + preference memory is the product |

---

## 3. Model routing tiers

```text
turn_class ∈ {
  morning_checkin, mood_log, meal_log, workout_log,
  dsa_hint, smalltalk, weekly_review, monthly_recomp, embed
}
```

| turn_class | Tier | Notes |
|---|---|---|
| `morning_checkin`, `mood_log`, `meal_log`, `workout_log`, `dsa_hint`, `smalltalk` | Flash | Context capped (~8 memory chunks) |
| `weekly_review`, `monthly_recomp` | Frontier | Scheduled, not conversational spam |
| Hard tutor escalation (user stuck >N hints) | Frontier once, then back to Flash | Rare |
| Memory / curriculum ingest | Embeddings only | Batch nightly where possible |

Prompt budget for Flash turns: system + plan.tone + ≤1800 tokens memory + last 6 messages.

---

## 4. Monthly cost table (steady state, solo)

Assumptions: ~30 voice/text check-ins/day average, mostly Flash; neural TTS for ~1 morning check-in/day; frontier ~5 calls/month; Cloud Run scale-to-zero.

| Line item | Est. monthly USD | Notes |
|---|---|---|
| Supabase free tier | 0 | DB, Auth, pgvector, `pg_cron` within free limits |
| Cloud Run | 0–2 | Scale-to-zero; WebSocket sessions are bursty |
| Flash-tier LLM | 2–4 | Dominant inference cost |
| Frontier LLM | 1–2 | 4–6 heavy calls |
| Embeddings | <0.50 | Nightly consolidation + ingest |
| On-device STT | 0 | `SFSpeechRecognizer` |
| Groq Whisper fallback | ~0–0.50 | Rare noisy retries |
| AVSpeech TTS | 0 | Default path |
| ElevenLabs Flash (morning only) | 0–5 | Cap usage; disable if month is tight |
| APNs | 0 | |
| **Total** | **≈ 4–14** | Headroom under $25 |

If spend creeps: disable neural TTS first (instant ~$0–5 save), then reduce frontier reviews to biweekly.

---

## 5. Free-tier / Phase 1 specifics

Phase 1 can run almost entirely on free tiers:

- Supabase free project
- Gemini API free/low tier for Flash chat
- Local Xcode builds (no TestFlight yet)
- HealthKit sync + text chat only (no neural TTS, no WebSocket voice)

See [05-roadmap.md](05-roadmap.md).

---

## 6. Repo layout (target)

```text
trainer/
  README.md
  docs/
    01-architecture.md
    02-data-model.md
    03-behavioral-engine.md
    04-tech-stack-and-cost.md
    05-roadmap.md
  supabase/
    migrations/
      0001_init.sql
  backend/
    app/
      main.py
      gateway/
      engine/
      memory/
      tools/
      llm/
      jobs/
    requirements.txt
    Dockerfile
  ios/
    Trainer/          # Xcode project (Phase 1+)
    TrainerWatch/
```

Backend and iOS app code are scaffolded starting in Phase 1 of the roadmap; this document set is the blueprint they implement against.
