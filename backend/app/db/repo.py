from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from typing import Any

import asyncpg

from app.config import get_settings


def _uuid(value: str | uuid.UUID) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _as_dt(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return None


async def ensure_demo_user(conn: asyncpg.Connection, user_id: str | uuid.UUID) -> uuid.UUID:
    """Create auth-less demo user + profile + goals if missing (local/dev)."""
    uid = _uuid(user_id)
    settings = get_settings()

    # Local Postgres has no auth.users — profiles are standalone with FK removed in local migration.
    await conn.execute(
        """
        insert into user_profile (id, display_name, sex, height_cm, birth_year, timezone, hard_dislikes, appetite_notes)
        values ($1, $2, 'male', $3, 1995, $4, $5, $6)
        on conflict (id) do nothing
        """,
        uid,
        "Demo User",
        settings.default_height_cm,
        settings.default_timezone,
        ["mass-gainer shakes"],
        "Low appetite on waking; avoid rigid breakfast pressure",
    )
    await conn.execute(
        """
        insert into goal_state (user_id, goal_type, protein_floor_g_per_kg, surplus_kcal, training_split, study_minutes_green)
        values ($1, 'lean_bulk', 1.6, 200, 'full_body_3x', 60)
        on conflict (user_id) do nothing
        """,
        uid,
    )
    # Seed a starting weight if none
    exists = await conn.fetchval(
        "select 1 from body_metrics where user_id = $1 limit 1", uid
    )
    if not exists:
        await conn.execute(
            """
            insert into body_metrics (user_id, weight_kg, weight_ewma)
            values ($1, $2, $2)
            """,
            uid,
            settings.default_weight_kg,
        )
    return uid


async def get_profile(conn: asyncpg.Connection, user_id: uuid.UUID) -> dict[str, Any]:
    row = await conn.fetchrow("select * from user_profile where id = $1", user_id)
    goals = await conn.fetchrow("select * from goal_state where user_id = $1", user_id)
    weight = await conn.fetchval(
        """
        select coalesce(weight_ewma, weight_kg)
        from body_metrics where user_id = $1
        order by measured_at desc limit 1
        """,
        user_id,
    )
    return {
        "profile": dict(row) if row else {},
        "goals": dict(goals) if goals else {},
        "weight_kg": float(weight or get_settings().default_weight_kg),
    }


async def upsert_health_daily(conn: asyncpg.Connection, user_id: uuid.UUID, payload: dict[str, Any]) -> None:
    day = payload["day"]
    if isinstance(day, str):
        day = date.fromisoformat(day)
    await conn.execute(
        """
        insert into health_daily (
          user_id, day, sleep_start, sleep_end, sleep_hours, sleep_efficiency, sleep_stages,
          hrv_sdnn_ms, rhr_bpm, active_energy_kcal, steps, wake_detected_at,
          hrv_baseline_14d, rhr_baseline_14d, readiness_score, day_state, source, synced_at
        ) values (
          $1,$2,$3,$4,$5,$6,$7::jsonb,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17, now()
        )
        on conflict (user_id, day) do update set
          sleep_start = coalesce(excluded.sleep_start, health_daily.sleep_start),
          sleep_end = coalesce(excluded.sleep_end, health_daily.sleep_end),
          sleep_hours = coalesce(excluded.sleep_hours, health_daily.sleep_hours),
          sleep_efficiency = coalesce(excluded.sleep_efficiency, health_daily.sleep_efficiency),
          sleep_stages = coalesce(excluded.sleep_stages, health_daily.sleep_stages),
          hrv_sdnn_ms = coalesce(excluded.hrv_sdnn_ms, health_daily.hrv_sdnn_ms),
          rhr_bpm = coalesce(excluded.rhr_bpm, health_daily.rhr_bpm),
          active_energy_kcal = coalesce(excluded.active_energy_kcal, health_daily.active_energy_kcal),
          steps = coalesce(excluded.steps, health_daily.steps),
          wake_detected_at = coalesce(excluded.wake_detected_at, health_daily.wake_detected_at),
          hrv_baseline_14d = coalesce(excluded.hrv_baseline_14d, health_daily.hrv_baseline_14d),
          rhr_baseline_14d = coalesce(excluded.rhr_baseline_14d, health_daily.rhr_baseline_14d),
          readiness_score = coalesce(excluded.readiness_score, health_daily.readiness_score),
          day_state = coalesce(excluded.day_state, health_daily.day_state),
          synced_at = now()
        """,
        user_id,
        day,
        _as_dt(payload.get("sleep_start")),
        _as_dt(payload.get("sleep_end")),
        payload.get("sleep_hours"),
        payload.get("sleep_efficiency"),
        json.dumps(payload.get("sleep_stages") or {}),
        payload.get("hrv_sdnn_ms"),
        payload.get("rhr_bpm"),
        payload.get("active_energy_kcal"),
        payload.get("steps"),
        _as_dt(payload.get("wake_detected_at")),
        payload.get("hrv_baseline_14d"),
        payload.get("rhr_baseline_14d"),
        payload.get("readiness_score"),
        payload.get("day_state"),
        payload.get("source") or "healthkit",
    )


async def get_health_day(conn: asyncpg.Connection, user_id: uuid.UUID, day: date) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        "select * from health_daily where user_id = $1 and day = $2", user_id, day
    )
    return dict(row) if row else None


async def consecutive_red_days(conn: asyncpg.Connection, user_id: uuid.UUID, before: date) -> int:
    rows = await conn.fetch(
        """
        select day_state from health_daily
        where user_id = $1 and day < $2 and day_state is not null
        order by day desc limit 14
        """,
        user_id,
        before,
    )
    count = 0
    for r in rows:
        if r["day_state"] in ("RED", "DELOAD"):
            count += 1
        else:
            break
    return count


async def latest_mood(conn: asyncpg.Connection, user_id: uuid.UUID, since: datetime | None = None) -> dict[str, Any] | None:
    if since is None:
        row = await conn.fetchrow(
            """
            select * from mood_checkins where user_id = $1
            order by logged_at desc limit 1
            """,
            user_id,
        )
    else:
        row = await conn.fetchrow(
            """
            select * from mood_checkins where user_id = $1 and logged_at >= $2
            order by logged_at desc limit 1
            """,
            user_id,
            since,
        )
    return dict(row) if row else None


async def insert_mood(conn: asyncpg.Connection, user_id: uuid.UUID, data: dict[str, Any]) -> uuid.UUID:
    mid = uuid.uuid4()
    await conn.execute(
        """
        insert into mood_checkins (id, user_id, valence, energy, stress, trigger_text, source)
        values ($1,$2,$3,$4,$5,$6,$7)
        """,
        mid,
        user_id,
        data["valence"],
        data["energy"],
        data["stress"],
        data.get("trigger_text"),
        data.get("source") or "tap",
    )
    return mid


async def insert_body_metric(conn: asyncpg.Connection, user_id: uuid.UUID, weight_kg: float, waist_cm: float | None = None) -> None:
    prev = await conn.fetchval(
        """
        select coalesce(weight_ewma, weight_kg) from body_metrics
        where user_id = $1 order by measured_at desc limit 1
        """,
        user_id,
    )
    alpha = 0.2
    ewma = weight_kg if prev is None else alpha * weight_kg + (1 - alpha) * float(prev)
    await conn.execute(
        """
        insert into body_metrics (user_id, weight_kg, weight_ewma, waist_cm)
        values ($1,$2,$3,$4)
        """,
        user_id,
        weight_kg,
        ewma,
        waist_cm,
    )


async def save_plan(conn: asyncpg.Connection, user_id: uuid.UUID, plan: dict[str, Any]) -> uuid.UUID:
    day = plan["day"]
    if isinstance(day, str):
        day = date.fromisoformat(day)
    plan_id = await conn.fetchval(
        """
        insert into daily_plans (
          user_id, day, day_state, wake_at, tone, nutrition, workout, study, suppress_checkins_until
        ) values ($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb,$8::jsonb,$9)
        on conflict (user_id, day) do update set
          day_state = excluded.day_state,
          wake_at = excluded.wake_at,
          tone = excluded.tone,
          nutrition = excluded.nutrition,
          workout = excluded.workout,
          study = excluded.study,
          suppress_checkins_until = excluded.suppress_checkins_until
        returning id
        """,
        user_id,
        day,
        plan["day_state"],
        _as_dt(plan.get("wake_at")),
        plan["tone"],
        json.dumps(plan["nutrition"]),
        json.dumps(plan["workout"]),
        json.dumps(plan["study"]),
        _as_dt(plan.get("suppress_checkins_until")),
    )
    await conn.execute("delete from micro_tasks where plan_id = $1", plan_id)
    for i, task in enumerate(plan.get("micro_tasks") or []):
        await conn.execute(
            """
            insert into micro_tasks (plan_id, user_id, kind, title, minutes, counts_toward_streak, sort_order)
            values ($1,$2,$3,$4,$5,$6,$7)
            """,
            plan_id,
            user_id,
            task["kind"],
            task["title"],
            task.get("minutes"),
            task.get("counts_toward_streak", True),
            i,
        )
    if plan.get("adjustment_reason"):
        await conn.execute(
            """
            insert into plan_adjustments (plan_id, user_id, from_state, to_state, reason, diff)
            values ($1,$2,$3,$4,$5,$6::jsonb)
            """,
            plan_id,
            user_id,
            plan.get("from_state"),
            plan["day_state"],
            plan["adjustment_reason"],
            json.dumps({"volume_multiplier": plan.get("volume_multiplier")}),
        )
    return plan_id


async def get_today_plan(conn: asyncpg.Connection, user_id: uuid.UUID, day: date) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        "select * from daily_plans where user_id = $1 and day = $2", user_id, day
    )
    if not row:
        return None
    tasks = await conn.fetch(
        "select * from micro_tasks where plan_id = $1 order by sort_order", row["id"]
    )
    plan = dict(row)
    for key in ("nutrition", "workout", "study"):
        val = plan.get(key)
        if isinstance(val, str):
            plan[key] = json.loads(val)
    plan["micro_tasks"] = [dict(t) for t in tasks]
    plan["id"] = str(plan["id"])
    return plan


async def complete_micro_task(conn: asyncpg.Connection, user_id: uuid.UUID, task_id: uuid.UUID) -> dict[str, Any]:
    row = await conn.fetchrow(
        """
        update micro_tasks set completed_at = now()
        where id = $1 and user_id = $2
        returning *
        """,
        task_id,
        user_id,
    )
    if not row:
        raise ValueError("task not found")
    plan = await conn.fetchrow("select day, day_state from daily_plans where id = $1", row["plan_id"])
    if plan and row["counts_toward_streak"]:
        await conn.execute(
            """
            insert into daily_streaks (user_id, day, showed_up, tasks_completed, day_state)
            values ($1,$2,true,1,$3)
            on conflict (user_id, day) do update set
              showed_up = true,
              tasks_completed = daily_streaks.tasks_completed + 1
            """,
            user_id,
            plan["day"],
            plan["day_state"],
        )
    return dict(row)


async def create_conversation(conn: asyncpg.Connection, user_id: uuid.UUID, channel: str = "text") -> uuid.UUID:
    return await conn.fetchval(
        """
        insert into conversations (user_id, channel) values ($1,$2) returning id
        """,
        user_id,
        channel,
    )


async def add_message(
    conn: asyncpg.Connection,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    role: str,
    content: str,
    turn_class: str | None = None,
    model_tier: str | None = None,
    token_counts: dict | None = None,
) -> uuid.UUID:
    return await conn.fetchval(
        """
        insert into messages (conversation_id, user_id, role, content, turn_class, model_tier, token_counts)
        values ($1,$2,$3,$4,$5,$6,$7::jsonb) returning id
        """,
        conversation_id,
        user_id,
        role,
        content,
        turn_class,
        model_tier,
        json.dumps(token_counts or {}),
    )


async def recent_messages(conn: asyncpg.Connection, conversation_id: uuid.UUID, limit: int = 6) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        select role, content from messages
        where conversation_id = $1
        order by created_at desc limit $2
        """,
        conversation_id,
        limit,
    )
    return list(reversed([dict(r) for r in rows]))


async def dashboard_stats(conn: asyncpg.Connection, user_id: uuid.UUID, days: int = 28) -> dict[str, Any]:
    weights = await conn.fetch(
        """
        select measured_at, weight_kg, weight_ewma from body_metrics
        where user_id = $1 order by measured_at desc limit $2
        """,
        user_id,
        days,
    )
    readiness = await conn.fetch(
        """
        select day, readiness_score, day_state from health_daily
        where user_id = $1 order by day desc limit $2
        """,
        user_id,
        days,
    )
    streaks = await conn.fetch(
        """
        select day, showed_up, tasks_completed, day_state from daily_streaks
        where user_id = $1 order by day desc limit $2
        """,
        user_id,
        days,
    )
    progress = await conn.fetch(
        """
        select status, count(*)::int as n from study_progress
        where user_id = $1 group by status
        """,
        user_id,
    )
    return {
        "weights": [dict(r) for r in reversed(weights)],
        "readiness": [dict(r) for r in reversed(readiness)],
        "streaks": [dict(r) for r in reversed(streaks)],
        "curriculum": {r["status"]: r["n"] for r in progress},
    }


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
