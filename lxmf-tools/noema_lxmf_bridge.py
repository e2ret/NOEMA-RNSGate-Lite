#!/usr/bin/env python3
"""
NOEMA LXMF Bridge — unified LXMFy + MQTT bridge for Home Assistant.
Replaces lxmf_bridge_mqtt.py with LXMFy framework.

Install: pip install lxmfy paho-mqtt
"""

import json
import os
import time
import configparser
import threading
import paho.mqtt.client as mqtt_client
from lxmfy import LXMFBot

# ─── Config ──────────────────────────────────────────────────────────────────

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.cfg.owr")
_cfg = configparser.ConfigParser()
_cfg.read(CONFIG_PATH)

def cfg(section, key, fallback=""):
    try:
        return _cfg[section][key].strip()
    except KeyError:
        return fallback

MQTT_HOST      = cfg("mqtt", "host", "10.0.1.111")
MQTT_PORT      = int(cfg("mqtt", "port", "1883"))
MQTT_USER      = cfg("mqtt", "username", "mqtt")
MQTT_PASS      = cfg("mqtt", "password", "")
MQTT_CLIENT_ID = cfg("mqtt", "client_id", "lxmf_mqtt_bridge")

TOPIC_SEND     = cfg("topics", "topic_send",     "message/lxmf/send")
TOPIC_RECEIVE  = cfg("topics", "topic_receive",  "message/lxmf/receive")
TOPIC_ANNOUNCE = cfg("topics", "topic_announce", "message/lxmf/announce")
TOPIC_POWER    = cfg("topics", "topic_power",    "message/lxmf/power")
TOPIC_STATE    = cfg("topics", "topic_state",    "message/lxmf/state")
TOPIC_RM_POWER = cfg("topics", "topic_rm_power", "message/lxmf/rm_power")
TOPIC_RM_STATE = cfg("topics", "topic_rm_state", "message/lxmf/rm_state")

LXMF_TO_MQTT  = _cfg.getboolean("router", "lxmf_to_mqtt",  fallback=True)
MQTT_TO_LXMF  = _cfg.getboolean("router", "mqtt_to_lxmf",  fallback=True)
STATE_TO_MQTT  = _cfg.getboolean("router", "state_to_mqtt", fallback=True)
STATE_INTERVAL = int(cfg("topics", "state_interval", "60"))

DISPLAY_NAME   = cfg("lxmf", "display_name", "LXMF Bridge")
ANNOUNCE_START = _cfg.getboolean("lxmf", "announce_startup", fallback=True)

STORAGE_PATH   = os.path.join(os.path.dirname(__file__), "lxmfy_data")

# ─── MQTT client ─────────────────────────────────────────────────────────────

_mqtt = None
_mqtt_connected = False
_bot_ref = None   # filled after bot creation


def mqtt_connect():
    global _mqtt, _mqtt_connected

    def on_connect(client, userdata, flags, rc, props=None):
        global _mqtt_connected
        _mqtt_connected = (rc == 0)
        if rc == 0:
            client.subscribe(TOPIC_SEND)
            client.subscribe(TOPIC_POWER)
            client.subscribe(TOPIC_STATE)
            print(f"[MQTT] Connected to {MQTT_HOST}:{MQTT_PORT}")
            if STATE_TO_MQTT:
                _publish_state()
        else:
            print(f"[MQTT] Connection failed rc={rc}")

    def on_message(client, userdata, msg):
        topic = msg.topic
        try:
            payload = msg.payload.decode("utf-8")
        except Exception:
            return

        if topic == TOPIC_SEND and MQTT_TO_LXMF and _bot_ref:
            _handle_mqtt_to_lxmf(payload)
        elif topic == TOPIC_POWER:
            _handle_power(payload)
        elif topic == TOPIC_STATE:
            _handle_state(payload)

    def on_disconnect(client, userdata, rc, props=None):
        global _mqtt_connected
        _mqtt_connected = False
        print("[MQTT] Disconnected, reconnecting...")

    _mqtt = mqtt_client.Client(
        client_id=MQTT_CLIENT_ID,
        callback_api_version=mqtt_client.CallbackAPIVersion.VERSION2
    )
    _mqtt.username_pw_set(MQTT_USER, MQTT_PASS)
    _mqtt.on_connect    = on_connect
    _mqtt.on_message    = on_message
    _mqtt.on_disconnect = on_disconnect

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
    state = json.dumps({
        "power": "on",
        "timestamp": time.time()
    })
    _publish(TOPIC_RM_STATE, state)


def _handle_power(payload):
    val = payload.strip().lower()
    if val in ("on", "1"):
        _publish(TOPIC_RM_POWER, "on")
    else:
        _publish(TOPIC_RM_POWER, "off")


def _handle_state(payload):
    _publish(TOPIC_RM_STATE, payload)


def _handle_mqtt_to_lxmf(payload):
    try:
        data = json.loads(payload)
        destination = data.get("destination", "").strip()
        content = data.get("content", "").strip()
        title = data.get("title", "Reply").strip()
        if destination and content and _bot_ref:
            _bot_ref.send(destination, content, title=title)
    except Exception as e:
        print(f"[MQTT→LXMF] Error: {e}")


# ─── LXMFy Bot ───────────────────────────────────────────────────────────────

bot = LXMFBot(
    name=DISPLAY_NAME,
    announce=600,
    announce_immediately=ANNOUNCE_START,
    storage_type="json",
    storage_path=STORAGE_PATH,
    rate_limit=5,
    cooldown=60,
    command_prefix="/",
    first_message_enabled=True,
    message_persistence_enabled=True,
)

_bot_ref = bot


# ─── First message greeting ──────────────────────────────────────────────────

@bot.on_first_message()
def welcome(sender, message):
    bot.send(sender,
        "👋 Добро пожаловать в NOEMA LXMF Bridge!\n\n"
        "Используйте /help для списка команд.\n"
        "Все сообщения перенаправляются в Home Assistant через MQTT."
    )
    return False  # continue processing


# ─── All messages → MQTT ─────────────────────────────────────────────────────

@bot.on_message()
def forward_to_mqtt(sender, message):
    if not LXMF_TO_MQTT:
        return False

    try:
        content = message.content.decode("utf-8", errors="replace").strip()
        payload = json.dumps({
            "source":      sender,
            "destination": "",
            "title":       message.title.decode("utf-8", errors="replace").strip() if message.title else "",
            "content":     content,
            "timestamp":   message.timestamp,
            "date_time":   time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(message.timestamp)),
            "signature_valid": 1 if message.signature_validated else 0,
        })
        _publish(TOPIC_RECEIVE, payload)
    except Exception as e:
        print(f"[LXMF→MQTT] Error: {e}")

    return False  # continue to command processing


# ─── Commands ────────────────────────────────────────────────────────────────

@bot.command(name="статус", description="Статус MQTT подключения")
def cmd_status(ctx):
    status = "✅ Подключён" if _mqtt_connected else "❌ Отключён"
    ctx.reply(
        f"MQTT Broker: {MQTT_HOST}:{MQTT_PORT}\n"
        f"Статус: {status}\n"
        f"Топик приёма: {TOPIC_RECEIVE}\n"
        f"Топик отправки: {TOPIC_SEND}"
    )


@bot.command(name="status", description="MQTT connection status")
def cmd_status_en(ctx):
    status = "✅ Connected" if _mqtt_connected else "❌ Disconnected"
    ctx.reply(
        f"MQTT Broker: {MQTT_HOST}:{MQTT_PORT}\n"
        f"Status: {status}\n"
        f"Receive topic: {TOPIC_RECEIVE}\n"
        f"Send topic: {TOPIC_SEND}"
    )


@bot.command(name="ping", description="Проверка связи")
def cmd_ping(ctx):
    ctx.reply("🏓 Pong! NOEMA LXMF Bridge работает.")


@bot.command(name="info", description="Информация о шлюзе")
def cmd_info(ctx):
    ctx.reply(
        "🔌 NOEMA RNSGate Lite\n"
        "LXMF ↔ MQTT Bridge\n\n"
        f"Broker: {MQTT_HOST}:{MQTT_PORT}\n"
        f"LXMF→MQTT: {'✅' if LXMF_TO_MQTT else '❌'}\n"
        f"MQTT→LXMF: {'✅' if MQTT_TO_LXMF else '❌'}"
    )


# ─── Scheduled state publishing ───────────────────────────────────────────────

@bot.scheduler.schedule(
    name="mqtt_state",
    cron_expr=f"*/{max(1, STATE_INTERVAL // 60)} * * * *"
)
def scheduled_state():
    if STATE_TO_MQTT:
        _publish_state()


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"[NOEMA] Starting LXMF Bridge MQTT")
    print(f"[NOEMA] MQTT: {MQTT_HOST}:{MQTT_PORT}")
    print(f"[NOEMA] Config: {CONFIG_PATH}")

    mqtt_connect()
    time.sleep(2)  # wait for MQTT connection

    bot.run()
