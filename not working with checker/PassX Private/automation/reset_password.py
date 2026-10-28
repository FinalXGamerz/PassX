from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from automation.driver import create_driver, mark_driver_success, mark_driver_fail
from automation import ratelimit
import time
import random

MAX_RESET_RETRIES = 3

EMAIL_IDS = [
    "AccountNameInput", "i0116", "usernameEntry", "EmailAddress",
    "iProofEmail", "loginfmt",
]
PASS_IDS = ["iPassword", "Password", "NewPassword", "iNewPassword", "passwordEntry"]
RETYPE_IDS = ["iRetypePassword", "RetypePassword", "ConfirmPassword", "iConfirmPassword"]
NEXT_IDS = ["iNext", "idSIButton9", "iBtn_action", "iLandingViewAction"]


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


def _find(driver, wait, ids, timeout=20):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        for eid in ids:
            try:
                el = driver.find_element(By.ID, eid)
                if el.is_displayed() and el.is_enabled():
                    return el
            except Exception as e:
                last = e
            try:
                el = driver.find_element(By.NAME, eid)
                if el.is_displayed() and el.is_enabled():
                    return el
            except Exception as e:
                last = e
        try:
            el = wait.until(EC.presence_of_element_located((By.ID, ids[0])))
            if el:
                return el
        except Exception as e:
            last = e
        time.sleep(0.25)
    if last:
        print(f"⚠️ reset field not found: {last}")
    return None


def _click_next(driver):
    for eid in NEXT_IDS:
        try:
            el = driver.find_element(By.ID, eid)
            if el.is_displayed() and el.is_enabled():
                el.click()
                return True
        except Exception:
            continue
    for by, sel in [
        (By.CSS_SELECTOR, 'button[data-testid="primaryButton"]'),
        (By.CSS_SELECTOR, 'button[type="submit"]'),
        (By.CSS_SELECTOR, 'input[type="submit"]'),
        (By.XPATH, '//button[contains(., "Next")]'),
        (By.XPATH, '//input[@value="Next"]'),
    ]:
        try:
            el = driver.find_element(by, sel)
            if el.is_displayed() and el.is_enabled():
                el.click()
                return True
        except Exception:
            continue
    return False


def _page_blocked(driver):
    try:
        page = (driver.page_source or "").lower()
    except Exception:
        return False
    return "too many requests" in page or "temporarily blocked" in page or "unusual activity" in page


def perform_password_reset(reset_link, email=None, new_password=None):
    """
    Called as:
      perform_password_reset(reset_link, email, new_password)
      perform_password_reset(driver, reset_link, new_password)
    """
    existing = None
    if reset_link is not None and not isinstance(reset_link, str) and hasattr(reset_link, "get"):
        existing = reset_link
        reset_link = email
        email = None

    print("🔁 Starting password reset...")
    try:
        ratelimit.wait_turn("reset")
    except Exception:
        pass

    if existing is not None:
        wait = WebDriverWait(existing, 25)
        try:
            result = _perform_reset_inner(existing, wait, reset_link, email, new_password)
            return None if result == "RATE_LIMITED" else result
        except Exception as e:
            print(f"❌ Reset on existing Chrome: {e}")
            return None

    for attempt in range(MAX_RESET_RETRIES + 1):
        use_proxy = attempt > 0
        force_rotate = attempt > 1
        if attempt > 0:
            try:
                ratelimit.trip()
                ratelimit.wait_turn(f"reset-retry-{attempt}")
            except Exception:
                pass
            print(f"🔄 Reset retry #{attempt}")

        driver = create_driver(headless=False, use_proxy=use_proxy, force_rotate=force_rotate)
        wait = WebDriverWait(driver, 25)
        try:
            result = _perform_reset_inner(driver, wait, reset_link, email, new_password)
            if result == "RATE_LIMITED":
                mark_driver_fail(driver)
                driver.quit()
                continue
            if result:
                mark_driver_success(driver)
                driver.quit()
                return result
            driver.quit()
            return None
        except Exception as e:
            print(f"❌ Reset attempt {attempt + 1}: {e}")
            mark_driver_fail(driver)
            try:
                driver.quit()
            except Exception:
                pass
            continue
    return None


def _perform_reset_inner(driver, wait, reset_link, email, new_password):
    try:
        if not reset_link or not isinstance(reset_link, str):
            print(f"❌ Bad reset link: {reset_link!r}")
            return None

        driver.get(reset_link)
        print("🔗 Opened reset link.")
        time.sleep(1.2)

        if _page_blocked(driver):
            try:
                ratelimit.trip()
            except Exception:
                pass
            return "RATE_LIMITED"

        email_input = _find(driver, wait, EMAIL_IDS, timeout=12)
        if email_input is not None and email:
            _type(email_input, email)
            try:
                email_input.send_keys(Keys.RETURN)
            except Exception:
                _click_next(driver)
            print("📨 Email entered.")
            time.sleep(1.0)
        elif email_input is None:
            print("ℹ️ No email field on reset page — going straight to password")

        if _page_blocked(driver):
            try:
                ratelimit.trip()
            except Exception:
                pass
            return "RATE_LIMITED"

        new_pass = _find(driver, wait, PASS_IDS, timeout=20)
        if new_pass is None:
            print("❌ New-password field never showed up")
            try:
                print(f"   URL: {driver.current_url}")
                print(f"   Title: {driver.title}")
            except Exception:
                pass
            return None
        _type(new_pass, new_password)

        new_pass_re = _find(driver, wait, RETYPE_IDS, timeout=8)
        if new_pass_re is not None:
            _type(new_pass_re, new_password)
            print("🔑 New password filled.")
            time.sleep(0.4)
            try:
                new_pass_re.send_keys(Keys.RETURN)
            except Exception:
                _click_next(driver)
        else:
            print("🔑 New password filled (no retype box).")
            try:
                new_pass.send_keys(Keys.RETURN)
            except Exception:
                _click_next(driver)

        time.sleep(3.5)

        if _page_blocked(driver):
            try:
                ratelimit.trip()
            except Exception:
                pass
            return "RATE_LIMITED"

        try:
            prev = driver.find_element(By.CSS_SELECTOR, 'input[data-nuid="PreviousPasswordInput"]')
            if prev.is_displayed():
                fallback_pass = "Px" + "".join(str(random.randint(0, 9)) for _ in range(6)) + "!A"
                print(f"⚠️ Password rejected — fallback: {fallback_pass}")
                box = _find(driver, wait, PASS_IDS, timeout=6) or driver.find_element(By.ID, "iPassword")
                rebox = _find(driver, wait, RETYPE_IDS, timeout=4)
                _type(box, fallback_pass)
                if rebox:
                    _type(rebox, fallback_pass)
                    rebox.send_keys(Keys.RETURN)
                else:
                    box.send_keys(Keys.RETURN)
                time.sleep(2.5)
                return fallback_pass
        except Exception:
            pass

        print("✅ Password accepted.")
        return new_password
    except Exception as e:
        print(f"❌ Password reset may have failed: {e}")
        return None