import requests
import hashlib
import json
import uuid
import platform
import sys
from datetime import datetime, date
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


def get_client_device_id():
    return _get_device_id()


def _command_targets_this_client(command):
    if not isinstance(command, dict):
        return False
    return str(command.get("device_id") or "").strip() == _get_device_id()


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


def _detail(data):
    if isinstance(data, dict) and "detail" in data:
        return data["detail"]
    return data


def _json_or_text(response):
    try:
        return response.json()
    except Exception:
        return response.text[:200]


def _normalize_command_list(data):
    payload = _detail(data)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        commands = payload.get("commands")
        if isinstance(commands, list):
            return commands
    return []


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


# ── Device Heartbeat / Server Commands ───────────────────────────────────────

def post_heartbeat(device_reachable: bool, records_today: int = 0):
    """POST /biometric/device/heartbeat/ — report client/device liveness.

    This is deliberately best-effort. Callers should ignore failures so the
    attendance poll loop keeps running when the server is unreachable.
    """
    if not is_device_approved():
        return False, "Device not approved"
    payload = {
        "device_status": "online",
        "biometric_device_reachable": bool(device_reachable),
        "records_today": int(records_today or 0),
        "last_pull_at": datetime.now().isoformat(),
    }
    try:
        r = requests.post(
            f"{BASE_URL}/biometric/device/heartbeat/",
            json=payload,
            headers=_headers(),
            timeout=5,
        )
        if r.status_code in (200, 204):
            return True, "OK"
        return False, f"Error {r.status_code}: {_json_or_text(r)}"
    except Exception as e:
        return False, str(e)


def fetch_pending_commands():
    """GET /biometric/commands/pending/ — polling fallback for server commands."""
    if not is_device_approved():
        return []
    try:
        r = requests.get(
            f"{BASE_URL}/biometric/commands/pending/",
            headers=_headers(),
            timeout=10,
        )
        if r.status_code == 200:
            return [
                command
                for command in _normalize_command_list(r.json())
                if _command_targets_this_client(command)
            ]
    except Exception:
        pass
    return []


def complete_command(command_id, status, result=None):
    """POST /biometric/commands/<id>/complete/."""
    if not command_id:
        return False, "command_id is required"
    try:
        r = requests.post(
            f"{BASE_URL}/biometric/commands/{command_id}/complete/",
            json={"status": status, "result": result or {}},
            headers=_headers(),
            timeout=10,
        )
        if r.status_code in (200, 201):
            return True, "OK"
        return False, f"Error {r.status_code}: {_json_or_text(r)}"
    except Exception as e:
        return False, str(e)


def post_reconcile_result(command_id, result):
    """POST /biometric/commands/<id>/reconcile-result/."""
    try:
        r = requests.post(
            f"{BASE_URL}/biometric/commands/{command_id}/reconcile-result/",
            json=result or {},
            headers=_headers(),
            timeout=15,
        )
        if r.status_code in (200, 201):
            return True, "OK"
        return False, f"Error {r.status_code}: {_json_or_text(r)}"
    except Exception as e:
        return False, str(e)


def post_verify_result(command_id, result):
    """POST /biometric/commands/<id>/verify-result/."""
    try:
        r = requests.post(
            f"{BASE_URL}/biometric/commands/{command_id}/verify-result/",
            json=result or {},
            headers=_headers(),
            timeout=15,
        )
        if r.status_code in (200, 201):
            return True, "OK"
        return False, f"Error {r.status_code}: {_json_or_text(r)}"
    except Exception as e:
        return False, str(e)


def listen_command_stream(command_queue, stop_event, log_callback=None):
    """Listen to GET /biometric/device/stream/ and enqueue command events.

    The scheduler drains command_queue and executes commands serially. If SSE
    disconnects, this function reconnects with bounded backoff; the scheduler's
    polling fallback continues to work independently.
    """
    backoff = 10

    def log(msg):
        if log_callback:
            log_callback(msg)

    while not stop_event.is_set():
        if not is_device_approved():
            stop_event.wait(10)
            continue

        try:
            with requests.get(
                f"{BASE_URL}/biometric/device/stream/",
                headers=_headers(),
                stream=True,
                timeout=(10, None),
            ) as response:
                response.raise_for_status()
                backoff = 10
                log("[SSE] Connected to command stream")

                event_name = None
                data_lines = []
                for raw_line in response.iter_lines(decode_unicode=True):
                    if stop_event.is_set():
                        break
                    if raw_line is None:
                        continue
                    line = raw_line.strip()
                    if not line:
                        if event_name == "command" and data_lines:
                            try:
                                command = json.loads("\n".join(data_lines))
                                if _command_targets_this_client(command):
                                    command_queue.put(command)
                                    log(f"[SSE] Command received: {command.get('command_type')}")
                                else:
                                    log(
                                        "[SSE] Ignored command for device "
                                        f"{command.get('device_id')}; this client is {_get_device_id()}"
                                    )
                            except Exception as exc:
                                log(f"[SSE] Invalid command payload: {exc}")
                        event_name = None
                        data_lines = []
                        continue
                    if line.startswith(":"):
                        continue
                    if line.startswith("event:"):
                        event_name = line[6:].strip()
                    elif line.startswith("data:"):
                        data_lines.append(line[5:].strip())
        except Exception:
            if stop_event.is_set():
                break
            log(f"[SSE] Disconnected — reconnecting in {backoff}s")
            stop_event.wait(backoff)
            backoff = min(60, 30 if backoff == 10 else backoff * 2)


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
            payload = _detail(data)
            users = payload.get("users", payload if isinstance(payload, list) else [])
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


# ── Bulk Fallback Mark (bio_code → server resolves user_id) ─────────────────

def bulk_mark_by_biocodes(records):
    """POST /biometric/upload/direct/ — fallback bulk mark using raw bio_codes.

    The server resolves bio_code → SI user_id via StaffBiometricCode, so this
    works even when local code_mappings are stale or empty.

    records: list of dicts:
        {"bio_code": "71", "date": "2026-06-09",
         "check_in": "2026-06-09T08:30:00+05:30",   # ISO 8601
         "check_out": "2026-06-09T17:14:00+05:30"}   # or None

    Returns (ok: bool, detail: dict)
    """
    if not is_device_approved():
        return False, "Device not approved"
    school_id = db.get_setting("si_school_id", "")
    if not school_id:
        return False, "School ID not set"
    if not records:
        return True, {"created": 0, "updated": 0, "unchanged": 0,
                      "unmatched": 0, "unmatched_codes": []}
    try:
        r = requests.post(
            f"{BASE_URL}/biometric/upload/direct/",
            json={"school_id": int(school_id), "records": records},
            headers=_headers(),
            timeout=30,
        )
        if r.status_code in (200, 201):
            return True, _detail(r.json())
        return False, _detail(_json_or_text(r))
    except Exception as e:
        return False, str(e)


# ── Real-time Mark ───────────────────────────────────────────────────────────

def mark_attendance(si_user_id, date_str, check_in, check_out=None):
    """POST /staff-attendance/mark/ — single call with derived check_in/check_out.

    check_in : ISO 8601 string e.g. "2026-06-09T07:42:00+05:30"
    check_out: ISO 8601 string or None (explicitly sent as null to clear stale value)
    Returns (ok: bool, message: str)
    """
    if not is_device_approved():
        return False, "Device not approved"
    school_id = db.get_setting("si_school_id", "")
    if not school_id:
        return False, "School ID not set"
    payload = {
        "user_id": int(si_user_id),
        "school_id": int(school_id),
        "date": date_str,
        "status": "present",
        "source": "biometric_upload",
        "check_in": check_in,
        "check_out": check_out,  # None clears stale check_out on server
    }
    try:
        r = requests.post(
            f"{BASE_URL}/staff-attendance/mark/",
            json=payload,
            headers=_headers(),
            timeout=10,
        )
        if r.status_code in (200, 201):
            return True, "OK"
        data = r.json()
        return False, data.get("detail", r.text[:200])
    except Exception as e:
        return False, str(e)


def _staff_user_id(row):
    return row.get("user_id") or row.get("si_user_id") or row.get("id")


def _staff_name(row):
    return (
        row.get("name")
        or row.get("full_name")
        or row.get("si_name")
        or row.get("username")
        or ""
    )


def _time_hhmm(value):
    if value in (None, "", "—"):
        return None
    text = str(value)
    if "T" in text and len(text) >= 16:
        return text[11:16]
    if " " in text and len(text) >= 16:
        return text[11:16]
    if len(text) >= 5 and text[2] == ":":
        return text[:5]
    return None


def _minute_value(value):
    hhmm = _time_hhmm(value)
    if not hhmm:
        return None
    try:
        hours, minutes = hhmm.split(":", 1)
        return int(hours) * 60 + int(minutes)
    except Exception:
        return None


def _minutes_differ(left, right, tolerance=1):
    left_minutes = _minute_value(left)
    right_minutes = _minute_value(right)
    if left_minutes is None and right_minutes is None:
        return False
    if left_minutes is None or right_minutes is None:
        return True
    return abs(left_minutes - right_minutes) > tolerance


def _server_staff_map(staff_list):
    result = {}
    for row in staff_list or []:
        user_id = _staff_user_id(row)
        if user_id is not None:
            result[int(user_id)] = row
    return result


def build_reconciliation_report(device_users, target_date=None):
    """Build Scenario 2 reconciliation payload for the server."""
    if target_date is None:
        target_date = date.today()
    date_str = target_date.isoformat() if hasattr(target_date, "isoformat") else str(target_date)

    mappings = db.get_all_code_mappings()
    marked_today = db.get_marked_today(date_str)
    ok, staff_or_err = get_staff_list()
    server_map = _server_staff_map(staff_or_err) if ok else {}

    device_user_codes = {str(u.get("user_id")) for u in (device_users or []) if u.get("user_id") is not None}
    unmapped_device_users = sorted(code for code in device_user_codes if code not in mappings)

    staff_rows = []
    present = absent = unmarked = 0
    for bio_code, mapping in sorted(mappings.items(), key=lambda item: item[1].get("si_name", "")):
        si_user_id = int(mapping["si_user_id"])
        server_row = server_map.get(si_user_id, {})
        status = server_row.get("status")
        check_in = _time_hhmm(server_row.get("check_in"))
        check_out = _time_hhmm(server_row.get("check_out"))
        source = server_row.get("source")
        marked_any = status == "present" or bool(check_in or check_out)
        marked_bio = bio_code in marked_today

        if marked_any:
            present += 1
        elif status == "absent":
            absent += 1
        else:
            unmarked += 1

        staff_rows.append({
            "bio_code": bio_code,
            "si_name": mapping.get("si_name") or _staff_name(server_row),
            "on_device": bio_code in device_user_codes,
            "marked_biometric": marked_bio,
            "marked_any_source": marked_any,
            "check_in": check_in,
            "check_out": check_out,
            "source": source,
        })

    return {
        "date": date_str,
        "mapped_count": len(mappings),
        "device_enrolled_count": len(device_user_codes),
        "staff": staff_rows,
        "unmapped_device_users": unmapped_device_users,
        "summary": {"present": present, "absent": absent, "unmarked": unmarked},
    }


def verify_today_attendance(all_punches, target_date=None, log_callback=None):
    """Scenario 3 — full-day verify and correction pass.

    Runs _derive_daily_records() once over the full day pull, compares the
    derived check-in/out against the server state, and calls mark_attendance()
    at most once per mapped staff member.
    """
    if target_date is None:
        target_date = date.today()
    date_str = target_date.isoformat() if hasattr(target_date, "isoformat") else str(target_date)

    mappings = db.get_all_code_mappings()
    derived_records = {
        str(row["user_id"]): row
        for row in _derive_daily_records(all_punches or [])
    }

    ok, staff_or_err = get_staff_list()
    server_map = _server_staff_map(staff_or_err) if ok else {}

    corrected = []
    already_correct = 0
    no_punches = 0
    failed = 0

    def log(msg):
        if log_callback:
            log_callback(msg)

    if not ok:
        return {
            "date": date_str,
            "total_mapped": len(mappings),
            "corrected": [],
            "already_correct": 0,
            "no_punches": 0,
            "failed": len(mappings),
            "error": staff_or_err,
        }

    for bio_code, mapping in sorted(mappings.items(), key=lambda item: item[1].get("si_name", "")):
        derived = derived_records.get(str(bio_code))
        si_name = mapping.get("si_name", "")
        if not derived:
            no_punches += 1
            continue

        server_row = server_map.get(int(mapping["si_user_id"]), {})
        old_check_in = _time_hhmm(server_row.get("check_in"))
        old_check_out = _time_hhmm(server_row.get("check_out"))
        new_check_in = _time_hhmm(derived.get("check_in"))
        new_check_out = _time_hhmm(derived.get("check_out"))

        action = "no_change"
        should_mark = False
        if new_check_out and not old_check_out:
            action = "check_out_added"
            should_mark = True
        elif old_check_out and not new_check_out:
            action = "check_out_cleared"
            should_mark = True
        elif _minutes_differ(old_check_in, new_check_in):
            action = "check_in_corrected"
            should_mark = True
        elif _minutes_differ(old_check_out, new_check_out):
            # A shifted check-out (not added/cleared) is its own action so the
            # verify report does not mislabel it as a check-in correction.
            action = "check_out_corrected"
            should_mark = True

        if not should_mark:
            already_correct += 1
            continue

        mark_ok, mark_msg = mark_attendance(
            mapping["si_user_id"],
            derived["date"],
            derived["check_in"],
            derived.get("check_out"),
        )
        if mark_ok:
            db.save_marked_today(bio_code, date_str, derived.get("check_out"))
            corrected.append({
                "bio_code": bio_code,
                "si_name": si_name,
                "old_check_in": old_check_in,
                "old_check_out": old_check_out,
                "new_check_in": new_check_in,
                "new_check_out": new_check_out,
                "action": action,
            })
            log(f"[Verify] Corrected {si_name}: {action}")
        else:
            failed += 1
            log(f"[Verify] Failed {si_name}: {mark_msg}")

    return {
        "date": date_str,
        "total_mapped": len(mappings),
        "corrected": corrected,
        "already_correct": already_correct,
        "no_punches": no_punches,
        "failed": failed,
    }


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

    code_mappings = db.get_all_code_mappings()  # bio_code → {si_user_id, si_name}

    marked, unmatched, failed = 0, 0, 0
    for rec in daily_records:
        mapping = code_mappings.get(str(rec["user_id"]))
        if not mapping:
            unmatched += 1
            continue
        ok, msg = mark_attendance(
            mapping["si_user_id"],
            rec["date"],
            rec["check_in"],
            rec["check_out"],
        )
        if ok:
            marked += 1
        else:
            failed += 1

    total = len(daily_records)
    parts = [f"{marked} marked"]
    if unmatched:
        parts.append(f"{unmatched} unmapped (assign codes in Staff tab)")
    if failed:
        parts.append(f"{failed} failed")
    msg = f"Uploaded {marked}/{total} records. " + ", ".join(parts)
    return True, msg.strip(), marked
