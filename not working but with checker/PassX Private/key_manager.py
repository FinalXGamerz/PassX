"""
PassX — Key License System (v3)
Handles generation, storage, redemption and expiry of timed access keys.
Keys are stored in keys.json alongside authorized_users.json

Products:
- "passchanger" — PassX password changer access
- "checker" — Minecraft checker access
- "both" — Access to both products

Features:
- Custom durations: days, hours, minutes, seconds, or lifetime
- Key validity: how long a key stays redeemable before it expires unused
- Timer starts when the user redeems, NOT when the key is generated
- Authorize grants lifetime access for a specific product
"""

import json
import os
import random
import string
from datetime import datetime, timedelta

KEYS_FILE = "keys.json"

# Valid products
PRODUCTS = ["passchanger", "checker", "both"]


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


def _format_duration(seconds):
    """Format seconds into a human-readable string."""
    if seconds is None:
        return "Lifetime"
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 and days == 0:
        parts.append(f"{secs}s")
    return " ".join(parts) if parts else "0s"


def _parse_duration_to_seconds(days=0, hours=0, minutes=0, seconds=0):
    """Convert duration components to total seconds."""
    total = (days * 86400) + (hours * 3600) + (minutes * 60) + seconds
    return total if total > 0 else None


def generate_key(duration_seconds=None, key_valid_hours=None, product="both"):
    """
    Generate a new key.
    
    Args:
        duration_seconds: How long the license lasts after redemption (None = lifetime)
        key_valid_hours: How long the key stays redeemable (None = forever)
        product: "passchanger", "checker", or "both"
    
    Returns the key string.
    """
    if product not in PRODUCTS:
        product = "both"

    # Format: PASSX-XXXX-XXXX-XXXX  (uppercase alphanumeric)
    chars = string.ascii_uppercase + string.digits
    segments = ["".join(random.choices(chars, k=4)) for _ in range(3)]
    key = "PASSX-" + "-".join(segments)

    # Key validity (when does the unredeemed key expire)
    key_expires_at = None
    if key_valid_hours is not None and key_valid_hours > 0:
        key_expires_at = str(datetime.now() + timedelta(hours=key_valid_hours))

    keys = _load_keys()
    keys[key] = {
        "product": product,
        "duration_seconds": duration_seconds,  # None = lifetime
        "duration_label": _format_duration(duration_seconds),
        "created_at": str(datetime.now()),
        "key_expires_at": key_expires_at,
        "redeemed": False,
        "redeemed_by": None,
        "redeemed_at": None,
        "license_expires_at": None,
    }
    _save_keys(keys)
    return key


def redeem_key(key, user_id):
    """
    Attempt to redeem a key for user_id.
    Timer starts NOW — duration counts from redemption time.
    Returns (success, result_dict_or_error_string).
    """
    keys = _load_keys()
    key = key.strip().upper()

    if key not in keys:
        return False, "Invalid key. Check and try again."

    entry = keys[key]

    # Check if key itself has expired (unredeemed key validity)
    if not entry["redeemed"] and entry.get("key_expires_at"):
        key_exp = datetime.fromisoformat(entry["key_expires_at"])
        if datetime.now() >= key_exp:
            return False, "This key has expired and can no longer be redeemed."

    if entry["redeemed"]:
        if str(entry["redeemed_by"]) == str(user_id):
            if entry["license_expires_at"] is None:
                return False, "You already redeemed this key (Lifetime — still active)."
            exp = datetime.fromisoformat(entry["license_expires_at"])
            if datetime.now() < exp:
                remaining = exp - datetime.now()
                return False, f"You already redeemed this key ({_format_duration(int(remaining.total_seconds()))} remaining)."
            else:
                return False, "You already redeemed this key (expired)."
        return False, "This key has already been used by another user."

    # Mark as redeemed — timer starts NOW
    duration_seconds = entry["duration_seconds"]
    license_expires_at = None
    if duration_seconds is not None:
        license_expires_at = str(datetime.now() + timedelta(seconds=duration_seconds))

    keys[key]["redeemed"] = True
    keys[key]["redeemed_by"] = str(user_id)
    keys[key]["redeemed_at"] = str(datetime.now())
    keys[key]["license_expires_at"] = license_expires_at
    _save_keys(keys)

    return True, {
        "product": entry.get("product", "both"),
        "duration_seconds": duration_seconds,
        "duration_label": entry["duration_label"],
        "license_expires_at": license_expires_at,
    }


def get_user_license(user_id, product=None):
    """
    Find the active license for a user.
    If product is specified, only look for keys matching that product (or "both").
    Returns dict with info, or None if no valid license.
    """
    keys = _load_keys()
    uid = str(user_id)
    best = None

    for key, entry in keys.items():
        if not entry["redeemed"] or entry["redeemed_by"] != uid:
            continue

        # Product filter
        key_product = entry.get("product", "both")
        if product and product != "both":
            if key_product != product and key_product != "both":
                continue

        # Lifetime — always valid
        if entry["duration_seconds"] is None:
            return {
                "key": key,
                "product": key_product,
                "duration_label": "Lifetime",
                "license_expires_at": None,
                "active": True,
            }

        if not entry.get("license_expires_at"):
            continue

        exp = datetime.fromisoformat(entry["license_expires_at"])
        if datetime.now() >= exp:
            continue  # expired

        if best is None or exp > datetime.fromisoformat(best["license_expires_at"]):
            best = {
                "key": key,
                "product": key_product,
                "duration_label": entry.get("duration_label", "Unknown"),
                "license_expires_at": entry["license_expires_at"],
                "active": True,
            }

    return best


def has_valid_license(user_id, product=None):
    """Check if user has a valid license. If product specified, checks for that product."""
    return get_user_license(user_id, product) is not None


def grant_lifetime(user_id, granted_by, product="both"):
    """
    Grant lifetime access directly (used by /authorize).
    Creates an auto-redeemed lifetime key internally.
    """
    if product not in PRODUCTS:
        product = "both"

    chars = string.ascii_uppercase + string.digits
    segments = ["".join(random.choices(chars, k=4)) for _ in range(3)]
    key = "PASSX-" + "-".join(segments)

    keys = _load_keys()
    keys[key] = {
        "product": product,
        "duration_seconds": None,
        "duration_label": "Lifetime",
        "created_at": str(datetime.now()),
        "key_expires_at": None,
        "redeemed": True,
        "redeemed_by": str(user_id),
        "redeemed_at": str(datetime.now()),
        "license_expires_at": None,
        "_granted_by": str(granted_by),
        "_grant_type": "authorize",
    }
    _save_keys(keys)
    return key


def revoke_user_keys(user_id, product=None):
    """
    Expire all keys belonging to a user.
    If product specified, only revoke keys for that product.
    """
    keys = _load_keys()
    uid = str(user_id)
    for key, entry in keys.items():
        if entry["redeemed_by"] != uid:
            continue
        # Product filter
        if product and product != "both":
            key_product = entry.get("product", "both")
            if key_product != product and key_product != "both":
                continue
        if entry["duration_seconds"] is not None:
            keys[key]["license_expires_at"] = str(datetime.now())
        else:
            keys[key]["license_expires_at"] = str(datetime.now() - timedelta(seconds=1))
            keys[key]["duration_seconds"] = 1
    _save_keys(keys)


def list_all_keys(product=None):
    """Return all keys with their status. Filter by product if specified."""
    keys = _load_keys()
    result = []
    for key, entry in keys.items():
        key_product = entry.get("product", "both")
        if product and product != "both":
            if key_product != product and key_product != "both":
                continue

        status = "unused"
        if entry["redeemed"]:
            if entry.get("license_expires_at") is None and entry.get("duration_seconds") is None:
                status = "active_lifetime"
            elif entry.get("license_expires_at") and datetime.now() < datetime.fromisoformat(entry["license_expires_at"]):
                status = "active"
            else:
                status = "expired"
        else:
            if entry.get("key_expires_at") and datetime.now() >= datetime.fromisoformat(entry["key_expires_at"]):
                status = "key_expired"
            else:
                status = "unused"

        result.append({
            "key": key,
            "product": key_product,
            "duration_label": entry.get("duration_label", "Unknown"),
            "status": status,
            "redeemed_by": entry["redeemed_by"],
            "license_expires_at": entry.get("license_expires_at"),
            "key_expires_at": entry.get("key_expires_at"),
            "created_at": entry.get("created_at"),
        })
    return result
