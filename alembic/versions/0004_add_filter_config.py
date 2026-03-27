"""add filter config table

Revision ID: 0004_add_filter_config
Revises: 0003_add_search_keyword
Create Date: 2026-03-27 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004_add_filter_config"
down_revision = "0003_add_search_keyword"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "filter_config",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("search_terms", sa.JSON(), nullable=False),
        sa.Column("include_keywords", sa.JSON(), nullable=False),
        sa.Column("exclude_keywords", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("filter_config")
