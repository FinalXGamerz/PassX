from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from automation.driver import create_driver, mark_driver_success, mark_driver_fail
from automation import ratelimit
import time
import random

MAX_RESET_RETRIES = 3


def _type(el, text):
    el.click()
    try:
        el.send_keys(Keys.CONTROL, "a")
    except Exception:
        pass
    for ch in text:
        el.send_keys(ch)
        time.sleep(random.uniform(0.018, 0.05))


def perform_password_reset(resetlink, email, new_password):
    print("🔁 Starting password reset flow...")
    ratelimit.wait_turn("reset")

    for attempt in range(MAX_RESET_RETRIES + 1):
        use_proxy = attempt > 0
        force_rotate = attempt > 1
        if attempt > 0:
            ratelimit.trip()
            ratelimit.wait_turn(f"reset-retry-{attempt}")
            print(f"🔄 Password reset retry #{attempt} with proxy...")

        driver = create_driver(headless=False, use_proxy=use_proxy, force_rotate=force_rotate)
        wait = WebDriverWait(driver, 25)
        try:
            result = _perform_reset_inner(driver, wait, resetlink, email, new_password)
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
            print(f"❌ Password reset attempt {attempt + 1} failed: {e}")
            mark_driver_fail(driver)
            try:
                driver.quit()
            except Exception:
                pass
            continue
    return None


def _perform_reset_inner(driver, wait, resetlink, email, new_password):
    try:
        driver.get(resetlink)
        print("🔗 Opened reset link.")
        page = driver.page_source or ""
        if "Too Many Requests" in page or "temporarily blocked" in page.lower():
            ratelimit.trip()
            return "RATE_LIMITED"

        email_input = wait.until(EC.presence_of_element_located((By.ID, "AccountNameInput")))
        _type(email_input, email)
        email_input.send_keys(Keys.RETURN)
        print("📨 Email entered.")

        new_pass = wait.until(EC.presence_of_element_located((By.ID, "iPassword")))
        _type(new_pass, new_password)
        new_pass_re = wait.until(EC.presence_of_element_located((By.ID, "iRetypePassword")))
        _type(new_pass_re, new_password)
        print("🔑 New password filled.")
        time.sleep(0.4)
        new_pass_re.send_keys(Keys.RETURN)
        time.sleep(3.5)

        page = driver.page_source or ""
        if "Too Many Requests" in page or "temporarily blocked" in page.lower():
            ratelimit.trip()
            return "RATE_LIMITED"

        try:
            driver.find_element(By.CSS_SELECTOR, 'input[data-nuid="PreviousPasswordInput"]')
            fallback_pass = "Px" + "".join(str(random.randint(0, 9)) for _ in range(6)) + "!A"
            print(f"⚠️ Password rejected — fallback: {fallback_pass}")
            _type(driver.find_element(By.ID, "iPassword"), fallback_pass)
            _type(driver.find_element(By.ID, "iRetypePassword"), fallback_pass)
            driver.find_element(By.ID, "iRetypePassword").send_keys(Keys.RETURN)
            return fallback_pass
        except Exception:
            print("✅ Password accepted.")
            return new_password
    except Exception as e:
        print(f"❌ Password reset may have failed: {e}")
        return None