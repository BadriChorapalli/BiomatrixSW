import customtkinter as ctk
import threading
from datetime import date, timedelta
from ..core import database as db
from ..core.device import pull_attendance
from ..core.database import save_attendance
from ..core.api_client import _derive_daily_records, _parse_time


class HistoryTab(ctk.CTkFrame):
    def __init__(self, parent, main_window):
        super().__init__(parent, fg_color="transparent")
        self.main_window = main_window
        self.pack(fill="both", expand=True)
        self._build()
        self._load_dates()

    def _build(self):
        # ── Controls row ──────────────────────────────────────────────────────
        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.pack(fill="x", padx=4, pady=(4, 6))

        ctk.CTkLabel(ctrl, text="Date:", font=ctk.CTkFont(size=13)).pack(side="left", padx=(0, 6))

        self.date_var = ctk.StringVar(value=str(date.today()))
        self.date_entry = ctk.CTkEntry(ctrl, textvariable=self.date_var, width=120, height=34,
                                       placeholder_text="YYYY-MM-DD")
        self.date_entry.pack(side="left", padx=(0, 6))

        ctk.CTkButton(ctrl, text="Load", width=70, height=34,
                      command=self._load_from_db).pack(side="left", padx=(0, 6))

        ctk.CTkButton(ctrl, text="Pull from Device", height=34, width=130,
                      fg_color="#1565c0", hover_color="#0d47a1",
                      command=self._pull_from_device).pack(side="left", padx=(0, 12))

        for label, delta in [("Today", 0), ("Yesterday", -1), ("2 Days Ago", -2)]:
            d = str(date.today() + timedelta(days=delta))
            ctk.CTkButton(ctrl, text=label, width=90, height=34,
                          fg_color="#37474f", hover_color="#263238",
                          command=lambda x=d: self._quick_load(x)).pack(side="left", padx=2)

        # ── View toggle ───────────────────────────────────────────────────────
        toggle = ctk.CTkFrame(self, fg_color="transparent")
        toggle.pack(fill="x", padx=4, pady=(0, 4))

        self.view_var = ctk.StringVar(value="summary")
        ctk.CTkLabel(toggle, text="View:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 8))
        ctk.CTkRadioButton(toggle, text="Daily Summary  (first / last punch per person)",
                           variable=self.view_var, value="summary",
                           command=self._refresh_view).pack(side="left", padx=(0, 16))
        ctk.CTkRadioButton(toggle, text="Raw Punches  (every device entry)",
                           variable=self.view_var, value="raw",
                           command=self._refresh_view).pack(side="left")

        # ── Stats bar ─────────────────────────────────────────────────────────
        self.stats_frame = ctk.CTkFrame(self, fg_color="#1e1e2e", corner_radius=8, height=40)
        self.stats_frame.pack(fill="x", padx=4, pady=(0, 6))
        self.stats_frame.pack_propagate(False)
        self.stats_label = ctk.CTkLabel(self.stats_frame, text="Select a date to view attendance",
                                        text_color="#888", font=ctk.CTkFont(size=12))
        self.stats_label.pack(side="left", padx=16, pady=8)
        self.export_btn = ctk.CTkButton(self.stats_frame, text="Export CSV", width=100, height=28,
                                        fg_color="#37474f", hover_color="#263238",
                                        command=self._export_csv)
        self.export_btn.pack(side="right", padx=10, pady=6)
        self.export_btn.pack_forget()

        # ── Table area ────────────────────────────────────────────────────────
        self.header_frame = ctk.CTkFrame(self, fg_color="#263238", corner_radius=6, height=34)
        self.header_frame.pack(fill="x", padx=4)
        self.header_frame.pack_propagate(False)

        self.table = ctk.CTkScrollableFrame(self, corner_radius=6, fg_color="transparent")
        self.table.pack(fill="both", expand=True, padx=4, pady=(2, 4))

        self._records = []
        self._build_header_summary()

    # ── Header helpers ────────────────────────────────────────────────────────

    def _build_header_raw(self):
        for w in self.header_frame.winfo_children():
            w.destroy()
        for text, width in [("#", 50), ("User ID", 80), ("Name", 260),
                             ("Time", 90), ("Status", 100), ("Device", 130)]:
            ctk.CTkLabel(self.header_frame, text=text, font=ctk.CTkFont(size=12, weight="bold"),
                         width=width, anchor="w").pack(side="left", padx=6, pady=6)

    # ── Load / refresh ────────────────────────────────────────────────────────

    def _quick_load(self, date_str):
        self.date_var.set(date_str)
        self._load_from_db()

    def _load_dates(self):
        dates = db.get_attendance_dates()
        if dates:
            self.date_var.set(dates[0])
            self._load_from_db()

    def _load_from_db(self):
        date_str = self.date_var.get().strip()
        self._records = db.get_attendance_by_date(date_str)
        self._refresh_view()

    def _refresh_view(self):
        if self.view_var.get() == "summary":
            self._build_header_summary()
            self._render_summary(self._records)
        else:
            self._build_header_raw()
            self._render_raw(self._records)

    # ── Summary view (derived per-person first/last punch) ────────────────────

    def _build_header_summary(self):
        for w in self.header_frame.winfo_children():
            w.destroy()
        for text, width in [("#", 44), ("ID", 60), ("Name", 220),
                             ("Check IN", 80), ("Check OUT", 80),
                             ("Server", 90), ("Breaks", 160), ("Punches", 60)]:
            ctk.CTkLabel(self.header_frame, text=text,
                         font=ctk.CTkFont(size=12, weight="bold"),
                         width=width, anchor="w").pack(side="left", padx=6, pady=6)

    def _render_summary(self, records):
        for w in self.table.winfo_children():
            w.destroy()

        date_str = self.date_var.get().strip()

        if not records:
            ctk.CTkLabel(self.table, text=f"No records for {date_str}. Try 'Pull from Device'.",
                         text_color="#666").pack(pady=30)
            self.stats_label.configure(text=f"{date_str}  —  No records", text_color="#888")
            self.export_btn.pack_forget()
            return

        daily = _derive_daily_records(records)
        daily.sort(key=lambda x: x.get("check_in") or "")

        with_checkout  = sum(1 for d in daily if d.get("check_out"))
        with_breaks    = sum(1 for d in daily if d.get("breaks"))
        checkin_only   = len(daily) - with_checkout

        # Load server-marked status from local marked_today table
        marked_data = db.get_marked_today(date_str)  # bio_code → check_out (None if checkin only)
        server_marked_count = len(marked_data)

        self.stats_label.configure(
            text=(f"{date_str}   |   Staff: {len(daily)}   |   "
                  f"Full day: {with_checkout}   |   Check-in only: {checkin_only}"
                  + (f"   |   Permission breaks: {with_breaks}" if with_breaks else "")
                  + f"   |   ✓ Marked on server: {server_marked_count}"),
            text_color="white"
        )
        self.export_btn.pack(side="right", padx=10, pady=6)

        for i, d in enumerate(daily):
            has_breaks = bool(d.get("breaks"))
            row_h = 44 if has_breaks else 32
            bg = "#1a1a2e" if i % 2 == 0 else "#1e1e2e"
            row = ctk.CTkFrame(self.table, fg_color=bg, corner_radius=4, height=row_h)
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)

            bio_code    = str(d["user_id"])
            check_in_t  = _fmt_time(d.get("check_in"))
            check_out_t = _fmt_time(d.get("check_out"))
            raw_count   = d.get("raw_count", 1)

            for text, width in [
                (str(i + 1),         44),
                (bio_code,           60),
                (d.get("name", ""), 220),
            ]:
                ctk.CTkLabel(row, text=text, width=width, anchor="w",
                             font=ctk.CTkFont(size=12)).pack(side="left", padx=6)

            ctk.CTkLabel(row, text=check_in_t, width=80, anchor="w",
                         font=ctk.CTkFont(size=12),
                         text_color="#a5d6a7").pack(side="left", padx=6)

            out_color = "#81d4fa" if check_out_t else "#555"
            ctk.CTkLabel(row, text=check_out_t or "—", width=80, anchor="w",
                         font=ctk.CTkFont(size=12),
                         text_color=out_color).pack(side="left", padx=6)

            # Server marked column
            if bio_code in marked_data:
                stored_co = marked_data[bio_code]
                if stored_co:
                    server_text  = "✓ IN+OUT"
                    server_color = "#66bb6a"   # green — fully marked
                else:
                    server_text  = "✓ IN only"
                    server_color = "#ffa726"   # orange — check-in sent, awaiting checkout
            else:
                server_text  = "—"
                server_color = "#555"          # grey — not yet marked
            ctk.CTkLabel(row, text=server_text, width=90, anchor="w",
                         font=ctk.CTkFont(size=12),
                         text_color=server_color).pack(side="left", padx=6)

            # Breaks column
            breaks = d.get("breaks", [])
            if breaks:
                break_text = "  ".join(
                    f"{_fmt_hhmm(b['time'])}({'×'+str(b['raw_count']) if b['raw_count']>1 else ''})"
                    for b in breaks
                )
                ctk.CTkLabel(row, text=f"⟳ {break_text}", width=160, anchor="w",
                             font=ctk.CTkFont(size=11),
                             text_color="#ffb74d").pack(side="left", padx=6)
            else:
                ctk.CTkLabel(row, text="", width=160, anchor="w",
                             font=ctk.CTkFont(size=11)).pack(side="left", padx=6)

            punch_color = "#ffb74d" if raw_count > d.get("cluster_count", 1) else "#888"
            ctk.CTkLabel(row, text=str(raw_count), width=60, anchor="w",
                         font=ctk.CTkFont(size=12),
                         text_color=punch_color).pack(side="left", padx=6)

    # ── Raw punches view ──────────────────────────────────────────────────────

    def _render_raw(self, records):
        for w in self.table.winfo_children():
            w.destroy()

        date_str = self.date_var.get().strip()

        if not records:
            ctk.CTkLabel(self.table, text=f"No records for {date_str}.",
                         text_color="#666").pack(pady=30)
            self.stats_label.configure(text=f"{date_str}  —  No records", text_color="#888")
            self.export_btn.pack_forget()
            return

        self.stats_label.configure(
            text=f"{date_str}   |   {len(records)} raw punches   "
                 f"(status from device — unreliable if users don't press IN/OUT button)",
            text_color="#ffb74d"
        )
        self.export_btn.pack(side="right", padx=10, pady=6)

        for i, r in enumerate(records):
            bg = "#1a1a2e" if i % 2 == 0 else "#1e1e2e"
            row = ctk.CTkFrame(self.table, fg_color=bg, corner_radius=4, height=32)
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)

            for text, width in [
                (str(i + 1), 50),
                (str(r["user_id"]), 80),
                (r["name"], 260),
                (r["time"], 90),
            ]:
                ctk.CTkLabel(row, text=text, width=width, anchor="w",
                             font=ctk.CTkFont(size=12)).pack(side="left", padx=6)

            status_color = "#a5d6a7" if r["status"] == "CHECK IN" else "#ef9a9a"
            ctk.CTkLabel(row, text=r["status"], width=100, anchor="w",
                         font=ctk.CTkFont(size=12),
                         text_color=status_color).pack(side="left", padx=6)
            ctk.CTkLabel(row, text=r.get("device_name", ""), width=130, anchor="w",
                         font=ctk.CTkFont(size=11), text_color="#888").pack(side="left", padx=6)

    # ── Pull from device ──────────────────────────────────────────────────────

    def _pull_from_device(self):
        date_str = self.date_var.get().strip()
        try:
            from datetime import datetime
            target = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            self.stats_label.configure(text="Invalid date format. Use YYYY-MM-DD.",
                                       text_color="#ef9a9a")
            return

        devices = [d for d in db.get_all_devices() if d["enabled"]]
        if not devices:
            self.stats_label.configure(text="No devices configured.", text_color="#ef9a9a")
            return

        self.stats_label.configure(text=f"Pulling from device for {date_str}…",
                                   text_color="#4fc3f7")

        def do_pull():
            for device in devices:
                ok, result = pull_attendance(device["ip"], device["port"],
                                             device["password"], target,
                                             brand=device.get("brand", "essl"))
                if ok:
                    save_attendance(device["id"], device["name"], result)
            self.after(0, self._load_from_db)

        threading.Thread(target=do_pull, daemon=True).start()

    # ── Export ────────────────────────────────────────────────────────────────

    def _export_csv(self):
        if not self._records:
            return
        import csv, os
        date_str = self.date_var.get().strip()
        from ..core.database import EXPORT_DIR
        os.makedirs(EXPORT_DIR, exist_ok=True)

        if self.view_var.get() == "summary":
            daily = _derive_daily_records(self._records)
            path = os.path.join(EXPORT_DIR, f"summary_{date_str}.csv")
            with open(path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["user_id", "name", "date", "check_in", "check_out"])
                writer.writeheader()
                for d in sorted(daily, key=lambda x: x.get("check_in") or ""):
                    writer.writerow({
                        "user_id": d["user_id"],
                        "name": d.get("name", ""),
                        "date": d["date"],
                        "check_in": _fmt_time(d.get("check_in")),
                        "check_out": _fmt_time(d.get("check_out")) or "",
                    })
        else:
            path = os.path.join(EXPORT_DIR, f"raw_{date_str}.csv")
            with open(path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["user_id", "name", "date", "time", "status"])
                writer.writeheader()
                for r in self._records:
                    writer.writerow({k: r[k] for k in ["user_id", "name", "date", "time", "status"]})

        self.stats_label.configure(text=f"Exported: {path}", text_color="#a5d6a7")
        import subprocess, sys
        if sys.platform == "darwin":
            subprocess.Popen(["open", os.path.dirname(path)])
        elif sys.platform == "win32":
            os.startfile(os.path.dirname(path))


def _fmt_time(ts):
    """Extract HH:MM from an ISO timestamp or raw time string."""
    if not ts:
        return ""
    ts = str(ts)
    if "T" in ts:
        ts = ts.split("T")[1]
    parts = ts.split("+")[0].split(":")
    if len(parts) >= 2:
        return f"{parts[0]}:{parts[1]}"
    return ts


def _fmt_hhmm(t):
    """Extract HH:MM from a raw time string like HH:MM:SS."""
    if not t:
        return ""
    parts = str(t).split(":")
    if len(parts) >= 2:
        return f"{parts[0]}:{parts[1]}"
    return t
