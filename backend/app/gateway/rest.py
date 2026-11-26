from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException

from app.auth import current_user_id
from app.config import get_settings
from app.db import repo
from app.db.session import get_pool
from app.engine.adapter import opener_from_plan_dict
from app.engine.readiness import DayState
from app.llm.prompts import build_system_prompt
from app.llm.router import generate
from app.memory.consolidate import consolidate_user
from app.memory.ingest import ingest_text, upsert_preference
from app.memory.retrieve import retrieve_memories
from app.schemas import (
    ChatIn,
    HealthSyncIn,
    MoodIn,
    PreferenceIn,
    ProblemAttemptIn,
    TaskCompleteIn,
    WeightIn,
)
from app.services.planning import build_and_save_plan
from app.tools.dsa_tutor import tutor_reply

router = APIRouter()


def _jsonable(obj):
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    return obj


@router.get("/healthz")
async def healthz():
    return {"ok": True}


@router.get("/status")
async def status():
    settings = get_settings()
    live = bool(settings.gemini_api_key)
    return {
        "ok": True,
        "ai_mode": "live" if live else "offline",
        "ai_model": settings.gemini_flash_model if live else "offline-fallback",
        "hint": None
        if live
        else "Add a free Gemini API key to .env as GEMINI_API_KEY, then rebuild the api container.",
    }


@router.post("/health/sync")
async def health_sync(body: HealthSyncIn, user_id: uuid.UUID = Depends(current_user_id)):
    pool = get_pool()
    async with pool.acquire() as conn:
        await repo.ensure_demo_user(conn, user_id)
        for day in body.days:
            await repo.upsert_health_daily(conn, user_id, day.model_dump())
        plan = await build_and_save_plan(conn, user_id)
    return {"synced": len(body.days), "plan": _jsonable(plan)}


@router.post("/mood")
async def log_mood(body: MoodIn, user_id: uuid.UUID = Depends(current_user_id)):
    pool = get_pool()
    async with pool.acquire() as conn:
        await repo.ensure_demo_user(conn, user_id)
        mid = await repo.insert_mood(conn, user_id, body.model_dump())
        if body.trigger_text:
            await ingest_text(
                conn,
                user_id,
                f"Mood trigger: {body.trigger_text} (valence={body.valence}, energy={body.energy}, stress={body.stress})",
                kind="trigger" if body.stress >= 4 or body.valence <= 2 else "episodic",
                metadata={"valence": body.valence, "energy": body.energy, "stress": body.stress},
                salience=0.7 if body.stress >= 4 else 0.5,
            )
        plan = await build_and_save_plan(conn, user_id)
    return {"mood_id": str(mid), "plan": _jsonable(plan)}


@router.post("/weight")
async def log_weight(body: WeightIn, user_id: uuid.UUID = Depends(current_user_id)):
    pool = get_pool()
    async with pool.acquire() as conn:
        await repo.ensure_demo_user(conn, user_id)
        await repo.insert_body_metric(conn, user_id, body.weight_kg, body.waist_cm)
    return {"ok": True}


@router.get("/plans/today")
async def plans_today(user_id: uuid.UUID = Depends(current_user_id), rebuild: bool = False):
    pool = get_pool()
    day = datetime.now(timezone.utc).date()
    async with pool.acquire() as conn:
        await repo.ensure_demo_user(conn, user_id)
        plan = None if rebuild else await repo.get_today_plan(conn, user_id, day)
        if plan is None:
            plan = await build_and_save_plan(conn, user_id, day)
        else:
            plan["opener"] = opener_from_plan_dict(plan)
    return _jsonable(plan)


@router.post("/tasks/complete")
async def complete_task(body: TaskCompleteIn, user_id: uuid.UUID = Depends(current_user_id)):
    pool = get_pool()
    async with pool.acquire() as conn:
        try:
            row = await repo.complete_micro_task(conn, user_id, body.task_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"task": _jsonable(row), "showed_up": True}


@router.post("/chat")
async def chat(body: ChatIn, user_id: uuid.UUID = Depends(current_user_id)):
    pool = get_pool()
    async with pool.acquire() as conn:
        await repo.ensure_demo_user(conn, user_id)
        plan = await repo.get_today_plan(conn, user_id, datetime.now(timezone.utc).date())
        if plan is None:
            plan = await build_and_save_plan(conn, user_id)

        conversation_id = body.conversation_id or await repo.create_conversation(conn, user_id, "text")
        await repo.add_message(conn, user_id, conversation_id, "user", body.message, body.turn_class)

        try:
            memories = await retrieve_memories(conn, user_id, body.message, limit=6)
            mem_texts = [m["content"] for m in memories]
        except Exception:  # noqa: BLE001
            mem_texts = []

        plan_summary = (
            f"state={plan.get('day_state')} tone={plan.get('tone')} "
            f"study={plan.get('study')} nutrition={plan.get('nutrition')} workout={plan.get('workout')}"
        )
        history = await repo.recent_messages(conn, conversation_id, limit=6)

        lower = body.message.lower()
        if body.turn_class == "dsa_hint" or any(k in lower for k in ("leetcode", "solve", "code", "dsa")):
            result = await tutor_reply(
                user_message=body.message,
                history=history[:-1],
                plan_summary=plan_summary,
                memories=mem_texts,
                tone=plan.get("tone") or "neutral",
            )
        else:
            system = build_system_prompt(
                tone=plan.get("tone") or "neutral",
                plan_summary=plan_summary,
                memories=mem_texts,
            )
            result = await generate(
                system=system,
                messages=history,
                turn_class=body.turn_class,
            )

        await repo.add_message(
            conn,
            user_id,
            conversation_id,
            "assistant",
            result["text"],
            body.turn_class,
            result.get("model_tier"),
        )
        try:
            await ingest_text(
                conn,
                user_id,
                f"User: {body.message}\nAssistant: {result['text']}",
                kind="episodic",
                metadata={"conversation_id": str(conversation_id)},
            )
        except Exception:  # noqa: BLE001
            pass

    return {
        "conversation_id": str(conversation_id),
        "reply": result["text"],
        "model_tier": result.get("model_tier"),
        "memories_used": mem_texts,
        "day_state": plan.get("day_state"),
    }


@router.post("/preferences")
async def add_preference(body: PreferenceIn, user_id: uuid.UUID = Depends(current_user_id)):
    pool = get_pool()
    async with pool.acquire() as conn:
        await repo.ensure_demo_user(conn, user_id)
        mid = await upsert_preference(conn, user_id, body.content, body.metadata)
    return {"memory_id": str(mid)}


@router.post("/problems/attempt")
async def problem_attempt(body: ProblemAttemptIn, user_id: uuid.UUID = Depends(current_user_id)):
    pool = get_pool()
    async with pool.acquire() as conn:
        await repo.ensure_demo_user(conn, user_id)
        await conn.execute(
            """
            insert into problem_attempts (
              user_id, topic_id, problem_ref, difficulty, outcome, bug_tags, minutes_spent, hints_used
            ) values ($1,$2,$3,$4,$5,$6,$7,$8)
            """,
            user_id,
            body.topic_id,
            body.problem_ref,
            body.difficulty,
            body.outcome,
            body.bug_tags,
            body.minutes_spent,
            body.hints_used,
        )
        if body.bug_tags:
            # If same tag appears 3+ times, promote bug_pattern memory
            for tag in body.bug_tags:
                count = await conn.fetchval(
                    """
                    select count(*) from problem_attempts
                    where user_id = $1 and $2 = any(bug_tags)
                    """,
                    user_id,
                    tag,
                )
                if count >= 3:
                    await ingest_text(
                        conn,
                        user_id,
                        f"Recurring DSA bug pattern: {tag} (seen {count} times)",
                        kind="bug_pattern",
                        metadata={"bug_tag": tag, "count": int(count)},
                        salience=0.85,
                    )
    return {"ok": True}


@router.get("/dashboard")
async def dashboard(user_id: uuid.UUID = Depends(current_user_id)):
    pool = get_pool()
    async with pool.acquire() as conn:
        await repo.ensure_demo_user(conn, user_id)
        stats = await repo.dashboard_stats(conn, user_id)
    return _jsonable(stats)


@router.post("/jobs/morning")
async def job_morning(
    x_job_secret: str | None = Header(default=None, alias="X-Job-Secret"),
    user_id: uuid.UUID | None = None,
):
    settings = get_settings()
    if x_job_secret != settings.job_secret:
        raise HTTPException(status_code=401, detail="bad job secret")
    pool = get_pool()
    uid = user_id or uuid.UUID(settings.dev_user_id)
    async with pool.acquire() as conn:
        plan = await build_and_save_plan(conn, uid)
    return {"plan": _jsonable(plan)}


@router.post("/jobs/consolidate")
async def job_consolidate(
    x_job_secret: str | None = Header(default=None, alias="X-Job-Secret"),
):
    settings = get_settings()
    if x_job_secret != settings.job_secret:
        raise HTTPException(status_code=401, detail="bad job secret")
    pool = get_pool()
    uid = uuid.UUID(settings.dev_user_id)
    async with pool.acquire() as conn:
        result = await consolidate_user(conn, uid)
    return result


@router.post("/demo/bad-day")
async def demo_bad_day(user_id: uuid.UUID = Depends(current_user_id)):
    """Seed a poor-sleep HealthKit-like day and rebuild the plan (for simulator demos)."""
    pool = get_pool()
    day = datetime.now(timezone.utc).date()
    async with pool.acquire() as conn:
        await repo.ensure_demo_user(conn, user_id)
        await repo.upsert_health_daily(
            conn,
            user_id,
            {
                "day": day,
                "sleep_hours": 4.8,
                "sleep_efficiency": 0.72,
                "hrv_sdnn_ms": 28,
                "rhr_bpm": 72,
                "hrv_baseline_14d": 45,
                "rhr_baseline_14d": 58,
                "wake_detected_at": datetime.now(timezone.utc).replace(hour=11, minute=0, second=0, microsecond=0),
                "steps": 1200,
                "active_energy_kcal": 180,
                "source": "demo",
            },
        )
        await repo.insert_mood(
            conn,
            user_id,
            {"valence": 2, "energy": 2, "stress": 4, "trigger_text": "late wake, rough sleep", "source": "tap"},
        )
        plan = await build_and_save_plan(conn, user_id, day)
    assert plan["day_state"] in {DayState.RED.value, DayState.DELOAD.value, DayState.AMBER.value}
    return _jsonable(plan)


@router.post("/demo/good-day")
async def demo_good_day(user_id: uuid.UUID = Depends(current_user_id)):
    """Seed strong recovery metrics so the plan flips to GREEN (for demos)."""
    pool = get_pool()
    day = datetime.now(timezone.utc).date()
    async with pool.acquire() as conn:
        await repo.ensure_demo_user(conn, user_id)
        await repo.upsert_health_daily(
            conn,
            user_id,
            {
                "day": day,
                "sleep_hours": 7.8,
                "sleep_efficiency": 0.92,
                "hrv_sdnn_ms": 52,
                "rhr_bpm": 56,
                "hrv_baseline_14d": 48,
                "rhr_baseline_14d": 58,
                "wake_detected_at": datetime.now(timezone.utc).replace(hour=7, minute=0, second=0, microsecond=0),
                "steps": 6500,
                "active_energy_kcal": 420,
                "source": "demo",
            },
        )
        await repo.insert_mood(
            conn,
            user_id,
            {"valence": 4, "energy": 4, "stress": 2, "trigger_text": "slept well", "source": "tap"},
        )
        plan = await build_and_save_plan(conn, user_id, day)
    return _jsonable(plan)
