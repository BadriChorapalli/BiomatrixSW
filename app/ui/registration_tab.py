import customtkinter as ctk
import threading
import time
from ..core import api_client
from ..core import database as db


class RegistrationTab(ctk.CTkFrame):
    def __init__(self, parent, main_window):
        super().__init__(parent, fg_color="transparent")
        self.main_window = main_window
        self.pack(fill="both", expand=True)
        self._orgs = []
        self._schools = []
        self._polling = False
        self._build()
        self._check_existing_status()

    def _build(self):
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=4, pady=4)

        # Status banner
        self.status_banner = ctk.CTkFrame(scroll, corner_radius=8, height=52, fg_color="#1e1e2e")
        self.status_banner.pack(fill="x", padx=4, pady=(4, 12))
        self.status_banner.pack_propagate(False)
        self.banner_icon = ctk.CTkLabel(self.status_banner, text="○", font=ctk.CTkFont(size=18),
                                        text_color="#666")
        self.banner_icon.pack(side="left", padx=(16, 8))
        self.banner_label = ctk.CTkLabel(self.status_banner, text="Device not registered",
                                         font=ctk.CTkFont(size=13), text_color="#888")
        self.banner_label.pack(side="left")

        # Step 1 - Organization
        self._section(scroll, "Step 1 — Select Organization")
        org_row = ctk.CTkFrame(scroll, fg_color="transparent")
        org_row.pack(fill="x", padx=16, pady=(4, 0))
        self.org_var = ctk.StringVar(value="Select organization...")
        self.org_menu = ctk.CTkOptionMenu(org_row, variable=self.org_var,
                                          values=["Select organization..."],
                                          command=self._on_org_select, width=320, height=36)
        self.org_menu.pack(side="left")
        ctk.CTkButton(org_row, text="Load", width=70, height=36,
                      command=self._load_orgs).pack(side="left", padx=8)

        # Step 2 - School
        self._section(scroll, "Step 2 — Select School")
        self.school_var = ctk.StringVar(value="Select school...")
        self.school_menu = ctk.CTkOptionMenu(scroll, variable=self.school_var,
                                             values=["Select school..."],
                                             width=320, height=36)
        self.school_menu.pack(anchor="w", padx=16, pady=(4, 0))

        # Step 3 - Device Info
        self._section(scroll, "Step 3 — Device Info")
        ctk.CTkLabel(scroll, text="Device Name", anchor="w").pack(fill="x", padx=16, pady=(4, 2))
        self.device_name = ctk.CTkEntry(scroll, placeholder_text="e.g. Main Gate Biometric",
                                        height=36)
        self.device_name.pack(fill="x", padx=16)

        ctk.CTkLabel(scroll, text="Location", anchor="w").pack(fill="x", padx=16, pady=(10, 2))
        self.location = ctk.CTkEntry(scroll, placeholder_text="e.g. School Front Gate",
                                     height=36)
        self.location.pack(fill="x", padx=16)

        # Device ID display
        device_id = api_client._get_device_id()
        ctk.CTkLabel(scroll, text=f"Device ID: {device_id[:24]}...",
                     text_color="#555", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=16, pady=(8, 0))

        # Submit
        self.submit_btn = ctk.CTkButton(scroll, text="Submit Registration Request",
                                        height=42, font=ctk.CTkFont(size=13, weight="bold"),
                                        fg_color="#1565c0", hover_color="#0d47a1",
                                        command=self._submit)
        self.submit_btn.pack(fill="x", padx=16, pady=16)

        self.msg_label = ctk.CTkLabel(scroll, text="", font=ctk.CTkFont(size=12),
                                      wraplength=500)
        self.msg_label.pack(anchor="w", padx=16)

        # Approval status section
        self._section(scroll, "Approval Status")
        self.approval_frame = ctk.CTkFrame(scroll, fg_color="#1e1e2e", corner_radius=8)
        self.approval_frame.pack(fill="x", padx=16, pady=(4, 0))

        self.request_label = ctk.CTkLabel(self.approval_frame, text="No pending request",
                                          text_color="#666", font=ctk.CTkFont(size=12))
        self.request_label.pack(anchor="w", padx=12, pady=(10, 4))

        self.approval_status = ctk.CTkLabel(self.approval_frame, text="",
                                            font=ctk.CTkFont(size=13, weight="bold"))
        self.approval_status.pack(anchor="w", padx=12, pady=(0, 4))

        check_row = ctk.CTkFrame(self.approval_frame, fg_color="transparent")
        check_row.pack(fill="x", padx=8, pady=(0, 10))
        ctk.CTkButton(check_row, text="Check Status", width=120, height=32,
                      fg_color="#37474f", command=self._check_status).pack(side="left", padx=4)
        self.poll_btn = ctk.CTkButton(check_row, text="Auto Poll", width=100, height=32,
                                      fg_color="#2e7d32", hover_color="#1b5e20",
                                      command=self._toggle_poll)
        self.poll_btn.pack(side="left", padx=4)

    def _section(self, parent, title):
        ctk.CTkLabel(parent, text=title,
                     font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=16, pady=(16, 2))
        ctk.CTkFrame(parent, height=1, fg_color="#333").pack(fill="x", padx=16, pady=(0, 4))

    def _check_existing_status(self):
        status = db.get_setting("si_device_status", "")
        request_id = db.get_setting("si_request_id", "")
        if status == "APPROVED":
            self._set_banner("APPROVED")
        elif status == "PENDING" and request_id:
            self._set_banner("PENDING")
            self.request_label.configure(text=f"Request ID: {request_id}")
        elif status == "REJECTED":
            self._set_banner("REJECTED")

    def _set_banner(self, status):
        colors = {
            "APPROVED": ("#a5d6a7", "✓  Device Approved — Connected to School Insights", "#1b5e20"),
            "PENDING":  ("#fff176", "⏳  Awaiting approval from School Insights admin", "#f57f17"),
            "REJECTED": ("#ef9a9a", "✗  Registration rejected", "#b71c1c"),
        }
        text_color, label, bg = colors.get(status, ("#888", "Not registered", "#1e1e2e"))
        self.status_banner.configure(fg_color=bg)
        self.banner_icon.configure(text_color=text_color)
        self.banner_label.configure(text=label, text_color=text_color)
        self.approval_status.configure(text=f"Status: {status}",
                                       text_color=text_color)

    def _load_orgs(self):
        self.org_menu.configure(values=["Loading..."])
        self.msg_label.configure(text="Fetching organizations...", text_color="#4fc3f7")

        def do():
            ok, result = api_client.get_organizations()
            if ok:
                self._orgs = result
                names = [f"{o.get('name', o.get('id'))} (ID:{o['id']})" for o in result]
                self.after(0, lambda: self.org_menu.configure(values=names))
                self.after(0, lambda: self.org_var.set(names[0] if names else "No organizations"))
                self.after(0, lambda: self.msg_label.configure(
                    text=f"Loaded {len(result)} organizations.", text_color="#a5d6a7"))
            else:
                self.after(0, lambda: self.msg_label.configure(
                    text=f"Failed: {result}", text_color="#ef9a9a"))

        threading.Thread(target=do, daemon=True).start()

    def _on_org_select(self, value):
        org = self._get_selected_org()
        if not org:
            return
        self.school_menu.configure(values=["Loading..."])

        def do():
            ok, result = api_client.get_schools(org["id"])
            if ok:
                self._schools = result
                names = [f"{s.get('name', s.get('id'))} (ID:{s['id']})" for s in result]
                self.after(0, lambda: self.school_menu.configure(values=names))
                self.after(0, lambda: self.school_var.set(names[0] if names else "No schools"))
            else:
                self.after(0, lambda: self.school_menu.configure(values=[f"Error: {result}"]))

        threading.Thread(target=do, daemon=True).start()

    def _get_selected_org(self):
        val = self.org_var.get()
        for o in self._orgs:
            if str(o["id"]) in val:
                return o
        return None

    def _get_selected_school(self):
        val = self.school_var.get()
        for s in self._schools:
            if str(s["id"]) in val:
                return s
        return None

    def _submit(self):
        org = self._get_selected_org()
        school = self._get_selected_school()
        name = self.device_name.get().strip()
        loc = self.location.get().strip()

        if not org:
            self.msg_label.configure(text="Please select an organization.", text_color="#ef9a9a")
            return
        if not school:
            self.msg_label.configure(text="Please select a school.", text_color="#ef9a9a")
            return
        if not name:
            self.msg_label.configure(text="Please enter a device name.", text_color="#ef9a9a")
            return
        if not loc:
            self.msg_label.configure(text="Please enter a location.", text_color="#ef9a9a")
            return

        self.submit_btn.configure(state="disabled", text="Submitting...")
        self.msg_label.configure(text="Submitting registration request...", text_color="#4fc3f7")

        def do():
            ok, result = api_client.submit_device_request(org["id"], school["id"], name, loc)
            if ok:
                self.after(0, lambda: self.request_label.configure(
                    text=f"Request ID: {result}"))
                self.after(0, lambda: self._set_banner("PENDING"))
                self.after(0, lambda: self.msg_label.configure(
                    text="Request submitted! Ask your School Insights admin to approve it.",
                    text_color="#a5d6a7"))
                self.after(0, self._toggle_poll)
            else:
                self.after(0, lambda: self.msg_label.configure(
                    text=f"Failed: {result}", text_color="#ef9a9a"))
            self.after(0, lambda: self.submit_btn.configure(
                state="normal", text="Submit Registration Request"))

        threading.Thread(target=do, daemon=True).start()

    def _check_status(self):
        def do():
            ok, result = api_client.check_approval_status()
            if ok:
                status = result.get("status", "PENDING")
                self.after(0, lambda: self._set_banner(status))
                if status == "APPROVED":
                    self.after(0, lambda: self.msg_label.configure(
                        text="Device approved! Attendance sync is now active.",
                        text_color="#a5d6a7"))
                    self._polling = False
                    self.after(0, lambda: self.poll_btn.configure(text="Auto Poll"))
                    self.after(0, self.main_window.dashboard.refresh)
                elif status == "REJECTED":
                    reason = result.get("rejection_reason", "No reason given.")
                    self.after(0, lambda: self.msg_label.configure(
                        text=f"Rejected: {reason}", text_color="#ef9a9a"))
                    self._polling = False
            else:
                self.after(0, lambda: self.msg_label.configure(
                    text=f"Check failed: {result}", text_color="#ef9a9a"))

        threading.Thread(target=do, daemon=True).start()

    def _toggle_poll(self):
        if self._polling:
            self._polling = False
            self.poll_btn.configure(text="Auto Poll", fg_color="#2e7d32")
        else:
            self._polling = True
            self.poll_btn.configure(text="Stop Polling", fg_color="#c62828")
            threading.Thread(target=self._poll_loop, daemon=True).start()

    def _poll_loop(self):
        while self._polling:
            ok, result = api_client.check_approval_status()
            if ok:
                status = result.get("status", "PENDING")
                self.after(0, lambda s=status: self._set_banner(s))
                if status in ("APPROVED", "REJECTED"):
                    self._polling = False
                    self.after(0, lambda: self.poll_btn.configure(
                        text="Auto Poll", fg_color="#2e7d32"))
                    if status == "APPROVED":
                        self.after(0, lambda: self.msg_label.configure(
                            text="Device approved! Attendance sync is now active.",
                            text_color="#a5d6a7"))
                        self.after(0, self.main_window.dashboard.refresh)
                    break
            for _ in range(10):
                if not self._polling:
                    break
                time.sleep(1)
