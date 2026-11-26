from __future__ import annotations

import re

from app.llm.prompts import DSA_GUARDRAIL, build_system_prompt
from app.llm.router import generate

_SOLUTION_MARKERS = [
    re.compile(r"```(?:python|java|cpp|c\+\+|javascript|ts)", re.I),
    re.compile(r"\bdef\s+\w+\s*\(.*\)\s*:", re.I),
    re.compile(r"\bclass\s+Solution\b"),
    re.compile(r"\bpublic\s+static\s+void\s+main\b"),
]


def looks_like_full_solution(text: str) -> bool:
    has_marker = any(m.search(text) for m in _SOLUTION_MARKERS)
    if not has_marker:
        return False
    fences = text.count("```")
    # Fenced solution blocks or multi-line method bodies
    if fences >= 2 and text.count("\n") >= 6:
        return True
    if text.count("\n") >= 8 and ("return " in text or "def " in text):
        return True
    return False


async def tutor_reply(
    *,
    user_message: str,
    history: list[dict[str, str]],
    plan_summary: str,
    memories: list[str],
    tone: str,
) -> dict:
    system = build_system_prompt(tone=tone, plan_summary=plan_summary, memories=memories) + "\n" + DSA_GUARDRAIL
    messages = history + [{"role": "user", "content": user_message}]
    result = await generate(system=system, messages=messages, turn_class="dsa_hint")
    text = result["text"]
    if looks_like_full_solution(text):
        result = await generate(
            system=system
            + "\nYour previous draft leaked a full solution. Reply again with ONLY the next small hint.",
            messages=messages,
            turn_class="dsa_hint",
        )
        text = result["text"]
        if looks_like_full_solution(text):
            text = (
                "I will not paste a full working solution. "
                "What is your current approach for the base case or the first failing edge case?"
            )
            result["model_tier"] = "none"
    result["text"] = text
    return result
