# BiomatrixSync — Project Context

## What this software does
BiomatrixSync is a cross-platform desktop application (Mac + Windows) built for **BellWeather** that:
1. Connects to **eSSL / ZKTeco biometric attendance devices** over LAN (port 4370)
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

## Hardware
- **Device model:** eSSL x2008
- **Protocol:** ZKTeco SDK over TCP port 4370
- **Fingerprint algorithm:** ZKFinger VX10.0
- **Platform:** ZLM60_TFT
- **Firmware:** Ver 8.0.4.2-20210223
- **Test device IP:** 192.168.100.9 (LAN: 192.168.100.x subnet)
- **Serial:** CGKK220861010
- **Enrolled users:** 177 staff | **Total records:** 53,973+
- **DHCP:** ON — IP may change; always configure per-device

## Tech stack
| Layer | Tech |
|---|---|
| Language | Python 3.12 |
| UI | CustomTkinter (dark theme) |
| Device comms | pyzk 0.9 |
| Scheduling | schedule library + threading |
| Storage | SQLite (biomatrix.db) — file-based, no server needed |
| API upload | requests |
| Packaging | PyInstaller → `.app` (Mac) or `.exe` (Windows) |

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
│   │   ├── device.py          # ZKTeco connect, pull_attendance()
│   │   ├── api_client.py      # Full School Insights API integration
│   │   ├── sync.py            # Orchestrates pull → CSV → DB → upload
│   │   └── scheduler.py       # Daily background scheduler thread
│   └── ui/
│       ├── login_window.py    # Login screen (shown on app launch)
│       ├── main_window.py     # CTk root window — tabs: Dashboard, History, Devices, Registration, Settings, Logs
│       ├── dashboard_tab.py   # Device status, manual sync buttons
│       ├── history_tab.py     # Attendance history viewer by date
│       ├── devices_tab.py     # Add/edit/delete device configs
│       ├── registration_tab.py # School Insights device registration & approval flow
│       ├── settings_tab.py    # Sync time, change password
│       └── logs_tab.py        # Live log textbox + sync history viewer
```

## Database schema (SQLite — biomatrix.db)
- **devices** — id, name, ip, port, password, enabled
- **settings** — key/value store (see all keys below)
- **attendance** — device_id, device_name, user_id, name, date, time, status (UNIQUE per device+user+datetime)
- **sync_logs** — device_id, status, records_pulled, records_uploaded, message, synced_at

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

## Key behaviors
- Login screen shown before main window on every launch
- Scheduler starts automatically after login
- Sync time is configurable in Settings tab (default 18:00)
- Each sync: pull today's records → save CSV → save to DB → upload to School Insights
- Registration tab: select org → school → submit → auto-poll for approval
- History tab: browse attendance by date, pull from device for any date, export CSV
- Multiple devices per installation supported

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

## Pending / TODO
- [ ] Verify biometric device `user_id` matches School Insights `user_id` (mapping may be needed)
- [ ] Add Windows Service support (NSSM) for headless background operation
- [ ] Test on Windows machine
- [ ] Add missed-sync recovery (re-sync previous day if machine was off)
- [ ] Token refresh logic when access_token expires (30-day expiry)
