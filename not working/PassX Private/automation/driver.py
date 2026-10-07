from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import os
import platform

from automation.proxymanager import get_proxy_manager


def create_driver(headless=True, use_proxy=True, force_rotate=False):
    """
    Create a Chrome WebDriver instance.
    If use_proxy=True and proxies are available, automatically applies the next
    proxy from the rotation pool. If force_rotate=True, skips the current proxy
    and uses the next one (for retries after blocks).
    """

    options = Options()

    if headless:
        options.add_argument("--headless=new")
    else:
        options.add_argument("--start-minimized")

    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--incognito")
    options.add_argument("--disable-webauthn")
    options.add_argument("--disable-features=WebAuthentication,WebAuthn")

    system = platform.system().lower()
    if system == 'linux':
        user_agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
    else:
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"

    options.add_argument(f"user-agent={user_agent}")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    # ── Proxy rotation ──
    proxy_applied = None
    if use_proxy:
        mgr = get_proxy_manager()
        proxy = mgr.get_next_proxy(force_rotate=force_rotate)
        if proxy:
            options.add_argument(f"--proxy-server={proxy.auth_string}")
            proxy_applied = proxy
            print(f"🌐 Proxy applied: {proxy.ip}:{proxy.port}")

    chrome_paths = [
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "/opt/google/chrome/chrome",
        "/snap/bin/chromium"
    ]

    for chrome_path in chrome_paths:
        if os.path.exists(chrome_path):
            options.binary_location = chrome_path
            print(f"🔍 Found Chrome at: {chrome_path}")
            break

    try:
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
        print("✅ ChromeDriver initialized successfully")
    except Exception as e:
        print(f"❌ ChromeDriver initialization failed: {e}")
        try:
            driver = webdriver.Chrome(
                options=options
            )
            print("✅ ChromeDriver initialized with system driver")
        except Exception as e2:
            print(f"❌ System ChromeDriver also failed: {e2}")
            raise e2

    try:
        driver.execute_cdp_cmd(
            'Page.addScriptToEvaluateOnNewDocument',
            {
                'source': '''
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                    window.navigator.chrome = { runtime: {} };
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3]
                    });
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['en-US', 'en']
                    });
                '''
            }
        )
    except Exception as e:
        print(f"⚠️  Could not set anti-detection measures: {e}")

    # Attach proxy info to driver for later marking success/fail
    driver._proxy_applied = proxy_applied
    return driver


def mark_driver_success(driver):
    """Call after a successful operation to mark the proxy as good."""
    proxy = getattr(driver, '_proxy_applied', None)
    if proxy:
        mgr = get_proxy_manager()
        mgr.mark_current_success()


def mark_driver_fail(driver):
    """Call after a block/failure to mark the proxy as bad and rotate."""
    proxy = getattr(driver, '_proxy_applied', None)
    if proxy:
        mgr = get_proxy_manager()
        mgr.mark_current_fail()