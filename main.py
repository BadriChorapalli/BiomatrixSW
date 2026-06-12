import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app.core.database import init_db
from app.ui.login_window import LoginWindow
from app.ui.main_window import MainWindow

_START_HIDDEN = "--startup" in sys.argv


def launch_main():
    app = MainWindow(start_hidden=_START_HIDDEN)
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()


def main():
    init_db()
    login = LoginWindow(on_success=launch_main)
    login.mainloop()


if __name__ == "__main__":
    main()
