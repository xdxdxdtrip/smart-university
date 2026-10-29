"""Pydantic-схемы запросов и ответов API."""

import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import BookingStatus, EquipmentStatus, Role

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Пользователи и авторизация ----------


class UserCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=120, examples=["Айгерим Нурланова"])
    email: str = Field(max_length=255, examples=["student@smartuni.kz"])
    password: str = Field(min_length=8, max_length=128, examples=["Student123"])
    role: Literal["student", "teacher"] = "student"

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not EMAIL_RE.match(value):
            raise ValueError("Некорректный email")
        return value

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not re.search(r"[A-Za-zА-Яа-я]", value) or not re.search(r"\d", value):
            raise ValueError("Пароль должен содержать буквы и цифры")
        return value


class UserOut(ORMModel):
    id: int
    full_name: str
    email: str
    role: Role
    is_active: bool
    created_at: datetime | None = None


class UserUpdate(BaseModel):
    role: Role | None = None
    is_active: bool | None = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- Лаборатории ----------


class LaboratoryCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    building: str = Field(min_length=1, max_length=80)
    room: str = Field(min_length=1, max_length=20)
    description: str | None = None


class LaboratoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    building: str | None = Field(default=None, min_length=1, max_length=80)
    room: str | None = Field(default=None, min_length=1, max_length=20)
    description: str | None = None


class LaboratoryOut(ORMModel):
    id: int
    name: str
    building: str
    room: str
    description: str | None = None


# ---------- Оборудование ----------


class EquipmentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    inventory_number: str = Field(min_length=1, max_length=50)
    category: str = Field(min_length=2, max_length=60)
    description: str | None = None
    laboratory_id: int
    status: EquipmentStatus = EquipmentStatus.AVAILABLE


class EquipmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    category: str | None = Field(default=None, min_length=2, max_length=60)
    description: str | None = None
    laboratory_id: int | None = None
    status: EquipmentStatus | None = None


class EquipmentOut(ORMModel):
    id: int
    name: str
    inventory_number: str
    category: str
    description: str | None = None
    status: EquipmentStatus
    laboratory_id: int
    laboratory_name: str | None = None


class TimeSlot(BaseModel):
    start: datetime
    end: datetime


class BusySlot(TimeSlot):
    status: BookingStatus
    booking_id: int


class AvailabilityOut(BaseModel):
    equipment_id: int
    day: date
    work_start: datetime
    work_end: datetime
    busy: list[BusySlot]
    free: list[TimeSlot]


# ---------- Брони ----------


class BookingCreate(BaseModel):
    equipment_id: int
    start_time: datetime = Field(examples=["2026-11-02T10:00:00"])
    end_time: datetime = Field(examples=["2026-11-02T12:00:00"])
    purpose: str = Field(min_length=3, max_length=255, examples=["Лабораторная работа №3"])

    @field_validator("start_time", "end_time")
    @classmethod
    def drop_timezone(cls, value: datetime) -> datetime:
        # Все времена храним как локальное время кампуса.
        return value.replace(tzinfo=None, second=0, microsecond=0)


class ReviewIn(BaseModel):
    comment: str | None = Field(default=None, max_length=255)


class BookingOut(ORMModel):
    id: int
    user_id: int
    user_full_name: str | None = None
    equipment_id: int
    equipment_name: str | None = None
    start_time: datetime
    end_time: datetime
    purpose: str
    status: BookingStatus
    reviewed_by_id: int | None = None
    review_comment: str | None = None
    created_at: datetime | None = None


class BookingHistoryOut(ORMModel):
    id: int
    old_status: BookingStatus | None = None
    new_status: BookingStatus
    changed_by_id: int | None = None
    changed_by_name: str | None = None
    comment: str | None = None
    changed_at: datetime | None = None


# ---------- Уведомления и статистика ----------


class NotificationOut(ORMModel):
    id: int
    message: str
    booking_id: int | None = None
    is_read: bool
    created_at: datetime | None = None


class EquipmentUsage(BaseModel):
    equipment_id: int
    name: str
    bookings: int


class StatsOut(BaseModel):
    users_total: int
    users_by_role: dict[str, int]
    laboratories_total: int
    equipment_total: int
    bookings_total: int
    bookings_by_status: dict[str, int]
    top_equipment: list[EquipmentUsage]


class Message(BaseModel):
    detail: str
