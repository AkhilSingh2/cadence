from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from .readiness import DayState, Tone


@dataclass
class NutritionPlan:
    surface_calories: bool
    protein_floor_g: float
    first_intake: dict[str, Any] | None
    meal_count: int
    soft_surplus_kcal: int | None = None


@dataclass
class StudyBlock:
    minutes: int
    task_title: str
    allow_hints: bool
    counts_toward_streak: bool
    difficulty_bias: str  # at | below | above mastery


@dataclass
class DailyPlan:
    day: date
    day_state: DayState
    tone: Tone
    volume_multiplier: float
    wake_at: datetime | None
    workout: dict[str, Any]
    nutrition: NutritionPlan
    study: StudyBlock
    suppress_checkins_until: datetime | None
    micro_tasks: list[dict[str, Any]] = field(default_factory=list)
    readiness_score: float = 0.0
    adjustment_reason: str = ""
    from_state: str | None = None


def _protein(weight_kg: float, per_kg: float) -> float:
    return round(weight_kg * per_kg, 1)


def baseline_plan(
    day: date,
    weight_kg: float,
    protein_per_kg: float,
    study_minutes_green: int,
    surplus_kcal: int,
    wake_at: datetime | None,
) -> DailyPlan:
    return DailyPlan(
        day=day,
        day_state=DayState.GREEN,
        tone=Tone.COACHING,
        volume_multiplier=1.0,
        wake_at=wake_at,
        workout={
            "kind": "full_body",
            "minutes": 45,
            "rpe_cap": 8,
            "title": "Full-body strength (prescribed)",
        },
        nutrition=NutritionPlan(
            surface_calories=True,
            protein_floor_g=_protein(weight_kg, protein_per_kg),
            first_intake={
                "suggestion": "Whatever is easy — eggs, curd+banana, or leftover dal-rice",
                "effort": "low",
            },
            meal_count=3,
            soft_surplus_kcal=surplus_kcal,
        ),
        study=StudyBlock(
            minutes=study_minutes_green,
            task_title="Study: next unfinished topic at current mastery",
            allow_hints=True,
            counts_toward_streak=True,
            difficulty_bias="at",
        ),
        suppress_checkins_until=None,
    )


def retrieve_liked_low_appetite_option(hard_dislikes: list[str]) -> dict[str, Any]:
    options = [
        {
            "suggestion": "Flavored milk or protein coffee + banana (sip, no cooking)",
            "effort": "none",
            "texture": "drinkable",
            "appetite": "low",
        },
        {
            "suggestion": "Curd + honey + handful of roasted chana",
            "effort": "none",
            "texture": "soft",
            "appetite": "low",
        },
        {
            "suggestion": "Peanut butter on two biscuits or toast — no shake",
            "effort": "none",
            "texture": "soft",
            "appetite": "low",
        },
    ]
    for opt in options:
        text = opt["suggestion"].lower()
        if any(d.lower() in text for d in hard_dislikes):
            continue
        if "mass-gainer" in " ".join(hard_dislikes).lower() and "shake" in text and "protein coffee" not in text:
            continue
        return opt
    return options[0]


def build_micro_tasks(plan: DailyPlan) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    if plan.nutrition.first_intake:
        tasks.append(
            {
                "kind": "intake",
                "title": f"First intake: {plan.nutrition.first_intake['suggestion']}",
                "minutes": 5,
                "counts_toward_streak": True,
            }
        )
    tasks.append(
        {
            "kind": "movement",
            "title": plan.workout.get("title", "Move"),
            "minutes": plan.workout.get("minutes", 15),
            "counts_toward_streak": True,
        }
    )
    tasks.append(
        {
            "kind": "study",
            "title": f"{plan.study.task_title} ({plan.study.minutes} min)",
            "minutes": plan.study.minutes,
            "counts_toward_streak": True,
        }
    )
    if plan.day_state in (DayState.RED, DayState.DELOAD):
        tasks.append(
            {
                "kind": "recovery",
                "title": "Optional: 10-minute walk or nap — either counts",
                "minutes": 10,
                "counts_toward_streak": True,
            }
        )
    return tasks


def adapt_plan(
    state: DayState,
    score: float,
    *,
    day: date,
    weight_kg: float,
    protein_per_kg: float,
    study_minutes_green: int,
    surplus_kcal: int,
    wake_at: datetime | None,
    hard_dislikes: list[str] | None = None,
) -> DailyPlan:
    hard_dislikes = hard_dislikes or []
    plan = baseline_plan(day, weight_kg, protein_per_kg, study_minutes_green, surplus_kcal, wake_at)
    plan.readiness_score = score
    plan.from_state = DayState.GREEN.value

    if state in (DayState.RED, DayState.DELOAD):
        plan.day_state = state
        plan.volume_multiplier = 0.4
        plan.workout = {
            "kind": "movement_snack",
            "minutes": 12,
            "rpe_cap": 5,
            "title": "Movement snack: easy walk + band pulls",
        }
        plan.nutrition = NutritionPlan(
            surface_calories=False,
            protein_floor_g=_protein(weight_kg, 1.4),
            first_intake=retrieve_liked_low_appetite_option(hard_dislikes),
            meal_count=2,
            soft_surplus_kcal=None,
        )
        plan.study = StudyBlock(
            minutes=15,
            task_title="Easy study review below mastery — one small problem",
            allow_hints=True,
            counts_toward_streak=True,
            difficulty_bias="below",
        )
        plan.tone = Tone.EMPATHETIC_NO_GUILT
        if wake_at is not None:
            plan.suppress_checkins_until = wake_at + timedelta(minutes=45)
        plan.adjustment_reason = (
            f"{state.value}: dialed back volume to 40%, protein floor only, "
            f"15m study below mastery, empathetic tone"
        )
    elif state == DayState.AMBER:
        plan.day_state = state
        plan.volume_multiplier = 0.7
        plan.workout = {
            "kind": "scaled_full_body",
            "minutes": 30,
            "rpe_cap": 7,
            "title": "Scaled strength (70% volume)",
        }
        plan.nutrition.surface_calories = False
        plan.nutrition.soft_surplus_kcal = None
        plan.study = StudyBlock(
            minutes=30,
            task_title="Study: one topic at current mastery",
            allow_hints=True,
            counts_toward_streak=True,
            difficulty_bias="at",
        )
        plan.tone = Tone.NEUTRAL
        plan.adjustment_reason = "AMBER: 70% volume, hide calories, 30m study"
    else:
        plan.day_state = DayState.GREEN
        plan.tone = Tone.COACHING
        plan.adjustment_reason = "GREEN: full prescribed plan"

    plan.micro_tasks = build_micro_tasks(plan)
    return plan


def plan_to_dict(plan: DailyPlan) -> dict[str, Any]:
    def ser(v: Any) -> Any:
        if isinstance(v, (DayState, Tone)):
            return v.value
        if isinstance(v, date) and not isinstance(v, datetime):
            return v.isoformat()
        if isinstance(v, datetime):
            return v.isoformat()
        if isinstance(v, NutritionPlan):
            return asdict(v)
        if isinstance(v, StudyBlock):
            return asdict(v)
        return v

    return {
        "day": plan.day.isoformat(),
        "day_state": plan.day_state.value,
        "tone": plan.tone.value,
        "volume_multiplier": plan.volume_multiplier,
        "wake_at": plan.wake_at.isoformat() if plan.wake_at else None,
        "workout": plan.workout,
        "nutrition": asdict(plan.nutrition),
        "study": asdict(plan.study),
        "suppress_checkins_until": (
            plan.suppress_checkins_until.isoformat() if plan.suppress_checkins_until else None
        ),
        "micro_tasks": plan.micro_tasks,
        "readiness_score": plan.readiness_score,
        "adjustment_reason": plan.adjustment_reason,
        "from_state": plan.from_state,
    }


def voice_opener(plan: DailyPlan) -> str:
    if plan.tone == Tone.EMPATHETIC_NO_GUILT:
        return (
            "Rough recovery day — we are not doing a full program. "
            "One easy sip-something when you are ready, a short walk later, "
            "and fifteen minutes on an easy problem if the head clears. Nothing else is owed."
        )
    if plan.tone == Tone.NEUTRAL:
        return (
            f"Amber day. Scaled session (~{plan.workout.get('minutes')} min), "
            f"protein floor {plan.nutrition.protein_floor_g}g, "
            f"{plan.study.minutes} minutes of study. Pick the order that fits."
        )
    return (
        f"Green day. Full-body work, protein around {plan.nutrition.protein_floor_g}g, "
        f"and {plan.study.minutes} minutes of study. One thing at a time."
    )


def opener_from_plan_dict(plan: dict[str, Any]) -> str:
    tone = plan.get("tone") or Tone.NEUTRAL.value
    nutrition = plan.get("nutrition") or {}
    study = plan.get("study") or {}
    workout = plan.get("workout") or {}
    protein = nutrition.get("protein_floor_g") or 0
    if tone == Tone.EMPATHETIC_NO_GUILT.value:
        return (
            "Rough recovery day — we are not doing a full program. "
            "One easy sip-something when you are ready, a short walk later, "
            "and fifteen minutes on an easy problem if the head clears. Nothing else is owed."
        )
    if tone == Tone.NEUTRAL.value:
        return (
            f"Amber day. Scaled session (~{workout.get('minutes', 30)} min), "
            f"protein floor {protein}g, {study.get('minutes', 30)} minutes of study. "
            "Pick the order that fits."
        )
    return (
        f"Green day. Full-body work, protein around {protein}g, "
        f"and {study.get('minutes', 60)} minutes of study. One thing at a time."
    )


def parse_wake(wake_at: datetime | None) -> datetime | None:
    if wake_at is None:
        return None
    if wake_at.tzinfo is None:
        return wake_at.replace(tzinfo=timezone.utc)
    return wake_at
