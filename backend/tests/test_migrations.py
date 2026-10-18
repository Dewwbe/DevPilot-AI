import pytest
import sqlalchemy as sa
from alembic.config import Config

from alembic import command


@pytest.fixture(autouse=True)
def _reset_settings():
    yield  # runs after monkeypatch restored the env, so later tests get the normal settings
    from app.core import config

    config.get_settings.cache_clear()


def _config(tmp_path, monkeypatch):
    from pathlib import Path

    url = f"sqlite:///{tmp_path / 'mig.db'}"
    monkeypatch.setenv("DEVPILOT_DATABASE_URL", url)
    from app.core import config

    config.get_settings.cache_clear()
    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    return cfg, url


def _cols(url, table):
    return {c["name"] for c in sa.inspect(sa.create_engine(url)).get_columns(table)}


def test_fresh_database_reaches_head_with_all_tables(tmp_path, monkeypatch):
    cfg, url = _config(tmp_path, monkeypatch)
    command.upgrade(cfg, "head")
    tables = set(sa.inspect(sa.create_engine(url)).get_table_names())
    assert {"repositories", "diagnoses", "proposed_fixes", "check_runs", "audit_events",
            "alembic_version"} <= tables
    assert {"prompt_version"} <= _cols(url, "diagnoses")
    assert {"pr_url"} <= _cols(url, "proposed_fixes")


def test_pre_alembic_database_is_upgraded_in_place(tmp_path, monkeypatch):
    """A DB made by the old create_all (no new columns, no alembic_version) must migrate cleanly."""
    cfg, url = _config(tmp_path, monkeypatch)
    command.upgrade(cfg, "head")
    engine = sa.create_engine(url)
    with engine.begin() as conn:  # simulate the Phase 2 schema
        conn.execute(sa.text("ALTER TABLE diagnoses DROP COLUMN prompt_version"))
        conn.execute(sa.text("ALTER TABLE proposed_fixes DROP COLUMN pr_url"))
        conn.execute(sa.text("DROP TABLE alembic_version"))
    assert "prompt_version" not in _cols(url, "diagnoses")

    command.upgrade(cfg, "head")
    assert "prompt_version" in _cols(url, "diagnoses")
    assert "pr_url" in _cols(url, "proposed_fixes")


def test_upgrade_is_idempotent(tmp_path, monkeypatch):
    cfg, _ = _config(tmp_path, monkeypatch)
    command.upgrade(cfg, "head")
    command.upgrade(cfg, "head")  # second run must be a no-op


def test_0003_upgrades_a_phase3_schema_making_pipeline_run_nullable(tmp_path, monkeypatch):
    """Phase 3 databases have diagnoses.pipeline_run_id NOT NULL and none of the history columns."""
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    cfg, url = _config(tmp_path, monkeypatch)
    command.upgrade(cfg, "head")
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        op = Operations(MigrationContext.configure(conn))
        with op.batch_alter_table("diagnoses") as batch:
            batch.alter_column("pipeline_run_id", existing_type=sa.String(36), nullable=False)
            for col in ("source", "created_by", "log_excerpt"):
                batch.drop_column(col)
    command.stamp(cfg, "0002")

    cols = {c["name"]: c for c in sa.inspect(engine).get_columns("diagnoses")}
    assert not cols["pipeline_run_id"]["nullable"] and "source" not in cols

    command.upgrade(cfg, "head")
    cols = {c["name"]: c for c in sa.inspect(sa.create_engine(url)).get_columns("diagnoses")}
    assert cols["pipeline_run_id"]["nullable"]
    assert {"source", "created_by", "log_excerpt"} <= set(cols)
