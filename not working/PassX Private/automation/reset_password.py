from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from automation.driver import create_driver, mark_driver_success, mark_driver_fail
import time

MAX_RESET_RETRIES = 3  # Retry with new proxy if blocked


def perform_password_reset(resetlink, email, new_password):
    """
    Perform password reset with automatic proxy rotation on rate limit.
    If Microsoft blocks, rotates proxy and retries.
    """
    print("🔁 Starting password reset flow...")

    for attempt in range(MAX_RESET_RETRIES + 1):
        # First attempt: proxyless. Subsequent: use proxy.
        use_proxy = attempt > 0
        force_rotate = attempt > 1
        if attempt > 0:
            print(f"🔄 Password reset retry #{attempt} with proxy (rate limited proxyless)...")

        driver = create_driver(use_proxy=use_proxy, force_rotate=force_rotate)
        wait = WebDriverWait(driver, 25)

        try:
            result = _perform_reset_inner(driver, wait, resetlink, email, new_password)

            # Check if rate limited
            if result == "RATE_LIMITED":
                print(f"🚫 Rate limited on password reset attempt {attempt + 1}")
                mark_driver_fail(driver)
                driver.quit()
                continue

            # Success
            if result:
                mark_driver_success(driver)
                driver.quit()
                return result

            # Failed but not rate limited — don't retry
            driver.quit()
            return None

        except Exception as e:
            print(f"❌ Password reset attempt {attempt + 1} failed: {e}")
            mark_driver_fail(driver)
            try:
                driver.quit()
            except:
                pass
            continue

    print(f"🚫 All password reset attempts exhausted for {email}")
    return None


def _perform_reset_inner(driver, wait, resetlink, email, new_password):
    """Inner reset logic for a single attempt."""
    try:
        driver.get(resetlink)
        print("🔗 Opened reset link.")

        # Check for rate limit on the reset page
        try:
            page = driver.page_source
            if "Too Many Requests" in page or "temporarily blocked" in page.lower():
                return "RATE_LIMITED"
        except:
            pass

        email_input = wait.until(EC.presence_of_element_located((By.ID, "AccountNameInput")))
        email_input.clear()
        email_input.send_keys(email)
        email_input.send_keys(Keys.RETURN)
        print("📨 Email entered.")


        new_pass = wait.until(EC.presence_of_element_located((By.ID, "iPassword")))
        new_pass.clear()
        new_pass.send_keys(new_password)

        new_pass_re = wait.until(EC.presence_of_element_located((By.ID, "iRetypePassword")))
        new_pass_re.clear()
        new_pass_re.send_keys(new_password)
        print("🔑 New password filled.")
        time.sleep(1)
        new_pass_re.send_keys(Keys.RETURN)


        print("⏳ Waiting for confirmation...")

        time.sleep(5)

        # Check for rate limit after submission
        try:
            page = driver.page_source
            if "Too Many Requests" in page or "temporarily blocked" in page.lower():
                return "RATE_LIMITED"
        except:
            pass

        try:
            driver.find_element(By.CSS_SELECTOR, 'input[data-nuid="PreviousPasswordInput"]')
            fallback_pass = "SladePass!12"
            print(f"⚠️ Password was rejected — retrying with fallback password: {fallback_pass}")


            pass_input = driver.find_element(By.ID, "iPassword")
            pass_input.clear()
            pass_input.send_keys(fallback_pass)

            retype_input = driver.find_element(By.ID, "iRetypePassword")
            retype_input.clear()
            retype_input.send_keys(fallback_pass)
            retype_input.send_keys(Keys.RETURN)


            return fallback_pass

        except:
            print("✅ Password accepted. No retry required.")
            return new_password


    except Exception as e:
        print(f"❌ Password reset may have failed: {e}")
        return None
