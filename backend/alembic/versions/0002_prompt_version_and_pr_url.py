"""Add diagnoses.prompt_version and proposed_fixes.pr_url (Phase 3).

Guarded so it is a no-op on databases where 0001 just created the tables with these columns.

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if not _has_column("diagnoses", "prompt_version"):
        op.add_column("diagnoses", sa.Column("prompt_version", sa.String(40),
                                             nullable=False, server_default=""))
    if not _has_column("proposed_fixes", "pr_url"):
        op.add_column("proposed_fixes", sa.Column("pr_url", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("proposed_fixes", "pr_url")
    op.drop_column("diagnoses", "prompt_version")
