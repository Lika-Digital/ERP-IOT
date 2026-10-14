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
                 "smart_mode", "last_heartbeat_at", "last_polled_at", "created_at"),
    "marinas": ("id", "name", "timezone"),
}

# GRANT INSERT ON <table> — the only write
INSERT_TABLES = ("security_alarms",)

# GRANT USAGE ON SEQUENCE — only the one the only write needs
SEQUENCES = ("security_alarms_id_seq",)
