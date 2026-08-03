# User Data Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Isolate portfolio, watchlist, notes, uploaded reports, and Ask AI conversations by authenticated user.

**Architecture:** A central `user_storage.py` derives a safe user directory from server-verified identity. Private endpoints pass that directory into focused JSON/file repositories; the frontend moves browser-global data to authenticated APIs while retaining only device-level settings locally.

**Tech Stack:** FastAPI, signed HttpOnly session cookies, atomic JSON files, React 19, React Router, TypeScript, Node test runner, pytest.

## Global Constraints

- Admin and normal users can access only their own data.
- Usernames never appear in filesystem paths; directories use the first 16 hex characters of SHA-256.
- `VR_API_KEY` alone cannot access private data.
- Without configured login users, private data maps to `_local` for backward-compatible single-user use.
- JSON writes use a temporary file plus `os.replace`; paths never derive from client-provided usernames.
- Existing unscoped data is preserved and is never automatically assigned to a user.

---

### Task 1: User storage boundary and request identity

**Files:**
- Create: `backend/user_storage.py`
- Modify: `backend/app.py`
- Test: `backend/tests/test_user_storage.py`

**Interfaces:**
- Produces: `UserIdentity`, `identity_from_request(request)`, `user_dir(identity)`, `private_identity(request)`.

- [ ] Write failing tests proving `alice` and `bob` resolve to different hash directories, `../alice` cannot escape the root, authenticated requests receive `request.state.user`, and bearer-only private requests return 401.
- [ ] Run `python -m pytest tests/test_user_storage.py -q` and verify missing module/behavior failures.
- [ ] Implement immutable `UserIdentity(username, role)`, SHA-256 directory derivation, atomic `identity.json`, and middleware request identity assignment.
- [ ] Add `_local` identity when `LOGIN_USERS` is empty and reject missing session identity on private endpoints.
- [ ] Run the targeted tests and commit only Task 1 files.

### Task 2: Per-user portfolio and report repositories

**Files:**
- Modify: `backend/portfolio.py`
- Modify: `backend/myreports.py`
- Modify: `backend/app.py`
- Test: `backend/tests/test_private_data_isolation.py`

**Interfaces:**
- Consumes: `private_identity(request)` and `user_dir(identity)`.
- Produces: portfolio/report endpoints whose storage root is explicit per request.

- [ ] Write failing integration tests: Alice adds a holding and report; Bob sees an empty portfolio/report list and cannot download/delete Alice's report ID.
- [ ] Run the isolation tests and verify cross-user leakage failures against the current global files.
- [ ] Refactor portfolio functions to accept `data_dir`, deriving `portfolio.json` inside it while preserving atomic writes and per-file locks.
- [ ] Refactor report functions to accept `reports_dir`, with `index.json` plus `files/<id>.<ext>` and no module-global user directory.
- [ ] Pass the current user's directory from every portfolio/report route and update the scheduler to iterate existing user directories without sharing failures.
- [ ] Run targeted and existing portfolio/report tests, then commit Task 2 files.

### Task 3: Watchlist and research-note APIs

**Files:**
- Create: `backend/private_json.py`
- Modify: `backend/app.py`
- Test: `backend/tests/test_watchlist_notes.py`

**Interfaces:**
- Produces: `GET/PUT /api/watchlist`; `GET/POST/DELETE /api/notes`; atomic bounded JSON repositories.

- [ ] Write failing tests proving watchlist normalization/deduplication, note CRUD, size limits, and Alice/Bob isolation.
- [ ] Run targeted tests and verify 404 failures.
- [ ] Implement an atomic JSON repository with a lock keyed by resolved file path.
- [ ] Implement watchlist validation and a maximum of 200 codes.
- [ ] Implement note IDs server-side, a 1000-note limit, and bounded title/body/source fields.
- [ ] Run targeted tests and commit Task 3 files.

### Task 4: Ask AI conversation API

**Files:**
- Modify: `backend/private_json.py`
- Modify: `backend/app.py`
- Test: `backend/tests/test_chat_storage.py`

**Interfaces:**
- Produces: `GET/PUT/DELETE /api/chats/{scope}` storing `{scope, messages, updatedAt}` in `chats/<sha256(scope)>.json`.

- [ ] Write failing tests for round-trip, clear, malformed scope, message cap, body cap, and cross-user isolation for identical scopes.
- [ ] Run targeted tests and verify missing-route failures.
- [ ] Implement scope hashing, maximum 40 persisted messages, accepted `user|assistant` roles, and a 512 KiB serialized payload limit.
- [ ] Run targeted tests and commit Task 4 files.

### Task 5: Frontend migration to authenticated storage APIs

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/lib/watchlist.ts`
- Modify: `frontend/src/lib/notes.ts`
- Modify: `frontend/src/pages/Watchlist.tsx`
- Modify: `frontend/src/pages/DailyReview.tsx`
- Modify: `frontend/src/pages/Intel.tsx`
- Modify: `frontend/src/pages/Notes.tsx`
- Modify: `frontend/src/components/ui/SaveNoteButton.tsx`
- Modify: `frontend/src/components/ui/AskAiButton.tsx`
- Test: `frontend/tests/user-storage.test.mjs`

**Interfaces:**
- Consumes: watchlist, notes, and chats endpoints from Tasks 3-4.
- Produces: async user-scoped frontend persistence with no unscoped private `localStorage` writes.

- [ ] Write failing tests around exported client calls and static guards that reject `vr-watchlist`, `vr-notes`, and route-only chat persistence as primary storage.
- [ ] Run `npm test` and verify the new tests fail for existing local-only behavior.
- [ ] Add typed API functions for watchlist, notes, and chats.
- [ ] Convert pages and buttons to async loading/error states; update all watchlist consumers.
- [ ] Change Ask AI history load/save/clear to the chat API and retain complete-turn filtering and request identity guards.
- [ ] Run frontend tests and `npm run build`, then commit Task 5 files.

### Task 6: Migration command, documentation, and full verification

**Files:**
- Create: `backend/migrate_user_data.py`
- Create: `backend/tests/test_migrate_user_data.py`
- Modify: `backend/.env.example`
- Modify: `README.md`

**Interfaces:**
- Produces: `python3 migrate_user_data.py --to-user USER [--move]`, defaulting to copy and printing a file-count report without contents.

- [ ] Write failing tests for unknown users, copy-by-default, explicit move, and refusal to overwrite populated target data.
- [ ] Run targeted tests and verify the command is absent.
- [ ] Implement migration for legacy portfolio/report files using the same `user_storage` resolver; never infer a destination user.
- [ ] Document `LOGIN_USERS`, directory layout, migration, backup, and API-key private-data restriction.
- [ ] Run `python -m pytest -q`, `npm test`, `npm run build`, and `git diff --check`.
- [ ] Verify with two live test users that switching accounts changes all five private data views, then commit Task 6 files.

