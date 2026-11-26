from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class HealthDayIn(BaseModel):
    day: date
    sleep_start: datetime | None = None
    sleep_end: datetime | None = None
    sleep_hours: float | None = None
    sleep_efficiency: float | None = None
    sleep_stages: dict[str, Any] = Field(default_factory=dict)
    hrv_sdnn_ms: float | None = None
    rhr_bpm: float | None = None
    active_energy_kcal: float | None = None
    steps: int | None = None
    wake_detected_at: datetime | None = None
    hrv_baseline_14d: float | None = None
    rhr_baseline_14d: float | None = None
    source: str = "healthkit"


class HealthSyncIn(BaseModel):
    days: list[HealthDayIn]


class MoodIn(BaseModel):
    valence: int = Field(ge=1, le=5)
    energy: int = Field(ge=1, le=5)
    stress: int = Field(ge=1, le=5)
    trigger_text: str | None = None
    source: str = "tap"


class WeightIn(BaseModel):
    weight_kg: float
    waist_cm: float | None = None


class ChatIn(BaseModel):
    message: str
    conversation_id: UUID | None = None
    turn_class: str = "chat"


class TaskCompleteIn(BaseModel):
    task_id: UUID


class PreferenceIn(BaseModel):
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProblemAttemptIn(BaseModel):
    problem_ref: str
    difficulty: str = "medium"
    outcome: str
    bug_tags: list[str] = Field(default_factory=list)
    minutes_spent: int | None = None
    hints_used: int = 0
    topic_id: UUID | None = None
