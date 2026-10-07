import requests
import random
import string
import time
import re

BASE_URL = "https://api.mail.tm"

def random_name(length=10):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def get_domains():
    r = requests.get(f"{BASE_URL}/domains")
    return r.json()['hydra:member'][0]['domain']

def register_account(email, password):
    payload = {"address": email, "password": password}
    r = requests.post(f"{BASE_URL}/accounts", json=payload)
    return r.status_code in [201, 422]

def get_token(email, password):
    payload = {"address": email, "password": password}
    r = requests.post(f"{BASE_URL}/token", json=payload)
    return r.json()['token']

def get_messages(token):
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{BASE_URL}/messages", headers=headers)
    return r.json().get('hydra:member', [])

def read_message(token, message_id):
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{BASE_URL}/messages/{message_id}", headers=headers)
    return r.json()

def generate_temp_mail_account():
    username = random_name()
    password = random_name(12)
    domain = get_domains()
    email = f"{username}@{domain}"
    register_account(email, password)
    token = get_token(email, password)
    return email, password, token

def wait_for_emails(token, expected_count=2, timeout=90, interval=5):
    attempts = timeout // interval
    for _ in range(attempts):
        inbox = get_messages(token)
        if len(inbox) >= expected_count:
            return inbox[:expected_count]
        time.sleep(interval)
    return get_messages(token)

def extract_otp(text):
    match = re.search(r'\b\d{6}\b', text)
    return match.group(0) if match else None

def get_otp_from_first_email(token):
    emails = wait_for_emails(token, expected_count=1)

    if not emails:
        print("❌ No email received.")
        return None

    msg = read_message(token, emails[0]['id'])
    otp = extract_otp(msg['text'])

    if otp:
        print("🔐 Extracted OTP:", otp)
    else:
        print("❌ OTP not found in email.")

    return otp

def print_second_email(token, emails):
    if len(emails) < 2:
        print("❌ Less than 2 emails available.")
        return

    msg = read_message(token, emails[1]['id'])
    print("\n📧 Full Email Content (2nd Email):\n")
    print(msg['text'])

def extract_specific_link(text: str) -> str | None:
    """Extract the Microsoft password reset link from email text."""
    if not text:
        return None

    # ── Exact Microsoft password reset URL patterns ──
    ms_reset_patterns = [
        r'https://account\.live\.com/password/reset[^\s)\">]*',
        r'https://account\.live\.com/ResetPassword[^\s)\">]*',
        r'https://account\.live\.com/resetpassword[^\s)\">]*',
        r'https://accountservices\.msn\.com[^\s)\">]*',
        r'https://account\.live\.com/Reset/[^\s)\">]*',
    ]
    
    for pattern in ms_reset_patterns:
        match = re.search(pattern, text)
        if match:
            url = match.group(0).rstrip('.)">')
            print(f"🔗 Extracted reset link: {url[:60]}...")
            return url

    # ── Method 2: Lines after trigger phrases ──
    lines = text.splitlines()
    for i, line in enumerate(lines):
        line_lower = line.strip().lower()
        if any(p in line_lower for p in [
            "click the link below",
            "reset your password",
            "to reset your password",
        ]):
            for j in range(i + 1, min(i + 4, len(lines))):
                next_line = lines[j].strip()
                for pattern in ms_reset_patterns:
                    match = re.search(pattern, next_line)
                    if match:
                        return match.group(0).rstrip('.)">')

    print("❌ No Microsoft reset link found in email")
    return None