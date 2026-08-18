#!/usr/bin/env python3
__version__ = "1.4.2"
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
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
    out = (r.stdout + r.stderr).strip()
    return out, r.returncode

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

@app.route("/api/chat/settings", methods=["POST"])
def chat_settings():
    data = request.json or {}
    max_msgs = int(data.get("max_msgs", 200))
    max_files_mb = int(data.get("max_files_mb", 50))
    # Apply message limit
    with _chat_lock:
        try:
            hist = _chat_json.load(open(CHAT_FILE))
            for addr in hist:
                hist[addr] = hist[addr][-max_msgs:]
            _chat_json.dump(hist, open(CHAT_FILE, "w"))
        except: pass
    # Apply file limit
    try:
        _chat_cleanup_files(max_mb=max_files_mb)
    except: pass
    return jsonify({"ok": True})

@app.route("/api/chat/cleanup", methods=["POST"])
def chat_cleanup():
    import glob as _g
    max_mb = int((request.json or {}).get("max_files_mb", 50))
    before = sum(os.path.getsize(f) for f in _g.glob(os.path.join(CHAT_FILES_DIR, "*")) if os.path.isfile(f))
    try:
        _chat_cleanup_files(max_mb=max_mb)
    except: pass
    after = sum(os.path.getsize(f) for f in _g.glob(os.path.join(CHAT_FILES_DIR, "*")) if os.path.isfile(f))
    return jsonify({"ok": True, "freed": max(0, before - after)})

@app.route("/api/chat/history/clear", methods=["POST"])
def chat_history_clear():
    import time as _t
    days = (request.json or {}).get("days", 0)
    cutoff = int(_t.time()) - days * 86400 if days > 0 else 0
    with _chat_lock:
        try:
            try:
                data = _chat_json.load(open(CHAT_FILE, encoding="utf-8"))
            except:
                data = {}
            deleted = 0
            removed_fids = set()
            for addr in data:
                before = len(data[addr])
                if cutoff > 0:
                    kept = [m for m in data[addr] if m.get("ts", 0) >= cutoff]
                    removed = [m for m in data[addr] if m.get("ts", 0) < cutoff]
                    data[addr] = kept
                else:
                    removed = data[addr]
                    data[addr] = []
                deleted += before - len(data[addr])
                for m in removed:
                    if m.get("file_id"):
                        removed_fids.add(m["file_id"])
            _chat_json.dump(data, open(CHAT_FILE, "w", encoding="utf-8"), ensure_ascii=False)
            # Remove orphaned files
            meta = _files_get_meta()
            new_meta = []
            for m in meta:
                if m.get("id") in removed_fids:
                    try: os.remove(os.path.join(CHAT_FILES_DIR, m["id"]))
                    except: pass
                else:
                    new_meta.append(m)
            _files_save_meta(new_meta)
            return jsonify({"ok": True, "deleted": deleted})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

@app.route("/api/backup/download")
def backup_download():
    import zipfile, io, time as _t, glob as _g
    buf = io.BytesIO()

    single_files = {
        "configs/reticulum.cfg":       f"{_HOME}/.reticulum/config",
        "configs/noema_bridge.cfg":    "/etc/noema/bridge.cfg",
        "configs/nomadnet.cfg":        f"{_HOME}/.nomadnetwork/config",
        "identity/lxmf_identity":      f"{_HOME}/lxmf-tools/identity",
        "identity/reticulum_identity": f"{_HOME}/.reticulum/storage/identity",
        "identity/i2p_keys":           "/var/lib/i2pd/router.keys",
        "data/monitored_nodes.json":   f"{_HOME}/dashboard/monitored_nodes.json",
        "data/nomadnet_hashes":        NOMADNET_ADDR_FILE,
    }

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for arcname, path in single_files.items():
            try:
                zf.write(path, arcname)
            except: pass

        for p in _g.glob(f"{NOMADNET_PAGES_DIR}/*.mu"):
            try: zf.write(p, f"pages/{os.path.basename(p)}")
            except: pass

        # Nomadnet chat data
        for fname in ["chat_log.json", "topic.json", "emoticons.txt", "emoticon.txt", "chatusers.db"]:
            p = os.path.join(NOMADNET_PAGES_DIR, fname)
            if os.path.exists(p):
                try: zf.write(p, f"pages/{fname}")
                except: pass

        for p in _g.glob(f"{SCRIPTS_DIR}/*.py") + _g.glob(f"{SCRIPTS_DIR}/*.sh"):
            try: zf.write(p, f"scripts/{os.path.basename(p)}")
            except: pass

        for p in _g.glob("/etc/i2pd/tunnels.conf") + _g.glob("/etc/i2pd/tunnels.d/*.conf"):
            try: zf.write(p, f"configs/i2p/{os.path.basename(p)}")
            except: pass

        rns_dest = f"{_HOME}/.reticulum/storage/destinations"
        for p in _g.glob(f"{rns_dest}/*"):
            try:
                if os.path.isfile(p):
                    zf.write(p, f"identity/rns_destinations/{os.path.basename(p)}")
            except: pass

        # Nomadnet identity and node_address
        nn_identity = os.path.join(_HOME, ".nomadnetwork/storage/identity")
        if os.path.exists(nn_identity):
            try: zf.write(nn_identity, "identity/nomadnet_identity")
            except: pass
        nn_addr = os.path.join(_HOME, ".nomadnetwork/node_address")
        if os.path.exists(nn_addr):
            try: zf.write(nn_addr, "identity/nomadnet_node_address")
            except: pass

        # Chat LXMF identity directory
        chat_lxmf_dir = os.path.join(_HOME, "dashboard/chat_lxmf")
        for p in _g.glob(f"{chat_lxmf_dir}/**/*", recursive=True) + _g.glob(f"{chat_lxmf_dir}/*"):
            try:
                if os.path.isfile(p):
                    rel = os.path.relpath(p, os.path.join(_HOME, "dashboard"))
                    zf.write(p, f"identity/chat_lxmf/{os.path.relpath(p, chat_lxmf_dir)}")
            except: pass

        # I2P tunnel key (reticulum.dat)
        for p in ["/var/lib/i2pd/reticulum.dat", "/etc/i2pd/tunnels.d/reticulum.dat"]:
            if os.path.exists(p):
                try: zf.write(p, "identity/i2p_tunnel.dat")
                except: pass
                break

        # Chat history, contacts, files meta
        for key, path in [
            ("data/chat_history.json",      f"{_HOME}/dashboard/chat_history.json"),
            ("data/chat_contacts.json",     f"{_HOME}/dashboard/chat_contacts.json"),
            ("data/chat_files_meta.json",   f"{_HOME}/dashboard/chat_files_meta.json"),
        ]:
            try: zf.write(path, key)
            except: pass

        # Chat files
        chat_files_dir = os.path.join(_HOME, "dashboard/chat_files")
        for p in _g.glob(f"{chat_files_dir}/*"):
            try:
                if os.path.isfile(p):
                    zf.write(p, f"data/chat_files/{os.path.basename(p)}")
            except: pass

    buf.seek(0)
    from flask import send_file
    ts = _t.strftime("%Y%m%d_%H%M%S")
    return send_file(buf, mimetype="application/zip",
                     as_attachment=True,
                     download_name=f"noema_backup_{ts}.zip")

@app.route("/api/backup/restore", methods=["POST"])
def backup_restore():
    import zipfile, io
    f = request.files.get("file")
    if not f: return jsonify({"error": "no file"}), 400

    single_restore = {
        "configs/reticulum.cfg":       f"{_HOME}/.reticulum/config",
        "configs/noema_bridge.cfg":    "/etc/noema/bridge.cfg",
        "configs/nomadnet.cfg":        f"{_HOME}/.nomadnetwork/config",
        "identity/lxmf_identity":      f"{_HOME}/lxmf-tools/identity",
        "identity/reticulum_identity": f"{_HOME}/.reticulum/storage/identity",
        "data/monitored_nodes.json":   f"{_HOME}/dashboard/monitored_nodes.json",
        "data/nomadnet_hashes":        NOMADNET_ADDR_FILE,
        # legacy keys from old backups
        "reticulum_config":            f"{_HOME}/.reticulum/config",
        "noema_bridge.cfg":            "/etc/noema/bridge.cfg",
        "monitored_nodes.json":        f"{_HOME}/dashboard/monitored_nodes.json",
    }

    try:
        with zipfile.ZipFile(io.BytesIO(f.read())) as zf:
            names = zf.namelist()

            # Single files
            for arcname, path in single_restore.items():
                if arcname in names:
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    open(path, "wb").write(zf.read(arcname))

            # Pages
            os.makedirs(NOMADNET_PAGES_DIR, exist_ok=True)
            for n in names:
                if n.startswith("pages/") and (n.endswith(".mu") or
                        os.path.basename(n) in {"chat_log.json","topic.json","emoticons.txt","emoticon.txt","chatusers.db"}):
                    fname = os.path.basename(n)
                    if fname:
                        open(os.path.join(NOMADNET_PAGES_DIR, fname), "wb").write(zf.read(n))

            # Scripts
            os.makedirs(SCRIPTS_DIR, exist_ok=True)
            for n in names:
                if n.startswith("scripts/") and (n.endswith(".py") or n.endswith(".sh")):
                    fname = os.path.basename(n)
                    if fname:
                        open(os.path.join(SCRIPTS_DIR, fname), "wb").write(zf.read(n))

            # RNS destinations
            rns_dest = f"{_HOME}/.reticulum/storage/destinations"
            os.makedirs(rns_dest, exist_ok=True)
            for n in names:
                if n.startswith("identity/rns_destinations/"):
                    fname = os.path.basename(n)
                    if fname:
                        open(os.path.join(rns_dest, fname), "wb").write(zf.read(n))

            # Nomadnet identity
            if "identity/nomadnet_identity" in names:
                nn_id_path = os.path.join(_HOME, ".nomadnetwork/storage/identity")
                os.makedirs(os.path.dirname(nn_id_path), exist_ok=True)
                data = zf.read("identity/nomadnet_identity")
                if data:  # Only write if not empty
                    open(nn_id_path, "wb").write(data)
                    # Recalculate nomadnet address from restored identity
                    try:
                        import subprocess as _sp_nn
                        _venv = os.path.join(_HOME, "NOEMA-RNSGate-Lite/.venv/bin/python3")
                        _script = os.path.join(_HOME, "NOEMA-RNSGate-Lite/recalc_nn_addr.py")
                        if os.path.exists(_venv) and os.path.exists(_script):
                            _sp_nn.run([_venv, _script], timeout=30, capture_output=True)
                    except: pass

            # Chat LXMF identity
            chat_lxmf_dir = os.path.join(_HOME, "dashboard/chat_lxmf")
            for n in names:
                if n.startswith("identity/chat_lxmf/"):
                    fname = n[len("identity/chat_lxmf/"):]
                    if fname:
                        p = os.path.join(chat_lxmf_dir, fname)
                        os.makedirs(os.path.dirname(p), exist_ok=True)
                        open(p, "wb").write(zf.read(n))

            # I2P tunnel key — stop i2pd first to prevent key regeneration
            if "identity/i2p_tunnel.dat" in names:
                import subprocess as _sp_i2p
                _sp_i2p.run("systemctl stop i2pd", shell=True, capture_output=True)
                import time as _t_i2p; _t_i2p.sleep(1)
                for dest in ["/var/lib/i2pd/reticulum.dat", "/etc/i2pd/tunnels.d/reticulum.dat"]:
                    try:
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        open(dest, "wb").write(zf.read("identity/i2p_tunnel.dat"))
                        break
                    except: pass

            # Chat history, contacts, files meta
            chat_restore = {
                "data/chat_history.json":    f"{_HOME}/dashboard/chat_history.json",
                "data/chat_contacts.json":   f"{_HOME}/dashboard/chat_contacts.json",
                "data/chat_files_meta.json": f"{_HOME}/dashboard/chat_files_meta.json",
            }
            for arcname, path in chat_restore.items():
                if arcname in names:
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    open(path, "wb").write(zf.read(arcname))

            # Chat files
            chat_files_dir = os.path.join(_HOME, "dashboard/chat_files")
            os.makedirs(chat_files_dir, exist_ok=True)
            for n in names:
                if n.startswith("data/chat_files/"):
                    fname = os.path.basename(n)
                    if fname:
                        open(os.path.join(chat_files_dir, fname), "wb").write(zf.read(n))

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

def _load_chat_access():
    import configparser as _cp5
    parser = _cp5.ConfigParser()
    parser.read("/etc/noema/bridge.cfg")
    enabled = parser.get("chat_access", "enabled", fallback="0") == "1"
    wl = set(x.strip() for x in parser.get("chat_access", "whitelist", fallback="").split(",") if x.strip())
    return enabled, wl

_chat_access_enabled, _chat_access_whitelist = _load_chat_access()

# ─── Deduplication ───────────────────────────────────────────────────────────
# Same LXMF message can arrive more than once over multiple paths/retransmits.

_chat_dedup_lock = threading.Lock()
_chat_seen_messages = {}  # message_id -> first_seen_timestamp
_CHAT_DEDUP_TTL = 3600  # 1 hour

def _chat_is_duplicate(message, src):
    import time as _t_dedup
    msg_id = None
    try:
        if hasattr(message, "hash") and message.hash:
            msg_id = message.hash.hex() if isinstance(message.hash, (bytes, bytearray)) else str(message.hash)
    except Exception:
        msg_id = None
    if not msg_id:
        try:
            import hashlib
            raw = f"{src}|{message.content}|{message.timestamp}".encode("utf-8", errors="replace")
            msg_id = hashlib.sha256(raw).hexdigest()
        except Exception:
            return False
    now = _t_dedup.time()
    with _chat_dedup_lock:
        expired = [k for k, t in _chat_seen_messages.items() if now - t > _CHAT_DEDUP_TTL]
        for k in expired:
            del _chat_seen_messages[k]
        if msg_id in _chat_seen_messages:
            return True
        _chat_seen_messages[msg_id] = now
        return False
CONTACTS_FILE = f"{_HOME}/dashboard/chat_contacts.json"

_chat_lock = _chat_th.Lock()
_chat_router = None
_chat_identity = None
_chat_dest = None
_chat_incoming = deque(maxlen=500)

CHAT_STORAGE = f"{_HOME}/dashboard/chat_lxmf"

def _chat_init():
    global _chat_router, _chat_identity, _chat_dest
    if _chat_router is not None:
        return  # Already initialized
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
    try:
        dest = router.register_delivery_identity(identity, display_name="NOEMA Chat")
    except Exception as _reg_e:
        if "already registered" in str(_reg_e).lower():
            # Get existing destination
            dest_hash = RNS.Destination.hash(identity, "lxmf", "delivery")
            dest = RNS.Destination(identity, RNS.Destination.IN, RNS.Destination.SINGLE, "lxmf", "delivery")
        else:
            raise
    router.register_delivery_callback(_chat_on_receive)
    router.announce(destination_hash=dest.hash)
    _chat_router = router
    _chat_dest = dest
    # Save address to file for persistent access
    try:
        addr_str = RNS.hexrep(dest.hash, delimit=False)
        open(f"{CHAT_STORAGE}/address", "w").write(addr_str)
    except: pass

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
        if _chat_access_enabled and src not in _chat_access_whitelist:
            print(f"[CHAT ACCESS] Blocked message from {src} (not whitelisted)")
            return
        if _chat_is_duplicate(message, src):
            print(f"[CHAT DEDUP] Dropped duplicate message from {src}")
            return
        text = message.content.decode("utf-8") if isinstance(message.content, bytes) else str(message.content)
        ts = int(_t.time())
        msg = {"ts": ts, "from": src, "to": "me", "text": text, "direction": "in"}

        # Extract file attachment from LXMF fields
        try:
            fields = message.fields or {}
            fname = None
            fdata = None

            # LXMF field 0x05 = file attachments [[name, data], ...]
            att_data = fields.get(0x05)
            if att_data and isinstance(att_data, list) and len(att_data) > 0:
                att = att_data[0]
                if isinstance(att, list) and len(att) >= 2:
                    fname = str(att[0]) if att[0] else "file"
                    fdata = att[1] if isinstance(att[1], bytes) else None

            # LXMF field 0x06 = image container [format, data] — used by some clients (e.g. Columba)
            if fdata is None:
                img_data = fields.get(0x06)
                if img_data and isinstance(img_data, list) and len(img_data) >= 2:
                    img_fmt = str(img_data[0]) if img_data[0] else "webp"
                    img_bytes = img_data[1] if isinstance(img_data[1], bytes) else None
                    if img_bytes:
                        fname = f"image.{img_fmt}"
                        fdata = img_bytes

            if fdata:
                fid = str(_uid.uuid4())
                fpath = os.path.join(CHAT_FILES_DIR, fid)
                open(fpath, "wb").write(fdata)
                # Detect mime from data signature
                mime = _mt.guess_type(fname)[0] or "application/octet-stream"
                if fdata[:8] == b"\x89PNG\r\n\x1a\n": mime = "image/png"
                elif fdata[:3] == b"\xff\xd8\xff": mime = "image/jpeg"
                elif fdata[:6] in (b"GIF87a", b"GIF89a"): mime = "image/gif"
                elif fdata[:4] == b"RIFF" and fdata[8:12] == b"WEBP": mime = "image/webp"
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
        # Telegram notification for chat messages
        try:
            name = msg.get("from_name") or src[:16]
            text = msg.get("text","")[:200]
            _tg_send(f"💬 <b>NOEMA Chat</b>\nОт: <code>{name}</code>\n{text}")
        except: pass
    except: pass

def _load_chat_history(addr):
    try:
        data = _chat_json.load(open(CHAT_FILE))
        return data.get(addr, [])
    except:
        return []

def _save_chat_msg(addr, msg):
    if not msg.get('text') and not msg.get('file_id'):
        return  # skip empty
    with _chat_lock:
        try:
            try:
                data = _chat_json.load(open(CHAT_FILE, encoding="utf-8"))
            except:
                data = {}
            if addr not in data:
                data[addr] = []
            data[addr].append(msg)
            data[addr] = data[addr][-200:]
            _chat_json.dump(data, open(CHAT_FILE, "w", encoding="utf-8"), ensure_ascii=False)
        except: pass
    # Cleanup chat files if folder exceeds 50MB
    try:
        _chat_cleanup_files(max_mb=50)
    except: pass

def _chat_cleanup_files(max_mb=50):
    import glob as _g
    max_bytes = max_mb * 1024 * 1024
    files = sorted(
        [f for f in _g.glob(os.path.join(CHAT_FILES_DIR, "*")) if os.path.isfile(f)],
        key=os.path.getmtime
    )
    total = sum(os.path.getsize(f) for f in files)
    removed_ids = set()
    while total > max_bytes and files:
        oldest = files.pop(0)
        size = os.path.getsize(oldest)
        os.remove(oldest)
        total -= size
        fid = os.path.basename(oldest)
        removed_ids.add(fid)
        try:
            meta = _files_get_meta()
            meta = [m for m in meta if m.get("id") != fid]
            _files_save_meta(meta)
        except: pass
    # Remove orphaned file references from chat history
    if removed_ids:
        with _chat_lock:
            try:
                data = _chat_json.load(open(CHAT_FILE))
                for addr in data:
                    data[addr] = [m for m in data[addr] if m.get("file_id") not in removed_ids]
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

@app.route("/api/chat/history/<addr>/delete", methods=["POST"])
def chat_history_delete(addr):
    with _chat_lock:
        try:
            try:
                data = _chat_json.load(open(CHAT_FILE, encoding="utf-8"))
            except:
                data = {}
            msgs = data.pop(addr, [])
            _chat_json.dump(data, open(CHAT_FILE, "w", encoding="utf-8"), ensure_ascii=False)
            # Remove files from this contact
            fids = {m["file_id"] for m in msgs if m.get("file_id")}
            if fids:
                meta = _files_get_meta()
                new_meta = []
                for m in meta:
                    if m.get("id") in fids:
                        try: os.remove(os.path.join(CHAT_FILES_DIR, m["id"]))
                        except: pass
                    else:
                        new_meta.append(m)
                _files_save_meta(new_meta)
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

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


def _tg_send(text):
    """Send Telegram notification using settings from bridge.cfg"""
    try:
        import configparser as _cp2, urllib.request as _ur, urllib.parse as _up
        _c = _cp2.ConfigParser()
        _c.read("/etc/noema/bridge.cfg")
        if not _c.has_section("telegram"):
            return
        token   = _c["telegram"].get("bot_token","").strip()
        chat_id = _c["telegram"].get("chat_id","").strip()
        notify_chat = _c["telegram"].get("notify_chat","1").strip()
        if not token or not chat_id or notify_chat == "0":
            return
        url  = f"https://api.telegram.org/bot{token}/sendMessage"
        data = _up.urlencode({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
        _ur.urlopen(url, data, timeout=8)
    except Exception as e:
        print(f"[TG] Error: {e}")

@app.route("/api/telegram/settings", methods=["GET","POST"])
def telegram_settings():
    import configparser as _cp
    cfg_path = "/etc/noema/bridge.cfg"
    parser = _cp.ConfigParser()
    parser.read(cfg_path)
    if request.method == "POST":
        data = request.json or {}
        if not parser.has_section("telegram"):
            parser.add_section("telegram")
        # Don't overwrite token/chat_id if not provided
        if data.get("bot_token","").strip():
            parser.set("telegram", "bot_token", data["bot_token"].strip())
        if data.get("chat_id","").strip():
            parser.set("telegram", "chat_id", data["chat_id"].strip())
        parser.set("telegram", "notify_bridge","1" if data.get("notify_bridge",True) else "0")
        parser.set("telegram", "notify_chat",  "1" if data.get("notify_chat",True)   else "0")
        with open(cfg_path, "w") as f:
            parser.write(f)
        import subprocess as _sp2
        _sp2.run("systemctl restart noema_lxmf_bridge", shell=True)
        return jsonify({"ok": True})
    token   = parser.get("telegram","bot_token",fallback="") if parser.has_section("telegram") else ""
    chat_id = parser.get("telegram","chat_id",fallback="")   if parser.has_section("telegram") else ""
    notify_bridge = parser.get("telegram","notify_bridge",fallback="1") if parser.has_section("telegram") else "1"
    notify_chat   = parser.get("telegram","notify_chat",fallback="1")   if parser.has_section("telegram") else "1"
    return jsonify({"bot_token": token, "chat_id": chat_id, "enabled": bool(token and chat_id),
                    "notify_bridge": notify_bridge=="1", "notify_chat": notify_chat=="1"})

@app.route("/api/git_status")
def git_status():
    try:
        install_dir = os.path.join(_HOME, "NOEMA-RNSGate-Lite")
        subprocess.run("git fetch origin", shell=True, cwd=install_dir, capture_output=True, timeout=10)
        r = subprocess.run("git rev-list HEAD..origin/main --count", shell=True, cwd=install_dir, capture_output=True, text=True, timeout=5)
        behind = int(r.stdout.strip() or 0)
        h = subprocess.run("git rev-parse --short HEAD", shell=True, cwd=install_dir, capture_output=True, text=True, timeout=5)
        commit = h.stdout.strip()
        return jsonify({"behind": behind, "commit": commit, "update_available": behind > 0})
    except Exception as e:
        return jsonify({"behind": 0, "commit": "unknown", "update_available": False, "error": str(e)})

@app.route("/api/run", methods=["POST"])
def run_command():
    allowed = {
        "find_ports":      "ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null || echo 'не найдено'",
        "rnstatus":        f"{_RNS_BIN}/rnstatus",
        "restart_rnsd":    "sudo systemctl restart rnsd && sleep 2 && systemctl is-active rnsd",
        "restart_lxmf":    "sudo systemctl restart noema_lxmf_bridge && sleep 1 && systemctl is-active noema_lxmf_bridge",
        "restart_dash":    None,  # handled separately
        "free_mem":        "LC_ALL=C free -h",
        "disk":            "df -h /",
        "uptime":          "uptime",
        "rns_update":      f"{_RNS_BIN}/pip install --upgrade rns && echo OK",
        "noema_update":    (
            f"cd {_HOME}/NOEMA-RNSGate-Lite && git fetch origin 2>&1 && git checkout dashboard/index.html dashboard/app.py lxmf-tools/noema_lxmf_bridge.py 2>&1; git pull 2>&1 && "
            f"{_HOME}/NOEMA-RNSGate-Lite/.venv/bin/pip install --upgrade rns lxmf lxmfy flask paho-mqtt nomadnet -q 2>&1 && "
            "sudo systemctl restart dashboard noema_lxmf_bridge rnsd && "
            "sleep 3 && systemctl is-active dashboard noema_lxmf_bridge rnsd"
        ),
        "log_cleanup":     (
            "journalctl --vacuum-size=50M 2>&1 && "
            "rm -rf /var/log/i2pd/* && "
            "truncate -s 0 /var/log/syslog 2>/dev/null; "
            "truncate -s 0 /var/log/kern.log 2>/dev/null; "
            "truncate -s 0 /var/log/dmesg 2>/dev/null; "
            "apt clean -y 2>/dev/null; "
            "mkdir -p /etc/systemd/journald.conf.d && "
            "printf '[Journal]\\nSystemMaxUse=100M\\n' > /etc/systemd/journald.conf.d/size.conf && "
            "systemctl restart systemd-journald && "
            "mkdir -p /etc/logrotate.d && "
            "printf '/var/log/i2pd/*.log {\\n  daily\\n  rotate 3\\n  compress\\n  missingok\\n  notifempty\\n  size 20M\\n  copytruncate\\n}\\n' > /etc/logrotate.d/i2pd && "
            "df -h /"
        ),
    }
    cmd_id = (request.json or {}).get("cmd", "")
    if cmd_id not in allowed:
        return jsonify({"error": "unknown command"}), 400
    if cmd_id == "restart_dash":
        subprocess.Popen("sleep 2 && systemctl restart dashboard", shell=True)
        return jsonify({"output": "Restarting...", "rc": 0})
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


@app.route("/api/version")
def version(): return jsonify({"version": __version__})
@app.route("/api/rns_config_parsed")
def rns_config_parsed():
    import configparser, re
    path = f"{_HOME}/.reticulum/config"
    try:
        text = open(path).read()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # Parse [reticulum] section
    rns = {}
    rns_match = re.search(r'^\[reticulum\](.*?)^(?=\[|\Z)', text, re.MULTILINE | re.DOTALL)
    if rns_match:
        for line in rns_match.group(1).splitlines():
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                rns[k.strip()] = v.strip()

    # Parse [[Interface]] sections
    interfaces = []
    for m in re.finditer(r'^\s*\[\[([^\]]+)\]\](.*?)(?=^\s*\[\[|\Z)', text, re.MULTILINE | re.DOTALL):
        name = m.group(1).strip()
        params = {}
        for line in m.group(2).splitlines():
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                params[k.strip()] = v.strip()
        interfaces.append({"name": name, "params": params})

    return jsonify({"reticulum": rns, "interfaces": interfaces})


@app.route("/api/rns_config_save", methods=["POST"])
def rns_config_save():
    import re
    data = request.get_json()
    if not data:
        return jsonify({"error": "no data"}), 400
    path = f"{_HOME}/.reticulum/config"
    try:
        # Build new config text
        rns = data.get("reticulum", {})
        interfaces = data.get("interfaces", [])

        lines = ["[reticulum]\n"]
        for k, v in rns.items():
            lines.append(f"  {k} = {v}\n")
        lines.append("\n[interfaces]\n\n")

        for iface in interfaces:
            name = iface.get("name", "Interface")
            params = iface.get("params", {})
            lines.append(f"  [[{name}]]\n")
            for k, v in params.items():
                lines.append(f"    {k} = {v}\n")
            lines.append("\n")

        # Backup
        import shutil, time as _t
        shutil.copy2(path, path + ".bak." + _t.strftime("%Y%m%d_%H%M%S"))
        open(path, "w").write("".join(lines))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
        _sp.Popen(f"sleep 1 && sudo systemctl restart i2pd rnsd noema_lxmf_bridge nomadnet && sleep 8 && {_HOME}/NOEMA-RNSGate-Lite/.venv/bin/python3 {_HOME}/NOEMA-RNSGate-Lite/recalc_nn_addr.py && sleep 2 && sudo systemctl restart dashboard", shell=True)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})




@app.route("/api/cron/rnsd", methods=["GET", "POST"])
def cron_rnsd():
    cron_line = "0 4 * * * systemctl restart rnsd"
    def get_crontab():
        try:
            r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
            return r.stdout if r.returncode == 0 else ""
        except Exception:
            return ""
    def set_crontab(lines):
        text = chr(10).join(lines) + chr(10)
        p = subprocess.Popen(["crontab", "-"], stdin=subprocess.PIPE, text=True)
        p.communicate(text)
    if request.method == "GET":
        return jsonify({"enabled": cron_line in get_crontab()})
    data = request.get_json(silent=True) or {}
    enabled = bool(data.get("enabled", False))
    lines = [l for l in get_crontab().splitlines() if cron_line not in l and l.strip()]
    if enabled:
        lines.append(cron_line)
    set_crontab(lines)
    return jsonify({"enabled": enabled})

@app.route("/api/cron/tcp_watchdog", methods=["GET", "POST"])
def cron_tcp_watchdog():
    watchdog_path = f"{_HOME}/lxmf-tools/tcp_watchdog.py"
    python_bin = f"{_HOME}/NOEMA-RNSGate-Lite/.venv/bin/python3"
    cron_line = f"*/5 * * * * {python_bin} {watchdog_path} >> /var/log/noema_tcp_watchdog.log 2>&1"
    def get_crontab():
        try:
            r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
            return r.stdout if r.returncode == 0 else ""
        except Exception:
            return ""
    def set_crontab(lines):
        text = chr(10).join(lines) + chr(10)
        p = subprocess.Popen(["crontab", "-"], stdin=subprocess.PIPE, text=True)
        p.communicate(text)
    if request.method == "GET":
        current = get_crontab()
        enabled = any("tcp_watchdog.py" in l for l in current.splitlines())
        return jsonify({"enabled": enabled})
    data = request.get_json(silent=True) or {}
    enabled = bool(data.get("enabled", False))
    lines = [l for l in get_crontab().splitlines() if "tcp_watchdog.py" not in l and l.strip()]
    if enabled:
        lines.append(cron_line)
    set_crontab(lines)
    return jsonify({"enabled": enabled})



@app.route("/api/access/settings", methods=["GET", "POST"])
def access_settings():
    import configparser as _cp3
    BRIDGE_CFG = "/etc/noema/bridge.cfg"
    parser = _cp3.ConfigParser()
    parser.read(BRIDGE_CFG)
    if request.method == "GET":
        enabled = parser.get("access", "enabled", fallback="0") == "1"
        whitelist_raw = parser.get("access", "whitelist", fallback="")
        whitelist = [x.strip() for x in whitelist_raw.split(",") if x.strip()]
        rate_limit = parser.get("access", "rate_limit", fallback="5")
        cooldown = parser.get("access", "cooldown", fallback="60")
        return jsonify({"enabled": enabled, "whitelist": whitelist, "rate_limit": rate_limit, "cooldown": cooldown})

    data = request.get_json(silent=True) or {}
    if not parser.has_section("access"):
        parser.add_section("access")
    if "enabled" in data:
        parser.set("access", "enabled", "1" if data.get("enabled") else "0")
    if "whitelist" in data:
        wl = data.get("whitelist") or []
        parser.set("access", "whitelist", ",".join(x.strip() for x in wl if x.strip()))
    if "rate_limit" in data:
        parser.set("access", "rate_limit", str(int(data.get("rate_limit", 5))))
    if "cooldown" in data:
        parser.set("access", "cooldown", str(int(data.get("cooldown", 60))))
    with open(BRIDGE_CFG, "w") as f:
        parser.write(f)
    import subprocess as _sp3
    _sp3.Popen("sleep 1 && systemctl restart noema_lxmf_bridge", shell=True)
    return jsonify({"ok": True, "restarting": True})

@app.route("/api/chat_access/settings", methods=["GET", "POST"])
def chat_access_settings():
    import configparser as _cp4
    BRIDGE_CFG = "/etc/noema/bridge.cfg"
    parser = _cp4.ConfigParser()
    parser.read(BRIDGE_CFG)
    if request.method == "GET":
        enabled = parser.get("chat_access", "enabled", fallback="0") == "1"
        whitelist_raw = parser.get("chat_access", "whitelist", fallback="")
        whitelist = [x.strip() for x in whitelist_raw.split(",") if x.strip()]
        return jsonify({"enabled": enabled, "whitelist": whitelist})

    data = request.get_json(silent=True) or {}
    if not parser.has_section("chat_access"):
        parser.add_section("chat_access")
    if "enabled" in data:
        parser.set("chat_access", "enabled", "1" if data.get("enabled") else "0")
    if "whitelist" in data:
        wl = data.get("whitelist") or []
        parser.set("chat_access", "whitelist", ",".join(x.strip() for x in wl if x.strip()))
    with open(BRIDGE_CFG, "w") as f:
        parser.write(f)
    global _chat_access_enabled, _chat_access_whitelist
    _chat_access_enabled = parser.get("chat_access", "enabled", fallback="0") == "1"
    _chat_access_whitelist = set(x.strip() for x in parser.get("chat_access", "whitelist", fallback="").split(",") if x.strip())
    return jsonify({"ok": True})

@app.route("/<path:filename>")
def static_files(filename): return send_from_directory(".", filename)

@app.route("/")
def index(): return send_from_directory(".", "index.html")

if __name__ == "__main__":
    print("▶ http://0.0.0.0:8081")
    app.run(host="0.0.0.0", port=8081, threaded=True)
