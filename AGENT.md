# BiomatrixSync — AI Agent Context

This file is for AI coding assistants working on this codebase. Read this before making any changes.

---

## What This App Does

BiomatrixSync pulls punch records from biometric attendance terminals over LAN, derives check-in/check-out times using edge-case logic, and marks attendance in School Insights via REST API. It runs as a desktop app (Mac `.app` / Windows `.exe`) built with Python + CustomTkinter + PyInstaller.

**Two device brands are supported:**
- **eSSL / ZKTeco** (and compatible: Realtime, FingerTec, Anviz, Matrix) — ZK protocol via **pyzk** library, TCP port 4370
- **Morx BioFace-MSD1K** — SBXPC protocol via custom pure-Python implementation in `morx_device.py`, TCP port 5005

`device.py` is the single dispatch layer. All callers pass `brand=device.get("brand", "essl")` and `device.py` routes to the correct implementation. **No eSSL code path is touched when brand is Morx.**

---

## Non-Obvious Rules — Read Before Changing Anything

### 1. Never use device `status` field for check-in/check-out direction
Devices placed at exit gates report all punches as `CHECK OUT` (status=1) regardless of direction. The status field is captured but **completely ignored** for any business logic. Always use `_derive_daily_records()` in `api_client.py`. This applies to both eSSL and Morx devices.

### 2. Never call `mark_attendance()` twice for the same user in one cycle
`_derive_daily_records()` must run locally first, then a **single** `POST /staff-attendance/mark/` call is made with both `check_in` and `check_out` together. The backend has `explicit_clear_checkout` logic: sending `check_out: null` explicitly clears a stale check-out; omitting `check_out` preserves the existing value.

### 3. `marked_today` is the gatekeeper for backend calls
After each auto-pull, the scheduler compares `sorted(code_mappings.keys())` vs `sorted(get_marked_today(today))`. If equal → skip the primary marking pass entirely. Only missing bio_codes trigger `mark_attendance()`. A successful mark immediately inserts into `marked_today`. Never bypass this.

`run_fallback_sync()` also respects `marked_today` — it filters out already-marked codes before building its payload, so it will not re-send a code that was already successfully marked.

### 4. Database migrations must be backward-compatible
New columns are added via `ALTER TABLE ... ADD COLUMN` inside a `try/except` block in `init_db()` after the main `executescript`. This handles existing installs silently. Never `DROP` or `RENAME` a column.

### 5. All UI updates from threads must use `self.after(0, lambda: ...)`
Tkinter is not thread-safe. Any call that touches a widget from a background thread must be dispatched via `self.after(0, ...)`.

### 6. `save_staff()` uses `user_id` not `id`
The School Insights API returns staff with field `user_id`. An earlier bug used `id` which stored NULL. The fix: `s.get("user_id") or s.get("id")`.

### 7. Always pass `brand=` when calling device functions
Every call to `pull_attendance()`, `get_device_users()`, and `test_connection()` in `device.py` must include `brand=device.get("brand", "essl")`. Missing this kwarg silently routes a Morx device to the ZK/pyzk code path, which fails against port 5005. All call sites: `scheduler.py`, `sync.py`, `history_tab.py`, `staff_tab.py`, `devices_tab.py`.

### 8. Morx device: do NOT send EnableDevice(0) before reads
Sending the lock command (`79 19 0b 01`) before a read leaves the device locked if the read socket is closed before the unlock command is sent. Instead: read without locking, then send EnableDevice(1) (`79 19 0c 01`) via a **fresh TCP connection** using `_unlock()` after the data stream is drained.

### 9. Morx user records have no name field
The SBXPC user record is 8 bytes — there is no name field in the hardware protocol. Names come from the `code_mappings` table (bio_code → si_name). `_enrich_names()` in `device.py` fills names after every Morx get_device_users/pull_attendance call. If `code_mappings` is empty, the Name column will be blank — that is expected until staff are mapped in School Insights.

---

## Architecture at a Glance

```
main.py
  └─ init_db()
  └─ LoginWindow → MainWindow
       ├─ DashboardTab      ← reads local attendance count + fetches SI server for today's status
       ├─ HistoryTab        ← reads local attendance table
       ├─ DevicesTab        ← CRUD for devices (brand, force_udp); Morx auto-sets port 5005
       ├─ RegistrationTab   ← device approval flow; hides form when APPROVED/PENDING
       ├─ SettingsTab       ← poll time slots, clear cloud sync data
       └─ LogsTab           ← live log output

scheduler.py (background threads)
  ├─ Daily sync at configured time → sync.py → device.py + api_client.py
  └─ Auto-pull loop (_run_poll):
       pull_attendance(since=last_pull, force_udp=..., brand=...)   ← brand routes to eSSL or Morx
       save_attendance()
       compare marked_today vs code_mappings
       for missed: _derive_daily_records() → mark_attendance() → save_marked_today()
       run_fallback_sync(today)   ← always runs; no-op if all codes already marked
       sleep(_current_interval())   ← reads poll_slots from DB every cycle

device.py (brand dispatch)
  ├─ _is_morx(brand) → True if brand.lower() == "morx"
  ├─ Morx path → morx_device.py (SBXPC protocol, port 5005, stdlib only)
  └─ eSSL/ZKTeco path → pyzk (ZK protocol, port 4370)
```

---

## File Responsibilities

| File | Owns |
|---|---|
| `database.py` | All SQLite reads/writes. `init_db()` creates tables and runs migrations. |
| `device.py` | Brand router. `_is_morx()` dispatches to morx_device (SBXPC) or pyzk (ZK). Exposes `pull_attendance(brand)`, `get_device_users(brand)`, `test_connection(brand)`. Also owns `_enrich_names()` for Morx name lookup. |
| `morx_device.py` | **Morx BioFace-MSD1K only.** Complete SBXPC wire protocol: connect, ReadAllUserID, ReadAllGLogData, EnableDevice. Pure Python — no DLL, no pip packages beyond stdlib. |
| `api_client.py` | School Insights API calls. Also owns `_derive_daily_records()`, `_cluster_punches()`, `bulk_mark_by_biocodes()`, and `run_fallback_sync()` — the attendance derivation and fallback upload logic. |
| `sync.py` | Batch sync orchestration: pull → CSV → DB → upload. Called by scheduler daily and by manual "Sync Now". |
| `scheduler.py` | Two background threads: daily schedule + auto-pull poll loop. Both are daemon threads. |

---

## Device Brand Details

### eSSL / ZKTeco path
- Library: `pyzk 0.9`
- Port: 4370 (TCP), optional UDP via `force_udp=True`
- Auth: `ZK(ip, port, timeout=10, password=int(password), force_udp=..., ommit_ping=False)`
- Name: stored on device; returned by `conn.get_users()`
- Records: `conn.get_attendance()` — incremental via `since=` filter applied client-side

### Morx BioFace-MSD1K path
- Library: none (stdlib `socket` + `struct`)
- Port: 5005 (TCP only)
- Packet: `[55 aa][mach 2B LE][cmd 4B][params 4B][pad 2B][cs 2B]` = 16 bytes total; `cs = sum(all_preceding_bytes) & 0xFFFF`
- Auth: two-packet handshake (`79 19 52 00` command with password as LE uint32 in params)
- Machine number: always 0 (`_MACH = 0`) — hardware refuses other values
- Timestamp epoch: 2000-01-01 00:00:00 (not Unix epoch)
- Full log every pull — SBXPC has no incremental read; filter by date/since client-side
- ACK beacon: must send `5a a5 [mach 2B] 01 00 00 00 [cs]` between device beacon and response header for ReadAllGLogData
- Log stream: starts with a 14-byte `a5 5a` header that must be skipped

---

## Database Tables

| Table | Key fields | Notes |
|---|---|---|
| `devices` | id, name, ip, port, password, enabled, **brand**, **force_udp** | brand includes "Morx"; force_udp ignored for Morx |
| `attendance` | device_id, user_id, date, time | UNIQUE constraint prevents duplicates |
| `code_mappings` | bio_code (PK), si_user_id, si_name | bio_code = device enrollment ID as TEXT; used for Morx name lookup |
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
# REQUIRED after every Mac build — restores LAN/network entitlements
codesign --sign - --force --deep --entitlements entitlements.plist dist/BiomatrixSync.app
open dist/BiomatrixSync.app
```

**Windows (must run on a Windows machine — PyInstaller cannot cross-compile):**

```bat
# Activate venv first if using one
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Python 3.14 only: override the two incompatible packages
pip install pyinstaller==6.20.0 Pillow==12.2.0

# Build both EXEs (GUI + service)
build.bat
```

Output:
- `dist\BiomatrixSync.exe` — GUI desktop app
- `dist\BiomatrixSyncService.exe` — headless Windows Service (entry point: `windows_service.py`)

**After building on Windows, rebuild the installer:**

```bat
cd BiomatrixSyncPackage
copy /Y ..\dist\BiomatrixSync.exe dist\
copy /Y ..\dist\BiomatrixSyncService.exe dist\
build_installer.bat
```

Output: `BiomatrixSyncPackage\Output\BiomatrixSync_Setup.exe` — single-file installer for school PCs. Requires Inno Setup 6 installed on the build machine.

> `pystray._win32` warnings on Mac builds ("Hidden import not found") are harmless — the module is Windows-only and intentionally absent on Mac.
> `win32timezone` must be in hidden imports for the service EXE — without it `win32serviceutil` crashes at install time with `ModuleNotFoundError`.

Git: commit only `app/**/*.py`, `main.py`, `windows_service.py`, `build.spec`, `build.sh`, `build.bat`, `requirements.txt`, `entitlements.plist`, `BiomatrixSyncPackage/setup.iss`, `BiomatrixSyncPackage/build_installer.bat`. Never commit `dist/`, `build/`, `BiomatrixSyncPackage/dist/`, `BiomatrixSyncPackage/Output/`, `__pycache__/`, `*.db`, `exports/`.

---

## What Changes Are Safe vs Risky

**Safe:**
- Adding new UI widgets inside existing tabs
- Adding new `database.py` helper functions
- Adding new API endpoints in `api_client.py`
- Changing log messages
- Adding new SBXPC commands to `morx_device.py`

**Risky — test carefully:**
- Any change to `_derive_daily_records()` or `_cluster_punches()` — affects all attendance correctness for both brands
- Any change to `_run_poll()` in `scheduler.py` — affects real-time marking
- Any change to `mark_attendance()` payload — must stay compatible with backend `explicit_clear_checkout` logic
- `init_db()` schema changes — must include `ALTER TABLE` migration
- SBXPC packet format in `morx_device.py` — checksum must cover all bytes including magic header `55 aa`

**Never do:**
- Call `mark_attendance()` more than once per user per poll cycle — `run_fallback_sync()` uses a different endpoint (`bulk_mark_by_biocodes`) and is the correct retry path, not a second `mark_attendance()` call
- Use `r.status` from pyzk to determine check-in vs check-out direction
- Update UI widgets directly from a background thread
- Drop or rename existing database columns
- Send `EnableDevice(0)` (lock) before a Morx read without a guaranteed subsequent `_unlock()` call
- Call device functions without `brand=` kwarg (silently fails for Morx devices)
