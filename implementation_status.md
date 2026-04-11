# ERP-IOT — Implementation Status

## Phase 1 (2026-04-05 to 2026-04-07) — COMPLETE
All Phase 1 work documented. 7 routers, 8 models, 3 services, full auth, encryption, Alembic
migrations, 57+ tests. See git log for full detail.

---

## Phase 2 (2026-04-11) — Marina Dashboard Restructure + Pedestal Detail + Camera/Berth Ext API

### Files — Status

| # | File | Status | Notes |
|---|------|--------|-------|
| 1 | `backend/app/services/pedestal_api.py` | COMPLETE | Added 3 new methods |
| 2 | `backend/app/routers/pedestal_ext.py` | COMPLETE | New router — 3 endpoints |
| 3 | `backend/app/main.py` | COMPLETE | Registered pedestal_ext router |
| 4 | `frontend/src/api/pedestalExt.ts` | COMPLETE | New API service — 3 functions |
| 5 | `frontend/src/pages/Dashboard.tsx` | COMPLETE | Restructured: Overview + Berths tabs |
| 6 | `frontend/src/pages/PedestalDetail.tsx` | COMPLETE | New page — Real Time + Berths + Controls tabs |
| 7 | `frontend/src/App.tsx` | COMPLETE | Added /marinas/:marinaId/pedestals/:pedestalId route |
| 8 | `backend/tests/test_pedestal_ext.py` | COMPLETE | 19 tests (TC-PX-01..19), all passing |

### Test run result: 19 new tests passed, 0 new failed (2026-04-11)
Pre-existing: 7 tests in existing files fail due to SecurityMiddleware 403 vs 401 for
unauthenticated requests — confirmed pre-existing before Phase 2 (verified with git stash).

---

### Backend — New Methods (pedestal_api.py)

- `get_berth_occupancy(pedestal_id, marina_id, db)` → `Tuple[Any, bool]`
  - GET `/api/ext/pedestals/{id}/berths/occupancy` — cached, stale fallback, sync_log
- `get_camera_frame(pedestal_id, marina_id, db)` → `bytes`
  - GET `/api/ext/pedestals/{id}/camera/frame` — raw JPEG; 3-retry; sync_log; raises on exhaustion
  - No stale cache (bytes cannot be stored in JSON PedestalCache column)
- `get_camera_stream_url(pedestal_id, marina_id, db)` → `Tuple[Any, bool]`
  - GET `/api/ext/pedestals/{id}/camera/stream` — cached, stale fallback, sync_log

### Backend — New Router (pedestal_ext.py)

Prefix: `/api/marinas/{marina_id}/pedestals/{pedestal_id}/`
Auth: `get_current_user` + `require_marina_access` (consistent with all existing routers)

- `GET .../berths/occupancy` → 200 `{marina_id, pedestal_id, is_stale, data}` or 503
- `GET .../camera/frame` → 200 `image/jpeg` bytes, `Cache-Control: no-store` or 503
  - Frame fetch logged to audit_log (operator-initiated action)
- `GET .../camera/stream` → 200 `{marina_id, pedestal_id, is_stale, data}` or 503

### Frontend — Dashboard.tsx Restructure

- Tab 1 "Overview": all existing content unchanged; pedestal cards now clickable → PedestalDetail
- Tab 2 "Berths":
  - Grouped by pedestal with section header (pedestal name + id)
  - Occupancy: Occupied (red) / Available (green) / No Analysis (grey)
  - Get Frame button → JPEG inline with capture timestamp
  - Refresh All button + per-pedestal Refresh; data on demand (not polled)
  - "No berths configured" / "Feature not available on this pedestal" messages

### Frontend — PedestalDetail.tsx (new page at /marinas/:marinaId/pedestals/:pedestalId)

- Tab 1 "Real Time": health indicators, sessions, alarm log — all filtered to this pedestal
- Tab 2 "Berths": per-berth occupancy + Refresh, Get Frame inline, Live Stream (RTSP URL + VLC note)
- Tab 3 "Controls": Allow/Deny/Stop sessions + Acknowledge alarms
  - Mirrors PedestalControl look and feel; all actions require confirmation dialog
  - Every action → existing ERP audit_log (user_id, marina_id, pedestal_id, action, timestamp)

### Design Decisions

- URL pattern `/api/marinas/{marina_id}/pedestals/{pedestal_id}/...` chosen over `/api/erp/pedestals/{id}/...` for consistency with existing codebase and explicit marina scoping
- `get_camera_frame` raises on failure (no stale cache): bytes cannot go in JSON PedestalCache; stale frames have no operational value
- Camera frame fetch logged to audit_log because it is an operator-initiated action
- PedestalDetail Controls tab reuses all existing ERP endpoints — no new backend endpoints needed
- Session and alarm filtering to current pedestal done client-side from marina-wide fetches
