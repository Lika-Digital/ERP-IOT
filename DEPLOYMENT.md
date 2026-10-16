# Deployment

The ERP is installed on the VPS by the runbook in `docs/erp_spec.md` §8.4 and the
step-by-step plan in §10.15, with the scripts and units in `deploy/` (see
`deploy/README.md`): systemd, no Docker (§8); PostgreSQL on its Unix socket with peer
auth and no password, database `erp_iot` (§8.3); secrets generated on the machine and
handed over as systemd credentials; the frontend is the `dist` the CI gate built.

The previous text of this file (Docker, a database password over TCP, a default admin
password) described what the spec has since replaced; it is in git history.
