import sys
import os

_APP_NAME = "BiomatrixSync"
_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _exe_path():
    if getattr(sys, "frozen", False):
        return sys.executable
    return os.path.abspath(sys.argv[0])


def enable():
    if sys.platform != "win32":
        return False
    import winreg
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_PATH, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, f'"{_exe_path()}" --startup')
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def disable():
    if sys.platform != "win32":
        return
    import winreg
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_PATH, 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, _APP_NAME)
        winreg.CloseKey(key)
    except Exception:
        pass


def is_enabled():
    if sys.platform != "win32":
        return False
    import winreg
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_PATH, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, _APP_NAME)
        winreg.CloseKey(key)
        return True
    except Exception:
        return False
