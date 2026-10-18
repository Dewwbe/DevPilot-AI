"""Diagnosis history: allow pasted-log diagnoses (no pipeline run) and record their origin.

- diagnoses.pipeline_run_id becomes nullable
- diagnoses.source, diagnoses.created_by, diagnoses.log_excerpt are added

Guarded so it is a no-op where 0001 just created the tables from the current models.

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def _columns() -> dict:
    return {c["name"]: c for c in sa.inspect(op.get_bind()).get_columns("diagnoses")}


def upgrade() -> None:
    cols = _columns()
    if "source" not in cols:
        op.add_column("diagnoses", sa.Column("source", sa.String(20), nullable=False,
                                             server_default="run"))
    if "created_by" not in cols:
        op.add_column("diagnoses", sa.Column("created_by", sa.String(255), nullable=True))
    if "log_excerpt" not in cols:
        op.add_column("diagnoses", sa.Column("log_excerpt", sa.Text(), nullable=False,
                                             server_default=""))
    if not cols["pipeline_run_id"]["nullable"]:
        with op.batch_alter_table("diagnoses") as batch:  # batch mode also works on SQLite
            batch.alter_column("pipeline_run_id", existing_type=sa.String(36), nullable=True)


def downgrade() -> None:
    pass  # not reversible without deleting pasted diagnoses; restore from a backup instead
