"""
Session Manager
Handles saving and loading user sessions to remember user ID
"""

import json
import os

SESSION_FILE = "user_session.json"

def save_session(user_id: str):
    """Save user ID to session file"""
    try:
        with open(SESSION_FILE, 'w') as f:
            json.dump({"user_id": user_id}, f)
        return True
    except Exception as e:
        print(f"Failed to save session: {e}")
        return False

def load_session():
    """Load user ID from session file"""
    try:
        if os.path.exists(SESSION_FILE):
            with open(SESSION_FILE, 'r') as f:
                data = json.load(f)
                return data.get("user_id")
        return None
    except Exception as e:
        print(f"Failed to load session: {e}")
        return None

def clear_session():
    """Delete session file (logout)"""
    try:
        if os.path.exists(SESSION_FILE):
            os.remove(SESSION_FILE)
        return True
    except Exception as e:
        print(f"Failed to clear session: {e}")
        return False

def has_saved_session():
    """Check if a session file exists"""
    return os.path.exists(SESSION_FILE)
