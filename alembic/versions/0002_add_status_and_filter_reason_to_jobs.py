"""add status and filter reason to jobs

Revision ID: 0002_add_job_status_filter
Revises: 0001_create_jobs_table
Create Date: 2026-03-26 00:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_add_job_status_filter"
down_revision = "0001_create_jobs_table"
branch_labels = None
depends_on = None


job_status = sa.Enum("pending", "ready_for_ai", "discarded", "analyzed", name="job_status")


def upgrade() -> None:
    bind = op.get_bind()
    job_status.create(bind, checkfirst=True)

    op.add_column(
        "jobs",
        sa.Column(
            "status",
            job_status,
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column("jobs", sa.Column("filter_reason", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "filter_reason")
    op.drop_column("jobs", "status")

    bind = op.get_bind()
    job_status.drop(bind, checkfirst=True)
