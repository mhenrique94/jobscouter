"""create jobs table

Revision ID: 0001_create_jobs_table
Revises:
Create Date: 2026-03-26 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_create_jobs_table"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("company", sa.String(length=255), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("description_raw", sa.Text(), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("salary", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "external_id", name="uq_jobs_source_external_id"),
        sa.UniqueConstraint("source", "url", name="uq_jobs_source_url"),
    )
    op.create_index("ix_jobs_company", "jobs", ["company"], unique=False)
    op.create_index("ix_jobs_external_id", "jobs", ["external_id"], unique=False)
    op.create_index("ix_jobs_source", "jobs", ["source"], unique=False)
    op.create_index("ix_jobs_title", "jobs", ["title"], unique=False)
    op.create_index("ix_jobs_source_created_at", "jobs", ["source", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_jobs_source_created_at", table_name="jobs")
    op.drop_index("ix_jobs_title", table_name="jobs")
    op.drop_index("ix_jobs_source", table_name="jobs")
    op.drop_index("ix_jobs_external_id", table_name="jobs")
    op.drop_index("ix_jobs_company", table_name="jobs")
    op.drop_table("jobs")
