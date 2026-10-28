"""Capture Microsoft HIP from the live Chrome tab (cookies + canvas + iframe)."""
from io import BytesIO
import time

from selenium.webdriver.common.by import By
from PIL import Image

SELECTORS = [
    (By.XPATH, '//img[contains(@src, "GetHIPData")]'),
    (By.XPATH, '//img[contains(@src, "hip")]'),
    (By.XPATH, '//img[contains(@src, "HIP")]'),
    (By.XPATH, '//img[contains(@id, "hip") or contains(@id, "HIP")]'),
    (By.CSS_SELECTOR, 'img[id*="hip" i]'),
    (By.CSS_SELECTOR, 'img[id*="HIP" i]'),
    (By.CSS_SELECTOR, 'img[alt*="captcha" i]'),
    (By.CSS_SELECTOR, 'img[alt*="character" i]'),
    (By.CSS_SELECTOR, '#hipCaptcha img, #captchaImage, img.captcha'),
    (By.CSS_SELECTOR, 'img[src*="captcha" i]'),
    (By.CSS_SELECTOR, 'canvas'),
]


def _to_png_buf(img_or_bytes):
    if isinstance(img_or_bytes, BytesIO):
        img_or_bytes.seek(0)
        img = Image.open(img_or_bytes)
    elif isinstance(img_or_bytes, Image.Image):
        img = img_or_bytes
    else:
        img = Image.open(BytesIO(img_or_bytes))
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA")
    w, h = img.size
    if w < 40 or h < 20:
        return None
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def _dpr(driver):
    try:
        v = driver.execute_script("return window.devicePixelRatio || 1")
        return float(v or 1)
    except Exception:
        return 1.0


def _crop_el(driver, el):
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        time.sleep(0.15)
    except Exception:
        pass
    try:
        png = el.screenshot_as_png
        buf = _to_png_buf(png)
        if buf:
            return buf
    except Exception:
        pass
    try:
        loc = el.location_once_scrolled_into_view or el.location
        size = el.size or {}
        png = driver.get_screenshot_as_png()
        img = Image.open(BytesIO(png))
        dpr = _dpr(driver)
        l = int(loc.get("x", 0) * dpr)
        t = int(loc.get("y", 0) * dpr)
        r = int((loc.get("x", 0) + size.get("width", 0)) * dpr)
        b = int((loc.get("y", 0) + size.get("height", 0)) * dpr)
        l, t = max(0, l), max(0, t)
        r, b = min(img.width, r), min(img.height, b)
        if r - l < 40 or b - t < 20:
            return None
        return _to_png_buf(img.crop((l, t, r, b)))
    except Exception:
        return None


def _search(driver):
    for by, sel in SELECTORS:
        try:
            els = driver.find_elements(by, sel)
        except Exception:
            continue
        for el in els:
            try:
                if not el.is_displayed():
                    continue
                size = el.size or {}
                if (size.get("width") or 0) < 20 or (size.get("height") or 0) < 20:
                    continue
                buf = _crop_el(driver, el)
                if buf:
                    print(f"🧩 CAPTCHA captured via {sel}")
                    return buf
            except Exception:
                continue
    return None


def _walk(driver):
    buf = _search(driver)
    if buf:
        return buf
    try:
        frames = driver.find_elements(By.TAG_NAME, "iframe")
    except Exception:
        frames = []
    for i, frame in enumerate(frames):
        try:
            driver.switch_to.frame(frame)
            buf = _search(driver)
            if buf:
                print(f"🧩 CAPTCHA captured inside iframe {i}")
                driver.switch_to.default_content()
                return buf
            nested = _walk(driver)
            driver.switch_to.default_content()
            if nested:
                return nested
        except Exception:
            try:
                driver.switch_to.default_content()
            except Exception:
                pass
    return None


def download_captcha(driver) -> BytesIO:
    last = None
    for _ in range(8):
        try:
            buf = _walk(driver)
            if buf:
                return buf
        except Exception as e:
            last = e
        time.sleep(0.4)
    try:
        png = driver.get_screenshot_as_png()
        buf = _to_png_buf(png)
        print("🧩 CAPTCHA fallback: full page screenshot")
        return buf
    except Exception as e:
        print(f"❌ Failed to download CAPTCHA: {last or e}")
        empty = BytesIO()
        Image.new("RGB", (420, 120), (30, 30, 30)).save(empty, format="PNG")
        empty.seek(0)
        return empty