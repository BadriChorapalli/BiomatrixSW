import sys
import os

# Ensure the app directory is in sys.path when running as a frozen exe
if getattr(sys, "frozen", False):
    _base = os.path.dirname(sys.executable)
else:
    _base = os.path.dirname(os.path.abspath(__file__))
if _base not in sys.path:
    sys.path.insert(0, _base)

import datetime
import win32serviceutil
import win32service
import win32event
import servicemanager

_LOG_PATH = os.path.join(
    os.environ.get("PROGRAMDATA", r"C:\ProgramData"),
    "BiomatrixSync", "service.log",
)


def _log(msg):
    try:
        os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  {msg}\n")
    except Exception:
        pass


class BiomatrixSyncService(win32serviceutil.ServiceFramework):
    _svc_name_ = "BiomatrixSync"
    _svc_display_name_ = "Biomatrix Sync — BellWeather"
    _svc_description_ = "Biometric attendance sync service for BellWeather School Insights"

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self._stop_event = win32event.CreateEvent(None, 0, 0, None)

    def SvcStop(self):
        _log("Service stopping...")
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self._stop_event)
        try:
            from app.core import scheduler
            scheduler.stop()
            scheduler.stop_device_poll()
        except Exception as exc:
            _log(f"Stop error: {exc}")

    def SvcDoRun(self):
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )
        _log("Service started")
        try:
            from app.core.database import init_db
            from app.core import scheduler

            init_db()
            scheduler.start(log_callback=_log)
            scheduler.start_device_poll(log_callback=_log)
            _log("Scheduler and device poll running")
        except Exception as exc:
            _log(f"Startup error: {exc}")
            servicemanager.LogErrorMsg(f"BiomatrixSync service startup failed: {exc}")
            return

        # Block until SvcStop signals us
        win32event.WaitForSingleObject(self._stop_event, win32event.INFINITE)
        _log("Service stopped")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        # Started by the SCM — hand control to the service dispatcher
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(BiomatrixSyncService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        # Called manually: install / remove / start / stop
        win32serviceutil.HandleCommandLine(BiomatrixSyncService)
