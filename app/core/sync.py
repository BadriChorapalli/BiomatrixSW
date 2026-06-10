import csv
import os
from datetime import date
from . import database as db
from .device import pull_attendance, get_device_users
from .api_client import upload_attendance, sync_device_users
from .database import save_attendance, EXPORT_DIR


def save_csv(records, device_name, target_date):
    os.makedirs(EXPORT_DIR, exist_ok=True)
    safe_name = "".join(c if c.isalnum() else "_" for c in device_name)
    filename = os.path.join(EXPORT_DIR, f"{safe_name}_{target_date}.csv")
    with open(filename, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["user_id", "name", "date", "time", "status"])
        writer.writeheader()
        for r in records:
            writer.writerow({k: r[k] for k in ["user_id", "name", "date", "time", "status"]})
    return filename


def sync_device(device, target_date=None, log_callback=None):
    if target_date is None:
        target_date = date.today()

    def log(msg):
        if log_callback:
            log_callback(msg)

    log(f"[{device['name']}] Connecting to {device['ip']}:{device['port']}...")
    ok, result = pull_attendance(
        device["ip"], device["port"], device["password"], target_date,
        force_udp=bool(device.get("force_udp", 0)),
        brand=device.get("brand", "essl"),
    )

    if not ok:
        msg = f"Failed to pull data: {result}"
        log(f"[{device['name']}] {msg}")
        db.add_log(device["id"], device["name"], "FAILED", 0, 0, msg)
        return False, msg

    records = result
    log(f"[{device['name']}] Pulled {len(records)} records for {target_date}")

    csv_path = save_csv(records, device["name"], target_date)
    log(f"[{device['name']}] Saved CSV: {csv_path}")

    save_attendance(device["id"], device["name"], records)
    log(f"[{device['name']}] Saved to local database")

    if not records:
        msg = "No records for today."
        db.add_log(device["id"], device["name"], "SUCCESS", 0, 0, msg)
        return True, msg

    api_ok, api_msg, uploaded = upload_attendance(records, device["name"])
    if api_ok:
        log(f"[{device['name']}] {api_msg}")
        db.add_log(device["id"], device["name"], "SUCCESS", len(records), uploaded, api_msg)
    else:
        log(f"[{device['name']}] Upload skipped/failed: {api_msg}")
        db.add_log(device["id"], device["name"], "CSV_ONLY", len(records), 0, api_msg)

    return True, f"Pulled {len(records)} records. {api_msg}"


def sync_all_devices(log_callback=None):
    devices = [d for d in db.get_all_devices() if d["enabled"]]
    if not devices:
        if log_callback:
            log_callback("No enabled devices configured.")
        return

    for device in devices:
        sync_device(device, log_callback=log_callback)


def sync_device_users_all(log_callback=None):
    """Pull enrolled users from all enabled devices and sync new ones to School Insights."""
    def log(msg):
        if log_callback:
            log_callback(msg)

    devices = [d for d in db.get_all_devices() if d["enabled"]]
    if not devices:
        return

    all_users = {}
    for device in devices:
        log(f"[DeviceUsers] Pulling roster from {device['name']}…")
        ok, result = get_device_users(
            device["ip"], device["port"], device["password"],
            force_udp=bool(device.get("force_udp", 0)),
            brand=device.get("brand", "essl"),
        )
        if ok:
            for u in result:
                all_users[u["user_id"]] = u
            log(f"[DeviceUsers] {device['name']}: {len(result)} users on device")
        else:
            log(f"[DeviceUsers] {device['name']}: Failed — {result}")
            return

    if not all_users:
        return

    log(f"[DeviceUsers] Syncing {len(all_users)} users to School Insights…")
    ok, created_or_err, skipped = sync_device_users(list(all_users.values()))
    if ok:
        log(f"[DeviceUsers] Done — {created_or_err} new, {skipped} already stored")
    else:
        log(f"[DeviceUsers] Sync failed: {created_or_err}")


def sync_code_mappings_job(log_callback=None):
    """Pull StaffBiometricCode mapping from School Insights and store locally."""
    from .api_client import sync_code_mappings
    def log(msg):
        if log_callback:
            log_callback(msg)
    log("[Mappings] Pulling staff code mappings from School Insights…")
    ok, mapped, unmapped = sync_code_mappings()
    if ok:
        log(f"[Mappings] Done — {mapped} mapped, {unmapped} unmapped staff")
    else:
        log(f"[Mappings] Failed: {mapped}")
