# BiomatrixSync

BiomatrixSync connects your school's biometric attendance machine to the **School Insights** platform automatically. Once set up, it silently runs in the background — pulling attendance punches from the device every few minutes and marking staff present on the School Insights dashboard in real time.

---

## What it does (plain English)

1. Your staff tap their finger on the biometric machine at the gate.
2. BiomatrixSync reads those taps every 1–2 minutes (or whatever interval you configure).
3. It figures out who came in and at what time, then sends that information to School Insights.
4. The School Insights dashboard shows each staff member as **Present** with their check-in (and check-out) time.

You do not need to do anything manually after the initial setup.

---

## System Requirements

| | Minimum |
|---|---|
| Windows | Windows 10 or 11 (64-bit) |
| Mac | macOS 11 Big Sur or later (Intel or Apple Silicon) |
| Network | Same LAN as the biometric device |
| Internet | Required for School Insights sync |

---

## Installation

### On Windows

1. Copy the entire folder containing `BiomatrixSync.exe`, `BiomatrixSyncService.exe`, `install_service.bat`, and `uninstall_service.bat` to the PC (e.g. `C:\BiomatrixSync\`).
2. Double-click `BiomatrixSync.exe` to launch the GUI app.
3. That's it — no Python, no installation wizard needed.

> If Windows Defender shows a warning, click **More info → Run anyway**. The app is safe; it just isn't signed with a paid certificate.

**Optional: Run as a Windows Service (recommended for school PCs)**

Installing as a Windows Service means the app runs in the background automatically at boot — even before anyone logs in. See [Running as a Windows Service](#running-as-a-windows-service-windows-only) below.

### On Mac

1. Copy `BiomatrixSync.app` to your Applications folder.
2. Double-click to open.
3. If macOS says "cannot be opened because it is from an unidentified developer", go to  
   **System Settings → Privacy & Security → scroll down → click Open Anyway**.

---

## First-Time Setup (5 steps)

### Step 1 — Log in
- Username: `admin`
- Password: `admin123`

Change the password immediately from the **Settings** tab after login.

### Step 2 — Add your biometric device
1. Go to the **Devices** tab.
2. Click **+ Add New Device**.
3. Fill in:
   - **Device Name** — anything you like, e.g. "Main Gate"
   - **IP Address** — the IP of the biometric machine on your LAN (e.g. `192.168.100.9`)
   - **Device Brand** — select your brand from the list below. The Port field auto-fills when you choose.
   - **Port** — filled automatically based on brand (see table below). Change only if your device uses a non-standard port.
   - **Password** — `0` unless your device has a specific password set
   - **Connection Protocol** — leave as **TCP** for most devices; choose **UDP** only for very old eSSL/ZKTeco models
4. Click **Test Connection** to verify the device is reachable.
5. Click **Save Device**.

**Supported brands and default ports:**

| Brand | Default Port | Notes |
|---|---|---|
| eSSL | 4370 | ZKTeco-compatible devices |
| ZKTeco | 4370 | |
| Realtime | 4370 | ZKTeco-compatible |
| FingerTec | 4370 | ZKTeco-compatible |
| Anviz | 4370 | ZKTeco-compatible |
| Matrix | 4370 | ZKTeco-compatible |
| **Morx** | **5005** | Morx BioFace-MSD1K — port auto-fills when you select this brand |
| Other | 4370 | |

> **Morx BioFace-MSD1K:** When you select **Morx** as the brand, the Port field automatically changes to `5005`. This device uses a different communication protocol (SBXPC) and must use port 5005. Staff names on Morx devices are not stored in the hardware — they will appear in the app once you complete Step 4 (Map staff to biometric codes).

### Step 3 — Register with School Insights
1. Go to the **Registration** tab.
2. Click **Load** to fetch the list of organisations.
3. Select your organisation, then select your school.
4. Enter a device name (e.g. "Main Gate Biometric") and location (e.g. "School Front Gate").
5. Click **Submit Registration Request**.
6. Ask your School Insights administrator to **approve** the device from the admin panel.
7. The app will automatically detect approval and turn the banner green.

### Step 4 — Map staff to biometric codes
1. Go to the **Staff** tab.
2. Click **Sync from School Insights** to load the staff list.
3. For each staff member, enter their biometric enrollment number (the ID on the device) and click **Assign**.

> If you are not sure what the enrollment number is, go to **History → Pull from Device** for today's date and look at the user IDs in the records.

### Step 5 — Enable auto-pull
1. Go to **Settings**.
2. Turn on **Auto Pull**.
3. Set pull intervals per time slot — for example:
   - 7:00–8:00 → every 2 minutes
   - 8:00–8:25 → every 1 minute
   - 8:25–8:35 → every 30 seconds
   - Outside slots → every 15 minutes (default)
4. Click **Save**.

The app will now run automatically. You can minimise the window — it keeps working in the background.

---

## Running as a Windows Service (Windows only)

By default the app runs as a normal desktop program — it must be open (or minimised to the tray) to work. Installing it as a **Windows Service** removes that requirement: the background sync starts at boot and keeps running even when no user is logged in.

### Files needed

| File | Purpose |
|---|---|
| `BiomatrixSyncService.exe` | Headless service (no window) |
| `install_service.bat` | Installs and starts the service |
| `uninstall_service.bat` | Stops and removes the service |

### Install

1. Right-click `install_service.bat` → **Run as administrator**.
2. The script installs the service, sets it to start automatically at boot, and starts it immediately.
3. You can confirm it is running with:
   ```
   sc query BiomatrixSync
   ```

### Uninstall

Right-click `uninstall_service.bat` → **Run as administrator**.

### Service logs

When running as a service, all activity is logged to:
```
C:\ProgramData\BiomatrixSync\service.log
```

### Using the GUI alongside the service

You can still open `BiomatrixSync.exe` at any time to view the dashboard, history, and logs — it reads from the same database. The GUI and the service do not conflict.

---

## Day-to-day Use

You generally don't need to do anything. Just make sure the app is open on the PC.

- **Dashboard** — shows how many records were pulled today, each mapped staff member's status (Present/Absent), check-in and check-out time, and when the last auto-pull happened.
- **History** — browse attendance records by date, export to CSV.
- **Logs** — see exactly what the app is doing, with timestamps.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| "Failed to connect" on device test | Check the IP address and make sure the PC and device are on the same network. Try pinging the device IP. For Morx devices, confirm port is `5005`. |
| Staff showing as Absent even after punching | Check if the staff member is mapped (Staff tab). Also check Logs for any "failed" mark messages. |
| App not pulling automatically | Make sure Auto Pull is enabled in Settings. Check the Logs tab for errors. |
| Registration tab shows a form after already being approved | This shouldn't happen — the form hides automatically on approval. If it does, check your internet connection and click "Check Status". |
| Forgot password | Delete the file `biomatrix.db` from the app data folder and restart. This resets everything (you'll need to redo setup). |
| Windows Service won't start | Run `install_service.bat` as Administrator. Check `C:\ProgramData\BiomatrixSync\service.log` for error details. |
| Service installed but attendance not syncing | Open `BiomatrixSync.exe` and check the Logs tab. Make sure devices are configured and the device is approved in School Insights. |
| Names showing blank in attendance records (Morx devices) | Morx hardware does not store staff names. Names come from the staff mapping in School Insights. Go to the **Staff** tab → **Sync from School Insights**, then assign biometric codes to each staff member. |

---

## App Data Location

The app stores its database and exported CSVs here:

- **Mac:** `~/Library/Application Support/BiomatrixSync/`
- **Windows:** `C:\ProgramData\BiomatrixSync\`

CSV exports are in the `exports/` subfolder — one file per device per date.

> **Upgrading from an older version on Windows?** The database was previously stored in `C:\Users\<YourName>\AppData\Roaming\BiomatrixSync\`. On first launch after updating, the app automatically copies your existing data to the new location — no manual steps needed.

---

## Default Login

| Field | Value |
|---|---|
| Username | `admin` |
| Password | `admin123` |

Change this from **Settings → Change Password** after first login.
