# NOEMA RNSGate Lite — LoRa · MQTT · I2P · Nomadnet

<p align="left">
  <img src="https://github.com/e2ret/NOEMA-RNSGate-Lite/blob/main/001.png" width="800" alt="NOEMA RNSGate Lite">
</p>

[🇷🇺 Читать на русском](#ru)

**Reticulum Mesh Gateway** — a lightweight gateway for the Reticulum network, combining LoRa radio, LXMF messaging, MQTT integration with Home Assistant, anonymous I2P network, Nomadnet, and a modern web dashboard.

![RNS](https://img.shields.io/badge/RNS-1.4.2-teal) ![License](https://img.shields.io/badge/license-MIT-green)

> **Lite** version — no built-in LXMF Chat, no Group Chat, no RMAP map. Designed for minimal resource usage on low-power hardware.

---

## ⚠️ Important

This device is intended for technically prepared users. The project is created for personal use and distributed **as is**, without any warranty.

Basic knowledge required: Linux, TCP/IP, MQTT, system administration.

The author is not responsible for failures, data loss, or any other consequences of use.

---

## Features

- Reticulum Mesh (TCP/IP + LoRa)
- LXMF Bridge → MQTT (receive commands from Reticulum → Home Assistant)
- MQTT Bridge for Home Assistant automations
- I2P Anonymous Network
- Nomadnet Node + page editor
- rBrowser — built-in Nomadnet browser
- Web dashboard with monitoring and management
- All gateway addresses in one place (Addresses tab)
- Edit configs via browser without SSH
- RNode telemetry
- RNS version check and one-click update

---

## Architecture

```
Smartphone ──BT──▶ RNode ──LoRa──▶ NOEMA RNSGate Lite ──MQTT──▶ Home Assistant
                                           │
                                    I2P / TCP / LAN
                                           │
                                     Other gateway
                                           │
                                       Nomadnet
```

---

## Installation

Requirements: Debian/Ubuntu, Python 3.10+, root access.

Connect via SSH to your gateway and run:

```bash
git clone https://github.com/e2ret/NOEMA-RNSGate-Lite.git && cd NOEMA-RNSGate-Lite && sudo bash install.sh
```

The script will automatically:
- Clone the repository and install dependencies
- Ask for MQTT broker parameters (IP, port, login, password)
- Configure all services
- Create and start systemd services

---

## First Connection

1. Connect an Ethernet cable to your router
2. Find the device in your router's client list
3. Open browser: `http://GATEWAY_IP:8081`
4. SSH: `ssh root@GATEWAY_IP` (default password: `1234`)

Configure Wi-Fi:
```bash
nmtui
```

---

## Web Dashboard

| Section | Description |
|---------|-------------|
| Services | Service status |
| Configs | Edit configs with backup |
| Addresses | All gateway addresses |
| Monitor | LXMF message log + RNS interfaces |
| RNode | LoRa telemetry |
| Network | Public nodes + RNprobe |
| I2P | Anonymous network |
| Nomadnet | Info page, editor, Micron Composer |
| Browser | Built-in Nomadnet browser (rBrowser) |
| Logs | Service logs |
| System | Commands, backup, RNS update, reset identity |

---

## Services

| Service | Description |
|---------|-------------|
| `rnsd` | Reticulum Network Stack |
| `dashboard` | Web interface :8081 |
| `lxmf_bridge_mqtt` | LXMF ↔ MQTT bridge |
| `i2pd` | I2P daemon |
| `nomadnet` | Nomadnet Node |
| `rbrowser` | Nomadnet Browser :5000 |

Check status:
```bash
systemctl status rnsd dashboard lxmf_bridge_mqtt i2pd nomadnet rbrowser
```

---

## MQTT Configuration

`Dashboard → Configs → lxmf_bridge_mqtt`

```ini
[mqtt]
host = 192.168.1.100
port = 1883
username = username
password = password
```

After changes click **Save** in the dashboard — the service restarts automatically.

Home Assistant automation example:

```yaml
trigger:
  - platform: mqtt
    topic: message/lxmf/receive
action:
  - service: mqtt.publish
    data:
      topic: message/lxmf/send
      payload: >
        {{ {
          "destination": trigger.payload_json.source,
          "content": "Reply!"
        } | to_json }}
```

---

## LoRa / RNode Configuration

`Dashboard → Configs → Reticulum`

```ini
[[RNode]]
  type = RNodeInterface
  enabled = yes
  port = /dev/ttyUSB0
  frequency = 869525000
  bandwidth = 125000
  txpower = 17
  spreadingfactor = 9
  codingrate = 8
```

Find port: `Dashboard → System → Ports`

---

## Client Connection

**Sideband (iOS / Android)**
```
Settings → Interfaces → Add Interface → TCP Client
Host: GATEWAY_IP  Port: 4242
```

**MeshChat / Retichat**
```
Host: GATEWAY_IP  Port: 4242
```

---

## Addresses

The Addresses tab contains all gateway addresses:

| Address | Description |
|---------|-------------|
| LXMF Bridge | Receive commands from Reticulum → MQTT. Add to Sideband as a contact |
| I2P (b32) | Anonymous connection without public IP |
| Nomadnet Node | Info page address |
| Nomadnet Chat | IRC-style chat address |

---

## I2P

`Dashboard → I2P`

1. Click **Setup Reticulum tunnel in i2pd**
2. Wait 2–5 minutes for the b32 address to appear
3. Exchange addresses with another gateway
4. Add their b32 → **Add to config**
5. Start exchanging LXMF messages

> ⚠️ Initial network stabilization takes 5–10 minutes. Reconnections every ~2 min are normal.

---

## Nomadnet Page

The gateway automatically publishes an info page. Open in any Nomadnet client:

```
<node_address>:/page/index.mu
```

Edit: `Dashboard → Nomadnet → Page Editor`

**Micron markup basics:**
```
`c          — center
`f...`f     — large font
`b...`b     — bold
`[Title`]   — section header
---         — divider
```

Use [Micron Composer](https://fr33n0w.github.io/micron-composer/) for visual editing — available directly from the Nomadnet tab.

---

## Nomadnet Browser

`Dashboard → Browser`

Built-in browser for viewing Nomadnet pages without installing additional apps. Runs on port 5000. Also accessible directly:

```
http://GATEWAY_IP:5000
```

Features: multi-tab, favorites, known nodes list, ping, search.

Based on [rBrowser](https://github.com/fr33n0w/rBrowser) — fr33n0w, MIT.

---

## Typical Use Cases

**Local browser over LAN**
```
PC/Phone ──Wi-Fi──▶ NOEMA RNSGate
```
No setup needed. Open: `http://GATEWAY_IP:8081`

**Sideband over TCP**
```
Smartphone ──TCP──▶ NOEMA RNSGate
```
Requires internet, port 4242.

**Two gateways via I2P**
```
RNSGate ──I2P──▶ RNSGate
```
Anonymous, no public IP needed.

**LoRa → Gateway → I2P**
```
Smartphone ──BT──▶ RNode ──LoRa──▶ RNSGate ──▶ I2P
```
Smartphone offline, internet only on the gateway.

**Wi-Fi → Gateway → I2P**
```
Smartphone ──Wi-Fi──▶ RNSGate ──▶ I2P
```
No mobile internet needed on the smartphone.

---

## RNS Version Check

`Dashboard → System → RNS Version`

Shows installed vs latest PyPI version. If an update is available, the **Update RNS** button appears — click to update without SSH.

---

## Backup & Restore

`Dashboard → System → Download Backup` — ZIP with configs and keys  
`Dashboard → System → Restore` — restore from archive

---

## Reset Identity

`Dashboard → System → Reset All Identity`

Use before selling the gateway. Deletes all identities, keys, history. Preserves configs and Nomadnet pages.

What is deleted:
- LXMF Bridge identity and keys
- Reticulum identity
- I2P keys (new b32 after reset)
- Nomadnet identity (new node address)

What is preserved:
- Reticulum and MQTT configuration
- Nomadnet pages

> ⚠️ Irreversible. Make a backup first.

---

## File Locations

```
~/lxmf-tools/config.cfg.owr              — MQTT config
~/.reticulum/config                       — Reticulum / LoRa config
~/lxmf-tools/identity                     — LXMF Bridge key
~/.nomadnetwork/storage/pages/index.mu    — Nomadnet main page
~/.nomadnetwork/config                    — Nomadnet config
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| LoRa not detected | `ls /dev/ttyUSB* /dev/ttyACM*`, check `port` in config |
| MQTT error | Check IP, port, username, password |
| Service crashed | `journalctl -u <service> -n 20 --no-pager` |
| No route to contact | `systemctl restart rnsd`, wait 30 sec |
| Dashboard not opening | `systemctl restart dashboard` |
| I2P unstable | Wait 5–10 minutes after start |

---

## Credits

- [Reticulum (RNS)](https://github.com/markqvist/Reticulum) — Mark Qvist, MIT
- [LXMF](https://github.com/markqvist/LXMF) — Mark Qvist, MIT
- [Nomadnet](https://github.com/markqvist/NomadNet) — Mark Qvist, GPL-3.0
- [Flask](https://flask.palletsprojects.com/) — Pallets, BSD
- [paho-mqtt](https://github.com/eclipse/paho.mqtt.python) — Eclipse, EPL/EDL
- [rBrowser](https://github.com/fr33n0w/rBrowser) — fr33n0w, MIT
- [lxmf-tools](https://github.com/SebastianObi/LXMF-Tools) — SebastianObi
- [i2pd](https://github.com/PurpleI2P/i2pd) — PurpleI2P, BSD

---

---

<a name="ru"></a>

# NOEMA RNSGate Lite — LoRa · MQTT · I2P · Nomadnet

[🇬🇧 Read in English](#top)

**Reticulum Mesh Gateway** — лёгкий шлюз для сети Reticulum, объединяющий радиосвязь LoRa, LXMF мессенджер, MQTT-интеграцию с Home Assistant, анонимную сеть I2P, Nomadnet и современный веб-интерфейс управления.

> **Lite** версия — без встроенного LXMF Chat, без Group Chat, без карты RMAP. Предназначена для минимального потребления ресурсов на маломощном железе.

---

## ⚠️ Важно

Это устройство для технически подготовленных пользователей. Проект создан в личных целях и распространяется **как есть**, без гарантий работоспособности.

Для работы необходимо понимание основ: Linux, TCP/IP, MQTT, базовое администрирование.

Автор не несёт ответственности за сбои, потерю данных или любые иные последствия использования.

---

## Возможности

- Reticulum Mesh (TCP/IP + LoRa)
- LXMF Bridge → MQTT (приём команд из Reticulum → Home Assistant)
- MQTT Bridge для автоматизаций Home Assistant
- Анонимная сеть I2P
- Nomadnet Node + редактор страниц
- rBrowser — встроенный Nomadnet браузер
- Веб-дашборд с мониторингом и управлением
- Все адреса шлюза в одном месте (вкладка Addresses)
- Редактирование конфигов через браузер без SSH
- Телеметрия RNode
- Проверка версии RNS и обновление в один клик

---

## Архитектура

```
Смартфон ──BT──▶ RNode ──LoRa──▶ NOEMA RNSGate Lite ──MQTT──▶ Home Assistant
                                          │
                                   I2P / TCP / LAN
                                          │
                                    Другой шлюз
                                          │
                                      Nomadnet
```

---

## Установка

Требования: Debian/Ubuntu, Python 3.10+, root.

Подключитесь по SSH к вашему шлюзу и выполните:

```bash
git clone https://github.com/e2ret/NOEMA-RNSGate-Lite.git && cd NOEMA-RNSGate-Lite && sudo bash install.sh
```

Скрипт автоматически:
- Клонирует репозиторий и устанавливает зависимости
- Спрашивает параметры MQTT брокера (IP, порт, логин, пароль)
- Настраивает все сервисы
- Создаёт и запускает systemd сервисы

---

## Первое подключение

1. Подключите Ethernet-кабель к роутеру
2. Найдите устройство в списке клиентов роутера
3. Откройте браузер: `http://IP_ШЛЮЗА:8081`
4. SSH: `ssh root@IP_ШЛЮЗА` (пароль по умолчанию: `1234`)

Настройка Wi-Fi:
```bash
nmtui
```

---

## Веб-дашборд

| Раздел | Описание |
|--------|----------|
| Services | Статус сервисов |
| Configs | Редактирование конфигов с бэкапом |
| Addresses | Все адреса шлюза |
| Monitor | Лог LXMF сообщений + RNS интерфейсы |
| RNode | Телеметрия LoRa |
| Network | Публичные узлы + RNprobe |
| I2P | Анонимная сеть |
| Nomadnet | Страница-визитка, редактор, Micron Composer |
| Browser | Встроенный Nomadnet браузер (rBrowser) |
| Logs | Журналы сервисов |
| System | Команды, бэкап, обновление RNS, сброс identity |

---

## Сервисы

| Сервис | Описание |
|--------|----------|
| `rnsd` | Reticulum Network Stack |
| `dashboard` | Веб-интерфейс :8081 |
| `lxmf_bridge_mqtt` | Мост LXMF ↔ MQTT |
| `i2pd` | I2P демон |
| `nomadnet` | Nomadnet Node |
| `rbrowser` | Nomadnet Browser :5000 |

Проверка:
```bash
systemctl status rnsd dashboard lxmf_bridge_mqtt i2pd nomadnet rbrowser
```

---

## Настройка MQTT

`Dashboard → Configs → lxmf_bridge_mqtt`

```ini
[mqtt]
host = 192.168.1.100
port = 1883
username = username
password = password
```

После изменений нажмите **Save** в дашборде — сервис перезапустится автоматически.

Пример автоматизации Home Assistant:

```yaml
trigger:
  - platform: mqtt
    topic: message/lxmf/receive
action:
  - service: mqtt.publish
    data:
      topic: message/lxmf/send
      payload: >
        {{ {
          "destination": trigger.payload_json.source,
          "content": "Ответ!"
        } | to_json }}
```

---

## Настройка LoRa / RNode

`Dashboard → Configs → Reticulum`

```ini
[[RNode]]
  type = RNodeInterface
  enabled = yes
  port = /dev/ttyUSB0
  frequency = 869525000
  bandwidth = 125000
  txpower = 17
  spreadingfactor = 9
  codingrate = 8
```

Найти порт: `Dashboard → System → Ports`

---

## Подключение клиентов

**Sideband (iOS / Android)**
```
Settings → Interfaces → Add Interface → TCP Client
Host: IP_ШЛЮЗА  Port: 4242
```

**MeshChat / Retichat**
```
Host: IP_ШЛЮЗА  Port: 4242
```

---

## Addresses

Вкладка Addresses содержит все адреса шлюза:

| Адрес | Описание |
|-------|----------|
| LXMF Bridge | Приём команд из Reticulum → MQTT. Добавьте в Sideband как контакт |
| I2P (b32) | Анонимное подключение без публичного IP |
| Nomadnet Node | Адрес страницы-визитки |
| Nomadnet Chat | IRC-style чат |

---

## I2P

`Dashboard → I2P`

1. Нажмите **Setup Reticulum tunnel in i2pd**
2. Подождите 2–5 минут, пока появится b32-адрес
3. Обменяйтесь адресами с другим шлюзом
4. Добавьте его b32 → **Add to config**
5. Начните обмен LXMF-сообщениями

> ⚠️ Первичная стабилизация сети занимает 5–10 минут. Переподключения каждые ~2 мин — норма.

---

## Страница Nomadnet

Шлюз автоматически публикует страницу-визитку. Открыть в любом Nomadnet клиенте:

```
<node_address>:/page/index.mu
```

Редактирование: `Dashboard → Nomadnet → Page Editor`

**Основы разметки Micron:**
```
`c          — центрирование
`f...`f     — крупный шрифт
`b...`b     — жирный
`[Заголовок`] — раздел
---         — разделитель
```

Используйте [Micron Composer](https://fr33n0w.github.io/micron-composer/) для визуального редактирования — кнопка доступна прямо во вкладке Nomadnet.

---

## Nomadnet Browser

`Dashboard → Browser`

Встроенный браузер для просмотра Nomadnet страниц без установки дополнительных приложений. Работает на порту 5000. Также доступен напрямую:

```
http://IP_ШЛЮЗА:5000
```

Возможности: мультитаб, избранное, список известных нод, ping, поиск.

Основан на [rBrowser](https://github.com/fr33n0w/rBrowser) — fr33n0w, MIT.

---

## Типовые сценарии

**Браузер по LAN**
```
ПК/Телефон ──Wi-Fi──▶ NOEMA RNSGate
```
Без настройки. Открыть: `http://IP_ШЛЮЗА:8081`

**Sideband по TCP**
```
Смартфон ──TCP──▶ NOEMA RNSGate
```
Нужен интернет, порт 4242.

**Два шлюза через I2P**
```
RNSGate ──I2P──▶ RNSGate
```
Анонимно, без публичного IP.

**LoRa → Шлюз → I2P**
```
Смартфон ──BT──▶ RNode ──LoRa──▶ RNSGate ──▶ I2P
```
Смартфон офлайн, интернет только на шлюзе.

**Wi-Fi → Шлюз → I2P**
```
Смартфон ──Wi-Fi──▶ RNSGate ──▶ I2P
```
Мобильный интернет не нужен.

---

## Проверка версии RNS

`Dashboard → System → RNS Version`

Показывает установленную и актуальную версию с PyPI. При наличии обновления появляется кнопка **Update RNS** — обновление без SSH.

---

## Backup & Restore

`Dashboard → System → Download Backup` — ZIP с конфигами и ключами  
`Dashboard → System → Restore` — восстановление из архива

---

## Сброс идентификаторов

`Dashboard → System → Reset All Identity`

Используйте перед продажей шлюза. Удаляет все identity, ключи, историю. Сохраняет конфиги и страницы Nomadnet.

Что удаляется:
- LXMF Bridge identity и ключи
- Reticulum identity
- I2P ключи (новый b32 после сброса)
- Nomadnet identity (новый адрес node)

Что сохраняется:
- Конфигурация Reticulum и MQTT
- Страницы Nomadnet

> ⚠️ Необратимо. Сделайте бэкап заранее.

---

## Расположение файлов

```
~/lxmf-tools/config.cfg.owr              — конфиг MQTT
~/.reticulum/config                       — конфиг Reticulum / LoRa
~/lxmf-tools/identity                     — ключ LXMF Bridge
~/.nomadnetwork/storage/pages/index.mu    — главная страница Nomadnet
~/.nomadnetwork/config                    — конфиг Nomadnet
```

---

## Устранение неполадок

| Проблема | Решение |
|----------|---------|
| LoRa не определяется | `ls /dev/ttyUSB* /dev/ttyACM*`, проверь `port` в конфиге |
| Ошибка MQTT | Проверь IP, порт, username, password |
| Сервис упал | `journalctl -u <сервис> -n 20 --no-pager` |
| Нет маршрута к контакту | `systemctl restart rnsd`, подожди 30 сек |
| Dashboard не открывается | `systemctl restart dashboard` |
| I2P нестабилен | Подожди 5–10 минут после запуска |

---

## Используемые компоненты

- [Reticulum (RNS)](https://github.com/markqvist/Reticulum) — Mark Qvist, MIT
- [LXMF](https://github.com/markqvist/LXMF) — Mark Qvist, MIT
- [Nomadnet](https://github.com/markqvist/NomadNet) — Mark Qvist, GPL-3.0
- [Flask](https://flask.palletsprojects.com/) — Pallets, BSD
- [paho-mqtt](https://github.com/eclipse/paho.mqtt.python) — Eclipse, EPL/EDL
- [rBrowser](https://github.com/fr33n0w/rBrowser) — fr33n0w, MIT
- [lxmf-tools](https://github.com/SebastianObi/LXMF-Tools) — SebastianObi
- [i2pd](https://github.com/PurpleI2P/i2pd) — PurpleI2P, BSD

---

## Благодарности

- **Mark Qvist** — Reticulum, LXMF, Nomadnet
- **SebastianObi** — lxmf-tools
- **fr33n0w** — rBrowser
- **PurpleI2P Team** — i2pd

Спасибо всем разработчикам, благодаря которым экосистема Reticulum продолжает развиваться.
