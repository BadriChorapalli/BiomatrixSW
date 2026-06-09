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

1. Copy `BiomatrixSync.exe` to any folder on the PC (e.g. `C:\BiomatrixSync\`).
2. Double-click `BiomatrixSync.exe` to launch.
3. That's it — no Python, no installation wizard needed.

> If Windows Defender shows a warning, click **More info → Run anyway**. The app is safe; it just isn't signed with a paid certificate.

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
   - **Port** — leave as `4370` (default for all ZKTeco/eSSL devices)
   - **Password** — `0` unless your device has a specific password set
   - **Device Brand** — select your brand (eSSL, ZKTeco, Realtime, etc.)
   - **Connection Protocol** — leave as **TCP** for most devices; choose **UDP** only for very old models
4. Click **Test Connection** to verify the device is reachable.
5. Click **Save Device**.

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

## Day-to-day Use

You generally don't need to do anything. Just make sure the app is open on the PC.

- **Dashboard** — shows how many records were pulled today, each mapped staff member's status (Present/Absent), check-in and check-out time, and when the last auto-pull happened.
- **History** — browse attendance records by date, export to CSV.
- **Logs** — see exactly what the app is doing, with timestamps.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| "Failed to connect" on device test | Check the IP address and make sure the PC and device are on the same network. Try pinging the device IP. |
| Staff showing as Absent even after punching | Check if the staff member is mapped (Staff tab). Also check Logs for any "failed" mark messages. |
| App not pulling automatically | Make sure Auto Pull is enabled in Settings. Check the Logs tab for errors. |
| Registration tab shows a form after already being approved | This shouldn't happen — the form hides automatically on approval. If it does, check your internet connection and click "Check Status". |
| Forgot password | Delete the file `biomatrix.db` from the app data folder and restart. This resets everything (you'll need to redo setup). |

---

## App Data Location

The app stores its database and exported CSVs here:

- **Mac:** `~/Library/Application Support/BiomatrixSync/`
- **Windows:** `C:\Users\<YourName>\AppData\Roaming\BiomatrixSync\`

CSV exports are in the `exports/` subfolder — one file per device per date.

---

## Default Login

| Field | Value |
|---|---|
| Username | `admin` |
| Password | `admin123` |

Change this from **Settings → Change Password** after first login.
