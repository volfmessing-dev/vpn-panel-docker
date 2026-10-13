# VPN Panel — Docker

Панель управления MikroTik, облачным WireGuard-шлюзом и выходными серверами AmneziaWG. FastAPI + PostgreSQL + React + Traefik.

Репозиторий содержит только исходный код и универсальные примеры. При первом запуске база, реестр узлов, пользователи и bypass-списки пусты. Личные адреса, ключи, пароли, резервные копии, конфигурации серверов и прежняя Git-история не включены.

Панель управляет конфигурацией удалённых узлов через SSH; VPN-трафик через её контейнеры не проходит. WireGuard/AmneziaWG устанавливаются на VPN-узлах отдельно. Кнопки «Применить», создание узла с AWG-туннелем и удаление узлов могут менять настройки удалённых серверов.

## Быстрая установка

Требуются Docker Engine, Docker Compose v2, Python 3 и Git. На Linux установите Docker из [официальной инструкции](https://docs.docker.com/engine/install/), на macOS/Windows — Docker Desktop. Серверу панели достаточно начать с 2 CPU и 2 GB RAM; фактический расход зависит от размера реестра.

```bash
git clone https://github.com/volfmessing-dev/vpn-panel-docker.git
cd vpn-panel-docker
python3 scripts/setup.py
docker compose up -d --build
docker compose ps
```

Скрипт попросит новый пароль панели (логин `admin`), создаст случайный пароль PostgreSQL и локальные файлы `.env`, `traefik/users.htpasswd`, `secrets/ssh/known_hosts`. Повторный запуск не перезаписывает существующие настройки.

Откройте `http://localhost:8080`. По умолчанию порт доступен только на самом хосте. На удалённом сервере используйте SSH-туннель с вашего компьютера:

```bash
ssh -N -L 8080:127.0.0.1:8080 USER@SERVER
```

Затем откройте тот же адрес `http://localhost:8080` на компьютере. Домен не требуется. Замените USER и SERVER своими значениями. Для публичного доступа настройте HTTPS по инструкции ниже: Basic Auth по обычному HTTP не защищает пароль от перехвата.

Подробное руководство: [установка и настройка](docs/INSTALL.md). Описание состава обезличенной версии: [SANITIZATION.md](docs/SANITIZATION.md).
