from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg

from app.llm.router import generate_embedding


def _vec_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{v:.8f}" for v in values) + "]"


async def ingest_text(
    conn: asyncpg.Connection,
    user_id: uuid.UUID,
    content: str,
    *,
    kind: str = "episodic",
    metadata: dict[str, Any] | None = None,
    salience: float = 0.5,
    source_id: uuid.UUID | None = None,
) -> uuid.UUID:
    embedding = await generate_embedding(content)
    mid = uuid.uuid4()
    await conn.execute(
        """
        insert into memory_chunks (id, user_id, kind, source_id, content, embedding, metadata, salience)
        values ($1,$2,$3,$4,$5,$6::vector,$7::jsonb,$8)
        """,
        mid,
        user_id,
        kind,
        source_id,
        content,
        _vec_literal(embedding),
        json.dumps(metadata or {}),
        salience,
    )
    return mid


async def upsert_preference(
    conn: asyncpg.Connection,
    user_id: uuid.UUID,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> uuid.UUID:
    return await ingest_text(
        conn,
        user_id,
        content,
        kind="preference",
        metadata=metadata,
        salience=0.9,
    )
