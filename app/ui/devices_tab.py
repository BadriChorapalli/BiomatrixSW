import customtkinter as ctk
import threading
from ..core import database as db
from ..core.device import test_connection


class DevicesTab(ctk.CTkFrame):
    def __init__(self, parent, main_window):
        super().__init__(parent, fg_color="transparent")
        self.main_window = main_window
        self.pack(fill="both", expand=True)
        self._editing_id = None
        self._build()

    def _build(self):
        # Left: device list
        left = ctk.CTkFrame(self, corner_radius=8, width=260)
        left.pack(side="left", fill="y", padx=(4, 6), pady=4)
        left.pack_propagate(False)

        ctk.CTkLabel(left, text="Devices", font=ctk.CTkFont(size=13, weight="bold")).pack(
            anchor="w", padx=12, pady=(10, 4))

        self.list_frame = ctk.CTkScrollableFrame(left, corner_radius=0, fg_color="transparent")
        self.list_frame.pack(fill="both", expand=True)

        ctk.CTkButton(left, text="+ Add New Device", command=self._clear_form, height=34).pack(
            fill="x", padx=8, pady=8)

        # Right: form
        right = ctk.CTkFrame(self, corner_radius=8)
        right.pack(side="left", fill="both", expand=True, padx=(0, 4), pady=4)

        ctk.CTkLabel(right, text="Device Configuration",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=16, pady=(12, 8))

        form = ctk.CTkFrame(right, fg_color="transparent")
        form.pack(fill="x", padx=16)

        fields = [("Device Name", "e.g. Main Gate"), ("IP Address", "e.g. 192.168.100.9"),
                  ("Port", "4370"), ("Password (0 if none)", "0")]
        self.entries = {}
        for label, placeholder in fields:
            ctk.CTkLabel(form, text=label, anchor="w").pack(fill="x", pady=(8, 2))
            e = ctk.CTkEntry(form, placeholder_text=placeholder, height=36)
            e.pack(fill="x")
            self.entries[label] = e

        # Status label
        self.status_label = ctk.CTkLabel(right, text="", text_color="#4fc3f7")
        self.status_label.pack(anchor="w", padx=16, pady=6)

        # Buttons
        btn_row = ctk.CTkFrame(right, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=4)

        ctk.CTkButton(btn_row, text="Test Connection", fg_color="#37474f", hover_color="#263238",
                      command=self._test_connection, height=36).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="Save Device", command=self._save_device, height=36).pack(side="left")

        self.delete_btn = ctk.CTkButton(btn_row, text="Delete", fg_color="#c62828",
                                        hover_color="#b71c1c", command=self._delete_device,
                                        height=36, width=80)

        self._refresh_list()

    def _refresh_list(self):
        for w in self.list_frame.winfo_children():
            w.destroy()
        for device in db.get_all_devices():
            btn = ctk.CTkButton(self.list_frame, text=f"{device['name']}\n{device['ip']}",
                                anchor="w", fg_color="#1e1e2e", hover_color="#263238",
                                command=lambda d=device: self._load_device(d), height=48)
            btn.pack(fill="x", pady=2)

    def _load_device(self, device):
        self._editing_id = device["id"]
        self.entries["Device Name"].delete(0, "end")
        self.entries["Device Name"].insert(0, device["name"])
        self.entries["IP Address"].delete(0, "end")
        self.entries["IP Address"].insert(0, device["ip"])
        self.entries["Port"].delete(0, "end")
        self.entries["Port"].insert(0, str(device["port"]))
        self.entries["Password (0 if none)"].delete(0, "end")
        self.entries["Password (0 if none)"].insert(0, str(device["password"]))
        self.status_label.configure(text="")
        self.delete_btn.pack(side="right")

    def _clear_form(self):
        self._editing_id = None
        for e in self.entries.values():
            e.delete(0, "end")
        self.entries["Port"].insert(0, "4370")
        self.entries["Password (0 if none)"].insert(0, "0")
        self.status_label.configure(text="")
        self.delete_btn.pack_forget()

    def _test_connection(self):
        ip = self.entries["IP Address"].get().strip()
        port = self.entries["Port"].get().strip() or "4370"
        pwd = self.entries["Password (0 if none)"].get().strip() or "0"
        if not ip:
            self.status_label.configure(text="Enter an IP address first.", text_color="#ef9a9a")
            return
        self.status_label.configure(text="Testing...", text_color="#4fc3f7")

        def do_test():
            ok, msg = test_connection(ip, port, pwd)
            color = "#a5d6a7" if ok else "#ef9a9a"
            self.after(0, lambda: self.status_label.configure(text=msg, text_color=color))

        threading.Thread(target=do_test, daemon=True).start()

    def _save_device(self):
        name = self.entries["Device Name"].get().strip()
        ip = self.entries["IP Address"].get().strip()
        port = self.entries["Port"].get().strip() or "4370"
        pwd = self.entries["Password (0 if none)"].get().strip() or "0"

        if not name or not ip:
            self.status_label.configure(text="Name and IP are required.", text_color="#ef9a9a")
            return

        if self._editing_id:
            db.update_device(self._editing_id, name, ip, port, pwd)
            self.status_label.configure(text="Device updated.", text_color="#a5d6a7")
        else:
            db.add_device(name, ip, port, pwd)
            self.status_label.configure(text="Device added.", text_color="#a5d6a7")
            self._clear_form()

        self._refresh_list()
        self.main_window.dashboard.refresh()

    def _delete_device(self):
        if self._editing_id:
            db.delete_device(self._editing_id)
            self._clear_form()
            self._refresh_list()
            self.main_window.dashboard.refresh()
