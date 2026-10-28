"""
Multi-provider temp inbox.
get_messages() ALWAYS returns a list of dicts.
Reads FULL bodies. Extracts 4–8 digit OTPs and Microsoft reset links.
"""
import html as htmlmod
import quopri
import random
import re
import socket
import string
import time
import uuid
from urllib.parse import parse_qs, unquote, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from urllib3.util import connection as urllib3_cn
    urllib3_cn.allowed_gai_family = lambda: socket.AF_INET
except Exception:
    pass

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
TIMEOUT = 18
_ACCOUNTS = {}

HREF_RE = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.I)
URL_RE = re.compile(r"https?://[^\s\"'<>\\]+", re.I)
RESET_HOSTS = (
    "account.live.com", "login.live.com", "account.microsoft.com",
    "accountprotection.microsoft.com", "aka.ms",
    "safelinks.protection.outlook.com", "safelink.emails.azure.net",
    "click.mail.microsoftonline.com", "click.email.microsoft.com",
    "microsoft.com",
)
RESET_HINTS = (
    "resetpassword", "reset-password", "password/reset", "passwd",
    "recover", "reauth", "proof", "acsr", "identity/confirm",
    "account.live.com", "login.live.com",
)


class _IPv4Adapter(HTTPAdapter):
    def init_poolmanager(self, connections, maxsize, block=False, **kw):
        kw["source_address"] = ("0.0.0.0", 0)
        return super().init_poolmanager(connections, maxsize, block, **kw)


def random_name(length=10):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


def _is_10013(err):
    s = str(err)
    return "10013" in s or "forbidden by its access permissions" in s.lower()


def _sess(proxies=None, trust_env=False):
    s = requests.Session()
    s.trust_env = trust_env
    s.headers.update({
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
    })
    retry = Retry(total=2, connect=2, read=2, backoff_factor=0.4, status_forcelist=(429, 502, 503, 504))
    ad = _IPv4Adapter(max_retries=retry)
    s.mount("https://", ad)
    s.mount("http://", ad)
    if proxies:
        s.proxies.update(proxies)
    return s


def _proxy_dict():
    try:
        from automation.proxymanager import get_proxy_manager
        p = get_proxy_manager().get_next_proxy()
        if not p:
            return None
        a = str(getattr(p, "auth_string", None) or f"{p.ip}:{p.port}")
        if "://" not in a:
            a = "http://" + a
        return {"http": a, "https": a}
    except Exception:
        return None


def _sessions():
    out = [_sess(None, False), _sess(None, True)]
    px = _proxy_dict()
    if px:
        out.append(_sess(px, False))
    return out


def _get(s, url, **kw):
    kw.setdefault("timeout", TIMEOUT)
    last = None
    for _ in range(4):
        try:
            return s.get(url, **kw)
        except Exception as e:
            last = e
            time.sleep(random.uniform(0.2, 0.7) if _is_10013(e) else 0.25)
    raise last


def _post(s, url, **kw):
    kw.setdefault("timeout", TIMEOUT)
    last = None
    for _ in range(4):
        try:
            return s.post(url, **kw)
        except Exception as e:
            last = e
            time.sleep(random.uniform(0.2, 0.7) if _is_10013(e) else 0.25)
    raise last


def _json(r):
    try:
        return r.json()
    except Exception:
        return None


def _as_list(data, *keys):
    if data is None:
        return []
    if isinstance(data, list):
        return [x for x in data if x is not None]
    if isinstance(data, dict):
        for k in keys + ("hydra:member", "member", "messages", "mails", "emails", "list", "items"):
            v = data.get(k)
            if isinstance(v, list):
                return v
        if any(k in data for k in ("id", "subject", "intro", "text", "html")):
            return [data]
    return []


def _as_dict(data):
    return data if isinstance(data, dict) else {}


def _store(kind, email, extra):
    token = f"px-{kind}-{uuid.uuid4().hex[:12]}"
    rec = {"kind": kind, "email": email, "password": extra.get("password") or random_name(12)}
    rec.update(extra)
    _ACCOUNTS[token] = rec
    print(f"📩 Temp mail: {email}  ({kind})")
    return email, rec["password"], token


def _acc(token):
    return _ACCOUNTS.get(token) or {}


def _create_mailtm(base):
    last = None
    for s in _sessions():
        for _ in range(3):
            try:
                r = _get(s, f"{base}/domains")
                r.raise_for_status()
                members = _as_list(_json(r), "hydra:member")
                active = []
                for d in members:
                    if isinstance(d, dict) and d.get("isActive", True) and d.get("domain"):
                        active.append(d["domain"])
                if not active:
                    last = f"{base} no domains"
                    continue
                domain = random.choice(active)
                username = random_name(12)
                password = random_name(14) + "Aa1"
                email = f"{username}@{domain}"
                cr = _post(s, f"{base}/accounts", json={"address": email, "password": password})
                if cr.status_code not in (200, 201, 422):
                    last = f"{base} register HTTP {cr.status_code} {cr.text[:80]}"
                    continue
                tr = _post(s, f"{base}/token", json={"address": email, "password": password})
                tr.raise_for_status()
                jwt = _as_dict(_json(tr)).get("token")
                if not jwt:
                    last = f"{base} no token"
                    continue
                return _store("mailtm", email, {"password": password, "base": base, "jwt": jwt})
            except Exception as e:
                last = e
                time.sleep(0.3)
    raise RuntimeError(last)


_ONESEC = (
    "https://www.1secmail.com/api/v1/",
    "https://www.1secmail.org/api/v1/",
    "https://www.1secmail.net/api/v1/",
)


def _create_onesec():
    last = None
    for api in _ONESEC:
        for s in _sessions():
            try:
                r = _get(s, api, params={"action": "genRandomMailbox", "count": 1})
                r.raise_for_status()
                data = _json(r)
                email = None
                if isinstance(data, list) and data:
                    email = data[0]
                elif isinstance(data, str) and "@" in data:
                    email = data
                elif isinstance(data, dict):
                    email = data.get("email") or data.get("address")
                if not email or "@" not in str(email):
                    last = f"1secmail bad resp {data!r}"[:120]
                    continue
                login, domain = str(email).split("@", 1)
                return _store("onesec", email, {"api": api, "login": login, "domain": domain})
            except Exception as e:
                last = e
    raise RuntimeError(last)


def _create_guerrilla():
    last = None
    for s in _sessions():
        try:
            r = _get(s, "https://api.guerrillamail.com/ajax.php", params={"f": "get_email_address", "lang": "en"})
            r.raise_for_status()
            data = _as_dict(_json(r))
            email, sid = data.get("email_addr"), data.get("sid_token")
            if not email or not sid:
                last = f"guerrilla missing fields {data}"
                continue
            s.cookies.set("PHPSESSID", sid)
            return _store("guerrilla", email, {"sid": sid, "session": s})
        except Exception as e:
            last = e
    raise RuntimeError(last)


def _create_tempmail_lol():
    last = None
    for s in _sessions():
        for url, body in (
            ("https://api.tempmail.lol/v2/inbox/create", {}),
            ("https://api.tempmail.lol/generate", None),
        ):
            try:
                r = _get(s, url) if body is None else _post(s, url, json=body)
                if r.status_code >= 400:
                    last = f"tempmail.lol HTTP {r.status_code}"
                    continue
                data = _as_dict(_json(r))
                email, tok = data.get("address") or data.get("email"), data.get("token")
                if not email or not tok:
                    last = f"tempmail.lol fields {data}"
                    continue
                return _store("lol", email, {"lol_token": tok})
            except Exception as e:
                last = e
    raise RuntimeError(last)


def _create_dropmail():
    last = None
    gql = "https://dropmail.me/api/graphql/passx" + random_name(8)
    query = "mutation { introduceSession { id expiresAt addresses { address } } }"
    for s in _sessions():
        try:
            r = _post(s, gql, json={"query": query}, headers={"Content-Type": "application/json"})
            r.raise_for_status()
            data = _as_dict(_json(r))
            sess = _as_dict(_as_dict(data.get("data")).get("introduceSession"))
            addrs = sess.get("addresses") if isinstance(sess.get("addresses"), list) else []
            email = _as_dict(addrs[0] if addrs else {}).get("address")
            sid = sess.get("id")
            if not email or not sid:
                last = f"dropmail fields {r.text[:120]}"
                continue
            return _store("dropmail", email, {"gql": gql, "sid": sid})
        except Exception as e:
            last = e
    raise RuntimeError(last)


def _create_tempmail_io():
    last = None
    for s in _sessions():
        try:
            r = _post(
                s,
                "https://api.internal.temp-mail.io/api/v3/email/new",
                json={"min_name_length": 10, "max_name_length": 12},
            )
            r.raise_for_status()
            data = _as_dict(_json(r))
            email = data.get("email")
            if not email:
                last = f"temp-mail.io {data}"
                continue
            return _store("tempio", email, {})
        except Exception as e:
            last = e
    raise RuntimeError(last)


def generate_temp_mail_account():
    errors = []
    providers = [
        ("mail.tm", lambda: _create_mailtm("https://api.mail.tm")),
        ("mail.gw", lambda: _create_mailtm("https://api.mail.gw")),
        ("1secmail", _create_onesec),
        ("guerrilla", _create_guerrilla),
        ("tempmail.lol", _create_tempmail_lol),
        ("dropmail", _create_dropmail),
        ("temp-mail.io", _create_tempmail_io),
    ]
    saw_10013 = False
    for name, fn in providers:
        try:
            print(f"[tempmail] trying {name} …")
            return fn()
        except Exception as e:
            if _is_10013(e):
                saw_10013 = True
            errors.append(f"{name}: {e}")
            print(f"[tempmail] {name} failed: {e}")
    lines = ["Temp mail create failed on every provider:"] + [f"  - {x}" for x in errors]
    if saw_10013:
        lines += [
            "",
            "ROOT CAUSE: WinError 10013 — Windows blocked Python from opening an outbound socket.",
            "Fix: firewall-allow python.exe, `net stop winnat`, disable VPN/AV HTTPS scan.",
        ]
    raise RuntimeError("\n".join(lines))


def _normalize_msg(mid, subject="", intro="", text="", html="", frm=""):
    return {
        "id": str(mid) if mid is not None else "",
        "subject": subject or "",
        "intro": intro or "",
        "text": text or "",
        "html": html or "",
        "from": frm or "",
    }


def _auth_headers(jwt):
    return {"Authorization": f"Bearer {jwt}", "Accept": "application/json", "User-Agent": UA}


def _list_mailtm(acc):
    s = _sess()
    base, jwt = acc.get("base") or "https://api.mail.tm", acc.get("jwt")
    r = _get(s, f"{base}/messages", headers=_auth_headers(jwt))
    if r.status_code == 401:
        tr = _post(s, f"{base}/token", json={"address": acc["email"], "password": acc.get("password")})
        if tr.status_code == 200:
            acc["jwt"] = _as_dict(_json(tr)).get("token") or jwt
            r = _get(s, f"{base}/messages", headers=_auth_headers(acc["jwt"]))
    r.raise_for_status()
    out = []
    for m in _as_list(_json(r), "hydra:member"):
        m = _as_dict(m)
        out.append(_normalize_msg(m.get("id"), m.get("subject"), m.get("intro"), m.get("text"), m.get("html"),
                                  str(_as_dict(m.get("from")).get("address") or m.get("from") or "")))
    return out


def _read_mailtm(acc, mid):
    s = _sess()
    base, jwt = acc.get("base") or "https://api.mail.tm", acc.get("jwt")
    r = _get(s, f"{base}/messages/{mid}", headers=_auth_headers(jwt))
    r.raise_for_status()
    m = _as_dict(_json(r))
    frm = m.get("from")
    frm = _as_dict(frm).get("address") if isinstance(frm, dict) else (frm or "")
    return _normalize_msg(m.get("id") or mid, m.get("subject"), m.get("intro"), m.get("text"), m.get("html"), frm)


def _list_onesec(acc):
    s = _sess()
    r = _get(s, acc["api"], params={"action": "getMessages", "login": acc["login"], "domain": acc["domain"]})
    r.raise_for_status()
    out = []
    for m in _as_list(_json(r)):
        m = _as_dict(m)
        out.append(_normalize_msg(m.get("id"), m.get("subject"), m.get("text") or "", "", "", m.get("from")))
    return out


def _read_onesec(acc, mid):
    s = _sess()
    r = _get(s, acc["api"], params={"action": "readMessage", "login": acc["login"], "domain": acc["domain"], "id": mid})
    r.raise_for_status()
    m = _as_dict(_json(r))
    return _normalize_msg(
        mid, m.get("subject"), "",
        m.get("textBody") or m.get("body") or "",
        m.get("htmlBody") or "",
        m.get("from"),
    )


def _list_guerrilla(acc):
    s = acc.get("session") or _sess()
    r = _get(s, "https://api.guerrillamail.com/ajax.php", params={"f": "get_email_list", "offset": 0, "sid_token": acc["sid"]})
    r.raise_for_status()
    out = []
    for m in _as_list(_json(r), "list"):
        m = _as_dict(m)
        out.append(_normalize_msg(
            m.get("mail_id"), m.get("mail_subject"), m.get("mail_excerpt") or "",
            m.get("mail_excerpt") or "", "", m.get("mail_from"),
        ))
    return out


def _read_guerrilla(acc, mid):
    s = acc.get("session") or _sess()
    r = _get(s, "https://api.guerrillamail.com/ajax.php", params={"f": "fetch_email", "email_id": mid, "sid_token": acc["sid"]})
    r.raise_for_status()
    m = _as_dict(_json(r))
    return _normalize_msg(
        mid, m.get("mail_subject"), "",
        m.get("mail_body") or m.get("mail_excerpt") or "",
        m.get("mail_body_html") or m.get("mail_html") or "",
        m.get("mail_from"),
    )


def _list_lol(acc):
    s = _sess()
    r = _get(s, "https://api.tempmail.lol/v2/inbox", params={"token": acc.get("lol_token")})
    if r.status_code >= 400:
        r = _get(s, f"https://api.tempmail.lol/auth/{acc.get('lol_token')}")
    r.raise_for_status()
    out = []
    for i, m in enumerate(_as_list(_json(r), "emails", "messages")):
        m = _as_dict(m)
        out.append(_normalize_msg(
            m.get("id") or i, m.get("subject"),
            m.get("body") or m.get("text") or "",
            m.get("body") or m.get("text") or "",
            m.get("html") or "", m.get("from"),
        ))
    return out


def _list_dropmail(acc):
    s = _sess()
    q = {
        "query": "query($id: ID!){ session(id:$id){ mails{ fromAddr headerSubject text html } } }",
        "variables": {"id": acc["sid"]},
    }
    r = _post(s, acc["gql"], json=q, headers={"Content-Type": "application/json"})
    r.raise_for_status()
    data = _as_dict(_json(r))
    session = _as_dict(_as_dict(data.get("data")).get("session"))
    mails = session.get("mails") if isinstance(session.get("mails"), list) else []
    out = []
    for i, m in enumerate(mails):
        m = _as_dict(m)
        out.append(_normalize_msg(
            i, m.get("headerSubject"), m.get("text") or "",
            m.get("text") or "", m.get("html") or "", m.get("fromAddr"),
        ))
    return out


def _list_tempio(acc):
    s = _sess()
    r = _get(s, f"https://api.internal.temp-mail.io/api/v3/email/{acc['email']}/messages")
    r.raise_for_status()
    out = []
    for m in _as_list(_json(r)):
        m = _as_dict(m)
        out.append(_normalize_msg(
            m.get("_id") or m.get("id"), m.get("subject"),
            m.get("body_text") or "", m.get("body_text") or "",
            m.get("body_html") or "", m.get("from"),
        ))
    return out


def get_messages(token):
    """Always a list of message dicts. Never a tuple."""
    acc = _acc(token)
    kind = acc.get("kind")
    try:
        if kind == "mailtm":
            inbox = _list_mailtm(acc)
        elif kind == "onesec":
            inbox = _list_onesec(acc)
        elif kind == "guerrilla":
            inbox = _list_guerrilla(acc)
        elif kind == "lol":
            inbox = _list_lol(acc)
        elif kind == "dropmail":
            inbox = _list_dropmail(acc)
        elif kind == "tempio":
            inbox = _list_tempio(acc)
        else:
            inbox = []
    except Exception as e:
        print(f"⚠️ get_messages: {e}")
        inbox = []
    if not isinstance(inbox, list):
        inbox = _as_list(inbox)
    clean = []
    for m in inbox:
        if isinstance(m, dict):
            clean.append(m)
        elif isinstance(m, str):
            clean.append(_normalize_msg(len(clean), "", m, m, "", ""))
    return clean


def read_message(token, message_id, base=None):
    acc = _acc(token)
    kind = acc.get("kind")
    try:
        if kind == "mailtm":
            return _read_mailtm(acc, message_id)
        if kind == "onesec":
            return _read_onesec(acc, message_id)
        if kind == "guerrilla":
            return _read_guerrilla(acc, message_id)
        inbox = get_messages(token)
        for m in inbox:
            if str(_as_dict(m).get("id")) == str(message_id):
                return m
        return inbox[0] if inbox else {}
    except Exception as e:
        print(f"⚠️ read_message: {e}")
        return {}


def wait_for_emails(token, expected_count=1, timeout=90, interval=5):
    deadline = time.time() + timeout
    inbox = []
    while time.time() < deadline:
        inbox = get_messages(token)
        if len(inbox) >= expected_count:
            return inbox[:expected_count]
        time.sleep(interval)
    return inbox


def _blob_text(blob):
    if not blob:
        return ""
    if isinstance(blob, (list, tuple)):
        return "\n".join(_blob_text(x) for x in blob)
    if isinstance(blob, dict):
        parts = []
        for k in ("subject", "intro", "text", "html", "preview", "body", "mail_body", "from"):
            if blob.get(k):
                parts.append(str(blob[k]))
        parts.extend(str(v) for v in blob.values() if isinstance(v, str))
        return "\n".join(parts)
    return str(blob)


def _decode_blob(s):
    s = htmlmod.unescape(str(s or ""))
    s = s.replace("=\n", "").replace("=\r\n", "").replace("&amp;", "&")
    try:
        s = quopri.decodestring(s.encode("utf-8", "replace")).decode("utf-8", "replace")
    except Exception:
        pass
    return s


def extract_otp(text):
    t = _decode_blob(_blob_text(text))
    if not t:
        return None
    m = re.search(
        r"(?:security code|verification code|one[- ]time(?: code)?|otp|code is|code:|"
        r"enter this code|use this code)\D{0,40}(\d{4,8})",
        t, re.I,
    )
    if m:
        return m.group(1)
    # Microsoft ACSR is usually 4 digits; also 6
    for pat in (r"\b(\d{4})\b", r"\b(\d{6})\b", r"\b(\d{8})\b"):
        for c in re.findall(pat, t):
            if len(c) == 4 and c.startswith("20"):
                continue
            return c
    return None


def get_otp_from_first_email(token):
    emails = wait_for_emails(token, expected_count=1)
    if not emails:
        print("❌ No email received.")
        return None
    msg = read_message(token, emails[0].get("id"))
    otp = extract_otp(msg) or extract_otp(emails[0])
    print("🔐 Extracted OTP:" if otp else "❌ OTP not found in email.", otp or "")
    return otp


def wait_for_otp(token, timeout=180, interval=5):
    print(f"📬 Polling temp inbox up to {timeout}s for Microsoft security code…")
    deadline = time.time() + timeout
    seen = set()
    last_log = 0
    while time.time() < deadline:
        inbox = get_messages(token)
        for item in inbox:
            mid = str(_as_dict(item).get("id") or "")
            blobs = [item]
            if mid not in seen:
                seen.add(mid)
                subj = _as_dict(item).get("subject") or ""
                print(f"📧 mail: {subj[:90]}")
                try:
                    if mid:
                        blobs.append(read_message(token, mid))
                except Exception as e:
                    print(f"⚠️ read_message: {e}")
            for b in blobs:
                dump = _decode_blob(_blob_text(b))
                print(f"   body: {dump[:240].replace(chr(10), ' ')}")
                otp = extract_otp(b)
                if otp:
                    print(f"🔐 OTP: {otp}")
                    return otp
        now = time.time()
        if now - last_log > 15:
            print(f"⏳ Waiting for security code… {int(deadline - now)}s left  inbox={len(inbox)}")
            last_log = now
        time.sleep(interval)
    return None


def _unwrap_safelink(url):
    try:
        q = parse_qs(urlparse(url).query)
        for key in ("url", "u", "r", "redirect", "link"):
            if q.get(key):
                return unquote(q[key][0])
    except Exception:
        pass
    return url


def _clean_url(u):
    u = htmlmod.unescape(u or "").strip().rstrip(").,]}>\"'")
    u = u.replace("&amp;", "&").replace("\\/", "/").replace("\\u0026", "&")
    u = unquote(u)
    if "safelink" in u.lower() or "click.mail" in u.lower() or "click.email" in u.lower():
        u = _unwrap_safelink(u)
    return u


def extract_specific_link(text):
    return extract_reset_link(text)


def extract_reset_link(blob):
    text = _decode_blob(_blob_text(blob))
    if not text:
        return None
    raw = []
    for u in HREF_RE.findall(text) + URL_RE.findall(text):
        u = _clean_url(u)
        if u.startswith("http") and u not in raw:
            raw.append(u)
    if not raw:
        return None

    def score(u):
        l = u.lower()
        s = 0
        if "resetpassword" in l or "password/reset" in l or "resetpassword.aspx" in l:
            s += 80
        if "account.live.com" in l or "login.live.com" in l:
            s += 40
        if "accountprotection.microsoft.com" in l:
            s += 20
        if "recover" in l or "proof" in l or "identity/confirm" in l:
            s += 15
        if "unsubscribe" in l or "privacy" in l or "support.microsoft" in l:
            s -= 50
        if "safelink" in l or "click.mail" in l:
            s -= 5
        if any(h in l for h in RESET_HOSTS):
            s += 10
        return s

    ranked = sorted(raw, key=score, reverse=True)
    best = ranked[0]
    if score(best) <= 0:
        return None
    print(f"🔗 candidate: {best[:140]}")
    return best


def wait_for_reset_link(token, timeout=720, interval=8):
    print(f"📬 Polling temp inbox up to {timeout}s for Microsoft reset link…")
    deadline = time.time() + timeout
    last_log = 0
    seen = set()
    while time.time() < deadline:
        inbox = get_messages(token)
        for item in inbox:
            if not isinstance(item, dict):
                link = extract_reset_link(item)
                if link:
                    print(f"🔗 Reset link: {link[:120]}")
                    return link
                continue
            mid = str(item.get("id") or "")
            blobs = [item]
            key = mid or (item.get("subject") or "") + (item.get("intro") or "")[:40]
            if key not in seen:
                seen.add(key)
                print(f"📧 mail: {(item.get('subject') or '')[:90]}")
                try:
                    if mid:
                        full = read_message(token, mid)
                        blobs.append(full)
                        dump = _decode_blob(_blob_text(full))
                        print(f"   from: {full.get('from', '')}")
                        print(f"   body: {dump[:300].replace(chr(10), ' ')}")
                except Exception as e:
                    print(f"⚠️ read_message {mid}: {e}")
            for b in blobs:
                otp = extract_otp(b)
                if otp:
                    print(f"   (this mail is a CODE {otp}, not a reset link — keep waiting)")
                link = extract_reset_link(b)
                if link:
                    print(f"🔗 Reset link: {link[:120]}")
                    return link
        now = time.time()
        if now - last_log > 20:
            print(f"⏳ Waiting for recovery mail… {int(deadline - now)}s left  inbox={len(inbox)}")
            last_log = now
        time.sleep(interval)
    return None


def print_second_email(token, emails):
    if not emails or len(emails) < 2:
        print("❌ Less than 2 emails available.")
        return
    msg = read_message(token, emails[1].get("id"))
    print("\n📧 Full Email Content (2nd Email):\n")
    print(msg.get("text") or msg.get("html") or msg)