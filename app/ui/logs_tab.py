import customtkinter as ctk
from ..core import database as db


class LogsTab(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        self.pack(fill="both", expand=True)
        self._build()
        self._load_history()

    def _build(self):
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=4, pady=(4, 0))
        ctk.CTkLabel(top, text="Sync Logs", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        ctk.CTkButton(top, text="Clear", width=70, height=28, fg_color="#37474f",
                      command=self._clear).pack(side="right")
        ctk.CTkButton(top, text="Refresh History", width=120, height=28, fg_color="#37474f",
                      command=self._load_history).pack(side="right", padx=6)

        self.log_box = ctk.CTkTextbox(self, font=ctk.CTkFont(family="Courier", size=12),
                                      corner_radius=8, state="disabled")
        self.log_box.pack(fill="both", expand=True, padx=4, pady=6)

    def append(self, message):
        import datetime
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{ts}] {message}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _clear(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def _load_history(self):
        self._clear()
        logs = db.get_logs(50)
        if not logs:
            self.append("No sync history yet.")
            return
        self.append("=== Sync History (last 50) ===\n")
        for log in logs:
            icon = "✓" if log["status"] == "SUCCESS" else "~" if log["status"] == "CSV_ONLY" else "✗"
            self.append(
                f"[{log['synced_at']}] {icon} {log['device_name']} | "
                f"Pulled: {log['records_pulled']} | Uploaded: {log['records_uploaded']} | {log['message']}"
            )
