import customtkinter as ctk
import threading
from ..core import database as db
from ..core.sync import sync_device, sync_all_devices
from ..core import scheduler


class DashboardTab(ctk.CTkFrame):
    def __init__(self, parent, main_window):
        super().__init__(parent, fg_color="transparent")
        self.main_window = main_window
        self.pack(fill="both", expand=True)
        self._build()
        self._schedule_refresh()

    def _build(self):
        # Top row - stats
        stats_frame = ctk.CTkFrame(self, corner_radius=8)
        stats_frame.pack(fill="x", padx=4, pady=(4, 8))

        self.stat_devices = self._stat_card(stats_frame, "Devices", "0")
        self.stat_synced = self._stat_card(stats_frame, "Last Sync", "Never")
        self.stat_records = self._stat_card(stats_frame, "Records Today", "0")
        self.stat_schedule = self._stat_card(stats_frame, "Next Sync", "--:--")
        self.stat_pull = self._stat_card(stats_frame, "Last Auto-Pull", "—")

        # Auto-pull status banner
        self.autopull_banner = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=11), text_color="#888"
        )
        self.autopull_banner.pack(anchor="w", padx=10, pady=(0, 4))

        # Today's attendance status for mapped users
        ctk.CTkLabel(self, text="Today's Attendance (Mapped Staff)",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(
            anchor="w", padx=8, pady=(4, 2))

        self.attendance_frame = ctk.CTkScrollableFrame(self, corner_radius=8, height=160)
        self.attendance_frame.pack(fill="x", padx=4, pady=(0, 6))

        # Device list with sync buttons
        ctk.CTkLabel(self, text="Configured Devices",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(
            anchor="w", padx=8, pady=(0, 4))

        self.device_list_frame = ctk.CTkScrollableFrame(self, corner_radius=8)
        self.device_list_frame.pack(fill="both", expand=True, padx=4)

        # Sync all button
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=4, pady=8)
        ctk.CTkButton(btn_frame, text="Sync All Devices Now", command=self._sync_all,
                      font=ctk.CTkFont(weight="bold"), fg_color="#1565c0", hover_color="#0d47a1",
                      height=38).pack(side="right")

        self.refresh()

    def _stat_card(self, parent, label, value):
        card = ctk.CTkFrame(parent, corner_radius=8, fg_color="#1e1e2e")
        card.pack(side="left", expand=True, fill="both", padx=6, pady=6)
        ctk.CTkLabel(card, text=label, font=ctk.CTkFont(size=11), text_color="#888").pack(pady=(10, 0))
        val_label = ctk.CTkLabel(card, text=value, font=ctk.CTkFont(size=20, weight="bold"))
        val_label.pack(pady=(2, 10))
        return val_label

    def _schedule_refresh(self):
        """Auto-refresh every 60 seconds."""
        self._refresh_stat_pull()
        self._refresh_attendance_status()
        self.after(60_000, self._schedule_refresh)

    def _refresh_stat_pull(self):
        last = db.get_setting("last_device_pull", "")
        if last:
            # Show only HH:MM
            self.stat_pull.configure(text=last[11:16] if len(last) > 11 else last)
        else:
            self.stat_pull.configure(text="—")

        enabled = db.get_setting("auto_pull_enabled", "1") == "1"
        interval = db.get_setting("auto_pull_interval", "5")
        if enabled:
            self.autopull_banner.configure(
                text=f"Auto-pull active — every {interval} min",
                text_color="#4caf50",
            )
        else:
            self.autopull_banner.configure(
                text="Auto-pull is OFF  (enable in Settings)",
                text_color="#888",
            )

    def _refresh_attendance_status(self):
        from datetime import date
        from collections import defaultdict

        for w in self.attendance_frame.winfo_children():
            w.destroy()

        mappings = db.get_all_code_mappings()
        if not mappings:
            ctk.CTkLabel(self.attendance_frame, text="No mapped staff yet — assign codes in Staff tab.",
                         text_color="#666", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=8, pady=6)
            return

        today = date.today().isoformat()
        all_records = db.get_attendance_by_date(today)
        user_records = defaultdict(list)
        for r in all_records:
            user_records[str(r["user_id"])].append(r)

        # Header
        hdr = ctk.CTkFrame(self.attendance_frame, fg_color="transparent")
        hdr.pack(fill="x", padx=4)
        for text, w in [("", 18), ("Name", 180), ("Check-In", 80), ("Check-Out", 80), ("Punches", 60)]:
            ctk.CTkLabel(hdr, text=text, width=w, anchor="w",
                         font=ctk.CTkFont(size=11), text_color="#888").pack(side="left")

        for bio_code, m in sorted(mappings.items(), key=lambda x: x[1]["si_name"]):
            punches = sorted(user_records.get(bio_code, []), key=lambda r: r["time"])
            has_data = bool(punches)
            check_in  = punches[0]["time"][:5]  if punches else "—"
            check_out = punches[-1]["time"][:5] if len(punches) > 1 else "—"
            dot_color = "#4caf50" if has_data else "#ef5350"

            row = ctk.CTkFrame(self.attendance_frame, fg_color="#1e1e2e", corner_radius=6)
            row.pack(fill="x", pady=2, padx=2)
            ctk.CTkLabel(row, text="●", text_color=dot_color, width=18).pack(side="left", padx=(8, 0))
            ctk.CTkLabel(row, text=m["si_name"], width=180, anchor="w").pack(side="left", padx=4)
            ctk.CTkLabel(row, text=check_in,  width=80, anchor="w", text_color="#a5d6a7").pack(side="left")
            ctk.CTkLabel(row, text=check_out, width=80, anchor="w", text_color="#90caf9").pack(side="left")
            ctk.CTkLabel(row, text=str(len(punches)), width=60, anchor="w", text_color="#888").pack(side="left")

    def refresh(self):
        for w in self.device_list_frame.winfo_children():
            w.destroy()

        devices = db.get_all_devices()
        self.stat_devices.configure(text=str(len(devices)))

        logs = db.get_logs(1)
        if logs:
            self.stat_synced.configure(text=logs[0]["synced_at"][:16])

        sync_time = db.get_setting("sync_time", "18:00")
        self.stat_schedule.configure(text=sync_time)

        self._refresh_stat_pull()
        self._refresh_attendance_status()

        if not devices:
            ctk.CTkLabel(self.device_list_frame, text="No devices added yet. Go to Devices tab to add one.",
                         text_color="#666").pack(pady=20)
            return

        for device in devices:
            self._device_row(device)

    def _device_row(self, device):
        row = ctk.CTkFrame(self.device_list_frame, corner_radius=6, fg_color="#1e1e2e")
        row.pack(fill="x", pady=4, padx=2)

        status_color = "#4caf50" if device["enabled"] else "#666"
        ctk.CTkLabel(row, text="●", text_color=status_color, font=ctk.CTkFont(size=14)).pack(
            side="left", padx=(12, 4))
        ctk.CTkLabel(row, text=device["name"], font=ctk.CTkFont(size=13, weight="bold")).pack(
            side="left", padx=4)
        ctk.CTkLabel(row, text=f"{device['ip']}:{device['port']}", text_color="#888").pack(
            side="left", padx=8)

        ctk.CTkButton(row, text="Sync Now", width=90, height=28,
                      command=lambda d=device: self._sync_one(d)).pack(side="right", padx=12, pady=8)

    def _sync_one(self, device):
        self.main_window.append_log(f"Manual sync started for {device['name']}...")
        threading.Thread(target=sync_device, args=(device,),
                         kwargs={"log_callback": self.main_window.append_log}, daemon=True).start()

    def _sync_all(self):
        self.main_window.append_log("Manual sync started for all devices...")
        threading.Thread(target=sync_all_devices,
                         kwargs={"log_callback": self.main_window.append_log}, daemon=True).start()
        self.main_window.tabs.set("Logs")
