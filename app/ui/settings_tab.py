import customtkinter as ctk
import hashlib
from ..core import database as db
from ..core import scheduler


def _hash(password):
    return hashlib.sha256(password.encode()).hexdigest()


class SettingsTab(ctk.CTkFrame):
    def __init__(self, parent, main_window):
        super().__init__(parent, fg_color="transparent")
        self.main_window = main_window
        self.pack(fill="both", expand=True)
        self._build()

    def _build(self):
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=4, pady=4)

        # School Insight API
        self._section(scroll, "School Insight API")

        ctk.CTkLabel(scroll, text="API URL", anchor="w").pack(fill="x", padx=16, pady=(4, 2))
        self.api_url = ctk.CTkEntry(scroll, placeholder_text="https://api.schoolinsight.com/attendance",
                                    height=36)
        self.api_url.pack(fill="x", padx=16)
        self.api_url.insert(0, db.get_setting("api_url", ""))

        ctk.CTkLabel(scroll, text="API Key / Token", anchor="w").pack(fill="x", padx=16, pady=(10, 2))
        self.api_key = ctk.CTkEntry(scroll, placeholder_text="Your API key", height=36, show="*")
        self.api_key.pack(fill="x", padx=16)
        self.api_key.insert(0, db.get_setting("api_key", ""))

        # Sync Schedule
        self._section(scroll, "Sync Schedule")

        ctk.CTkLabel(scroll, text="Daily Sync Time (24h format)", anchor="w").pack(
            fill="x", padx=16, pady=(4, 2))
        self.sync_time = ctk.CTkEntry(scroll, placeholder_text="18:00", height=36, width=120)
        self.sync_time.pack(anchor="w", padx=16)
        self.sync_time.insert(0, db.get_setting("sync_time", "18:00"))

        ctk.CTkLabel(scroll,
                     text="The service will automatically pull and upload attendance at this time daily.",
                     text_color="#888", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=16, pady=(4, 0))

        # Auto-Pull
        self._section(scroll, "Auto-Pull from Device")

        ap_row = ctk.CTkFrame(scroll, fg_color="transparent")
        ap_row.pack(fill="x", padx=16, pady=(4, 0))

        self.auto_pull_var = ctk.BooleanVar(value=db.get_setting("auto_pull_enabled", "1") == "1")
        ctk.CTkSwitch(ap_row, text="Pull from device automatically every",
                      variable=self.auto_pull_var,
                      button_color="#4caf50", progress_color="#1b5e20",
                      font=ctk.CTkFont(size=12)).pack(side="left")

        self.auto_pull_interval = ctk.CTkEntry(ap_row, width=54, height=30,
                                               justify="center")
        self.auto_pull_interval.pack(side="left", padx=(10, 4))
        self.auto_pull_interval.insert(0, db.get_setting("auto_pull_interval", "5"))

        ctk.CTkLabel(ap_row, text="minutes", font=ctk.CTkFont(size=12)).pack(side="left")

        ctk.CTkLabel(scroll,
                     text="Default interval (outside any slot). School Insights upload still happens at daily sync time.",
                     text_color="#888", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=16, pady=(4, 0))

        # Pull Time Slots
        self._section(scroll, "Pull Time Slots")

        ctk.CTkLabel(scroll,
                     text="Define time ranges with faster pull intervals. Outside these slots the default above applies.",
                     text_color="#888", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=16, pady=(0, 8))

        self._slots_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        self._slots_frame.pack(fill="x", padx=16)
        self._render_slots()

        # Add slot row
        add_row = ctk.CTkFrame(scroll, fg_color="transparent")
        add_row.pack(fill="x", padx=16, pady=(10, 0))

        ctk.CTkLabel(add_row, text="From", width=32).pack(side="left")
        self._slot_start = ctk.CTkEntry(add_row, width=64, height=30, placeholder_text="07:00")
        self._slot_start.pack(side="left", padx=(4, 8))

        ctk.CTkLabel(add_row, text="To", width=20).pack(side="left")
        self._slot_end = ctk.CTkEntry(add_row, width=64, height=30, placeholder_text="08:00")
        self._slot_end.pack(side="left", padx=(4, 8))

        ctk.CTkLabel(add_row, text="Every", width=36).pack(side="left")
        self._slot_interval = ctk.CTkEntry(add_row, width=54, height=30, placeholder_text="120")
        self._slot_interval.pack(side="left", padx=(4, 4))
        ctk.CTkLabel(add_row, text="sec").pack(side="left", padx=(0, 12))

        ctk.CTkButton(add_row, text="+ Add Slot", width=90, height=30,
                      fg_color="#37474f", hover_color="#263238",
                      command=self._add_slot).pack(side="left")

        # Export
        self._section(scroll, "Export")
        ctk.CTkLabel(scroll, text="CSV files are saved in the exports/ folder next to the application.",
                     text_color="#888", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=16, pady=(4, 0))

        # Change Password
        self._section(scroll, "Change Password")

        ctk.CTkLabel(scroll, text="Current Password", anchor="w").pack(fill="x", padx=16, pady=(4, 2))
        self.cur_pass = ctk.CTkEntry(scroll, placeholder_text="Current password", height=36, show="*")
        self.cur_pass.pack(fill="x", padx=16)

        ctk.CTkLabel(scroll, text="New Password", anchor="w").pack(fill="x", padx=16, pady=(10, 2))
        self.new_pass = ctk.CTkEntry(scroll, placeholder_text="New password", height=36, show="*")
        self.new_pass.pack(fill="x", padx=16)

        ctk.CTkLabel(scroll, text="Confirm New Password", anchor="w").pack(fill="x", padx=16, pady=(10, 2))
        self.confirm_pass = ctk.CTkEntry(scroll, placeholder_text="Confirm new password", height=36, show="*")
        self.confirm_pass.pack(fill="x", padx=16)

        self.pass_status = ctk.CTkLabel(scroll, text="", font=ctk.CTkFont(size=12))
        self.pass_status.pack(anchor="w", padx=16, pady=(6, 0))

        ctk.CTkButton(scroll, text="Change Password", command=self._change_password,
                      height=36, fg_color="#37474f", hover_color="#263238").pack(anchor="w", padx=16, pady=(4, 0))

        # Clear Data
        self._section(scroll, "Clear Local Data")

        ctk.CTkLabel(scroll,
                     text="Clears staff list and code mappings synced from School Insights. Local attendance and device data are kept. You can re-sync from cloud anytime.",
                     text_color="#888", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=16, pady=(0, 8))

        self._clear_status = ctk.CTkLabel(scroll, text="", font=ctk.CTkFont(size=12))
        self._clear_status.pack(anchor="w", padx=16)

        ctk.CTkButton(scroll, text="Clear Cloud Sync Data", command=self._clear_data,
                      height=36, fg_color="#b71c1c", hover_color="#7f0000").pack(anchor="w", padx=16, pady=(4, 0))

        # Save button
        self.status_label = ctk.CTkLabel(scroll, text="", text_color="#a5d6a7")
        self.status_label.pack(anchor="w", padx=16, pady=(16, 4))

        ctk.CTkButton(scroll, text="Save Settings", command=self._save,
                      height=38, font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=16, pady=(0, 16))

    def _render_slots(self):
        for w in self._slots_frame.winfo_children():
            w.destroy()
        slots = db.get_poll_slots()
        if not slots:
            ctk.CTkLabel(self._slots_frame, text="No slots configured — default interval always applies.",
                         text_color="#666", font=ctk.CTkFont(size=11)).pack(anchor="w")
            return
        # Header
        hdr = ctk.CTkFrame(self._slots_frame, fg_color="transparent")
        hdr.pack(fill="x")
        for text, w in [("From", 70), ("To", 70), ("Interval", 90), ("", 70)]:
            ctk.CTkLabel(hdr, text=text, width=w, anchor="w",
                         font=ctk.CTkFont(size=11), text_color="#888").pack(side="left")
        for i, slot in enumerate(slots):
            row = ctk.CTkFrame(self._slots_frame, fg_color="#1e1e1e", corner_radius=6)
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=slot["start"], width=70, anchor="w").pack(side="left", padx=8)
            ctk.CTkLabel(row, text=slot["end"],   width=70, anchor="w").pack(side="left")
            secs = slot["interval"]
            label = f"{secs}s" if secs < 60 else f"{secs//60}m {secs%60}s" if secs % 60 else f"{secs//60} min"
            ctk.CTkLabel(row, text=label, width=90, anchor="w").pack(side="left")
            ctk.CTkButton(row, text="Delete", width=64, height=24,
                          fg_color="#b71c1c", hover_color="#7f0000",
                          font=ctk.CTkFont(size=11),
                          command=lambda idx=i: self._delete_slot(idx)).pack(side="left", padx=4, pady=4)

    def _add_slot(self):
        start = self._slot_start.get().strip()
        end   = self._slot_end.get().strip()
        try:
            interval = int(self._slot_interval.get().strip())
            assert interval > 0
        except Exception:
            return
        import re
        if not re.match(r"^\d{2}:\d{2}$", start) or not re.match(r"^\d{2}:\d{2}$", end):
            return
        slots = db.get_poll_slots()
        slots.append({"start": start, "end": end, "interval": interval})
        slots.sort(key=lambda s: s["start"])
        db.save_poll_slots(slots)
        self._slot_start.delete(0, "end")
        self._slot_end.delete(0, "end")
        self._slot_interval.delete(0, "end")
        self._render_slots()

    def _delete_slot(self, idx):
        slots = db.get_poll_slots()
        if 0 <= idx < len(slots):
            slots.pop(idx)
            db.save_poll_slots(slots)
        self._render_slots()

    def _clear_data(self):
        from tkinter import messagebox
        if not messagebox.askyesno(
            "Clear Cloud Sync Data",
            "This will clear the staff list and code mappings synced from School Insights.\n\nLocal attendance records are NOT affected. You can re-sync from cloud anytime.\n\nContinue?"
        ):
            return
        conn = db.get_conn()
        conn.execute("DELETE FROM staff")
        conn.execute("DELETE FROM code_mappings")
        conn.commit()
        conn.close()
        self._clear_status.configure(text="Cloud sync data cleared. Re-sync from Staff tab.", text_color="#a5d6a7")
        self.after(4000, lambda: self._clear_status.configure(text=""))

    def _section(self, parent, title):
        ctk.CTkLabel(parent, text=title, font=ctk.CTkFont(size=13, weight="bold")).pack(
            anchor="w", padx=16, pady=(18, 2))
        ctk.CTkFrame(parent, height=1, fg_color="#333").pack(fill="x", padx=16, pady=(0, 6))

    def _change_password(self):
        cur = self.cur_pass.get()
        new = self.new_pass.get()
        confirm = self.confirm_pass.get()

        stored = db.get_setting("auth_password", _hash("admin123"))
        if _hash(cur) != stored:
            self.pass_status.configure(text="Current password is incorrect.", text_color="#ef9a9a")
            return
        if len(new) < 6:
            self.pass_status.configure(text="New password must be at least 6 characters.", text_color="#ef9a9a")
            return
        if new != confirm:
            self.pass_status.configure(text="Passwords do not match.", text_color="#ef9a9a")
            return

        db.set_setting("auth_password", _hash(new))
        self.cur_pass.delete(0, "end")
        self.new_pass.delete(0, "end")
        self.confirm_pass.delete(0, "end")
        self.pass_status.configure(text="Password changed successfully.", text_color="#a5d6a7")

    def _save(self):
        db.set_setting("api_url", self.api_url.get().strip())
        db.set_setting("api_key", self.api_key.get().strip())

        sync_time = self.sync_time.get().strip() or "18:00"
        db.set_setting("sync_time", sync_time)
        scheduler.restart(log_callback=self.main_window.append_log)

        try:
            interval = max(1, int(self.auto_pull_interval.get().strip() or "5"))
        except ValueError:
            interval = 5
        db.set_setting("auto_pull_interval", str(interval))

        enabled = self.auto_pull_var.get()
        db.set_setting("auto_pull_enabled", "1" if enabled else "0")

        if enabled:
            scheduler.restart_device_poll(
                interval_minutes=interval,
                log_callback=self.main_window.append_log,
            )
        else:
            scheduler.stop_device_poll()

        msg = f"Settings saved. Daily sync at {sync_time}."
        if enabled:
            msg += f" Auto-pull every {interval} min."
        self.status_label.configure(text=msg)
        self.main_window.dashboard.refresh()
