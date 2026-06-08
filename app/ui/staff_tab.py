import customtkinter as ctk
import threading
from ..core import api_client
from ..core import database as db
from ..core.device import get_device_users
from ..core.sync import sync_device_users_all

_PRIVILEGE = {0: "User", 2: "Enroller", 6: "Manager", 14: "Admin"}


class StaffTab(ctk.CTkFrame):
    def __init__(self, parent, main_window):
        super().__init__(parent, fg_color="transparent")
        self.main_window = main_window
        self.pack(fill="both", expand=True)
        self._si_staff = []
        self._device_users = []
        self._build()
        self._load_local()

    def _build(self):
        # ── Top bar ───────────────────────────────────────────────────────────
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=4, pady=(4, 6))

        ctk.CTkLabel(top, text="Staff", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")

        self.count_label = ctk.CTkLabel(top, text="", text_color="#888",
                                        font=ctk.CTkFont(size=12))
        self.count_label.pack(side="right", padx=12)

        # ── View toggle ───────────────────────────────────────────────────────
        toggle = ctk.CTkFrame(self, fg_color="transparent")
        toggle.pack(fill="x", padx=4, pady=(0, 6))

        self.view_var = ctk.StringVar(value="si")
        ctk.CTkRadioButton(toggle, text="School Insights Staff",
                           variable=self.view_var, value="si",
                           command=self._switch_view).pack(side="left", padx=(0, 20))
        ctk.CTkRadioButton(toggle, text="Device Enrolled Users",
                           variable=self.view_var, value="device",
                           command=self._switch_view).pack(side="left")

        # Action button (changes with view)
        self.action_btn = ctk.CTkButton(toggle, text="Sync from School Insights",
                                        height=32, width=210,
                                        fg_color="#1565c0", hover_color="#0d47a1",
                                        command=self._action)
        self.action_btn.pack(side="right")

        # ── Search ────────────────────────────────────────────────────────────
        search_frame = ctk.CTkFrame(self, fg_color="transparent")
        search_frame.pack(fill="x", padx=4, pady=(0, 6))
        self.search_var = ctk.StringVar()
        self.search_var.trace("w", lambda *a: self._filter())
        ctk.CTkEntry(search_frame, textvariable=self.search_var,
                     placeholder_text="Search by name or ID...",
                     height=34).pack(fill="x")

        # ── Table header ──────────────────────────────────────────────────────
        self.header_frame = ctk.CTkFrame(self, fg_color="#263238", corner_radius=6, height=34)
        self.header_frame.pack(fill="x", padx=4)
        self.header_frame.pack_propagate(False)

        # ── Table ─────────────────────────────────────────────────────────────
        self.table = ctk.CTkScrollableFrame(self, corner_radius=6, fg_color="transparent")
        self.table.pack(fill="both", expand=True, padx=4, pady=(2, 4))

        self.status_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=12))
        self.status_label.pack(anchor="w", padx=8, pady=4)

        self._build_header_si()

    # ── Header builders ───────────────────────────────────────────────────────

    def _build_header_si(self):
        for w in self.header_frame.winfo_children():
            w.destroy()
        for text, width in [("#", 50), ("User ID", 80), ("Name", 280),
                             ("Email", 230), ("Roles", 200)]:
            ctk.CTkLabel(self.header_frame, text=text,
                         font=ctk.CTkFont(size=12, weight="bold"),
                         width=width, anchor="w").pack(side="left", padx=6, pady=6)

    def _build_header_device(self):
        for w in self.header_frame.winfo_children():
            w.destroy()
        for text, width in [("#", 50), ("Device ID", 100), ("Name", 320),
                             ("Privilege", 120), ("Card No", 160)]:
            ctk.CTkLabel(self.header_frame, text=text,
                         font=ctk.CTkFont(size=12, weight="bold"),
                         width=width, anchor="w").pack(side="left", padx=6, pady=6)

    # ── View switching ────────────────────────────────────────────────────────

    def _switch_view(self):
        if self.view_var.get() == "si":
            self._build_header_si()
            self.action_btn.configure(text="Sync from School Insights",
                                      fg_color="#1565c0", hover_color="#0d47a1")
            self._filter()
        else:
            self._build_header_device()
            self.action_btn.configure(text="Pull from Device",
                                      fg_color="#37474f", hover_color="#263238")
            self._filter()

    def _action(self):
        if self.view_var.get() == "si":
            self._sync_si()
        else:
            self._pull_device()

    # ── School Insights sync ──────────────────────────────────────────────────

    def _load_local(self):
        self._si_staff = db.get_all_staff()
        self._render_si(self._si_staff)

    def _sync_si(self):
        if not api_client.is_device_approved():
            self.status_label.configure(
                text="Device not approved. Complete registration first.", text_color="#ef9a9a")
            return
        self.status_label.configure(text="Syncing from School Insights...", text_color="#4fc3f7")

        def do():
            ok, result = api_client.get_staff_list()
            if ok:
                school_id = db.get_setting("si_school_id", "")
                db.save_staff(result, school_id)
                self._si_staff = db.get_all_staff()
                self.after(0, lambda: self._render_si(self._si_staff))
                self.after(0, lambda: self.status_label.configure(
                    text=f"Synced {len(self._si_staff)} staff from School Insights.",
                    text_color="#a5d6a7"))
            else:
                self.after(0, lambda: self.status_label.configure(
                    text=f"Sync failed: {result}", text_color="#ef9a9a"))

        threading.Thread(target=do, daemon=True).start()

    # ── Device user pull ──────────────────────────────────────────────────────

    def _pull_device(self):
        devices = [d for d in db.get_all_devices() if d["enabled"]]
        if not devices:
            self.status_label.configure(text="No enabled devices configured.", text_color="#ef9a9a")
            return
        self.status_label.configure(text="Pulling enrolled users from device...", text_color="#4fc3f7")

        def do():
            all_users = {}
            for device in devices:
                ok, result = get_device_users(device["ip"], device["port"], device["password"])
                if ok:
                    for u in result:
                        all_users[u["user_id"]] = u  # deduplicate by device user_id
                else:
                    self.after(0, lambda r=result, n=device["name"]: self.status_label.configure(
                        text=f"{n}: {r}", text_color="#ef9a9a"))
                    return

            self._device_users = list(all_users.values())
            self.after(0, lambda: self._render_device(self._device_users))
            self.after(0, lambda: self.status_label.configure(
                text=f"{len(self._device_users)} users on device. Syncing to School Insights…",
                text_color="#4fc3f7"))

            # Sync new users to School Insights
            ok, created_or_err, skipped = api_client.sync_device_users(self._device_users)
            if ok:
                n = created_or_err
                msg = (f"{len(self._device_users)} users on device. "
                       f"{n} new synced to School Insights, {skipped} already stored.")
                self.after(0, lambda m=msg: self.status_label.configure(
                    text=m, text_color="#a5d6a7"))
            else:
                self.after(0, lambda e=created_or_err: self.status_label.configure(
                    text=f"Pulled OK but SI sync failed: {e}", text_color="#ffb74d"))

        threading.Thread(target=do, daemon=True).start()

    # ── Filter ────────────────────────────────────────────────────────────────

    def _filter(self):
        query = self.search_var.get().lower()
        if self.view_var.get() == "si":
            filtered = [s for s in self._si_staff
                        if query in s["name"].lower()
                        or query in str(s.get("si_user_id", "")).lower()
                        or query in (s.get("email", "") or "").lower()
                        or query in (s.get("roles", "") or "").lower()]
            self._render_si(filtered)
        else:
            filtered = [u for u in self._device_users
                        if query in u["name"].lower()
                        or query in str(u["user_id"]).lower()]
            self._render_device(filtered)

    # ── Renderers ─────────────────────────────────────────────────────────────

    def _render_si(self, staff):
        for w in self.table.winfo_children():
            w.destroy()
        self.count_label.configure(text=f"{len(staff)} staff")

        if not staff:
            ctk.CTkLabel(self.table,
                         text="No staff found. Click 'Sync from School Insights' to load.",
                         text_color="#666").pack(pady=30)
            return

        for i, s in enumerate(staff):
            bg = "#1a1a2e" if i % 2 == 0 else "#1e1e2e"
            row = ctk.CTkFrame(self.table, fg_color=bg, corner_radius=4, height=32)
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)
            for text, width in [
                (str(i + 1),                     50),
                (str(s.get("si_user_id", "")),   80),
                (s.get("name", ""),             280),
                (s.get("email", ""),            230),
                (s.get("roles", ""),            200),
            ]:
                ctk.CTkLabel(row, text=text, width=width, anchor="w",
                             font=ctk.CTkFont(size=12)).pack(side="left", padx=6)

    def _render_device(self, users):
        for w in self.table.winfo_children():
            w.destroy()
        self.count_label.configure(text=f"{len(users)} users")

        if not users:
            ctk.CTkLabel(self.table,
                         text="No users found. Click 'Pull from Device' to load.",
                         text_color="#666").pack(pady=30)
            return

        for i, u in enumerate(users):
            bg = "#1a1a2e" if i % 2 == 0 else "#1e1e2e"
            row = ctk.CTkFrame(self.table, fg_color=bg, corner_radius=4, height=32)
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)

            priv_label = _PRIVILEGE.get(u["privilege"], str(u["privilege"]))
            priv_color = "#ffb74d" if u["privilege"] > 0 else "#ccc"

            for text, width in [
                (str(i + 1),         50),
                (str(u["user_id"]), 100),
                (u["name"],         320),
            ]:
                ctk.CTkLabel(row, text=text, width=width, anchor="w",
                             font=ctk.CTkFont(size=12)).pack(side="left", padx=6)

            ctk.CTkLabel(row, text=priv_label, width=120, anchor="w",
                         font=ctk.CTkFont(size=12),
                         text_color=priv_color).pack(side="left", padx=6)

            ctk.CTkLabel(row, text=u["card"] or "—", width=160, anchor="w",
                         font=ctk.CTkFont(size=12), text_color="#888").pack(side="left", padx=6)
