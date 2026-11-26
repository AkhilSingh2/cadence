from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import get_settings
from app.db import repo
from app.db.session import get_pool
from app.llm.prompts import build_system_prompt
from app.llm.router import generate
from app.memory.ingest import ingest_text
from app.memory.retrieve import retrieve_memories
from app.engine.adapter import opener_from_plan_dict
from app.services.planning import build_and_save_plan
from app.tools.dsa_tutor import tutor_reply

logger = logging.getLogger(__name__)
router = APIRouter()


def _split_sentences(text: str) -> list[str]:
    parts: list[str] = []
    buf = ""
    for ch in text:
        buf += ch
        if ch in ".?!" and len(buf.strip()) > 1:
            parts.append(buf.strip())
            buf = ""
    if buf.strip():
        parts.append(buf.strip())
    return parts or [text]


@router.websocket("/voice")
async def voice_socket(ws: WebSocket):
    await ws.accept()
    settings = get_settings()
    user_id = uuid.UUID(settings.dev_user_id)
    conversation_id: uuid.UUID | None = None
    warm_memories: list[str] = []

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            mtype = msg.get("type")
            if mtype == "hello":
                if msg.get("user_id"):
                    user_id = uuid.UUID(msg["user_id"])
                await ws.send_json({"type": "hello_ack", "user_id": str(user_id)})
                continue

            if mtype == "partial_transcript":
                text = (msg.get("text") or "").strip()
                if len(text) < 8:
                    continue
                pool = get_pool()
                async with pool.acquire() as conn:
                    memories = await retrieve_memories(conn, user_id, text, limit=6)
                    warm_memories = [m["content"] for m in memories]
                await ws.send_json({"type": "retrieval_warm", "count": len(warm_memories)})
                continue

            if mtype == "final_turn":
                text = (msg.get("text") or "").strip()
                turn_class = msg.get("turn_class") or "morning_checkin"
                if not text:
                    await ws.send_json({"type": "error", "detail": "empty transcript"})
                    continue

                pool = get_pool()
                async with pool.acquire() as conn:
                    await repo.ensure_demo_user(conn, user_id)
                    plan = await repo.get_today_plan(conn, user_id, datetime.now(timezone.utc).date())
                    if plan is None:
                        plan = await build_and_save_plan(conn, user_id)
                    if conversation_id is None:
                        conversation_id = await repo.create_conversation(conn, user_id, "voice")
                    await repo.add_message(conn, user_id, conversation_id, "user", text, turn_class)

                    memories = warm_memories or [
                        m["content"] for m in await retrieve_memories(conn, user_id, text, limit=6)
                    ]
                    plan_summary = (
                        f"state={plan.get('day_state')} tone={plan.get('tone')} "
                        f"study={plan.get('study')} nutrition={plan.get('nutrition')}"
                    )
                    history = await repo.recent_messages(conn, conversation_id, limit=6)

                    if turn_class == "dsa_hint":
                        result = await tutor_reply(
                            user_message=text,
                            history=history[:-1],
                            plan_summary=plan_summary,
                            memories=memories,
                            tone=plan.get("tone") or "neutral",
                        )
                    else:
                        system = build_system_prompt(
                            tone=plan.get("tone") or "neutral",
                            plan_summary=plan_summary,
                            memories=memories,
                        )
                        # Prefer plan opener on first morning check-in turn
                        if turn_class == "morning_checkin" and len(history) <= 1:
                            result = {
                                "text": plan.get("opener") or opener_from_plan_dict(plan),
                                "model_tier": "none",
                            }
                        else:
                            result = await generate(
                                system=system, messages=history, turn_class=turn_class
                            )

                    await repo.add_message(
                        conn,
                        user_id,
                        conversation_id,
                        "assistant",
                        result["text"],
                        turn_class,
                        result.get("model_tier"),
                    )
                    await ingest_text(
                        conn,
                        user_id,
                        f"User: {text}\nAssistant: {result['text']}",
                        kind="episodic",
                    )

                sentences = _split_sentences(result["text"])
                await ws.send_json(
                    {
                        "type": "assistant_start",
                        "conversation_id": str(conversation_id),
                        "model_tier": result.get("model_tier"),
                        "day_state": plan.get("day_state"),
                    }
                )
                for i, sentence in enumerate(sentences):
                    await ws.send_json(
                        {
                            "type": "assistant_sentence",
                            "index": i,
                            "text": sentence,
                            "is_final": i == len(sentences) - 1,
                        }
                    )
                await ws.send_json({"type": "assistant_end"})
                warm_memories = []
                continue

            await ws.send_json({"type": "error", "detail": f"unknown type {mtype}"})
    except WebSocketDisconnect:
        logger.info("voice socket disconnected")
    except Exception as exc:  # noqa: BLE001
        logger.exception("voice socket error: %s", exc)
        try:
            await ws.send_json({"type": "error", "detail": str(exc)})
        except Exception:  # noqa: BLE001
            pass
