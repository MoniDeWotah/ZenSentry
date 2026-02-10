import os
import json
from typing import Dict, Any

# --- SYSTEM PATHS ---
APP_NAME = "ZenSentry"
DB_NAME = "zen_sentry.db"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, DB_NAME)
CONFIG_PATH = os.path.join(BASE_DIR, "zen_config.json")

# --- ICON COLORS ---
ICON_COLOR_ACTIVE = (0, 255, 127)   
ICON_COLOR_RESEARCH = (0, 191, 255) 
ICON_COLOR_PAUSED = (128, 128, 128) 
ICON_COLOR_WARN   = (255, 165, 0)   
ICON_COLOR_ALERT  = (255, 0, 0)     
ICON_COLOR_SUCCESS = (0, 255, 255) # Cyan

# --- LOAD JSON CONFIG ---
def load_config():
    try:
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print("[ERROR] zen_config.json not found! Using defaults.")
        return {} # Should handle defaults ideally, but for now assuming file exists

data: Dict[str, Any] = load_config()

# --- EXPORT CONFIGS ---
WHITELIST_APPS = data.get("WHITELIST_APPS", [])
BLACKLIST_APPS = data.get("BLACKLIST_APPS", [])
SESSION_KEYWORDS = data.get("SESSION_KEYWORDS", [])
SYSTEM_TITLES = data.get("SYSTEM_TITLES", [])

TIMING: Dict[str, Any] = data.get("TIMING", {})
HEARTBEAT_INTERVAL = TIMING.get("HEARTBEAT_INTERVAL", 2)
GRACE_PERIOD = TIMING.get("GRACE_PERIOD", 15)
IDLE_TIMEOUT = TIMING.get("IDLE_TIMEOUT", 300)
TRUST_DURATION = TIMING.get("TRUST_DURATION_MINS", 30) * 60

ECONOMY: Dict[str, Any] = data.get("ECONOMY", {})
POINTS = {
    "BASE_INCOME": ECONOMY.get("BASE_INCOME", 10),
    "SWITCH_TAX": ECONOMY.get("SWITCH_TAX", -5),
    "PENALTY": ECONOMY.get("PENALTY", -20),
    "BETRAYAL": ECONOMY.get("TRUST_BETRAYAL_PENALTY", -50),
    "RAPID_SWITCH": -10
}

RAPID_SWITCH_LIMIT = 10 # Seconds

MULTIPLIERS = { "TIER_1": 1.0, "TIER_2": 1.25, "TIER_3": 1.5 }