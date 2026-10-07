import json
import os

CONFIG_PATH = "config/config.json"

if not os.path.exists(CONFIG_PATH):
    raise FileNotFoundError("config/config.json not found")

with open(CONFIG_PATH, "r") as f:
    CONFIG = json.load(f)
