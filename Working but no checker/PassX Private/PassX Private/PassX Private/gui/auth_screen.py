import customtkinter as ctk
from tkinter import messagebox
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.api_client import APIClient
from gui.styles import COLORS, FONTS, BUTTON_STYLES, ENTRY_STYLES, FRAME_STYLES

class AuthScreen(ctk.CTkFrame):
    def __init__(self, parent, on_auth_success):
        super().__init__(parent, fg_color=COLORS["bg_dark"])
        self.parent = parent
        self.on_auth_success = on_auth_success
        self.api_client = APIClient()

        self.user_id = None
        self.otp_attempts = 0
        self.max_otp_attempts = 3

        self.create_widgets()

    def create_widgets(self):
        # Main container
        main_frame = ctk.CTkFrame(self, **FRAME_STYLES)
        main_frame.place(relx=0.5, rely=0.5, anchor="center")

        title_label = ctk.CTkLabel(
            main_frame,
            text="MS Account Password Changer",
            font=FONTS["title"],
            text_color=COLORS["text_white"]
        )
        title_label.pack(pady=(30, 10), padx=40)

        # Subtitle
        subtitle_label = ctk.CTkLabel(
            main_frame,
            text="Discord Authentication Required",
            font=FONTS["subtitle"],
            text_color=COLORS["accent_purple"]
        )
        subtitle_label.pack(pady=(0, 30), padx=40)

        # Discord ID input
        id_label = ctk.CTkLabel(
            main_frame,
            text="Enter Your Discord User ID:",
            font=FONTS["body_bold"],
            text_color=COLORS["text_white"]
        )
        id_label.pack(pady=(10, 5), padx=40)

        self.id_entry = ctk.CTkEntry(
            main_frame,
            **ENTRY_STYLES,
            width=300,
            placeholder_text="793101872784867352"
        )
        self.id_entry.pack(pady=(0, 20), padx=40)

        # Login button
        self.login_button = ctk.CTkButton(
            main_frame,
            text="Continue",
            command=self.check_authorization,
            **BUTTON_STYLES["primary"],
            width=300,
            font=FONTS["button"]
        )
        self.login_button.pack(pady=(0, 30), padx=40)

        # Status label
        self.status_label = ctk.CTkLabel(
            main_frame,
            text="",
            font=FONTS["body"],
            text_color=COLORS["text_gray"]
        )
        self.status_label.pack(pady=(0, 20), padx=40)

    def check_authorization(self):
        user_id = self.id_entry.get().strip()

        if not user_id:
            messagebox.showerror("Error", "Please enter your Discord User ID")
            return

        if not user_id.isdigit():
            messagebox.showerror("Error", "User ID must be numbers only")
            return

        self.user_id = user_id
        self.login_button.configure(state="disabled")
        self.status_label.configure(text="Checking authorization...", text_color=COLORS["warning"])

        self.parent.after(100, self._check_auth_async)

    def _check_auth_async(self):
        authorized, message = self.api_client.check_authorization(self.user_id)

        if authorized:
            self.status_label.configure(text="Authorized. Requesting OTP...", text_color=COLORS["success"])
            self.parent.after(500, self.request_otp)
        else:
            self.login_button.configure(state="normal")
            self.status_label.configure(text="", text_color=COLORS["text_gray"])
            self.show_not_authorized()

    def show_not_authorized(self):
        # Clear current widgets
        for widget in self.winfo_children():
            widget.destroy()

        # Not authorized message
        error_frame = ctk.CTkFrame(self, **FRAME_STYLES)
        error_frame.place(relx=0.5, rely=0.5, anchor="center")

        error_title = ctk.CTkLabel(
            error_frame,
            text="Not Authorized",
            font=FONTS["title"],
            text_color=COLORS["text_white"]
        )
        error_title.pack(pady=(40, 10), padx=60)

        error_msg = ctk.CTkLabel(
            error_frame,
            text="You are not authorized to use this application.\n\nPlease contact Steve to get authorization.",
            font=FONTS["body"],
            text_color=COLORS["text_gray"],
            justify="center"
        )
        error_msg.pack(pady=(0, 30), padx=60)

        close_button = ctk.CTkButton(
            error_frame,
            text="Close",
            command=self.parent.quit,
            **BUTTON_STYLES["danger"],
            width=200,
            font=FONTS["button"]
        )
        close_button.pack(pady=(0, 40), padx=60)

    def request_otp(self):
        success, message = self.api_client.request_otp(self.user_id)

        if success:
            self.status_label.configure(text="", text_color=COLORS["text_gray"])
            self.show_otp_screen()
        else:
            self.login_button.configure(state="normal")
            self.status_label.configure(text="", text_color=COLORS["text_gray"])
            messagebox.showerror("Error", f"Failed to request OTP: {message}")

    def show_otp_screen(self):
        # Clear current widgets
        for widget in self.winfo_children():
            widget.destroy()

        # OTP screen
        otp_frame = ctk.CTkFrame(self, **FRAME_STYLES)
        otp_frame.place(relx=0.5, rely=0.5, anchor="center")

        title_label = ctk.CTkLabel(
            otp_frame,
            text="OTP Sent",
            font=FONTS["title"],
            text_color=COLORS["text_white"]
        )
        title_label.pack(pady=(30, 10), padx=40)

        # Info
        info_label = ctk.CTkLabel(
            otp_frame,
            text="Check your Discord DMs for the OTP code.\n\nValid for 5 minutes. Max 3 attempts.",
            font=FONTS["body"],
            text_color=COLORS["text_gray"],
            justify="center"
        )
        info_label.pack(pady=(0, 20), padx=40)

        # OTP input
        otp_label = ctk.CTkLabel(
            otp_frame,
            text="Enter OTP:",
            font=FONTS["body_bold"],
            text_color=COLORS["text_white"]
        )
        otp_label.pack(pady=(10, 5), padx=40)

        self.otp_entry = ctk.CTkEntry(
            otp_frame,
            **ENTRY_STYLES,
            width=300,
            placeholder_text="123456",
            justify="center"
        )
        self.otp_entry.pack(pady=(0, 20), padx=40)

        # Verify button
        self.verify_button = ctk.CTkButton(
            otp_frame,
            text="Verify OTP",
            command=self.verify_otp,
            **BUTTON_STYLES["success"],
            width=300,
            font=FONTS["button"]
        )
        self.verify_button.pack(pady=(0, 10), padx=40)

        # Attempts counter
        self.attempts_label = ctk.CTkLabel(
            otp_frame,
            text=f"Attempts remaining: {self.max_otp_attempts - self.otp_attempts}",
            font=FONTS["small"],
            text_color=COLORS["text_gray"]
        )
        self.attempts_label.pack(pady=(0, 30), padx=40)

        # Focus on OTP entry
        self.otp_entry.focus()

    def verify_otp(self):
        otp = self.otp_entry.get().strip()

        if not otp:
            messagebox.showerror("Error", "Please enter the OTP")
            return

        if not otp.isdigit() or len(otp) != 6:
            messagebox.showerror("Error", "OTP must be 6 digits")
            return

        self.verify_button.configure(state="disabled")

        # Verify with server
        success, message = self.api_client.verify_otp(self.user_id, otp)

        if success:
            # MODIFIED: Save session after successful authentication
            from utils.session_manager import save_session
            save_session(self.user_id)

            messagebox.showinfo("Success", "Authentication successful!\nYour session has been saved.")
            self.on_auth_success(self.user_id)
        else:
            self.otp_attempts += 1
            remaining = self.max_otp_attempts - self.otp_attempts

            if remaining > 0:
                self.verify_button.configure(state="normal")
                self.otp_entry.delete(0, "end")
                self.attempts_label.configure(text=f"Attempts remaining: {remaining}")
                messagebox.showerror("Error", message)
            else:
                messagebox.showerror("Error", "Maximum attempts exceeded. Please restart the application.")
                self.parent.quit()

