from zk import ZK
from datetime import date, datetime
from . import morx_device as _morx


def _is_morx(brand):
    return str(brand).strip().lower() == "morx"


def _zk(ip, port, password, force_udp=False):
    """Create a ZK connection object. force_udp=True for older/UDP-only devices."""
    return ZK(ip, port=int(port), timeout=10, password=int(password),
               force_udp=bool(force_udp), ommit_ping=False)


def _enrich_names(records, key="user_id"):
    """Fill in name from local code_mappings for records where name is empty."""
    from . import database as db
    mappings = db.get_all_code_mappings()
    for r in records:
        if not r.get("name"):
            m = mappings.get(str(r.get(key, "")))
            if m:
                r["name"] = m.get("si_name", "")
    return records


def get_device_users(ip, port, password, force_udp=False, brand="essl"):
    """Pull all enrolled users from the biometric device."""
    if _is_morx(brand):
        ok, result = _morx.get_device_users(ip, port, password)
        if ok:
            _enrich_names(result)
        return ok, result
    zk = _zk(ip, port, password, force_udp)
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


def test_connection(ip, port, password, force_udp=False, brand="essl"):
    if _is_morx(brand):
        return _morx.test_connection(ip, port, password)
    zk = _zk(ip, port, password, force_udp)
    conn = None
    try:
        conn = zk.connect()
        name = conn.get_device_name()
        serial = conn.get_serialnumber()
        conn.disconnect()
        return True, f"Connected: {name} | Serial: {serial}"
    except Exception as e:
        return False, str(e)
    finally:
        if conn:
            try:
                conn.disconnect()
            except Exception:
                pass


def pull_attendance(ip, port, password, target_date=None, since=None, force_udp=False, brand="essl"):
    """Pull attendance records from device.

    since     : datetime — if given, only return records with timestamp > since.
    force_udp : bool     — True for older ZKTeco-compatible devices that need UDP.
    """
    if _is_morx(brand):
        ok, result = _morx.pull_attendance(ip, port, password, target_date=target_date, since=since)
        if ok:
            _enrich_names(result)
        return ok, result
    if target_date is None:
        target_date = date.today()

    zk = _zk(ip, port, password, force_udp)
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
                "user_id":    r.user_id,
                "name":       users.get(r.user_id, "Unknown"),
                "date":       r.timestamp.strftime("%Y-%m-%d"),
                "time":       r.timestamp.strftime("%H:%M:%S"),
                "datetime":   r.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "status":     "CHECK IN" if r.status == 0 else "CHECK OUT",
                "status_code": r.status,
                "punch":      getattr(r, "punch", 0),  # 0=finger, 1=fp, 2=card, 3=password
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
