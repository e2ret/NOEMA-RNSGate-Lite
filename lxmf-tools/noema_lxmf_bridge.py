#!/usr/bin/env python3
"""
NOEMA LXMF Bridge — LXMFy + MQTT bridge for Home Assistant.
Config: /etc/noema/bridge.cfg
"""

import json
import os
import time
import configparser
import threading
import paho.mqtt.client as mqtt_client
from lxmfy import LXMFBot

# ─── Config ──────────────────────────────────────────────────────────────────

CONFIG_PATH  = "/etc/noema/bridge.cfg"
STORAGE_PATH   = os.path.join(os.path.expanduser("~"), "lxmf-tools", "lxmfy_data")
ADDRESS_FILE   = "/root/lxmf-tools/lxmf_address"

_cfg = configparser.ConfigParser()
_cfg.read(CONFIG_PATH)

def cfg(section, key, fallback=""):
    try:
        return _cfg[section][key].strip()
    except KeyError:
        return fallback

MQTT_HOST      = cfg("mqtt", "host",      "localhost")
MQTT_PORT      = int(cfg("mqtt", "port",  "1883"))
MQTT_USER      = cfg("mqtt", "username",  "")
MQTT_PASS      = cfg("mqtt", "password",  "")
MQTT_CLIENT_ID = cfg("mqtt", "client_id", "noema_lxmf_bridge")

TOPIC_SEND     = cfg("topics", "send",     "message/lxmf/send")
TOPIC_RECEIVE  = cfg("topics", "receive",  "message/lxmf/receive")
TOPIC_RM_STATE = cfg("topics", "state",    "message/lxmf/rm_state")
TOPIC_POWER    = cfg("topics", "power",    "message/lxmf/power")
TOPIC_RM_POWER = cfg("topics", "rm_power", "message/lxmf/rm_power")

DISPLAY_NAME   = cfg("lxmf", "display_name", "LXMF Bridge")

# ─── MQTT ────────────────────────────────────────────────────────────────────

_mqtt = None
_mqtt_connected = False
_bot_ref = None

def mqtt_connect():
    global _mqtt, _mqtt_connected

    def on_connect(client, userdata, flags, rc, props=None):
        global _mqtt_connected
        _mqtt_connected = (rc == 0)
        if rc == 0:
            client.subscribe(TOPIC_SEND)
            client.subscribe(TOPIC_POWER)
            print(f"[MQTT] Connected to {MQTT_HOST}:{MQTT_PORT}")
            _publish_state()
        else:
            print(f"[MQTT] Connection failed rc={rc}")

    def on_disconnect(client, userdata, disconnect_flags, reason_code, props=None):
        global _mqtt_connected
        _mqtt_connected = False
        print("[MQTT] Disconnected, reconnecting...")

    def on_message(client, userdata, msg):
        if msg.topic == TOPIC_SEND and _bot_ref:
            _handle_mqtt_to_lxmf(msg.payload.decode("utf-8", errors="replace"))
        elif msg.topic == TOPIC_POWER:
            _publish(TOPIC_RM_POWER, "on" if msg.payload.decode().strip().lower() in ("on","1") else "off")

    _mqtt = mqtt_client.Client(
        client_id=MQTT_CLIENT_ID,
        callback_api_version=mqtt_client.CallbackAPIVersion.VERSION2
    )
    if MQTT_USER:
        _mqtt.username_pw_set(MQTT_USER, MQTT_PASS)
    _mqtt.on_connect    = on_connect
    _mqtt.on_disconnect = on_disconnect
    _mqtt.on_message    = on_message

    def _loop():
        while True:
            try:
                _mqtt.connect(MQTT_HOST, MQTT_PORT, 60)
                _mqtt.loop_forever()
            except Exception as e:
                print(f"[MQTT] Error: {e}, retry in 10s")
                time.sleep(10)

    threading.Thread(target=_loop, daemon=True).start()

def _publish(topic, payload):
    if _mqtt and _mqtt_connected:
        _mqtt.publish(topic, payload)

def _publish_state():
    _publish(TOPIC_RM_STATE, json.dumps({"power": "on", "timestamp": time.time()}))

def _handle_mqtt_to_lxmf(payload):
    try:
        data = json.loads(payload)
        dest    = data.get("destination", "").strip()
        content = data.get("content", "").strip()
        title   = data.get("title", "Reply").strip()
        if dest and content and _bot_ref:
            _bot_ref.send(dest, content, title=title)
    except Exception as e:
        print(f"[MQTT→LXMF] Error: {e}")

# ─── Bot ─────────────────────────────────────────────────────────────────────

CONFIG_DIR = os.path.join(os.path.expanduser("~"), "lxmf-tools", "lxmfy_config")
os.makedirs(STORAGE_PATH, exist_ok=True)
os.makedirs(CONFIG_DIR, exist_ok=True)

bot = LXMFBot(
    name=DISPLAY_NAME,
    announce=600,
    announce_immediately=True,
    storage_type="json",
    storage_path=STORAGE_PATH,
    config_path=CONFIG_DIR,
    rate_limit=5,
    cooldown=60,
    command_prefix="/",
    first_message_enabled=True,
    message_persistence_enabled=True,
    reticulum_config_dir=os.path.join(os.path.expanduser("~"), ".reticulum"),
    landlock_enabled=False,
)
_bot_ref = bot

# Save address for dashboard
try:
    addr = list(bot.router.delivery_destinations.values())[0].hexhash
    open(os.path.join(os.path.expanduser("~"), "lxmf-tools", "lxmf_address"), "w").write(addr)
    print(f"[NOEMA] Address: {addr}")
except Exception as e:
    print(f"[NOEMA] Could not save address: {e}")

@bot.on_first_message()
def welcome(sender, message):
    bot.send(sender,
        "👋 NOEMA LXMF Bridge\n\n"
        "Commands: /status /ping /info\n"
        "Messages are forwarded to Home Assistant via MQTT."
    )
    return False

@bot.on_message()
def forward_to_mqtt(sender, message):
    try:
        content = message.content.decode("utf-8", errors="replace").strip()
        title   = message.title.decode("utf-8", errors="replace").strip() if message.title else ""
        _publish(TOPIC_RECEIVE, json.dumps({
            "source":         sender,
            "title":          title,
            "content":        content,
            "timestamp":      message.timestamp,
            "date_time":      time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(message.timestamp)),
            "signature_valid": 1 if message.signature_validated else 0,
        }))
    except Exception as e:
        print(f"[LXMF→MQTT] Error: {e}")
    return False

@bot.command(name="status", description="MQTT status")
def cmd_status(ctx):
    ctx.reply(f"MQTT: {'✅ Connected' if _mqtt_connected else '❌ Disconnected'}\nBroker: {MQTT_HOST}:{MQTT_PORT}")

@bot.command(name="ping", description="Ping")
def cmd_ping(ctx):
    ctx.reply("🏓 Pong!")

@bot.command(name="info", description="Bridge info")
def cmd_info(ctx):
    ctx.reply(f"🔌 NOEMA RNSGate Lite\nLXMF ↔ MQTT\nBroker: {MQTT_HOST}:{MQTT_PORT}")

# ─── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"[NOEMA] LXMF Bridge starting")
    print(f"[NOEMA] Config: {CONFIG_PATH}")
    print(f"[NOEMA] MQTT: {MQTT_HOST}:{MQTT_PORT}")
    mqtt_connect()
    time.sleep(2)
    bot.run()
