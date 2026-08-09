#!/usr/bin/env python3
__version__ = "1.0.0"
import subprocess, threading, os
from collections import deque
from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__, static_folder=".")

_HOME = os.path.expanduser("~")

# Detect RNS binary path - support both old (rns-env) and new (MeshGate/.venv) layouts
import shutil as _shutil
def _find_rns_bin(name):
    # Check known locations
    for path in [
        f"{_HOME}/rns-env/bin/{name}",
        f"{_HOME}/MeshGate/.venv/bin/{name}",
        f"{_HOME}/NOEMA-RNSGate-Lite/.venv/bin/{name}",
    ]:
        if os.path.exists(path):
            return path
    # Fallback to system PATH
    found = _shutil.which(name)
    return found or name
_RNS_BIN = os.path.dirname(_find_rns_bin("rnstatus"))

SERVICES = ["noema_lxmf_bridge", "rnsd", "i2pd", "nomadnet", "rbrowser"]

NOMADNET_PAGE = f"{_HOME}/.nomadnetwork/storage/pages/index.mu"
NOMADNET_PAGES_DIR = f"{_HOME}/.nomadnetwork/storage/pages"
SCRIPTS_DIR = f"{_HOME}/NOEMA-RNSGate-Lite/scripts"
NOMADNET_ADDR_FILE = f"{_HOME}/.nomadnetwork/storage/hashes"

CONFIGS = {
    "LXMF Bridge": "/etc/noema/bridge.cfg",
    "reticulum": f"{_HOME}/.reticulum/config",
    "nomadnet": f"{_HOME}/.nomadnetwork/config",
}

lxmf_log = deque(maxlen=200)

# Background CPU monitor
_cpu_percent = 0
def _cpu_monitor():
    global _cpu_percent
    import time as _t
    while True:
        try:
            def _r():
                s = open("/proc/stat").readline().split()
                return sum(int(x) for x in s[1:8]), int(s[4])
            t1,i1=_r(); _t.sleep(1); t2,i2=_r()
            dt=t2-t1
            if dt>0: _cpu_percent=round(100*(dt-(i2-i1))/dt)
        except: pass
        _t.sleep(4)
import threading as _cpu_th
_cpu_th.Thread(target=_cpu_monitor,daemon=True).start()

traffic_history = deque(maxlen=60)

def sh(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
    return r.stdout.strip(), r.returncode

# RNode history for graphs
from collections import deque as _dq
rnode_history = _dq(maxlen=120)  # 120 samples = 20 min at 10s intervals

def collect_metrics():
    import time as _t, subprocess as _sp
    while True:
        try:
            r = _sp.run(f"{_RNS_BIN}/rnstatus", shell=True, capture_output=True, text=True, timeout=15)
            ts = int(_t.time())
            interfaces = {}
            cur = None
            for line in r.stdout.splitlines():
                line = line.strip()
                if not line: continue
                if "[" in line and "]" in line:
                    cur = line
                    interfaces[cur] = {}
                elif cur and ":" in line:
                    k,v = line.split(":",1)
                    interfaces[cur][k.strip()] = v.strip()
            traffic_history.append({"ts": ts, "interfaces": interfaces})
            # Collect RNode specific metrics
            for iname, fields in interfaces.items():
                if "RNode" in iname:
                    try:
                        airtime_str = fields.get("Airtime","0%").split("%")[0].split("(")[-1] if "(" in fields.get("Airtime","") else fields.get("Airtime","0%").split("%")[0]
                        noise_str = fields.get("Noise Fl.","0").split()[0].replace("dBm","")
                        traffic_str = fields.get("Traffic","0").replace("↑","").replace("↓","").strip()
                        rnode_history.append({
                            "ts": ts,
                            "iface": iname,
                            "airtime": float(airtime_str.strip()) if airtime_str.strip().replace(".","").isdigit() else 0,
                            "noise": float(noise_str.strip()) if noise_str.strip().replace("-","").replace(".","").isdigit() else 0,
                            "traffic_raw": traffic_str,
                        })
                    except: pass
        except: pass
        _t.sleep(10)

import threading as _th
_th.Thread(target=collect_metrics, daemon=True).start()

@app.route("/api/lxmf/clear", methods=["POST"])
def lxmf_clear():
    lxmf_log.clear()
    return jsonify({"ok": True})

def lxmf_collector():
    import paho.mqtt.client as mqtt, time
    def on_connect(cl, u, f, rc):
        if rc == 0:
            cl.subscribe([("message/lxmf/receive", 0), ("message/lxmf/send", 0)])
    def on_message(cl, u, m):
        import json as _j
        try:
            raw = m.payload.decode("utf-8", errors="replace")
            ts = time.strftime("%H:%M:%S")
            topic = m.topic
            lxmf_log.append(f"[{ts}] {topic} >> {raw}")
        except: pass
    while True:
        try:
            client = mqtt.Client()
            cfg = {}
            try:
                with open("/etc/noema/bridge.cfg") as f:
                    for line in f:
                        if "=" in line and not line.strip().startswith("#"):
                            k,v = line.split("=",1)
                            cfg[k.strip().lower()] = v.strip()
            except: pass
            host = cfg.get("host","10.0.1.111")
            port = int(cfg.get("port",1883))
            user = cfg.get("username","mqtt")
            pw   = cfg.get("password","mqtt")
            client.username_pw_set(user, pw)
            client.on_connect = on_connect
            client.on_message = on_message
            client.connect(host, port, 60)
            client.loop_forever()
        except Exception as e:
            lxmf_log.append(f"MQTT error: {e}")
            import time; time.sleep(10)

threading.Thread(target=lxmf_collector, daemon=True).start()

@app.route("/api/lxmf/stats")
def lxmf_stats():
    import json as _json
    count = {"total": 0, "sent": 0, "recv": 0}
    nodes = {}
    for line in lxmf_log:
        count["total"] += 1
        if "lxmf/send" in line:
            count["sent"] += 1
        elif "lxmf/receive" in line:
            count["recv"] += 1
            try:
                raw = line.split(">>",1)[1].strip()
                d = _json.loads(raw)
                src = d.get("source","")
                if src:
                    if src not in nodes:
                        nodes[src] = {"msgs": 0, "last": ""}
                    nodes[src]["msgs"] += 1
                    ts = line.split("]")[0].replace("[","").strip()
                    nodes[src]["last"] = ts
            except: pass
    return jsonify({
        "count": count,
        "nodes": [{"id": k, "last": v["last"], "msgs": v["msgs"]}
                  for k,v in sorted(nodes.items(), key=lambda x: x[1]["last"], reverse=True)]
    })

@app.route("/api/lxmf")
def lxmf_api():
    since = int(request.args.get("since", 0))
    msgs = list(lxmf_log)
    return jsonify({"msgs": msgs[since:], "total": len(msgs)})

@app.route("/api/services")
def svc_list():
    return jsonify([
        {"name": s, "status": sh(f"systemctl is-active {s}")[0], "enabled": sh(f"systemctl is-enabled {s}")[0]}
        for s in SERVICES
    ])

@app.route("/api/services/<name>/status")
def svc_status(name):
    return jsonify({"enabled": sh(f"systemctl is-enabled {name}")[0]})

@app.route("/api/services/<name>/<action>", methods=["POST"])
def svc_action(name, action):
    if name not in SERVICES or action not in ("start","stop","restart","enable","disable"):
        return jsonify({"error":"bad"}), 400
    sh(f"sudo systemctl {action} {name}")
    import time; time.sleep(1)
    enabled = sh(f"systemctl is-enabled {name}")[0]
    return jsonify({"status": sh(f"systemctl is-active {name}")[0], "enabled": enabled})

@app.route("/api/system")
def system():
    cpu = str(_cpu_percent)
    mem,_  = sh("LC_ALL=C free -m | awk '/^Mem:/{print $2,$3}'")
    disk,_ = sh("df -m / | awk 'NR==2{print $2,$3}'")
    temp,_ = sh("cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null || echo 0")
    up,_   = sh("cat /proc/uptime")
    ip,_   = sh("hostname -I | awk '{print $1}'")
    try: rt,ru = map(int, mem.split())
    except: rt,ru = 1,0
    try: dt,du = map(int, disk.split())
    except: dt,du = 1,0
    try:
        s = int(float(up.split()[0]))
        uptime = f"{s//86400}д {(s%86400)//3600}ч {(s%3600)//60}м"
    except: uptime = "—"
    ver,_ = sh(f"{_RNS_BIN}/python3 -c 'import RNS; print(RNS.__version__)' 2>/dev/null")
    pyver,_ = sh(f"{_RNS_BIN}/python3 --version 2>&1")
    return jsonify({
        "rns_version": ver or "—",
        "py_version": pyver.replace("Python ","") or "—",
        "cpu": int(cpu) if cpu else 0,
        "temp": round(int(temp)/1000) if temp else 0,
        "ram_used": ru, "ram_total": rt,
        "disk_used": du, "disk_total": dt,
        "uptime": uptime, "ip": ip
    })

@app.route("/api/reboot", methods=["POST"])
def reboot():
    sh("sudo shutdown -r +0")
    return jsonify({"ok": True})

import json as _json, os as _os
NODES_FILE = f"{_HOME}/dashboard/monitored_nodes.json"

def load_nodes_list():
    try:
        return _json.load(open(NODES_FILE))
    except:
        return [
            {"name": "Санкт-Петербург", "host": "rns.obomba.tech", "port": 4242},
            {"name": "Норильск", "host": "rns_m9.kopcap.online", "port": 4242},
            {"name": "Москва", "host": "artyom.ddns.net", "port": 4242},
            {"name": "Сидней", "host": "sydney.reticulum.au", "port": 4242},
            {"name": "Новосибирск", "host": "37.193.84.9", "port": 4242},
        ]

def save_nodes_list(nodes):
    _json.dump(nodes, open(NODES_FILE, "w"), indent=2)

@app.route("/api/nodes_monitor")
def nodes_monitor():
    import socket, threading
    nodes = load_nodes_list()
    result = [{**n, "status": "offline"} for n in nodes]
    def check(i, n):
        try:
            s = socket.create_connection((n["host"], n["port"]), timeout=5)
            s.close()
            result[i]["status"] = "online"
        except: pass
    threads = [threading.Thread(target=check, args=(i, n)) for i, n in enumerate(nodes)]
    for t in threads: t.start()
    for t in threads: t.join(timeout=6)
    return jsonify(result)

@app.route("/api/nodes_monitor", methods=["POST"])
def nodes_monitor_save():
    nodes = request.json or []
    save_nodes_list(nodes)
    return jsonify({"ok": True})

@app.route("/api/rnprobe", methods=["POST"])
def rnprobe():
    addr = (request.json or {}).get("addr","").strip()
    if not addr: return jsonify({"error":"no address"}), 400
    out, rc = sh(f"{_RNS_BIN}/rnprobe lxmf.delivery {addr} -n 3 -t 10 2>&1")
    return jsonify({"output": out, "rc": rc})

@app.route("/api/addresses")
def addresses():
    addrs = {}
    try:
        addrs["lxmf_bridge"] = open("/root/lxmf-tools/lxmf_address").read().strip()
    except: pass
    return jsonify(addrs)

@app.route("/api/lxmf/address")
def lxmf_address():
    try:
        addr = open("/root/lxmf-tools/lxmf_address").read().strip()
        return jsonify({"address": addr})
    except:
        return jsonify({"address": ""})

@app.route("/api/rnode/history")
def rnode_history_api():
    iface = request.args.get("iface")
    data = list(rnode_history)
    if iface:
        data = [d for d in data if iface in d.get("iface","")]
    return jsonify(data)

@app.route("/api/rnstatus")
def rnstatus():
    import subprocess as _sp
    r = _sp.run(f"{_RNS_BIN}/rnstatus", shell=True, capture_output=True, text=True, timeout=15)
    out = r.stdout
    interfaces = []
    cur = None
    for line in out.splitlines():
        line = line.strip()
        if not line: continue
        if "[" in line and "]" in line:
            if cur: interfaces.append(cur)
            cur = {"name": line, "fields": {}}
        elif cur and ":" in line:
            k,v = line.split(":",1)
            cur["fields"][k.strip()] = v.strip()
    if cur: interfaces.append(cur)
    return jsonify({"interfaces": interfaces})

@app.route("/api/mqtt/status")
def mqtt_status():
    cfg = {}
    try:
        with open("/etc/noema/bridge.cfg") as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    k,v = line.split("=",1)
                    cfg[k.strip().lower()] = v.strip()
    except: pass
    import socket
    host = cfg.get("host","10.0.1.111")
    port = int(cfg.get("port",1883))
    try:
        s = socket.create_connection((host, port), timeout=3)
        s.close()
        status = "ok"
    except:
        status = "error"
    return jsonify({"status": status, "host": host, "port": port})

@app.route("/api/configs")
def get_configs():
    result = {}
    for k, path in CONFIGS.items():
        try:
            result[k] = {"path": path, "content": open(path).read()}
        except:
            result[k] = {"path": path, "content": ""}
    return jsonify(result)

@app.route("/api/configs/<name>", methods=["POST"])
def save_config(name):
    if name not in CONFIGS:
        return jsonify({"error": "unknown config"}), 400
    content = (request.json or {}).get("content", "")
    try:
        open(CONFIGS[name], "w").write(content)
        if name == "noema_lxmf_bridge":
            sh("sudo systemctl restart noema_lxmf_bridge")
        elif name == "reticulum":
            sh("sudo systemctl restart rnsd")
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/logs/<name>")
def get_log(name):
    import re as _re
    allowed = {"rnsd": "rnsd", "noema_lxmf_bridge": "noema_lxmf_bridge",
               "nomadnet": "nomadnet", "dashboard": "dashboard", "rbrowser": "rbrowser"}
    if name not in allowed:
        return jsonify({"error": "unknown"}), 400
    out, _ = sh(f"journalctl -u {allowed[name]} -n 200 --no-pager -o cat")
    lines = []
    for line in out.splitlines():
        line = line.strip()
        if not line: continue
        ll = line.lower()
        if any(w in ll for w in ("error","fail","crit","exception","traceback")): lvl="err"
        elif any(w in ll for w in ("warn","warning")): lvl="warn"
        elif any(w in ll for w in ("info","notice","started","connected","address")): lvl="info"
        else: lvl="ok"
        lines.append({"t": line, "l": lvl})
    return jsonify(lines)

@app.route("/api/chat/history/clear", methods=["POST"])
def chat_history_clear():
    import time as _t
    days = (request.json or {}).get("days", 0)
    cutoff = int(_t.time()) - days * 86400 if days > 0 else 0
    with _chat_lock:
        try:
            try:
                data = _chat_json.load(open(CHAT_FILE))
            except:
                data = {}
            deleted = 0
            for addr in data:
                before = len(data[addr])
                if cutoff > 0:
                    data[addr] = [m for m in data[addr] if m.get("ts", 0) >= cutoff]
                else:
                    data[addr] = []
                deleted += before - len(data[addr])
            _chat_json.dump(data, open(CHAT_FILE, "w"))
            return jsonify({"ok": True, "deleted": deleted})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

@app.route("/api/backup/download")
def backup_download():
    import zipfile, io, time as _t
    buf = io.BytesIO()
    files = {
        "reticulum_config": f"{_HOME}/.reticulum/config",
        "noema_bridge.cfg": "/etc/noema/bridge.cfg",
        "lxmf_identity": f"{_HOME}/lxmf-tools/identity",
        "monitored_nodes.json": f"{_HOME}/dashboard/monitored_nodes.json",
    }
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, path in files.items():
            try:
                zf.write(path, name)
            except: pass
    buf.seek(0)
    from flask import send_file
    ts = _t.strftime("%Y%m%d_%H%M%S")
    return send_file(buf, mimetype="application/zip",
                     as_attachment=True,
                     download_name=f"meshgate_backup_{ts}.zip")

@app.route("/api/backup/restore", methods=["POST"])
def backup_restore():
    import zipfile, io
    f = request.files.get("file")
    if not f: return jsonify({"error": "no file"}), 400
    restore_map = {
        "reticulum_config": f"{_HOME}/.reticulum/config",
        "noema_bridge.cfg": "/etc/noema/bridge.cfg",
        "monitored_nodes.json": f"{_HOME}/dashboard/monitored_nodes.json",
    }
    try:
        with zipfile.ZipFile(io.BytesIO(f.read())) as zf:
            for name, path in restore_map.items():
                if name in zf.namelist():
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    open(path, "wb").write(zf.read(name))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/backup", methods=["POST"])
def backup():
    import time as _t
    ts = _t.strftime("%Y%m%d_%H%M%S")
    for path in CONFIGS.values():
        try:
            content = open(path).read()
            open(f"{path}.bak.{ts}", "w").write(content)
        except: pass
    return jsonify({"ok": True, "ts": ts})


# ============================================================
# LXMF MESSENGER
# ============================================================
import json as _chat_json
import threading as _chat_th

CHAT_FILE = f"{_HOME}/dashboard/chat_history.json"
CONTACTS_FILE = f"{_HOME}/dashboard/chat_contacts.json"

_chat_lock = _chat_th.Lock()
_chat_router = None
_chat_identity = None
_chat_dest = None
_chat_incoming = deque(maxlen=500)

CHAT_STORAGE = f"{_HOME}/dashboard/chat_lxmf"

def _chat_init():
    global _chat_router, _chat_identity, _chat_dest
    import sys as _sys, glob as _glob
    # Find site-packages in venv
    _sp_paths = _glob.glob(f"{_HOME}/rns-env/lib/python*/site-packages") +                 _glob.glob(f"{_HOME}/MeshGate/.venv/lib/python*/site-packages") + \
                _glob.glob(f"{_HOME}/NOEMA-RNSGate-Lite/.venv/lib/python*/site-packages")
    if _sp_paths: _sys.path.insert(0, _sp_paths[0])
    import RNS, LXMF
    os.makedirs(CHAT_STORAGE, exist_ok=True)
    identity_file = f"{CHAT_STORAGE}/identity"
    RNS.Reticulum(loglevel=RNS.LOG_CRITICAL)
    if os.path.exists(identity_file):
        identity = RNS.Identity.from_file(identity_file)
    else:
        identity = RNS.Identity()
        identity.to_file(identity_file)
    router = LXMF.LXMRouter(identity=identity, storagepath=CHAT_STORAGE)
    dest = router.register_delivery_identity(identity, display_name="NOEMA Chat")
    router.register_delivery_callback(_chat_on_receive)
    router.announce(destination_hash=dest.hash)
    _chat_router = router

    # Re-announce and request paths periodically
    def _announce_loop():
        import time as _t
        _t.sleep(5)
        # Request paths to all known contacts
        try:
            contacts = _load_contacts()
            for c in contacts:
                try:
                    dest_hash = bytes.fromhex(c["addr"])
                    if not RNS.Identity.recall(dest_hash):
                        RNS.Transport.request_path(dest_hash)
                except: pass
        except: pass
        while True:
            try:
                router.announce(destination_hash=dest.hash)
            except: pass
            _t.sleep(300)
    import threading as _ann_th
    _ann_th.Thread(target=_announce_loop, daemon=True).start()
    _chat_identity = identity
    _chat_dest = dest
    open(f"{CHAT_STORAGE}/address", "w").write(RNS.hexrep(dest.hash, delimit=False))

def _chat_on_receive(message):
    import RNS, time as _t, uuid as _uid, mimetypes as _mt
    try:
        src = RNS.hexrep(message.source_hash, delimit=False)
        text = message.content.decode("utf-8") if isinstance(message.content, bytes) else str(message.content)
        ts = int(_t.time())
        msg = {"ts": ts, "from": src, "to": "me", "text": text, "direction": "in"}

        # Extract file attachment from LXMF fields
        try:
            fields = message.fields or {}
            # LXMF field 0x06 = image, 0x05 = file attachments
            att_data = fields.get(0x05)  # FILE_ATTACHMENTS field [[name, data], ...]
            if att_data and isinstance(att_data, list) and len(att_data) > 0:
                att = att_data[0]
                if isinstance(att, list) and len(att) >= 2:
                    fname = str(att[0]) if att[0] else "file"
                    fdata = att[1] if isinstance(att[1], bytes) else None
                    if fdata:
                        fid = str(_uid.uuid4())
                        fpath = os.path.join(CHAT_FILES_DIR, fid)
                        open(fpath, "wb").write(fdata)
                        # Detect mime from data signature
                        mime = _mt.guess_type(fname)[0] or "application/octet-stream"
                        if fdata[:8] == b"\x89PNG\r\n\x1a\n": mime = "image/png"
                        elif fdata[:3] == b"\xff\xd8\xff": mime = "image/jpeg"
                        elif fdata[:6] in (b"GIF87a", b"GIF89a"): mime = "image/gif"
                        meta = _files_get_meta()
                        meta.append({"id": fid, "name": fname, "size": len(fdata), "mime": mime, "ts": ts})
                        _files_save_meta(meta)
                        msg["file_id"] = fid
                        msg["file_name"] = fname
                        msg["file_size"] = len(fdata)
                        msg["file_mime"] = mime
        except: pass

        _save_chat_msg(src, msg)
        _chat_incoming.append(msg)
    except: pass

def _load_chat_history(addr):
    try:
        data = _chat_json.load(open(CHAT_FILE))
        return data.get(addr, [])
    except:
        return []

def _save_chat_msg(addr, msg):
    with _chat_lock:
        try:
            try:
                data = _chat_json.load(open(CHAT_FILE))
            except:
                data = {}
            if addr not in data:
                data[addr] = []
            data[addr].append(msg)
            data[addr] = data[addr][-200:]
            _chat_json.dump(data, open(CHAT_FILE, "w"))
        except: pass

def _load_contacts():
    try:
        return _chat_json.load(open(CONTACTS_FILE))
    except:
        return []

def _save_contacts(contacts):
    _chat_json.dump(contacts, open(CONTACTS_FILE, "w"), ensure_ascii=False)

# Init chat in main thread at startup
try:
    _chat_init()
except Exception as _e:
    open(f"{_HOME}/dashboard/chat_init_error.log", "w").write(str(_e))

# Sync contacts from history - restore any missing contacts
try:
    _hist = _chat_json.load(open(CHAT_FILE)) if os.path.exists(CHAT_FILE) else {}
    _contacts = _load_contacts()
    _contact_addrs = {c["addr"] for c in _contacts}
    _changed = False
    # Get own chat address to exclude it
    _own_addr = ""
    try:
        _own_addr = open(f"{_HOME}/dashboard/chat_lxmf/address").read().strip()
    except: pass
    for _addr in _hist:
        if _addr not in _contact_addrs and _addr != "me" and _addr != _own_addr:
            _contacts.append({"addr": _addr, "name": _addr[:8]})
            _changed = True
    if _changed:
        _save_contacts(_contacts)
except: pass

@app.route("/api/chat/address")
def chat_address():
    try:
        addr = open(f"{CHAT_STORAGE}/address").read().strip()
        return jsonify({"address": addr})
    except:
        return jsonify({"address": ""})

@app.route("/api/chat/contacts")
def chat_contacts():
    return jsonify(_load_contacts())

@app.route("/api/chat/contacts", methods=["POST"])
def chat_contacts_save():
    contacts = request.json or []
    _save_contacts(contacts)
    return jsonify({"ok": True})

@app.route("/api/chat/history/<addr>")
def chat_history(addr):
    return jsonify(_load_chat_history(addr))

@app.route("/api/chat/send", methods=["POST"])
def chat_send():
    import sys as _sys, glob as _glob
    # Find site-packages in venv
    _sp_paths = _glob.glob(f"{_HOME}/rns-env/lib/python*/site-packages") +                 _glob.glob(f"{_HOME}/MeshGate/.venv/lib/python*/site-packages") + \
                _glob.glob(f"{_HOME}/NOEMA-RNSGate-Lite/.venv/lib/python*/site-packages")
    if _sp_paths: _sys.path.insert(0, _sp_paths[0])
    import RNS, LXMF, time as _t
    data = request.json or {}
    dest_addr = data.get("to", "").strip().replace("<","").replace(">","")
    text = data.get("text", "").strip()
    file_id = data.get("file_id")
    file_name = data.get("file_name")
    file_size = data.get("file_size")
    file_mime = data.get("file_mime")
    if not dest_addr or (not text and not file_id):
        return jsonify({"error": "no dest or text"}), 400
    # MeshChat requires non-empty text with attachments
    if file_id and not text:
        text = file_name or "📎 файл"
    if not _chat_router or not _chat_dest:
        return jsonify({"error": "LXMF not ready"}), 503
    try:
        dest_hash = bytes.fromhex(dest_addr)
        identity = RNS.Identity.recall(dest_hash)
        if not identity:
            RNS.Transport.request_path(dest_hash)
            import time; time.sleep(3)
            identity = RNS.Identity.recall(dest_hash)
        if not identity:
            return jsonify({"error": "destination unknown, requesting path..."}), 404
        dest = RNS.Destination(identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery")
        msg = LXMF.LXMessage(dest, _chat_dest, text, desired_method=LXMF.LXMessage.DIRECT)
        # Attach file if provided
        if file_id:
            fpath = os.path.join(CHAT_FILES_DIR, file_id)
            if os.path.exists(fpath):
                fdata = open(fpath, "rb").read()
                fname = file_name or "file"
                # Always use FILE_ATTACHMENTS field (0x05) - MeshChat format
                msg.fields = {0x05: [[fname, fdata]]}
        _chat_router.handle_outbound(msg)
        ts = int(_t.time())
        record = {"ts": ts, "from": "me", "to": dest_addr, "text": text, "direction": "out"}
        if file_id:
            record.update({"file_id": file_id, "file_name": file_name, "file_size": file_size, "file_mime": file_mime})
        _save_chat_msg(dest_addr, record)
        return jsonify({"ok": True, "ts": ts})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/chat/incoming")
def chat_incoming():
    since = int(request.args.get("since", 0))
    msgs = [m for m in _chat_incoming if m["ts"] > since]
    return jsonify(msgs)



# ============================================================
# CHAT FILES
# ============================================================
import uuid as _uuid
import shutil as _shutil

CHAT_FILES_DIR = f"{_HOME}/dashboard/chat_files"
CHAT_FILES_MAX_MB = 100
CHAT_FILES_META = f"{_HOME}/dashboard/chat_files_meta.json"

os.makedirs(CHAT_FILES_DIR, exist_ok=True)

def _files_get_meta():
    try:
        return _chat_json.load(open(CHAT_FILES_META))
    except:
        return []

def _files_save_meta(meta):
    _chat_json.dump(meta, open(CHAT_FILES_META, "w"), ensure_ascii=False)

def _files_get_dir_size_mb():
    total = 0
    for f in os.scandir(CHAT_FILES_DIR):
        try: total += f.stat().st_size
        except: pass
    return total / 1024 / 1024

def _files_cleanup():
    """Remove oldest files if over limit"""
    meta = _files_get_meta()
    while _files_get_dir_size_mb() > CHAT_FILES_MAX_MB and meta:
        oldest = meta.pop(0)
        try:
            os.remove(os.path.join(CHAT_FILES_DIR, oldest["id"]))
        except: pass
    _files_save_meta(meta)

@app.route("/api/chat/files/upload", methods=["POST"])
def chat_file_upload():
    import time as _t
    f = request.files.get("file")
    if not f: return jsonify({"error": "no file"}), 400
    fid = str(_uuid.uuid4())
    fname = f.filename or "file"
    fpath = os.path.join(CHAT_FILES_DIR, fid)
    f.save(fpath)
    fsize = os.path.getsize(fpath)
    mime = f.content_type or "application/octet-stream"
    meta = _files_get_meta()
    meta.append({
        "id": fid,
        "name": fname,
        "size": fsize,
        "mime": mime,
        "ts": int(_t.time())
    })
    _files_save_meta(meta)
    _files_cleanup()
    return jsonify({"ok": True, "id": fid, "name": fname, "size": fsize, "mime": mime})

@app.route("/api/chat/files/<fid>")
def chat_file_download(fid):
    from flask import send_file
    fpath = os.path.join(CHAT_FILES_DIR, fid)
    if not os.path.exists(fpath):
        return jsonify({"error": "not found"}), 404
    meta = _files_get_meta()
    info = next((m for m in meta if m["id"] == fid), {})
    fname = info.get("name", fid)
    return send_file(fpath, as_attachment=True, download_name=fname)

@app.route("/api/chat/files/<fid>/preview")
def chat_file_preview(fid):
    from flask import send_file
    fpath = os.path.join(CHAT_FILES_DIR, fid)
    if not os.path.exists(fpath):
        return jsonify({"error": "not found"}), 404
    meta = _files_get_meta()
    info = next((m for m in meta if m["id"] == fid), {})
    mime = info.get("mime", "application/octet-stream")
    return send_file(fpath, mimetype=mime)

@app.route("/api/chat/files")
def chat_files_list():
    meta = _files_get_meta()
    size_mb = round(_files_get_dir_size_mb(), 2)
    return jsonify({
        "files": meta,
        "size_mb": size_mb,
        "max_mb": CHAT_FILES_MAX_MB
    })

@app.route("/api/chat/files/<fid>", methods=["DELETE"])
def chat_file_delete(fid):
    fpath = os.path.join(CHAT_FILES_DIR, fid)
    try: os.remove(fpath)
    except: pass
    meta = [m for m in _files_get_meta() if m["id"] != fid]
    _files_save_meta(meta)
    return jsonify({"ok": True})

@app.route("/api/chat/files/clear", methods=["POST"])
def chat_files_clear():
    meta = _files_get_meta()
    for m in meta:
        try: os.remove(os.path.join(CHAT_FILES_DIR, m["id"]))
        except: pass
    _files_save_meta([])
    return jsonify({"ok": True})

@app.route("/api/chat/files/settings", methods=["POST"])
def chat_files_settings():
    global CHAT_FILES_MAX_MB
    data = request.json or {}
    if "max_mb" in data:
        CHAT_FILES_MAX_MB = int(data["max_mb"])
    return jsonify({"ok": True, "max_mb": CHAT_FILES_MAX_MB})


@app.route("/api/run", methods=["POST"])
def run_command():
    allowed = {
        "find_ports":   "ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null || echo 'не найдено'",
        "rnstatus":     f"{_RNS_BIN}/rnstatus",
        "restart_rnsd": "sudo systemctl restart rnsd && sleep 2 && systemctl is-active rnsd",
        "restart_lxmf": "sudo systemctl restart noema_lxmf_bridge && sleep 1 && systemctl is-active noema_lxmf_bridge",
        "restart_dash": "sudo systemctl restart dashboard",
        "free_mem":     "LC_ALL=C free -h",
        "disk":         "df -h /",
        "uptime":       "uptime",
        "rns_update":   f"{_RNS_BIN}/pip install --upgrade rns && echo OK",
    }
    cmd_id = (request.json or {}).get("cmd", "")
    if cmd_id not in allowed:
        return jsonify({"error": "unknown command"}), 400
    out, rc = sh(allowed[cmd_id])
    return jsonify({"output": out, "rc": rc})


import subprocess as _i2p_sp

def _i2p_running():
    out, _ = sh("systemctl is-active i2pd 2>/dev/null || echo inactive")
    return out.strip() == "active"

def _i2p_b32():
    try:
        import urllib.request
        r = urllib.request.urlopen("http://127.0.0.1:7070/?page=i2p_tunnels", timeout=3)
        html = r.read().decode()
        import re
        m = re.search(r'reticulum.*?([a-z2-7]{52}\.b32\.i2p)', html, re.DOTALL)
        if m: return m.group(1)
    except: pass
    return None

@app.route("/api/i2p/status")
def i2p_status():
    running = _i2p_running()
    b32 = _i2p_b32() if running else None
    return jsonify({"running": running, "b32_address": b32})

@app.route("/api/i2p/action", methods=["POST"])
def i2p_action():
    import time as _t
    action = (request.json or {}).get("action","")
    allowed = ["install","start","stop","restart","setup_tunnel"]
    if action not in allowed:
        return jsonify({"ok":False,"error":"unknown action"}), 400

    if action == "install":
        install_cmd = (
            "wget -q -O - https://repo.i2pd.xyz/.help/add_repo | sudo bash -s - 2>&1 && "
            "sudo apt-get update -qq 2>&1 && "
            "sudo apt-get install -y i2pd 2>&1"
        )
        out, rc = sh(install_cmd)
        if rc == 0:
            sh("sudo systemctl enable --now i2pd")
        return jsonify({"ok": rc==0, "output": out})

    elif action in ["start","stop","restart"]:
        out, rc = sh(f"sudo systemctl {action} i2pd 2>&1")
        _t.sleep(2)
        return jsonify({"ok": rc==0, "output": out or f"i2pd {action}ed"})

    elif action == "setup_tunnel":
        # Add tunnel to i2pd config
        tunnel_conf = """
[reticulum]
type = server
host = 127.0.0.1
port = 4242
keys = reticulum.dat
"""
        try:
            conf_paths = ["/var/lib/i2pd/tunnels.conf", "/etc/i2pd/tunnels.conf"]
            conf_path = None
            for p in conf_paths:
                if os.path.exists(p):
                    conf_path = p
                    break
            if not conf_path:
                conf_path = "/etc/i2pd/tunnels.conf"

            existing = open(conf_path).read() if os.path.exists(conf_path) else ""
            if "[reticulum]" not in existing:
                with open(conf_path, "a") as f:
                    f.write(tunnel_conf)

            subprocess.Popen("sudo systemctl stop i2pd && sleep 2 && sudo systemctl start i2pd", shell=True)
            _t.sleep(5)
            b32 = _i2p_b32()
            return jsonify({"ok": True, "output": f"Tunnel configured.\nAddress: {b32 or 'generating...'}", "b32_address": b32})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)})

    return jsonify({"ok": False, "error": "unknown"})

@app.route("/api/i2p/add_interface", methods=["POST"])
def i2p_add_interface():
    addr = (request.json or {}).get("addr","").strip()
    name = (request.json or {}).get("name","I2P-Node").strip()
    if not addr or ".b32.i2p" not in addr:
        return jsonify({"ok":False,"error":"invalid b32 address"})
    try:
        cfg_path = os.path.expanduser("~/.reticulum/config")
        cfg = open(cfg_path).read()
        if addr in cfg:
            return jsonify({"ok":False,"error":"address already in config"})
        import re
        # If I2PInterface block exists - add peer to it
        pattern = r"(\[\[I2P-Node\]\][^\[]*peers\s*=\s*)([^\n]+)"
        match = re.search(pattern, cfg)
        if match:
            current_peers = match.group(2).strip()
            new_peers = current_peers + ", " + addr
            cfg = cfg[:match.start(2)] + new_peers + cfg[match.end(2):]
        else:
            block = f"""
  [[{name}]]
    type = I2PInterface
    enabled = yes
    peers = {addr}
"""
            cfg += block
        open(cfg_path,"w").write(cfg)
        return jsonify({"ok":True})
    except Exception as e:
        return jsonify({"ok":False,"error":str(e)})

@app.route("/api/nomadnet/status")
def nomadnet_status():
    running, _ = sh("systemctl is-active nomadnet 2>/dev/null")
    # Try to get page address from nomadnet log
    addr = ""
    try:
        addr = open("/root/.nomadnetwork/node_address").read().strip()
        if not addr: raise ValueError
    except:
        try:
            import sys as _sys, glob as _glob
            _sp = _glob.glob(f"{_HOME}/NOEMA-RNSGate-Lite/.venv/lib/python*/site-packages")
            if _sp: _sys.path.insert(0, _sp[0])
            import RNS as _rns
            _rns.Reticulum(configdir=f"{_HOME}/.reticulum", loglevel=_rns.LOG_CRITICAL)
            _id = _rns.Identity.from_file(f"{_HOME}/.nomadnetwork/storage/identity")
            _dest = _rns.Destination(_id, _rns.Destination.IN, _rns.Destination.SINGLE, "nomadnetwork", "node")
            addr = _rns.hexrep(_dest.hash, delimit=False)
            open(f"{_HOME}/.nomadnetwork/node_address","w").write(addr)
        except: addr = ""
    return jsonify({"running": running.strip() == "active", "status": running.strip(), "page_addr": addr})

@app.route("/api/nomadnet/page")
def nomadnet_page_get():
    try:
        content = open(NOMADNET_PAGE).read()
        return jsonify({"content": content, "path": NOMADNET_PAGE})
    except:
        return jsonify({"content": "", "path": NOMADNET_PAGE})

@app.route("/api/nomadnet/page", methods=["POST"])
def nomadnet_page_save():
    content = (request.json or {}).get("content", "")
    try:
        os.makedirs(os.path.dirname(NOMADNET_PAGE), exist_ok=True)
        open(NOMADNET_PAGE, "w").write(content)
        sh("sudo systemctl restart nomadnet")
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

# Multi-page support
@app.route("/api/nomadnet/pages")
def nomadnet_pages_list():
    SYSTEM_PAGES = {"fullchat.mu", "last100.mu", "meshchat.mu", "nomadnet.mu"}
    try:
        files = [f for f in os.listdir(NOMADNET_PAGES_DIR) if f.endswith(".mu") and f not in SYSTEM_PAGES]
        return jsonify(sorted(files))
    except:
        return jsonify([])

@app.route("/api/nomadnet/pages/<name>")
def nomadnet_page_read(name):
    if not name.endswith(".mu") or "/" in name:
        return jsonify({"ok": False, "error": "Invalid name"})
    path = os.path.join(NOMADNET_PAGES_DIR, name)
    try:
        return jsonify({"content": open(path).read(), "path": path})
    except:
        return jsonify({"content": "", "path": path})

@app.route("/api/nomadnet/pages/<name>", methods=["POST"])
def nomadnet_page_save_named(name):
    if not name.endswith(".mu") or "/" in name:
        return jsonify({"ok": False, "error": "Invalid name"})
    content = (request.json or {}).get("content", "")
    path = os.path.join(NOMADNET_PAGES_DIR, name)
    try:
        os.makedirs(NOMADNET_PAGES_DIR, exist_ok=True)
        open(path, "w").write(content)
        sh("sudo systemctl restart nomadnet")
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route("/api/nomadnet/pages/<name>", methods=["DELETE"])
def nomadnet_page_delete(name):
    if not name.endswith(".mu") or "/" in name or name == "index.mu":
        return jsonify({"ok": False, "error": "Cannot delete"})
    path = os.path.join(NOMADNET_PAGES_DIR, name)
    try:
        os.remove(path)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

# Scripts support
@app.route("/api/scripts")
def scripts_list():
    try:
        os.makedirs(SCRIPTS_DIR, exist_ok=True)
        files = [f for f in os.listdir(SCRIPTS_DIR) if f.endswith(".py")]
        return jsonify(sorted(files))
    except:
        return jsonify([])

@app.route("/api/scripts/<name>")
def script_read(name):
    if not name.endswith(".py") or "/" in name:
        return jsonify({"ok": False, "error": "Invalid name"})
    path = os.path.join(SCRIPTS_DIR, name)
    try:
        return jsonify({"content": open(path).read(), "path": path})
    except:
        return jsonify({"content": "", "path": path})

@app.route("/api/scripts/<name>", methods=["POST"])
def script_save(name):
    if not name.endswith(".py") or "/" in name:
        return jsonify({"ok": False, "error": "Invalid name"})
    content = (request.json or {}).get("content", "")
    path = os.path.join(SCRIPTS_DIR, name)
    try:
        os.makedirs(SCRIPTS_DIR, exist_ok=True)
        open(path, "w").write(content)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route("/api/scripts/<name>", methods=["DELETE"])
def script_delete(name):
    if not name.endswith(".py") or "/" in name:
        return jsonify({"ok": False, "error": "Invalid name"})
    path = os.path.join(SCRIPTS_DIR, name)
    try:
        os.remove(path)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route("/api/scripts/<name>/run", methods=["POST"])
def script_run(name):
    if not name.endswith(".py") or "/" in name:
        return jsonify({"ok": False, "error": "Invalid name"})
    path = os.path.join(SCRIPTS_DIR, name)
    try:
        venv_python = f"{_HOME}/NOEMA-RNSGate-Lite/.venv/bin/python3"
        out, rc = sh(f"{venv_python} {path} 2>&1")
        return jsonify({"ok": rc == 0, "output": out})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route("/api/scripts/<name>/cron")
def script_cron_get(name):
    if not name.endswith(".py") or "/" in name:
        return jsonify({"ok": False, "error": "Invalid name"})
    path = os.path.join(SCRIPTS_DIR, name)
    try:
        venv_python = f"{_HOME}/NOEMA-RNSGate-Lite/.venv/bin/python3"
        crontab_out, _ = sh("crontab -l 2>/dev/null")
        marker = f"# noema-script:{name}"
        schedule = None
        for line in crontab_out.splitlines():
            if marker in line and not line.strip().startswith("#"):
                parts = line.split()
                schedule = " ".join(parts[:5])
                break
        return jsonify({"ok": True, "schedule": schedule, "enabled": schedule is not None})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route("/api/scripts/<name>/cron", methods=["POST"])
def script_cron_set(name):
    if not name.endswith(".py") or "/" in name:
        return jsonify({"ok": False, "error": "Invalid name"})
    path = os.path.join(SCRIPTS_DIR, name)
    data = request.json or {}
    schedule = data.get("schedule")  # None = disable
    try:
        venv_python = f"{_HOME}/NOEMA-RNSGate-Lite/.venv/bin/python3"
        marker = f"# noema-script:{name}"
        crontab_out, _ = sh("crontab -l 2>/dev/null")
        lines = [l for l in crontab_out.splitlines() if marker not in l]
        if schedule:
            lines.append(f"{schedule} {venv_python} {path} >> /tmp/{name}.log 2>&1 {marker}")
        new_crontab = "\n".join(lines) + "\n"
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cron', delete=False) as f:
            f.write(new_crontab)
            tmp = f.name
        sh(f"crontab {tmp}")
        os.unlink(tmp)
        return jsonify({"ok": True, "schedule": schedule, "enabled": schedule is not None})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


def version(): return jsonify({"version": __version__})
@app.route("/api/rns_update_check")
def rns_update_check():
    import urllib.request, json as _json
    def get_ver(mod):
        v,_ = sh(f"{_RNS_BIN}/python3 -c 'import {mod}; print({mod}.__version__)' 2>/dev/null")
        return (v or "").strip() or "—"
    def get_pypi(pkg):
        try:
            with urllib.request.urlopen(f"https://pypi.org/pypi/{pkg}/json", timeout=5) as r:
                return _json.loads(r.read())["info"]["version"]
        except: return "—"
    try:
        py_ver,_ = sh(f"{_RNS_BIN}/python3 --version 2>&1")
        rns_cur   = get_ver("RNS")
        lxmf_cur  = get_ver("LXMF")
        lxmfy_cur = get_ver("lxmfy")
        nomad_ver,_ = sh(f"{_RNS_BIN}/python3 -c 'from nomadnet._version import __version__; print(__version__)' 2>/dev/null")
        nomad_cur = (nomad_ver or "").strip() or "\u2014"
        flask_cur = get_ver("flask")
        mqtt_ver,_ = sh(f"{_RNS_BIN}/python3 -c 'import paho.mqtt; print(paho.mqtt.__version__)' 2>/dev/null")
        mqtt_cur  = (mqtt_ver or "").strip() or "—"
        rns_lat   = get_pypi("rns")
        lxmf_lat  = get_pypi("lxmf")
        lxmfy_lat = get_pypi("lxmfy")
        nomad_lat = get_pypi("nomadnet")
        mqtt_lat  = get_pypi("paho-mqtt")
        return jsonify({
            "current": rns_cur, "latest": rns_lat, "update_available": rns_cur != rns_lat,
            "python": py_ver.replace("Python ","").strip(),
            "components": [
                {"name": "RNS",       "pkg": "rns",       "installed": rns_cur,   "latest": rns_lat},
                {"name": "LXMF",      "pkg": "lxmf",      "installed": lxmf_cur,  "latest": lxmf_lat},
                {"name": "lxmfy",     "pkg": "lxmfy",     "installed": lxmfy_cur, "latest": lxmfy_lat},
                {"name": "nomadnet",  "pkg": "nomadnet",  "installed": nomad_cur, "latest": nomad_lat},
                {"name": "paho-mqtt", "pkg": "paho-mqtt", "installed": mqtt_cur,  "latest": mqtt_lat},
                {"name": "Flask",     "pkg": "flask",     "installed": flask_cur,  "latest": "—"},
            ]
        })
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/api/rns_update", methods=["POST"])
def rns_update():
    pkg = (request.json or {}).get("package", "rns")
    allowed = ["rns","lxmf","lxmfy","nomadnet","paho-mqtt","flask","waitress"]
    if pkg not in allowed:
        return jsonify({"ok": False, "error": "not allowed"})
    out, rc = sh(f"{_RNS_BIN}/pip install --upgrade {pkg} 2>&1")
    return jsonify({"ok": rc==0, "output": out})


@app.route("/api/rns_config_parsed")
def rns_config_parsed():
    import re, configparser
    cfg_path = os.path.expanduser("~/.reticulum/config")
    try:
        raw = open(cfg_path).read()
    except:
        return jsonify({"error": "config not found"})

    result = {"reticulum": {}, "interfaces": []}

    # Parse [reticulum] section
    rns_match = re.search(r'^\[reticulum\](.*?)(?=^\[|\Z)', raw, re.M | re.S)
    if rns_match:
        for line in rns_match.group(1).splitlines():
            m = re.match(r'\s*(\w+)\s*=\s*(.+)', line)
            if m:
                result["reticulum"][m.group(1).strip()] = m.group(2).strip()

    # Parse [[interfaces]]
    iface_blocks = re.findall(r'  \[\[(.+?)\]\](.*?)(?=  \[\[|\Z)', raw, re.S)
    for name, body in iface_blocks:
        iface = {"name": name.strip(), "params": {}}
        for line in body.splitlines():
            m = re.match(r'\s+(\w+)\s*=\s*(.+)', line)
            if m:
                iface["params"][m.group(1).strip()] = m.group(2).strip()
        result["interfaces"].append(iface)

    return jsonify(result)

@app.route("/api/rns_config_save", methods=["POST"])
def rns_config_save():
    import re
    data = request.json or {}
    cfg_path = os.path.expanduser("~/.reticulum/config")
    try:
        rns_section = data.get("reticulum", {})
        interfaces = data.get("interfaces", [])

        lines = ["[reticulum]"]
        for k, v in rns_section.items():
            lines.append(f"  {k} = {v}")
        lines.append("")
        lines.append("[interfaces]")
        for iface in interfaces:
            lines.append(f"  [[{iface['name']}]]")
            for k, v in iface.get("params", {}).items():
                lines.append(f"    {k} = {v}")
            lines.append("")

        # Backup
        import shutil, time as _t
        shutil.copy2(cfg_path, cfg_path + f".bak.{int(_t.time())}")

        open(cfg_path, "w").write("\n".join(lines))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route("/api/rns_iface_delete", methods=["POST"])
def rns_iface_delete():
    name = (request.json or {}).get("name", "")
    if not name:
        return jsonify({"ok": False, "error": "no name"})
    import re
    cfg_path = os.path.expanduser("~/.reticulum/config")
    try:
        raw = open(cfg_path).read()
        # Remove interface block
        pattern = rf'  \[\[{re.escape(name)}\]\][^\[]*'
        new_cfg = re.sub(pattern, '', raw)
        import shutil, time as _t
        shutil.copy2(cfg_path, cfg_path + f".bak.{int(_t.time())}")
        open(cfg_path, "w").write(new_cfg)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route("/api/reset_identity", methods=["POST"])
def reset_identity():
    import shutil, time as _t, subprocess as _sp
    try:
        # Remove LXMF chat identity
        chat_lxmf = os.path.join(_HOME, "dashboard/chat_lxmf")
        if os.path.exists(chat_lxmf):
            shutil.rmtree(chat_lxmf)
        # Remove chat history and contacts
        for f in ["dashboard/chat_history.json", "dashboard/chat_contacts.json",
                  "dashboard/chat_files_meta.json"]:
            p = os.path.join(_HOME, f)
            if os.path.exists(p): os.remove(p)
        chat_files = os.path.join(_HOME, "dashboard/chat_files")
        if os.path.exists(chat_files):
            shutil.rmtree(chat_files)
        # Remove Reticulum identity/storage
        rns_storage = os.path.join(_HOME, ".reticulum/storage")
        if os.path.exists(rns_storage):
            shutil.rmtree(rns_storage)
        # Remove lxmf-tools identity
        for f in ["lxmf-tools/identity", "lxmf-tools/lxmf_address"]:
            p = os.path.join(_HOME, f)
            if os.path.exists(p): os.remove(p)
        # Remove group chat identity

        # Remove Nomadnet identity (keep pages)
        nn_storage = os.path.join(_HOME, ".nomadnetwork/storage")
        nn_addr = os.path.join(_HOME, ".nomadnetwork/node_address")
        if os.path.exists(nn_storage):
            for item in os.listdir(nn_storage):
                if item != "pages":
                    p = os.path.join(nn_storage, item)
                    shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
        if os.path.exists(nn_addr): os.remove(nn_addr)
        # Remove I2P tunnel keys
        for p in ["/etc/i2pd/tunnels.d/reticulum.dat",
                  "/var/lib/i2pd/reticulum.dat"]:
            if os.path.exists(p):
                sh(f"sudo rm -f {p}")
        # Recalculate nomadnet address after restart
        def _recalc_nn():
            import time as _time
            id_file = f"{_HOME}/.nomadnetwork/storage/identity"
            for _ in range(30):
                _time.sleep(2)
                if os.path.exists(id_file):
                    break
            try:
                import RNS as _rns
                _rns.Reticulum(configdir=f"{_HOME}/.reticulum", loglevel=_rns.LOG_CRITICAL)
                _id = _rns.Identity.from_file(id_file)
                _dest = _rns.Destination(_id, _rns.Destination.IN, _rns.Destination.SINGLE, "nomadnetwork", "node")
                addr = _rns.hexrep(_dest.hash, delimit=False)
                open(f"{_HOME}/.nomadnetwork/node_address","w").write(addr)
            except: pass
        import threading as _thr
        _thr.Thread(target=_recalc_nn, daemon=True).start()
        # Restart all services in background - dashboard last
        _sp.Popen(f"sleep 1 && sudo systemctl restart i2pd rnsd noema_lxmf_bridge nomadnet && sleep 8 && {_HOME}/NOEMA-RNSGate-Lite/.venv/bin/python3 {_HOME}/NOEMA-RNSGate/recalc_nn_addr.py && sleep 2 && sudo systemctl restart dashboard", shell=True)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/<path:filename>")
def static_files(filename): return send_from_directory(".", filename)

@app.route("/")
def index(): return send_from_directory(".", "index.html")

if __name__ == "__main__":
    print("▶ http://0.0.0.0:8081")
    app.run(host="0.0.0.0", port=8081, threaded=True)
