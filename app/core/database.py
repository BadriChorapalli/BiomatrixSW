import sqlite3
import os
import sys


def _get_data_dir():
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    else:
        base = os.path.expanduser("~/Library/Application Support") if sys.platform == "darwin" \
               else os.path.expanduser("~/.local/share")
    data_dir = os.path.join(base, "BiomatrixSync")
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


DATA_DIR = _get_data_dir()
DB_PATH = os.path.join(DATA_DIR, "biomatrix.db")
EXPORT_DIR = os.path.join(DATA_DIR, "exports")


def get_conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            ip TEXT NOT NULL,
            port INTEGER DEFAULT 4370,
            password INTEGER DEFAULT 0,
            enabled INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS sync_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER,
            device_name TEXT,
            status TEXT,
            records_pulled INTEGER DEFAULT 0,
            records_uploaded INTEGER DEFAULT 0,
            message TEXT,
            synced_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER,
            device_name TEXT,
            user_id TEXT,
            name TEXT,
            date TEXT,
            time TEXT,
            status TEXT,
            UNIQUE(device_id, user_id, date, time)
        );

        CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance(date);
        CREATE INDEX IF NOT EXISTS idx_attendance_device ON attendance(device_id);

        CREATE TABLE IF NOT EXISTS staff (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            si_user_id INTEGER UNIQUE,
            name TEXT,
            email TEXT,
            roles TEXT,
            school_id INTEGER,
            synced_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS code_mappings (
            bio_code TEXT PRIMARY KEY,
            si_user_id INTEGER,
            si_name TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()


def get_all_devices():
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM devices ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_device(name, ip, port, password):
    conn = get_conn()
    conn.execute("INSERT INTO devices (name, ip, port, password) VALUES (?, ?, ?, ?)",
                 (name, ip, int(port), int(password)))
    conn.commit()
    conn.close()


def update_device(device_id, name, ip, port, password):
    conn = get_conn()
    conn.execute("UPDATE devices SET name=?, ip=?, port=?, password=? WHERE id=?",
                 (name, ip, int(port), int(password), device_id))
    conn.commit()
    conn.close()


def delete_device(device_id):
    conn = get_conn()
    conn.execute("DELETE FROM devices WHERE id=?", (device_id,))
    conn.commit()
    conn.close()


def toggle_device(device_id, enabled):
    conn = get_conn()
    conn.execute("UPDATE devices SET enabled=? WHERE id=?", (1 if enabled else 0, device_id))
    conn.commit()
    conn.close()


def get_setting(key, default=None):
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row[0] if row else default


def set_setting(key, value):
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


def add_log(device_id, device_name, status, records_pulled, records_uploaded, message):
    conn = get_conn()
    conn.execute(
        "INSERT INTO sync_logs (device_id, device_name, status, records_pulled, records_uploaded, message) VALUES (?,?,?,?,?,?)",
        (device_id, device_name, status, records_pulled, records_uploaded, message)
    )
    conn.commit()
    conn.close()


def save_staff(staff_list, school_id):
    conn = get_conn()
    for s in staff_list:
        roles = ", ".join(s.get("roles", []))
        conn.execute(
            "INSERT OR REPLACE INTO staff (si_user_id, name, email, roles, school_id, synced_at) VALUES (?,?,?,?,?,datetime('now'))",
            (s.get("id"), s.get("name", ""), s.get("email", ""), roles, school_id)
        )
    conn.commit()
    conn.close()


def get_all_staff():
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM staff ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_attendance(device_id, device_name, records):
    conn = get_conn()
    for r in records:
        conn.execute(
            "INSERT OR IGNORE INTO attendance (device_id, device_name, user_id, name, date, time, status) VALUES (?,?,?,?,?,?,?)",
            (device_id, device_name, r["user_id"], r["name"], r["date"], r["time"], r["status"])
        )
    conn.commit()
    conn.close()


def get_attendance_by_date(date_str, device_id=None):
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    if device_id:
        rows = conn.execute(
            "SELECT * FROM attendance WHERE date=? AND device_id=? ORDER BY time",
            (date_str, device_id)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM attendance WHERE date=? ORDER BY device_name, time",
            (date_str,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_attendance_dates():
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT date FROM attendance ORDER BY date DESC LIMIT 60"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_poll_slots():
    import json
    raw = get_setting("poll_slots", "[]")
    try:
        return json.loads(raw)
    except Exception:
        return []


def save_poll_slots(slots):
    import json
    set_setting("poll_slots", json.dumps(slots))


def save_code_mappings(mappings):
    """Upsert bio_code → SI user mappings. mappings = [{bio_code, si_user_id, si_name}]."""
    conn = get_conn()
    for m in mappings:
        conn.execute(
            "INSERT OR REPLACE INTO code_mappings (bio_code, si_user_id, si_name, updated_at) "
            "VALUES (?, ?, ?, datetime('now'))",
            (str(m["bio_code"]), m["si_user_id"], m["si_name"])
        )
    conn.commit()
    conn.close()


def get_code_mapping(bio_code):
    """Return {si_user_id, si_name} for a bio_code, or None."""
    conn = get_conn()
    row = conn.execute(
        "SELECT si_user_id, si_name FROM code_mappings WHERE bio_code=?", (str(bio_code),)
    ).fetchone()
    conn.close()
    return {"si_user_id": row[0], "si_name": row[1]} if row else None


def get_all_code_mappings():
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM code_mappings").fetchall()
    conn.close()
    return {r["bio_code"]: dict(r) for r in rows}


def get_logs(limit=100):
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM sync_logs ORDER BY synced_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
