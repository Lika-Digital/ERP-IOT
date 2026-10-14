"""Security agent — reads, never acts (D21, spec §13.1).

A separate process (`python -m app.agent`, systemd unit deploy/erp-agent.service)
with its own database role `erp_agent`: SELECT on the sources in sources.py,
INSERT on security_alarms, nothing else. The unit has no network. So even a
fully compromised agent — or a prompt injection hidden in a log line — cannot
write anything but an alarm, nor open a single connection: the database and the
kernel refuse it, not a rule in this code.

What this package may import is fixed by TC-ERP-AGT-03 (tests/test_d21.py):
the standard library minus every network and process module, SQLAlchemy, and
itself. Never app.config or app.database — they belong to the backend's role.

Content of logs, webhooks and cabinet answers is DATA, never instruction: it
is quoted into `evidence` and nothing else ever reads it as text to act on.
"""
