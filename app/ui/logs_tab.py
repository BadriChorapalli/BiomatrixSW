import customtkinter as ctk
import datetime
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

        # Color tags via underlying tk Text widget
        tb = self.log_box._textbox
        tb.tag_config("success",  foreground="#66bb6a")   # green
        tb.tag_config("error",    foreground="#ef5350")   # red
        tb.tag_config("warning",  foreground="#ffa726")   # orange
        tb.tag_config("info",     foreground="#4fc3f7")   # blue
        tb.tag_config("muted",    foreground="#666666")   # grey
        tb.tag_config("header",   foreground="#90caf9")   # light blue
        tb.tag_config("mark_ok",  foreground="#a5d6a7")   # light green
        tb.tag_config("mark_err", foreground="#ef9a9a")   # light red

    def _write(self, text, tag=None):
        tb = self.log_box._textbox
        self.log_box.configure(state="normal")
        if tag:
            tb.insert("end", text, tag)
        else:
            tb.insert("end", text)
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def append(self, message):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {message}\n"

        # Route to color based on content
        m = message.strip()
        if m.startswith("✓") or "marked" in m.lower() and "already" not in m.lower() and "failed" not in m.lower():
            tag = "mark_ok"
        elif m.startswith("✗") or "failed" in m.lower() or "Failed" in m:
            tag = "mark_err"
        elif m.startswith("⚠") or "no punch" in m.lower() or "no mapping" in m.lower() or "skipping" in m.lower():
            tag = "warning"
        elif m.startswith("───") or m.startswith("==="):
            tag = "header"
        elif m.startswith("→") or "Pulled" in m or "AutoPull" in m:
            tag = "info"
        elif m.startswith("#") or "Next pull" in m or "muted" in m:
            tag = "muted"
        else:
            tag = None

        self._write(line, tag)

    def divider(self, label=""):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        if label:
            text = f"\n[{ts}] ─── {label} {'─' * max(1, 44 - len(label))}\n"
        else:
            text = f"[{ts}] {'─' * 50}\n"
        self._write(text, "header")

    def _clear(self):
        self.log_box.configure(state="normal")
        self.log_box._textbox.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def _load_history(self):
        self._clear()
        logs = db.get_logs(50)
        if not logs:
            self._write("No sync history yet.\n", "muted")
            return
        self._write("═══ Sync History (last 50) ═══\n\n", "header")
        for log in reversed(logs):
            if log["status"] == "SUCCESS":
                icon, tag = "✓", "mark_ok"
            elif log["status"] == "CSV_ONLY":
                icon, tag = "~", "warning"
            else:
                icon, tag = "✗", "mark_err"
            line = (f"  {icon}  {log['synced_at'][:16]}  {log['device_name']:<20}"
                    f"  Pulled: {log['records_pulled']:<5} Uploaded: {log['records_uploaded']}\n")
            self._write(line, tag)
            if log["message"]:
                self._write(f"     {log['message']}\n", "muted")
