# BiomatrixSync — Developer Guide

## Overview

BiomatrixSync is a Python desktop application that bridges biometric attendance terminals with the School Insights platform. It runs on Mac and Windows, packages as a single binary via PyInstaller, and stores all state in a local SQLite database.

**Supported device brands:**
- **eSSL / ZKTeco** (and compatible: Realtime, FingerTec, Anviz, Matrix) — ZK protocol via `pyzk` library
- **Morx BioFace-MSD1K** — SBXPC protocol via custom pure-Python implementation (`morx_device.py`). No DLL or extra pip package required.

---

## Dev Environment Setup

**Prerequisites:** Python 3.12+ (3.14 confirmed working on Windows), pip

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
Pillow==12.2.0
pyinstaller==6.20.0
```

> **Python 3.14 (Windows):** PyInstaller 6.6.0 and Pillow 10.3.0 are incompatible with Python 3.14. Use `pyinstaller==6.20.0` and `Pillow==12.2.0` as shown above.

> **Morx devices:** `morx_device.py` uses only `socket` and `struct` from the Python standard library. No additional pip package is needed for Morx support.

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
│   │   ├── device.py          # Brand router: eSSL → pyzk, Morx → morx_device
│   │   ├── morx_device.py     # Morx BioFace-MSD1K — SBXPC protocol, pure Python stdlib
│   │   ├── api_client.py      # School Insights REST API + attendance derivation logic
│   │   ├── sync.py            # Orchestrates pull → CSV → DB → upload
│   │   └── scheduler.py       # Background threads (daily sync + auto-pull)
│   └── ui/
│       ├── login_window.py
│       ├── main_window.py     # Tab container
│       ├── dashboard_tab.py
│       ├── history_tab.py
│       ├── devices_tab.py     # Brand selector auto-sets port (Morx → 5005, others → 4370)
│       ├── registration_tab.py
│       ├── settings_tab.py
│       └── logs_tab.py
```

---

## Device Communication

### eSSL / ZKTeco (`device.py` → `pyzk`)

| Property | Value |
|---|---|
| Library | `pyzk 0.9` |
| Protocol | ZKTeco ZK SDK |
| Port | TCP 4370 (default); UDP optional via `force_udp=True` |
| Auth | Integer password (default 0) |
| User data | Name stored on device, returned by `conn.get_users()` |
| Attendance | `conn.get_attendance()` — all records; filtered by date/since client-side |
| Connection | `ZK(ip, port, timeout=10, password, force_udp, ommit_ping=False)` |

The `force_udp` flag is per-device in the database and passed through all callers. Use it only for older models that don't respond over TCP.

### Morx BioFace-MSD1K (`device.py` → `morx_device.py`)

| Property | Value |
|---|---|
| Library | stdlib only (`socket`, `struct`) — no DLL, no pip package |
| Protocol | SBXPC (SmackBio proprietary) |
| Port | TCP 5005 |
| Machine number | Always `_MACH = 0` (hardware requirement — other values refused) |
| Auth | Two-packet handshake; password sent as LE uint32 in `params` field |
| User data | **No name in hardware.** Names filled from `code_mappings` via `_enrich_names()` |
| Attendance | Full log every pull — SBXPC has no incremental read. Filter by date/since client-side. |
| Timestamp epoch | 2000-01-01 00:00:00 (not Unix epoch) |

#### SBXPC Packet Format
```
[55 aa][mach 2B LE][cmd 4B][params 4B][pad 2B][cs 2B]  = 16 bytes total
checksum = sum(all_preceding_bytes) & 0xFFFF
```

#### SBXPC Commands Used
| Command | Hex | Purpose |
|---|---|---|
| Connect | `79 19 52 00` | Authenticate (two-exchange handshake) |
| EnableDevice(1) / Unlock | `79 19 0c 01` | Release device lock after read |
| ReadAllUserID | `79 19 12 01` | Get enrolled users (8-byte records) |
| ReadAllGLogData | `79 19 07 01` | Get all attendance logs (12-byte records) |

> **EnableDevice lock warning:** Do NOT send EnableDevice(0) (`79 19 0b 01`) before reads. After each read, call `_unlock()` (sends EnableDevice(1) on a fresh TCP connection) so the device doesn't stay locked until TCP timeout (~30–60 s).

> **ReadAllGLogData ACK:** Must send `5a a5 [mach 2B] 01 00 00 00 [cs]` between the device's first beacon and the response header. Missing this ACK causes the device to not return data.

#### Brand routing in `device.py`
```python
def _is_morx(brand):
    return str(brand).strip().lower() == "morx"

def pull_attendance(ip, port, password, target_date=None, since=None, force_udp=False, brand="essl"):
    if _is_morx(brand):
        ok, result = _morx.pull_attendance(ip, port, password, target_date=target_date, since=since)
        if ok: _enrich_names(result)
        return ok, result
    # ... pyzk path unchanged ...
```

All callers must pass `brand=device.get("brand", "essl")`. Missing this kwarg silently routes Morx devices through the pyzk path, which fails.

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

> **Build must run on a Windows machine.** PyInstaller cannot cross-compile from Mac.

#### Prerequisites

- Python 3.10–3.12 recommended. Python 3.14 works but requires package version overrides (see below).
- Git for cloning or pulling the repo.
- The Windows machine must be on the same LAN as a biometric device for testing.

#### Steps

1. **Clone or copy the repo** to the Windows machine.

2. **Create a virtual environment (recommended):**
   ```bat
   cd BiomatrixSW
   python -m venv venv
   venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bat
   pip install -r requirements.txt
   ```

   > **Python 3.14 only:** `requirements.txt` pins `pyinstaller==6.6.0` and `Pillow==10.3.0`, which are incompatible with Python 3.14. After running the above, override the two conflicting packages:
   > ```bat
   > pip install pyinstaller==6.20.0 Pillow==12.2.0
   > ```
   > All other dependencies from `requirements.txt` install normally on 3.14.

4. **Run the build:**
   ```bat
   build.bat
   ```
   Alternatively, run PyInstaller directly:
   ```bat
   pyinstaller build.spec --clean --noconfirm
   ```

5. **Output:** `dist\BiomatrixSync.exe` — fully self-contained, no Python needed on the target PC.

#### Distributing the build

- Copy `dist\BiomatrixSync.exe` to the target PC. No installer wizard is needed — just double-click to launch.
- If Windows Defender shows a SmartScreen warning ("Windows protected your PC"), click **More info → Run anyway**. This is expected for unsigned executables and is not a security issue.
- Some antivirus products may flag PyInstaller executables as suspicious. Add an exclusion for the app folder on affected machines if needed.

#### Windows-specific features in the build

- **System tray (`pystray`):** On Windows the app minimises to the system tray on close (instead of quitting). The `pystray._win32` hidden import in `build.spec` is required for this to work in the packaged `.exe`; the "not found" warnings printed during a Mac build are harmless (the module is platform-specific).
- **Autostart (`winreg`):** The Settings tab includes a "Start with Windows" toggle that writes to `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`. This is Windows-only and is a no-op on Mac.

> **Note:** The same `build.spec` is used for both platforms. PyInstaller detects the OS at build time — Mac builds a `.app` bundle, Windows builds a single `.exe`.

### PyInstaller Notes

- `jaraco.*` packages must be listed as hidden imports in `build.spec` — pyzk depends on them but PyInstaller doesn't auto-detect them. The warnings printed at build time are harmless.
- `pystray._win32` and `pystray._base` are listed as hidden imports for the Windows system tray feature. On Mac these emit "not found" warnings during the build — also harmless; the module is platform-specific and is never loaded at runtime on Mac.
- macOS entitlements are stripped by PyInstaller's signing step; `codesign` must be re-run manually every time after a Mac build.
- The `--onedir` mode is used (not `--onefile`) for faster startup.
- **Python 3.14 (Windows):** Use `pyinstaller==6.20.0` and `Pillow==12.2.0`. The versions pinned in `requirements.txt` (`pyinstaller==6.6.0`, `Pillow==10.3.0`) are Mac-compatible but refuse to install against Python 3.14.

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
`brand` — eSSL / ZKTeco / Realtime / FingerTec / Anviz / Matrix / **Morx** / Other  
`force_udp` — 0 = TCP (default), 1 = UDP. Ignored for Morx (TCP only on port 5005).

New columns are added via `ALTER TABLE` migration in `init_db()` so existing installs auto-upgrade.

**`attendance`**
```sql
device_id, device_name, user_id TEXT, name, date, time, status
UNIQUE(device_id, user_id, date, time)
```
Raw punch records. `INSERT OR IGNORE` prevents duplicates. `name` is blank for Morx until `code_mappings` is populated.

**`code_mappings`**
```sql
bio_code TEXT PRIMARY KEY, si_user_id INTEGER, si_name TEXT
```
Maps biometric device enrollment ID (as TEXT) → School Insights user_id and name. Populated from `GET /biometric/codes/`. Critical for Morx devices since hardware has no name storage — `_enrich_names()` in `device.py` fills names from this table.

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

The most important function in the codebase. Converts raw punch timestamps into one `{check_in, check_out}` record per person per day. Works identically for both eSSL and Morx devices.

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
  ↓ pull_attendance(since=last_pull, force_udp=..., brand=...)   ← routes to eSSL or Morx
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
- `since=last_pull` — for eSSL, filters new records since last cycle. For Morx, full log is always returned; `since` filtering happens client-side in `morx_device.py`.
- `marked_today` check — if all mapped staff are already marked, the entire marking block is skipped regardless of whether new records came in.
- `mark_attendance()` is called **once per user** using the full day's punch history — never called twice for the same person in the same cycle.

### `mark_attendance()` — `api_client.py`

Single `POST /staff-attendance/mark/` call with both `check_in` and `check_out`. Sending `check_out: null` explicitly tells the backend to clear any stale check-out from a previous call (the backend has `explicit_clear_checkout` logic for this).

### Multi-device support

The `devices` table stores `brand` and `force_udp` per device. All device function calls thread both through via `brand=device.get("brand", "essl")` and `force_udp=bool(device.get("force_udp", 0))`. `force_udp` applies only to eSSL/ZKTeco; Morx always uses TCP.

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

### Devices tab — brand/port auto-fill
`devices_tab.py` has `_on_brand_change(brand)`: when **Morx** is selected the Port field is auto-filled with `5005`; switching away from Morx restores `4370`. The brand dropdown is a `CTkOptionMenu` with `command=_on_brand_change`. Note: programmatic `set()` does NOT trigger the command callback — only user interaction does.

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
| Calling device functions without `brand=` | Morx device silently uses ZK/pyzk path, connection fails | Always pass `brand=device.get("brand", "essl")` at every call site |
| Sending EnableDevice(0) before Morx read | Device stays locked until TCP timeout (~30–60 s) | Never lock; call `_unlock()` (EnableDevice(1) on fresh connection) after each read |
| Empty Name column for Morx users | `code_mappings` table is empty — no staff mapped yet | Map staff in School Insights → Staff tab → Sync; names populate automatically |
| Python 3.14 + pyinstaller 6.6.0 | Build fails — package incompatible | Use pyinstaller 6.20.0 and Pillow 12.2.0 |
