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
                     text="Only saves to local database. School Insights upload still happens at the daily sync time.",
                     text_color="#888", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=16, pady=(4, 0))

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

        # Save button
        self.status_label = ctk.CTkLabel(scroll, text="", text_color="#a5d6a7")
        self.status_label.pack(anchor="w", padx=16, pady=(16, 4))

        ctk.CTkButton(scroll, text="Save Settings", command=self._save,
                      height=38, font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=16, pady=(0, 16))

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
