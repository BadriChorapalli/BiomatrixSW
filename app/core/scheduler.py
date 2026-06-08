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


def _run_poll(interval_minutes, log_callback):
    global _poll_running
    from .device import pull_attendance
    from .database import save_attendance

    def log(msg):
        if log_callback:
            log_callback(msg)

    while _poll_running:
        devices = [d for d in db.get_all_devices() if d["enabled"]]
        if devices:
            today = date.today()
            for device in devices:
                if not _poll_running:
                    return
                log(f"[AutoPull] {device['name']} ({device['ip']})…")
                ok, result = pull_attendance(
                    device["ip"], device["port"], device["password"], today
                )
                if ok:
                    save_attendance(device["id"], device["name"], result)
                    db.set_setting(
                        "last_device_pull",
                        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    )
                    log(f"[AutoPull] {device['name']}: {len(result)} records saved")
                else:
                    log(f"[AutoPull] {device['name']}: Failed — {result}")
        else:
            log("[AutoPull] No enabled devices — skipping")

        # Sleep in 5-second chunks so stop_device_poll() reacts quickly
        total = interval_minutes * 60
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
