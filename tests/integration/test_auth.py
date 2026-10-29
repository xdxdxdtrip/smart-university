"""Integration-тесты регистрации, входа и доступа по ролям."""

from app.models import Role
from tests.conftest import auth

NEW_USER = {
    "full_name": "Айгерим Нурланова",
    "email": "Aigerim@SmartUni.kz",
    "password": "Student123",
    "role": "student",
}


def test_register_creates_user_without_exposing_password(client):
    response = client.post("/api/auth/register", json=NEW_USER)
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "aigerim@smartuni.kz"  # email нормализуется
    assert body["role"] == "student"
    assert "password" not in body and "password_hash" not in body


def test_register_duplicate_email_returns_409(client):
    client.post("/api/auth/register", json=NEW_USER)
    response = client.post("/api/auth/register", json={**NEW_USER, "full_name": "Другой"})
    assert response.status_code == 409


def test_register_validation_errors(client):
    weak = client.post("/api/auth/register", json={**NEW_USER, "password": "onlyletters"})
    bad_email = client.post("/api/auth/register", json={**NEW_USER, "email": "not-an-email"})
    as_admin = client.post("/api/auth/register", json={**NEW_USER, "role": "admin"})
    assert weak.status_code == bad_email.status_code == as_admin.status_code == 422


def test_login_returns_jwt_and_me_works(client):
    client.post("/api/auth/register", json=NEW_USER)
    login = client.post("/api/auth/login", data={"username": "aigerim@smartuni.kz", "password": "Student123"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["full_name"] == NEW_USER["full_name"]


def test_login_with_wrong_password_returns_401(client):
    client.post("/api/auth/register", json=NEW_USER)
    response = client.post("/api/auth/login", data={"username": NEW_USER["email"], "password": "Wrong1234"})
    assert response.status_code == 401


def test_protected_endpoints_require_token(client):
    assert client.get("/api/equipment").status_code == 401
    bad = client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"})
    assert bad.status_code == 401


def test_deactivated_user_cannot_use_api(client, db, student):
    student.is_active = False
    db.commit()
    assert client.get("/api/auth/me", headers=auth(student)).status_code == 403


def test_only_admin_manages_users(client, admin, student):
    assert client.get("/api/users", headers=auth(student)).status_code == 403
    response = client.patch(f"/api/users/{student.id}", json={"role": "teacher"}, headers=auth(admin))
    assert response.status_code == 200
    assert response.json()["role"] == Role.TEACHER.value
    own = client.patch(f"/api/users/{admin.id}", json={"is_active": False}, headers=auth(admin))
    assert own.status_code == 400
