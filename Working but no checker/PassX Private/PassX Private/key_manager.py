"""
PassX — Key License System
Handles generation, storage, redemption and expiry of timed access keys.
Keys are stored in keys.json alongside authorized_users.json
"""

import json
import os
import random
import string
from datetime import datetime, timedelta

KEYS_FILE = "keys.json"

# Key durations in hours
KEY_DURATIONS = {
    "1day":    24,
    "7day":    168,
    "30day":   720,
    "lifetime": None,   # None = never expires
}

KEY_LABELS = {
    "1day":    "1 Day",
    "7day":    "7 Days",
    "30day":   "30 Days",
    "lifetime": "Lifetime",
}


def _load_keys():
    if os.path.exists(KEYS_FILE):
        try:
            with open(KEYS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_keys(data):
    with open(KEYS_FILE, "w") as f:
        json.dump(data, f, indent=2)
    _git_commit(KEYS_FILE)


def _git_commit(filename):
    """Push changed file back to repo so data survives GitHub Actions restarts."""
    import subprocess
    try:
        is_git = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True
        ).returncode == 0
        if not is_git:
            return

        subprocess.run(["git", "add", filename], check=True, capture_output=True)

        diff = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            capture_output=True
        )
        if diff.returncode == 0:
            return  # Nothing changed

        subprocess.run([
            "git", "commit", "-m",
            f"chore: auto-save {filename} [skip ci]"
        ], check=True, capture_output=True)

        subprocess.run(["git", "push"], check=True, capture_output=True)
        print(f"✅ Auto-saved {filename} to repo")
    except Exception as e:
        print(f"⚠️ Git auto-save failed for {filename}: {e}")


def generate_key(plan):
    """Generate a new key for the given plan. Returns the key string or None if plan invalid."""
    if plan not in KEY_DURATIONS:
        return None

    # Format: PASSX-XXXX-XXXX-XXXX  (uppercase alphanumeric)
    chars = string.ascii_uppercase + string.digits
    segments = ["".join(random.choices(chars, k=4)) for _ in range(3)]
    key = "PASSX-" + "-".join(segments)

    keys = _load_keys()
    keys[key] = {
        "plan":       plan,
        "created_at": str(datetime.now()),
        "redeemed":   False,
        "redeemed_by": None,
        "redeemed_at": None,
        "expires_at":  None,    # set on redemption
    }
    _save_keys(keys)
    return key


def redeem_key(key, user_id):
    """
    Attempt to redeem a key for user_id.
    Returns (success, message).
    """
    keys = _load_keys()
    key = key.strip().upper()

    if key not in keys:
        return False, "Invalid key. Check and try again."

    entry = keys[key]

    if entry["redeemed"]:
        # Already redeemed — was it by this same user?
        if str(entry["redeemed_by"]) == str(user_id):
            # Check if still valid
            if entry["expires_at"] is None:
                return False, "You already redeemed this key (Lifetime — still active)."
            exp = datetime.fromisoformat(entry["expires_at"])
            if datetime.now() < exp:
                remaining = exp - datetime.now()
                days = remaining.days
                hours = remaining.seconds // 3600
                return False, f"You already redeemed this key ({days}d {hours}h remaining)."
        return False, "This key has already been used by another user."

    # Mark as redeemed
    plan     = entry["plan"]
    hours    = KEY_DURATIONS[plan]
    exp_str  = None
    if hours is not None:
        expires_at = datetime.now() + timedelta(hours=hours)
        exp_str    = str(expires_at)

    keys[key]["redeemed"]    = True
    keys[key]["redeemed_by"] = str(user_id)
    keys[key]["redeemed_at"] = str(datetime.now())
    keys[key]["expires_at"]  = exp_str
    _save_keys(keys)

    return True, plan


def get_user_license(user_id):
    """
    Find the active license for a user (most recently redeemed non-expired key).
    Returns dict with plan/expires_at/label, or None if no valid license.
    """
    keys  = _load_keys()
    uid   = str(user_id)
    best  = None

    for key, entry in keys.items():
        if not entry["redeemed"] or entry["redeemed_by"] != uid:
            continue

        plan = entry["plan"]

        # Lifetime — always valid
        if KEY_DURATIONS[plan] is None:
            return {
                "key":        key,
                "plan":       plan,
                "label":      KEY_LABELS[plan],
                "expires_at": None,
                "active":     True,
            }

        exp = datetime.fromisoformat(entry["expires_at"])
        if datetime.now() >= exp:
            continue   # expired

        # Pick the one that expires latest
        if best is None or exp > datetime.fromisoformat(best["expires_at"]):
            best = {
                "key":        key,
                "plan":       plan,
                "label":      KEY_LABELS[plan],
                "expires_at": entry["expires_at"],
                "active":     True,
            }

    return best


def has_valid_license(user_id):
    return get_user_license(user_id) is not None


def revoke_user_keys(user_id):
    """Expire all keys belonging to a user (used when admin revokes access)."""
    keys = _load_keys()
    uid  = str(user_id)
    for key, entry in keys.items():
        if entry["redeemed_by"] == uid:
            keys[key]["expires_at"] = str(datetime.now())  # expire immediately
    _save_keys(keys)


def list_all_keys():
    """Return all keys with their status, for admin /listkeys command."""
    keys   = _load_keys()
    result = []
    for key, entry in keys.items():
        status = "unused"
        if entry["redeemed"]:
            if entry["expires_at"] is None:
                status = "active_lifetime"
            elif datetime.now() < datetime.fromisoformat(entry["expires_at"]):
                status = "active"
            else:
                status = "expired"
        result.append({
            "key":         key,
            "plan":        entry["plan"],
            "label":       KEY_LABELS[entry["plan"]],
            "status":      status,
            "redeemed_by": entry["redeemed_by"],
            "expires_at":  entry["expires_at"],
        })
    return result