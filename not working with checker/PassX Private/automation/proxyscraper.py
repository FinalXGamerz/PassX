# automation/proxyscraper.py
"""
Automatic proxy scraper + validator.
Scrapes fresh proxies from public lists every 2 hours,
validates them against Microsoft's login page,
and feeds them into the proxy manager.

Per-proxy IPs / connection errors are NOT printed.
"""

import requests
import re
import time
import threading
import concurrent.futures
from datetime import datetime, timedelta
from typing import Optional
from bs4 import BeautifulSoup

from automation.proxymanager import get_proxy_manager, Proxy

PROXY_SOURCES = [
    {"url": "https://www.sslproxies.org/", "parser": "sslproxies"},
    {"url": "https://free-proxy-list.net/", "parser": "sslproxies"},
    {"url": "https://www.us-proxy.org/", "parser": "sslproxies"},
    {"url": "https://www.proxy-list.download/api/v1/get?type=http", "parser": "raw"},
    {"url": "https://www.proxy-list.download/api/v1/get?type=https", "parser": "raw"},
    {"url": "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt", "parser": "raw"},
    {"url": "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt", "parser": "raw"},
    {"url": "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt", "parser": "raw"},
    {"url": "https://proxyspace.pro/http.txt", "parser": "raw"},
]

TEST_URL = "https://login.live.com"
TEST_TIMEOUT = 15
MAX_PROXIES = 100
VALIDATION_THREADS = 30


def _parse_table_proxies(html: str) -> list[tuple[str, int]]:
    proxies = []
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", {"id": "proxylisttable"})
    if not table:
        table = soup.find("table")
    if table:
        rows = table.find("tbody").find_all("tr") if table.find("tbody") else table.find_all("tr")[1:]
        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 2:
                ip = cols[0].text.strip()
                port_text = cols[1].text.strip()
                if ip and port_text.isdigit():
                    proxies.append((ip, int(port_text)))
    return proxies


def _parse_raw_proxies(text: str) -> list[tuple[str, int]]:
    proxies = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d+)$", line)
        if match:
            proxies.append((match.group(1), int(match.group(2))))
    return proxies


def scrape_proxies() -> list[tuple[str, int]]:
    all_proxies = set()
    for source in PROXY_SOURCES:
        try:
            resp = requests.get(
                source["url"],
                timeout=20,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            )
            resp.raise_for_status()
            if source["parser"] == "sslproxies":
                found = _parse_table_proxies(resp.text)
            else:
                found = _parse_raw_proxies(resp.text)
            for ip, port in found:
                all_proxies.add((ip, port))
        except Exception:
            pass
    proxy_list = list(all_proxies)
    print(f"📦 Scraped {len(proxy_list)} unique proxies")
    return proxy_list


def validate_single_proxy(ip: str, port: int, timeout: int = TEST_TIMEOUT) -> Optional[tuple[str, int]]:
    proxy_url = f"http://{ip}:{port}"
    proxies = {"http": proxy_url, "https": proxy_url}
    try:
        start = time.time()
        resp = requests.get(
            TEST_URL,
            proxies=proxies,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        elapsed = time.time() - start
        if resp.status_code == 200 and elapsed < timeout:
            return (ip, port)
        return None
    except Exception:
        return None


def validate_proxies(proxy_list: list[tuple[str, int]]) -> list[tuple[str, int]]:
    valid = []
    total = len(proxy_list)
    done = 0
    print(f"🔍 Validating {total} proxies (IPs hidden)...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=VALIDATION_THREADS) as executor:
        futures = {
            executor.submit(validate_single_proxy, ip, port): (ip, port)
            for ip, port in proxy_list
        }
        for future in concurrent.futures.as_completed(futures):
            done += 1
            result = future.result()
            if result:
                valid.append(result)
            if done % 50 == 0 or done == total:
                print(f"   checked {done}/{total}  live {len(valid)}")
    print(f"✅ Live proxies: {len(valid)} / {total}")
    return valid


def refresh_proxy_pool():
    print("\n" + "=" * 60)
    print("🔄 PROXY POOL REFRESH")
    print("=" * 60)

    raw = scrape_proxies()
    if not raw:
        print("⚠️ No proxies scraped — keeping existing pool")
        return

    valid = validate_proxies(raw)
    if not valid:
        print("⚠️ No live proxies — keeping existing pool")
        return

    import random
    random.shuffle(valid)
    valid = valid[:MAX_PROXIES]

    mgr = get_proxy_manager()
    mgr.proxies.clear()
    for ip, port in valid:
        mgr.proxies.append(Proxy(ip, port))
    mgr.current_index = 0
    mgr._save()

    print(f"✅ Pool ready: {len(valid)} working proxies")
    print("⏰ Next refresh in 2 hours")
    print("=" * 60 + "\n")


_refresh_thread: Optional[threading.Thread] = None
_refresh_running = False


def _refresh_loop():
    global _refresh_running
    _refresh_running = True
    try:
        refresh_proxy_pool()
    except Exception as e:
        print(f"⚠️ Initial proxy refresh failed: {e}")
    while _refresh_running:
        time.sleep(2 * 60 * 60)
        if not _refresh_running:
            break
        try:
            refresh_proxy_pool()
        except Exception as e:
            print(f"⚠️ Proxy refresh cycle failed: {e}")


def start_proxy_refresher(daemon: bool = True):
    global _refresh_thread
    if _refresh_thread and _refresh_thread.is_alive():
        return
    _refresh_thread = threading.Thread(target=_refresh_loop, daemon=daemon)
    _refresh_thread.start()
    print("🔄 Auto-proxy refresher started (every 2 hours)")


def stop_proxy_refresher():
    global _refresh_running, _refresh_thread
    _refresh_running = False
    if _refresh_thread:
        _refresh_thread.join(timeout=5)


def force_refresh():
    refresh_proxy_pool()