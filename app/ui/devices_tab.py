import customtkinter as ctk
import threading
from ..core import database as db
from ..core.device import test_connection

BRANDS = ["eSSL", "ZKTeco", "Realtime", "FingerTec", "Anviz", "Matrix", "Morx", "Other"]
PROTOCOLS = ["TCP (default)", "UDP (older devices)"]


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

        # Text fields
        text_fields = [
            ("Device Name", "e.g. Main Gate"),
            ("IP Address",  "e.g. 192.168.100.9"),
            ("Port",        "4370"),
            ("Password (0 if none)", "0"),
        ]
        self.entries = {}
        for label, placeholder in text_fields:
            ctk.CTkLabel(form, text=label, anchor="w").pack(fill="x", pady=(8, 2))
            e = ctk.CTkEntry(form, placeholder_text=placeholder, height=36)
            e.pack(fill="x")
            self.entries[label] = e

        # Brand dropdown
        ctk.CTkLabel(form, text="Device Brand", anchor="w").pack(fill="x", pady=(8, 2))
        self.brand_var = ctk.StringVar(value=BRANDS[0])
        self.brand_menu = ctk.CTkOptionMenu(
            form, variable=self.brand_var, values=BRANDS, height=36,
            command=self._on_brand_change)
        self.brand_menu.pack(fill="x")

        # Protocol dropdown
        ctk.CTkLabel(form, text="Connection Protocol", anchor="w").pack(fill="x", pady=(8, 2))
        self.protocol_var = ctk.StringVar(value=PROTOCOLS[0])
        self.protocol_menu = ctk.CTkOptionMenu(form, variable=self.protocol_var, values=PROTOCOLS, height=36)
        self.protocol_menu.pack(fill="x")

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
            brand = device.get("brand") or "eSSL"
            proto = "UDP" if device.get("force_udp") else "TCP"
            label = f"{device['name']}\n{device['ip']}  •  {brand} / {proto}"
            btn = ctk.CTkButton(self.list_frame, text=label,
                                anchor="w", fg_color="#1e1e2e", hover_color="#263238",
                                command=lambda d=device: self._load_device(d), height=52)
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
        brand = device.get("brand") or "eSSL"
        self.brand_var.set(brand if brand in BRANDS else "Other")
        self.protocol_var.set(PROTOCOLS[1] if device.get("force_udp") else PROTOCOLS[0])
        self.status_label.configure(text="")
        self.delete_btn.pack(side="right")

    def _clear_form(self):
        self._editing_id = None
        for e in self.entries.values():
            e.delete(0, "end")
        self.entries["Port"].insert(0, "4370")
        self.entries["Password (0 if none)"].insert(0, "0")
        self.brand_var.set(BRANDS[0])
        self.protocol_var.set(PROTOCOLS[0])
        self.status_label.configure(text="")
        self.delete_btn.pack_forget()

    def _on_brand_change(self, brand):
        port_entry = self.entries["Port"]
        current_port = port_entry.get().strip()
        if brand == "Morx":
            port_entry.delete(0, "end")
            port_entry.insert(0, "5005")
        elif current_port == "5005":
            port_entry.delete(0, "end")
            port_entry.insert(0, "4370")

    def _force_udp(self):
        return 1 if self.protocol_var.get() == PROTOCOLS[1] else 0

    def _test_connection(self):
        ip = self.entries["IP Address"].get().strip()
        port = self.entries["Port"].get().strip() or "4370"
        pwd = self.entries["Password (0 if none)"].get().strip() or "0"
        if not ip:
            self.status_label.configure(text="Enter an IP address first.", text_color="#ef9a9a")
            return
        force_udp = bool(self._force_udp())
        proto = "UDP" if force_udp else "TCP"
        self.status_label.configure(text=f"Testing ({proto})…", text_color="#4fc3f7")

        def do_test():
            ok, msg = test_connection(ip, port, pwd, force_udp=force_udp,
                                      brand=self.brand_var.get())
            color = "#a5d6a7" if ok else "#ef9a9a"
            self.after(0, lambda: self.status_label.configure(text=msg, text_color=color))

        threading.Thread(target=do_test, daemon=True).start()

    def _save_device(self):
        name = self.entries["Device Name"].get().strip()
        ip   = self.entries["IP Address"].get().strip()
        port = self.entries["Port"].get().strip() or "4370"
        pwd  = self.entries["Password (0 if none)"].get().strip() or "0"
        brand     = self.brand_var.get()
        force_udp = self._force_udp()

        if not name or not ip:
            self.status_label.configure(text="Name and IP are required.", text_color="#ef9a9a")
            return

        if self._editing_id:
            db.update_device(self._editing_id, name, ip, port, pwd, brand, force_udp)
            self.status_label.configure(text="Device updated.", text_color="#a5d6a7")
        else:
            db.add_device(name, ip, port, pwd, brand, force_udp)
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
