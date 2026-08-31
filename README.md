# NOEMA RNSGate Lite
<img width="300" alt="NOEMA RNSGate Lite" src="https://github.com/user-attachments/assets/0f2329a0-5481-416f-90ee-b7ec26bc5267" />

**NOEMA RNSGate Lite** — a gateway for the Reticulum network, combining LoRa radio, the LXMF messenger, MQTT integration with Home Assistant, the anonymous I2P network, Nomadnet, and a modern web management interface.

[![Translate](https://img.shields.io/badge/Translate-To_Your_Language-red)](https://translate.google.com/translate?sl=auto&u=https://github.com/e2ret/NOEMA-RNSGate-Lite)

> 🔬 Want more? Check out **[NOEMA RNSGate FULL](https://github.com/e2ret/NOEMA-RNSGate-FULL)** — the version with Radio Observatory: real RSSI/SNR/Noise data from RNode, network map with hop rings, RF packet log, interference detection and browser terminal.

### Features
- Reticulum Mesh (TCP/IP + LoRa via RNode)
- LXMF Bridge → MQTT → Home Assistant
- Built-in P2P chat (LXMF) with notifications and attachments
- Access Control: LXMF address whitelisting and rate limiting against spam
- Telegram notifications for incoming messages
- Anonymous I2P network (connect gateways without a public IP)
- Nomadnet Node + page editor + IRC-style chat
- rBrowser — built-in Nomadnet browser
- Modern web dashboard (light/dark theme): monitoring, service management, config editor without SSH
- Backup & Restore for all identities and data
- One-click update from GitHub right in the dashboard

### ⚠️ Important
This project was built for personal use and is distributed **as-is**, with no guarantee of functionality. Basic knowledge required: Linux, TCP/IP, MQTT, general system administration.

### Installation
Requirements: Debian/Ubuntu, Python 3.10+, root.
```bash
git clone https://github.com/e2ret/NOEMA-RNSGate-Lite.git && cd NOEMA-RNSGate-Lite && sudo bash install.sh
```
The script automatically installs all dependencies and starts the systemd services. During installation you'll be asked two things:

- **MQTT broker** — host/IP, port, username, and password (for LXMF Bridge → Home Assistant). If you don't have a broker yet, just press Enter to keep the defaults (`localhost`) and configure it later via [[Configs]] in the dashboard.
- **Nomadnet node name** — how your gateway will appear to other nodes in the network's announces. Defaults to `NOEMA RNSGate (hostname)` — fine if you're only running one gateway; if you're planning to run several, it's worth picking clear names right away (e.g. `NOEMA Home`, `NOEMA Cabin`) to tell them apart on the network. This can also be changed later in the dashboard, under [[Nomadnet]].

> **Note:** during installation you'll need to press Enter twice — for Nomadnet initialization and cron setup.

### First login

Once installed, the dashboard is available in your browser on **port 8081**:

```
http://GATEWAY_IP:8081
```

Find the device's IP in your router's client list, or via `hostname -I` over SSH on the gateway itself. No authentication is required by default — the dashboard is open to anyone on the local network.

### On what hardware

The project **is not tied to Orange Pi** — that's just the device it was tested on. All you really need is any Linux (Debian/Ubuntu) with Python 3.10+:

- **Single-board computers**: Orange Pi Zero/Zero 2/Zero 3, Raspberry Pi (any model with Ubuntu/Debian)
- **VM/LXC on Proxmox**: any Debian/Ubuntu container or VM — this is how the author runs it
- **Old laptop / mini-PC**: x86_64 with Ubuntu Server
- **VPS**: if you need a public TCP node without a home network

RNode connects either via USB or Wi-Fi (for ESP32-based models with a network interface) — a physical USB port is only required for the USB variant. Everything else (TCP/Wi-Fi/Ethernet mesh, I2P, MQTT, chat) runs on any VM with no physical hardware access at all.

Minimum requirements: ~256 MB RAM, ~2 GB disk for a full install.

### Documentation
**[→ Full documentation in the Wiki](https://github.com/e2ret/NOEMA-RNSGate-Lite/wiki)**

### Discussion
[→ Telegram](https://t.me/reticulum_belgorod/70)

### Components used
- [Reticulum (RNS)](https://github.com/markqvist/Reticulum) — Mark Qvist, MIT
- [LXMF](https://github.com/markqvist/LXMF) — Mark Qvist, MIT
- [Nomadnet](https://github.com/markqvist/NomadNet) — Mark Qvist, GPL-3.0
- [lxmfy](https://github.com/lxmfy/lxmfy) — lxmfy, MIT
- [Flask](https://flask.palletsprojects.com/) — Pallets, BSD
- [paho-mqtt](https://github.com/eclipse/paho.mqtt.python) — Eclipse, EPL/EDL
- [rBrowser](https://github.com/fr33n0w/rBrowser) — fr33n0w, MIT
- [i2pd](https://github.com/PurpleI2P/i2pd) — PurpleI2P, BSD

### Acknowledgements
**Mark Qvist** — Reticulum, LXMF, Nomadnet · **fr33n0w** — rBrowser · **PurpleI2P Team** — i2pd

Thanks to all the developers who keep the Reticulum ecosystem growing.

## Support the project
If you find this useful, donations are welcome.

## Support the project
If you find this useful, donations are welcome.

![USDT TRC20](https://img.shields.io/badge/USDT_(TRC20)-26A17B?style=flat&logo=tether&logoColor=white) `TD89XXL9ehwhp4WysfqHSBGJjxxdoaVsYD`

![TON](https://img.shields.io/badge/TON-0098EA?style=flat&logo=ton&logoColor=white) `UQCmROnKeaWIt5Uxu3MTebKUjYQHuvVeyOauWdVn6srUWKX8`

[![Boosty](https://img.shields.io/badge/Boosty-E55F2A?style=flat&logo=boosty&logoColor=white)](https://boosty.to/noemarns/donate)

## Contacts

[![Telegram](https://img.shields.io/badge/Telegram-2CA5E0?style=flat&logo=telegram&logoColor=2CA5E0&labelColor=white&label=)](t.me/https://t.me/reticulum_belgorod/70) 

![LXMF](https://img.shields.io/badge/LXMF-222222?style=flat) `3c4d222ee3acca1b386f5c2ad7ff1c6f`

[![GitHub](https://img.shields.io/badge/GitHub-121011?style=flat&logo=github&logoColor=121011&labelColor=white&label=)](https://github.com/e2ret)
