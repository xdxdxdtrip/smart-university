"""Integration-тесты бронирования: конфликты, согласование, отмена, история, уведомления."""

from app.models import EquipmentStatus
from tests.conftest import auth, booking_payload


def _book(client, user, equipment_id, start, end):
    return client.post("/api/bookings", json=booking_payload(equipment_id, start, end), headers=auth(user))


def test_student_creates_pending_booking_and_admin_is_notified(client, admin, student, equipment, tomorrow):
    response = _book(client, student, equipment.id, tomorrow(10), tomorrow(12))
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["equipment_name"] == "Осциллограф"

    admin_notes = client.get("/api/notifications", headers=auth(admin)).json()
    assert len(admin_notes) == 1 and "Новая заявка" in admin_notes[0]["message"]
    student_notes = client.get("/api/notifications", headers=auth(student)).json()
    assert "создана" in student_notes[0]["message"]


def test_overlapping_booking_is_rejected_with_409(client, student, teacher, equipment, tomorrow):
    assert _book(client, student, equipment.id, tomorrow(10), tomorrow(12)).status_code == 201
    conflict = _book(client, teacher, equipment.id, tomorrow(11), tomorrow(13))
    assert conflict.status_code == 409
    assert "пересекается" in conflict.json()["detail"]


def test_adjacent_booking_is_allowed(client, student, teacher, equipment, tomorrow):
    assert _book(client, student, equipment.id, tomorrow(10), tomorrow(12)).status_code == 201
    assert _book(client, teacher, equipment.id, tomorrow(12), tomorrow(13)).status_code == 201


def test_booking_validation_errors(client, db, student, equipment, tomorrow):
    outside_hours = _book(client, student, equipment.id, tomorrow(6), tomorrow(7))
    reversed_time = _book(client, student, equipment.id, tomorrow(12), tomorrow(10))
    missing = _book(client, student, 9999, tomorrow(10), tomorrow(11))
    assert outside_hours.status_code == 400
    assert reversed_time.status_code == 400
    assert missing.status_code == 404

    equipment.status = EquipmentStatus.MAINTENANCE
    db.commit()
    maintenance = _book(client, student, equipment.id, tomorrow(10), tomorrow(11))
    assert maintenance.status_code == 400
    assert "недоступно" in maintenance.json()["detail"]


def test_admin_cannot_create_bookings(client, admin, equipment, tomorrow):
    assert _book(client, admin, equipment.id, tomorrow(10), tomorrow(11)).status_code == 403


def test_teacher_approves_student_booking(client, teacher, student, equipment, tomorrow):
    booking_id = _book(client, student, equipment.id, tomorrow(10), tomorrow(12)).json()["id"]
    response = client.post(
        f"/api/bookings/{booking_id}/approve",
        json={"comment": "Хорошо, приходите"},
        headers=auth(teacher),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert response.json()["reviewed_by_id"] == teacher.id

    notes = client.get("/api/notifications", params={"unread_only": True}, headers=auth(student))
    assert any("одобрена" in n["message"] for n in notes.json())


def test_role_restrictions_on_review(client, student, make_user, teacher, admin, equipment, tomorrow):
    other_student = make_user()
    student_booking = _book(client, student, equipment.id, tomorrow(10), tomorrow(11)).json()["id"]
    teacher_booking = _book(client, teacher, equipment.id, tomorrow(14), tomorrow(15)).json()["id"]

    # Студент не может одобрять заявки
    assert (
        client.post(f"/api/bookings/{student_booking}/approve", headers=auth(other_student)).status_code
        == 403
    )
    # Преподаватель не может одобрить заявку другого преподавателя — только админ
    assert client.post(f"/api/bookings/{teacher_booking}/approve", headers=auth(teacher)).status_code == 403
    assert client.post(f"/api/bookings/{teacher_booking}/approve", headers=auth(admin)).status_code == 200


def test_rejected_booking_frees_the_slot(client, admin, student, teacher, equipment, tomorrow):
    booking_id = _book(client, student, equipment.id, tomorrow(10), tomorrow(12)).json()["id"]
    rejected = client.post(
        f"/api/bookings/{booking_id}/reject", json={"comment": "Плановое ТО"}, headers=auth(admin)
    )
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["review_comment"] == "Плановое ТО"
    assert _book(client, teacher, equipment.id, tomorrow(10), tomorrow(12)).status_code == 201


def test_invalid_status_transition_returns_400(client, admin, student, equipment, tomorrow):
    booking_id = _book(client, student, equipment.id, tomorrow(10), tomorrow(12)).json()["id"]
    client.post(f"/api/bookings/{booking_id}/reject", headers=auth(admin))
    again = client.post(f"/api/bookings/{booking_id}/approve", headers=auth(admin))
    assert again.status_code == 400


def test_cancel_by_owner_only(client, make_user, student, equipment, tomorrow):
    stranger = make_user()
    booking_id = _book(client, student, equipment.id, tomorrow(10), tomorrow(12)).json()["id"]
    assert client.post(f"/api/bookings/{booking_id}/cancel", headers=auth(stranger)).status_code == 403
    cancelled = client.post(f"/api/bookings/{booking_id}/cancel", headers=auth(student))
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    # после отмены время снова свободно
    assert _book(client, stranger, equipment.id, tomorrow(10), tomorrow(12)).status_code == 201


def test_my_bookings_and_privacy(client, make_user, student, teacher, equipment, tomorrow):
    other = make_user()
    mine = _book(client, student, equipment.id, tomorrow(10), tomorrow(11)).json()["id"]
    others = _book(client, other, equipment.id, tomorrow(12), tomorrow(13)).json()["id"]

    my_list = client.get("/api/bookings/my", headers=auth(student)).json()
    assert [b["id"] for b in my_list] == [mine]
    assert client.get(f"/api/bookings/{others}", headers=auth(student)).status_code == 403
    assert client.get("/api/bookings", headers=auth(student)).status_code == 403
    all_for_teacher = client.get("/api/bookings", params={"status": "pending"}, headers=auth(teacher))
    assert len(all_for_teacher.json()) == 2


def test_history_records_every_status_change(client, teacher, student, equipment, tomorrow):
    booking_id = _book(client, student, equipment.id, tomorrow(10), tomorrow(12)).json()["id"]
    client.post(f"/api/bookings/{booking_id}/approve", headers=auth(teacher))
    client.post(f"/api/bookings/{booking_id}/cancel", headers=auth(student))

    history = client.get(f"/api/bookings/{booking_id}/history", headers=auth(student)).json()
    assert [(h["old_status"], h["new_status"]) for h in history] == [
        (None, "pending"),
        ("pending", "approved"),
        ("approved", "cancelled"),
    ]
    assert history[1]["changed_by_name"] == teacher.full_name


def test_admin_statistics(client, admin, student, teacher, equipment, tomorrow):
    first = _book(client, student, equipment.id, tomorrow(10), tomorrow(11)).json()["id"]
    _book(client, teacher, equipment.id, tomorrow(12), tomorrow(13))
    client.post(f"/api/bookings/{first}/approve", headers=auth(admin))

    assert client.get("/api/stats", headers=auth(teacher)).status_code == 403
    stats = client.get("/api/stats", headers=auth(admin)).json()
    assert stats["bookings_total"] == 2
    assert stats["bookings_by_status"]["approved"] == 1
    assert stats["bookings_by_status"]["pending"] == 1
    assert stats["users_by_role"] == {"student": 1, "teacher": 1, "admin": 1}
    assert stats["top_equipment"][0]["bookings"] == 2


def test_mark_notifications_read(client, student, equipment, tomorrow):
    _book(client, student, equipment.id, tomorrow(10), tomorrow(11))
    notes = client.get("/api/notifications", headers=auth(student)).json()
    read = client.post(f"/api/notifications/{notes[0]['id']}/read", headers=auth(student))
    assert read.json()["is_read"] is True
    unread = client.get("/api/notifications", params={"unread_only": True}, headers=auth(student))
    assert unread.json() == []


def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["database"] == "ok"
