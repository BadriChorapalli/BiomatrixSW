from zk import ZK
from datetime import date, datetime


def get_device_users(ip, port, password):
    """Pull all enrolled users from the biometric device."""
    zk = ZK(ip, port=int(port), timeout=10, password=int(password))
    conn = None
    try:
        conn = zk.connect()
        users = conn.get_users()
        result = []
        for u in users:
            result.append({
                "user_id":   u.user_id,
                "name":      u.name or "",
                "privilege": u.privilege,
                "card":      u.card or "",
            })
        result.sort(key=lambda x: int(x["user_id"]) if str(x["user_id"]).isdigit() else 0)
        return True, result
    except Exception as e:
        return False, str(e)
    finally:
        if conn:
            try:
                conn.disconnect()
            except Exception:
                pass


def test_connection(ip, port, password):
    zk = ZK(ip, port=int(port), timeout=5, password=int(password))
    try:
        conn = zk.connect()
        name = conn.get_device_name()
        serial = conn.get_serialnumber()
        conn.disconnect()
        return True, f"Connected: {name} | Serial: {serial}"
    except Exception as e:
        return False, str(e)


def pull_attendance(ip, port, password, target_date=None, since=None):
    """Pull attendance records from device.

    since: datetime — if given, only return records with timestamp > since.
    """
    if target_date is None:
        target_date = date.today()

    zk = ZK(ip, port=int(port), timeout=10, password=int(password))
    conn = None
    try:
        conn = zk.connect()
        users = {u.user_id: u.name for u in conn.get_users()}
        all_records = conn.get_attendance()
        records = [
            a for a in all_records
            if a.timestamp.date() == target_date
            and (since is None or a.timestamp > since)
        ]
        records.sort(key=lambda x: x.timestamp)

        result = []
        for r in records:
            result.append({
                "user_id": r.user_id,
                "name": users.get(r.user_id, "Unknown"),
                "date": r.timestamp.strftime("%Y-%m-%d"),
                "time": r.timestamp.strftime("%H:%M:%S"),
                "datetime": r.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "status": "CHECK IN" if r.status == 0 else "CHECK OUT",
                "status_code": r.status,
            })
        return True, result
    except Exception as e:
        return False, str(e)
    finally:
        if conn:
            try:
                conn.disconnect()
            except Exception:
                pass
