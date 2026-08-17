# NOEMA RNSGate Lite
![RNS](https://img.shields.io/badge/RNS-1.4.2-teal) ![License](https://img.shields.io/badge/license-MIT-green) ![Platform](https://img.shields.io/badge/platform-Debian%20%7C%20Ubuntu-blue)

**Reticulum Mesh Gateway** — шлюз для сети Reticulum, объединяющий радиосвязь LoRa, LXMF мессенджер, MQTT-интеграцию с Home Assistant, анонимную сеть I2P, Nomadnet и современный веб-интерфейс управления.

---

## Возможности
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

---

## ⚠️ Важно
Проект создан в личных целях и распространяется **как есть**, без гарантий работоспособности. Требуется понимание основ: Linux, TCP/IP, MQTT, базовое администрирование.

---

## Установка
Требования: Debian/Ubuntu, Python 3.10+, root.
```bash
git clone https://github.com/e2ret/NOEMA-RNSGate-Lite.git && cd NOEMA-RNSGate-Lite && sudo bash install.sh
```
Скрипт автоматически устанавливает все зависимости, спрашивает параметры MQTT брокера и запускает systemd сервисы.

> **Примечание:** в процессе установки дважды потребуется нажать Enter — для инициализации Nomadnet и настройки cron-задач.

---

## Первое подключение
1. Подключите Ethernet-кабель к роутеру
2. Найдите устройство в списке клиентов роутера
3. Откройте браузер: `http://IP_ШЛЮЗА:8081`
4. SSH: `ssh root@IP_ШЛЮЗА` (пароль по умолчанию: `1234`)

---

## Документация
**[→ Полная документация в Wiki](https://github.com/e2ret/NOEMA-RNSGate-Lite/wiki)**

## Обсуждение
[→ Telegram](https://t.me/reticulum_belgorod/70)

---

## Используемые компоненты
- [Reticulum (RNS)](https://github.com/markqvist/Reticulum) — Mark Qvist, MIT
- [LXMF](https://github.com/markqvist/LXMF) — Mark Qvist, MIT
- [Nomadnet](https://github.com/markqvist/NomadNet) — Mark Qvist, GPL-3.0
- [lxmfy](https://github.com/lxmfy/lxmfy) — lxmfy, MIT
- [Flask](https://flask.palletsprojects.com/) — Pallets, BSD
- [paho-mqtt](https://github.com/eclipse/paho.mqtt.python) — Eclipse, EPL/EDL
- [rBrowser](https://github.com/fr33n0w/rBrowser) — fr33n0w, MIT
- [i2pd](https://github.com/PurpleI2P/i2pd) — PurpleI2P, BSD

---

## Благодарности
**Mark Qvist** — Reticulum, LXMF, Nomadnet · **fr33n0w** — rBrowser · **PurpleI2P Team** — i2pd

Спасибо всем разработчикам, благодаря которым экосистема Reticulum продолжает развиваться.
