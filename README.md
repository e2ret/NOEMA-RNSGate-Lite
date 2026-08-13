# NOEMA RNSGate — Интеграция с Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
![Version](https://img.shields.io/badge/version-1.0.0-teal)
![HA](https://img.shields.io/badge/HA-2024.1+-blue)

Интеграция и Lovelace карточка для Home Assistant для работы с NOEMA RNSGate Lite — шлюзом сети Reticulum с поддержкой LoRa радио, LXMF мессенджера, MQTT моста, I2P и Nomadnet.

<p align="left">
  <img src="https://github.com/e2ret/NOEMA-RNSGate-HA/blob/main/docs/card.png" width="300" alt="NOEMA RNSGate HA">
</p>

---

## Возможности

**Интеграция (`noema_rnsgate`):**
- Метрики системы — CPU, RAM, Диск, Температура, IP, Uptime
- Статус сервисов — rnsd, lxmf_bridge_mqtt, i2pd, nomadnet, rbrowser
- Статус подключения к MQTT брокеру
- Статистика LXMF — отправлено, получено, всего
- Адреса шлюза — LXMF Bridge, I2P b32, Nomadnet нода
- Версия RNS с определением наличия обновлений
- Кнопки перезапуска каждого сервиса

**Lovelace карточка (`noema-rnsgate-card`):**
- Автоматическое обнаружение всех сущностей по префиксу интеграции
- Индикаторы CPU, RAM, Диска, Температуры
- Статус сервисов с кнопками перезапуска
- Диалог подтверждения перед перезапуском сервисов
- Информация и статистика LXMF Bridge
- Статус MQTT
- Версия RNS с индикатором обновления
- Не требует ручной настройки сущностей

---

## Требования

- NOEMA RNSGate Lite в локальной сети
- Home Assistant 2024.1+
- HACS

---

## Установка

### Интеграция через HACS

1. HACS → **Интеграции** → ⋮ → **Пользовательские репозитории**
2. Добавить `https://github.com/e2ret/NOEMA-RNSGate-HA` → Категория: **Интеграция**
3. Найти **NOEMA RNSGate** → Установить
4. Перезапустить Home Assistant
5. **Настройки → Интеграции → Добавить → NOEMA RNSGate**

### Lovelace карточка — установка вручную

Скачайте `www/noema-rnsgate-card.js` и скопируйте в конфиг HA:

```bash
cp noema-rnsgate-card.js /config/www/
```

Добавьте ресурс в HA: **Настройки → Дашборды → Ресурсы → Добавить**
- URL: `/local/noema-rnsgate-card.js`
- Тип: JavaScript module

---

## Настройка интеграции

**Настройки → Интеграции → Добавить → NOEMA RNSGate**

| Поле | Описание | По умолчанию |
|------|----------|--------------|
| Host | IP адрес шлюза | — |
| Port | Порт дашборда | 8081 |
| Name | Имя устройства в HA | NOEMA RNSGate |

---

## Использование карточки

```yaml
type: custom:noema-rnsgate-card
title: NOEMA RNSGate Lite
prefix: noema_rnsgate_noema
```

| Параметр | Описание | По умолчанию |
|----------|----------|--------------|
| `title` | Заголовок карточки | NOEMA RNSGate Lite |
| `prefix` | Префикс entity ID | noema_rnsgate_noema |

`prefix` — общая часть ID сущностей. Если сущности называются `sensor.noema_rnsgate_noema_cpu_usage`, префикс: `noema_rnsgate_noema`.

---

## Сущности

### Сенсоры
| Сущность | Описание |
|----------|----------|
| `sensor.*_cpu_usage` | Загрузка CPU % |
| `sensor.*_ram_usage` | Использование RAM % |
| `sensor.*_disk_usage` | Использование диска % |
| `sensor.*_cpu_temperature` | Температура CPU °C |
| `sensor.*_uptime` | Время работы системы |
| `sensor.*_ip_address` | IP адрес шлюза |
| `sensor.*_rns_version` | Установленная версия RNS |
| `sensor.*_rns_latest` | Последняя версия RNS на PyPI |
| `sensor.*_lxmf_sent` | Отправлено LXMF сообщений |
| `sensor.*_lxmf_received` | Получено LXMF сообщений |
| `sensor.*_lxmf_total` | Всего LXMF сообщений |
| `sensor.*_lxmf_bridge_address` | Адрес LXMF Bridge |
| `sensor.*_i2p_address` | I2P b32 адрес |
| `sensor.*_nomadnet_address` | Адрес Nomadnet ноды |

### Бинарные сенсоры
| Сущность | Описание |
|----------|----------|
| `binary_sensor.*_mqtt_broker` | Подключение к MQTT брокеру |
| `binary_sensor.*_rns_update_available` | Доступно обновление RNS |
| `binary_sensor.*_rnsd` | Статус сервиса rnsd |
| `binary_sensor.*_lxmf_bridge_mqtt` | Статус lxmf_bridge_mqtt |
| `binary_sensor.*_i2pd` | Статус сервиса i2pd |
| `binary_sensor.*_nomadnet` | Статус сервиса nomadnet |
| `binary_sensor.*_rbrowser` | Статус сервиса rbrowser |

### Кнопки
| Сущность | Описание |
|----------|----------|
| `button.*_restart_rnsd` | Перезапустить rnsd |
| `button.*_restart_lxmf_bridge_mqtt` | Перезапустить LXMF Bridge |
| `button.*_restart_i2pd` | Перезапустить i2pd |
| `button.*_restart_nomadnet` | Перезапустить Nomadnet |
| `button.*_restart_rbrowser` | Перезапустить rBrowser |
| `button.*_restart_dashboard` | Перезапустить дашборд |
| `button.*_restart_all` | Перезапустить все сервисы |

---

## Лицензия

MIT
