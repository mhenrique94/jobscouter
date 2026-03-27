"""add search keyword to jobs

Revision ID: 0003_add_search_keyword
Revises: 8a5103463f7b
Create Date: 2026-03-27 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_add_search_keyword"
down_revision = "8a5103463f7b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("search_keyword", sa.String(length=255), nullable=True))

    op.drop_constraint("uq_jobs_source_external_id", "jobs", type_="unique")
    op.drop_constraint("uq_jobs_source_url", "jobs", type_="unique")
    op.create_unique_constraint(
        "uq_jobs_source_external_id_keyword",
        "jobs",
        ["source", "external_id", "search_keyword"],
    )
    op.create_unique_constraint(
        "uq_jobs_source_url_keyword",
        "jobs",
        ["source", "url", "search_keyword"],
    )

    op.drop_index("ix_jobs_source_created_at", table_name="jobs")
    op.create_index(
        "ix_jobs_source_keyword_created_at",
        "jobs",
        ["source", "search_keyword", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_source_keyword_created_at", table_name="jobs")
    op.create_index("ix_jobs_source_created_at", "jobs", ["source", "created_at"], unique=False)

    op.drop_constraint("uq_jobs_source_url_keyword", "jobs", type_="unique")
    op.drop_constraint("uq_jobs_source_external_id_keyword", "jobs", type_="unique")
    op.create_unique_constraint("uq_jobs_source_url", "jobs", ["source", "url"])
    op.create_unique_constraint("uq_jobs_source_external_id", "jobs", ["source", "external_id"])

    op.drop_column("jobs", "search_keyword")
