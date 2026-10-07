from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from tempmail import get_otp_from_first_email, wait_for_emails, read_message, extract_specific_link
from datetime import datetime
from automation.captcha import download_captcha
import time

def get_month_name(date_str):
    try:
        date_obj = datetime.strptime(date_str, "%m/%d/%Y")
        month_name = date_obj.strftime("%B")
        day = str(date_obj.day)
        year = str(date_obj.year)
        return month_name, day, year
    except ValueError:
        return "May", "5", "1989"



def continue_acsr_flow(driver, account_info, token, captcha_text, user_id):
    wait = WebDriverWait(driver, 20)

    try:

        captcha_value = captcha_text

        try:

            captcha_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, '//input[contains(@id, "SolutionElement")]'))
            )
            captcha_input.clear()
            captcha_input.send_keys(captcha_value)
            captcha_input.send_keys(Keys.RETURN)
            print("📨 CAPTCHA submitted. Waiting for OTP input field...")


            code_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "iOttText"))
            )
            print("✅ CAPTCHA accepted.")

        except Exception:
            print("❌ CAPTCHA failed or OTP input not found.")
            print("🔁 Waiting for new CAPTCHA to regenerate...\n")

            try:
                captcha_image = download_captcha(driver)
                print("🧩 New CAPTCHA downloaded.")
                with open(f"captcha_retry_{user_id}.png", "wb") as f:
                    f.write(captcha_image.read())

                return "CAPTCHA_RETRY_NEEDED"
            except Exception as e:
                print(f"❌ Failed to detect new CAPTCHA image: {e}")
                return "CAPTCHA_DOWNLOAD_FAILED"


        print("⌛ Waiting for OTP via tempmail...")
        otp = get_otp_from_first_email(token)
        if not otp:
            print("❌ OTP not received.")
            return "❌ OTP not received."

        print(f"📥 OTP received: {otp}")


        code_input = wait.until(EC.presence_of_element_located((By.ID, "iOttText")))
        code_input.clear()
        code_input.send_keys(otp)
        code_input.send_keys(Keys.RETURN)
        print("🔐 OTP submitted.")
        time.sleep(2)

        # Step 5: Fill name
        print("🧾 Filling name...")
        first, last = account_info['name'].split(maxsplit=1) if ' ' in account_info['name'] else (account_info['name'], "Last")
        wait.until(EC.presence_of_element_located((By.ID, "FirstNameInput"))).send_keys(first)
        wait.until(EC.presence_of_element_located((By.ID, "LastNameInput"))).send_keys(last)

        month, day, year = get_month_name(account_info['dob'])

        if not all([month, day, year]):
            raise ValueError("❌ Invalid or missing DOB, aborting ACSR form.")


        day_element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "BirthDate_dayInput"))
        )
        Select(day_element).select_by_visible_text(day)


        month_element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "BirthDate_monthInput"))
        )
        Select(month_element).select_by_visible_text(month)


        year_element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "BirthDate_yearInput"))
        )
        Select(year_element).select_by_visible_text(year)
        print(f"Parsed DOB: {month=}, {day=}, {year=}")
        print("✅ Dropdown Options Loaded:", [o.text for o in Select(month_element).options])

        print("📆 DOB filled.")


        wait.until(EC.presence_of_element_located((By.ID, "CountryInput"))).send_keys(account_info['region'])
        print("🌍 Region filled.")
        time.sleep(1)


        first_name_input = driver.find_element(By.ID, "FirstNameInput")
        first_name_input.send_keys(Keys.RETURN)
        time.sleep(1)

        print("🔐 Entering old password...")
        previous_pass_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'input[data-nuid="PreviousPasswordInput"]'))
        )
        previous_pass_input.clear()
        previous_pass_input.send_keys(account_info["password"])
        print("✅ Old password entered.")
        time.sleep(2)


        skype_checkbox = driver.find_element(By.ID, "ProductOptionSkype")
        if not skype_checkbox.is_selected():
            skype_checkbox.click()
            print("☑️ Skype option selected.")


        xbox_checkbox = driver.find_element(By.ID, "ProductOptionXbox")
        if not xbox_checkbox.is_selected():
            xbox_checkbox.click()
            print("🎮 Xbox option selected.")

        # Skype info
        previous_pass_input.send_keys(Keys.RETURN)
        skype_name_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "SkypeNameInput"))
        )
        skype_name_input.clear()
        skype_name_input.send_keys(account_info["skype_id"])

        skype_email_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "SkypeAccountCreateEmailInput"))
        )
        skype_email_input.clear()
        skype_email_input.send_keys(account_info["skype_email"])
        print("🔑 Skype info filled.")
        time.sleep(2)
        skype_email_input.send_keys(Keys.RETURN)

        # Xbox product
        print("🎮 Selecting Xbox One...")
        xbox_radio = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "XboxOneOption"))
        )
        if not xbox_radio.is_selected():
            xbox_radio.click()
        xbox_radio.send_keys(Keys.ENTER)
        print("✅ Xbox One selected.")
        time.sleep(2)

        # Gamertag
        print("🎮 Entering Xbox Gamertag...")
        xbox_name_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "XboxGamertagInput"))
        )
        xbox_name_input.clear()
        xbox_name_input.send_keys(account_info["gamertag"])
        xbox_name_input.send_keys(Keys.RETURN)
        print("✅ Gamertag submitted.")

        try:
            print("📬 Fetching password reset link from temp mail...")
            time.sleep(90)

            emails = wait_for_emails(token, expected_count=2)
            email2 = read_message(token, emails[0]['id'])
            resetlink = extract_specific_link(email2['text'])

            try:
                driver.quit()
            except Exception:
                pass

            if resetlink:
                print(f"🔗 Target Link: {resetlink}")
                return resetlink
            else:
                print("❌ Target reset link not found.")
                return None
        except Exception as e:
            print(f"❌ Failed to fetch or extract reset link: {e}")
            return None

    except Exception as e:
        print(f"❌ Error while continuing ACSR flow: {e}")
        return None
