# BiomatrixSync — Developer Guide

## Overview

BiomatrixSync is a Python desktop application that bridges ZKTeco-compatible biometric attendance terminals with the School Insights platform. It runs on Mac and Windows, packages as a single binary via PyInstaller, and stores all state in a local SQLite database.

---

## Dev Environment Setup

**Prerequisites:** Python 3.12, pip

```bash
cd BiomatrixSW

# Create virtual environment
python3 -m venv venv
source venv/bin/activate          # Mac/Linux
venv\Scripts\activate             # Windows

# Install dependencies
pip install -r requirements.txt

# Run in dev mode (no build needed)
python main.py
```

**requirements.txt:**
```
customtkinter==5.2.2
pyzk==0.9
requests==2.31.0
schedule==1.2.1
Pillow==10.3.0
pyinstaller==6.6.0
```

---

## Project Structure

```
BiomatrixSW/
├── main.py                    # Entry point — init DB, show login window
├── build.spec                 # PyInstaller spec (auto-detects Mac/Windows)
├── build.sh                   # Mac build script
├── build.bat                  # Windows build script
├── entitlements.plist         # macOS network sandbox entitlements
├── requirements.txt
├── app/
│   ├── core/
│   │   ├── database.py        # All SQLite operations
│   │   ├── device.py          # pyzk wrapper — connect, pull, get_users
│   │   ├── api_client.py      # School Insights REST API + attendance logic
│   │   ├── sync.py            # Orchestrates pull → CSV → DB → upload
│   │   └── scheduler.py       # Background threads (daily sync + auto-pull)
│   └── ui/
│       ├── login_window.py
│       ├── main_window.py     # Tab container
│       ├── dashboard_tab.py
│       ├── history_tab.py
│       ├── devices_tab.py
│       ├── registration_tab.py
│       ├── settings_tab.py
│       └── logs_tab.py
```

---

## Building

### Mac

```bash
chmod +x build.sh
./build.sh

# REQUIRED after every build — restores LAN access entitlements
codesign --sign - --force --deep --entitlements entitlements.plist dist/BiomatrixSync.app

# Run
open dist/BiomatrixSync.app
```

Output: `dist/BiomatrixSync.app`

### Windows

Run on the Windows machine directly (PyInstaller cannot cross-compile):

```bat
build.bat
```

Output: `dist\BiomatrixSync.exe`

> **Note:** The same `build.spec` file is used for both platforms. PyInstaller detects the OS at build time.

### PyInstaller Notes

- `jaraco.*` packages must be listed as hidden imports in `build.spec` — pyzk depends on them but PyInstaller doesn't auto-detect them.
- macOS entitlements are stripped by PyInstaller's signing step; `codesign` must be re-run manually every time.
- The `--onedir` mode is used (not `--onefile`) for faster startup.

---

## Database Schema

SQLite file location:
- **Mac:** `~/Library/Application Support/BiomatrixSync/biomatrix.db`
- **Windows:** `%APPDATA%\BiomatrixSync\biomatrix.db`

### Tables

**`devices`**
```sql
id, name, ip, port, password, enabled, brand TEXT DEFAULT 'eSSL', force_udp INTEGER DEFAULT 0
```
`brand` — display label (eSSL/ZKTeco/Realtime/FingerTec/Anviz/Matrix/Other)  
`force_udp` — 0 = TCP (default), 1 = UDP (older device models)

New columns are added via `ALTER TABLE` migration in `init_db()` so existing installs auto-upgrade.

**`attendance`**
```sql
device_id, device_name, user_id TEXT, name, date, time, status
UNIQUE(device_id, user_id, date, time)
```
Raw punch records. `INSERT OR IGNORE` prevents duplicates.

**`code_mappings`**
```sql
bio_code TEXT PRIMARY KEY, si_user_id INTEGER, si_name TEXT
```
Maps biometric device enrollment ID → School Insights user_id. Populated from `GET /biometric/codes/`.

**`marked_today`**
```sql
bio_code TEXT, date TEXT, marked_at TEXT
PRIMARY KEY (bio_code, date)
```
Tracks which staff have been successfully marked in School Insights for today. Reset naturally each day (keyed by date).

**`staff`** — local cache of SI staff list  
**`sync_logs`** — record of each pull/upload operation  
**`settings`** — key/value store for all config

### Settings Keys

| Key | Purpose |
|---|---|
| `auth_username` / `auth_password` | App login (password SHA-256 hashed) |
| `sync_time` | Daily batch upload time (24h, default 18:00) |
| `auto_pull_enabled` | "1" / "0" |
| `auto_pull_interval` | Default interval in minutes (used outside time slots) |
| `poll_slots` | JSON array of `{start, end, interval}` time slots |
| `last_device_pull` | Datetime of last incremental pull |
| `si_device_id` | Persistent UUID for this installation |
| `si_request_id` | Approval request ID |
| `si_access_token` | JWT (30-day) |
| `si_refresh_token` | JWT (365-day) |
| `si_device_status` | PENDING / APPROVED / REJECTED |
| `si_org_id` / `si_school_id` | Selected org + school |

---

## Core Logic

### `_derive_daily_records()` — `api_client.py`

The most important function in the codebase. Converts raw punch timestamps into one `{check_in, check_out}` record per person per day.

**Why it exists:** Indian biometric devices (especially exit-gate units) report all punches as `CHECK OUT` regardless of direction. The device `status` field is unreliable and is completely ignored.

**Algorithm:**
1. Group all punches for a user by time.
2. Cluster consecutive punches within 2 minutes into one event (handles double/triple taps).
3. `check_in` = first punch of the first cluster (earliest morning tap).
4. `check_out` = last punch of the last cluster — **only** if it is >5 minutes after check_in (prevents a morning double-tap becoming a fake check-out).
5. Clusters between first and last = permission breaks (stored in `breaks[]`, display only).

This function is used for **both** real-time auto-pull and batch upload — single source of truth.

### Auto-pull loop — `scheduler.py`

```
_run_poll()
  ↓ pull_attendance(since=last_pull)   ← incremental, only new records
  ↓ save_attendance()                  ← INSERT OR IGNORE
  ↓ get_marked_today(today)            ← who's already sent to SI today
  ↓ if sorted(mapped) == sorted(marked) → skip
  ↓ for each missed bio_code:
      get_attendance_by_date()         ← ALL today's punches for that user
      _derive_daily_records()          ← edge-case derivation
      mark_attendance()                ← single POST to SI
      save_marked_today()              ← persist success
  ↓ sleep(_current_interval())         ← reads poll_slots from DB every cycle
```

**Key design decisions:**
- `since=last_pull` — only fetches new records since the last cycle, reducing device load.
- `marked_today` check — if all mapped staff are already marked, the entire marking block is skipped regardless of whether new records came in.
- `mark_attendance()` is called **once per user** using the full day's punch history — never called twice for the same person in the same cycle.

### `mark_attendance()` — `api_client.py`

Single `POST /staff-attendance/mark/` call with both `check_in` and `check_out`. Sending `check_out: null` explicitly tells the backend to clear any stale check-out from a previous call (the backend has `explicit_clear_checkout` logic for this).

### Multi-device support

pyzk's `ZK()` constructor accepts `force_udp=True` for older devices that use UDP instead of TCP. The `devices` table stores `force_udp` per device and it's threaded through all device functions. All other logic (data format, derivation, marking) is identical regardless of device brand.

---

## School Insights API

**Base URL:** `https://api.schoolinsights.in`

**Required headers on every request:**
```
X-App-Token: ae96a8093cab7d726766c83a6caf1460a4348a56d9ac3ef167b77e00f020436e
X-Device-Id: <si_device_id>
Authorization: Bearer <si_access_token>   (after approval only)
```

### Key Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/face-attendance/v1/face-attendance/organizations` | GET | List organisations |
| `/face-attendance/v1/face-attendance/schools?organization_id=X` | GET | List schools |
| `/face-attendance/v1/face-attendance/device-approval/request` | POST | Submit device registration |
| `/face-attendance/v1/face-attendance/device-approval/status/{id}` | GET | Poll approval status |
| `/staff-attendance/by-school/?school_id=X&date=Y` | GET | Staff list with today's attendance |
| `/staff-attendance/mark/` | POST | Mark attendance (create or update) |
| `/biometric/codes/?school_id=X` | GET | Staff → bio_code mappings |
| `/biometric/codes/assign/` | POST | Assign bio_code to staff |
| `/biometric/device-users/sync/` | POST | Bulk sync enrolled device users |

### mark/ payload
```json
{
  "user_id": 45,
  "school_id": 2,
  "date": "2026-06-09",
  "status": "present",
  "source": "biometric_upload",
  "check_in": "2026-06-09T08:30:00+05:30",
  "check_out": null
}
```
`check_out: null` (explicit) → backend clears stale check_out.  
`check_out` omitted → backend preserves existing check_out.

---

## UI Architecture

All UI is CustomTkinter (dark theme). Every tab is a class that extends `CTkFrame`.

- `main_window.py` holds the tab strip and the shared `append_log()` method.
- Long-running operations always run in `threading.Thread(daemon=True)` — never on the main thread.
- UI updates from threads always go through `self.after(0, lambda: ...)`.
- The Dashboard auto-refreshes every 60 seconds via `self.after(60_000, ...)`.

### Registration tab behaviour
- If `si_device_status` is APPROVED or PENDING on load → form is hidden, only status banner + approval panel show.
- A **Re-register** button on the banner reveals the form if needed.
- After successful submission → form auto-hides, polling starts.

---

## Adding a New Feature

1. Database changes → add to `init_db()` DDL + an `ALTER TABLE` migration block for existing installs.
2. New API calls → add to `api_client.py`.
3. New UI sections → add to the relevant `*_tab.py`. Use `threading.Thread` + `self.after(0, ...)` for any I/O.
4. Build and test with `python main.py` before packaging.
5. Build: `./build.sh` → `codesign ...` → `open dist/BiomatrixSync.app`.

---

## Common Pitfalls

| Pitfall | What happens | Fix |
|---|---|---|
| Forgot `codesign` after Mac build | App can't connect to device (sandbox blocks TCP) | Always run `codesign` after `build.sh` |
| Marking twice for same user | `marked_today` prevents this — but don't bypass the check | Never call `mark_attendance` without checking `marked_today` first |
| Using device `status` field | Gives wrong check_in/check_out on exit-gate devices | Always use `_derive_daily_records()`, never raw status |
| UI update from background thread | Tkinter crash (not thread-safe) | Wrap all UI updates in `self.after(0, lambda: ...)` |
| `save_staff()` using `id` instead of `user_id` | Staff stored with NULL si_user_id | API returns `user_id`, not `id` — use `s.get("user_id") or s.get("id")` |
