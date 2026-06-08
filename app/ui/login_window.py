import customtkinter as ctk
import hashlib
from ..core import database as db


def _hash(password):
    return hashlib.sha256(password.encode()).hexdigest()


def _ensure_default_user():
    if not db.get_setting("auth_username"):
        db.set_setting("auth_username", "admin")
        db.set_setting("auth_password", _hash("admin123"))


class LoginWindow(ctk.CTk):
    def __init__(self, on_success):
        super().__init__()
        self.on_success = on_success
        self.title("Biomatrix Sync")
        self.geometry("420x520")
        self.resizable(False, False)
        _ensure_default_user()
        self._build()
        self._center()

    def _center(self):
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 420) // 2
        y = (self.winfo_screenheight() - 520) // 2
        self.geometry(f"420x520+{x}+{y}")

    def _build(self):
        # Background
        self.configure(fg_color="#0f0f1a")

        # Logo / header area
        header = ctk.CTkFrame(self, fg_color="#1a1a2e", corner_radius=0, height=160)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(header, text="B", font=ctk.CTkFont(size=52, weight="bold"),
                     text_color="#4fc3f7").pack(pady=(28, 0))
        ctk.CTkLabel(header, text="BiomatrixSync", font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="white").pack()
        ctk.CTkLabel(header, text="by BellWeather", font=ctk.CTkFont(size=11),
                     text_color="#555").pack()

        # Form
        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=40, pady=30)

        ctk.CTkLabel(form, text="Sign In", font=ctk.CTkFont(size=20, weight="bold"),
                     text_color="white").pack(anchor="w", pady=(0, 20))

        ctk.CTkLabel(form, text="Username", text_color="#aaa",
                     font=ctk.CTkFont(size=12)).pack(anchor="w")
        self.username_entry = ctk.CTkEntry(form, height=42, corner_radius=8,
                                           placeholder_text="Enter username",
                                           font=ctk.CTkFont(size=13))
        self.username_entry.pack(fill="x", pady=(4, 14))
        self.username_entry.insert(0, "admin")

        ctk.CTkLabel(form, text="Password", text_color="#aaa",
                     font=ctk.CTkFont(size=12)).pack(anchor="w")
        self.password_entry = ctk.CTkEntry(form, height=42, corner_radius=8,
                                           placeholder_text="Enter password",
                                           show="*", font=ctk.CTkFont(size=13))
        self.password_entry.pack(fill="x", pady=(4, 6))
        self.password_entry.bind("<Return>", lambda e: self._login())

        self.error_label = ctk.CTkLabel(form, text="", text_color="#ef9a9a",
                                        font=ctk.CTkFont(size=12))
        self.error_label.pack(anchor="w", pady=(2, 12))

        ctk.CTkButton(form, text="Sign In", height=44, corner_radius=8,
                      font=ctk.CTkFont(size=14, weight="bold"),
                      fg_color="#1565c0", hover_color="#0d47a1",
                      command=self._login).pack(fill="x")

        ctk.CTkLabel(self, text="Default: admin / admin123",
                     text_color="#333", font=ctk.CTkFont(size=11)).pack(pady=(0, 12))

    def _login(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()

        stored_user = db.get_setting("auth_username", "admin")
        stored_pass = db.get_setting("auth_password", _hash("admin123"))

        if username == stored_user and _hash(password) == stored_pass:
            self.destroy()
            self.on_success()
        else:
            self.error_label.configure(text="Invalid username or password.")
            self.password_entry.delete(0, "end")
