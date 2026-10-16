"""P3 (spec §8.4): on PostgreSQL only the migrations change the schema.

The app never runs create_all there; it starts only on a database at the migrations'
head and otherwise refuses with a message that says what to run. SQLite (tests, demo)
keeps create_all.
"""
import pytest
from sqlalchemy import create_engine, text

from app import database
from app.database import SchemaNotAtHead, check_schema_at_head, init_db


def _head():
    from pathlib import Path

    from alembic.config import Config
    from alembic.script import ScriptDirectory
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(database.__file__).resolve().parents[1] / "alembic"))
    return ScriptDirectory.from_config(cfg).get_current_head()


def _engine_at(tmp_path, revision):
    eng = create_engine(f"sqlite:///{(tmp_path / 'p3.db').as_posix()}")
    if revision is not None:
        with eng.begin() as c:
            c.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
            c.execute(text("INSERT INTO alembic_version VALUES (:v)"), {"v": revision})
    return eng


def test_a_database_behind_head_is_refused_with_what_to_run(tmp_path):
    with pytest.raises(SchemaNotAtHead) as e:
        check_schema_at_head(_engine_at(tmp_path, "010"))
    msg = str(e.value)
    assert "revision 010" in msg and f"needs {_head()}" in msg and "alembic upgrade head" in msg


def test_an_empty_database_is_refused(tmp_path):
    with pytest.raises(SchemaNotAtHead, match="none \\(empty database\\)"):
        check_schema_at_head(_engine_at(tmp_path, None))


def test_a_database_at_head_passes(tmp_path):
    check_schema_at_head(_engine_at(tmp_path, _head()))


class _Postgres:
    """Only what init_db looks at: the dialect's name."""
    class dialect:
        name = "postgresql"


def test_on_postgresql_the_start_never_creates_tables(monkeypatch):
    created, checked = [], []
    monkeypatch.setattr(database.Base.metadata, "create_all", lambda **kw: created.append(kw))
    monkeypatch.setattr(database, "check_schema_at_head", lambda bind: checked.append(bind))
    pg = _Postgres()
    init_db(pg)
    assert created == [] and checked == [pg]


def test_on_postgresql_a_database_behind_head_stops_the_start(monkeypatch):
    def behind(bind):
        raise SchemaNotAtHead("Database is at revision 010, the code needs 014 — run `alembic upgrade head`")
    monkeypatch.setattr(database, "check_schema_at_head", behind)
    with pytest.raises(SchemaNotAtHead):
        init_db(_Postgres())


def test_sqlite_keeps_create_all(tmp_path):
    eng = _engine_at(tmp_path, None)
    init_db(eng)
    with eng.connect() as c:
        names = {r[0] for r in c.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
    assert {"marinas", "users", "vessels"} <= names
