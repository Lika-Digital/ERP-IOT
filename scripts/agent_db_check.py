"""TC-ERP-AGT-01 / AGT-02 — the database itself holds the agent to "read, and write only alarms".

PostgreSQL only: SQLite has no roles. Used by scripts/boot_check.py on the
migrated boot database (CI: PostgreSQL 16), and runnable by hand:

    backend/.venv/Scripts/python scripts/agent_db_check.py postgresql://...

AGT-01 reads the grants back from the catalog and compares them, in both
directions, with backend/app/agent/sources.py:
  - table and sequence privileges of erp_agent (pg_class.relacl), and the same
    seen through information_schema.role_table_grants;
  - column privileges (pg_attribute.attacl) — only the listed columns;
  - nothing granted to PUBLIC on any relation, no default privileges
    (pg_default_acl) for erp_agent or PUBLIC;
  - no SECURITY DEFINER function erp_agent may execute;
  - role attributes: no superuser, createrole, createdb, replication,
    bypassrls; member of no other role; no CREATE on the schema or database.

AGT-02 becomes erp_agent (SET ROLE) inside ONE transaction that is rolled back,
each attempt in its own savepoint, and tries every write: INSERT, UPDATE,
DELETE and TRUNCATE on every table of the schema, UPDATE on security_alarms,
CREATE TABLE / SCHEMA, ALTER, COPY ... TO PROGRAM, nextval on a foreign
sequence, and reading secrets. Every one must fail with insufficient_privilege
(42501). One INSERT into security_alarms must succeed. Nothing is left behind.
"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.agent import sources  # noqa: E402

DENIED = "42501"


def _expected_relacl() -> set:
    exp = {(t, "SELECT") for t in sources.SELECT_TABLES}
    exp |= {(t, "INSERT") for t in sources.INSERT_TABLES}
    exp |= {(s, "USAGE") for s in sources.SEQUENCES}
    return exp


def agt01(c) -> list[tuple[str, bool, str]]:
    out = []
    role = sources.ROLE

    def check(name, got, expected):
        missing, extra = expected - got, got - expected
        out.append((name, not missing and not extra,
                    f"missing {sorted(missing)}; extra {sorted(extra)}" if missing or extra
                    else f"{len(got)} exact"))

    got = {(r[0], r[1]) for r in c.execute(text(
        "SELECT c.relname, a.privilege_type FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "CROSS JOIN LATERAL aclexplode(c.relacl) a "
        "WHERE n.nspname NOT IN ('pg_catalog', 'information_schema') "
        "AND a.grantee = (SELECT oid FROM pg_roles WHERE rolname = :r)"), {"r": role})}
    check("AGT-01 relation privileges (pg_class.relacl) = sources.py", got, _expected_relacl())

    got = {(r[0], r[1]) for r in c.execute(text(
        "SELECT table_name, privilege_type FROM information_schema.role_table_grants "
        "WHERE grantee = :r"), {"r": role})}
    exp = {(t, p) for t, p in _expected_relacl() if p != "USAGE"}
    check("AGT-01 information_schema.role_table_grants = sources.py", got, exp)

    got = {(r[0], r[1], r[2]) for r in c.execute(text(
        "SELECT c.relname, at.attname, a.privilege_type FROM pg_attribute at "
        "JOIN pg_class c ON c.oid = at.attrelid JOIN pg_namespace n ON n.oid = c.relnamespace "
        "CROSS JOIN LATERAL aclexplode(at.attacl) a "
        "WHERE n.nspname NOT IN ('pg_catalog', 'information_schema') "
        "AND a.grantee = (SELECT oid FROM pg_roles WHERE rolname = :r)"), {"r": role})}
    exp = {(t, col, "SELECT") for t, cols in sources.SELECT_COLUMNS.items() for col in cols}
    check("AGT-01 column privileges (pg_attribute.attacl) = sources.py", got, exp)

    got = {(r[0], r[1]) for r in c.execute(text(
        "SELECT c.relname, a.privilege_type FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "CROSS JOIN LATERAL aclexplode(c.relacl) a "
        "WHERE n.nspname NOT IN ('pg_catalog', 'information_schema') AND a.grantee = 0"))}
    check("AGT-01 nothing granted to PUBLIC on any relation", got, set())

    got = {(r[0], r[1]) for r in c.execute(text(
        "SELECT d.defaclobjtype::text, a.privilege_type FROM pg_default_acl d "
        "CROSS JOIN LATERAL aclexplode(d.defaclacl) a "
        "WHERE a.grantee = 0 OR a.grantee = (SELECT oid FROM pg_roles WHERE rolname = :r)"),
        {"r": role})}
    check("AGT-01 no default privileges for erp_agent or PUBLIC (pg_default_acl)", got, set())

    got = {r[0] for r in c.execute(text(
        "SELECT p.oid::regprocedure::text FROM pg_proc p "
        "JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE p.prosecdef AND n.nspname NOT IN ('pg_catalog', 'information_schema') "
        "AND has_function_privilege(:r, p.oid, 'EXECUTE')"), {"r": role})}
    check("AGT-01 no SECURITY DEFINER function erp_agent can execute", got, set())

    row = c.execute(text(
        "SELECT rolsuper, rolcreaterole, rolcreatedb, rolreplication, rolbypassrls "
        "FROM pg_roles WHERE rolname = :r"), {"r": role}).first()
    out.append(("AGT-01 role exists, with no superuser/createrole/createdb/replication/bypassrls",
                row is not None and not any(row), f"attributes {tuple(row) if row else None}"))

    got = {r[0] for r in c.execute(text(
        "SELECT g.rolname FROM pg_auth_members m JOIN pg_roles g ON g.oid = m.roleid "
        "WHERE m.member = (SELECT oid FROM pg_roles WHERE rolname = :r)"), {"r": role})}
    check("AGT-01 member of no other role", got, set())

    row = c.execute(text(
        "SELECT has_schema_privilege(:r, 'public', 'CREATE'), "
        "has_database_privilege(:r, current_database(), 'CREATE')"), {"r": role}).first()
    out.append(("AGT-01 no CREATE on schema public or on the database", not any(row),
                f"schema CREATE={row[0]}, database CREATE={row[1]}"))
    return out


def _attempt(c, sql: str, params: dict | None = None) -> str | None:
    """Run one statement in a savepoint; return its SQLSTATE, or None if it worked."""
    sp = c.begin_nested()
    try:
        c.execute(text(sql), params or {})
    except DBAPIError as exc:
        sp.rollback()
        return getattr(exc.orig, "pgcode", None) or "error"
    sp.rollback()
    return None


def agt02(c) -> list[tuple[str, bool, str]]:
    out = []
    role = sources.ROLE
    tables = [r[0] for r in c.execute(text(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"))]
    first_col = {t: c.execute(text(
        "SELECT attname FROM pg_attribute WHERE attrelid = CAST(:t AS regclass) AND attnum > 0 "
        "AND NOT attisdropped ORDER BY attnum LIMIT 1"), {"t": t}).scalar_one() for t in tables}
    foreign_seq = c.execute(text(
        "SELECT sequencename FROM pg_sequences WHERE schemaname = 'public' "
        "AND sequencename <> ALL(:own) ORDER BY 1 LIMIT 1"), {"own": list(sources.SEQUENCES)}
    ).scalar()

    # becoming the role: a superuser may SET ROLE to anyone; a role that created
    # erp_agent (CREATEROLE) grants itself membership — inside this transaction only
    is_super = c.execute(text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
                         ).scalar_one()
    if not is_super:
        c.execute(text(f"GRANT {role} TO CURRENT_USER"))   # rolled back with the rest
    c.execute(text(f"SET LOCAL ROLE {role}"))
    if c.execute(text("SELECT current_user")).scalar_one() != role:
        return [("AGT-02 became erp_agent", False, "SET ROLE did not take")]

    attempts = []
    for t in tables:
        col = first_col[t]
        if t not in sources.INSERT_TABLES:
            attempts.append((f"INSERT {t}", f"INSERT INTO {t} ({col}) SELECT NULL WHERE false"))
        # WHERE false and no column read: the statement needs ONLY the privilege under
        # test, so a stray grant shows up as success, not as a missing SELECT
        attempts.append((f"UPDATE {t}", f"UPDATE {t} SET {col} = NULL WHERE false"))
        attempts.append((f"DELETE {t}", f"DELETE FROM {t} WHERE false"))
        attempts.append((f"TRUNCATE {t}", f"TRUNCATE {t}"))
        attempts.append((f"ALTER {t}", f"ALTER TABLE {t} ADD COLUMN agt02_x integer"))
    attempts += [
        ("UPDATE security_alarms state",
         "UPDATE security_alarms SET state = 'closed' WHERE false"),
        ("CREATE TABLE public", "CREATE TABLE public.agt02_x (i integer)"),
        ("CREATE SCHEMA", "CREATE SCHEMA agt02_x"),
        ("CREATE FUNCTION public",
         "CREATE FUNCTION public.agt02_x() RETURNS integer LANGUAGE sql AS 'SELECT 1'"),
        ("COPY TO PROGRAM", "COPY (SELECT 1) TO PROGRAM 'true'"),
        ("read users (secrets)", "SELECT password_hash, totp_secret_enc FROM users"),
        ("read cabinets.service_pw_enc", "SELECT service_pw_enc FROM cabinets"),
        ("read marinas.pedestal_service_password_encrypted",
         "SELECT pedestal_service_password_encrypted FROM marinas"),
    ]
    if foreign_seq:
        attempts.append((f"nextval {foreign_seq}", f"SELECT nextval('{foreign_seq}')"))

    let_through = []
    for label, sql in attempts:
        code = _attempt(c, sql)
        if code != DENIED:
            let_through.append(f"{label}: {code or 'SUCCEEDED'}")
    out.append((f"AGT-02 {len(attempts)} writes and secret reads as erp_agent -> each 42501",
                not let_through, "; ".join(let_through) or f"{len(attempts)} refused"))

    code = _attempt(c, (
        "INSERT INTO security_alarms (rule_id, fingerprint, severity, title, why, evidence, "
        "created_at, state) VALUES ('agt02', repeat('a', 64), 'info', 't', 'w', "
        "CAST('[]' AS JSONB), now() AT TIME ZONE 'UTC', 'open') "
        "ON CONFLICT (fingerprint) DO NOTHING"))
    out.append(("AGT-02 INSERT ... ON CONFLICT DO NOTHING into security_alarms as erp_agent",
                code is None, f"SQLSTATE {code}" if code else "inserted"))
    code = _attempt(c, "SELECT count(*) FROM security_alarms JOIN cabinets ON true "
                       "JOIN auth_audit ON true LIMIT 1")
    out.append(("AGT-02 reading the sources as erp_agent works", code is None,
                f"SQLSTATE {code}" if code else "read"))
    return out


def run(engine: Engine) -> list[tuple[str, bool, str]]:
    if engine.dialect.name != "postgresql":
        raise RuntimeError("AGT-01/02 need PostgreSQL (SQLite has no roles)")
    with engine.connect() as c:
        trans = c.begin()
        try:
            results = agt01(c) + agt02(c)
        finally:
            trans.rollback()        # SET LOCAL ROLE, the self-grant, every attempt: gone
    return results


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: agent_db_check.py <postgresql URL of a migrated database>")
        return 2
    eng = create_engine(argv[1])
    try:
        results = run(eng)
    finally:
        eng.dispose()
    for name, ok, detail in results:
        print(f"  [{'ok' if ok else 'FAIL'}] {name} - {detail}")
    bad = [r for r in results if not r[1]]
    print(f"AGENT_DB: {len(results) - len(bad)}/{len(results)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
