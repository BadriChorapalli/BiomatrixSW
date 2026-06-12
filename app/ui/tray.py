import sys
import threading


def _make_icon_image():
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([2, 2, 62, 62], fill=(79, 195, 247))
    draw.ellipse([20, 20, 44, 44], fill=(26, 26, 46))
    return img


class TrayIcon:
    """System-tray icon (Windows only). All methods are no-ops on other platforms."""

    def __init__(self, on_show, on_quit):
        self._on_show = on_show
        self._on_quit = on_quit
        self._icon = None

    def start(self):
        if sys.platform != "win32":
            return
        try:
            import pystray
        except ImportError:
            return

        def _show(icon, item):
            icon.stop()
            self._icon = None
            self._on_show()

        def _quit(icon, item):
            icon.stop()
            self._icon = None
            self._on_quit()

        menu = pystray.Menu(
            pystray.MenuItem("Show BiomatrixSync", _show, default=True),
            pystray.MenuItem("Quit", _quit),
        )
        self._icon = pystray.Icon("BiomatrixSync", _make_icon_image(), "Biomatrix Sync", menu)
        threading.Thread(target=self._icon.run, daemon=True).start()

    def stop(self):
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None
