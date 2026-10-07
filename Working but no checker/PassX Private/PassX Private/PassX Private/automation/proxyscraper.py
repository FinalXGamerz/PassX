# automation/proxyscraper.py
"""
Automatic proxy scraper + validator.
Scrapes fresh proxies from public lists every 2 hours,
validates them against Microsoft's login page,
and feeds them into the proxy manager.
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

# ── Proxy sources (free public proxy lists) ──
PROXY_SOURCES = [
    {
        "url": "https://www.sslproxies.org/",
        "parser": "sslproxies",
    },
    {
        "url": "https://free-proxy-list.net/",
        "parser": "sslproxies",  # same HTML structure
    },
    {
        "url": "https://www.us-proxy.org/",
        "parser": "sslproxies",
    },
    {
        "url": "https://www.proxy-list.download/api/v1/get?type=http",
        "parser": "raw",  # returns raw text IP:PORT lines
    },
    {
        "url": "https://www.proxy-list.download/api/v1/get?type=https",
        "parser": "raw",
    },
    {
        "url": "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
        "parser": "raw",
    },
    {
        "url": "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
        "parser": "raw",
    },
    {
        "url": "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt",
        "parser": "raw",
    },
    {
        "url": "https://proxyspace.pro/http.txt",
        "parser": "raw",
    },
]

# ── Validation config ──
TEST_URL = "https://login.live.com"
TEST_TIMEOUT = 15  # seconds per proxy
MAX_PROXIES = 100  # max to keep in pool
VALIDATION_THREADS = 30  # concurrent validation workers


def _parse_table_proxies(html: str) -> list[tuple[str, int]]:
    """Parse proxies from an HTML table (sslproxies.org style)."""
    proxies = []
    soup = BeautifulSoup(html, 'html.parser')
    table = soup.find('table', {'id': 'proxylisttable'})
    if not table:
        # Try any table with IP/port columns
        table = soup.find('table')
    if table:
        for row in table.find('tbody').find_all('tr') if table.find('tbody') else table.find_all('tr')[1:]:
            cols = row.find_all('td')
            if len(cols) >= 2:
                ip = cols[0].text.strip()
                port_text = cols[1].text.strip()
                if ip and port_text.isdigit():
                    proxies.append((ip, int(port_text)))
    return proxies


def _parse_raw_proxies(text: str) -> list[tuple[str, int]]:
    """Parse proxies from raw IP:PORT lines."""
    proxies = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        match = re.match(r'^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d+)$', line)
        if match:
            proxies.append((match.group(1), int(match.group(2))))
    return proxies


def scrape_proxies() -> list[tuple[str, int]]:
    """Scrape proxies from all sources and deduplicate."""
    all_proxies = set()

    for source in PROXY_SOURCES:
        try:
            print(f"🌐 Scraping proxies from: {source['url']}")
            resp = requests.get(source['url'], timeout=20, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            resp.raise_for_status()

            if source['parser'] == 'sslproxies':
                found = _parse_table_proxies(resp.text)
            else:
                found = _parse_raw_proxies(resp.text)

            for ip, port in found:
                all_proxies.add((ip, port))

            print(f"   ➕ Found {len(found)} proxies from this source")
        except Exception as e:
            print(f"   ⚠️ Failed to scrape {source['url']}: {e}")

    proxy_list = list(all_proxies)
    print(f"\n📦 Total unique proxies scraped: {len(proxy_list)}")
    return proxy_list


def validate_single_proxy(ip: str, port: int, timeout: int = TEST_TIMEOUT) -> Optional[tuple[str, int]]:
    """Test if a proxy connects to Microsoft's login page."""
    proxy_url = f"http://{ip}:{port}"
    proxies = {
        "http": proxy_url,
        "https": proxy_url,
    }
    try:
        start = time.time()
        resp = requests.get(
            TEST_URL,
            proxies=proxies,
            timeout=timeout,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
        )
        elapsed = time.time() - start

        if resp.status_code == 200 and elapsed < timeout:
            print(f"   ✅ {ip}:{port} — {elapsed:.1f}s — (HTTP {resp.status_code})")
            return (ip, port)
        else:
            print(f"   ❌ {ip}:{port} — {elapsed:.1f}s — (HTTP {resp.status_code})")
            return None
    except Exception as e:
        print(f"   ❌ {ip}:{port} — {str(e)[:40]}")
        return None


def validate_proxies(proxy_list: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """Validate all scraped proxies concurrently."""
    valid = []
    print(f"\n🔍 Validating {len(proxy_list)} proxies against {TEST_URL}...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=VALIDATION_THREADS) as executor:
        futures = {
            executor.submit(validate_single_proxy, ip, port): (ip, port)
            for ip, port in proxy_list
        }
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                valid.append(result)

    print(f"\n✅ Valid proxies: {len(valid)} / {len(proxy_list)}")
    return valid


def refresh_proxy_pool():
    """
    Full refresh cycle:
    1. Scrape fresh proxies
    2. Validate them
    3. Replace the proxy manager pool
    """
    print("\n" + "="*60)
    print("🔄 PROXY POOL REFRESH CYCLE STARTING")
    print("="*60)

    # Scrape
    raw = scrape_proxies()
    if not raw:
        print("⚠️ No proxies scraped — keeping existing pool")
        return

    # Validate
    valid = validate_proxies(raw)
    if not valid:
        print("⚠️ No valid proxies found — keeping existing pool")
        return

    # Sort by (randomized) and limit
    import random
    random.shuffle(valid)
    valid = valid[:MAX_PROXIES]

    # Replace pool
    mgr = get_proxy_manager()
    mgr.proxies.clear()
    for ip, port in valid:
        mgr.proxies.append(Proxy(ip, port))
    mgr.current_index = 0
    mgr._save()

    print(f"\n✅ Proxy pool refreshed: {len(valid)} working proxies")
    print(f"⏰ Next refresh in 2 hours")
    print("="*60 + "\n")


# ── Background scheduler ──
_refresh_thread: Optional[threading.Thread] = None
_refresh_running = False


def _refresh_loop():
    """Background loop that refreshes proxies every 2 hours."""
    global _refresh_running
    _refresh_running = True

    # Initial refresh on startup
    try:
        refresh_proxy_pool()
    except Exception as e:
        print(f"⚠️ Initial proxy refresh failed: {e}")

    while _refresh_running:
        time.sleep(2 * 60 * 60)  # 2 hours
        if not _refresh_running:
            break
        try:
            refresh_proxy_pool()
        except Exception as e:
            print(f"⚠️ Proxy refresh cycle failed: {e}")


def start_proxy_refresher(daemon: bool = True):
    """Start the background proxy refresh thread."""
    global _refresh_thread
    if _refresh_thread and _refresh_thread.is_alive():
        print("⚠️ Proxy refresher already running")
        return

    _refresh_thread = threading.Thread(target=_refresh_loop, daemon=daemon)
    _refresh_thread.start()
    print("🔄 Auto-proxy refresher started (every 2 hours)")


def stop_proxy_refresher():
    """Stop the background refresh thread."""
    global _refresh_running, _refresh_thread
    _refresh_running = False
    if _refresh_thread:
        _refresh_thread.join(timeout=5)
    print("⏹️ Proxy refresher stopped")


# ── Manual one-shot ──
def force_refresh():
    """Manually trigger an immediate proxy refresh."""
    refresh_proxy_pool()