from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_FLASH_CLASSES = {
    "morning_checkin",
    "mood_log",
    "meal_log",
    "workout_log",
    "dsa_hint",
    "smalltalk",
    "chat",
}
_FRONTIER_CLASSES = {"weekly_review", "monthly_recomp", "dsa_escalation"}

# Prefer models verified against current Gemini free-tier keys.
_GENERATE_CANDIDATES = [
    "gemini-3.1-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-3.5-flash",
    "gemini-3.6-flash",
]
_EMBED_CANDIDATES = [
    "gemini-embedding-001",
    "models/gemini-embedding-001",
]


def pick_tier(turn_class: str) -> str:
    if turn_class in _FRONTIER_CLASSES:
        return "frontier"
    return "flash"


def _parse_plan_bits(system: str) -> dict[str, str]:
    state = "UNKNOWN"
    m = re.search(r"state=([A-Z]+)", system)
    if m:
        state = m.group(1)
    protein = re.search(r"'protein_floor_g':\s*([0-9.]+)|protein_floor_g[\"']?:\s*([0-9.]+)", system)
    minutes = re.search(r"'minutes':\s*(\d+)|\"minutes\":\s*(\d+)", system)
    return {
        "state": state,
        "protein": (protein.group(1) or protein.group(2)) if protein else "85",
        "study_min": (minutes.group(1) or minutes.group(2)) if minutes else "15",
    }


def _offline_reply(system: str, user_message: str, turn_class: str) -> str:
    lower = user_message.lower().strip()
    bits = _parse_plan_bits(system)
    state = bits["state"]
    protein = bits["protein"]
    study_min = bits["study_min"]

    if "solution" in lower or "give me the code" in lower or "full answer" in lower or "write the code" in lower:
        return (
            "I will not paste a full working solution. "
            "Tell me your current approach and where it fails (base case / edge case), "
            "and I will give the next small hint only."
        )

    if any(w in lower for w in ("hello", "hi", "hey", "yo")) and len(lower) < 12:
        if state in ("RED", "DELOAD"):
            return (
                f"Hey — today is a {state} recovery day. "
                f"Tiny plan only: easy sip-something (~{protein}g protein floor), "
                f"a short walk, and {study_min} minutes on an easy practice problem. "
                "Nothing else is owed. What do you want to tackle first?"
            )
        if state == "AMBER":
            return (
                f"Hey — amber day. Scaled training, protein floor ~{protein}g (no calorie target), "
                f"{study_min} min study. Want food, movement, or study first?"
            )
        return (
            f"Hey — green day if recovery holds. Protein ~{protein}g, full-ish session, "
            f"~{study_min} min study. Food, lift, or study?"
        )

    if any(
        w in lower
        for w in ("tired", "exhausted", "awful", "rough", "slept", "sleep", "stressed", "late", "bad day", "burnt", "burned")
    ):
        return (
            f"Got it — we treat this as a low-energy day (current plan state: {state}). "
            f"Skip the hero session. Do one of: flavored milk/curd+banana, a 10–12 min walk, "
            f"or {study_min} easy minutes of study below mastery. "
            "Mark any one Done in Today and it counts as showing up."
        )

    if any(w in lower for w in ("food", "eat", "meal", "hungry", "appetite", "breakfast", "lunch", "dinner", "protein")):
        if state in ("RED", "DELOAD", "AMBER"):
            return (
                f"Low-effort only. Aim for ~{protein}g protein today — calories stay hidden. "
                "Ideas: flavored milk + banana, curd + honey + chana, peanut butter on toast, "
                "leftover dal-rice. No mass-gainer shakes. What sounds least awful?"
            )
        return (
            f"Keep convenience-friendly meals around ~{protein}g protein. "
            "Dal-rice, eggs, curd, paneer wrap, peanut butter toast all count. Want a 2-meal sketch?"
        )

    if any(w in lower for w in ("workout", "gym", "lift", "train", "exercise", "walk")):
        if state in ("RED", "DELOAD"):
            return (
                "Not a heavy day. Movement snack: easy walk + band pull-aparts, ~12 min, RPE ≤ 5. "
                "Stop while it still feels easy."
            )
        if state == "AMBER":
            return "Scaled full-body ~30 min at RPE ≤ 7. Cut a set from each lift vs a normal day."
        return "Full-body strength ~45 min is fine if joints feel good. Leave 1–2 reps in the tank."

    if any(w in lower for w in ("study", "dsa", "leetcode", "code", "problem", "array", "tree", "graph", "dp")):
        if turn_class == "dsa_hint" or "hint" in lower:
            return (
                "Before coding: restate the invariant in one sentence, then pick the simplest data structure "
                "that protects it. What’s the smallest input where your idea breaks?"
            )
        return (
            f"Timebox {study_min} minutes. "
            + (
                "Pick something below your current mastery — easy win today."
                if state in ("RED", "DELOAD")
                else "One topic at your current level is enough."
            )
            + " Showing up for the block counts."
        )

    if any(w in lower for w in ("plan", "today", "what should", "schedule", "do today")):
        if state in ("RED", "DELOAD"):
            return (
                f"Today’s adapted plan is {state}: protein floor ~{protein}g (no calorie number), "
                f"12-min movement snack, {study_min}-min easy study block. "
                "Pick one micro-task and mark it Done."
            )
        return (
            f"Today’s plan is {state}: protein ~{protein}g, training as prescribed, "
            f"{study_min} min study. Say food / workout / study and I’ll zoom in."
        )

    if state in ("RED", "DELOAD"):
        return (
            f"I’m here. Today is dialed back ({state}). "
            "Ask me about food, a short walk, or an easy study block — one thing."
        )
    return (
        f"I’m here (plan state {state}). "
        "Ask about food, training, or study and I’ll keep it concrete."
    )


def _contents_from_messages(messages: list[dict[str, str]]) -> list[dict[str, Any]]:
    contents: list[dict[str, Any]] = []
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})
    return contents


async def _gemini_generate(system: str, messages: list[dict[str, str]], model_name: str) -> str:
    settings = get_settings()
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model_name}:generateContent?key={settings.gemini_api_key}"
    )
    payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": _contents_from_messages(messages),
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 512},
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0)) as client:
        resp = await client.post(url, json=payload)
        data = resp.json()
        if resp.status_code >= 400:
            raise RuntimeError(data.get("error", {}).get("message") or resp.text[:200])
        candidates = data.get("candidates") or []
        parts = (((candidates[0] if candidates else {}).get("content") or {}).get("parts") or [])
        text = "".join(p.get("text", "") for p in parts).strip()
        if not text:
            raise RuntimeError("empty model response")
        return text


async def generate(
    *,
    system: str,
    messages: list[dict[str, str]],
    turn_class: str = "chat",
) -> dict[str, Any]:
    settings = get_settings()
    tier = pick_tier(turn_class)
    user_message = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")

    if not settings.gemini_api_key:
        return {
            "text": _offline_reply(system, user_message, turn_class),
            "model_tier": "none",
            "model": "offline-fallback",
        }

    preferred = settings.gemini_frontier_model if tier == "frontier" else settings.gemini_flash_model
    candidates = [preferred, *_GENERATE_CANDIDATES]
    seen: set[str] = set()
    models = [m for m in candidates if not (m in seen or seen.add(m))]

    last_err: Exception | None = None
    for model_name in models:
        try:
            text = await _gemini_generate(system, messages, model_name)
            return {"text": text, "model_tier": tier, "model": model_name}
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            logger.warning("generate model %s failed: %s", model_name, exc)

    logger.error("all generate models failed: %s", last_err)
    return {
        "text": _offline_reply(system, user_message, turn_class),
        "model_tier": "none",
        "model": "offline-fallback",
        "error": str(last_err) if last_err else "unknown",
    }


def _pseudo_embedding(text: str, dims: int) -> list[float]:
    import hashlib
    import struct

    digest = hashlib.sha256(text.encode("utf-8")).digest()
    vals: list[float] = []
    seed = digest
    while len(vals) < dims:
        seed = hashlib.sha256(seed).digest()
        for i in range(0, len(seed), 4):
            if len(vals) >= dims:
                break
            (n,) = struct.unpack(">I", seed[i : i + 4])
            vals.append((n / 2**32) * 2 - 1)
    norm = sum(v * v for v in vals) ** 0.5 or 1.0
    return [v / norm for v in vals]


async def generate_embedding(text: str) -> list[float]:
    settings = get_settings()
    if not settings.gemini_api_key:
        return _pseudo_embedding(text, settings.embedding_dims)

    candidates = [settings.gemini_embed_model, *_EMBED_CANDIDATES]
    seen: set[str] = set()
    models = [m for m in candidates if not (m in seen or seen.add(m))]

    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0)) as client:
        for model_name in models:
            bare = model_name.replace("models/", "")
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{bare}:embedContent?key={settings.gemini_api_key}"
            )
            payload = {
                "model": f"models/{bare}",
                "content": {"parts": [{"text": text}]},
                "outputDimensionality": settings.embedding_output_dims,
            }
            try:
                resp = await client.post(url, json=payload)
                data = resp.json()
                if resp.status_code >= 400:
                    raise RuntimeError(data.get("error", {}).get("message") or resp.text[:200])
                emb = list((data.get("embedding") or {}).get("values") or [])
                if not emb:
                    raise RuntimeError("empty embedding")
                if len(emb) > settings.embedding_dims:
                    emb = emb[: settings.embedding_dims]
                elif len(emb) < settings.embedding_dims:
                    emb = emb + [0.0] * (settings.embedding_dims - len(emb))
                return emb
            except Exception as exc:  # noqa: BLE001
                logger.warning("embed model %s failed: %s", model_name, exc)

    return _pseudo_embedding(text, settings.embedding_dims)
