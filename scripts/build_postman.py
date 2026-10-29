"""Генерирует Postman-коллекцию postman/SmartUniversity.postman_collection.json.

Запуск: python scripts/build_postman.py
"""

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "postman"


def req(name, method, path, token=None, body=None, form=None, tests=(), query=None):
    url_path = path.lstrip("/").split("?")[0].split("/")
    raw = "{{baseUrl}}/" + path.lstrip("/")
    url = {"raw": raw, "host": ["{{baseUrl}}"], "path": url_path}
    if query:
        url["query"] = [{"key": k, "value": v} for k, v in query.items()]
        url["raw"] += "?" + "&".join(f"{k}={v}" for k, v in query.items())
    request = {"method": method, "header": [], "url": url}
    if token:
        request["auth"] = {"type": "bearer", "bearer": [{"key": "token", "value": "{{" + token + "}}"}]}
    else:
        request["auth"] = {"type": "noauth"}
    if body is not None:
        request["header"].append({"key": "Content-Type", "value": "application/json"})
        request["body"] = {"mode": "raw", "raw": json.dumps(body, ensure_ascii=False, indent=2)}
    if form is not None:
        request["body"] = {
            "mode": "urlencoded",
            "urlencoded": [{"key": k, "value": v, "type": "text"} for k, v in form.items()],
        }
    item = {"name": name, "request": request}
    if tests:
        item["event"] = [{"listen": "test", "script": {"type": "text/javascript", "exec": list(tests)}}]
    return item


def status(code):
    return f'pm.test("Статус {code}", () => pm.response.to.have.status({code}));'


def save(var, expr):
    return f'pm.collectionVariables.set("{var}", {expr});'


PRE_REQUEST = [
    "// Дата «завтра» в формате YYYY-MM-DD для броней",
    "const d = new Date(Date.now() + 24 * 3600 * 1000);",
    "const pad = (n) => String(n).padStart(2, '0');",
    "pm.collectionVariables.set('tomorrow', `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`);",
]

folders = [
    {
        "name": "1. Авторизация",
        "item": [
            req(
                "Регистрация студента",
                "POST",
                "/api/auth/register",
                body={
                    "full_name": "Тестовый Студент",
                    "email": "student{{$timestamp}}@smartuni.kz",
                    "password": "Student123",
                    "role": "student",
                },
                tests=[
                    status(201),
                    'pm.test("Пароль не возвращается", () => '
                    'pm.expect(pm.response.json()).to.not.have.property("password_hash"));',
                ],
            ),
            req(
                "Регистрация: слабый пароль (422)",
                "POST",
                "/api/auth/register",
                body={"full_name": "Тест", "email": "weak@smartuni.kz", "password": "abc", "role": "student"},
                tests=[status(422)],
            ),
            req(
                "Вход администратора",
                "POST",
                "/api/auth/login",
                form={"username": "{{adminEmail}}", "password": "{{adminPassword}}"},
                tests=[status(200), save("adminToken", "pm.response.json().access_token")],
            ),
            req(
                "Вход преподавателя",
                "POST",
                "/api/auth/login",
                form={"username": "teacher@smartuni.kz", "password": "Teacher123"},
                tests=[status(200), save("teacherToken", "pm.response.json().access_token")],
            ),
            req(
                "Вход студента",
                "POST",
                "/api/auth/login",
                form={"username": "student@smartuni.kz", "password": "Student123"},
                tests=[status(200), save("studentToken", "pm.response.json().access_token")],
            ),
            req(
                "Вход: неверный пароль (401)",
                "POST",
                "/api/auth/login",
                form={"username": "student@smartuni.kz", "password": "Wrong1234"},
                tests=[status(401)],
            ),
            req(
                "Текущий пользователь",
                "GET",
                "/api/auth/me",
                token="studentToken",
                tests=[
                    status(200),
                    'pm.test("Роль student", () => pm.expect(pm.response.json().role).to.eql("student"));',
                ],
            ),
            req("Без токена (401)", "GET", "/api/equipment", tests=[status(401)]),
        ],
    },
    {
        "name": "2. Лаборатории и оборудование",
        "item": [
            req("Список лабораторий", "GET", "/api/laboratories", token="studentToken", tests=[status(200)]),
            req(
                "Создать лабораторию (админ)",
                "POST",
                "/api/laboratories",
                token="adminToken",
                body={"name": "Лаборатория {{$timestamp}}", "building": "Корпус D", "room": "101"},
                tests=[status(201), save("labId", "pm.response.json().id")],
            ),
            req(
                "Создать оборудование (админ)",
                "POST",
                "/api/equipment",
                token="adminToken",
                body={
                    "name": "Микроскоп Levenhuk",
                    "inventory_number": "BIO-{{$timestamp}}",
                    "category": "Оптика",
                    "laboratory_id": "{{labId}}",
                },
                tests=[status(201), save("equipmentId", "pm.response.json().id")],
            ),
            req(
                "Студент не может добавить оборудование (403)",
                "POST",
                "/api/equipment",
                token="studentToken",
                body={"name": "X", "inventory_number": "X-1", "category": "XX", "laboratory_id": "{{labId}}"},
                tests=[status(403)],
            ),
            req("Список оборудования", "GET", "/api/equipment", token="studentToken", tests=[status(200)]),
            req(
                "Поиск и фильтр",
                "GET",
                "/api/equipment",
                token="studentToken",
                query={"status": "available", "q": "Микроскоп"},
                tests=[status(200)],
            ),
            req(
                "Свободное время на завтра",
                "GET",
                "/api/equipment/{{equipmentId}}/availability",
                token="studentToken",
                query={"day": "{{tomorrow}}"},
                tests=[
                    status(200),
                    'pm.test("Есть свободные слоты", () => pm.expect(pm.response.json().free.length).to.be.above(0));',
                ],
            ),
        ],
    },
    {
        "name": "3. Бронирование",
        "item": [
            req(
                "Создать бронь (студент)",
                "POST",
                "/api/bookings",
                token="studentToken",
                body={
                    "equipment_id": "{{equipmentId}}",
                    "start_time": "{{tomorrow}}T10:00:00",
                    "end_time": "{{tomorrow}}T12:00:00",
                    "purpose": "Лабораторная работа №3",
                },
                tests=[
                    status(201),
                    'pm.test("Статус pending", () => pm.expect(pm.response.json().status).to.eql("pending"));',
                    save("bookingId", "pm.response.json().id"),
                ],
            ),
            req(
                "Конфликт времени (409)",
                "POST",
                "/api/bookings",
                token="teacherToken",
                body={
                    "equipment_id": "{{equipmentId}}",
                    "start_time": "{{tomorrow}}T11:00:00",
                    "end_time": "{{tomorrow}}T13:00:00",
                    "purpose": "Пересекающаяся бронь",
                },
                tests=[status(409)],
            ),
            req(
                "Вне рабочего времени (400)",
                "POST",
                "/api/bookings",
                token="studentToken",
                body={
                    "equipment_id": "{{equipmentId}}",
                    "start_time": "{{tomorrow}}T21:00:00",
                    "end_time": "{{tomorrow}}T22:00:00",
                    "purpose": "Ночная работа",
                },
                tests=[status(400)],
            ),
            req("Мои брони", "GET", "/api/bookings/my", token="studentToken", tests=[status(200)]),
            req(
                "Заявки на рассмотрение (преподаватель)",
                "GET",
                "/api/bookings",
                token="teacherToken",
                query={"status": "pending"},
                tests=[status(200)],
            ),
            req(
                "Студент не может одобрить (403)",
                "POST",
                "/api/bookings/{{bookingId}}/approve",
                token="studentToken",
                tests=[status(403)],
            ),
            req(
                "Одобрить заявку (преподаватель)",
                "POST",
                "/api/bookings/{{bookingId}}/approve",
                token="teacherToken",
                body={"comment": "Одобрено, приходите вовремя"},
                tests=[
                    status(200),
                    'pm.test("approved", () => pm.expect(pm.response.json().status).to.eql("approved"));',
                ],
            ),
            req(
                "История брони",
                "GET",
                "/api/bookings/{{bookingId}}/history",
                token="studentToken",
                tests=[
                    status(200),
                    'pm.test("2 записи", () => pm.expect(pm.response.json().length).to.eql(2));',
                ],
            ),
            req(
                "Отменить бронь (владелец)",
                "POST",
                "/api/bookings/{{bookingId}}/cancel",
                token="studentToken",
                tests=[
                    status(200),
                    'pm.test("cancelled", () => pm.expect(pm.response.json().status).to.eql("cancelled"));',
                ],
            ),
        ],
    },
    {
        "name": "4. Уведомления и статистика",
        "item": [
            req("Мои уведомления", "GET", "/api/notifications", token="studentToken", tests=[status(200)]),
            req(
                "Прочитать все",
                "POST",
                "/api/notifications/read-all",
                token="studentToken",
                tests=[status(200)],
            ),
            req("Статистика (админ)", "GET", "/api/stats", token="adminToken", tests=[status(200)]),
            req(
                "Статистика для студента (403)",
                "GET",
                "/api/stats",
                token="studentToken",
                tests=[status(403)],
            ),
            req("Health-check", "GET", "/api/health", tests=[status(200)]),
        ],
    },
]

collection = {
    "info": {
        "name": "Smart University API",
        "description": "Коллекция для тестирования системы бронирования лабораторного оборудования. "
        "Запускайте папки по порядку (Collection Runner). Нужны демо-данные (SEED_DEMO_DATA=true).",
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
    },
    "event": [{"listen": "prerequest", "script": {"type": "text/javascript", "exec": PRE_REQUEST}}],
    "variable": [
        {"key": "baseUrl", "value": "http://localhost:8000"},
        {"key": "adminEmail", "value": "admin@smartuni.kz"},
        {"key": "adminPassword", "value": "Admin12345"},
        {"key": "adminToken", "value": ""},
        {"key": "teacherToken", "value": ""},
        {"key": "studentToken", "value": ""},
        {"key": "labId", "value": ""},
        {"key": "equipmentId", "value": ""},
        {"key": "bookingId", "value": ""},
        {"key": "tomorrow", "value": ""},
    ],
    "item": folders,
}

if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    path = OUT / "SmartUniversity.postman_collection.json"
    path.write_text(json.dumps(collection, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(len(f["item"]) for f in folders)
    print(f"Сохранено {path} ({total} запросов)")
