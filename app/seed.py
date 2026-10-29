"""Создание таблиц, администратора и демонстрационных данных.

Запуск вручную:  python -m app.seed
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import Equipment, EquipmentStatus, Laboratory, Role, User
from app.security import hash_password

DEMO_USERS = [
    ("Ерлан Сапаров", "teacher@smartuni.kz", "Teacher123", Role.TEACHER),
    ("Айгерим Нурланова", "student@smartuni.kz", "Student123", Role.STUDENT),
    ("Данияр Ахметов", "student2@smartuni.kz", "Student123", Role.STUDENT),
]

DEMO_LABS = {
    "Лаборатория физики": ("Корпус А", "201", "Оптика, механика, электричество"),
    "Лаборатория химии": ("Корпус Б", "105", "Аналитическая и органическая химия"),
    "Лаборатория робототехники и IoT": ("Корпус C", "310", "Микроконтроллеры, датчики, 3D-печать"),
    "Компьютерная лаборатория": ("Корпус А", "404", "Высокопроизводительные рабочие станции"),
}

DEMO_EQUIPMENT = [
    ("Цифровой осциллограф Rigol DS1054Z", "PHY-001", "Измерительные приборы", "Лаборатория физики"),
    ("Лазерный набор для оптики", "PHY-002", "Оптика", "Лаборатория физики"),
    ("Спектрофотометр UV-1800", "CHM-001", "Аналитические приборы", "Лаборатория химии"),
    ("Вытяжной шкаф №2", "CHM-002", "Лабораторная мебель", "Лаборатория химии"),
    ("3D-принтер Prusa MK4", "ROB-001", "3D-печать", "Лаборатория робототехники и IoT"),
    ("Набор Arduino + датчики", "ROB-002", "Микроконтроллеры", "Лаборатория робототехники и IoT"),
    ("Робот-манипулятор uArm", "ROB-003", "Робототехника", "Лаборатория робототехники и IoT"),
    ("GPU-станция RTX 4090", "CMP-001", "Вычислительная техника", "Компьютерная лаборатория"),
]


def ensure_admin(db: Session) -> User:
    admin = db.scalar(select(User).where(User.email == settings.admin_email))
    if admin is None:
        admin = User(
            full_name="Администратор системы",
            email=settings.admin_email,
            password_hash=hash_password(settings.admin_password),
            role=Role.ADMIN,
        )
        db.add(admin)
        db.commit()
    return admin


def seed_demo(db: Session) -> None:
    for full_name, email, password, role in DEMO_USERS:
        if not db.scalar(select(User).where(User.email == email)):
            db.add(
                User(
                    full_name=full_name,
                    email=email,
                    password_hash=hash_password(password),
                    role=role,
                )
            )
    labs: dict[str, Laboratory] = {}
    for name, (building, room, description) in DEMO_LABS.items():
        lab = db.scalar(select(Laboratory).where(Laboratory.name == name))
        if lab is None:
            lab = Laboratory(name=name, building=building, room=room, description=description)
            db.add(lab)
            db.flush()
        labs[name] = lab
    for name, inv, category, lab_name in DEMO_EQUIPMENT:
        if not db.scalar(select(Equipment).where(Equipment.inventory_number == inv)):
            db.add(
                Equipment(
                    name=name,
                    inventory_number=inv,
                    category=category,
                    laboratory_id=labs[lab_name].id,
                    status=EquipmentStatus.MAINTENANCE if inv == "CHM-002" else EquipmentStatus.AVAILABLE,
                )
            )
    db.commit()


def init_db(with_demo: bool | None = None) -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        ensure_admin(db)
        if settings.seed_demo_data if with_demo is None else with_demo:
            seed_demo(db)


if __name__ == "__main__":
    init_db(with_demo=True)
    print("База данных инициализирована, демо-данные загружены.")
