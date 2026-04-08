# ERP-IOT Phase 1 — Implementation Status

All 57 backend tests pass. Phase 1 is COMPLETE.

---

## 2026-04-05T00:00:00 implementation_status.md
- **Section**: Bootstrap
- **Status**: COMPLETE
- **What was implemented**: Created the implementation status tracking file.
- **Next file**: Directory structure
- **Decisions**: Using ISO 8601 timestamps.

## 2026-04-05T00:01:00 Directory structure
- **Section**: Bootstrap
- **Status**: COMPLETE
- **What was implemented**: Created all project directories including backend, frontend, tests, scripts subtrees.
- **Next file**: backend/requirements.txt
- **Decisions**: Followed spec exactly.

## 2026-04-05T00:02:00 backend/requirements.txt
- **Section**: Backend infrastructure
- **Status**: COMPLETE
- **What was implemented**: All Python dependencies: fastapi, sqlalchemy, pydantic, jose, passlib, httpx, alembic, psycopg2, bcrypt==4.0.1 (version pinned for passlib compat).
- **Next file**: backend/.env.example
- **Decisions**: Used unpinned versions except bcrypt which needs 4.0.1 for passlib compatibility.

## 2026-04-05T00:03:00 backend/.env.example
- **Section**: Backend infrastructure
- **Status**: COMPLETE
- **What was implemented**: Environment variable template with database URL, JWT secret, admin seed credentials, pedestal API settings.
- **Next file**: backend/app/config.py
- **Decisions**: Included all env vars the settings class needs.

## 2026-04-05T00:04:00 backend/app/config.py
- **Section**: Backend infrastructure
- **Status**: COMPLETE
- **What was implemented**: Pydantic BaseSettings config for PostgreSQL DSN, JWT, CORS, admin seed. Auto-generates random JWT secret with warning if not set.
- **Next file**: backend/app/database.py
- **Decisions**: Copied Pedestal SW pattern, adapted for PostgreSQL.

## 2026-04-05T00:05:00 backend/app/database.py
- **Section**: Backend infrastructure
- **Status**: COMPLETE
- **What was implemented**: SQLAlchemy engine (PostgreSQL + SQLite fallback for tests), SessionLocal, Base, get_db dependency, init_db with seeding.
- **Next file**: backend/app/models/marina.py
- **Decisions**: SQLite connect_args applied only when DATABASE_URL starts with sqlite.

## 2026-04-05T00:06:00 backend/app/models/marina.py
- **Section**: Data models
- **Status**: COMPLETE
- **What was implemented**: Marina model with all fields from spec: id, name, location, timezone, logo_url, pedestal_api_base_url, pedestal_api_key, webhook_secret, status, timestamps.
- **Next file**: backend/app/models/user.py
- **Decisions**: All spec fields included.

## 2026-04-05T00:07:00 backend/app/models/user.py
- **Section**: Data models
- **Status**: COMPLETE
- **What was implemented**: User model (id, email, password_hash, full_name, role, is_active, timestamps), UserMarinaAccess junction table with explicit foreign_keys to resolve ambiguity.
- **Next file**: backend/app/models/cache.py
- **Decisions**: Required explicit foreign_keys= on relationship to resolve SQLAlchemy AmbiguousForeignKeysError (two FK paths between users and user_marina_access).

## 2026-04-05T00:08:00 backend/app/models/cache.py
- **Section**: Data models
- **Status**: COMPLETE
- **What was implemented**: PedestalCache, AlarmLog, SessionLog, SyncLog, AuditLog models with JSON columns for flexible payload storage.
- **Next file**: backend/app/schemas/
- **Decisions**: Used JSON type for alarm_data, session_data, last_seen_data to store raw Pedestal SW payloads.

## 2026-04-05T00:09:00 backend/app/schemas/auth.py, marina.py, user.py
- **Section**: Pydantic schemas
- **Status**: COMPLETE
- **What was implemented**: Request/response schemas for auth (login, token, me), marina (create, update, response), user (create, update, response).
- **Next file**: backend/alembic/
- **Decisions**: MarinaResponse excludes API key for security.

## 2026-04-05T00:10:00 backend/alembic/ setup + 001_initial_schema.py
- **Section**: Database migrations
- **Status**: COMPLETE
- **What was implemented**: alembic.ini, env.py (reads DATABASE_URL from env), migration 001 creating all 8 tables with indexes.
- **Next file**: backend/app/middleware/security.py
- **Decisions**: Migration creates all Phase 1 tables in one revision.

## 2026-04-05T00:11:00 backend/app/middleware/security.py
- **Section**: Security
- **Status**: COMPLETE
- **What was implemented**: Observe-only security middleware scanning for SQL injection/XSS patterns, malformed JWTs, 403 responses. Adds security response headers.
- **Next file**: backend/app/services/websocket_manager.py
- **Decisions**: Adapted from Pedestal SW, replaced error_log_service dependency with stdlib logging.

## 2026-04-05T00:12:00 backend/app/services/websocket_manager.py
- **Section**: Services
- **Status**: COMPLETE
- **What was implemented**: WebSocketManager with connect, disconnect, broadcast (all clients), broadcast_to_marina (marina-scoped), connection_count. Global ws_manager singleton.
- **Next file**: backend/app/services/audit_log.py
- **Decisions**: Added broadcast_to_marina for marina-scoped webhook events.

## 2026-04-05T00:13:00 backend/app/services/audit_log.py
- **Section**: Services
- **Status**: COMPLETE
- **What was implemented**: record_action() writes to AuditLog table with user_id, marina_id, pedestal_id, action, target_id, details, performed_at. get_audit_log() for queries.
- **Next file**: backend/app/services/pedestal_api.py
- **Decisions**: Simple synchronous service using caller's DB session.

## 2026-04-05T00:14:00 backend/app/services/pedestal_api.py
- **Section**: Services
- **Status**: COMPLETE
- **What was implemented**: Full PedestalAPIService with all 14 methods, X-API-Key header, 3-retry exponential backoff, sync_log writes, pedestal_cache fallback, (data, is_stale) return type.
- **Next file**: backend/app/routers/auth.py
- **Decisions**: Cache keyed by hash(sync_type) for endpoint-level caching. Control methods (allow/deny/stop) skip cache.

## 2026-04-05T00:15:00 backend/app/routers/auth.py
- **Section**: Routers
- **Status**: COMPLETE
- **What was implemented**: POST /login, GET /me, POST /refresh. JWT with user_id, role, marina_ids. require_any_operator and require_super_admin dependencies. require_marina_access() enforcer.
- **Next file**: backend/app/routers/marinas.py
- **Decisions**: Marina IDs empty list for super_admin (signals all-access).

## 2026-04-05T00:16:00 backend/app/routers/marinas.py
- **Section**: Routers
- **Status**: COMPLETE
- **What was implemented**: Full CRUD for marinas (super_admin only for write), list filtered by access, access grant/revoke endpoints.
- **Next file**: backend/app/routers/dashboard.py
- **Decisions**: Marina list filtered server-side based on UserMarinaAccess rows.

## 2026-04-05T00:17:00 backend/app/routers/dashboard.py
- **Section**: Routers
- **Status**: COMPLETE
- **What was implemented**: GET /dashboard (aggregated pedestals + health + sessions), GET /health, GET /pedestals, GET /berths — all proxied from Pedestal SW with stale-data flag.
- **Next file**: backend/app/routers/controls.py
- **Decisions**: Dashboard aggregates 4 parallel calls and returns combined is_stale.

## 2026-04-05T00:18:00 backend/app/routers/controls.py
- **Section**: Routers
- **Status**: COMPLETE
- **What was implemented**: allow/deny/stop session endpoints, run_diagnostics. All write to audit_log with user_id, marina_id, pedestal_id, action, timestamp.
- **Next file**: backend/app/routers/energy.py
- **Decisions**: All actions gated by require_marina_access before forwarding to Pedestal SW.

## 2026-04-05T00:19:00 backend/app/routers/energy.py
- **Section**: Routers
- **Status**: COMPLETE
- **What was implemented**: daily analytics, session summary, active/pending sessions — all proxied from Pedestal SW with caching.
- **Next file**: backend/app/routers/alarms.py
- **Decisions**: Date range params forwarded directly to Pedestal SW.

## 2026-04-05T00:20:00 backend/app/routers/alarms.py
- **Section**: Routers
- **Status**: COMPLETE
- **What was implemented**: GET active alarms (from Pedestal SW), GET alarm log (local), POST acknowledge (forwards to Pedestal SW + updates local log + audit_log).
- **Next file**: backend/app/routers/webhooks.py
- **Decisions**: Local alarm_log checked by alarm_data JSON field when acknowledging.

## 2026-04-05T00:21:00 backend/app/routers/webhooks.py
- **Section**: Routers
- **Status**: COMPLETE
- **What was implemented**: POST /api/webhooks/pedestal/{marina_id} with HMAC-SHA256 validation, alarm/session log writes, pedestal_cache update, WebSocket broadcast.
- **Next file**: backend/app/main.py
- **Decisions**: HMAC uses compare_digest to prevent timing attacks. Marina with no webhook_secret skips validation.

## 2026-04-05T00:22:00 backend/app/main.py
- **Section**: Backend entry point
- **Status**: COMPLETE
- **What was implemented**: FastAPI app with lifespan (init_db), CORS, SecurityMiddleware, all routers, health endpoint, WebSocket endpoint with optional JWT auth and marina_id filtering.
- **Next file**: backend/tests/conftest.py
- **Decisions**: WebSocket accepts marina_id query param for scoped subscriptions.

## 2026-04-05T00:23:00 backend/tests/conftest.py
- **Section**: Tests
- **Status**: COMPLETE
- **What was implemented**: SQLite test DB, session fixtures, seeded super_admin + marina_manager + inactive user, 2 marinas (1 restricted), access grant. Token fixtures for both roles.
- **Next file**: backend/tests/test_auth.py
- **Decisions**: Uses file-based SQLite for cross-module fixture sharing. Windows-safe teardown with retry loop.

## 2026-04-05T00:24:00 backend/tests/test_auth.py through test_energy.py (7 test files)
- **Section**: Tests
- **Status**: COMPLETE — 57 tests, all passing
- **What was implemented**: Full test coverage for auth, marinas, pedestal API, webhooks, alarms, controls, energy as specified.
- **Next file**: frontend/package.json
- **Decisions**: JWT decode uses base64 instead of jose.decode() to avoid python-jose API differences.

## 2026-04-05T00:30:00 frontend/ (all files)
- **Section**: Frontend
- **Status**: COMPLETE
- **What was implemented**: React 18 + Vite + TypeScript + TailwindCSS + Zustand + Recharts. Pages: Login, MarinaSelect, Dashboard, PedestalControl, Energy, Alarms. All API modules, useWebSocket hook, StaleDataBanner, ConfirmDialog, ProtectedRoute.
- **Next file**: docker-compose.yml
- **Decisions**: Zustand authStore includes marinaIds and role for super_admin/marina_manager. StaleDataBanner shown when any response has is_stale=true.

## 2026-04-05T00:35:00 docker-compose.yml + nginx.conf
- **Section**: Infrastructure
- **Status**: COMPLETE
- **What was implemented**: Docker Compose with postgres (with healthcheck), backend, frontend, nginx (production profile). nginx.conf with WS proxy and security headers.
- **Next file**: scripts/verify_system.sh
- **Decisions**: nginx in production profile only to avoid conflicts in dev.

## 2026-04-05T00:36:00 scripts/verify_system.sh
- **Section**: Operations
- **Status**: COMPLETE
- **What was implemented**: 10-point verification script: PostgreSQL, backend health, frontend dist, Cloudflare tunnel, WebSocket, marina API connectivity, webhook 401, Python imports, DB tables, JWT auth. --quick flag skips checks 4-6.
- **Next file**: tests/run_tests.sh
- **Decisions**: Color-coded output matching Pedestal SW pattern.

## 2026-04-05T00:37:00 tests/run_tests.sh
- **Section**: CI/CD
- **Status**: COMPLETE
- **What was implemented**: 3-stage test runner: pytest, bandit security scan, gap checks (app import + package.json). Activates venv if present.
- **Next file**: README.md + DEPLOYMENT.md
- **Decisions**: Adapted from Pedestal SW 4-stage runner, simplified for Phase 1.

## 2026-04-05T00:38:00 README.md + DEPLOYMENT.md + .gitignore
- **Section**: Documentation
- **Status**: COMPLETE
- **What was implemented**: README with architecture diagram, quick start, API reference, stale data flow. DEPLOYMENT.md with full production checklist, systemd service, webhook integration guide, backup procedures.
- **Next file**: .git/hooks/
- **Decisions**: Comprehensive production-ready documentation.

## 2026-04-05T00:39:00 .git/hooks/pre-commit + pre-push
- **Section**: Git workflow
- **Status**: COMPLETE
- **What was implemented**: pre-commit runs full test suite. pre-push has branch-aware gate: dev = run tests, main = tests + CLOUD_IOT_RELEASE=1 or interactive "release" confirmation.
- **Next file**: Initial commit + push to GitHub
- **Decisions**: Adapted directly from Pedestal SW hooks. Uses CLOUD_IOT_RELEASE env var for non-interactive release (CI/Claude Code compatible).

---

## 2026-04-07T00:00:00 Authentication Overhaul — Pre-read audit
Status: COMPLETE
What: Read all files in both projects. Identified: OTP-based login in cloud_iot needs a direct service-token endpoint; gateway only accepts external_api role; marina model has pedestal_api_key; 4 routers use PedestalAPIService directly.
Next: cloud_iot/scripts/create_erp_service_account.py
Decisions: Added POST /api/auth/service-token endpoint (skips OTP) for api_client role. Gateway updated to accept both external_api and api_client roles. api_client JWTs skip the stored-key hmac check.

## 2026-04-07T00:01:00 Step 1a — cloud_iot role migration
Status: COMPLETE
What: Added api_client role comment marker to _migrate_user_schema() in user_database.py. No DDL needed — SQLite TEXT column accepts any value.
Next: cloud_iot/scripts/create_erp_service_account.py
Decisions: SQLite has no enum constraints; role is stored as a plain string.

## 2026-04-07T00:02:00 Step 1b — cloud_iot/scripts/create_erp_service_account.py
Status: COMPLETE
What: Created idempotent CLI script using PBKDF2-HMAC-SHA256 (same as auth system), creates api_client user, exits cleanly if already exists.
Next: cloud_iot auth.py service-token endpoint
Decisions: Uses sys.path manipulation to import backend app modules.

## 2026-04-07T00:03:00 Step 1b — cloud_iot auth.py: POST /api/auth/service-token
Status: COMPLETE
What: Added new endpoint before /login that validates credentials and returns JWT directly for api_client role accounts, skipping OTP.
Next: cloud_iot external_api_gateway.py
Decisions: Only api_client role is accepted — human operator accounts are rejected with 403.

## 2026-04-07T00:04:00 Step 1c — cloud_iot external_api_gateway.py: accept api_client role
Status: COMPLETE
What: Updated _decode_external_jwt() to accept both external_api and api_client roles. Updated gateway to skip stored-key hmac check for api_client tokens (they are user JWTs, not static keys).
Next: alembic migration 002
Decisions: api_client tokens validated by JWT signature only; external_api tokens still validated against stored key for backwards compatibility.

## 2026-04-07T00:05:00 Step 2 — alembic/versions/002_marina_service_account.py
Status: COMPLETE
What: Migration adds pedestal_service_email and pedestal_service_password_encrypted (both nullable), drops pedestal_api_key. Fully reversible.
Next: app/utils/encryption.py
Decisions: Columns nullable for migration safety; code enforces non-null via ValueError.

## 2026-04-07T00:06:00 Step 3 — app/utils/encryption.py + config.py + requirements.txt
Status: COMPLETE
What: Created Fernet-based encrypt_password/decrypt_password. Added erp_encryption_key to Settings with warning on missing. Added cryptography to requirements.txt.
Next: app/services/pedestal_api.py replacement
Decisions: Module-level Fernet instance for efficiency; raises RuntimeError on missing key.

## 2026-04-07T00:07:00 Step 4 — app/services/pedestal_api.py complete replacement
Status: COMPLETE
What: Replaced PedestalAPIService with PedestalAPIClient implementing JWT auth flow: POST /api/auth/service-token, 7-hour token cache, Bearer header on all requests, /api/ext/ path prefix, 3-retry backoff, cache fallback, sync_log. PedestalAPIService kept as alias for backwards compat. Added PedestalAuthError and StaleResponse types.
Next: app/services/pedestal_api_factory.py
Decisions: Token cached for 7h (JWT valid 8h); 401 response clears token cache for immediate re-auth.

## 2026-04-07T00:08:00 Step 5 — app/services/pedestal_api_factory.py
Status: COMPLETE
What: Singleton PedestalAPIClientFactory that loads marina from DB, decrypts password, creates/caches PedestalAPIClient per marina_id. FastAPI dependency get_pedestal_factory(). Cache invalidated when credentials change.
Next: routers update
Decisions: Client cache keyed by (base_url + email) to detect credential changes.

## 2026-04-07T00:09:00 Step 6 — Update all 4 routers to use factory
Status: COMPLETE
What: Updated dashboard.py, alarms.py, controls.py, energy.py to inject PedestalAPIClientFactory via Depends and call factory.get_client(marina_id, db) instead of instantiating PedestalAPIService directly.
Next: marina model update
Decisions: Factory injected as FastAPI Depends for testability.

## 2026-04-07T00:10:00 Step 7 — Marina model + Pydantic schemas
Status: COMPLETE
What: Replaced pedestal_api_key with pedestal_service_email + pedestal_service_password_encrypted in Marina SQLAlchemy model. Updated MarinaCreate/MarinaUpdate/MarinaResponse schemas — plaintext password in create/update, encrypted blob never returned.
Next: marinas router (encrypt on save + test-connection endpoint)
Decisions: MarinaResponse includes pedestal_service_email but never the encrypted password.

## 2026-04-07T00:11:00 Step 9 — marinas.py: encrypt on save + test-connection endpoint
Status: COMPLETE
What: Updated create_marina and update_marina to encrypt pedestal_service_password before storing. Added POST /{marina_id}/test-connection that attempts login to Pedestal SW and returns {success, detail}. Factory cache invalidated on credential update.
Next: frontend
Decisions: test-connection requires super_admin role.

## 2026-04-07T00:12:00 Step 8 — Frontend: marina form + API types
Status: COMPLETE
What: Updated marinas.ts types (MarinaCreate/MarinaUpdate) to use pedestal_service_email + pedestal_service_password instead of pedestal_api_key. Added testConnection() API call. Updated MarinaSelect.tsx: replaced API Key field with Service Account Email + Password fields, added Test Connection button per marina card with inline green/red result banner.
Next: .env + .env.example
Decisions: Password field never shows stored value. Test Connection button only shown to super_admin.

## 2026-04-07T00:13:00 Step 10 — .env + .env.example
Status: COMPLETE
What: Added ERP_ENCRYPTION_KEY to .env (generated Fernet key) and .env.example (with generation instructions and security warning).
Next: tests
Decisions: Key sfkoAdxNaMndE1YTx-5qFVZT63baOe1ZLrWHoe23nHk= added to .env.

## 2026-04-07T00:14:00 Step 11 — Tests
Status: COMPLETE
What: Created tests/test_pedestal_client.py with 18 tests covering encryption inverse, no plaintext storage, token caching, expiry re-auth, PedestalAuthError on 401/network, Bearer header, /api/ext/ prefix, 3x retry, stale fallback, StaleResponse defaults, factory singleton, factory credential-change detection. Updated test_pedestal_api.py and test_marinas.py for new interfaces. Updated conftest.py with ERP_ENCRYPTION_KEY and new marina seed fields.
Next: DONE
Decisions: asyncio.sleep patched in retry tests to avoid delays.

---

## Final Summary

**Phase 1 COMPLETE** — 2026-04-05

### Files Created: 70+
### Tests: 57 passing, 0 failing

### Key Architecture Decisions
1. **Synchronous SQLAlchemy** — matches Pedestal SW pattern, simpler than async for Phase 1
2. **SQLite for tests** — fast, no PostgreSQL needed in CI
3. **(data, is_stale) tuple** — clean contract for stale data signaling from PedestalAPIService
4. **HMAC signature validation** — SHA256 with compare_digest to prevent timing attacks
5. **Empty marina_ids = all marinas** — super_admin JWT has [] which the frontend checks as "super admin"
6. **AuditLog on every control action** — user_id + marina_id + pedestal_id + timestamp on every allow/deny/stop
