"""Baseline: create any missing tables.

Databases created before Alembic existed were built with `create_all`, so this baseline is
idempotent (`checkfirst`): it creates only the tables that are missing and leaves existing ones.
Later migrations must be explicit, guarded changes (see 0002) and must not rely on the models.

Revision ID: 0001
Revises:
"""
from alembic import op
from app.core.db import Base
from app.models import entities  # noqa: F401

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    pass  # the baseline is never rolled back
