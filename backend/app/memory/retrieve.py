from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import Any

import asyncpg

from app.llm.router import generate_embedding
from app.memory.ingest import _vec_literal


def _rrf(rank: int, k: int = 60) -> float:
    return 1.0 / (k + rank)


def _recency_decay(last_accessed: datetime | None, created: datetime | None) -> float:
    ref = last_accessed or created
    if ref is None:
        return 0.7
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    days = max((datetime.now(timezone.utc) - ref).total_seconds() / 86400.0, 0.0)
    return math.exp(-days / 45.0)


async def retrieve_memories(
    conn: asyncpg.Connection,
    user_id: uuid.UUID,
    query: str,
    *,
    kinds: list[str] | None = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    embedding = await generate_embedding(query)
    vec = _vec_literal(embedding)
    kind_filter = kinds or ["episodic", "semantic", "preference", "trigger", "bug_pattern"]

    vector_rows = await conn.fetch(
        """
        select id, kind, content, salience, last_accessed_at, created_at, metadata,
               embedding <=> $1::vector as dist
        from memory_chunks
        where user_id = $2 and kind = any($3::text[]) and embedding is not null
        order by embedding <=> $1::vector
        limit 20
        """,
        vec,
        user_id,
        kind_filter,
    )
    bm25_rows = await conn.fetch(
        """
        select id, kind, content, salience, last_accessed_at, created_at, metadata,
               ts_rank_cd(content_tsv, plainto_tsquery('english', $1)) as rank
        from memory_chunks
        where user_id = $2 and kind = any($3::text[])
          and content_tsv @@ plainto_tsquery('english', $1)
        order by rank desc
        limit 20
        """,
        query,
        user_id,
        kind_filter,
    )

    scores: dict[str, float] = {}
    payloads: dict[str, dict[str, Any]] = {}

    for i, row in enumerate(vector_rows):
        key = str(row["id"])
        scores[key] = scores.get(key, 0.0) + _rrf(i + 1)
        payloads[key] = dict(row)
    for i, row in enumerate(bm25_rows):
        key = str(row["id"])
        scores[key] = scores.get(key, 0.0) + _rrf(i + 1)
        payloads[key] = dict(row)

    ranked: list[tuple[str, float]] = []
    for key, base in scores.items():
        row = payloads[key]
        salience = float(row.get("salience") or 0.5)
        decay = _recency_decay(row.get("last_accessed_at"), row.get("created_at"))
        final = base * (0.5 + 0.5 * salience) * decay
        ranked.append((key, final))
    ranked.sort(key=lambda x: x[1], reverse=True)

    # Light MMR: skip near-duplicate content prefixes
    selected: list[dict[str, Any]] = []
    seen_prefixes: list[str] = []
    for key, _ in ranked:
        content = payloads[key]["content"]
        prefix = content[:80].lower()
        if any(prefix[:40] == s[:40] for s in seen_prefixes):
            continue
        seen_prefixes.append(prefix)
        item = payloads[key]
        selected.append(
            {
                "id": key,
                "kind": item["kind"],
                "content": content,
                "salience": float(item.get("salience") or 0.5),
                "metadata": item.get("metadata") or {},
            }
        )
        if len(selected) >= limit:
            break

    # Touch accessed rows
    for item in selected:
        await conn.execute(
            """
            update memory_chunks
            set last_accessed_at = now(),
                salience = least(1.0, salience + 0.02)
            where id = $1
            """,
            uuid.UUID(item["id"]),
        )
    return selected
