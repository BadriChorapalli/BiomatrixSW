import requests
import hashlib
import uuid
import platform
import sys
from . import database as db

BASE_URL = "https://api.schoolinsights.in"
FACE_URL = f"{BASE_URL}/face-attendance/v1"
ATTENDANCE_URL = f"{BASE_URL}/staff-attendance"
APP_TOKEN_SECRET = "ae96a8093cab7d726766c83a6caf1460a4348a56d9ac3ef167b77e00f020436e"
APP_VERSION = "1.0.0"
PLATFORM = "windows" if sys.platform == "win32" else "windows"


def _get_device_id():
    device_id = db.get_setting("si_device_id")
    if not device_id:
        device_id = str(uuid.uuid4())
        db.set_setting("si_device_id", device_id)
    return device_id


def _os_version():
    v = platform.mac_ver()[0] or platform.release()
    return v[:20]


def _device_hash(device_id):
    raw = f"{device_id}{PLATFORM}{_os_version()}{APP_VERSION}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _headers(with_auth=True):
    headers = {
        "X-App-Token": APP_TOKEN_SECRET,
        "X-Device-Id": _get_device_id(),
        "Content-Type": "application/json",
    }
    if with_auth:
        token = db.get_setting("si_access_token", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
    return headers


# ── Device Registration ──────────────────────────────────────────────────────

def get_organizations():
    try:
        r = requests.get(f"{FACE_URL}/face-attendance/organizations",
                         headers=_headers(with_auth=False), timeout=15)
        if r.status_code == 200:
            return True, r.json()
        return False, f"Error {r.status_code}: {r.text[:200]}"
    except Exception as e:
        return False, str(e)


def get_schools(org_id):
    try:
        r = requests.get(f"{FACE_URL}/face-attendance/schools",
                         params={"organization_id": org_id},
                         headers=_headers(with_auth=False), timeout=15)
        if r.status_code == 200:
            return True, r.json()
        return False, f"Error {r.status_code}: {r.text[:200]}"
    except Exception as e:
        return False, str(e)


def submit_device_request(org_id, school_id, device_name, location):
    device_id = _get_device_id()
    payload = {
        "organization_id": int(org_id),
        "school_id": int(school_id),
        "device_info": {
            "device_id": device_id,
            "device_name": device_name,
            "location": location,
            "type": "biometric",
            "platform": PLATFORM,
            "os_version": _os_version(),
            "app_version": APP_VERSION,
            "device_hash": _device_hash(device_id),
        }
    }
    try:
        r = requests.post(f"{FACE_URL}/face-attendance/device-approval/request",
                          json=payload, headers=_headers(with_auth=False), timeout=15)
        if r.status_code in (200, 201):
            data = r.json()
            request_id = data.get("request_id", "")
            db.set_setting("si_request_id", request_id)
            db.set_setting("si_device_status", "PENDING")
            db.set_setting("si_org_id", str(org_id))
            db.set_setting("si_school_id", str(school_id))
            return True, request_id
        if r.status_code == 409:
            # Already has a pending request — recover the existing request_id
            data = r.json()
            request_id = data.get("request_id", db.get_setting("si_request_id", ""))
            if request_id:
                db.set_setting("si_request_id", request_id)
                db.set_setting("si_device_status", "PENDING")
                db.set_setting("si_org_id", str(org_id))
                db.set_setting("si_school_id", str(school_id))
                return True, request_id
        return False, f"Error {r.status_code}: {r.json().get('error', r.text[:200])}"
    except Exception as e:
        return False, str(e)


def check_approval_status(request_id=None):
    if not request_id:
        request_id = db.get_setting("si_request_id", "")
    if not request_id:
        return False, "No request ID found."
    try:
        r = requests.get(f"{FACE_URL}/face-attendance/device-approval/status/{request_id}",
                         headers=_headers(with_auth=False), timeout=15)
        if r.status_code == 200:
            data = r.json()
            status = data.get("status", "PENDING")
            db.set_setting("si_device_status", status)
            if status == "APPROVED":
                db.set_setting("si_access_token", data.get("access_token", ""))
                db.set_setting("si_refresh_token", data.get("refresh_token", ""))
            return True, data
        return False, f"Error {r.status_code}: {r.text[:200]}"
    except Exception as e:
        return False, str(e)


def is_device_approved():
    return db.get_setting("si_device_status") == "APPROVED" and bool(db.get_setting("si_access_token"))


# ── Staff Data ───────────────────────────────────────────────────────────────

def get_staff_list(school_id=None):
    if not school_id:
        school_id = db.get_setting("si_school_id", "")
    if not school_id:
        return False, "School ID not set. Complete device registration first."
    try:
        r = requests.get(
            f"{BASE_URL}/staff-attendance/by-school/",
            params={"school_id": school_id, "date": __import__("datetime").date.today().isoformat()},
            headers=_headers(),
            timeout=15
        )
        if r.status_code == 200:
            data = r.json()
            users = data.get("users", data if isinstance(data, list) else [])
            return True, users
        return False, f"Error {r.status_code}: {r.json().get('error', r.text[:200])}"
    except Exception as e:
        return False, str(e)


# ── Device Configuration (School Insights BiometricDevice) ───────────────────

def get_device_config(school_id=None):
    """GET /biometric/devices/{school_id}/ — load the SI biometric device config."""
    if not school_id:
        school_id = db.get_setting("si_school_id", "")
    if not school_id:
        return False, "School ID not set. Complete device registration first."
    try:
        r = requests.get(
            f"{BASE_URL}/biometric/devices/{school_id}/",
            headers=_headers(),
            timeout=15,
        )
        if r.status_code == 200:
            return True, r.json().get("detail", r.json())
        return False, f"Error {r.status_code}: {r.text[:200]}"
    except Exception as e:
        return False, str(e)


def save_device_config(config, school_id=None):
    """PUT /biometric/devices/{school_id}/ — upsert the SI biometric device config."""
    if not school_id:
        school_id = db.get_setting("si_school_id", "")
    if not school_id:
        return False, "School ID not set. Complete device registration first."
    try:
        r = requests.put(
            f"{BASE_URL}/biometric/devices/{school_id}/",
            json=config,
            headers=_headers(),
            timeout=15,
        )
        if r.status_code == 200:
            return True, r.json().get("detail", {})
        data = r.json()
        return False, data.get("detail", r.text[:200])
    except Exception as e:
        return False, str(e)


# ── Biometric Code Mapping ────────────────────────────────────────────────────

def get_biometric_codes(school_id=None):
    """GET /biometric/codes/ — staff list with their assigned biometric codes."""
    if not school_id:
        school_id = db.get_setting("si_school_id", "")
    if not school_id:
        return False, "School ID not set. Complete device registration first."
    try:
        r = requests.get(
            f"{BASE_URL}/biometric/codes/",
            params={"school_id": school_id},
            headers=_headers(),
            timeout=15,
        )
        if r.status_code == 200:
            data = r.json()
            detail = data.get("detail", data)
            return True, detail.get("staff", detail if isinstance(detail, list) else [])
        return False, f"Error {r.status_code}: {r.text[:200]}"
    except Exception as e:
        return False, str(e)


def assign_biometric_code(user_id, biometric_code, school_id=None):
    """POST /biometric/codes/assign/ — assign a device EmpCode to a staff member."""
    if not school_id:
        school_id = db.get_setting("si_school_id", "")
    if not school_id:
        return False, "School ID not set."
    try:
        r = requests.post(
            f"{BASE_URL}/biometric/codes/assign/",
            json={"user_id": int(user_id), "school_id": int(school_id), "biometric_code": str(biometric_code)},
            headers=_headers(),
            timeout=15,
        )
        if r.status_code in (200, 201):
            return True, r.json().get("detail", {})
        data = r.json()
        return False, data.get("detail", r.text[:200])
    except Exception as e:
        return False, str(e)


def update_biometric_code(code_id, biometric_code):
    """PUT /biometric/codes/{id}/ — update an existing biometric code mapping."""
    try:
        r = requests.put(
            f"{BASE_URL}/biometric/codes/{code_id}/",
            json={"biometric_code": str(biometric_code)},
            headers=_headers(),
            timeout=15,
        )
        if r.status_code == 200:
            return True, r.json().get("detail", {})
        data = r.json()
        return False, data.get("detail", r.text[:200])
    except Exception as e:
        return False, str(e)


# ── Device User Sync ────────────────────────────────────────────────────────

def sync_code_mappings(school_id=None):
    """Pull StaffBiometricCode mapping from SI and store locally.

    Fetches GET /biometric/codes/ and saves bio_code → {si_user_id, si_name}
    into the local code_mappings table so the History tab can show SI names.
    """
    if not is_device_approved():
        return False, "Device not approved.", 0
    ok, staff = get_biometric_codes(school_id)
    if not ok:
        return False, staff, 0
    mappings = [
        {"bio_code": s["biometric_code"], "si_user_id": s["user_id"], "si_name": s["full_name"]}
        for s in staff
        if s.get("is_mapped") and s.get("biometric_code")
    ]
    db.save_code_mappings(mappings)
    return True, len(mappings), len(staff) - len(mappings)


def sync_device_users(users, school_id=None):
    """POST /biometric/device-users/sync/ — bulk-sync device enrolled users.

    `users` is a list of dicts from get_device_users(): {user_id, name, ...}
    Server deduplicates by (school, device_code) so sending all users every
    time is safe — existing ones are skipped, only new ones are created.
    """
    if not is_device_approved():
        return False, "Device not approved.", 0
    if not school_id:
        school_id = db.get_setting("si_school_id", "")
    if not school_id:
        return False, "School ID not set.", 0

    payload = [{"code": str(u["user_id"]), "name": u["name"]} for u in users]
    try:
        r = requests.post(
            f"{BASE_URL}/biometric/device-users/sync/",
            json={"school_id": int(school_id), "users": payload},
            headers=_headers(),
            timeout=30,
        )
        if r.status_code == 200:
            data = r.json().get("detail", {})
            return True, data.get("created", 0), data.get("skipped", 0)
        return False, f"Error {r.status_code}: {r.json().get('detail', r.text[:200])}", 0
    except Exception as e:
        return False, str(e), 0


# ── Attendance Upload ────────────────────────────────────────────────────────

def _parse_time(t):
    """Parse HH:MM:SS or HH:MM string → total seconds since midnight, or None."""
    try:
        parts = str(t).split(":")
        h, m = int(parts[0]), int(parts[1])
        s = int(parts[2]) if len(parts) > 2 else 0
        return h * 3600 + m * 60 + s
    except (ValueError, IndexError, TypeError):
        return None


_CLUSTER_GAP = 2 * 60   # punches within 2 min → same tap-burst (double/triple tap)
_MIN_CHECKIN_OUT_GAP = 5 * 60  # check_out only counted when >5 min after check_in


def _cluster_punches(records):
    """Group sorted punch records into burst clusters.

    Any consecutive punches within _CLUSTER_GAP seconds of each other
    belong to the same cluster (accidental repeat taps at the same event).
    Each cluster represents one distinct device interaction.
    """
    if not records:
        return []
    clusters = [[records[0]]]
    for rec in records[1:]:
        gap = None
        prev_secs = _parse_time(clusters[-1][-1]["time"])
        curr_secs = _parse_time(rec["time"])
        if prev_secs is not None and curr_secs is not None:
            gap = curr_secs - prev_secs
        if gap is not None and gap < _CLUSTER_GAP:
            clusters[-1].append(rec)   # same burst
        else:
            clusters.append([rec])     # new event
    return clusters


def _derive_daily_records(punches):
    """Derive one attendance record per person per day from raw device punches.

    Handles common Indian biometric device problems:

    1. Status ignored — devices report all punches as CHECK OUT when users
       scan without pressing the IN/OUT button.

    2. Double/triple taps collapsed — consecutive punches within 2 minutes
       are treated as a single device interaction (one cluster).

    3. Permission breaks handled — intermediate clusters between the first
       and last event are exposed as `breaks` for display in the app.
       They do NOT affect check_in / check_out for the upload.

    Result per user:
      check_in  = FIRST punch of the FIRST cluster (earliest morning tap)
      check_out = LAST  punch of the LAST  cluster (latest evening tap),
                  but only when it is >5 minutes after check_in —
                  prevents a morning double-tap from becoming a fake check-out.
      breaks    = list of intermediate cluster events [{time, raw_count}]
                  e.g. 12:00 (left for permission) + 13:00 (returned)

    Trace — K PRAVEEN VARMA: 08:19, 08:20, 17:13, 17:14, 17:14
      clusters : [08:19, 08:20]  [17:13, 17:14, 17:14]
      check_in : 08:19   check_out : 17:14   breaks : []  ✓

    Trace — permission day: 08:30, 12:00 (left), 13:00 (back), 17:00
      clusters : [08:30]  [12:00]  [13:00]  [17:00]
      check_in : 08:30   check_out : 17:00
      breaks   : [{12:00, 1}, {13:00, 1}]  ✓

    Trace — double-tap only: 09:04:02, 09:04:04
      clusters : [09:04:02, 09:04:04]   (one cluster, gap = 2 s)
      check_in : 09:04   check_out : None  ✓
    """
    from collections import defaultdict
    user_punches = defaultdict(list)
    for p in punches:
        user_punches[p["user_id"]].append(p)

    daily = []
    for user_id, records in user_punches.items():
        records.sort(key=lambda x: x["time"])
        clusters = _cluster_punches(records)

        first_rec = clusters[0][0]      # earliest punch of first burst
        last_rec  = clusters[-1][-1]    # latest punch of last burst

        first_secs = _parse_time(first_rec["time"])
        last_secs  = _parse_time(last_rec["time"])

        has_gap = (
            first_secs is not None
            and last_secs  is not None
            and (last_secs - first_secs) >= _MIN_CHECKIN_OUT_GAP
        )

        check_in  = f"{first_rec['date']}T{first_rec['time']}+05:30"
        check_out = f"{last_rec['date']}T{last_rec['time']}+05:30" if has_gap else None

        # Intermediate clusters = permission break events (for UI display only)
        break_clusters = clusters[1:-1] if len(clusters) > 2 else []
        breaks = [
            {"time": c[0]["time"], "raw_count": len(c)}
            for c in break_clusters
        ]

        daily.append({
            "user_id":       user_id,
            "date":          first_rec["date"],
            "check_in":      check_in,
            "check_out":     check_out,
            "name":          first_rec["name"],
            "breaks":        breaks,
            "raw_count":     len(records),
            "cluster_count": len(clusters),
        })
    return daily


def upload_attendance(records, device_name):
    if not is_device_approved():
        return False, "Device not approved by School Insights. Register in the Registration tab.", 0

    school_id = db.get_setting("si_school_id", "")
    if not school_id:
        return False, "School ID not set. Complete device registration first.", 0

    daily_records = _derive_daily_records(records)
    if not daily_records:
        return True, "No records to upload.", 0

    # Build payload for the direct push endpoint.
    # bio_code = device user_id (EmpCode); must match StaffBiometricCode on the server.
    push_records = [
        {
            "bio_code": str(rec["user_id"]),
            "date": rec["date"],
            "check_in": rec["check_in"].split("T")[1][:5] if rec.get("check_in") else None,
            "check_out": rec["check_out"].split("T")[1][:5] if rec.get("check_out") else None,
        }
        for rec in daily_records
    ]

    try:
        r = requests.post(
            f"{BASE_URL}/biometric/upload/direct/",
            json={"school_id": int(school_id), "records": push_records},
            headers=_headers(),
            timeout=30,
        )
        if r.status_code == 200:
            data = r.json().get("detail", {})
            created = data.get("created", 0)
            updated = data.get("updated", 0)
            unmatched = data.get("unmatched", 0)
            total = len(push_records)
            parts = []
            if created:
                parts.append(f"{created} new")
            if updated:
                parts.append(f"{updated} updated")
            if unmatched:
                parts.append(f"{unmatched} unmatched (assign codes in Mapping tab)")
            msg = f"Uploaded {created + updated}/{total} records. " + (", ".join(parts) if parts else "")
            return True, msg.strip(), created + updated
        data = r.json()
        return False, f"Upload failed ({r.status_code}): {data.get('detail', r.text[:200])}", 0
    except Exception as e:
        return False, f"Upload error: {str(e)}", 0
