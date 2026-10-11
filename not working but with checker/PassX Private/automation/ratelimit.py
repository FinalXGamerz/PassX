"""
Global Microsoft rate-limit brake.
Spamming login.live.com / ACSR after a 429 is what gets the IP cooked.
"""
import random
import threading
import time

_lock = threading.Lock()
_cooldown_until = 0.0
_last_start = 0.0
_hits = 0

MIN_GAP_S = 12.0          # min seconds between account starts
BASE_COOLDOWN_S = 75.0    # first 429
MAX_COOLDOWN_S = 240.0


def remaining():
    with _lock:
        return max(0.0, _cooldown_until - time.time())


def hits():
    with _lock:
        return _hits


def wait_turn(label="login"):
    """Block until it's safe to hit Microsoft again."""
    global _last_start
    with _lock:
        now = time.time()
        cool = max(0.0, _cooldown_until - now)
        gap = max(0.0, MIN_GAP_S - (now - _last_start))
        extra = cool + gap + random.uniform(0.6, 2.2)
    if extra > 0.3:
        print(f"⏳ [{label}] spacing {extra:.1f}s (cooldown {cool:.0f}s)")
        time.sleep(extra)
    with _lock:
        _last_start = time.time()


def trip(seconds=None):
    """Call on Too Many Requests / unusual activity. Exponential, capped."""
    global _cooldown_until, _hits
    with _lock:
        _hits += 1
        base = seconds if seconds is not None else min(
            MAX_COOLDOWN_S, BASE_COOLDOWN_S * (1.55 ** min(_hits - 1, 4))
        )
        wait = base + random.uniform(8, 28)
        _cooldown_until = max(_cooldown_until, time.time() + wait)
        left = _cooldown_until - time.time()
        print(f"🚫 Global MS cooldown {left:.0f}s (hit #{_hits})")
        return left


def clear():
    global _cooldown_until, _hits
    with _lock:
        _cooldown_until = 0.0
        _hits = 0