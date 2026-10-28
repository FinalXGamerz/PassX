"""
Open https://account.live.com/acsr, fill Microsoft email + temp inbox, capture CAPTCHA.
Raises RuntimeError with the EXACT issue so Discord shows it.
"""
import random
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from automation.captcha import download_captcha
from automation.driver import create_driver
from tempmail import generate_temp_mail_account

try:
    from automation import ratelimit
except Exception:
    class ratelimit:
        @staticmethod
        def wait_turn(label="acsr"):
            return None

        @staticmethod
        def trip(seconds=None):
            return 0


EMAIL_SELECTORS = [
    (By.ID, "AccountNameInput"),
    (By.ID, "iProofEmail"),
    (By.ID, "EmailAddress"),
    (By.NAME, "EmailAddress"),
    (By.NAME, "loginfmt"),
    (By.CSS_SELECTOR, 'input[type="email"]'),
    (By.CSS_SELECTOR, 'input[name*="email" i]'),
    (By.CSS_SELECTOR, 'input[id*="email" i]'),
    (By.CSS_SELECTOR, 'input[autocomplete="username"]'),
]
ALT_SELECTORS = [
    (By.ID, "iCMailInput"),
    (By.ID, "AltEmail"),
    (By.ID, "iProofEmail2"),
    (By.ID, "iAltEmail"),
    (By.NAME, "iCMail"),
    (By.NAME, "AltEmail"),
    (By.CSS_SELECTOR, 'input[id*="CMail" i]'),
    (By.CSS_SELECTOR, 'input[id*="alt" i]'),
    (By.CSS_SELECTOR, 'input[placeholder*="alternate" i]'),
    (By.CSS_SELECTOR, 'input[placeholder*="email" i]'),
]


def _type(el, text):
    el.click()
    try:
        el.send_keys(Keys.CONTROL, "a")
    except Exception:
        pass
    try:
        el.send_keys(Keys.DELETE)
    except Exception:
        pass
    for ch in str(text):
        el.send_keys(ch)
        time.sleep(random.uniform(0.018, 0.05))


def _find(driver, selectors, timeout=12):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        for by, sel in selectors:
            try:
                for el in driver.find_elements(by, sel):
                    try:
                        if el.is_displayed() and el.is_enabled():
                            return el
                    except Exception as e:
                        last = e
            except Exception as e:
                last = e
        time.sleep(0.25)
    if last:
        print(f"⚠️ field not found: {last}")
    return None


def _page_issue(driver, extra=""):
    title = url = body = ""
    try:
        title = driver.title or ""
    except Exception:
        pass
    try:
        url = driver.current_url or ""
    except Exception:
        pass
    try:
        body = driver.find_element(By.TAG_NAME, "body").text or ""
        body = " ".join(body.split())[:900]
    except Exception:
        try:
            body = " ".join((driver.page_source or "")[:1500].split())
        except Exception:
            body = ""
    low = (body + " " + title + " " + url).lower()
    if "too many requests" in low:
        kind = "Microsoft rate-limited this IP (Too Many Requests)"
    elif "unusual activity" in low or "temporarily blocked" in low:
        kind = "Microsoft unusual-activity / blocked page"
    elif "couldn" in low and "find" in low:
        kind = "Microsoft says it could not find that account"
    elif extra:
        kind = extra
    else:
        kind = "ACSR page did not have the expected fields"
    parts = [kind]
    if extra and extra != kind:
        parts.append(extra)
    parts.append(f"URL: {url or '(none)'}")
    parts.append(f"Title: {title or '(none)'}")
    parts.append(f"Page: {body or '(no text)'}")
    return "\n".join(parts)


def submit_acsr_form(account_info: dict):
    email = (account_info or {}).get("email") or ""
    if not email:
        raise RuntimeError("ACSR called with no Microsoft email on the account_info dict.")

    try:
        ratelimit.wait_turn("acsr")
    except Exception:
        pass

    try:
        tempmail, temp_pass, token = generate_temp_mail_account()
    except Exception as e:
        raise RuntimeError(str(e)) from e

    print(f"📩 Generated Temp Mail: {tempmail}")

    driver = None
    try:
        driver = create_driver(headless=False, use_proxy=False)
    except Exception as e:
        raise RuntimeError(f"Chrome/driver failed to start: {e}") from e

    wait = WebDriverWait(driver, 20)

    try:
        driver.get("https://account.live.com/acsr")
        time.sleep(random.uniform(0.8, 1.5))

        src = driver.page_source or ""
        lowsrc = src.lower()
        if "too many requests" in lowsrc or "unusual activity" in lowsrc:
            try:
                ratelimit.trip()
            except Exception:
                pass
            issue = _page_issue(driver, "Microsoft blocked / rate-limited ACSR")
            try:
                driver.quit()
            except Exception:
                pass
            raise RuntimeError(issue)

        email_input = _find(driver, EMAIL_SELECTORS, timeout=10)
        if email_input is None:
            try:
                email_input = wait.until(EC.presence_of_element_located((By.ID, "AccountNameInput")))
            except Exception:
                email_input = None
        if email_input is None:
            raise RuntimeError(_page_issue(driver, "Could not find the Microsoft-email field"))

        _type(email_input, email)
        print("✉️ Entered Microsoft email.")

        tempmail_input = _find(driver, ALT_SELECTORS, timeout=8)
        if tempmail_input is None:
            inputs = []
            try:
                inputs = [
                    e for e in driver.find_elements(By.CSS_SELECTOR, 'input[type="email"], input[type="text"]')
                    if e.is_displayed()
                ]
            except Exception:
                inputs = []
            if len(inputs) >= 2:
                tempmail_input = inputs[1]
            elif len(inputs) == 1:
                only = inputs[0]
                try:
                    same = only == email_input
                except Exception:
                    same = False
                if not same:
                    tempmail_input = only
        if tempmail_input is None:
            raise RuntimeError(_page_issue(driver, "Could not find the alternate-email / temp-mail field"))

        _type(tempmail_input, tempmail)
        print("📨 Entered tempmail.")

        time.sleep(0.8)
        captcha_image = download_captcha(driver)
        if captcha_image is None:
            raise RuntimeError(_page_issue(driver, "CAPTCHA image could not be captured"))
        print("🧩 CAPTCHA ready.")
        return captcha_image, driver, token, tempmail

    except RuntimeError:
        try:
            if driver:
                driver.quit()
        except Exception:
            pass
        raise
    except Exception as e:
        issue = _page_issue(driver, f"ACSR automation error: {e}") if driver else f"ACSR automation error: {e}"
        print(f"❌ ACSR automation error: {e}")
        try:
            if driver:
                driver.quit()
        except Exception:
            pass
        raise RuntimeError(issue) from e