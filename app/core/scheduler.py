import schedule
import threading
import time
import datetime
import queue
import collections
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
_command_queue = queue.Queue()
_sse_thread = None
_sse_stop_event = None
# De-dup ledger so a command delivered by both SSE and the polling fallback runs
# once. Bounded so a process that stays up for weeks does not leak memory — old
# ids are safe to forget because the server never re-delivers a command that has
# left 'pending'.
_processed_command_ids = set()
_processed_command_order = collections.deque()
_PROCESSED_COMMAND_CAP = 2000


def _remember_command_id(command_id):
    """Record an executed command id, evicting the oldest beyond the cap."""
    if not command_id or command_id in _processed_command_ids:
        return
    _processed_command_ids.add(command_id)
    _processed_command_order.append(command_id)
    while len(_processed_command_order) > _PROCESSED_COMMAND_CAP:
        _processed_command_ids.discard(_processed_command_order.popleft())


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


def _log(log_callback, msg):
    if log_callback:
        log_callback(msg)


def _post_heartbeat(log_callback, reachable, records_today):
    from .api_client import post_heartbeat
    try:
        ok, _msg = post_heartbeat(reachable, records_today)
        if ok:
            _log(log_callback, f"[Heartbeat] device=online reachable={reachable} records={records_today}")
    except Exception:
        pass


def _count_records_today(today_str, device_id=None):
    try:
        return len(db.get_attendance_by_date(today_str, device_id))
    except Exception:
        return 0


def _mark_records_for_device(device, today, records, log_callback):
    from .api_client import mark_attendance, is_device_approved, _derive_daily_records

    today_str = today.isoformat()
    approved = is_device_approved()
    code_mappings = db.get_all_code_mappings()
    result = {
        "device": device["name"],
        "pulled": len(records or []),
        "marked": 0,
        "updated": 0,
        "no_punch": 0,
        "failed": 0,
        "skipped": False,
    }

    if not approved:
        result["skipped"] = True
        result["message"] = "Device not approved in School Insights"
        return result
    if not code_mappings:
        result["skipped"] = True
        result["message"] = "No staff mapped"
        return result

    mapped_codes = set(code_mappings.keys())
    marked_today_data = db.get_marked_today(today_str)
    marked_codes = set(marked_today_data.keys())
    all_today_records = db.get_attendance_by_date(today_str, device["id"])

    missed = mapped_codes - marked_codes
    needs_checkout = set()
    for bio_code in mapped_codes & marked_codes:
        if marked_today_data[bio_code] is None:
            user_recs = [r for r in all_today_records if str(r["user_id"]) == bio_code]
            if user_recs:
                derived = _derive_daily_records(user_recs)
                if derived and derived[0]["check_out"]:
                    needs_checkout.add(bio_code)

    for bio_code in missed | needs_checkout:
        mapping = code_mappings.get(bio_code)
        if not mapping:
            continue
        user_records = [r for r in all_today_records if str(r["user_id"]) == bio_code]
        if not user_records:
            result["no_punch"] += 1
            continue
        derived = _derive_daily_records(user_records)
        if not derived:
            continue
        rec = derived[0]
        ok, msg = mark_attendance(
            mapping["si_user_id"],
            rec["date"],
            rec["check_in"],
            rec["check_out"],
        )
        if ok:
            db.save_marked_today(bio_code, today_str, rec["check_out"])
            if bio_code in missed:
                result["marked"] += 1
            else:
                result["updated"] += 1
            ci = rec["check_in"][11:16]
            co = rec["check_out"][11:16] if rec["check_out"] else "-"
            _log(log_callback, f"[Command] Marked {mapping['si_name']} IN {ci} OUT {co}")
        else:
            result["failed"] += 1
            _log(log_callback, f"[Command] Failed {mapping['si_name']}: {msg}")

    return result


def _command_id(command):
    return command.get("id") or command.get("command_id")


def _enabled_devices():
    return [d for d in db.get_all_devices() if d["enabled"]]


def _execute_sync_now(log_callback, last_pull):
    from .device import pull_attendance
    from .database import save_attendance

    today = date.today()
    device_results = []
    for device in _enabled_devices():
        since = last_pull.get(device["id"])
        ok, pulled = pull_attendance(
            device["ip"], device["port"], device["password"], today,
            since=since, force_udp=bool(device.get("force_udp", 0))
        )
        if not ok:
            _log(log_callback, f"[Command] sync_now: {device['name']} offline: {pulled}")
            _post_heartbeat(log_callback, False, 0)
            device_results.append({"device": device["name"], "ok": False, "error": str(pulled)})
            continue

        if pulled:
            save_attendance(device["id"], device["name"], pulled)
        records_today = _count_records_today(today.isoformat(), device["id"])
        _post_heartbeat(log_callback, True, records_today)
        mark_result = _mark_records_for_device(device, today, pulled, log_callback)
        mark_result["ok"] = True
        device_results.append(mark_result)
        last_pull[device["id"]] = datetime.datetime.now()

    return {"devices": device_results}


def _execute_reconcile(log_callback):
    from .device import get_device_users
    from .api_client import build_reconciliation_report

    all_users = {}
    device_results = []
    for device in _enabled_devices():
        ok, users_or_err = get_device_users(
            device["ip"], device["port"], device["password"],
            force_udp=bool(device.get("force_udp", 0))
        )
        if ok:
            for user in users_or_err:
                all_users[str(user["user_id"])] = user
            device_results.append({"device": device["name"], "ok": True, "users": len(users_or_err)})
        else:
            device_results.append({"device": device["name"], "ok": False, "error": str(users_or_err)})
            _log(log_callback, f"[Reconcile] {device['name']} failed: {users_or_err}")

    report = build_reconciliation_report(list(all_users.values()), date.today())
    report["device_results"] = device_results
    summary = report["summary"]
    _log(
        log_callback,
        f"[Reconcile] {report['mapped_count']} mapped | "
        f"{sum(1 for row in report['staff'] if row['marked_biometric'])} marked (bio) | "
        f"{summary['present']} marked (any) | "
        f"{report['device_enrolled_count']} on device | "
        f"{len(report['unmapped_device_users'])} unmapped"
    )
    return report


def _execute_verify_today(log_callback):
    from .device import pull_attendance
    from .database import save_attendance
    from .api_client import verify_today_attendance

    today = date.today()
    all_records = []
    device_results = []
    for device in _enabled_devices():
        ok, pulled = pull_attendance(
            device["ip"], device["port"], device["password"], today,
            since=None, force_udp=bool(device.get("force_udp", 0))
        )
        if ok:
            if pulled:
                save_attendance(device["id"], device["name"], pulled)
            all_records.extend(pulled)
            device_results.append({"device": device["name"], "ok": True, "records": len(pulled)})
        else:
            device_results.append({"device": device["name"], "ok": False, "error": str(pulled)})
            _log(log_callback, f"[Verify] {device['name']} failed: {pulled}")

    result = verify_today_attendance(all_records, today, log_callback=log_callback)
    result["device_results"] = device_results
    _log(
        log_callback,
        f"[Verify] corrected={len(result['corrected'])} "
        f"already_correct={result['already_correct']} "
        f"no_punches={result['no_punches']} failed={result['failed']}"
    )
    return result


def _execute_get_status(log_callback):
    from .device import test_connection

    today_str = date.today().isoformat()
    devices = []
    total_records = 0
    any_reachable = False
    for device in _enabled_devices():
        reachable, msg = test_connection(
            device["ip"], device["port"], device["password"],
            force_udp=bool(device.get("force_udp", 0))
        )
        records_today = _count_records_today(today_str, device["id"])
        total_records += records_today
        any_reachable = any_reachable or reachable
        devices.append({
            "device": device["name"],
            "ip": device["ip"],
            "reachable": reachable,
            "message": msg,
            "records_today": records_today,
        })

    _post_heartbeat(log_callback, any_reachable, total_records)
    return {
        "device_status": "online",
        "biometric_device_reachable": any_reachable,
        "records_today": total_records,
        "devices": devices,
    }


def _command_targets_this_client(command, log_callback):
    from .api_client import get_client_device_id

    local_device_id = get_client_device_id()
    command_device_id = str(command.get("device_id") or "").strip()
    if command_device_id == local_device_id:
        return True

    _log(
        log_callback,
        f"[Command] Ignored #{_command_id(command)} for device "
        f"{command_device_id or 'missing'}; this client is {local_device_id}"
    )
    return False


def _execute_command(command, log_callback, last_pull):
    from .api_client import complete_command, post_reconcile_result, post_verify_result

    command_id = _command_id(command)
    command_type = command.get("command_type")
    if not _command_targets_this_client(command, log_callback):
        return

    _log(log_callback, f"[Command] Executing {command_type} #{command_id}")

    try:
        if command_type == "sync_now":
            result = _execute_sync_now(log_callback, last_pull)
            complete_command(command_id, "completed", result)
            return
        if command_type == "reconcile":
            result = _execute_reconcile(log_callback)
            ok, msg = post_reconcile_result(command_id, result)
            if not ok:
                complete_command(command_id, "failed", {"error": msg, "result": result})
            return
        if command_type == "verify_today":
            result = _execute_verify_today(log_callback)
            ok, msg = post_verify_result(command_id, result)
            if not ok:
                complete_command(command_id, "failed", {"error": msg, "result": result})
            return
        if command_type == "get_status":
            result = _execute_get_status(log_callback)
            complete_command(command_id, "completed", result)
            return

        complete_command(command_id, "failed", {"error": f"Unknown command_type: {command_type}"})
    except Exception as exc:
        complete_command(command_id, "failed", {"error": str(exc)})
        _log(log_callback, f"[Command] {command_type} failed: {exc}")


def _drain_command_queue(log_callback, last_pull):
    processed = 0
    while True:
        try:
            command = _command_queue.get_nowait()
        except queue.Empty:
            break
        command_id = _command_id(command)
        if command_id in _processed_command_ids:
            continue
        _remember_command_id(command_id)
        _execute_command(command, log_callback, last_pull)
        processed += 1
    return processed


def _poll_pending_commands(log_callback, last_pull):
    from .api_client import fetch_pending_commands
    for command in fetch_pending_commands():
        command_id = _command_id(command)
        if command_id in _processed_command_ids:
            continue
        _remember_command_id(command_id)
        _execute_command(command, log_callback, last_pull)


def _start_sse_listener(log_callback=None):
    global _sse_thread, _sse_stop_event
    if _sse_thread and _sse_thread.is_alive():
        return
    from .api_client import listen_command_stream
    _sse_stop_event = threading.Event()
    _sse_thread = threading.Thread(
        target=listen_command_stream,
        args=(_command_queue, _sse_stop_event, log_callback),
        daemon=True,
    )
    _sse_thread.start()


def _stop_sse_listener():
    global _sse_stop_event
    if _sse_stop_event:
        _sse_stop_event.set()


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
    last_command_poll_at = 0

    def poll_commands_if_due(force=False):
        nonlocal last_command_poll_at
        now_monotonic = time.monotonic()
        if force or (now_monotonic - last_command_poll_at) >= 30:
            _poll_pending_commands(log_callback, last_pull)
            last_command_poll_at = now_monotonic

    def divider(label=""):
        if log_callback and hasattr(log_callback, '__self__'):
            try:
                log_callback.__self__.divider(label)
                return
            except Exception:
                pass
        log(f"─── {label} {'─' * max(1, 44 - len(label))}" if label else "─" * 50)

    while _poll_running:
        _drain_command_queue(log_callback, last_pull)
        poll_commands_if_due()
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
                    _post_heartbeat(log_callback, False, 0)
                    continue

                if result:
                    save_attendance(device["id"], device["name"], result)
                    log(f"→ Pulled  {len(result)} new records from {device['name']}")
                else:
                    log(f"→ Pulled  0 new records  (no activity since last check)")
                _post_heartbeat(log_callback, True, _count_records_today(today.isoformat(), device["id"]))

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

        _drain_command_queue(log_callback, last_pull)
        poll_commands_if_due(force=True)

        # Next poll countdown
        total = _current_interval()
        next_time = (datetime.datetime.now() + datetime.timedelta(seconds=total)).strftime("%H:%M:%S")
        log(f"   Next pull at {next_time}  ({total}s)")

        elapsed = 0
        while elapsed < total and _poll_running:
            _drain_command_queue(log_callback, last_pull)
            poll_commands_if_due()
            time.sleep(1)
            elapsed += 1


def start_device_poll(interval_minutes=5, log_callback=None):
    global _poll_thread, _poll_running
    if _poll_running:
        return
    _poll_running = True
    _start_sse_listener(log_callback)
    _poll_thread = threading.Thread(
        target=_run_poll,
        args=(interval_minutes, log_callback),
        daemon=True,
    )
    _poll_thread.start()


def stop_device_poll():
    global _poll_running
    _poll_running = False
    _stop_sse_listener()


def restart_device_poll(interval_minutes=5, log_callback=None):
    stop_device_poll()
    time.sleep(0.5)
    start_device_poll(interval_minutes, log_callback)
