"""Общие фикстуры. Тесты работают с отдельной тестовой базой PostgreSQL."""

import os
from datetime import datetime, time, timedelta

os.environ["DATABASE_URL"] = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://smartuni:smartuni@localhost:5432/smart_university_test",
)
os.environ["PASSWORD_HASH_ITERATIONS"] = "1000"  # ускоряем хеширование в тестах
os.environ["INIT_DB_ON_STARTUP"] = "false"
os.environ["SEED_DEMO_DATA"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Equipment, EquipmentStatus, Laboratory, Role, User  # noqa: E402
from app.security import create_access_token, hash_password  # noqa: E402
from app.timeutils import now_local  # noqa: E402

TABLES = "booking_history, notifications, bookings, equipment, laboratories, users"


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _clean_tables():
    yield
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def make_user(db):
    counter = {"n": 0}

    def _make(role: Role = Role.STUDENT, name: str | None = None) -> User:
        counter["n"] += 1
        user = User(
            full_name=name or f"{role.value.title()} {counter['n']}",
            email=f"{role.value}{counter['n']}@test.kz",
            password_hash=hash_password("Password1"),
            role=role,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    return _make


def auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role.value)}"}


@pytest.fixture
def admin(make_user):
    return make_user(Role.ADMIN, "Админ")


@pytest.fixture
def teacher(make_user):
    return make_user(Role.TEACHER, "Преподаватель")


@pytest.fixture
def student(make_user):
    return make_user(Role.STUDENT, "Студент")


@pytest.fixture
def lab(db):
    laboratory = Laboratory(name="Лаборатория физики", building="А", room="201")
    db.add(laboratory)
    db.commit()
    db.refresh(laboratory)
    return laboratory


@pytest.fixture
def equipment(db, lab):
    item = Equipment(
        name="Осциллограф",
        inventory_number="PHY-001",
        category="Измерительные приборы",
        laboratory_id=lab.id,
        status=EquipmentStatus.AVAILABLE,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@pytest.fixture
def tomorrow():
    """Функция, возвращающая время на завтра: tomorrow(10) -> завтра 10:00."""
    day = (now_local() + timedelta(days=1)).date()

    def _at(hour: int, minute: int = 0) -> str:
        return datetime.combine(day, time(hour, minute)).isoformat()

    return _at


def booking_payload(equipment_id: int, start: str, end: str, purpose: str = "Лабораторная работа"):
    return {"equipment_id": equipment_id, "start_time": start, "end_time": end, "purpose": purpose}
