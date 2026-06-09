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

    def divider(label=""):
        if log_callback and hasattr(log_callback, '__self__'):
            try:
                log_callback.__self__.divider(label)
                return
            except Exception:
                pass
        log(f"─── {label} {'─' * max(1, 44 - len(label))}" if label else "─" * 50)

    while _poll_running:
        devices = [d for d in db.get_all_devices() if d["enabled"]]
        if not devices:
            log("⚠ No enabled devices configured")
        else:
            today = date.today()
            now   = datetime.datetime.now()
            approved     = is_device_approved()
            code_mappings = db.get_all_code_mappings()

            # Re-sync code mappings from SI on every cycle so newly
            # assigned bio-codes are picked up without waiting until 07:01
            from .api_client import sync_code_mappings
            try:
                m_ok, m_mapped, _ = sync_code_mappings()
                if m_ok:
                    code_mappings = db.get_all_code_mappings()
            except Exception:
                pass

            for device in devices:
                if not _poll_running:
                    return

                divider(f"Poll — {device['name']}")

                # ── Pull from device ──────────────────────────────────────
                since = last_pull.get(device["id"])
                ok, result = pull_attendance(
                    device["ip"], device["port"], device["password"], today,
                    since=since, force_udp=bool(device.get("force_udp", 0))
                )

                if not ok:
                    log(f"✗ Device offline  {device['name']} ({device['ip']})  —  {result}")
                    continue

                if result:
                    save_attendance(device["id"], device["name"], result)
                    log(f"→ Pulled  {len(result)} new records from {device['name']}")
                else:
                    log(f"→ Pulled  0 new records  (no activity since last check)")

                # ── Mark attendance ───────────────────────────────────────
                if not approved:
                    log("⚠ Marking skipped  —  device not approved in School Insights")
                elif not code_mappings:
                    log("⚠ Marking skipped  —  no staff mapped  (assign bio-codes in Staff tab)")
                else:
                    today_str          = today.isoformat()
                    mapped_codes       = set(code_mappings.keys())
                    marked_today_data  = db.get_marked_today(today_str)  # bio_code → check_out
                    marked_codes       = set(marked_today_data.keys())
                    all_today_records  = db.get_attendance_by_date(today_str, device["id"])
                    device_codes_today = set(str(r["user_id"]) for r in all_today_records)

                    matched  = mapped_codes & device_codes_today
                    no_punch = mapped_codes - device_codes_today
                    no_map   = device_codes_today - mapped_codes

                    log(f"   Staff mapped : {len(mapped_codes)}  |  "
                        f"Punched today : {len(device_codes_today)}  |  "
                        f"Matched : {len(matched)}  |  "
                        f"No punch : {len(no_punch)}")

                    if no_map:
                        log(f"⚠ {len(no_map)} device user(s) have no bio-code mapping — "
                            f"codes: {', '.join(sorted(no_map)[:8])}"
                            + (" ..." if len(no_map) > 8 else ""))

                    # Staff not marked at all today
                    missed = mapped_codes - marked_codes

                    # Staff marked earlier without checkout but now have one
                    needs_checkout = set()
                    for bio_code in mapped_codes & marked_codes:
                        if marked_today_data[bio_code] is None:  # previously no checkout
                            user_recs = [r for r in all_today_records if str(r["user_id"]) == bio_code]
                            if user_recs:
                                derived = _derive_daily_records(user_recs)
                                if derived and derived[0]["check_out"]:
                                    needs_checkout.add(bio_code)

                    to_process = missed | needs_checkout

                    if not to_process:
                        log(f"✓ All {len(mapped_codes)} mapped staff already marked with checkout — nothing to do")
                    else:
                        if missed:
                            log(f"   Checking {len(missed)} staff not yet marked today...")
                        if needs_checkout:
                            log(f"   Updating checkout for {len(needs_checkout)} staff...")

                        marked_count, no_punch_count, failed = 0, 0, 0
                        for bio_code in to_process:
                            mapping = code_mappings.get(bio_code)
                            if not mapping:
                                continue

                            user_records = [
                                r for r in all_today_records
                                if str(r["user_id"]) == bio_code
                            ]
                            if not user_records:
                                log(f"   – {mapping['si_name']:<28}  No punch on device today")
                                no_punch_count += 1
                                continue

                            derived = _derive_daily_records(user_records)
                            if not derived:
                                continue

                            rec       = derived[0]
                            check_in  = rec["check_in"]
                            check_out = rec["check_out"]

                            p_ok, p_msg = mark_attendance(
                                mapping["si_user_id"],
                                rec["date"],
                                check_in,
                                check_out,
                            )
                            ci = check_in[11:16]
                            co = check_out[11:16] if check_out else "—"
                            if p_ok:
                                db.save_marked_today(bio_code, today_str, check_out)
                                marked_count += 1
                                label = "Marked" if bio_code in missed else "Updated"
                                log(f"✓ {label}  {mapping['si_name']:<28}  IN {ci}  OUT {co}")
                            else:
                                failed += 1
                                log(f"✗ Failed  {mapping['si_name']:<28}  {p_msg}")

                        # Summary line
                        parts = []
                        if marked_count:   parts.append(f"{marked_count} marked/updated")
                        if no_punch_count: parts.append(f"{no_punch_count} no punch")
                        if failed:         parts.append(f"{failed} failed")
                        if parts:
                            log(f"   Summary : {' | '.join(parts)}")

                last_pull[device["id"]] = now
                db.set_setting("last_device_pull", now.strftime("%Y-%m-%d %H:%M:%S"))

        # Next poll countdown
        total = _current_interval()
        next_time = (datetime.datetime.now() + datetime.timedelta(seconds=total)).strftime("%H:%M:%S")
        log(f"   Next pull at {next_time}  ({total}s)")

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
