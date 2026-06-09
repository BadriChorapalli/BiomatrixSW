import schedule
import threading
import time
import datetime
from datetime import date
from . import database as db
from .sync import sync_all_devices, sync_device_users_all, sync_code_mappings_job

# ── Daily upload scheduler ────────────────────────────────────────────────────

_scheduler_thread = None
_running = False


def _run_scheduler():
    global _running
    while _running:
        schedule.run_pending()
        time.sleep(30)


def setup_schedule(log_callback=None):
    schedule.clear()
    sync_time = db.get_setting("sync_time", "18:00")
    schedule.every().day.at(sync_time).do(sync_all_devices, log_callback=log_callback)
    # Every morning at 07:00 — sync device roster + pull code mappings from SI
    schedule.every().day.at("07:00").do(sync_device_users_all, log_callback=log_callback)
    schedule.every().day.at("07:01").do(sync_code_mappings_job, log_callback=log_callback)


def start(log_callback=None):
    global _scheduler_thread, _running
    if _running:
        return
    setup_schedule(log_callback)
    _running = True
    _scheduler_thread = threading.Thread(target=_run_scheduler, daemon=True)
    _scheduler_thread.start()


def stop():
    global _running
    _running = False
    schedule.clear()


def restart(log_callback=None):
    stop()
    time.sleep(1)
    start(log_callback)


# ── Auto-pull thread (device → SQLite only, no SI upload) ────────────────────

_poll_thread = None
_poll_running = False


def _current_interval():
    """Return poll interval in seconds — reads slots and default from DB every cycle."""
    now = datetime.datetime.now().strftime("%H:%M")
    for slot in db.get_poll_slots():
        if slot["start"] <= now < slot["end"]:
            return slot["interval"]
    try:
        return int(db.get_setting("auto_pull_interval", "15")) * 60
    except Exception:
        return 900


def _run_poll(interval_minutes, log_callback):
    global _poll_running
    from .device import pull_attendance
    from .database import save_attendance
    from .api_client import mark_attendance, is_device_approved, _derive_daily_records

    def log(msg):
        if log_callback:
            log_callback(msg)

    # Track per-device last pull time so we only fetch new records each cycle
    last_pull = {}

    while _poll_running:
        devices = [d for d in db.get_all_devices() if d["enabled"]]
        if devices:
            today = date.today()
            now = datetime.datetime.now()
            approved = is_device_approved()
            code_mappings = db.get_all_code_mappings()  # bio_code → {si_user_id, si_name}

            for device in devices:
                if not _poll_running:
                    return
                since = last_pull.get(device["id"])
                ok, result = pull_attendance(
                    device["ip"], device["port"], device["password"], today,
                    since=since, force_udp=bool(device.get("force_udp", 0))
                )
                if ok:
                    if result:
                        save_attendance(device["id"], device["name"], result)
                        log(f"[AutoPull] {device['name']}: {len(result)} new records")
                    else:
                        log(f"[AutoPull] {device['name']}: no new records")

                    if approved and code_mappings:
                        today_str = today.isoformat()
                        mapped_codes = set(code_mappings.keys())
                        marked_codes = db.get_marked_today(today_str)

                        if sorted(mapped_codes) == sorted(marked_codes):
                            log(f"[Mark] All {len(mapped_codes)} mapped staff already marked — skipping")
                        else:
                            missed = mapped_codes - marked_codes
                            log(f"[Mark] {len(marked_codes)}/{len(mapped_codes)} marked — checking {len(missed)} missed")

                            marked_count, failed = 0, 0
                            for bio_code in missed:
                                mapping = code_mappings.get(bio_code)
                                if not mapping:
                                    continue

                                # Read ALL today's punches for this user from local DB
                                all_today = [
                                    r for r in db.get_attendance_by_date(today_str, device["id"])
                                    if str(r["user_id"]) == bio_code
                                ]
                                if not all_today:
                                    continue

                                derived = _derive_daily_records(all_today)
                                if not derived:
                                    continue

                                rec = derived[0]
                                check_in  = rec["check_in"]
                                check_out = rec["check_out"]

                                p_ok, p_msg = mark_attendance(
                                    mapping["si_user_id"],
                                    rec["date"],
                                    check_in,
                                    check_out,
                                )
                                if p_ok:
                                    db.save_marked_today(bio_code, today_str)
                                    marked_count += 1
                                    co = check_out[11:16] if check_out else "—"
                                    log(f"[Mark] {mapping['si_name']}: in={check_in[11:16]} out={co}")
                                else:
                                    failed += 1
                                    log(f"[Mark] {mapping['si_name']}: {p_msg}")

                            if marked_count or failed:
                                parts = [f"{marked_count} marked"]
                                if failed: parts.append(f"{failed} failed")
                                log(f"[Mark] {device['name']}: {', '.join(parts)}")

                    last_pull[device["id"]] = now
                    db.set_setting("last_device_pull", now.strftime("%Y-%m-%d %H:%M:%S"))
                else:
                    log(f"[AutoPull] {device['name']}: Failed — {result}")
        else:
            log("[AutoPull] No enabled devices — skipping")

        # Sleep in 5-second chunks so stop_device_poll() reacts quickly.
        # Interval is re-read from time slots on every cycle.
        total = _current_interval()
        elapsed = 0
        while elapsed < total and _poll_running:
            time.sleep(5)
            elapsed += 5


def start_device_poll(interval_minutes=5, log_callback=None):
    global _poll_thread, _poll_running
    if _poll_running:
        return
    _poll_running = True
    _poll_thread = threading.Thread(
        target=_run_poll,
        args=(interval_minutes, log_callback),
        daemon=True,
    )
    _poll_thread.start()


def stop_device_poll():
    global _poll_running
    _poll_running = False


def restart_device_poll(interval_minutes=5, log_callback=None):
    stop_device_poll()
    time.sleep(0.5)
    start_device_poll(interval_minutes, log_callback)
