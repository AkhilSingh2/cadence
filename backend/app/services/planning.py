from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

import asyncpg

from app.db import repo
from app.engine.adapter import adapt_plan, plan_to_dict, voice_opener
from app.engine.readiness import HealthSnapshot, MoodSnapshot, classify_day


async def build_and_save_plan(
    conn: asyncpg.Connection,
    user_id: uuid.UUID,
    day: date | None = None,
) -> dict[str, Any]:
    day = day or datetime.now(timezone.utc).date()
    await repo.ensure_demo_user(conn, user_id)
    ctx = await repo.get_profile(conn, user_id)
    health_row = await repo.get_health_day(conn, user_id, day)
    consecutive = await repo.consecutive_red_days(conn, user_id, day)

    wake_at = None
    health = HealthSnapshot()
    if health_row:
        wake_at = health_row.get("wake_detected_at") or health_row.get("sleep_end")
        health = HealthSnapshot(
            sleep_hours=float(health_row["sleep_hours"]) if health_row.get("sleep_hours") is not None else None,
            sleep_efficiency=float(health_row["sleep_efficiency"])
            if health_row.get("sleep_efficiency") is not None
            else None,
            hrv_sdnn_ms=float(health_row["hrv_sdnn_ms"]) if health_row.get("hrv_sdnn_ms") is not None else None,
            rhr_bpm=float(health_row["rhr_bpm"]) if health_row.get("rhr_bpm") is not None else None,
            hrv_baseline=float(health_row["hrv_baseline_14d"])
            if health_row.get("hrv_baseline_14d") is not None
            else None,
            rhr_baseline=float(health_row["rhr_baseline_14d"])
            if health_row.get("rhr_baseline_14d") is not None
            else None,
        )

    mood_row = await repo.latest_mood(conn, user_id)
    mood = None
    if mood_row:
        mood = MoodSnapshot(
            valence=int(mood_row["valence"]),
            energy=int(mood_row["energy"]),
            stress=int(mood_row["stress"]),
        )

    score, state = classify_day(health, mood, consecutive)
    goals = ctx["goals"]
    profile = ctx["profile"]
    plan = adapt_plan(
        state,
        score,
        day=day,
        weight_kg=ctx["weight_kg"],
        protein_per_kg=float(goals.get("protein_floor_g_per_kg") or 1.6),
        study_minutes_green=int(goals.get("study_minutes_green") or 60),
        surplus_kcal=int(goals.get("surplus_kcal") or 200),
        wake_at=wake_at,
        hard_dislikes=list(profile.get("hard_dislikes") or []),
    )
    payload = plan_to_dict(plan)
    plan_id = await repo.save_plan(conn, user_id, payload)

    # Persist readiness onto health_daily if row exists or create thin row
    await repo.upsert_health_daily(
        conn,
        user_id,
        {
            "day": day,
            "readiness_score": score,
            "day_state": state.value,
            "wake_detected_at": wake_at,
            "sleep_hours": health.sleep_hours,
            "sleep_efficiency": health.sleep_efficiency,
            "hrv_sdnn_ms": health.hrv_sdnn_ms,
            "rhr_bpm": health.rhr_bpm,
            "hrv_baseline_14d": health.hrv_baseline,
            "rhr_baseline_14d": health.rhr_baseline,
            "source": (health_row or {}).get("source") or "derived",
        },
    )

    saved = await repo.get_today_plan(conn, user_id, day)
    assert saved is not None
    saved["opener"] = voice_opener(plan)
    saved["readiness_score"] = score
    saved["plan_id"] = str(plan_id)
    return saved
