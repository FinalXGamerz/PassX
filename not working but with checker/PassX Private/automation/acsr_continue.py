"""
After CAPTCHA: submit ACSR, handle Microsoft's 'we'll email you within 24 hours'
page, then poll the temp inbox until the reset link arrives.
"""
import re
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

try:
    import tempmail
except Exception:
    tempmail = None

MAIL_WAIT_S = 720          # 12 minutes — MS often sends in 1–15 min, official max 24h
MAIL_POLL_S = 8
LINK_RE = re.compile(
    r"https?://(?:account\.live\.com|account\.microsoft\.com|login\.live\.com)"
    r"/[^\s\"'<>]+",
    re.I,
)
RESET_HINTS = ("reset", "recover", "password", "proof", "acsr", "reauth", "identity")
CAPTCHA_FAIL = (
    "characters didn't match", "didn't match", "try again",
    "captcha", "the characters you entered", "hip",
)
SENT_24H = (
    "we'll send", "we will send", "within 24 hours", "up to 24 hours",
    "check your email", "we've received your request", "we received your request",
    "results of your recovery", "send the results", "you'll get an email",
    "you will get an email", "sent to the email address you gave",
)


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


def _captcha_wrong(driver):
    t = _visible_text(driver)
    return any(x in t for x in CAPTCHA_FAIL) and (
        "captcha" in t or "character" in t or "hip" in t or "try again" in t
    )


def _is_24h_page(driver):
    t = _visible_text(driver)
    return any(x in t for x in SENT_24H)


def _fill_if(driver, by, sel, value):
    if not value or str(value) in ("Name not found", "DOB not found", "Region not found", "—", "Not found"):
        return False
    try:
        el = driver.find_element(by, sel)
        if el.is_displayed() and el.is_enabled():
            el.click()
            el.send_keys(Keys.CONTROL, "a")
            el.send_keys(str(value))
            return True
    except Exception:
        return False
    return False


def _click_next(driver):
    for by, sel in [
        (By.CSS_SELECTOR, 'button[data-testid="primaryButton"]'),
        (By.ID, "iNext"),
        (By.ID, "idSIButton9"),
        (By.ID, "iBtn_action"),
        (By.CSS_SELECTOR, 'input[type="submit"]'),
        (By.CSS_SELECTOR, 'button[type="submit"]'),
        (By.XPATH, '//button[contains(., "Next")]'),
        (By.XPATH, '//input[@value="Next"]'),
        (By.XPATH, '//button[contains(., "Submit")]'),
        (By.XPATH, '//input[@value="Submit"]'),
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
        (By.NAME, "hip"),
        (By.CSS_SELECTOR, 'input[aria-label*="captcha" i]'),
        (By.CSS_SELECTOR, 'input[name*="captcha" i]'),
        (By.CSS_SELECTOR, 'input[id*="captcha" i]'),
        (By.CSS_SELECTOR, 'input[type="text"]'),
    ]:
        try:
            for el in driver.find_elements(by, sel):
                if el.is_displayed() and el.is_enabled():
                    el.click()
                    el.send_keys(Keys.CONTROL, "a")
                    el.send_keys(text)
                    print("🧩 CAPTCHA typed")
                    return True
        except Exception:
            continue
    return False


def _extract_links(blob):
    if not blob:
        return []
    if isinstance(blob, (list, tuple)):
        blob = " ".join(str(x) for x in blob)
    if isinstance(blob, dict):
        blob = " ".join(str(v) for v in blob.values())
    text = str(blob)
    found = LINK_RE.findall(text)
    extra = re.findall(r"https?://[^\s\"'<>]+", text)
    out = []
    for u in found + extra:
        u = u.rstrip(").,]}>\"'")
        low = u.lower()
        if any(h in low for h in RESET_HINTS) or "live.com" in low or "microsoft.com" in low:
            if u not in out:
                out.append(u)
    return out


def _messages_from_tempmail(token):
    if tempmail is None:
        return []
    blobs = []
    for name in (
        "get_messages", "fetch_messages", "check_inbox", "get_inbox",
        "fetch_emails", "read_mailbox", "get_mails", "poll_inbox",
    ):
        fn = getattr(tempmail, name, None)
        if not callable(fn):
            continue
        try:
            try:
                data = fn(token)
            except TypeError:
                data = fn()
            if data:
                blobs.append(data)
        except Exception as e:
            print(f"⚠️ tempmail.{name}: {e}")
    for name in ("get_reset_link", "wait_for_reset_link", "find_reset_link"):
        fn = getattr(tempmail, name, None)
        if callable(fn):
            try:
                try:
                    data = fn(token, 1)
                except TypeError:
                    try:
                        data = fn(token)
                    except TypeError:
                        data = fn()
                if isinstance(data, str) and data.startswith("http"):
                    return [{"link": data}]
                if data:
                    blobs.append(data)
            except Exception:
                pass
    return blobs


def _poll_reset_link(token, timeout=MAIL_WAIT_S):
    print(f"📬 Polling temp inbox up to {timeout}s for Microsoft reset link…")
    deadline = time.time() + timeout
    last_log = 0
    while time.time() < deadline:
        blobs = _messages_from_tempmail(token)
        for b in blobs:
            links = _extract_links(b)
            for u in links:
                low = u.lower()
                if any(x in low for x in ("resetpassword", "password/reset", "/recover", "passwd", "proof")):
                    print(f"🔗 Reset link: {u[:90]}…")
                    return u
            if links:
                print(f"🔗 Mail link: {links[0][:90]}…")
                return links[0]
        now = time.time()
        if now - last_log > 20:
            left = int(deadline - now)
            print(f"⏳ Still waiting for recovery mail… {left}s left")
            last_log = now
        time.sleep(MAIL_POLL_S)
    return None


def _fill_recovery_pages(driver, account_info, max_pages=8):
    """Walk remaining ACSR pages (name, DOB, region, skype, gt) then submit."""
    info = account_info or {}
    for _ in range(max_pages):
        if _is_24h_page(driver):
            return True
        t = _visible_text(driver)
        if "too many requests" in t:
            return False

        _fill_if(driver, By.ID, "FirstName", (info.get("name") or "").split(" ")[0] if info.get("name") else "")
        _fill_if(driver, By.ID, "LastName", " ".join((info.get("name") or "").split(" ")[1:]) if info.get("name") else "")
        _fill_if(driver, By.ID, "iBirthDate", info.get("dob"))
        _fill_if(driver, By.ID, "BirthDate", info.get("dob"))
        _fill_if(driver, By.ID, "Country", info.get("region"))
        _fill_if(driver, By.ID, "SkypeName", info.get("skype_id"))
        _fill_if(driver, By.ID, "XboxGamertag", info.get("gamertag"))
        _fill_if(driver, By.ID, "Gamertag", info.get("gamertag"))

        if not _click_next(driver):
            try:
                driver.find_element(By.TAG_NAME, "body").send_keys(Keys.RETURN)
            except Exception:
                pass
        time.sleep(1.2)
        if _is_24h_page(driver):
            return True
    return _is_24h_page(driver)


def continue_acsr_flow(driver, account_info, token, captcha_text, user_id=None):
    """
    Returns:
      reset URL string
      'CAPTCHA_RETRY_NEEDED'
      'ERROR: …'
    """
    print(f"🧩 Continuing ACSR with CAPTCHA `{captcha_text}`")
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
            return "ERROR: Rate limited on ACSR"

        # remaining form pages (name/dob/etc) + 24h confirmation
        submitted = _fill_recovery_pages(driver, account_info)
        if _captcha_wrong(driver):
            return "CAPTCHA_RETRY_NEEDED"

        if _is_24h_page(driver) or submitted:
            print("✅ ACSR accepted — Microsoft will email a link (up to 24h). Polling inbox…")
        else:
            print("ℹ️ No 24h banner yet — still polling inbox in case mail already sent")

        link = _poll_reset_link(token, timeout=MAIL_WAIT_S)
        if link:
            return link

        return (
            "ERROR: Microsoft accepted the recovery form (24h review). "
            "Reset email did not land in the temp inbox within 12 minutes. "
            "Wait and retry, or check the temp mailbox later."
        )
    except Exception as e:
        print(f"❌ ACSR continue crashed: {e}")
        return f"ERROR: {e}"