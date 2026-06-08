import customtkinter as ctk
from .dashboard_tab import DashboardTab
from .devices_tab import DevicesTab
from .settings_tab import SettingsTab
from .logs_tab import LogsTab
from .history_tab import HistoryTab
from .registration_tab import RegistrationTab
from .staff_tab import StaffTab
from .mapping_tab import MappingTab
from .device_config_tab import DeviceConfigTab
from ..core import scheduler

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Biomatrix Sync — BellWeather")
        self.geometry("900x620")
        self.minsize(800, 560)
        self._build_ui()
        scheduler.start(log_callback=self.append_log)
        # Start auto-pull if enabled in settings
        from ..core import database as _db
        if _db.get_setting("auto_pull_enabled", "1") == "1":
            try:
                interval = int(_db.get_setting("auto_pull_interval", "5"))
            except ValueError:
                interval = 5
            scheduler.start_device_poll(
                interval_minutes=interval,
                log_callback=self.append_log,
            )

    def _build_ui(self):
        # Header
        header = ctk.CTkFrame(self, height=50, corner_radius=0, fg_color="#1a1a2e")
        header.pack(fill="x")
        ctk.CTkLabel(header, text="  Biomatrix Sync", font=ctk.CTkFont(size=18, weight="bold"),
                     text_color="#4fc3f7").pack(side="left", padx=16, pady=10)
        ctk.CTkLabel(header, text="BellWeather", font=ctk.CTkFont(size=12),
                     text_color="#666").pack(side="right", padx=16)

        # Tab view
        self.tabs = ctk.CTkTabview(self, corner_radius=8)
        self.tabs.pack(fill="both", expand=True, padx=12, pady=(8, 12))

        for name in ["Dashboard", "History", "Staff", "Mapping", "SI Config",
                     "Devices", "Registration", "Settings", "Logs"]:
            self.tabs.add(name)

        self.dashboard = DashboardTab(self.tabs.tab("Dashboard"), self)
        self.history = HistoryTab(self.tabs.tab("History"), self)
        self.staff = StaffTab(self.tabs.tab("Staff"), self)
        self.mapping = MappingTab(self.tabs.tab("Mapping"), self)
        self.device_config = DeviceConfigTab(self.tabs.tab("SI Config"), self)
        self.devices = DevicesTab(self.tabs.tab("Devices"), self)
        self.registration = RegistrationTab(self.tabs.tab("Registration"), self)
        self.settings = SettingsTab(self.tabs.tab("Settings"), self)
        self.logs_tab = LogsTab(self.tabs.tab("Logs"))

    def append_log(self, message):
        self.after(0, self.logs_tab.append, message)

    def on_closing(self):
        scheduler.stop()
        scheduler.stop_device_poll()
        self.destroy()
