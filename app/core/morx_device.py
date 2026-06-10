"""
Morx BioFace-MSD1K device communication via direct SBXPC protocol.
Returns data in the same shape as device.py (ZK functions) so sync.py
and the rest of the app need no structural changes.

Protocol: TCP port 5005, machine number 0, password in SBXPC packet.
"""

import socket
import struct
from datetime import datetime, timedelta, date

_MACH = 0  # device's SBXPC machine number (must be 0)
_CONNECT_TIMEOUT = 10


# ── Packet helpers ────────────────────────────────────────────────────────────

def _cs16(data: bytes) -> int:
    return sum(data) & 0xFFFF


def _pkt(cmd: bytes, params: bytes = b"\x00\x00\x00\x00", pad: bytes = b"\x00\x00") -> bytes:
    body = struct.pack("<H", _MACH) + cmd + params + pad
    return b"\x55\xaa" + body + struct.pack("<H", _cs16(b"\x55\xaa" + body))


def _recv_exactly(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError(f"Connection closed ({len(buf)}/{n} bytes received)")
        buf += chunk
    return buf


def _recv_beacon(sock: socket.socket) -> bytes:
    data = _recv_exactly(sock, 8)
    if data[:2] != b"\x5a\xa5":
        raise ValueError(f"Expected 5a a5 beacon, got {data[:2].hex()}")
    return data


def _recv_header(sock: socket.socket) -> bytes:
    data = _recv_exactly(sock, 14)
    if data[:2] != b"\xaa\x55":
        raise ValueError(f"Expected aa 55 header, got {data[:2].hex()}")
    return data


def _drain(sock: socket.socket, timeout: float = 10.0) -> bytes:
    sock.settimeout(timeout)
    buf = b""
    try:
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
    except socket.timeout:
        pass
    return buf


# ── Connection ────────────────────────────────────────────────────────────────

def _connect(ip: str, port, password) -> socket.socket:
    """Authenticate and return a connected socket, or raise on failure."""
    s = socket.socket()
    s.settimeout(_CONNECT_TIMEOUT)
    s.connect((ip, int(port)))

    # Exchange 1: send password
    s.sendall(_pkt(b"\x79\x19\x52\x00", struct.pack("<I", int(password))))
    _recv_beacon(s)
    _recv_header(s)

    # Exchange 2: confirm
    s.sendall(_pkt(b"\x79\x19\x52\x00", b"\x00\x00\x00\x00", b"\x01\x00"))
    _recv_beacon(s)
    hdr = _recv_header(s)

    status = struct.unpack_from("<H", hdr, 6)[0]
    if status != 1:
        s.close()
        raise ConnectionError(f"Device authentication failed (status={status})")
    return s


# ── Public API (same return shapes as device.py ZK functions) ─────────────────

def test_connection(ip, port, password, **kwargs):
    """Return (True, info_str) or (False, error_str)."""
    try:
        s = _connect(ip, port, password)
        s.sendall(_pkt(b"\x79\x19\x12\x01", b"\x00\x00\x00\x00"))
        _recv_beacon(s)
        hdr = _recv_header(s)
        user_count = struct.unpack_from("<I", hdr, 8)[0]
        s.close()
        return True, f"Connected: Morx BioFace-MSD1K | Enrolled users: {user_count}"
    except Exception as e:
        return False, str(e)


def _unlock(ip, port, password):
    """Open a fresh connection and send EnableDevice(1) to unlock the device."""
    try:
        s = _connect(ip, port, password)
        s.sendall(_pkt(b"\x79\x19\x0c\x01", b"\x00\x00\x00\x00"))
        _recv_beacon(s)
        _recv_header(s)
        s.close()
    except Exception:
        pass


def get_device_users(ip, port, password, **kwargs):
    """Return (True, list[dict]) or (False, error_str).

    Each dict: {user_id: str, name: str, privilege: int, card: str}
    """
    try:
        s = _connect(ip, port, password)

        # Step 1: get finger-record count
        s.sendall(_pkt(b"\x79\x19\x12\x01", b"\x00\x00\x00\x00"))
        _recv_beacon(s)
        hdr = _recv_header(s)
        count = struct.unpack_from("<I", hdr, 8)[0]

        # Step 2: fetch all finger records
        s.sendall(_pkt(b"\x79\x19\x12\x01", struct.pack("<I", count), b"\x01\x00"))
        _recv_beacon(s)
        _recv_header(s)
        raw = _drain(s, timeout=15.0)
        s.close()
        _unlock(ip, port, password)

        finger_records = _parse_user_stream(raw)

        # One user entry per unique user_id (de-duplicate across multiple fingers)
        seen = {}
        for r in finger_records:
            uid = str(r["user_id"])
            if uid not in seen:
                seen[uid] = {
                    "user_id":   uid,
                    "name":      "",
                    "privilege": r["privilege"],
                    "card":      "",
                }

        result = sorted(seen.values(),
                        key=lambda x: int(x["user_id"]) if x["user_id"].isdigit() else 0)
        return True, result
    except Exception as e:
        return False, str(e)


def pull_attendance(ip, port, password, target_date=None, since=None, **kwargs):
    """Return (True, list[dict]) or (False, error_str).

    Each dict: {user_id, name, date, time, datetime, status, status_code, punch}
    Filtered to target_date (default: today) and optionally to records > since.
    """
    if target_date is None:
        target_date = date.today()

    try:
        s = _connect(ip, port, password)

        # Step 1: get log count
        s.sendall(_pkt(b"\x79\x19\x07\x01", b"\x00\x00\x00\x00"))
        _recv_beacon(s)
        hdr = _recv_header(s)
        count_raw = struct.unpack_from("<I", hdr, 8)[0]

        # Step 2: fetch logs (ACK beacon required between device beacon and response header)
        s.sendall(_pkt(b"\x79\x19\x07\x01", struct.pack("<I", count_raw), b"\x01\x00"))
        _recv_beacon(s)

        ack = b"\x5a\xa5" + struct.pack("<H", _MACH) + b"\x01\x00\x00\x00"
        ack += struct.pack("<H", _cs16(ack))
        s.sendall(ack)

        hdr2 = _recv_header(s)
        status = struct.unpack_from("<H", hdr2, 6)[0]

        if status != 1:
            s.close()
            return True, []

        raw = _drain(s, timeout=30.0)
        s.close()
        _unlock(ip, port, password)

        all_logs = _parse_log_stream(raw, count_raw)

        result = []
        for log in all_logs:
            if not log["datetime"]:
                continue
            try:
                dt = datetime.strptime(log["datetime"], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            if dt.date() != target_date:
                continue
            if since is not None and dt <= since:
                continue
            result.append({
                "user_id":     str(log["enroll_no"]),
                "name":        "",
                "date":        dt.strftime("%Y-%m-%d"),
                "time":        dt.strftime("%H:%M:%S"),
                "datetime":    dt.strftime("%Y-%m-%d %H:%M:%S"),
                "status":      "CHECK IN",   # derive logic handles in/out from timing clusters
                "status_code": log.get("verify_mode", 0),
                "punch":       0,
            })

        result.sort(key=lambda x: x["time"])
        return True, result
    except Exception as e:
        return False, str(e)


# ── Stream parsers ────────────────────────────────────────────────────────────

def _parse_user_stream(data: bytes) -> list:
    """Parse 8-byte user/finger records from the ReadAllUserID data stream.

    Format: [5a a5 2d 01 batch_sep] [user_id 4B LE] [e_mach 1B] [finger 1B] [priv 1B] [enable 1B]
    """
    records = []
    i, n = 0, len(data)
    while i < n - 7:
        if data[i:i+2] == b"\x5a\xa5":
            i += 4
            continue
        if i + 4 <= n and data[i+2:i+4] == b"\x5a\xa5":
            i += 2
            continue
        if i + 8 <= n:
            user_id   = struct.unpack_from("<I", data, i)[0]
            privilege = data[i+6]
            records.append({"user_id": user_id, "privilege": privilege})
            i += 8
        else:
            i += 1
    return records


def _parse_log_stream(data: bytes, count: int) -> list:
    """Parse 12-byte log records from the ReadAllGLogData data stream.

    Stream starts with a 14-byte a5 5a header, then batch separators + records.
    Format: [timestamp 4B LE secs-from-2000] [enroll_no 4B LE] [verify 1B] [mach 1B] [reserved 2B]
    """
    BASE = datetime(2000, 1, 1)
    records = []
    n = len(data)
    i = 14 if (n >= 14 and data[:2] == b"\xa5\x5a") else 0

    parsed = 0
    while i + 12 <= n and (count == 0 or parsed < count):
        if data[i:i+2] == b"\x5a\xa5":
            i += 4
            continue
        if i + 4 <= n and data[i+2:i+4] == b"\x5a\xa5":
            i += 2
            continue

        ts_sec  = struct.unpack_from("<I", data, i)[0]
        user_id = struct.unpack_from("<I", data, i+4)[0]
        verify  = data[i+8]

        try:
            dt_str = (BASE + timedelta(seconds=ts_sec)).strftime("%Y-%m-%d %H:%M:%S")
        except (OverflowError, OSError):
            dt_str = ""

        records.append({"enroll_no": user_id, "verify_mode": verify, "datetime": dt_str})
        i += 12
        parsed += 1

    return records
