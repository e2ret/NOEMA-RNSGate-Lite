# NOEMA RNSGate Lite — LoRa · MQTT · I2P · Nomadnet

<p align="left">
  <img src="https://github.com/e2ret/NOEMA-RNSGate-Lite/blob/main/001.png" width="800" alt="NOEMA RNSGate Lite">
</p>

**Reticulum Mesh Gateway** — лёгкий шлюз для сети Reticulum, объединяющий радиосвязь LoRa, LXMF мессенджер, MQTT-интеграцию с Home Assistant, анонимную сеть I2P, Nomadnet и современный веб-интерфейс управления.

> **Lite** версия — без встроенного LXMF Chat, без Group Chat, без карты RMAP. Предназначена для минимального потребления ресурсов на маломощном железе.

---

## ⚠️ Важно

Это устройство для технически подготовленных пользователей. Проект создан в личных целях и распространяется **как есть**, без гарантий работоспособности.

Для работы необходимо понимание основ: Linux, TCP/IP, MQTT, базовое администрирование.

Автор не несёт ответственности за сбои, потерю данных или любые иные последствия использования.

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

## Используемые компоненты

- [Reticulum (RNS)](https://github.com/markqvist/Reticulum) — Mark Qvist, MIT
- [LXMF](https://github.com/markqvist/LXMF) — Mark Qvist, MIT
- [Nomadnet](https://github.com/markqvist/NomadNet) — Mark Qvist, GPL-3.0
- [Flask](https://flask.palletsprojects.com/) — Pallets, BSD
- [paho-mqtt](https://github.com/eclipse/paho.mqtt.python) — Eclipse, EPL/EDL
- [rBrowser](https://github.com/fr33n0w/rBrowser) — fr33n0w, MIT
- [i2pd](https://github.com/PurpleI2P/i2pd) — PurpleI2P, BSD

---

## Благодарности

- **Mark Qvist** — Reticulum, LXMF, Nomadnet
- **fr33n0w** — rBrowser
- **PurpleI2P Team** — i2pd

Спасибо всем разработчикам, благодаря которым экосистема Reticulum продолжает развиваться.
