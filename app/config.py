"""Конфигурация приложения. Все значения читаются из переменных окружения."""

import os
from dataclasses import dataclass


def _bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str
    secret_key: str
    access_token_expire_minutes: int
    password_hash_iterations: int
    app_timezone: str
    work_day_start_hour: int
    work_day_end_hour: int
    min_booking_minutes: int
    max_booking_hours: int
    max_days_ahead: int
    admin_email: str
    admin_password: str
    init_db_on_startup: bool
    seed_demo_data: bool


def load_settings() -> Settings:
    return Settings(
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://smartuni:smartuni@localhost:5432/smart_university",
        ),
        secret_key=os.getenv("SECRET_KEY", "dev-only-secret-change-me-in-production-0123456789"),
        access_token_expire_minutes=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "120")),
        password_hash_iterations=int(os.getenv("PASSWORD_HASH_ITERATIONS", "390000")),
        app_timezone=os.getenv("APP_TIMEZONE", "Asia/Almaty"),
        work_day_start_hour=int(os.getenv("WORK_DAY_START_HOUR", "8")),
        work_day_end_hour=int(os.getenv("WORK_DAY_END_HOUR", "20")),
        min_booking_minutes=int(os.getenv("MIN_BOOKING_MINUTES", "30")),
        max_booking_hours=int(os.getenv("MAX_BOOKING_HOURS", "4")),
        max_days_ahead=int(os.getenv("MAX_DAYS_AHEAD", "30")),
        admin_email=os.getenv("ADMIN_EMAIL", "admin@smartuni.kz"),
        admin_password=os.getenv("ADMIN_PASSWORD", "Admin12345"),
        init_db_on_startup=_bool(os.getenv("INIT_DB_ON_STARTUP", "true")),
        seed_demo_data=_bool(os.getenv("SEED_DEMO_DATA", "false")),
    )


settings = load_settings()
