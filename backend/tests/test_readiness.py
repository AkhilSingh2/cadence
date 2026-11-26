from app.engine.adapter import adapt_plan
from app.engine.readiness import HealthSnapshot, MoodSnapshot, classify_day
from datetime import date


def test_green_day():
    health = HealthSnapshot(
        sleep_hours=7.8,
        sleep_efficiency=0.92,
        hrv_sdnn_ms=50,
        rhr_bpm=56,
        hrv_baseline=48,
        rhr_baseline=58,
    )
    mood = MoodSnapshot(valence=4, energy=4, stress=2)
    score, state = classify_day(health, mood, consecutive_red=0)
    assert state.value == "GREEN"
    assert score >= 0.70


def test_bad_day_red():
    health = HealthSnapshot(
        sleep_hours=4.8,
        sleep_efficiency=0.72,
        hrv_sdnn_ms=28,
        rhr_bpm=72,
        hrv_baseline=45,
        rhr_baseline=58,
    )
    mood = MoodSnapshot(valence=2, energy=2, stress=4)
    score, state = classify_day(health, mood, consecutive_red=0)
    assert state.value == "RED"
    plan = adapt_plan(
        state,
        score,
        day=date.today(),
        weight_kg=70,
        protein_per_kg=1.6,
        study_minutes_green=60,
        surplus_kcal=200,
        wake_at=None,
        hard_dislikes=["mass-gainer shakes"],
    )
    assert plan.study.minutes == 15
    assert plan.nutrition.surface_calories is False
    assert plan.volume_multiplier == 0.4
    assert "mass-gainer" not in (plan.nutrition.first_intake or {}).get("suggestion", "").lower()


def test_deload_after_three_red():
    health = HealthSnapshot(sleep_hours=5.0, sleep_efficiency=0.7)
    score, state = classify_day(health, None, consecutive_red=3)
    assert state.value == "DELOAD"


def test_subjective_veto():
    health = HealthSnapshot(
        sleep_hours=8.0,
        sleep_efficiency=0.95,
        hrv_sdnn_ms=55,
        rhr_bpm=55,
        hrv_baseline=50,
        rhr_baseline=58,
    )
    mood = MoodSnapshot(valence=1, energy=2, stress=5)
    score, state = classify_day(health, mood, consecutive_red=0)
    assert score <= 0.45
    assert state.value in ("RED", "AMBER")
