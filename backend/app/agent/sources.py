"""What the database role `erp_agent` may do — the single list (spec §13.1, D21).

Migration 011 grants exactly this; TC-ERP-AGT-01 (scripts/agent_db_check.py)
reads the grants back from PostgreSQL and fails on any difference, in either
direction. A new source is a new migration AND a line here, in the same commit.

Columns, not whole tables, where a table also holds secrets: `cabinets` carries
the encrypted service password and API keys, `marinas` the old per-marina
service account. The agent needs neither.
"""

ROLE = "erp_agent"

# GRANT SELECT ON <table>
SELECT_TABLES = (
    "command_audit",
    "auth_audit",
    "audit_log",
    "sync_log",
    "reconciliation_runs",
    "session_log",
    "alarm_log",
    "pedestal_cache",
    "outlets",
    "berths",
    "service_windows",
    "decoy_hits",
    "security_alarms",
    "admin_imports",
    "security_rule_settings",
)

# GRANT SELECT (<columns>) ON <table>
SELECT_COLUMNS = {
    "cabinets": ("id", "marina_id", "pedestal_pk", "display_id", "device_type", "dock",
                 "smart_mode", "last_heartbeat_at", "last_polled_at", "created_at",
                 # D28 (migration 012): real or simulated, and the cabinet SERVER a
                 # cached snapshot came from (a PK is unique only per server)
                 "is_simulated", "base_url"),
    "marinas": ("id", "name", "timezone"),
}

# GRANT INSERT ON <table> — the only writes: an alarm, and "I ran" (migration 013,
# D23: the dashboard card must know whether the agent runs at all)
INSERT_TABLES = ("security_alarms", "security_agent_passes")

# GRANT USAGE ON SEQUENCE — only the ones those writes need
SEQUENCES = ("security_alarms_id_seq", "security_agent_passes_id_seq")
