import requests, uuid, hashlib, sys
from utils.config_loader import CONFIG

SERVER = "https://vaultx-license-server-production-c265.up.railway.app/verify"

def device():
    return hashlib.sha256(str(uuid.getnode()).encode()).hexdigest()

def verify():
    key = CONFIG.get("license_key")

    if not key:
        print("❌ No license key")
        sys.exit(1)

    try:
        r = requests.get(
            SERVER,
            params={"key": key, "device": device()},
            timeout=10
        )

        if r.status_code != 200:
            print("❌ Server error")
            sys.exit(1)

        data = r.json()

        print("DEBUG:", data)  # 👈 keep this for now

        if data.get("valid") is not True:
            print("❌ Invalid License")
            sys.exit(1)

        print("✅ License OK")

    except Exception as e:
        print("❌ License check failed:", e)
        sys.exit(1)


# 🔥 VERY IMPORTANT — FORCE RUN
verify()
