"""
After CAPTCHA:
  1. Type captcha, click Next
  2. Fill first name / last name / DOB (this is the real ACSR page)
  3. Only if Microsoft actually asks for a CODE, read it from temp mail
  4. Poll temp inbox for the reset URL
"""
import html as htmlmod
import re
import time
from urllib.parse import parse_qs, unquote, urlparse

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select

try:
    import tempmail
except Exception:
    tempmail = None

MAIL_WAIT_S = 900
MAIL_POLL_S = 8
OTP_WAIT_S = 240

MONTHS = {
    "january": "1", "jan": "1", "1": "1", "01": "1",
    "february": "2", "feb": "2", "2": "2", "02": "2",
    "march": "3", "mar": "3", "3": "3", "03": "3",
    "april": "4", "apr": "4", "4": "4", "04": "4",
    "may": "5", "5": "5", "05": "5",
    "june": "6", "jun": "6", "6": "6", "06": "6",
    "july": "7", "jul": "7", "7": "7", "07": "7",
    "august": "8", "aug": "8", "8": "8", "08": "8",
    "september": "9", "sep": "9", "sept": "9", "9": "9", "09": "9",
    "october": "10", "oct": "10", "10": "10",
    "november": "11", "nov": "11", "11": "11",
    "december": "12", "dec": "12", "12": "12",
}

LINK_RE = re.compile(
    r"https?://(?:account\.live\.com|account\.microsoft\.com|login\.live\.com|"
    r"aka\.ms|microsoft\.com|nam\d*\.safelinks\.protection\.outlook\.com|"
    r"[a-z0-9.\-]*safelink[^\s\"'<>]*|click\.mail\.microsoftonline\.com|"
    r"click\.email\.microsoft\.com|accountprotection\.microsoft\.com)"
    r"[^\s\"'<>\\]+",
    re.I,
)
HREF_RE = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.I)
URL_RE = re.compile(r"https?://[^\s\"'<>\\]+", re.I)
RESET_HINTS = (
    "resetpassword", "reset-password", "password/reset", "passwd",
    "recover", "reauth", "proof", "identity/confirm",
    "account.live.com", "login.live.com", "accountprotection.microsoft.com",
)
SENT_24H = (
    "we'll send", "we will send", "within 24 hours", "up to 24 hours",
    "check your email", "we've received your request", "we received your request",
    "results of your recovery", "send the results", "you'll get an email",
    "you will get an email", "sent to the email address you gave",
    "if we can verify", "we'll email", "we will email",
)
CODE_LANG = (
    "enter the code", "we sent a code", "security code", "verification code",
    "one-time code", "sent a code to", "check your email for a code",
    "code we sent", "enter the security code",
)
BAD_INFO = (
    "name not found", "dob not found", "region not found",
    "not found", "error", "—", "-", "none", "n/a", "skipped",
)

FIRST_SELECTORS = [
    (By.ID, "iFirstName"), (By.ID, "FirstName"), (By.ID, "idFirstName"),
    (By.NAME, "FirstName"), (By.NAME, "iFirstName"), (By.NAME, "firstName"),
    (By.CSS_SELECTOR, 'input[aria-label*="first name" i]'),
    (By.CSS_SELECTOR, 'input[placeholder*="first name" i]'),
    (By.CSS_SELECTOR, 'input[id*="FirstName" i]'),
    (By.CSS_SELECTOR, 'input[name*="FirstName" i]'),
]
LAST_SELECTORS = [
    (By.ID, "iLastName"), (By.ID, "LastName"), (By.ID, "idLastName"),
    (By.NAME, "LastName"), (By.NAME, "iLastName"), (By.NAME, "lastName"),
    (By.CSS_SELECTOR, 'input[aria-label*="last name" i]'),
    (By.CSS_SELECTOR, 'input[placeholder*="last name" i]'),
    (By.CSS_SELECTOR, 'input[id*="LastName" i]'),
    (By.CSS_SELECTOR, 'input[name*="LastName" i]'),
]
OTP_IDS = (
    "iOttText", "iVerifyCode", "OneTimeCode", "otc",
    "EmailCode", "ProofConfirmation", "iProofCode",
)
CODE_SELECTORS = [
    (By.ID, x) for x in OTP_IDS
] + [
    (By.NAME, "iOttText"),
    (By.NAME, "otc"),
    (By.NAME, "iProofCode"),
    (By.CSS_SELECTOR, 'input[autocomplete="one-time-code"]'),
]


def _src(driver):
    try:
        return (driver.page_source or "").lower()
    except Exception:
        return ""


def _visible_text(driver):
    try:
        return (driver.find_element(By.TAG_NAME, "body").text or "").lower()
    except Exception:
        return _src(driver)


def _page_dump(driver):
    try:
        url = driver.current_url or ""
    except Exception:
        url = ""
    try:
        title = driver.title or ""
    except Exception:
        title = ""
    body = " ".join(_visible_text(driver).split())[:700]
    return f"URL: {url}\nTitle: {title}\nPage: {body or '(no text)'}"


def _good(value):
    if value is None:
        return False
    s = str(value).strip()
    if not s:
        return False
    return s.lower() not in BAD_INFO


def _captcha_wrong(driver):
    t = _visible_text(driver)
    if any(x in t for x in ("characters didn't match", "didn't match", "the characters you entered")):
        return True
    return "try again" in t and ("captcha" in t or "character" in t or "hip" in t)


def _is_24h_page(driver):
    t = _visible_text(driver)
    return any(x in t for x in SENT_24H)


def _is_identity_page(driver):
    t = _visible_text(driver)
    if "first name" in t and "last name" in t:
        return True
    if ("birth date" in t or "date of birth" in t) and ("month" in t or "year" in t):
        return True
    for by, sel in FIRST_SELECTORS + LAST_SELECTORS:
        try:
            for el in driver.find_elements(by, sel):
                if el.is_displayed() and el.is_enabled():
                    return True
        except Exception:
            continue
    return False


def _is_code_page(driver):
    if _is_identity_page(driver):
        return False
    t = _visible_text(driver)
    lang = any(x in t for x in CODE_LANG)
    has_otp = False
    for by, sel in CODE_SELECTORS:
        try:
            for el in driver.find_elements(by, sel):
                if not el.is_displayed() or not el.is_enabled():
                    continue
                typ = (el.get_attribute("type") or "text").lower()
                if typ in ("hidden", "email", "password"):
                    continue
                has_otp = True
                break
        except Exception:
            continue
        if has_otp:
            break
    return has_otp and lang


def _react_type(driver, el, value):
    try:
        driver.execute_script(
            "const el=arguments[0], v=arguments[1];"
            "el.focus(); el.value='';"
            "const proto=el.tagName==='TEXTAREA'"
            " ? window.HTMLTextAreaElement.prototype"
            " : window.HTMLInputElement.prototype;"
            "const setter=Object.getOwnPropertyDescriptor(proto,'value');"
            "if(setter && setter.set) setter.set.call(el, v); else el.value=v;"
            "el.dispatchEvent(new Event('input',{bubbles:true}));"
            "el.dispatchEvent(new Event('change',{bubbles:true}));",
            el, str(value),
        )
        return True
    except Exception:
        return False


def _find_first(driver, selectors, timeout=4):
    end = time.time() + timeout
    while time.time() < end:
        for by, sel in selectors:
            try:
                for el in driver.find_elements(by, sel):
                    if el.is_displayed() and el.is_enabled():
                        typ = (el.get_attribute("type") or "text").lower()
                        if typ in ("hidden", "password"):
                            continue
                        return el
            except Exception:
                continue
        time.sleep(0.2)
    return None


def _type_into(driver, el, value):
    try:
        el.click()
    except Exception:
        pass
    try:
        el.send_keys(Keys.CONTROL, "a")
        el.send_keys(Keys.DELETE)
    except Exception:
        pass
    try:
        el.send_keys(str(value))
    except Exception:
        pass
    _react_type(driver, el, value)
    return True


def _select_value(el, value):
    value = str(value).strip()
    mapped = MONTHS.get(value.lower(), value)
    sel = Select(el)
    for attempt in (mapped, value, value.lstrip("0") or value, value.zfill(2)):
        try:
            sel.select_by_value(str(attempt))
            return True
        except Exception:
            pass
        try:
            sel.select_by_visible_text(str(attempt))
            return True
        except Exception:
            pass
    want = MONTHS.get(value.lower(), value).lower()
    for opt in sel.options:
        t = (opt.text or "").strip()
        v = (opt.get_attribute("value") or "").strip()
        if want in t.lower() or want == v.lower() or value.lower() == t.lower():
            try:
                sel.select_by_visible_text(opt.text)
                return True
            except Exception:
                try:
                    sel.select_by_value(v)
                    return True
                except Exception:
                    continue
    return False


def _select_by_ids(driver, ids, value):
    for sid in ids:
        try:
            el = driver.find_element(By.ID, sid)
            if el.is_displayed():
                if (el.tag_name or "").lower() == "select":
                    if _select_value(el, value):
                        print(f"📅 select #{sid} = {value}")
                        return True
                else:
                    _type_into(driver, el, value)
                    return True
        except Exception:
            continue
        try:
            el = driver.find_element(By.NAME, sid)
            if el.is_displayed() and (el.tag_name or "").lower() == "select":
                if _select_value(el, value):
                    print(f"📅 select name={sid} = {value}")
                    return True
        except Exception:
            continue
    # any visible select whose id/name/aria looks like the field
    try:
        for el in driver.find_elements(By.TAG_NAME, "select"):
            if not el.is_displayed():
                continue
            blob = " ".join([
                el.get_attribute("id") or "",
                el.get_attribute("name") or "",
                el.get_attribute("aria-label") or "",
            ]).lower()
            key = ids[0].lower()
            if any(k in blob for k in ("month", "day", "year") if k in key):
                if _select_value(el, value):
                    print(f"📅 select fallback {blob} = {value}")
                    return True
    except Exception:
        pass
    return False


def _parse_dob(raw):
    if not _good(raw):
        return None
    s = str(raw).strip()
    m = re.search(
        r"(january|february|march|april|may|june|july|august|september|october|november|december)"
        r"[a-z]*\s+(\d{1,2})\s*,?\s*(\d{4})",
        s, re.I,
    )
    if m:
        return MONTHS[m.group(1).lower()], str(int(m.group(2))), m.group(3)
    m = re.search(
        r"(\d{1,2})\s+(january|february|march|april|may|june|july|august|september|october|november|december)"
        r"[a-z]*\s+(\d{4})",
        s, re.I,
    )
    if m:
        return MONTHS[m.group(2).lower()], str(int(m.group(1))), m.group(3)
    parts = re.split(r"[/\-.]", s)
    if len(parts) == 3:
        a, b, c = [p.strip() for p in parts]
        if len(a) == 4:
            return b.lstrip("0") or b, c.lstrip("0") or c, a
        if len(c) == 4:
            if a.isdigit() and int(a) > 12:
                return b.lstrip("0") or b, a.lstrip("0") or a, c
            return a.lstrip("0") or a, b.lstrip("0") or b, c
    return None


def _split_name(info):
    first = (info.get("first_name") or "").strip()
    last = (info.get("last_name") or "").strip()
    if _good(first) and _good(last):
        return first, last
    name = (info.get("name") or "").strip()
    if _good(name):
        name = re.sub(r"\s+", " ", name)
        bits = name.split(" ")
        first = first or bits[0]
        last = last or (" ".join(bits[1:]) if len(bits) > 1 else bits[0])
    return first, last


def _fill_identity(driver, account_info):
    info = account_info or {}
    first, last = _split_name(info)
    print(f"👤 Filling ACSR identity  first={first!r} last={last!r} dob={info.get('dob')!r}")

    if _good(first):
        el = _find_first(driver, FIRST_SELECTORS, timeout=3)
        if el:
            _type_into(driver, el, first)
            print("✉️ First name typed")
        else:
            print("⚠️ First-name field not found")
    else:
        print("⚠️ No first name in scrape — ACSR will reject the form")

    if _good(last):
        el = _find_first(driver, LAST_SELECTORS, timeout=2)
        if el:
            _type_into(driver, el, last)
            print("✉️ Last name typed")
        else:
            print("⚠️ Last-name field not found")

    parsed = _parse_dob(info.get("dob"))
    if parsed:
        month, day, year = parsed
        _select_by_ids(driver, ("iBirthMonth", "BirthMonth", "BirthMonthDropDown", "iSignupBirthMonth"), month)
        _select_by_ids(driver, ("iBirthDay", "BirthDay", "BirthDayDropDown", "iSignupBirthDay"), day)
        _select_by_ids(driver, ("iBirthYear", "BirthYear", "BirthYearDropDown", "iSignupBirthYear"), year)
        print(f"🎂 DOB set {month}/{day}/{year}")
    else:
        print("⚠️ No parseable DOB in scrape")

    region = info.get("region")
    if _good(region):
        _select_by_ids(driver, ("iCountry", "Country", "iSignupCountry", "region"), region)

    return _good(first) and _good(last)


def _click_next(driver):
    for by, sel in [
        (By.CSS_SELECTOR, 'button[data-testid="primaryButton"]'),
        (By.ID, "iNext"),
        (By.ID, "idSIButton9"),
        (By.ID, "iBtn_action"),
        (By.ID, "iLandingViewAction"),
        (By.ID, "idSubmit_proofs_Email"),
        (By.CSS_SELECTOR, 'input[type="submit"]'),
        (By.CSS_SELECTOR, 'button[type="submit"]'),
        (By.XPATH, '//button[contains(., "Next")]'),
        (By.XPATH, '//input[@value="Next"]'),
        (By.XPATH, '//button[contains(., "Submit")]'),
        (By.XPATH, '//input[@value="Submit"]'),
        (By.XPATH, '//button[contains(., "Continue")]'),
        (By.XPATH, '//button[contains(., "Verify")]'),
        (By.XPATH, '//input[@value="Verify"]'),
    ]:
        try:
            el = driver.find_element(by, sel)
            if el.is_displayed() and el.is_enabled():
                el.click()
                print(f"➡️ ACSR next via {sel}")
                return True
        except Exception:
            continue
    return False


def _enter_captcha(driver, text):
    for by, sel in [
        (By.ID, "hipCaptcha"),
        (By.ID, "captchaInput"),
        (By.ID, "wlspispSolutionElement"),
        (By.ID, "hip-solution"),
        (By.NAME, "hip"),
        (By.NAME, "Solution"),
        (By.CSS_SELECTOR, 'input[aria-label*="captcha" i]'),
        (By.CSS_SELECTOR, 'input[name*="captcha" i]'),
        (By.CSS_SELECTOR, 'input[id*="captcha" i]'),
        (By.CSS_SELECTOR, 'input[id*="hip" i]'),
        (By.CSS_SELECTOR, 'input[name*="hip" i]'),
        (By.CSS_SELECTOR, 'input[type="text"]'),
    ]:
        try:
            for el in driver.find_elements(by, sel):
                if el.is_displayed() and el.is_enabled():
                    typ = (el.get_attribute("type") or "text").lower()
                    if typ in ("hidden", "email", "password"):
                        continue
                    eid = (el.get_attribute("id") or "").lower()
                    name = (el.get_attribute("name") or "").lower()
                    if "email" in eid or "email" in name or "account" in eid:
                        continue
                    if "first" in eid or "last" in eid or "name" in eid:
                        continue
                    el.click()
                    el.send_keys(Keys.CONTROL, "a")
                    el.send_keys(text)
                    print("🧩 CAPTCHA typed")
                    return True
        except Exception:
            continue
    return False


def _enter_otp(driver, code):
    for by, sel in CODE_SELECTORS:
        try:
            for el in driver.find_elements(by, sel):
                if not el.is_displayed() or not el.is_enabled():
                    continue
                typ = (el.get_attribute("type") or "text").lower()
                if typ in ("hidden", "email", "password"):
                    continue
                el.click()
                el.send_keys(Keys.CONTROL, "a")
                el.send_keys(str(code))
                print(f"🔐 Typed security code {code} via {sel}")
                return True
        except Exception:
            continue
    return False


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


def extract_reset_link(blob):
    if not blob:
        return None
    if isinstance(blob, (list, tuple)):
        for item in blob:
            link = extract_reset_link(item)
            if link:
                return link
        blob = " ".join(str(x) for x in blob)
    if isinstance(blob, dict):
        parts = []
        for k in ("text", "html", "intro", "subject", "preview", "link", "body", "mail_body"):
            if blob.get(k):
                parts.append(str(blob[k]))
        parts.extend(str(v) for v in blob.values() if isinstance(v, str))
        blob = "\n".join(parts)
    text = htmlmod.unescape(str(blob))
    candidates = []
    for u in HREF_RE.findall(text) + LINK_RE.findall(text) + URL_RE.findall(text):
        u = _clean_url(u)
        if not u.startswith("http"):
            continue
        low = u.lower()
        if any(h in low for h in RESET_HINTS) or any(
            h in low for h in ("account.live.com", "login.live.com", "safelink")
        ):
            if u not in candidates:
                candidates.append(u)
    if not candidates:
        return None

    def score(u):
        l = u.lower()
        s = 0
        if "resetpassword" in l or "password/reset" in l:
            s += 80
        if "account.live.com" in l or "login.live.com" in l:
            s += 40
        if "recover" in l or "proof" in l:
            s += 15
        if "unsubscribe" in l or "privacy" in l:
            s -= 50
        if "safelink" in l:
            s -= 5
        return s

    candidates.sort(key=score, reverse=True)
    if score(candidates[0]) <= 0:
        return None
    return candidates[0]


def _inbox_list(token):
    if tempmail is None:
        return []
    try:
        data = tempmail.get_messages(token)
    except Exception as e:
        print(f"⚠️ get_messages: {e}")
        return []
    if isinstance(data, tuple):
        data = data[0] if data else []
    if isinstance(data, dict):
        data = data.get("hydra:member") or data.get("messages") or data.get("list") or []
    if not isinstance(data, list):
        data = [data] if data else []
    out = []
    for m in data:
        if m is None:
            continue
        if isinstance(m, dict):
            out.append(m)
        else:
            out.append({"id": str(len(out)), "text": str(m), "intro": str(m)})
    return out


def _messages_from_tempmail(token):
    blobs = []
    for item in _inbox_list(token):
        blobs.append(item)
        mid = item.get("id") if isinstance(item, dict) else None
        if mid and tempmail is not None and hasattr(tempmail, "read_message"):
            try:
                try:
                    full = tempmail.read_message(token, mid)
                except TypeError:
                    full = tempmail.read_message(token, mid, None)
                if full:
                    blobs.append(full)
            except Exception as e:
                print(f"⚠️ read_message: {e}")
    return blobs


def _get_otp(token, timeout=OTP_WAIT_S):
    if tempmail is None:
        return None
    if hasattr(tempmail, "wait_for_otp"):
        try:
            return tempmail.wait_for_otp(token, timeout=timeout)
        except TypeError:
            try:
                return tempmail.wait_for_otp(token)
            except Exception as e:
                print(f"⚠️ wait_for_otp: {e}")
        except Exception as e:
            print(f"⚠️ wait_for_otp: {e}")
    if hasattr(tempmail, "extract_otp"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            for b in _messages_from_tempmail(token):
                try:
                    otp = tempmail.extract_otp(b)
                except Exception:
                    otp = None
                if otp:
                    print(f"🔐 OTP from inbox: {otp}")
                    return otp
            time.sleep(MAIL_POLL_S)
    return None


def _handle_code_page(driver, token):
    if not _is_code_page(driver):
        return None
    for n in range(3):
        if not _is_code_page(driver):
            return None
        print(f"🔐 Microsoft asked for a security code (pass {n + 1})")
        print(_page_dump(driver))
        otp = _get_otp(token, timeout=OTP_WAIT_S)
        if not otp:
            return (
                "ERROR: Microsoft asked for a security code but none arrived in the temp inbox.\n"
                + _page_dump(driver)
            )
        if not _enter_otp(driver, otp):
            return (
                f"ERROR: Got security code `{otp}` but could not find the code input.\n"
                + _page_dump(driver)
            )
        time.sleep(0.35)
        _click_next(driver)
        time.sleep(1.8)
        t = _visible_text(driver)
        if "incorrect" in t and "code" in t:
            print("❌ Microsoft rejected that code, retrying…")
            continue
        if _captcha_wrong(driver):
            return "CAPTCHA_RETRY_NEEDED"
    if _is_code_page(driver):
        return "ERROR: Still on the security-code page after 3 attempts.\n" + _page_dump(driver)
    return None


def _poll_reset_link(token, timeout=MAIL_WAIT_S):
    if tempmail is not None and hasattr(tempmail, "wait_for_reset_link"):
        try:
            return tempmail.wait_for_reset_link(token, timeout=timeout)
        except TypeError:
            try:
                return tempmail.wait_for_reset_link(token)
            except Exception as e:
                print(f"⚠️ wait_for_reset_link: {e}")
        except Exception as e:
            print(f"⚠️ wait_for_reset_link: {e}")

    print(f"📬 Polling temp inbox up to {timeout}s for Microsoft reset link…")
    deadline = time.time() + timeout
    last_log = 0
    while time.time() < deadline:
        blobs = _messages_from_tempmail(token)
        print(f"   inbox blobs={len(blobs)}")
        for b in blobs:
            link = None
            if tempmail is not None and hasattr(tempmail, "extract_reset_link"):
                try:
                    link = tempmail.extract_reset_link(b)
                except Exception:
                    link = None
            if not link:
                link = extract_reset_link(b)
            if link:
                print(f"🔗 Reset link: {link[:120]}")
                return link
        now = time.time()
        if now - last_log > 20:
            print(f"⏳ Still waiting for recovery mail… {int(deadline - now)}s left")
            last_log = now
        time.sleep(MAIL_POLL_S)
    return None


def _fill_recovery_pages(driver, account_info, token=None, max_pages=12):
    for n in range(max_pages):
        if _is_24h_page(driver):
            return True
        t = _visible_text(driver)
        if "too many requests" in t:
            return False
        if _captcha_wrong(driver):
            return False
        if _is_code_page(driver) and token is not None:
            err = _handle_code_page(driver, token)
            if err:
                raise RuntimeError(err)
            continue
        if _is_identity_page(driver):
            filled = _fill_identity(driver, account_info)
            if not filled:
                raise RuntimeError(
                    "ERROR: ACSR is on the first-name / last-name / birth-date page but "
                    "scrape had no usable name. Fix profile scrape (name/DOB/region not found).\n"
                    + _page_dump(driver)
                )
        if not _click_next(driver):
            try:
                driver.find_element(By.TAG_NAME, "body").send_keys(Keys.RETURN)
            except Exception:
                pass
        time.sleep(1.4)
        if _is_24h_page(driver):
            return True
        if "enter a valid first name" in _visible_text(driver) or "enter a valid last name" in _visible_text(driver):
            if n >= 1:
                raise RuntimeError(
                    "ERROR: Microsoft rejected the name/DOB on ACSR (enter a valid first/last name). "
                    f"Scraped name={account_info.get('name')!r} dob={account_info.get('dob')!r}.\n"
                    + _page_dump(driver)
                )
    return _is_24h_page(driver)


def continue_acsr_flow(driver, account_info, token, captcha_text, user_id=None):
    print(f"🧩 Continuing ACSR with CAPTCHA `{captcha_text}`")
    print(f"   scrape name={ (account_info or {}).get('name')!r} "
          f"dob={(account_info or {}).get('dob')!r} "
          f"region={(account_info or {}).get('region')!r}")
    try:
        if not _enter_captcha(driver, captcha_text):
            print("⚠️ Could not find captcha input — submitting anyway")
        time.sleep(0.3)
        _click_next(driver)
        time.sleep(1.6)

        if _captcha_wrong(driver):
            print("❌ Wrong CAPTCHA")
            return "CAPTCHA_RETRY_NEEDED"

        page = _visible_text(driver)
        if "too many requests" in page:
            return "ERROR: Microsoft rate-limited ACSR (Too Many Requests)\n" + _page_dump(driver)

        if _is_identity_page(driver):
            print("👤 Identity page (name/DOB) — not a code page")
            filled = _fill_identity(driver, account_info)
            if not filled:
                return (
                    "ERROR: ACSR asked for first name / last name / birth date but scrape "
                    "returned Name not found / DOB not found. The profile scraper must land "
                    "on account.microsoft.com/profile and read the Personal info card.\n"
                    + _page_dump(driver)
                )
            _click_next(driver)
            time.sleep(1.5)

        code_err = _handle_code_page(driver, token)
        if code_err == "CAPTCHA_RETRY_NEEDED":
            return code_err
        if code_err:
            return code_err

        try:
            submitted = _fill_recovery_pages(driver, account_info, token=token)
        except RuntimeError as e:
            msg = str(e)
            if msg == "CAPTCHA_RETRY_NEEDED":
                return msg
            return msg if msg.startswith("ERROR") else f"ERROR: {msg}"

        if _captcha_wrong(driver):
            return "CAPTCHA_RETRY_NEEDED"

        code_err = _handle_code_page(driver, token)
        if code_err == "CAPTCHA_RETRY_NEEDED":
            return code_err
        if code_err:
            return code_err

        if _is_24h_page(driver) or submitted:
            print("✅ ACSR accepted — polling inbox for reset URL…")
        else:
            print("ℹ️ No 24h banner yet — still polling inbox")
            print(_page_dump(driver))

        link = _poll_reset_link(token, timeout=MAIL_WAIT_S)
        if link:
            return link

        return (
            "ERROR: No Microsoft reset URL in the temp inbox within 15 minutes.\n"
            + _page_dump(driver)
        )
    except Exception as e:
        print(f"❌ ACSR continue crashed: {e}")
        try:
            dump = _page_dump(driver)
        except Exception:
            dump = ""
        return f"ERROR: {e}\n{dump}"