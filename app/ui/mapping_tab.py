import threading
import customtkinter as ctk
from ..core import api_client
from ..core import database as db


class MappingTab(ctk.CTkFrame):
    """Biometric code mapping — assign device EmpCodes to School Insights staff.

    Mirrors the web frontend's Biometric Codes page so on-site admins can do
    the mapping from the desktop app without needing browser access.
    """

    def __init__(self, parent, main_window):
        super().__init__(parent, fg_color="transparent")
        self.main_window = main_window
        self.pack(fill="both", expand=True)
        self._all_staff = []
        self._build()

    def _build(self):
        # ── Top bar ───────────────────────────────────────────────────────────
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=4, pady=(4, 6))

        ctk.CTkLabel(top, text="Biometric Code Mapping",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")

        ctk.CTkButton(top, text="Refresh", height=34, width=100,
                      fg_color="#37474f", hover_color="#263238",
                      command=self._load).pack(side="right", padx=(6, 0))

        # ── Stat cards ────────────────────────────────────────────────────────
        cards = ctk.CTkFrame(self, fg_color="transparent")
        cards.pack(fill="x", padx=4, pady=(0, 6))
        self._total_lbl = self._card(cards, "Total Staff", "—", "#455a64")
        self._mapped_lbl = self._card(cards, "Mapped", "—", "#1b5e20")
        self._unmapped_lbl = self._card(cards, "Unmapped", "—", "#b71c1c")

        # ── Search + filter ───────────────────────────────────────────────────
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=4, pady=(0, 6))

        self.search_var = ctk.StringVar()
        self.search_var.trace("w", lambda *a: self._filter())
        ctk.CTkEntry(row, textvariable=self.search_var,
                     placeholder_text="Search by name or department…",
                     height=34).pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.filter_var = ctk.StringVar(value="all")
        for label, val in [("All", "all"), ("Mapped", "mapped"), ("Unmapped", "unmapped")]:
            ctk.CTkRadioButton(row, text=label, variable=self.filter_var, value=val,
                               command=self._filter).pack(side="left", padx=6)

        # ── Table header ──────────────────────────────────────────────────────
        header = ctk.CTkFrame(self, fg_color="#263238", corner_radius=6, height=34)
        header.pack(fill="x", padx=4)
        header.pack_propagate(False)
        for text, width in [("Name", 260), ("Designation", 180), ("Department", 160),
                             ("Device Code", 120), ("Status", 90), ("Action", 90)]:
            ctk.CTkLabel(header, text=text, font=ctk.CTkFont(size=12, weight="bold"),
                         width=width, anchor="w").pack(side="left", padx=6, pady=6)

        # ── Scrollable table ──────────────────────────────────────────────────
        self.table = ctk.CTkScrollableFrame(self, corner_radius=6, fg_color="transparent")
        self.table.pack(fill="both", expand=True, padx=4, pady=(2, 4))

        self.status_label = ctk.CTkLabel(self, text="Click Refresh to load staff.",
                                         font=ctk.CTkFont(size=12), text_color="#888")
        self.status_label.pack(anchor="w", padx=8, pady=4)

    def _card(self, parent, title, value, color):
        f = ctk.CTkFrame(parent, fg_color=color, corner_radius=8)
        f.pack(side="left", expand=True, fill="x", padx=4, pady=2)
        ctk.CTkLabel(f, text=title, font=ctk.CTkFont(size=11), text_color="#ccc").pack(pady=(8, 0))
        lbl = ctk.CTkLabel(f, text=value, font=ctk.CTkFont(size=22, weight="bold"))
        lbl.pack(pady=(0, 8))
        return lbl

    def _load(self):
        if not api_client.is_device_approved():
            self.status_label.configure(
                text="Device not approved. Complete registration first.", text_color="#ef9a9a")
            return
        self.status_label.configure(text="Loading staff from School Insights…", text_color="#4fc3f7")
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        ok, result = api_client.get_biometric_codes()
        if ok:
            self._all_staff = result
            self.after(0, self._update_stats)
            self.after(0, self._filter)
            self.after(0, lambda: self.status_label.configure(
                text=f"Loaded {len(result)} staff members.", text_color="#a5d6a7"))
        else:
            self.after(0, lambda: self.status_label.configure(
                text=f"Failed: {result}", text_color="#ef9a9a"))

    def _update_stats(self):
        total = len(self._all_staff)
        mapped = sum(1 for s in self._all_staff if s.get("is_mapped"))
        self._total_lbl.configure(text=str(total))
        self._mapped_lbl.configure(text=str(mapped))
        self._unmapped_lbl.configure(text=str(total - mapped))

    def _filter(self):
        query = self.search_var.get().lower()
        filt = self.filter_var.get()
        result = []
        for s in self._all_staff:
            if filt == "mapped" and not s.get("is_mapped"):
                continue
            if filt == "unmapped" and s.get("is_mapped"):
                continue
            if query and query not in s.get("full_name", "").lower() \
                    and query not in (s.get("department") or "").lower():
                continue
            result.append(s)
        self._render(result)

    def _render(self, staff):
        for w in self.table.winfo_children():
            w.destroy()

        if not staff:
            ctk.CTkLabel(self.table,
                         text="No staff found. Click Refresh to load.",
                         text_color="#666").pack(pady=30)
            return

        for s in staff:
            is_mapped = s.get("is_mapped", False)
            bg = "#1a2e1a" if is_mapped else "#2e1a1a"
            row = ctk.CTkFrame(self.table, fg_color=bg, corner_radius=4, height=36)
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)

            for text, width in [
                (s.get("full_name", ""), 260),
                (s.get("designation", "") or "", 180),
                (s.get("department", "") or "", 160),
                (s.get("biometric_code") or "—", 120),
                ("Mapped" if is_mapped else "Unmapped", 90),
            ]:
                color = "#a5d6a7" if (text == "Mapped") else ("#ef9a9a" if text == "Unmapped" else None)
                lbl = ctk.CTkLabel(row, text=text, width=width, anchor="w",
                                   font=ctk.CTkFont(size=12))
                if color:
                    lbl.configure(text_color=color)
                lbl.pack(side="left", padx=6)

            btn_text = "Edit" if is_mapped else "Assign"
            btn_color = "#1565c0" if is_mapped else "#2e7d32"
            ctk.CTkButton(
                row, text=btn_text, width=80, height=26,
                fg_color=btn_color, hover_color="#0d47a1" if is_mapped else "#1b5e20",
                command=lambda staff_row=s: self._open_assign_dialog(staff_row)
            ).pack(side="left", padx=4)

    def _open_assign_dialog(self, staff_row):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Assign Biometric Code")
        dialog.geometry("400x220")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.lift()

        name = staff_row.get("full_name", "")
        code_id = staff_row.get("biometric_code_id")
        current_code = staff_row.get("biometric_code") or ""

        ctk.CTkLabel(dialog, text=f"Staff: {name}",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(20, 4))
        ctk.CTkLabel(dialog, text="Enter the device EmpCode (biometric user ID):",
                     font=ctk.CTkFont(size=12), text_color="#aaa").pack()

        code_var = ctk.StringVar(value=current_code)
        entry = ctk.CTkEntry(dialog, textvariable=code_var, width=200, height=36,
                             placeholder_text="e.g. 71")
        entry.pack(pady=12)
        entry.focus()

        err_lbl = ctk.CTkLabel(dialog, text="", text_color="#ef9a9a",
                               font=ctk.CTkFont(size=12))
        err_lbl.pack()

        def save():
            code = code_var.get().strip()
            if not code:
                err_lbl.configure(text="Code cannot be empty.")
                return

            btn.configure(state="disabled", text="Saving…")

            def do():
                if code_id:
                    ok, result = api_client.update_biometric_code(code_id, code)
                else:
                    ok, result = api_client.assign_biometric_code(
                        staff_row["user_id"], code)

                if ok:
                    self.after(0, dialog.destroy)
                    self.after(0, self._load)
                else:
                    self.after(0, lambda: err_lbl.configure(text=str(result)))
                    self.after(0, lambda: btn.configure(state="normal", text="Save"))

            threading.Thread(target=do, daemon=True).start()

        btn = ctk.CTkButton(dialog, text="Save", width=120, height=34,
                            fg_color="#1565c0", hover_color="#0d47a1",
                            command=save)
        btn.pack(pady=8)
        entry.bind("<Return>", lambda e: save())
