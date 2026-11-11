import os, sys, json, time, random, string, hashlib, hmac, uuid, re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests, urllib3
from requests.adapters import HTTPAdapter
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from flask import Flask, request, jsonify, make_response

try:
    import blackboxprotobuf
except ImportError:
    os.system("pip install blackboxprotobuf -q")
    import blackboxprotobuf

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================================
# URLS & CONSTANTS
# ============================================================
URL_GUEST_REGISTER = "https://ffmconnect.live.gop.garenanow.com/api/v2/oauth/guest:register"
URL_TOKEN_GRANT    = "https://ffmconnect.live.gop.garenanow.com/api/v2/oauth/guest/token:grant"
URL_MAJOR_LOGIN    = "https://loginbp.ppmainecoonghj.com/MajorLogin"
URL_MAJOR_REGISTER = "https://loginbp.ppmainecoonghj.com/MajorRegister"
URL_NEWBIE_CHOICE  = "https://loginbp.ppmainecoonghj.com/ChooseNewbieChoice"

MAIN_KEY = bytes.fromhex('32656534343831396539623435393838343531343130363762323831363231383734643064356437616639643866376530306331653534373135623764316533')
AES_KEY = bytes([89,103,38,116,99,37,68,69,117,104,54,37,90,99,94,56])
AES_IV  = bytes([54,111,121,90,68,114,50,50,69,51,121,99,104,106,77,37])
CLIENT_SECRET = "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3"
APP_ID        = 100067
RELEASE_VER   = "OB55"
GAME_VERSION  = "2.132.4"

HTTP_TIMEOUT  = (5, 10)
POOL_CONN     = 1000
POOL_MAX      = 1000

# ============================================================
# SERVERS
# ============================================================
SERVERS = {
    "1": {"code":"BD","name":"Bangladesh","ips":["103.4.145.10","103.4.145.22","103.4.146.15"],"isp":"Grameenphone"},
    "2": {"code":"IND","name":"India","ips":["49.36.180.10","49.36.180.22","49.36.181.15"],"isp":"Jio"},
    "3": {"code":"PK","name":"Pakistan","ips":["103.22.180.10","103.22.180.22"],"isp":"Jazz"},
    "4": {"code":"SG","name":"Singapore","ips":["103.6.148.10","103.6.148.22"],"isp":"Singtel"},
    "5": {"code":"ID","name":"Indonesia","ips":["103.10.60.10","103.10.60.22"],"isp":"Telkomsel"},
    "6": {"code":"ME","ips":["5.42.200.10","185.44.100.10"],"name":"Middle East","isp":"Etisalat"},
}

DEVICES = [
    ("Asus ASUS_AI2501_B", "Android OS 12 / API-31 (SP1A.210812.016.C2)", "Adreno (TM) 640", "OpenGL ES 3.2"),
    ("Redmi Note 12 Pro",  "Android OS 13 / API-33 (TP1A.220624.014)", "Adreno (TM) 618", "OpenGL ES 3.2"),
    ("Samsung SM-M135F",   "Android OS 13 / API-33 (TP1A.220624.014)", "Mali-G68", "OpenGL ES 3.2"),
]

# ============================================================
# GLOBAL MEMORY (Multi-User Safe)
# ============================================================
# প্রতিটি রিকোয়েস্টের জন্য আলাদা ডেটা রাখার সিস্টেম
JOBS = {}  # job_id: { "job": {...}, "accounts": [...] }
LOCK = threading.Lock()

# ============================================================
# HELPER FUNCTIONS
# ============================================================
def enc_aes(data): return AES.new(AES_KEY, AES.MODE_CBC, AES_IV).encrypt(pad(data, AES.block_size))

def encode_f14(s):
    ks = [0x30,0x30,0x30,0x32,0x30,0x31,0x37,0x30,0x30,0x30,0x30,0x30,0x32,0x30,0x31,0x37,0x30,0x30,0x30,0x30,0x30,0x32,0x30,0x31,0x37,0x30,0x30,0x30,0x30,0x30,0x32,0x30]
    return bytes(ord(c) ^ ks[i % len(ks)] for i, c in enumerate(s))

def gen_password(): return hashlib.sha256(''.join(random.choice(string.ascii_letters + string.digits) for _ in range(32)).encode()).hexdigest().upper()

def gen_nickname(prefix, max_len=12):
    # ইমোজি বা স্পেস ছাড়া যেকোনো নাম সাপোর্ট করবে
    prefix = str(prefix).strip()
    if not prefix:
        prefix = "DM"
    avail = max_len - len(prefix)
    if avail < 1: return prefix[:max_len].encode()
    return f"{prefix}{''.join(random.choice('0123456789') for _ in range(avail))}".encode()

def _tf(t): return {'type': t, 'name': ''}
typedef_login = {'3':_tf('bytes'),'4':_tf('bytes'),'5':_tf('int'),'7':_tf('bytes'),'8':_tf('bytes'),'9':_tf('bytes'),'10':_tf('bytes'),'11':_tf('bytes'),'12':_tf('int'),'13':_tf('int'),'14':_tf('bytes'),'15':_tf('bytes'),'16':_tf('int'),'17':_tf('bytes'),'18':_tf('bytes'),'19':_tf('bytes'),'20':_tf('bytes'),'21':_tf('bytes'),'22':_tf('bytes'),'23':_tf('bytes'),'24':_tf('bytes'),'25':_tf('bytes'),'26':_tf('bytes'),'29':_tf('bytes'),'30':_tf('int'),'41':_tf('bytes'),'42':_tf('bytes'),'57':_tf('bytes'),'60':_tf('int'),'61':_tf('int'),'62':_tf('int'),'63':_tf('int'),'64':_tf('int'),'65':_tf('int'),'66':_tf('int'),'67':_tf('int'),'73':_tf('int'),'74':_tf('bytes'),'76':_tf('int'),'77':_tf('bytes'),'78':_tf('int'),'79':_tf('int'),'81':_tf('bytes'),'83':_tf('bytes'),'85':_tf('int'),'86':_tf('bytes'),'87':_tf('int'),'88':_tf('int'),'92':_tf('int'),'93':_tf('bytes'),'94':_tf('bytes'),'96':_tf('bytes'),'97':_tf('int'),'98':_tf('int'),'99':_tf('bytes'),'100':_tf('bytes'),'102':_tf('bytes'),'104':_tf('int'),'105':_tf('int'),'106':_tf('bytes'),'107':_tf('bytes')}
typedef_reg = {'1':_tf('bytes'),'2':_tf('bytes'),'3':_tf('bytes'),'5':_tf('int'),'6':_tf('int'),'7':_tf('int'),'13':_tf('int'),'14':_tf('bytes'),'15':_tf('bytes'),'16':_tf('int'),'20':_tf('bytes'),'21':_tf('int'),'22':_tf('bytes')}
typedef_newbie = {'1':_tf('int'),'2':_tf('int'),'3':_tf('int')}
FIELD_22 = bytes.fromhex("4747524501010100620200001052aa0d669c6a368f08338060d2ee0690053af84a41edcd3558556ec10f24f46c93ac64ca41a16732c46a2cb071246a79b8929032f9e1b6f4ef331bd53cabf29b09b97349a46e9863c0314e1a0d80819fef8aabf03876b3d037db354a7ccb5c1bce96411fb3753f6f50e44c69c4ed617fa30efb8ffc0517ff2f636739be1f304d999cfd6fd48bf69454199794c3dc88f55a4bdbd66534d5a061359cdfd1fb680cd37918df9fdb3cf7d80067b0a3506c90063cf62b2ccec11e23913a2fd7c4ef091331967bb518a5ad1e551146b90821be800883abadde39d6c80a5d798611466c748f075481806c5842ce45e6bd4e3368ec08fe2ec41ceb880cd86249eb71693f79f0bccf9e590c3fae12519fe08c7a1905d0927690109e0df28574bb14847225db1a59230e6662ed7730e15ff9a6c815cb41b420edeada735a4b03e181037c37c2c850257311df2f07b0a56e759372cbd0268e3f13a292ee4373e38ab5096e0342a5e0d7fec6da2bbc265d74baadd2b24ee4f74862f82c21d6694bac53f8ce80312a30068a6276a641c19b11d0305c6fe2f531ac7de578b29f543697f5c73663e6f23aa15277b6122dcd4d4171e38f9ac0b173f39c58416a16c5c1f4a35acd065ce78f449cf538a249339e763272d458e4ed86c976591a9c066b3a37111e44091eb6b5a795249f3e5145db022a6055f2cc675936391312f688f89627845df222a91156555225be36f9714a0ba50246d0f003bda3c9c1292ab73b4f79635ddd023218eda93a302d79e023404c14396544a930b98ed54771aca7fec10d095587685b473e81a9619764fad9256529dcd6e911f4f4629612287d4ee3ec5389f6ec4ec020b0e2aac017232a9197be9e46239ce690fe5d4872b2e98e651510c971667f3aca8b59f3e9d50e43")

HEADERS_MSDK = {"User-Agent": "GarenaMSDK/4.0.44(ASUS_AI2501_B ;Android 12;en;US;app 2.132.1 2019118525;)","Content-Type": "application/json; charset=utf-8","Connection": "keep-alive"}
HEADERS_LOGINBP = {'Host': 'loginbp.ggpolarbear.com','User-Agent': 'UnityPlayer/2018.4.12f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)','Accept': '*/*', 'Accept-Encoding': 'deflate, gzip','Authorization': 'Bearer', 'X-GA': 'v1 1','ReleaseVersion': RELEASE_VER,'Content-Type': 'application/x-www-form-urlencoded','X-Unity-Version': '2018.4.12f1'}

_tl = threading.local()
def get_session():
    s = getattr(_tl, "s", None)
    if s: return s
    s = requests.Session()
    a = HTTPAdapter(pool_connections=POOL_CONN, pool_maxsize=POOL_MAX, max_retries=0)
    s.mount("https://", a); s.mount("http://", a)
    _tl.s = s
    return s

def _build_login_meta(open_id, access_token, server):
    ip = random.choice(server["ips"]); model, os_str, gpu, gpu_full = random.choice(DEVICES)
    return {'3': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S').encode(),'4': b'free fire', '5': 1, '7': GAME_VERSION.encode(),'8': os_str.encode(),'9': b'Handheld', '10': server["isp"].encode(), '11': b'WIFI','12': 1280, '13': 720, '14': b'240','15': b'x86-64 SSE3 SSE4.1 SSE4.2 AVX AVX2 | 2400 | 4','16': random.choice([5951, 6000, 6100, 5500]),'17': gpu.encode(),'18': gpu_full.encode(),'19': f'Google|{uuid.uuid4()}'.encode(),'20': ip.encode(),'21': b'en', '22': open_id.encode(),'23': b'4', '24': b'Handheld','25': model.encode(),'26': server["code"].encode(),'29': access_token.encode(), '30': 1,'41': server["isp"].encode(), '42': b'WIFI','57': b'1ac4b80ecf0478a44203bf8fac6120f5','60': 30000, '61': 30000, '62': 2519, '63': 243,'64': 32357, '65': 34308, '66': 32357, '67': 34308, '73': 1,'74': b'/data/app/~~iw-K-GR3srU7dLE-UxJ4bg==/com.dts.freefiremax-kbPhw3SUYautW0I_oayB_A==/lib/arm','76': 2,'77': b'428775ab8c8845bd341b5357ec61d15e|/data/app/~~iw-K-GR3srU7dLE-UxJ4bg==/com.dts.freefiremax-kbPhw3SUYautW0I_oayB_A==/base.apk','78': 2, '79': 1, '81': b'32', '83': b'2019118525', '85': 3,'86': b'OpenGLES3', '87': 4095, '88': 4,'92': random.choice([19788, 20000, 21000]),'93': b'android_max','94': b'KqsHT2gyPt7vUCc9SCjv2ioi3WEZSEL86ErvXB38suVVK/Z4IVt78ESl/r2S15C1pqu/j6ZmgFL7HbwoFiiVconX08ooKiisQffvEAPCo/C+Lahr','96': b'{"cur_rate":null,"support_etc2":true}','97': 1, '98': 1, '99': b'4', '100': b'4', '102': b'','104': 77149, '105': 1,'106': b'https://dl.cdn.freefiremobile.com/live/ABHotUpdates/|https://dl-core.cdn.freefiremobile.com/live/ABHotUpdates/|6b2078db9d22dd98f8e9386a39af8462','107': b'c8e41b7a93f02d56e1a94c7b8203f5d1'}

def extract_jwt_from_login_response(content):
    try:
        if len(content) > 64:
            try:
                decoded, _ = blackboxprotobuf.decode_message(content[64:])
                if isinstance(decoded, dict):
                    for k in ['8', 8, b'8']:
                        if k in decoded:
                            jwt_val = decoded[k]
                            return jwt_val.decode('utf-8', errors='ignore') if isinstance(jwt_val, bytes) else jwt_val
            except: pass
        match = re.search(r'(eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+)', content.decode('utf-8', errors='ignore'))
        return match.group(1) if match else None
    except: return None

# ============================================================
# CORE GENERATOR (Multi-User Safe)
# ============================================================
def register_one(worker_id, job_id, server_obj, nick_prefix):
    session = get_session()
    
    # ইনফিনিট রিট্রাই (যতক্ষণ না সফল হচ্ছে)
    while True:
        # চেক করা এই জবটি ক্যান্সেল করা হয়েছে কিনা (যদি ক্যান্সেল হয়, তবে থেমে যাবে)
        with LOCK:
            if job_id not in JOBS or JOBS[job_id]["job"].get("cancelled"):
                return None

        try:
            password = gen_password()
            reg_body = json.dumps({"app_id": APP_ID, "client_type": 2, "password": password, "source": 2}, separators=(",", ":"))
            reg_sig = hmac.new(MAIN_KEY, reg_body.encode(), hashlib.sha256).hexdigest()
            r = session.post(URL_GUEST_REGISTER, headers={**HEADERS_MSDK, "Authorization": "Signature " + reg_sig}, data=reg_body, verify=False, timeout=HTTP_TIMEOUT)
            
            if r.status_code in [429, 503]:
                time.sleep(random.uniform(3, 7)) # ব্লক হলে ৩-৭ সেকেন্ড অপেক্ষা
                continue
                
            if r.status_code != 200: 
                time.sleep(2)
                continue
                
            uid = r.json()["data"]["uid"]

            grant_body = {"client_id": APP_ID, "client_secret": CLIENT_SECRET, "client_type": 2, "device_id": f"02-{uuid.uuid4()}", "password": password, "response_type": "token", "uid": int(uid)}
            r2 = session.post(URL_TOKEN_GRANT, headers=HEADERS_MSDK, json=grant_body, verify=False, timeout=HTTP_TIMEOUT)
            if r2.status_code != 200: 
                time.sleep(2)
                continue
                
            gd = r2.json()["data"]
            access_token, open_id = gd["access_token"], gd["open_id"]

            hdr = dict(HEADERS_LOGINBP); hdr["X-GA-SV"] = str(int(time.time()))
            jwt_token = None
            try:
                login_resp = session.post(URL_MAJOR_LOGIN, headers=hdr, data=enc_aes(blackboxprotobuf.encode_message(_build_login_meta(open_id, access_token, server_obj), typedef_login)), verify=False, timeout=HTTP_TIMEOUT)
                if login_resp.status_code == 200: jwt_token = extract_jwt_from_login_response(login_resp.content)
            except: pass

            # কাস্টম নেম জেনারেশন
            nick = gen_nickname(nick_prefix, 12)
            
            reg_msg = {'1': nick, '2': access_token.encode(), '3': open_id.encode(),'5': 102000007, '6': 4, '7': 1, '13': 1,'14': encode_f14(open_id), '15': b'en', '16': 2,'20': GAME_VERSION.encode(), '21': 1, '22': FIELD_22}
            rr = session.post(URL_MAJOR_REGISTER, headers=hdr, data=enc_aes(blackboxprotobuf.encode_message(reg_msg, typedef_reg)), verify=False, timeout=HTTP_TIMEOUT)
            
            if rr.status_code != 200: 
                time.sleep(2)
                continue
                
            res, _ = blackboxprotobuf.decode_message(rr.content)
            account_id = res.get('3') or res.get(b'3') if isinstance(res, dict) else None
            
            if not account_id: 
                time.sleep(2)
                continue

            try:
                session.post(URL_NEWBIE_CHOICE, headers=hdr, data=enc_aes(blackboxprotobuf.encode_message({'1': int(account_id), '2': 2, '3': 3}, typedef_newbie)), verify=False, timeout=HTTP_TIMEOUT)
            except: pass

            if not jwt_token:
                try:
                    hdr2 = dict(HEADERS_LOGINBP); hdr2["X-GA-SV"] = str(int(time.time()))
                    login_resp2 = session.post(URL_MAJOR_LOGIN, headers=hdr2, data=enc_aes(blackboxprotobuf.encode_message(_build_login_meta(open_id, access_token, server_obj), typedef_login)), verify=False, timeout=HTTP_TIMEOUT)
                    if login_resp2.status_code == 200: jwt_token = extract_jwt_from_login_response(login_resp2.content)
                except: pass

            return {
                "uid": str(uid), "password": str(password),
                "name": nick.decode('utf-8', errors='ignore'),
                "account_id": str(account_id), "open_id": open_id,
                "access_token": access_token, "jwt": jwt_token or "",
                "region": server_obj["code"],
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

        except Exception:
            time.sleep(2)

# ============================================================
# FLASK API SERVER (Multi-Device & Safe)
# ============================================================
app = Flask(__name__)

@app.route("/", methods=["GET"])
def home():
    return make_response("""
    <html>
        <body style="background:#0d0f14; color:#ffd166; font-family:monospace; padding:50px; text-align:center;">
            <h1>🟢 Multi-User API is Running</h1>
            <p>Unlimited generation enabled. Multiple devices supported.</p>
            <br>
            <p>POST /api/generate</p>
            <p>GET /api/status?job_id=YOUR_JOB_ID</p>
        </body>
    </html>
    """, 200)

@app.route("/api/generate", methods=["POST"])
def api_generate():
    body = request.get_json(force=True, silent=True) or {}
    
    count = int(body.get("count", 10))
    threads = int(body.get("threads", 5))
    server_key = str(body.get("server", "1"))
    nick_prefix = str(body.get("nick_prefix", "DM"))
    
    server_obj = SERVERS.get(server_key, SERVERS["1"])
    
    # প্রতিটা রিকোয়েস্টের জন্য ইউনিক Job ID তৈরি
    job_id = str(uuid.uuid4())[:8]
    
    with LOCK:
        JOBS[job_id] = {
            "job": {"running": True, "total": count, "done": 0, "errors": 0, "cancelled": False},
            "accounts": []
        }

    # আলাদা থ্রেডে কাজ শুরু
    def worker():
        try:
            with ThreadPoolExecutor(max_workers=threads) as ex:
                futures = [ex.submit(register_one, i, job_id, server_obj, nick_prefix) for i in range(1, count + 1)]
                for f in futures:
                    res = f.result()
                    with LOCK:
                        if job_id not in JOBS: return
                        if res: 
                            JOBS[job_id]["accounts"].append(res)
                        else: 
                            JOBS[job_id]["job"]["errors"] += 1
                        JOBS[job_id]["job"]["done"] += 1
        finally:
            with LOCK:
                if job_id in JOBS:
                    JOBS[job_id]["job"]["running"] = False

    threading.Thread(target=worker, daemon=True).start()
    
    return jsonify({
        "ok": True, 
        "job_id": job_id,
        "message": f"Started {count} accounts on {server_obj['code']}"
    })

@app.route("/api/status", methods=["GET"])
def api_status():
    job_id = request.args.get("job_id")
    
    with LOCK:
        # যদি নির্দিষ্ট কোনো Job ID দেওয়া হয়
        if job_id:
            if job_id not in JOBS:
                return jsonify({"ok": False, "message": "Invalid Job ID"}), 404
            return jsonify({
                "ok": True, 
                "job": dict(JOBS[job_id]["job"]), 
                "accounts": list(JOBS[job_id]["accounts"])
            })
        else:
            # যদি কোনো Job ID না দেওয়া হয়, তবে সব রানিং জব একসাথে দেখাবে
            return jsonify({"ok": True, "active_jobs": len([j for j in JOBS.values() if j["job"]["running"]])})

@app.route("/api/cancel", methods=["POST"])
def api_cancel():
    body = request.get_json(force=True, silent=True) or {}
    job_id = body.get("job_id")
    
    with LOCK:
        if job_id in JOBS:
            JOBS[job_id]["job"]["cancelled"] = True
            JOBS[job_id]["job"]["running"] = False
            return jsonify({"ok": True, "message": f"Job {job_id} cancelled."})
    return jsonify({"ok": False, "message": "Invalid Job ID"}), 404

# ============================================================
# ENTRY POINT
# ============================================================
if __name__ == "__main__":
    print("=========================================")
    print("  DARK MASTER - MULTI-USER API SERVER")
    print("=========================================")
    print("[+] Server running at: http://127.0.0.1:5000")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)