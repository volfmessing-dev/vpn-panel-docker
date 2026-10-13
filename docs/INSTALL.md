# Установка и настройка

## 1. Что устанавливается

Docker Compose запускает PostgreSQL 16, backend на Python 3.12, frontend на nginx и Traefik с обязательной Basic Auth. Публичный порт имеет только Traefik. PostgreSQL и backend доступны внутри сети Compose. Миграции Alembic выполняются при старте backend.

Именованные volumes `postgres_data` и `backend_data` сохраняют базу и домены bypass между перезапусками. При TLS добавляется volume сертификатов. Не используйте `docker compose down -v`: эта команда уничтожает volumes и данные.

## 2. Настройки .env

Сначала выполните команды из README. Затем при необходимости измените `.env`:

| Переменная | Назначение |
| --- | --- |
| POSTGRES_DB / POSTGRES_USER | Имя базы и пользователя; задаются до первого старта |
| POSTGRES_PASSWORD | Случайный пароль, созданный setup.py; изменение файла не меняет пароль в уже существующей базе |
| PANEL_BIND_IP | 127.0.0.1 по умолчанию; для публичного HTTPS задайте 0.0.0.0 |
| PANEL_HTTP_PORT | 8080 для обычного режима |
| BACKEND_CORS_ORIGINS | Разрешённые origin через запятую, например http://localhost:8080 |
| VITE_API_BASE_URL | Оставьте пустым: браузер обращается к /api на том же адресе |
| SSH_KEY_PATH | Путь ключа внутри backend; /run/secrets/ssh/id_ed25519 |
| BYPASS_DOMAINS_PATH | /data/bypass-domains.txt, хранится в backend_data |
| BYPASS_CIDRS | Собственные IPv4 CIDR через запятую; по умолчанию пусто |
| PANEL_DOMAIN / ACME_EMAIL | Только для режима HTTPS |

Если меняете настройки backend, выполните `docker compose up -d --force-recreate backend`. Изменение VITE_API_BASE_URL требует пересборки frontend. Не добавляйте .env, ключи и дампы в Git.

## 3. Доступ к Linux-узлам

Панель должна иметь сетевой доступ к SSH-портам шлюза и выходных серверов. NAT, VPN и firewall настраиваются отдельно. Создайте отдельный ключ для панели:

```bash
ssh-keygen -t ed25519 -f secrets/ssh/id_ed25519 -N ''
chmod 700 secrets secrets/ssh
chmod 600 secrets/ssh/id_ed25519
ssh-copy-id -i secrets/ssh/id_ed25519.pub USER@NODE
```

Для каждого узла соберите публичный host key (`ssh-keyscan -p PORT NODE`), сверьте его fingerprint с сервером через доверенный канал (`ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` на сервере), затем сохраните проверенную строку в `secrets/ssh/known_hosts`. Сам по себе ssh-keyscan не подтверждает подлинность узла. Для нестандартного порта строка должна содержать `[NODE]:PORT`. Backend использует StrictHostKeyChecking=yes и не принимает неизвестные ключи автоматически.

SSH-пользователю требуются права на команды настройки сети через sudo без интерактивного пароля. Подготовьте права осознанно: панель выполняет привилегированные команды WireGuard, iptables, ipset и systemctl. На Linux-узлах нужны WireGuard, Python 3, iproute2, iptables, ipset, dnsutils (dig), util-linux (flock); на AWG-узлах также установленный AmneziaWG, awg и awg-quick. Установка контейнеров панели не устанавливает эти компоненты на узлах.

Проверьте доступ внутри backend:

```bash
docker compose exec backend ssh -i /run/secrets/ssh/id_ed25519 \
  -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=/run/secrets/ssh/known_hosts -p PORT USER@NODE true
```

## 4. Первый запуск панели

1. В разделе узлов добавьте облачный шлюз (роль RU Cloud — внутреннее имя роли, страна не имеет значения), MikroTik и выходные серверы. Введите свои адреса, SSH-пользователей и порты. Выберите «Без туннеля» при первоначальном добавлении, если пока хотите только сохранить узел.
2. Проверьте доступность и сведения узлов. MikroTik имеет проверку TCP; полноценное автоматическое применение RouterOS через API пока не реализовано. Сгенерированные команды MikroTik просмотрите и применяйте вручную после проверки.
3. Создайте WireGuard-туннель MikroTik → шлюз и AmneziaWG-туннель шлюз → выход. Просмотрите генерируемые конфигурации до применения. Выберите непересекающиеся сети, свободные порты и реальный LAN CIDR.
4. Настройте направления в разделе политики. Выход для bypass должен быть выбранным AWG-туннелем. Проверьте routes, NAT, firewall и фактический внешний IP на узлах. Установите отдельное fail-closed правило, запрещающее bypass-трафику выходить напрямую при недоступности туннеля; контейнер панели сам не обеспечивает этот запрет на маршрутизаторах.
5. Введите собственные домены в разделе bypass. Статические IPv4 CIDR задаются в BYPASS_CIDRS. Обновление ipset выполняется через staging и atomic swap. Пустой список допустим; готовых доменов или CIDR в репозитории нет.
6. Создайте VPN-пользователей, примените список на шлюзе и скачайте индивидуальные конфигурации/QR. Эти ключи создаются уже в вашей базе и должны оставаться приватными.

Универсальные исходные значения: клиентская сеть 10.90.0.0/24, LAN-пример 192.168.50.0/24, автоматически выделяемые WG/AWG-пулы 10.230.0.0/16 и 10.240.0.0/16. Это новые шаблоны, а не готовая конфигурация сети. Перед использованием убедитесь, что они не пересекаются с вашей сетью. Клиентская сеть и часть служебных интерфейсов сейчас являются константами в коде; для другой клиентской сети согласованно измените users.py и routing_policy.py перед сборкой. DNS клиентов по умолчанию 1.1.1.1.

Имена Exit_A, Exit_B, Exit_C — примеры с совместимыми интерфейсами awg1, awg4, awg3. Для других имён интерфейс определяется именем туннеля/портом. Названия с префиксом Archived_ исключены из автоматических проверок. Не переименовывайте подключённые узлы без проверки генерируемых имён интерфейсов.

## Добавление нового выходного сервера через веб-панель

Для авторизации нужен **публичный SSH-ключ панели с сервера, где работает backend**, а не ключ вашего компьютера и не VPN-ключ WireGuard/AmneziaWG. Приватный файл `id_ed25519` остаётся на сервере панели; на новый VPS копируется только публичная строка.

### 1. Получить публичный ключ панели

На сервере панели перейдите в каталог проекта и выполните:

```bash
cat secrets/ssh/id_ed25519.pub
```

Если `.pub` отсутствует, выведите публичную часть существующего приватного ключа:

```bash
ssh-keygen -y -f secrets/ssh/id_ed25519
```

Скопируйте всю строку `ssh-ed25519 AAAA…`. Не создавайте новый ключ поверх существующего: это нарушит доступ к уже подключённым узлам. При переопределённом `SSH_KEY_PATH` используйте соответствующий файл на хосте; по умолчанию `secrets/ssh/id_ed25519` монтируется в backend как `/run/secrets/ssh/id_ed25519`.

### 2. Авторизовать панель на новом VPS

Войдите на новый VPS под **тем пользователем, которого затем укажете в панели**, и выполните:

```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
nano ~/.ssh/authorized_keys
```

Добавьте скопированный публичный ключ отдельной строкой, сохранив существующие строки. Сохраните файл и задайте права:

```bash
chmod 600 ~/.ssh/authorized_keys
```

Альтернатива с сервера панели, если доступ по паролю уже работает:

```bash
ssh-copy-id -i secrets/ssh/id_ed25519.pub -p PORT USER@NODE
```

Замените `USER`, `NODE` и `PORT` пользователем, адресом и SSH-портом нового VPS. Порт должен быть доступен с сервера панели. Для автоматической настройки туннеля пользователю нужны права выполнения используемых сетевых команд через `sudo` без интерактивного пароля.

### 3. Добавить узел в интерфейсе

Перед проверкой SSH и созданием AWG-туннеля сохраните проверенный host key нового VPS в `secrets/ssh/known_hosts` по разделу 3 выше. Публичная версия использует `StrictHostKeyChecking=yes`: одного `authorized_keys` недостаточно. Для нестандартного порта запись имеет вид `[NODE]:PORT`.

1. Откройте **«Узлы» → «Добавить узел»**.
2. Укажите имя, роль **«Выходной сервер»**, IP/имя хоста, SSH-пользователя и SSH-порт (обычно `22`). Поля для SSH-пароля нет: панель использует свой ключ.
3. Выберите **«Туннель к RU Cloud»**: «Без туннеля» сохраняет только запись; WireGuard создаёт конфигурацию; **AmneziaWG создаёт и применяет туннель на серверах**.
4. Нажмите **«Создать узел»** и проверьте результат операции. Затем проверьте SSH-доступ и статус туннеля в карточке. Если применение завершилось ошибкой, запись узла могла уже сохраниться — проверьте сообщение перед повторным созданием.

SSH-доступ и активность VPN-туннеля — отдельные проверки. Успешная авторизация сама по себе не переключает bypass-трафик на новый выход.

## 5. HTTPS (необязательно)

Требуются собственное DNS-имя с A-записью на сервер и доступные с Интернета TCP 80/443. Укажите в `.env`:

```dotenv
PANEL_BIND_IP=0.0.0.0
PANEL_DOMAIN=panel.example.com
ACME_EMAIL=admin@example.com
BACKEND_CORS_ORIGINS=https://panel.example.com
```

Замените примеры своими значениями. Сгенерируйте локальную конфигурацию Traefik и переключите Compose:

```bash
python3 scripts/configure-tls.py
docker compose down
docker compose -f docker-compose.tls.yml up -d --build
```

TLS-файл — самостоятельный Compose, его не нужно объединять с основным. HTTP перенаправляется на HTTPS. При смене домена снова выполните configure-tls.py и перезапустите Traefik. В TLS-режиме ко всем дальнейшим командам Compose добавляйте `-f docker-compose.tls.yml`. Без домена используйте SSH-туннель из README.

## 6. Проверка и диагностика

```bash
docker compose ps
docker compose logs --tail=100 backend traefik
docker compose exec -T backend python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health').read().decode())"
curl -u admin http://localhost:8080/health
```

curl запросит пароль. Ожидается `{"status":"ok"}`. Ответ 401 без авторизации ожидаем. При 502 смотрите миграции и backend logs; при SSH-ошибке проверьте key path, known_hosts, SSH user/port и sudo. При проблемах сертификата проверьте DNS, firewall, ACME_EMAIL и logs Traefik. Не публикуйте сырые журналы: после настройки они могут содержать ваши адреса.

## 7. Обновление

Сделайте резервную копию, затем:

```bash
git pull --ff-only
docker compose up -d --build
```

Миграции выполнятся автоматически. Перед обновлением проверьте изменения кода; откат схемы не выполняется автоматически.

## 8. Резервная копия и перенос

```bash
mkdir -p backups
chmod 700 backups
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > backups/database.sql
chmod 600 backups/database.sql
docker compose exec -T backend cat /data/bypass-domains.txt > backups/bypass-domains.txt
```

Если домены ещё не сохранялись, последняя команда может сообщить, что файла нет — список пуст. Сохраните отдельно .env, traefik/users.htpasswd, secrets/ssh и локальную TLS-конфигурацию. Эти файлы и дамп содержат секреты; храните их в защищённом месте, вне репозитория.

На новом хосте скопируйте исходный код и локальные файлы, затем:

```bash
docker compose up -d postgres
docker compose exec -T postgres sh -c 'until pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"; do sleep 2; done'
docker compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" "$POSTGRES_DB"' < backups/database.sql
docker compose run --rm --no-deps -T backend sh -c 'cat > /data/bypass-domains.txt' < backups/bypass-domains.txt
docker compose up -d --build
```

Восстанавливайте в новую пустую базу. Сохранённые пароли должны соответствовать дампу и .env. После переноса проверьте reachability узлов с нового хоста.
