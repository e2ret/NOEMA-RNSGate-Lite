# NOEMA RNSGate Lite
<img width="300" alt="NOEMA RNSGate Lite" src="https://github.com/user-attachments/assets/0f2329a0-5481-416f-90ee-b7ec26bc5267" />

[🇷🇺 Русский](#русский) | [🇬🇧 English](#english)

![RNS](https://img.shields.io/badge/RNS-1.4.2-teal) ![License](https://img.shields.io/badge/license-MIT-green) ![Platform](https://img.shields.io/badge/platform-Debian%20%7C%20Ubuntu-blue)

---

## Русский

**NOEMA RNSGate Lite** — шлюз для сети Reticulum, объединяющий радиосвязь LoRa, LXMF мессенджер, MQTT-интеграцию с Home Assistant, анонимную сеть I2P, Nomadnet и современный веб-интерфейс управления.

### Возможности
- Reticulum Mesh (TCP/IP + LoRa через RNode)
- LXMF Bridge → MQTT → Home Assistant
- Встроенный P2P чат (LXMF) с уведомлениями и вложениями
- Access Control: whitelist LXMF-адресов и rate limiting против спама
- Telegram уведомления при входящих сообщениях
- Анонимная сеть I2P (соединение шлюзов без публичного IP)
- Nomadnet Node + редактор страниц + IRC-чат
- rBrowser — встроенный Nomadnet браузер
- Современный веб-дашборд (светлая/тёмная тема): мониторинг, управление сервисами, редактор конфигов без SSH
- Backup & Restore всех идентификаторов и данных
- Обновление из GitHub в один клик прямо из дашборда

### ⚠️ Важно
Проект создан в личных целях и распространяется **как есть**, без гарантий работоспособности. Требуется понимание основ: Linux, TCP/IP, MQTT, базовое администрирование.

### Установка
Требования: Debian/Ubuntu, Python 3.10+, root.
```bash
git clone https://github.com/e2ret/NOEMA-RNSGate-Lite.git && cd NOEMA-RNSGate-Lite && sudo bash install.sh
```
Скрипт автоматически устанавливает все зависимости и запускает systemd сервисы. В процессе установки задаются два вопроса:

- **MQTT брокер** — IP/хост, порт, логин и пароль (для LXMF Bridge → Home Assistant). Если брокера пока нет — можно нажать Enter и оставить значения по умолчанию (`localhost`), настроить позже через [[Configs]] в дашборде.
- **Имя узла Nomadnet** — как ваш шлюз будет отображаться другим узлам сети в анонсах. По умолчанию подставляется `NOEMA RNSGate (hostname)` — этого достаточно, если у вас один шлюз; если планируете несколько, стоит сразу задать понятные имена (например `NOEMA Дом`, `NOEMA Дача`), чтобы отличать их в сети. Позже это тоже можно поменять в дашборде, вкладка [[Nomadnet]].

> **Примечание:** в процессе установки дважды потребуется нажать Enter — для инициализации Nomadnet и настройки cron-задач.

### Первый вход

После установки дашборд доступен в браузере на **порту 8081**:

```
http://IP_ШЛЮЗА:8081
```

IP-адрес устройства можно посмотреть в списке клиентов роутера, или через `hostname -I` по SSH на самом шлюзе. По умолчанию авторизация не требуется — дашборд открыт для всех в локальной сети.

### На чём запускать

Проект **не привязан к Orange Pi** — это просто пример устройства, на котором тестировался. Реально нужен любой Linux (Debian/Ubuntu) с Python 3.10+:

- **Одноплатники**: Orange Pi Zero/Zero 2/Zero 3, Raspberry Pi (любая модель с Ubuntu/Debian)
- **VM/LXC на Proxmox**: любой Debian/Ubuntu контейнер или виртуалка — так же, как автор запускает у себя
- **Старый ноутбук/мини-ПК**: x86_64 с Ubuntu Server
- **VPS**: если нужен публичный TCP-узел без домашней сети

Для LoRa нужен RNode — он подключается либо по USB, либо по Wi-Fi (для ESP32-моделей с сетевым интерфейсом). Физический USB-порт нужен только для USB-варианта. Остальной функционал (TCP/Wi-Fi/Ethernet mesh, I2P, MQTT, чат) работает на любой VM без физического доступа к железу.

Минимальные требования: ~256 МБ RAM, ~2 ГБ диска для установки всех компонентов.

### Документация
**[→ Полная документация в Wiki](https://github.com/e2ret/NOEMA-RNSGate-Lite/wiki)**

### Обсуждение
[→ Telegram](https://t.me/reticulum_belgorod/70)

### Используемые компоненты
- [Reticulum (RNS)](https://github.com/markqvist/Reticulum) — Mark Qvist, MIT
- [LXMF](https://github.com/markqvist/LXMF) — Mark Qvist, MIT
- [Nomadnet](https://github.com/markqvist/NomadNet) — Mark Qvist, GPL-3.0
- [lxmfy](https://github.com/lxmfy/lxmfy) — lxmfy, MIT
- [Flask](https://flask.palletsprojects.com/) — Pallets, BSD
- [paho-mqtt](https://github.com/eclipse/paho.mqtt.python) — Eclipse, EPL/EDL
- [rBrowser](https://github.com/fr33n0w/rBrowser) — fr33n0w, MIT
- [i2pd](https://github.com/PurpleI2P/i2pd) — PurpleI2P, BSD

### Благодарности
**Mark Qvist** — Reticulum, LXMF, Nomadnet · **fr33n0w** — rBrowser · **PurpleI2P Team** — i2pd

Спасибо всем разработчикам, благодаря которым экосистема Reticulum продолжает развиваться.

---

## English

**NOEMA RNSGate Lite** — a gateway for the Reticulum network, combining LoRa radio, the LXMF messenger, MQTT integration with Home Assistant, the anonymous I2P network, Nomadnet, and a modern web management interface.

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
