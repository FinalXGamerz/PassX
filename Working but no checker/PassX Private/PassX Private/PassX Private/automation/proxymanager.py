# automation/proxymanager.py
"""
Proxy rotation manager for Microsoft account recovery.
Rotates proxies between sessions to avoid rate limits.
"""

import os
import json
import random
import threading
from typing import Optional
from datetime import datetime, timedelta

PROXY_FILE = "proxies.json"
LOCK = threading.Lock()

class Proxy:
    def __init__(self, ip: str, port: int, username: str = "", password: str = ""):
        self.ip = ip
        self.port = port
        self.username = username
        self.password = password
        self.last_used: Optional[datetime] = None
        self.fail_count = 0
        self.max_fails = 3
        self.banned_until: Optional[datetime] = None

    @property
    def is_banned(self) -> bool:
        if self.banned_until and datetime.now() < self.banned_until:
            return True
        return False

    @property
    def is_valid(self) -> bool:
        return self.fail_count < self.max_fails and not self.is_banned

    @property
    def auth_string(self) -> str:
        if self.username and self.password:
            return f"http://{self.username}:{self.password}@{self.ip}:{self.port}"
        return f"http://{self.ip}:{self.port}"

    def mark_fail(self):
        self.fail_count += 1
        self.last_used = datetime.now()
        if self.fail_count >= self.max_fails:
            self.banned_until = datetime.now() + timedelta(minutes=30)
            print(f"🚫 Proxy {self.ip}:{self.port} banned for 30 min")

    def mark_success(self):
        self.fail_count = 0
        self.last_used = datetime.now()
        self.banned_until = None

    def to_dict(self) -> dict:
        return {
            "ip": self.ip,
            "port": self.port,
            "username": self.username,
            "password": self.password,
            "fail_count": self.fail_count,
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "banned_until": self.banned_until.isoformat() if self.banned_until else None,
        }

    @classmethod
    def from_dict(cls, data: dict):
        p = cls(data["ip"], data["port"], data.get("username", ""), data.get("password", ""))
        p.fail_count = data.get("fail_count", 0)
        if data.get("last_used"):
            p.last_used = datetime.fromisoformat(data["last_used"])
        if data.get("banned_until"):
            p.banned_until = datetime.fromisoformat(data["banned_until"])
        return p


class ProxyManager:
    """Rotating proxy manager — thread-safe, persists state to disk."""

    def __init__(self, proxy_file: str = PROXY_FILE):
        self.proxy_file = proxy_file
        self.proxies: list[Proxy] = []
        self.current_index = 0
        self._load()

    # ── File persistence ──────────────────────────
    def _load(self):
        if os.path.exists(self.proxy_file):
            try:
                with open(self.proxy_file) as f:
                    data = json.load(f)
                self.proxies = [Proxy.from_dict(p) for p in data.get("proxies", [])]
                self.current_index = data.get("current_index", 0)
                print(f"📂 Loaded {len(self.proxies)} proxies from {self.proxy_file}")
            except Exception as e:
                print(f"⚠️ Could not load proxy file: {e}")
                self.proxies = []
        else:
            self.proxies = []

    def _save(self):
        with LOCK:
            try:
                data = {
                    "proxies": [p.to_dict() for p in self.proxies],
                    "current_index": self.current_index,
                }
                with open(self.proxy_file, "w") as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                print(f"⚠️ Could not save proxy file: {e}")

    # ── Proxy management ──────────────────────────
    def add_proxy(self, ip: str, port: int, username: str = "", password: str = ""):
        with LOCK:
            # Avoid duplicates
            for p in self.proxies:
                if p.ip == ip and p.port == port:
                    print(f"⚠️ Proxy {ip}:{port} already exists, skipping")
                    return
            self.proxies.append(Proxy(ip, port, username, password))
            self._save()
            print(f"✅ Added proxy {ip}:{port}")

    def add_proxies_from_file(self, filepath: str, auth: tuple[str, str] | None = None):
        """Load proxies from a text file (one per line: ip:port)."""
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    parts = line.split(":")
                    ip = parts[0]
                    port = int(parts[1])
                    username = auth[0] if auth else ""
                    password = auth[1] if auth else ""
                    self.add_proxy(ip, port, username, password)
                except (ValueError, IndexError):
                    print(f"⚠️ Skipping invalid proxy line: {line}")

    def remove_proxy(self, ip: str, port: int):
        with LOCK:
            self.proxies = [p for p in self.proxies if not (p.ip == ip and p.port == port)]
            self._save()

    def get_proxy_count(self) -> dict:
        with LOCK:
            total = len(self.proxies)
            valid = sum(1 for p in self.proxies if p.is_valid)
            banned = total - valid
            return {"total": total, "valid": valid, "banned": banned}

    # ── Rotation ──────────────────────────────────
    def get_next_proxy(self, force_rotate: bool = False) -> Optional[Proxy]:
        """
        Get the next valid proxy (round-robin with skip on dead/banned).
        If force_rotate is True, skip the current and move to next.
        """
        with LOCK:
            if not self.proxies:
                print("⚠️ No proxies available — running without proxy")
                return None

            valid_proxies = [p for p in self.proxies if p.is_valid]
            if not valid_proxies:
                print("⚠️ All proxies are banned — resetting bans")
                for p in self.proxies:
                    p.banned_until = None
                    p.fail_count = 0
                valid_proxies = self.proxies

            # Round-robin: start from current_index + 1 if force rotate
            start = self.current_index + 1 if force_rotate else self.current_index
            start = start % len(self.proxies)

            for offset in range(len(self.proxies)):
                idx = (start + offset) % len(self.proxies)
                proxy = self.proxies[idx]
                if proxy.is_valid:
                    self.current_index = idx
                    print(f"🔄 Using proxy {proxy.ip}:{proxy.port}")
                    return proxy

            # Fallback: first valid one
            for p in self.proxies:
                if p.is_valid:
                    return p

            return None

    def mark_current_success(self):
        """Mark the current proxy as successful."""
        with LOCK:
            if 0 <= self.current_index < len(self.proxies):
                self.proxies[self.current_index].mark_success()
                self._save()

    def mark_current_fail(self):
        """Mark the current proxy as failed."""
        with LOCK:
            if 0 <= self.current_index < len(self.proxies):
                self.proxies[self.current_index].mark_fail()
                self._save()

    def print_status(self):
        """Print proxy pool status."""
        status = self.get_proxy_count()
        print(f"\n📊 Proxy Pool Status:")
        print(f"   Total: {status['total']} | Valid: {status['valid']} | Banned: {status['banned']}")
        for p in self.proxies:
            icon = "✅" if p.is_valid else "🚫"
            suffix = ""
            if p.fail_count > 0:
                suffix = f" (fails: {p.fail_count})"
            print(f"   {icon}  {p.ip}:{p.port}{suffix}")
        print()


# Global singleton
_proxy_manager: Optional[ProxyManager] = None

def get_proxy_manager() -> ProxyManager:
    global _proxy_manager
    if _proxy_manager is None:
        _proxy_manager = ProxyManager()
    return _proxy_manager


def init_proxies(filepath: str = "", auth: tuple = None):
    """Initialize proxy pool from a file. Call once on bot startup."""
    mgr = get_proxy_manager()
    if filepath and os.path.exists(filepath):
        mgr.add_proxies_from_file(filepath, auth)
        print(f"✅ Loaded proxies from {filepath}")
    else:
        print("ℹ️ No proxy file specified. Bot will run without proxies.")