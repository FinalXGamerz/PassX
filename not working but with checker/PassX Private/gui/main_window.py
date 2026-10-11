import customtkinter as ctk
from tkinter import messagebox, filedialog
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gui.styles import COLORS, FONTS, BUTTON_STYLES, ENTRY_STYLES, FRAME_STYLES
from gui.processing_screen import ProcessingScreen
from utils.password_generator import generate_shulker_password

class MainWindow(ctk.CTkFrame):
    def __init__(self, parent, user_id):
        super().__init__(parent, fg_color=COLORS["bg_dark"])
        self.parent = parent
        self.user_id = user_id
        self.accounts = []  # List of {email, password} dicts
        self.auto_password = ctk.BooleanVar(value=True)

        self.create_widgets()
        self.clear_all_accounts()

    def create_widgets(self):

        top_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_medium"], height=80)
        top_frame.pack(fill="x", padx=20, pady=(20, 10))
        top_frame.pack_propagate(False)

        title_label = ctk.CTkLabel(
            top_frame,
            text="MS Account Password Changer",
            font=FONTS["title"],
            text_color=COLORS["text_white"]
        )
        title_label.pack(side="left", padx=20, pady=20)


        user_label = ctk.CTkLabel(
            top_frame,
            text=f"Discord ID: {self.user_id}",
            font=FONTS["body"],
            text_color=COLORS["text_gray"]
        )
        user_label.pack(side="right", padx=20, pady=20)
        
        logout_button = ctk.CTkButton(
            top_frame,
            text="Logout",
            command=self.logout,
            fg_color=COLORS["error"],
            hover_color="#DC2626",
            text_color=COLORS["text_white"],
            corner_radius=8,
            width=100,
            height=35,
            font=FONTS["body"]
        )
        logout_button.pack(side="right", padx=10, pady=20)


        content_frame = ctk.CTkFrame(self, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=20, pady=10)


        left_frame = ctk.CTkFrame(content_frame, **FRAME_STYLES, width=400)
        left_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))

        input_title = ctk.CTkLabel(
            left_frame,
            text="Add Accounts",
            font=FONTS["heading"],
            text_color=COLORS["text_white"]
        )
        input_title.pack(pady=(20, 10), padx=20)


        add_single_btn = ctk.CTkButton(
            left_frame,
            text="Add Single Account",
            command=self.add_single_account,
            **BUTTON_STYLES["primary"],
            width=250,
            font=FONTS["button"]
        )
        add_single_btn.pack(pady=10, padx=20)


        upload_btn = ctk.CTkButton(
            left_frame,
            text="Upload from txt",
            command=self.upload_from_txt,
            **BUTTON_STYLES["secondary"],
            width=250,
            font=FONTS["button"]
        )
        upload_btn.pack(pady=10, padx=20)


        checkbox_frame = ctk.CTkFrame(left_frame, fg_color="transparent")
        checkbox_frame.pack(pady=20, padx=20)

        self.auto_checkbox = ctk.CTkCheckBox(
            checkbox_frame,
            text="Auto Password Set",
            variable=self.auto_password,
            font=FONTS["body_bold"],
            text_color=COLORS["text_white"],
            fg_color=COLORS["accent_purple"],
            hover_color=COLORS["accent_blue"],
            checkmark_color=COLORS["text_white"]
        )
        self.auto_checkbox.pack()

        auto_info = ctk.CTkLabel(
            left_frame,
            text="When checked: auto-generate ShulkerGen######\nWhen unchecked: enter a password for each account",
            font=FONTS["small"],
            text_color=COLORS["text_gray"],
            justify="left"
        )
        auto_info.pack(pady=(0, 10), padx=20)


        clear_btn = ctk.CTkButton(
            left_frame,
            text="Clear All",
            command=self.clear_all_accounts,
            **BUTTON_STYLES["danger"],
            width=250,
            font=FONTS["button"]
        )
        clear_btn.pack(pady=10, padx=20)


        right_frame = ctk.CTkFrame(content_frame, **FRAME_STYLES, width=400)
        right_frame.pack(side="right", fill="both", expand=True, padx=(10, 0))

        list_title = ctk.CTkLabel(
            right_frame,
            text="Account List",
            font=FONTS["heading"],
            text_color=COLORS["text_white"]
        )
        list_title.pack(pady=(20, 10), padx=20)


        self.account_list_frame = ctk.CTkScrollableFrame(
            right_frame,
            fg_color=COLORS["bg_dark"],
            width=350,
            height=350
        )
        self.account_list_frame.pack(pady=10, padx=20, fill="both", expand=True)


        self.count_label = ctk.CTkLabel(
            right_frame,
            text="Accounts: 0",
            font=FONTS["body"],
            text_color=COLORS["text_gray"]
        )
        self.count_label.pack(pady=(5, 20), padx=20)


        bottom_frame = ctk.CTkFrame(self, fg_color="transparent", height=80)
        bottom_frame.pack(fill="x", padx=20, pady=(10, 20))
        bottom_frame.pack_propagate(False)

        self.start_button = ctk.CTkButton(
            bottom_frame,
            text="Start Processing",
            command=self.start_processing,
            **{k: v for k, v in BUTTON_STYLES["success"].items() if k != "height"},
            width=400,
            height=50,
            font=("Arial", 18, "bold")
        )

        self.start_button.pack(pady=15)

    def add_single_account(self):
        dialog = ctk.CTkToplevel(self.parent)
        dialog.title("Add Single Account")
        dialog.geometry("400x250")
        dialog.configure(fg_color=COLORS["bg_dark"])
        dialog.transient(self.parent)
        dialog.grab_set()

        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (400 // 2)
        y = (dialog.winfo_screenheight() // 2) - (250 // 2)
        dialog.geometry(f"+{x}+{y}")

        title = ctk.CTkLabel(
            dialog,
            text="Enter Account Credentials",
            font=FONTS["heading"],
            text_color=COLORS["text_white"]
        )
        title.pack(pady=(20, 10))

        email_label = ctk.CTkLabel(
            dialog,
            text="Email:Password",
            font=FONTS["body"],
            text_color=COLORS["text_white"]
        )
        email_label.pack(pady=(10, 5))

        entry = ctk.CTkEntry(
            dialog,
            **ENTRY_STYLES,
            width=300,
            placeholder_text="email@example.com:password123"
        )
        entry.pack(pady=(0, 20))
        entry.focus()

        def add():
            combo = entry.get().strip()
            if not combo:
                messagebox.showerror("Error", "Please enter email:password")
                return

            if ':' not in combo:
                messagebox.showerror("Error", "Format must be email:password")
                return

            email, password = combo.split(':', 1)
            if not email or not password:
                messagebox.showerror("Error", "Both email and password are required")
                return

            self.accounts.append({"email": email, "password": password})
            self.update_account_list()
            dialog.destroy()

        add_btn = ctk.CTkButton(
            dialog,
            text="Add Account",
            command=add,
            **BUTTON_STYLES["success"],
            width=200
        )
        add_btn.pack(pady=10)

        entry.bind('<Return>', lambda e: add())

    def upload_from_txt(self):
        file_path = filedialog.askopenfilename(
            title="Select txt file",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )

        if not file_path:
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            added = 0
            for line in lines:
                line = line.strip()
                if not line or ':' not in line:
                    continue

                parts = line.split(':', 1)
                if len(parts) == 2:
                    email, password = parts
                    if email and password:
                        self.accounts.append({"email": email.strip(), "password": password.strip()})
                        added += 1

            if added > 0:
                self.update_account_list()
                messagebox.showinfo("Success", f"Added {added} accounts")
            else:
                messagebox.showwarning("Warning", "No valid accounts found in file")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to read file: {str(e)}")

    def update_account_list(self):
        # Clear current list
        for widget in self.account_list_frame.winfo_children():
            widget.destroy()

        # Add accounts
        for idx, account in enumerate(self.accounts, 1):
            account_frame = ctk.CTkFrame(
                self.account_list_frame,
                fg_color=COLORS["bg_light"],
                corner_radius=8
            )
            account_frame.pack(fill="x", pady=5, padx=5)

            info_label = ctk.CTkLabel(
                account_frame,
                text=f"{idx}. {account['email']}:{account['password']}",
                font=FONTS["body"],
                text_color=COLORS["text_white"],
                anchor="w"
            )
            info_label.pack(side="left", padx=10, pady=10, fill="x", expand=True)

            remove_btn = ctk.CTkButton(
                account_frame,
                text="Remove",
                command=lambda i=idx-1: self.remove_account(i),
                fg_color="transparent",
                hover_color=COLORS["error"],
                width=40,
                height=30
            )
            remove_btn.pack(side="right", padx=5, pady=5)

        # Update count
        self.count_label.configure(text=f"Accounts: {len(self.accounts)}")

    def remove_account(self, index):
        if 0 <= index < len(self.accounts):
            self.accounts.pop(index)
            self.update_account_list()

    def clear_all_accounts(self):
        if not self.accounts:
            return

        if messagebox.askyesno("Confirm", "Clear all accounts?"):
            self.accounts = []
            self.update_account_list()

    def start_processing(self):
        if not self.accounts:
            messagebox.showerror("Error", "Please add at least one account")
            return


        self.pack_forget()
        processing_screen = ProcessingScreen(
            self.parent,
            self.accounts,
            self.auto_password.get(),
            self.user_id
        )
        processing_screen.pack(fill="both", expand=True)
        processing_screen.start_processing()


    def logout(self):
        from tkinter import messagebox
        from utils.session_manager import clear_session

        if messagebox.askyesno("Logout", "Are you sure you want to logout?\n\nYou will need to login again next time."):
            clear_session()
            messagebox.showinfo("Logged Out", "Session cleared. Returning to login screen.")

            # Go back to auth screen
            self.pack_forget()
            self.parent.user_id = None
            self.parent.show_auth_screen()
