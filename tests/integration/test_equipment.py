"""Integration-тесты лабораторий и оборудования."""

from tests.conftest import auth, booking_payload


def test_admin_creates_laboratory_and_equipment(client, admin):
    lab = client.post(
        "/api/laboratories",
        json={"name": "Лаборатория химии", "building": "Б", "room": "105"},
        headers=auth(admin),
    )
    assert lab.status_code == 201
    item = client.post(
        "/api/equipment",
        json={
            "name": "Спектрофотометр",
            "inventory_number": "CHM-001",
            "category": "Аналитические приборы",
            "laboratory_id": lab.json()["id"],
        },
        headers=auth(admin),
    )
    assert item.status_code == 201
    assert item.json()["status"] == "available"
    assert item.json()["laboratory_name"] == "Лаборатория химии"


def test_student_and_teacher_cannot_modify_catalog(client, student, teacher, lab):
    payload = {"name": "Микроскоп", "inventory_number": "X-1", "category": "Оптика", "laboratory_id": lab.id}
    assert client.post("/api/equipment", json=payload, headers=auth(student)).status_code == 403
    assert client.post("/api/equipment", json=payload, headers=auth(teacher)).status_code == 403
    assert client.delete(f"/api/laboratories/{lab.id}", headers=auth(teacher)).status_code == 403


def test_duplicate_inventory_number_returns_409(client, admin, equipment, lab):
    payload = {
        "name": "Копия",
        "inventory_number": equipment.inventory_number,
        "category": "Прочее",
        "laboratory_id": lab.id,
    }
    assert client.post("/api/equipment", json=payload, headers=auth(admin)).status_code == 409


def test_equipment_for_missing_laboratory_returns_404(client, admin):
    payload = {"name": "Прибор", "inventory_number": "Z-9", "category": "Прочее", "laboratory_id": 999}
    assert client.post("/api/equipment", json=payload, headers=auth(admin)).status_code == 404


def test_list_equipment_filters(client, admin, student, equipment, lab):
    client.post(
        "/api/equipment",
        json={
            "name": "3D-принтер",
            "inventory_number": "ROB-001",
            "category": "3D-печать",
            "laboratory_id": lab.id,
            "status": "maintenance",
        },
        headers=auth(admin),
    )
    headers = auth(student)
    assert len(client.get("/api/equipment", headers=headers).json()) == 2
    available = client.get("/api/equipment", params={"status": "available"}, headers=headers).json()
    assert [e["inventory_number"] for e in available] == ["PHY-001"]
    found = client.get("/api/equipment", params={"q": "принтер"}, headers=headers).json()
    assert [e["name"] for e in found] == ["3D-принтер"]


def test_availability_shows_busy_and_free_slots(client, student, equipment, tomorrow):
    client.post(
        "/api/bookings",
        json=booking_payload(equipment.id, tomorrow(10), tomorrow(12)),
        headers=auth(student),
    )
    day = tomorrow(10)[:10]
    response = client.get(
        f"/api/equipment/{equipment.id}/availability", params={"day": day}, headers=auth(student)
    )
    assert response.status_code == 200
    body = response.json()
    assert [(b["start"][11:16], b["end"][11:16]) for b in body["busy"]] == [("10:00", "12:00")]
    assert [(f["start"][11:16], f["end"][11:16]) for f in body["free"]] == [
        ("08:00", "10:00"),
        ("12:00", "20:00"),
    ]


def test_cannot_delete_equipment_with_bookings(client, admin, student, equipment, tomorrow):
    client.post(
        "/api/bookings",
        json=booking_payload(equipment.id, tomorrow(10), tomorrow(11)),
        headers=auth(student),
    )
    assert client.delete(f"/api/equipment/{equipment.id}", headers=auth(admin)).status_code == 409


def test_laboratory_crud_rules(client, admin, lab, equipment):
    headers = auth(admin)
    renamed = client.patch(f"/api/laboratories/{lab.id}", json={"room": "202"}, headers=headers)
    assert renamed.status_code == 200 and renamed.json()["room"] == "202"

    duplicate = client.post(
        "/api/laboratories", json={"name": lab.name, "building": "Б", "room": "1"}, headers=headers
    )
    assert duplicate.status_code == 409
    # лабораторию с оборудованием удалить нельзя
    assert client.delete(f"/api/laboratories/{lab.id}", headers=headers).status_code == 409

    empty = client.post(
        "/api/laboratories", json={"name": "Пустая", "building": "В", "room": "3"}, headers=headers
    )
    assert client.delete(f"/api/laboratories/{empty.json()['id']}", headers=headers).status_code == 204
    assert client.get(f"/api/laboratories/{empty.json()['id']}", headers=headers).status_code == 404


def test_update_equipment_status(client, admin, equipment):
    response = client.patch(
        f"/api/equipment/{equipment.id}", json={"status": "maintenance"}, headers=auth(admin)
    )
    assert response.status_code == 200
    assert response.json()["status"] == "maintenance"
