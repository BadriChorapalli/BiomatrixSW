# BiomatrixSync — Project Context

## What this software does
BiomatrixSync is a cross-platform desktop application (Mac + Windows) built for **BellWeather** that:
1. Connects to **eSSL / ZKTeco** (ZK protocol, TCP port 4370) **or Morx BioFace-MSD1K** (SBXPC protocol, TCP port 5005) biometric attendance devices over LAN
2. Pulls daily attendance records from the device
3. Saves records as CSV to the `exports/` folder and into SQLite database
4. Registers with **School Insights** via device approval flow and uploads attendance
5. Runs a **background scheduler** that auto-syncs daily at a configured time
6. Provides login screen, registration, history viewer, and sync log viewer

## Deployment context
- Installed on **multiple Windows and Mac machines** across different schools/locations
- Each installation manages its own set of biometric devices
- Devices are on a **local LAN** — no internet required for device communication
- School Insights upload requires internet

## Supported Hardware

### eSSL / ZKTeco (and compatible: Realtime, FingerTec, Anviz, Matrix)
- **Example model:** eSSL x2008
- **Protocol:** ZKTeco SDK (ZK protocol) over **TCP port 4370**
- **Library:** `pyzk 0.9` — Python wrapper for the ZKTeco SDK
- **UDP mode:** `force_udp=True` for older device models that don't support TCP
- **Authentication:** integer password (default 0)
- **Data:** User name stored on device; attendance records have full timestamps + status codes
- **Test device:** 192.168.100.9:4370 (LAN: 192.168.100.x subnet)
- **Fingerprint algorithm:** ZKFinger VX10.0 | **Serial:** CGKK220861010
- **DHCP:** ON — IP may change; always configure per-device

### Morx BioFace-MSD1K
- **Protocol:** SBXPC (SmackBio proprietary) over **TCP port 5005**
- **Library:** None — pure Python stdlib (`socket` + `struct`). No DLL required.
- **Machine number:** Always 0 in every SBXPC packet (hardware requirement)
- **Authentication:** two-packet handshake with password embedded in packet params
- **Data:** User records are 8 bytes each — **no name field in hardware**. Names come from `code_mappings` table (synced from School Insights).
- **Log read:** Full log (all records ever) returned each pull. Filtered client-side by date/since. No incremental protocol.
- **Commands used:** Connect `79 19 52 00`, EnableDevice(1)/unlock `79 19 0c 01`, ReadAllUserID `79 19 12 01`, ReadAllGLogData `79 19 07 01`
- **EnableDevice lock:** Do NOT send EnableDevice(0) (lock) before reads. Send EnableDevice(1) (unlock) after each read via `_unlock()` helper to prevent device staying locked until TCP timeout.
- **Test device:** 192.168.13.104:5005 (BellWether main gate)

## Tech stack
| Layer | Tech |
|---|---|
| Language | Python 3.12 (Mac) / Python 3.14 (Windows build machine) |
| UI | CustomTkinter (dark theme) |
| eSSL/ZKTeco device comms | pyzk 0.9 |
| Morx device comms | stdlib `socket` + `struct` — `app/core/morx_device.py` |
| Brand routing | `device.py` dispatches on `brand` field: `_is_morx()` helper |
| Scheduling | schedule library + threading |
| Storage | SQLite (biomatrix.db) — file-based, no server needed |
| API upload | requests |
| Packaging | PyInstaller 6.20.0 → `.app` (Mac) or `.exe` (Windows) |

## Project structure
```
BiomatrixSW/
├── main.py                    # Entry point — init DB, show login, launch UI
├── requirements.txt
├── build.spec                 # PyInstaller spec — auto-detects Mac/Windows
├── build.sh                   # Mac build script → dist/BiomatrixSync.app
├── build.bat                  # Windows build script → dist/BiomatrixSync.exe
├── entitlements.plist         # macOS network entitlements (required for LAN access)
├── biomatrix.db               # SQLite database (auto-created on first run)
├── exports/                   # CSV exports: <device>_<date>.csv + JSON
├── app/
│   ├── core/
│   │   ├── database.py        # All SQLite operations
│   │   ├── device.py          # Brand router: dispatches to pyzk (eSSL) or morx_device (Morx)
│   │   ├── morx_device.py     # Morx BioFace-MSD1K — SBXPC protocol, pure Python
│   │   ├── api_client.py      # Full School Insights API integration
│   │   ├── sync.py            # Orchestrates pull → CSV → DB → upload
│   │   └── scheduler.py       # Daily background scheduler thread
│   └── ui/
│       ├── login_window.py    # Login screen (shown on app launch)
│       ├── main_window.py     # CTk root window — tabs: Dashboard, History, Devices, Registration, Settings, Logs
│       ├── dashboard_tab.py   # Device status, manual sync buttons
│       ├── history_tab.py     # Attendance history viewer by date
│       ├── devices_tab.py     # Add/edit/delete device configs (brand selector auto-sets port)
│       ├── registration_tab.py # School Insights device registration & approval flow
│       ├── settings_tab.py    # Sync time, change password
│       └── logs_tab.py        # Live log textbox + sync history viewer
```

## Database schema (SQLite — biomatrix.db)
- **devices** — id, name, ip, port, password, enabled, `brand TEXT DEFAULT 'eSSL'`, `force_udp INTEGER DEFAULT 0`
  - `brand` values: eSSL, ZKTeco, Realtime, FingerTec, Anviz, Matrix, **Morx**, Other
  - `force_udp` only applies to eSSL/ZKTeco brands (ignored for Morx)
- **settings** — key/value store (see all keys below)
- **attendance** — device_id, device_name, user_id, name, date, time, status (UNIQUE per device+user+datetime)
- **sync_logs** — device_id, status, records_pulled, records_uploaded, message, synced_at
- **code_mappings** — bio_code (device user_id as TEXT) → si_user_id, si_name. Used to fill in names for Morx records since the device has no name storage.

### Settings keys
| Key | Purpose |
|---|---|
| `auth_username` | App login username (default: admin) |
| `auth_password` | SHA-256 hashed password (default: admin123) |
| `sync_time` | Daily auto-sync time in 24h format (default: 18:00) |
| `si_device_id` | Persistent UUID for this installation |
| `si_request_id` | School Insights device approval request ID |
| `si_access_token` | JWT access token (30-day, received after approval) |
| `si_refresh_token` | JWT refresh token (365-day) |
| `si_device_status` | PENDING / APPROVED / REJECTED |
| `si_org_id` | Selected organization ID |
| `si_school_id` | Selected school ID |

## App Authentication
- Login screen shown on every app launch
- Credentials stored in `settings` table as SHA-256 hash
- Default: `admin` / `admin123`
- Password changeable from Settings tab

## School Insights API Integration

### Backend
- **Base URL:** `https://api.schoolinsights.in/api/v1`
- **App Token Secret:** `ae96a8093cab7d726766c83a6caf1460a4348a56d9ac3ef167b77e00f020436e`
- **Platform:** `macos` or `windows` (auto-detected)
- **App Version:** `1.0.0`

### Required headers (all requests)
```
X-App-Token: <APP_TOKEN_SECRET>
X-Device-Id: <si_device_id from settings>
Authorization: Bearer <si_access_token>  (only after approval)
```

### Device Registration Flow
1. `GET /face-attendance/organizations` → list orgs
2. `GET /face-attendance/schools?organization_id=<id>` → list schools
3. `POST /face-attendance/device-approval/request` → submit request, get request_id
4. `GET /face-attendance/device-approval/status/{request_id}` → poll every 10s
5. On APPROVED: save `access_token` + `refresh_token` to settings

### Device Registration Payload
```json
{
  "organization_id": 1,
  "school_id": 2,
  "device_info": {
    "device_id": "<uuid>",
    "device_name": "Main Gate Biometric",
    "location": "School Front Gate",
    "type": "biometric",
    "platform": "macos",
    "os_version": "<platform.version()>",
    "app_version": "1.0.0",
    "device_hash": "<SHA256(device_id+platform+os_version+app_version)>"
  }
}
```

### Attendance Upload
- **Endpoint:** `POST /staff-attendance/mark/`
- **Logic:** group punches by user_id → first punch = check_in, last punch = check_out
- **Source field:** `biometric_upload`
- **Payload per staff member:**
```json
{
  "user_id": 45,
  "school_id": 2,
  "date": "2026-06-08",
  "status": "present",
  "check_in": "2026-06-08T08:30:00+05:30",
  "check_out": "2026-06-08T17:30:00+05:30",
  "source": "biometric_upload",
  "remarks": "Synced from Main Gate Biometric"
}
```
- Upload only proceeds if device is APPROVED (has access_token)
- Falls back to CSV-only if not approved

## Attendance data format (from biometric device)
- `status == 0` → CHECK IN
- `status == 1` → CHECK OUT
- Most morning punches are CHECK OUT (device placed at exit gate)
- User ID 999 = Admin/test user
- Biometric `user_id` maps directly to School Insights `user_id`
- **Morx devices:** all records returned as "CHECK IN" status — direction is derived from timing clusters by `_derive_daily_records()` in `api_client.py`, same as eSSL

## Key behaviors
- Login screen shown before main window on every launch
- Scheduler starts automatically after login
- Sync time is configurable in Settings tab (default 18:00)
- Each sync: pull today's records → save CSV → save to DB → upload to School Insights
- Registration tab: select org → school → submit → auto-poll for approval
- History tab: browse attendance by date, pull from device for any date, export CSV
- Multiple devices per installation supported
- Selecting "Morx" in Devices tab auto-sets port to 5005; switching away auto-restores 4370

## Related BellWeather repos
- `school-insights/` — Django backend (staff_attendance app handles punch API)
- `school-insights-staff-attedence-app/` — Android app (same device approval flow)
- Key backend files:
  - `face_attendance/views.py` — device registration & token generation
  - `staff_attendance/views.py` — punch & mark endpoints
  - `staff_app/authentication.py` — StaffTokenAuthentication

## Build

**Mac:**
```bash
chmod +x build.sh && ./build.sh
# After build, re-apply network entitlements:
codesign --sign - --force --deep --entitlements entitlements.plist dist/BiomatrixSync.app
```

**Windows:**
```bat
build.bat
# Output: dist\BiomatrixSync.exe
```

The same `build.spec` handles both platforms automatically — detects OS at build time.

## Known issues / fixes applied
- **macOS network sandbox:** `entitlements.plist` must be re-applied after every PyInstaller build via `codesign`
- **Missing `jaraco` module:** Added as hidden import in `build.spec` to fix PyInstaller crash on launch
- **Python 3.14 (Windows build machine):** PyInstaller 6.6.0 does not support Python 3.14 — use 6.20.0. Pillow 10.3.0 also incompatible — use 12.2.0. Override after `pip install -r requirements.txt`: `pip install pyinstaller==6.20.0 Pillow==12.2.0`
- **`pystray._win32` "not found" on Mac build:** `pystray._win32` is listed as a hidden import in `build.spec` for the Windows system tray feature. On Mac this emits a build warning — harmless; the module is Windows-only and never loaded on Mac.
- **Morx SBXPC DLL (SBXPCDLL64.dll):** Original DLL has two fatal bugs (rejects mach=0, corrupts checksum). `morx_device.py` bypasses the DLL entirely with a pure Python reimplementation of the wire protocol.
- **Morx device locking:** Sending `EnableDevice(0)` before reads locks the device. The unlock command (`EnableDevice(1)`) must be sent after reads via a fresh TCP connection using `_unlock()`. Do NOT send the lock command at all.

## Windows Build — Step by Step

Run on a Windows machine (PyInstaller cannot cross-compile from Mac):

```bat
cd BiomatrixSW
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

:: Python 3.14 only — override the two incompatible versions
pip install pyinstaller==6.20.0 Pillow==12.2.0

build.bat
```

Output: `dist\BiomatrixSync.exe` — copy to target PC and run directly.

> Windows Defender SmartScreen may warn on first launch ("Windows protected your PC"). Click **More info → Run anyway**. Expected for unsigned executables.

## Pending / TODO
- [ ] Verify biometric device `user_id` matches School Insights `user_id` (mapping may be needed)
- [ ] Add missed-sync recovery (re-sync previous day if machine was off)
- [ ] Token refresh logic when access_token expires (30-day expiry)
- [ ] Populate `code_mappings` table for Morx installation so names appear in attendance records
