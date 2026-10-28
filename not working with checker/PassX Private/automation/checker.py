"""
PassX account checks after Selenium login.
Minecraft ownership, Xbox subscriptions, Hypixel, Donut.
"""
import json
import re
import time

import requests
from selenium.webdriver.common.by import By

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
)
TIMEOUT = 12


def _json_from_driver(driver):
    try:
        pre = driver.find_element(By.TAG_NAME, "pre").text
        return json.loads(pre)
    except Exception:
        pass
    src = driver.page_source or ""
    m = re.search(r"\{.*\}", src, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group())
    except Exception:
        return None


def check_minecraft(driver) -> dict:
    result = {
        "java": "❌ Not Owned",
        "bedrock": "❌ Not Owned",
        "username": "—",
        "uuid": "—",
        "capes": "None",
    }
    try:
        driver.get("https://api.minecraftservices.com/entitlements/mcstore")
        time.sleep(1.4)
        src = driver.page_source or ""
        if "product_minecraft" in src or "game_minecraft" in src:
            result["java"] = "✅ Owned"
        if "product_minecraft_bedrock" in src or "game_minecraft_bedrock" in src:
            result["bedrock"] = "✅ Owned"
    except Exception as e:
        print(f"⚠️ entitlements: {e}")

    try:
        driver.get("https://api.minecraftservices.com/minecraft/profile")
        time.sleep(1.4)
        profile = _json_from_driver(driver)
        if isinstance(profile, dict) and profile.get("name"):
            result["username"] = profile.get("name") or "—"
            uid = (profile.get("id") or "").replace("-", "")
            if len(uid) == 32:
                result["uuid"] = f"{uid[0:8]}-{uid[8:12]}-{uid[12:16]}-{uid[16:20]}-{uid[20:32]}"
            capes = profile.get("capes") or []
            names = []
            for c in capes:
                alias = c.get("alias") or c.get("id") or "Cape"
                names.append(f"{alias}*" if (c.get("state") or "").upper() == "ACTIVE" else alias)
            result["capes"] = ", ".join(names) if names else "None"
    except Exception as e:
        print(f"⚠️ profile: {e}")

    print(f"🎮 MC Java:{result['java']} User:{result['username']}")
    return result


def check_xbox_subscriptions(driver) -> dict:
    result = {
        "game_pass": "❌ Not Active",
        "gpu": "❌ Not Active",
        "pc_game_pass": "❌ Not Active",
        "gold": "❌ Not Active",
    }
    try:
        driver.get("https://account.microsoft.com/services/")
        time.sleep(3.5)
        low = (driver.page_source or "").lower()
        gpu_on = "game pass ultimate" in low or "xbox game pass ultimate" in low
        pc_on = "pc game pass" in low or "game pass for pc" in low
        gp_on = "xbox game pass" in low or gpu_on
        gold_on = "xbox live gold" in low or "game pass core" in low or gpu_on
        result["gpu"] = "✅ Active" if gpu_on else "❌ Not Active"
        result["pc_game_pass"] = "✅ Active" if pc_on or gpu_on else "❌ Not Active"
        result["game_pass"] = "✅ Active" if gp_on else "❌ Not Active"
        result["gold"] = "✅ Active" if gold_on else "❌ Not Active"
        print(f"🎮 Xbox GPU:{result['gpu']} PC:{result['pc_game_pass']} Gold:{result['gold']}")
    except Exception as e:
        print(f"⚠️ Xbox subscription check failed: {e}")
    return result


def check_hypixel_ban(minecraft_username: str) -> str:
    if not minecraft_username or minecraft_username == "—":
        return "⚠️ No MC Username"
    try:
        r = requests.get(
            f"https://plancke.io/hypixel/player/stats/{minecraft_username}",
            headers={"User-Agent": UA}, timeout=TIMEOUT,
        )
        src = r.text.lower()
        if "is banned" in src or "permanently banned" in src or "banned from hypixel" in src:
            return "🔨 Banned"
        if "player not found" in src or "never played" in src:
            return "⚠️ Never Played Hypixel"
        if r.status_code == 200:
            return "✅ Not Banned"
        return "⚠️ Could Not Check"
    except Exception as e:
        print(f"⚠️ Hypixel check failed: {e}")
        return "⚠️ Check Failed"


def check_donut_ban(minecraft_username: str) -> str:
    if not minecraft_username or minecraft_username == "—":
        return "⚠️ No MC Username"
    try:
        r = requests.get(
            f"https://api.donutsmp.net/v1/bans/{minecraft_username}",
            headers={"User-Agent": UA}, timeout=TIMEOUT,
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("banned"):
                return f"🔨 Banned — {data.get('reason', 'No reason given')}"
            return "✅ Not Banned"
        if r.status_code == 404:
            return "✅ Not Banned / Never Played"
        return "⚠️ Could Not Check"
    except Exception as e:
        print(f"⚠️ Donut SMP check failed: {e}")
        return "⚠️ Check Failed"


def run_all_checks(driver) -> dict:
    print("🔍 Running account checks...")
    mc = check_minecraft(driver)
    xbox = check_xbox_subscriptions(driver)
    user = mc["username"]
    return {
        "mc_java": mc["java"],
        "mc_bedrock": mc["bedrock"],
        "mc_username": mc["username"],
        "mc_uuid": mc.get("uuid", "—"),
        "mc_capes": mc.get("capes", "None"),
        "xbox_gp": xbox["game_pass"],
        "xbox_gpu": xbox["gpu"],
        "xbox_pc_gp": xbox["pc_game_pass"],
        "xbox_gold": xbox["gold"],
        "xbox_gp_core": xbox["gold"],
        "hypixel_ban": check_hypixel_ban(user),
        "donut_ban": check_donut_ban(user),
    }