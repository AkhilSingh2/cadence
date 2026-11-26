from __future__ import annotations

import logging
import uuid

import asyncpg

from app.llm.router import generate
from app.memory.ingest import ingest_text

logger = logging.getLogger(__name__)


async def consolidate_user(conn: asyncpg.Connection, user_id: uuid.UUID) -> dict:
    rows = await conn.fetch(
        """
        select id, content from memory_chunks
        where user_id = $1 and kind = 'episodic'
          and created_at < now() - interval '24 hours'
        order by created_at asc
        limit 40
        """,
        user_id,
    )
    if not rows:
        return {"promoted": 0, "deleted_episodic": 0}

    blob = "\n".join(f"- {r['content']}" for r in rows)
    prompt = (
        "Extract durable facts from these episodic notes. "
        "Return plain lines prefixed with KIND| where KIND is semantic, preference, trigger, or bug_pattern. "
        "Max 8 lines. If nothing durable, return NONE.\n\n"
        f"{blob}"
    )
    result = await generate(
        system="You compress episodic memories into durable facts.",
        messages=[{"role": "user", "content": prompt}],
        turn_class="chat",
    )
    text = result["text"].strip()
    promoted = 0
    if text.upper() != "NONE":
        for line in text.splitlines():
            line = line.strip().lstrip("- ").strip()
            if "|" not in line:
                continue
            kind, content = line.split("|", 1)
            kind = kind.strip().lower()
            content = content.strip()
            if kind not in {"semantic", "preference", "trigger", "bug_pattern"} or not content:
                continue
            await ingest_text(conn, user_id, content, kind=kind, salience=0.75)
            promoted += 1

    ids = [r["id"] for r in rows]
    await conn.execute("delete from memory_chunks where id = any($1::uuid[])", ids)

    # Purge raw messages older than 30 days
    await conn.execute(
        """
        delete from messages
        where user_id = $1 and created_at < now() - interval '30 days'
        """,
        user_id,
    )
    return {"promoted": promoted, "deleted_episodic": len(ids)}
