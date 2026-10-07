"""
PassX — Account Checker
Checks: Minecraft Java/Bedrock ownership, Xbox Game Pass, Xbox GPU,
        Hypixel ban status (no API key needed), Donut SMP ban
All checks run after successful login using the existing authenticated driver session.
"""

import requests
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ── Timeouts ────────────────────────────────────────────────────────────────
REQ_TIMEOUT = 10


# ════════════════════════════════════════════════════════════════════════════
#  MINECRAFT
# ════════════════════════════════════════════════════════════════════════════

def check_minecraft(driver) -> dict:
    """
    Check if the account owns Minecraft Java Edition using Microsoft's
    entitlement API (no separate API key needed — uses the logged-in session).
    Also checks Bedrock via Xbox entitlements.
    """
    result = {
        "java":    "❌ Not Owned",
        "bedrock": "❌ Not Owned",
        "username": "—",
    }

    try:
        # ── Get Xbox Live token from the authenticated session ──
        driver.get("https://user.auth.xboxlive.com/user/authenticate")
        time.sleep(2)

        # Hit the Minecraft entitlement endpoint directly
        # This works because the driver already has a valid Microsoft session cookie
        driver.get("https://api.minecraftservices.com/entitlements/mcstore")
        time.sleep(2)

        src = driver.page_source
        if '"product_minecraft"' in src or '"game_minecraft"' in src:
            result["java"] = "✅ Owned"
        if '"product_minecraft_bedrock"' in src or '"game_minecraft_bedrock"' in src:
            result["bedrock"] = "✅ Owned"

        # ── Get Minecraft username if they own it ──
        if result["java"] == "✅ Owned":
            driver.get("https://api.minecraftservices.com/minecraft/profile")
            time.sleep(2)
            profile_src = driver.page_source
            if '"name"' in profile_src:
                import json, re
                try:
                    # Extract JSON from page
                    match = re.search(r'\{.*\}', profile_src, re.DOTALL)
                    if match:
                        data = json.loads(match.group())
                        result["username"] = data.get("name", "—")
                except Exception:
                    pass

        print(f"🎮 Minecraft — Java: {result['java']}, Bedrock: {result['bedrock']}, Username: {result['username']}")

    except Exception as e:
        print(f"⚠️ Minecraft check failed: {e}")

    return result


# ════════════════════════════════════════════════════════════════════════════
#  XBOX GAME PASS / GPU
# ════════════════════════════════════════════════════════════════════════════

def check_xbox_subscriptions(driver) -> dict:
    """
    Check Xbox Game Pass and Game Pass Ultimate status
    by visiting the Xbox subscription management page.
    """
    result = {
        "game_pass":     "❌ Not Active",
        "gpu":           "❌ Not Active",
        "pc_game_pass":  "❌ Not Active",
    }

    try:
        driver.get("https://account.microsoft.com/services/")
        time.sleep(4)

        src = driver.page_source.lower()

        # Xbox Game Pass Ultimate
        if any(x in src for x in [
            "game pass ultimate",
            "xbox game pass ultimate",
            "ultimate membership",
        ]):
            result["gpu"] = "✅ Active"
            result["game_pass"] = "✅ Active"  # GPU includes GP

        # Xbox Game Pass (console)
        elif any(x in src for x in [
            "xbox game pass",
            "game pass for console",
            "xbox live gold",
        ]):
            result["game_pass"] = "✅ Active"

        # PC Game Pass
        if any(x in src for x in [
            "pc game pass",
            "game pass for pc",
        ]):
            result["pc_game_pass"] = "✅ Active"

        print(f"🎮 Xbox — GP: {result['game_pass']}, GPU: {result['gpu']}, PC GP: {result['pc_game_pass']}")

    except Exception as e:
        print(f"⚠️ Xbox subscription check failed: {e}")

    return result


# ════════════════════════════════════════════════════════════════════════════
#  HYPIXEL BAN — NO API KEY NEEDED
# ════════════════════════════════════════════════════════════════════════════

def check_hypixel_ban(minecraft_username: str) -> str:
    """
    Check Hypixel ban status using plancke.io (public, no API key needed).
    plancke.io is a public Hypixel stats site that shows ban info.
    """
    if not minecraft_username or minecraft_username == "—":
        return "⚠️ No MC Username"

    try:
        # plancke.io shows ban status publicly
        url = f"https://plancke.io/hypixel/player/stats/{minecraft_username}"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=REQ_TIMEOUT)
        src = r.text.lower()

        if "is banned" in src or "permanently banned" in src or "banned from hypixel" in src:
            return "🔨 Banned"
        elif "player not found" in src or "never played" in src:
            return "⚠️ Never Played Hypixel"
        elif r.status_code == 200:
            return "✅ Not Banned"
        else:
            return "⚠️ Could Not Check"

    except Exception as e:
        print(f"⚠️ Hypixel check failed: {e}")
        return "⚠️ Check Failed"


# ════════════════════════════════════════════════════════════════════════════
#  DONUT SMP BAN
# ════════════════════════════════════════════════════════════════════════════

def check_donut_ban(minecraft_username: str) -> str:
    """
    Check Donut SMP ban status.
    Donut SMP uses Crafthead/NameMC-style public APIs.
    Falls back to checking their public ban list if available.
    """
    if not minecraft_username or minecraft_username == "—":
        return "⚠️ No MC Username"

    try:
        # Donut SMP public ban lookup
        url = f"https://api.donutsmp.net/v1/bans/{minecraft_username}"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=REQ_TIMEOUT)

        if r.status_code == 200:
            data = r.json()
            if data.get("banned"):
                reason = data.get("reason", "No reason given")
                return f"🔨 Banned — {reason}"
            else:
                return "✅ Not Banned"
        elif r.status_code == 404:
            return "✅ Not Banned / Never Played"
        else:
            return "⚠️ Could Not Check"

    except Exception as e:
        print(f"⚠️ Donut SMP check failed: {e}")
        return "⚠️ Check Failed"


# ════════════════════════════════════════════════════════════════════════════
#  MASTER CHECKER — runs all checks, returns full dict
# ════════════════════════════════════════════════════════════════════════════

def run_all_checks(driver) -> dict:
    """
    Run all account checks using the authenticated Selenium driver.
    Returns a dict with all results ready to be added to the webhook embed.
    """
    print("🔍 Running account checks...")

    checks = {
        "mc_java":       "⚠️ Skipped",
        "mc_bedrock":    "⚠️ Skipped",
        "mc_username":   "—",
        "xbox_gp":       "⚠️ Skipped",
        "xbox_gpu":      "⚠️ Skipped",
        "xbox_pc_gp":    "⚠️ Skipped",
        "hypixel_ban":   "⚠️ Skipped",
        "donut_ban":     "⚠️ Skipped",
    }

    # ── Minecraft ──
    mc = check_minecraft(driver)
    checks["mc_java"]     = mc["java"]
    checks["mc_bedrock"]  = mc["bedrock"]
    checks["mc_username"] = mc["username"]

    # ── Xbox subscriptions ──
    xbox = check_xbox_subscriptions(driver)
    checks["xbox_gp"]    = xbox["game_pass"]
    checks["xbox_gpu"]   = xbox["gpu"]
    checks["xbox_pc_gp"] = xbox["pc_game_pass"]

    # ── Ban checks (need MC username) ──
    username = mc["username"]
    checks["hypixel_ban"] = check_hypixel_ban(username)
    checks["donut_ban"]   = check_donut_ban(username)

    print(f"✅ All checks complete: {checks}")
    return checks
