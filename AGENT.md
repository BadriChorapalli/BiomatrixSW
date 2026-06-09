# BiomatrixSync — AI Agent Context

This file is for AI coding assistants working on this codebase. Read this before making any changes.

---

## What This App Does

BiomatrixSync pulls punch records from ZKTeco-compatible biometric attendance terminals (eSSL, ZKTeco, Realtime, etc.) over LAN, derives check-in/check-out times using edge-case logic, and marks attendance in School Insights via REST API. It runs as a desktop app (Mac `.app` / Windows `.exe`) built with Python + CustomTkinter + PyInstaller.

---

## Non-Obvious Rules — Read Before Changing Anything

### 1. Never use device `status` field for check-in/check-out direction
Devices placed at exit gates report all punches as `CHECK OUT` (status=1) regardless of direction. The status field is captured but **completely ignored** for any business logic. Always use `_derive_daily_records()` in `api_client.py`.

### 2. Never call `mark_attendance()` twice for the same user in one cycle
`_derive_daily_records()` must run locally first, then a **single** `POST /staff-attendance/mark/` call is made with both `check_in` and `check_out` together. The backend has `explicit_clear_checkout` logic: sending `check_out: null` explicitly clears a stale check-out; omitting `check_out` preserves the existing value.

### 3. `marked_today` is the gatekeeper for backend calls
After each auto-pull, the scheduler compares `sorted(code_mappings.keys())` vs `sorted(get_marked_today(today))`. If equal → skip entirely. Only missing bio_codes trigger `mark_attendance()`. A successful mark immediately inserts into `marked_today`. Never bypass this.

### 4. Database migrations must be backward-compatible
New columns are added via `ALTER TABLE ... ADD COLUMN` inside a `try/except` block in `init_db()` after the main `executescript`. This handles existing installs silently. Never `DROP` or `RENAME` a column.

### 5. All UI updates from threads must use `self.after(0, lambda: ...)`
Tkinter is not thread-safe. Any call that touches a widget from a background thread must be dispatched via `self.after(0, ...)`.

### 6. `save_staff()` uses `user_id` not `id`
The School Insights API returns staff with field `user_id`. An earlier bug used `id` which stored NULL. The fix: `s.get("user_id") or s.get("id")`.

---

## Architecture at a Glance

```
main.py
  └─ init_db()
  └─ LoginWindow → MainWindow
       ├─ DashboardTab      ← reads local attendance count + fetches SI server for today's status
       ├─ HistoryTab        ← reads local attendance table
       ├─ DevicesTab        ← CRUD for devices (brand, force_udp)
       ├─ RegistrationTab   ← device approval flow; hides form when APPROVED/PENDING
       ├─ SettingsTab       ← poll time slots, clear cloud sync data
       └─ LogsTab           ← live log output

scheduler.py (background threads)
  ├─ Daily sync at configured time → sync.py → device.py + api_client.py
  └─ Auto-pull loop (_run_poll):
       pull_attendance(since=last_pull, force_udp=device.force_udp)
       save_attendance()
       compare marked_today vs code_mappings
       for missed: _derive_daily_records() → mark_attendance() → save_marked_today()
       sleep(_current_interval())   ← reads poll_slots from DB every cycle
```

---

## File Responsibilities

| File | Owns |
|---|---|
| `database.py` | All SQLite reads/writes. `init_db()` creates tables and runs migrations. |
| `device.py` | pyzk wrapper. `pull_attendance(force_udp)`, `get_device_users(force_udp)`, `test_connection(force_udp)`. Uses `_zk()` helper. |
| `api_client.py` | School Insights API calls. Also owns `_derive_daily_records()` and `_cluster_punches()` — the attendance derivation logic. |
| `sync.py` | Batch sync orchestration: pull → CSV → DB → upload. Called by scheduler daily and by manual "Sync Now". |
| `scheduler.py` | Two background threads: daily schedule + auto-pull poll loop. Both are daemon threads. |

---

## Database Tables

| Table | Key fields | Notes |
|---|---|---|
| `devices` | id, name, ip, port, password, enabled, **brand**, **force_udp** | brand/force_udp added via ALTER TABLE migration |
| `attendance` | device_id, user_id, date, time | UNIQUE constraint prevents duplicates |
| `code_mappings` | bio_code (PK), si_user_id, si_name | bio_code = device enrollment ID as TEXT |
| `marked_today` | bio_code, date (composite PK) | Resets naturally each day |
| `settings` | key, value | See DEVELOPER.md for all keys |
| `staff` | si_user_id (UNIQUE), name, email, roles | Local cache of SI staff |
| `sync_logs` | status, records_pulled, records_uploaded | One row per sync |

---

## API Essentials

Base: `https://api.schoolinsights.in`

All requests need:
```
X-App-Token: ae96a8093cab7d726766c83a6caf1460a4348a56d9ac3ef167b77e00f020436e
X-Device-Id: <uuid from settings>
Authorization: Bearer <si_access_token>  (when approved)
```

Mark attendance: `POST /staff-attendance/mark/`
```json
{
  "user_id": 45, "school_id": 2, "date": "2026-06-09",
  "status": "present", "source": "biometric_upload",
  "check_in": "2026-06-09T08:30:00+05:30",
  "check_out": null
}
```

Get today's attendance: `GET /staff-attendance/by-school/?school_id=X&date=Y`  
Returns `users[]` with `user_id`, `status`, `check_in`, `check_out`.

---

## Build Commands

**Mac (run on Mac):**
```bash
./build.sh
codesign --sign - --force --deep --entitlements entitlements.plist dist/BiomatrixSync.app
open dist/BiomatrixSync.app
```

**Windows (run on Windows PC directly — cannot cross-compile):**
```bat
build.bat
```
Output: `dist\BiomatrixSync.exe` — self-contained, no Python needed on target machine.

Git: commit only `app/**/*.py`, `main.py`, `build.spec`, `build.sh`, `build.bat`, `requirements.txt`, `entitlements.plist`. Never commit `dist/`, `build/`, `__pycache__/`, `*.db`, `exports/`.

---

## What Changes Are Safe vs Risky

**Safe:**
- Adding new UI widgets inside existing tabs
- Adding new `database.py` helper functions
- Adding new API endpoints in `api_client.py`
- Changing log messages

**Risky — test carefully:**
- Any change to `_derive_daily_records()` or `_cluster_punches()` — affects all attendance correctness
- Any change to `_run_poll()` in `scheduler.py` — affects real-time marking
- Any change to `mark_attendance()` payload — must stay compatible with backend `explicit_clear_checkout` logic
- `init_db()` schema changes — must include `ALTER TABLE` migration

**Never do:**
- Call `mark_attendance()` more than once per user per poll cycle
- Use `r.status` from pyzk to determine check-in vs check-out direction
- Update UI widgets directly from a background thread
- Drop or rename existing database columns
