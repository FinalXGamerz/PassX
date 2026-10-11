from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from automation.captcha import download_captcha
from tempmail import generate_temp_mail_account
import time
import random
from automation.driver import create_driver
from automation import ratelimit


def _type(el, text):
    el.click()
    try:
        el.send_keys(Keys.CONTROL, "a")
    except Exception:
        pass
    for ch in text:
        el.send_keys(ch)
        time.sleep(random.uniform(0.018, 0.05))


def submit_acsr_form(account_info: dict):
    email = account_info["email"]
    ratelimit.wait_turn("acsr")

    tempmail, temp_pass, token = generate_temp_mail_account()
    print(f"📩 Generated Temp Mail: {tempmail}")

    driver = create_driver(headless=False, use_proxy=False)
    wait = WebDriverWait(driver, 20)

    try:
        driver.get("https://account.live.com/acsr")
        time.sleep(random.uniform(0.6, 1.2))

        if "Too Many Requests" in (driver.page_source or ""):
            ratelimit.trip()
            driver.quit()
            return None, None, None, None

        email_input = wait.until(EC.presence_of_element_located((By.ID, "AccountNameInput")))
        _type(email_input, email)
        print("✉️ Entered Microsoft email.")

        tempmail_input = wait.until(EC.presence_of_element_located((By.ID, "iCMailInput")))
        _type(tempmail_input, tempmail)
        print("📨 Entered tempmail.")

        captcha_image = download_captcha(driver)
        print("🧩 CAPTCHA ready.")
        return captcha_image, driver, token, tempmail

    except Exception as e:
        print(f"❌ ACSR automation error: {e}")
        try:
            driver.quit()
        except Exception:
            pass
        return None, None, None, None