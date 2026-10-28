from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import os
import platform
import random

from automation.proxymanager import get_proxy_manager

STEALTH_JS = r"""
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.navigator.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){}, app: {} };
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
"""


def _ua():
    if platform.system().lower() == "linux":
        return (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
        )
    return (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
    )


def _build_options(headless, use_proxy, force_rotate):
    w = random.choice([1366, 1440, 1536, 1920])
    h = random.choice([768, 900, 864, 1080])
    options = Options()
    options.page_load_strategy = "eager"

    if headless:
        options.add_argument("--headless=new")
    else:
        options.add_argument("--start-maximized")

    options.add_argument("--disable-gpu")
    options.add_argument(f"--window-size={w},{h}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--incognito")
    options.add_argument("--disable-webauthn")
    options.add_argument("--disable-features=WebAuthentication,WebAuthn,PasswordImport")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--lang=en-US")
    options.add_argument("--disable-infobars")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--password-store=basic")
    options.add_argument("--use-mock-keychain")
    options.add_argument(f"--user-agent={_ua()}")

    proxy_applied = None
    if use_proxy:
        try:
            mgr = get_proxy_manager()
            proxy = mgr.get_next_proxy(force_rotate=force_rotate)
            if proxy:
                options.add_argument(f"--proxy-server={proxy.auth_string}")
                proxy_applied = proxy
                print(f"🌐 Proxy applied: {proxy.ip}:{proxy.port}")
        except Exception as e:
            print(f"⚠️ Proxy skipped: {e}")

    for chrome_path in [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "/opt/google/chrome/chrome",
        "/snap/bin/chromium",
    ]:
        if os.path.exists(chrome_path):
            options.binary_location = chrome_path
            print(f"🔍 Found Chrome at: {chrome_path}")
            break
    return options, proxy_applied


def _start_chrome(options):
    last = None
    try:
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options,
        )
        print("✅ ChromeDriver initialized (manager)")
        return driver
    except Exception as e:
        last = e
        print(f"⚠️ ChromeDriverManager failed: {e}")
    try:
        driver = webdriver.Chrome(options=options)
        print("✅ ChromeDriver initialized (system)")
        return driver
    except Exception as e:
        last = e
        print(f"❌ System ChromeDriver failed: {e}")
        raise last


def create_driver(headless=False, use_proxy=False, force_rotate=False):
    options, proxy_applied = _build_options(headless, use_proxy, force_rotate)
    driver = _start_chrome(options)
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": STEALTH_JS})
    except Exception as e:
        print(f"⚠️ stealth inject: {e}")
    try:
        driver.set_page_load_timeout(25)
        driver.implicitly_wait(0)
    except Exception:
        pass
    driver._proxy_applied = proxy_applied
    return driver


def mark_driver_success(driver):
    proxy = getattr(driver, "_proxy_applied", None)
    if proxy:
        try:
            get_proxy_manager().mark_current_success()
        except Exception:
            pass


def mark_driver_fail(driver):
    proxy = getattr(driver, "_proxy_applied", None)
    if proxy:
        try:
            get_proxy_manager().mark_current_fail()
        except Exception:
            pass