import threading
import customtkinter as ctk
from ..core import api_client
from ..core import database as db


_CONNECTION_LABELS = [
    ("Excel Upload (Manual)", "excel_upload"),
    ("API — Automatic (BiomatrixSync)", "api_automatic"),
    ("Both (API + Excel fallback)", "both"),
]
_LABEL_TO_VAL = {l: v for l, v in _CONNECTION_LABELS}
_VAL_TO_LABEL = {v: l for l, v in _CONNECTION_LABELS}


class DeviceConfigTab(ctk.CTkFrame):
    """School Insights biometric device configuration — mirrors the web configure page."""

    def __init__(self, parent, main_window):
        super().__init__(parent, fg_color="transparent")
        self.main_window = main_window
        self.pack(fill="both", expand=True)
        self._original = {}
        self._build()
        self._load()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build(self):
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=4, pady=4)
        self._scroll = scroll

        # Page title
        ctk.CTkLabel(scroll, text="Device Configuration",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", padx=4, pady=(4, 10))

        # ── Enable toggle ─────────────────────────────────────────────────────
        self._section_enable(scroll)

        # ── Device information ────────────────────────────────────────────────
        self._section_device_info(scroll)

        # ── Excel column mapping ──────────────────────────────────────────────
        self._section_column_mapping(scroll)

        # ── Notes ─────────────────────────────────────────────────────────────
        self._section_notes(scroll)

        # ── Status + buttons ──────────────────────────────────────────────────
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=8, pady=(4, 8))

        self.status_lbl = ctk.CTkLabel(bar, text="", font=ctk.CTkFont(size=12))
        self.status_lbl.pack(side="left")

        ctk.CTkButton(bar, text="Cancel", width=100, height=36,
                      fg_color="#37474f", hover_color="#263238",
                      command=self._load).pack(side="right", padx=(8, 0))

        self.save_btn = ctk.CTkButton(bar, text="Save Configuration",
                                      width=160, height=36,
                                      fg_color="#1b5e20", hover_color="#2e7d32",
                                      command=self._save)
        self.save_btn.pack(side="right")

    def _section_enable(self, parent):
        card = self._card(parent)
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x")

        left = ctk.CTkFrame(row, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(left, text="Enable Biometric Attendance",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(left,
                     text="Turn this on to allow biometric uploads and code mapping for this school.",
                     font=ctk.CTkFont(size=11), text_color="#888",
                     wraplength=500, justify="left").pack(anchor="w", pady=(2, 0))

        self.enable_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(row, text="", variable=self.enable_var,
                      width=50, button_color="#4caf50",
                      progress_color="#1b5e20").pack(side="right", padx=4)

    def _section_device_info(self, parent):
        card = self._card(parent)
        self._section_header(card, "Device Information",
                             "Physical device details for your records")
        g = self._grid(card)

        self.manufacturer_var = ctk.StringVar()
        self.model_var = ctk.StringVar()
        self.serial_var = ctk.StringVar()
        self.num_devices_var = ctk.StringVar(value="1")
        self.location_var = ctk.StringVar()
        self.connection_var = ctk.StringVar(value="API — Automatic (BiomatrixSync)")

        self._field(g, 0, 0, "Manufacturer", self.manufacturer_var,
                    placeholder="e.g., eSSL, ZKTeco, Realand")
        self._field(g, 0, 1, "Model", self.model_var,
                    placeholder="e.g., X990, G3, MB20")
        self._field(g, 1, 0, "Serial Number", self.serial_var,
                    placeholder="e.g., ESS-BW-001")
        self._field(g, 1, 1, "Number of Devices", self.num_devices_var,
                    placeholder="1")
        self._field(g, 2, 0, "Device Location", self.location_var,
                    placeholder="e.g., Main Gate, Staff Room")

        # Connection Type dropdown
        col_frame = ctk.CTkFrame(g, fg_color="transparent")
        col_frame.grid(row=2, column=1, sticky="ew", padx=4, pady=4)
        ctk.CTkLabel(col_frame, text="Connection Type",
                     font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w")
        ctk.CTkOptionMenu(col_frame,
                          values=[l for l, _ in _CONNECTION_LABELS],
                          variable=self.connection_var,
                          width=260).pack(fill="x", pady=(4, 0))

    def _section_column_mapping(self, parent):
        card = self._card(parent)
        self._section_header(card, "Excel Column Mapping",
                             "Enter the exact column headers as they appear in your device's exported file")

        # Info banner
        banner = ctk.CTkFrame(card, fg_color="#0d2137", corner_radius=6)
        banner.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(banner,
                     text="These headers must match exactly (case-insensitive) the column names in "
                          "your biometric device's Excel export. Check your device software to find "
                          "the correct headers.",
                     font=ctk.CTkFont(size=11), text_color="#90caf9",
                     wraplength=660, justify="left").pack(padx=12, pady=10)

        g = self._grid(card)

        self.bio_code_col_var = ctk.StringVar(value="EmpCode")
        self.date_col_var = ctk.StringVar()
        self.checkin_col_var = ctk.StringVar(value="InTime")
        self.checkout_col_var = ctk.StringVar(value="OutTime")

        self._field(g, 0, 0, "Biometric Code Column *", self.bio_code_col_var,
                    placeholder="EmpCode",
                    hint="Column containing the employee/biometric ID")
        self._field(g, 0, 1, "Date Column",  self.date_col_var,
                    placeholder="Date (optional)",
                    hint="Leave blank if file is single-day")
        self._field(g, 1, 0, "Check-in Column *", self.checkin_col_var,
                    placeholder="InTime",
                    hint="Column for the morning punch-in time")
        self._field(g, 1, 1, "Check-out Column", self.checkout_col_var,
                    placeholder="OutTime",
                    hint="Column for the evening punch-out time (optional)")

    def _section_notes(self, parent):
        card = self._card(parent)
        self._section_header(card, "Notes", "Optional notes about this device (visible to admins only)")
        self.notes_box = ctk.CTkTextbox(card, height=90, corner_radius=6)
        self.notes_box.pack(fill="x")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _card(self, parent):
        f = ctk.CTkFrame(parent, fg_color="#1e1e2e", corner_radius=10)
        f.pack(fill="x", padx=2, pady=6)
        inner = ctk.CTkFrame(f, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=16, pady=14)
        return inner

    def _section_header(self, parent, title, subtitle):
        ctk.CTkLabel(parent, text=title,
                     font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(parent, text=subtitle,
                     font=ctk.CTkFont(size=11), text_color="#888").pack(anchor="w", pady=(0, 10))

    def _grid(self, parent):
        g = ctk.CTkFrame(parent, fg_color="transparent")
        g.pack(fill="x")
        g.columnconfigure(0, weight=1)
        g.columnconfigure(1, weight=1)
        return g

    def _field(self, grid, row, col, label, var, placeholder="", hint=""):
        f = ctk.CTkFrame(grid, fg_color="transparent")
        f.grid(row=row, column=col, sticky="ew", padx=4, pady=4)
        ctk.CTkLabel(f, text=label,
                     font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w")
        if hint:
            ctk.CTkLabel(f, text=hint, font=ctk.CTkFont(size=10),
                         text_color="#666").pack(anchor="w")
        ctk.CTkEntry(f, textvariable=var, placeholder_text=placeholder,
                     height=36).pack(fill="x", pady=(4, 0))

    # ── Load / Save ───────────────────────────────────────────────────────────

    def _load(self):
        if not api_client.is_device_approved():
            self.status_lbl.configure(
                text="Device not approved. Complete registration first.", text_color="#ef9a9a")
            return
        self.status_lbl.configure(text="Loading configuration…", text_color="#4fc3f7")
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        ok, result = api_client.get_device_config()
        if ok:
            self._original = result
            self.after(0, lambda: self._populate(result))
            self.after(0, lambda: self.status_lbl.configure(text="", text_color="#888"))
        else:
            self.after(0, lambda: self.status_lbl.configure(
                text=f"Load failed: {result}", text_color="#ef9a9a"))

    def _populate(self, d):
        self.enable_var.set(bool(d.get("is_enabled", False)))
        self.manufacturer_var.set(d.get("manufacturer", ""))
        self.model_var.set(d.get("model", ""))
        self.serial_var.set(d.get("serial_number", ""))
        self.num_devices_var.set(str(d.get("num_devices", 1)))
        self.location_var.set(d.get("device_location", ""))

        ct = d.get("connection_type", "api_automatic")
        self.connection_var.set(_VAL_TO_LABEL.get(ct, "API — Automatic (BiomatrixSync)"))

        self.bio_code_col_var.set(d.get("biometric_code_col", "EmpCode"))
        self.date_col_var.set(d.get("date_col", ""))
        self.checkin_col_var.set(d.get("checkin_col", "InTime"))
        self.checkout_col_var.set(d.get("checkout_col", "OutTime"))

        self.notes_box.delete("1.0", "end")
        self.notes_box.insert("1.0", d.get("notes", ""))

    def _save(self):
        if not api_client.is_device_approved():
            self.status_lbl.configure(
                text="Device not approved. Complete registration first.", text_color="#ef9a9a")
            return

        # Validate required fields
        if not self.bio_code_col_var.get().strip():
            self.status_lbl.configure(
                text="Biometric Code Column is required.", text_color="#ef9a9a")
            return
        if not self.checkin_col_var.get().strip():
            self.status_lbl.configure(
                text="Check-in Column is required.", text_color="#ef9a9a")
            return

        school_id = db.get_setting("si_school_id", "")
        config = {
            "school": int(school_id) if school_id else None,
            "is_enabled": self.enable_var.get(),
            "manufacturer": self.manufacturer_var.get().strip(),
            "model": self.model_var.get().strip(),
            "serial_number": self.serial_var.get().strip(),
            "num_devices": int(self.num_devices_var.get() or 1),
            "device_location": self.location_var.get().strip(),
            "connection_type": _LABEL_TO_VAL.get(
                self.connection_var.get(), "api_automatic"),
            "biometric_code_col": self.bio_code_col_var.get().strip(),
            "date_col": self.date_col_var.get().strip(),
            "checkin_col": self.checkin_col_var.get().strip(),
            "checkout_col": self.checkout_col_var.get().strip(),
            "notes": self.notes_box.get("1.0", "end").strip(),
        }

        self.save_btn.configure(state="disabled", text="Saving…")
        self.status_lbl.configure(text="Saving…", text_color="#4fc3f7")

        def do():
            ok, result = api_client.save_device_config(config)
            if ok:
                self._original = result
                self.after(0, lambda: self._populate(result))
                self.after(0, lambda: self.status_lbl.configure(
                    text="Configuration saved successfully.", text_color="#a5d6a7"))
            else:
                self.after(0, lambda: self.status_lbl.configure(
                    text=f"Save failed: {result}", text_color="#ef9a9a"))
            self.after(0, lambda: self.save_btn.configure(
                state="normal", text="Save Configuration"))

        threading.Thread(target=do, daemon=True).start()
