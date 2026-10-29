# Smart University — система бронирования лабораторного оборудования

![CI](../../actions/workflows/ci.yml/badge.svg)

Веб-приложение и REST API для бронирования лабораторного оборудования университета.
Студенты и преподаватели смотрят свободное время и подают заявки, система **автоматически
находит пересечения по времени**, преподаватели и администраторы одобряют или отклоняют
заявки, все изменения сохраняются в истории, пользователи получают уведомления.

**Стек:** Python 3.12 · FastAPI · PostgreSQL 16 · SQLAlchemy 2.0 · JWT · pytest · Postman · Docker · GitHub Actions

---

## Возможности

| Роль | Что может |
|---|---|
| **Студент** | регистрация и вход, просмотр оборудования и свободного времени, создание заявки, отмена своей брони, история и уведомления |
| **Преподаватель** | всё, что студент + одобрение / отклонение заявок **студентов** |
| **Администратор** | управление лабораториями, оборудованием (статусы: доступно / обслуживание / списано), пользователями и ролями, рассмотрение любых заявок, статистика |

Правила бронирования:

- время работы лабораторий — 08:00–20:00, длительность брони 30 минут – 4 часа, в пределах одного дня;
- нельзя бронировать в прошлом и более чем на 30 дней вперёд;
- нельзя бронировать оборудование на обслуживании или списанное;
- **конфликт времени**: новая заявка отклоняется (HTTP 409), если пересекается с бронью в статусе
  `pending` или `approved` для того же оборудования. Соседние интервалы (10:00–11:00 и 11:00–12:00) допустимы;
- статусы брони: `pending → approved | rejected | cancelled`, `approved → cancelled`;
- каждое изменение статуса пишется в `booking_history`, заявитель получает уведомление.

Все параметры (часы работы, лимиты) настраиваются переменными окружения — см. `app/config.py`.

---

## Быстрый старт (Docker)

```bash
git clone <URL репозитория>
cd smart-university
cp .env.example .env          # при необходимости поменяйте пароли и SECRET_KEY
docker compose up -d --build
```

Откройте:

- веб-интерфейс — http://localhost:8000
- Swagger UI — http://localhost:8000/docs
- ReDoc — http://localhost:8000/redoc
- health-check — http://localhost:8000/api/health

Демо-аккаунты (создаются при `SEED_DEMO_DATA=true`):

| Роль | Email | Пароль |
|---|---|---|
| Администратор | admin@smartuni.kz | Admin12345 |
| Преподаватель | teacher@smartuni.kz | Teacher123 |
| Студент | student@smartuni.kz | Student123 |

Тесты внутри Docker:

```bash
docker compose --profile test run --rm tests
```

Остановить и удалить данные: `docker compose down -v`.

---

## Локальный запуск без Docker

Нужны Python 3.11+ и PostgreSQL.

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

# создать пользователя и базы в PostgreSQL
psql -U postgres -c "CREATE USER smartuni WITH PASSWORD 'smartuni';"
psql -U postgres -c "CREATE DATABASE smart_university OWNER smartuni;"
psql -U postgres -c "CREATE DATABASE smart_university_test OWNER smartuni;"

export SEED_DEMO_DATA=true           # Windows PowerShell: $env:SEED_DEMO_DATA="true"
uvicorn app.main:app --reload
```

Таблицы и администратор создаются автоматически при старте.

---

## Тестирование

```bash
pytest -v --cov=app --cov-report=term-missing
```

- `tests/unit/` — бизнес-правила без БД: пересечение интервалов, правила времени,
  расчёт свободных слотов, конечный автомат статусов, хеширование паролей, JWT;
- `tests/integration/` — запросы к API через `TestClient` на реальной PostgreSQL:
  регистрация и вход, роли (403), конфликты (409), согласование, отмена, история,
  уведомления, статистика, ошибки валидации (400 / 404 / 422).

Результат: **56 тестов, покрытие кода ≈ 95 %.**

### Postman

Коллекция: `postman/SmartUniversity.postman_collection.json` (29 запросов с автотестами).
Импортируйте её в Postman и запустите через **Collection Runner** по порядку —
токены и id сохраняются в переменные коллекции автоматически. Нужны демо-данные.

---

## CI/CD (GitHub Actions)

`.github/workflows/ci.yml` запускается на каждый push и pull request:

1. **lint** — `ruff check` и `ruff format --check` (стиль и качество кода);
2. **test** — pytest с сервисом PostgreSQL 16, отчёты покрытия и JUnit сохраняются как артефакты;
3. **docker** — `docker compose up --build`, проверка `/api/health`, тесты внутри контейнера.

---

## API (основные endpoint'ы)

| Метод | Путь | Доступ | Описание |
|---|---|---|---|
| POST | `/api/auth/register` | все | регистрация (student / teacher) |
| POST | `/api/auth/login` | все | вход, выдаёт JWT |
| GET | `/api/auth/me` | авторизованные | текущий пользователь |
| GET | `/api/laboratories` | авторизованные | список лабораторий |
| POST/PATCH/DELETE | `/api/laboratories[/{id}]` | админ | управление лабораториями |
| GET | `/api/equipment?laboratory_id=&status=&q=` | авторизованные | оборудование с фильтрами |
| GET | `/api/equipment/{id}/availability?day=` | авторизованные | занятые и свободные интервалы |
| POST/PATCH/DELETE | `/api/equipment[/{id}]` | админ | управление оборудованием |
| POST | `/api/bookings` | студент, преподаватель | создать заявку (проверка конфликтов) |
| GET | `/api/bookings/my` | авторизованные | мои брони |
| GET | `/api/bookings?status=&day=` | преподаватель, админ | все заявки |
| POST | `/api/bookings/{id}/approve` · `/reject` | преподаватель, админ | рассмотреть заявку |
| POST | `/api/bookings/{id}/cancel` | владелец, админ | отменить |
| GET | `/api/bookings/{id}/history` | владелец, персонал | журнал статусов |
| GET | `/api/notifications` · POST `/read-all` | авторизованные | уведомления |
| GET/PATCH | `/api/users[/{id}]` | админ | пользователи и роли |
| GET | `/api/stats` | админ | статистика |
| GET | `/api/health` | все | проверка работы |

Всего 29 операций. Полное описание со схемами — в Swagger UI.

---

## Структура проекта

```
smart-university/
├── app/
│   ├── main.py              # FastAPI-приложение, обработчики ошибок, статика
│   ├── config.py            # настройки из переменных окружения
│   ├── database.py          # подключение к PostgreSQL
│   ├── models.py            # ORM-модели (6 таблиц)
│   ├── schemas.py           # Pydantic-схемы и валидация
│   ├── security.py          # PBKDF2-хеширование паролей, JWT
│   ├── deps.py              # текущий пользователь, проверка ролей (RBAC)
│   ├── seed.py              # администратор и демо-данные
│   ├── services/
│   │   ├── booking_service.py   # бизнес-логика бронирования
│   │   └── errors.py            # доменные исключения
│   ├── routers/             # auth, users, laboratories, equipment, bookings, notifications, stats
│   └── static/              # веб-интерфейс (HTML, CSS, JS)
├── tests/unit/ · tests/integration/
├── postman/                 # Postman-коллекция
├── docs/diagrams/           # UML и ER (PlantUML + PNG + SVG)
├── docs/screenshots/        # скриншоты интерфейса
├── Dockerfile · docker-compose.yml · .env.example
├── .github/workflows/ci.yml
└── requirements.txt · requirements-dev.txt · pyproject.toml
```

## База данных

Таблицы: `users`, `laboratories`, `equipment`, `bookings`, `booking_history`, `notifications`.
ER-диаграмма — `docs/diagrams/png/er.png`.

## Диаграммы

| Диаграмма | Файл |
|---|---|
| Use Case | `docs/diagrams/png/use_case.png` |
| Activity (процесс бронирования) | `docs/diagrams/png/activity_booking.png` |
| Class | `docs/diagrams/png/class.png` |
| Component | `docs/diagrams/png/component.png` |
| Deployment | `docs/diagrams/png/deployment.png` |
| ER | `docs/diagrams/png/er.png` |
| Sequence (создание брони) | `docs/diagrams/png/sequence_booking.png` |

Исходники — `docs/diagrams/*.puml` (PlantUML).

## Безопасность

- пароли хранятся как PBKDF2-SHA256 с солью (390 000 итераций), сравнение за постоянное время;
- JWT (HS256) с ограниченным сроком действия, ключ задаётся через `SECRET_KEY`;
- ролевой доступ на уровне каждого endpoint'а; студент не видит чужие брони;
- защита от гонок: строка оборудования блокируется (`SELECT … FOR UPDATE`) при создании брони;
- ORM исключает SQL-инъекции, веб-интерфейс экранирует вывод (XSS).

## Ограничения и развитие

- нет миграций Alembic (таблицы создаются `create_all`) — следующий шаг;
- уведомления только внутри системы — можно добавить e-mail / Telegram;
- регистрация преподавателя без подтверждения — в проде роль выдаёт администратор;
- идеи: повторяющиеся брони (каждый вторник), календарь лаборатории, QR-код на оборудовании,
  отчёты по загрузке в Excel, интеграция с университетским SSO.
