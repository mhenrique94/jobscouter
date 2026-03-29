"""deduplicate jobs and replace search_keyword with search_keywords

Revision ID: 0005_deduplicate_jobs
Revises: 0004_add_filter_config
Create Date: 2026-03-29 00:00:00
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "0005_deduplicate_jobs"
down_revision = "0004_add_filter_config"
branch_labels = None
depends_on = None

# Ordem de prioridade de status para decidir qual análise de IA preservar
_STATUS_PRIORITY = {"analyzed": 3, "discarded": 2, "ready_for_ai": 1, "pending": 0}


def _best_record(group: list) -> object:
    """Retorna o registro com a análise de IA mais completa do grupo."""
    return max(group, key=lambda r: _STATUS_PRIORITY.get(r.status or "pending", 0))


def _parse_keywords(raw: object) -> list[str]:
    if isinstance(raw, list):
        return raw
    return json.loads(raw or "[]")


def _merge_keywords(group: list) -> list[str]:
    merged: list[str] = []
    for g in group:
        for kw in _parse_keywords(g.search_keywords):
            if kw and kw not in merged:
                merged.append(kw)
    return merged


def _apply_merge(conn: object, keep_id: int, best: object, merged_keywords: list[str]) -> None:
    """Atualiza o registro mantido com os campos de IA do melhor registro e os keywords mesclados."""
    conn.execute(
        sa.text("""
            UPDATE jobs SET
                search_keywords  = :kw,
                status           = :status,
                filter_reason    = :filter_reason,
                ai_score         = :ai_score,
                ai_summary       = :ai_summary,
                ai_analysis_at   = :ai_analysis_at
            WHERE id = :id
        """),
        {
            "kw": json.dumps(merged_keywords),
            "status": best.status,
            "filter_reason": best.filter_reason,
            "ai_score": best.ai_score,
            "ai_summary": best.ai_summary,
            "ai_analysis_at": best.ai_analysis_at,
            "id": keep_id,
        },
    )


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Adiciona search_keywords como nullable (SQLite não permite NOT NULL sem default em ALTER)
    op.add_column("jobs", sa.Column("search_keywords", sa.JSON(), nullable=True))

    # 2. Popula search_keywords a partir do search_keyword existente
    rows = conn.execute(sa.text("SELECT id, search_keyword FROM jobs")).fetchall()
    for row in rows:
        keywords = [row.search_keyword] if row.search_keyword else []
        conn.execute(
            sa.text("UPDATE jobs SET search_keywords = :kw WHERE id = :id"),
            {"kw": json.dumps(keywords), "id": row.id},
        )

    # 3. Deduplica por (source, external_id)
    dup_groups = conn.execute(
        sa.text("""
            SELECT source, external_id
            FROM jobs
            WHERE external_id IS NOT NULL
            GROUP BY source, external_id
            HAVING COUNT(*) > 1
        """)
    ).fetchall()

    for dup in dup_groups:
        group = conn.execute(
            sa.text("""
                SELECT id, search_keywords, status, filter_reason,
                       ai_score, ai_summary, ai_analysis_at
                FROM jobs
                WHERE source = :source AND external_id = :eid
                ORDER BY first_seen_at ASC, id ASC
            """),
            {"source": dup.source, "eid": dup.external_id},
        ).fetchall()

        keep_id = group[0].id
        best = _best_record(group)
        merged_keywords = _merge_keywords(group)

        _apply_merge(conn, keep_id, best, merged_keywords)
        for g in group[1:]:
            conn.execute(sa.text("DELETE FROM jobs WHERE id = :id"), {"id": g.id})

    # 4. Deduplica por (source, url) onde external_id IS NULL
    dup_url_groups = conn.execute(
        sa.text("""
            SELECT source, url
            FROM jobs
            WHERE external_id IS NULL
            GROUP BY source, url
            HAVING COUNT(*) > 1
        """)
    ).fetchall()

    for dup in dup_url_groups:
        group = conn.execute(
            sa.text("""
                SELECT id, search_keywords, status, filter_reason,
                       ai_score, ai_summary, ai_analysis_at
                FROM jobs
                WHERE source = :source AND url = :url AND external_id IS NULL
                ORDER BY first_seen_at ASC, id ASC
            """),
            {"source": dup.source, "url": dup.url},
        ).fetchall()

        keep_id = group[0].id
        best = _best_record(group)
        merged_keywords = _merge_keywords(group)

        _apply_merge(conn, keep_id, best, merged_keywords)
        for g in group[1:]:
            conn.execute(sa.text("DELETE FROM jobs WHERE id = :id"), {"id": g.id})

    # 5. Remove constraints antigas (que incluíam search_keyword)
    op.drop_constraint("uq_jobs_source_external_id_keyword", "jobs", type_="unique")
    op.drop_constraint("uq_jobs_source_url_keyword", "jobs", type_="unique")

    # 6. Cria novas constraints sem search_keyword
    op.create_unique_constraint("uq_jobs_source_external_id", "jobs", ["source", "external_id"])
    op.create_unique_constraint("uq_jobs_source_url", "jobs", ["source", "url"])

    # 7. Atualiza índice
    op.drop_index("ix_jobs_source_keyword_created_at", table_name="jobs")
    op.create_index("ix_jobs_source_created_at", "jobs", ["source", "created_at"], unique=False)

    # 8. Remove coluna antiga
    op.drop_column("jobs", "search_keyword")


def downgrade() -> None:
    op.add_column("jobs", sa.Column("search_keyword", sa.String(length=255), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, search_keywords FROM jobs")).fetchall()
    for row in rows:
        keywords = json.loads(row.search_keywords or "[]")
        keyword = keywords[0] if keywords else None
        conn.execute(
            sa.text("UPDATE jobs SET search_keyword = :kw WHERE id = :id"),
            {"kw": keyword, "id": row.id},
        )

    op.drop_index("ix_jobs_source_created_at", table_name="jobs")
    op.create_index(
        "ix_jobs_source_keyword_created_at",
        "jobs",
        ["source", "search_keyword", "created_at"],
        unique=False,
    )
    op.drop_constraint("uq_jobs_source_external_id", "jobs", type_="unique")
    op.drop_constraint("uq_jobs_source_url", "jobs", type_="unique")
    op.create_unique_constraint(
        "uq_jobs_source_external_id_keyword", "jobs", ["source", "external_id", "search_keyword"]
    )
    op.create_unique_constraint(
        "uq_jobs_source_url_keyword", "jobs", ["source", "url", "search_keyword"]
    )
    op.drop_column("jobs", "search_keywords")
