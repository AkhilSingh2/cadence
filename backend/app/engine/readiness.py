from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DayState(str, Enum):
    GREEN = "GREEN"
    AMBER = "AMBER"
    RED = "RED"
    DELOAD = "DELOAD"


class Tone(str, Enum):
    COACHING = "coaching"
    NEUTRAL = "neutral"
    EMPATHETIC_NO_GUILT = "empathetic_no_guilt"


@dataclass
class HealthSnapshot:
    sleep_hours: float | None = None
    sleep_efficiency: float | None = None
    hrv_sdnn_ms: float | None = None
    rhr_bpm: float | None = None
    hrv_baseline: float | None = None
    rhr_baseline: float | None = None


@dataclass
class MoodSnapshot:
    valence: int
    energy: int
    stress: int


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def z_to_unit(value: float | None, baseline: float | None, sigma: float | None = None) -> float:
    if baseline is None or value is None:
        return 0.5
    sigma = sigma or max(baseline * 0.15, 1.0)
    z = (value - baseline) / sigma
    return clamp(0.5 + z * 0.25, 0.0, 1.0)


def inv_z_to_unit(value: float | None, baseline: float | None, sigma: float | None = None) -> float:
    if baseline is None or value is None:
        return 0.5
    sigma = sigma or max(baseline * 0.08, 1.0)
    z = (baseline - value) / sigma
    return clamp(0.5 + z * 0.25, 0.0, 1.0)


def classify_day(
    health: HealthSnapshot,
    mood: MoodSnapshot | None,
    consecutive_red: int,
) -> tuple[float, DayState]:
    s = 0.0
    sleep_h = health.sleep_hours if health.sleep_hours is not None else 6.5
    sleep_eff = health.sleep_efficiency if health.sleep_efficiency is not None else 0.85

    s += clamp(sleep_h / 7.5, 0, 1) * 0.30
    s += clamp(sleep_eff / 0.90, 0, 1) * 0.15
    s += z_to_unit(health.hrv_sdnn_ms, health.hrv_baseline) * 0.25
    s += inv_z_to_unit(health.rhr_bpm, health.rhr_baseline) * 0.15

    if mood is not None:
        s += (mood.energy / 5.0) * 0.15
        if mood.stress >= 4 or mood.valence <= 2:
            s = min(s, 0.45)
    else:
        s += 0.5 * 0.15

    if consecutive_red >= 3:
        return s, DayState.DELOAD
    if s >= 0.70:
        return s, DayState.GREEN
    if s >= 0.45:
        return s, DayState.AMBER
    return s, DayState.RED
