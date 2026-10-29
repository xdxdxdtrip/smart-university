"""ORM-модели: users, laboratories, equipment, bookings, booking_history, notifications."""

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.timeutils import now_local


class Role(enum.StrEnum):
    STUDENT = "student"
    TEACHER = "teacher"
    ADMIN = "admin"


class EquipmentStatus(enum.StrEnum):
    AVAILABLE = "available"
    MAINTENANCE = "maintenance"
    DECOMMISSIONED = "decommissioned"


class BookingStatus(enum.StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


def _enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        length=20,
        values_callable=lambda items: [item.value for item in items],
        validate_strings=True,
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(_enum(Role, "user_role"), default=Role.STUDENT)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)

    bookings: Mapped[list["Booking"]] = relationship(back_populates="user", foreign_keys="Booking.user_id")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="user")


class Laboratory(Base):
    __tablename__ = "laboratories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    building: Mapped[str] = mapped_column(String(80))
    room: Mapped[str] = mapped_column(String(20))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)

    equipment: Mapped[list["Equipment"]] = relationship(back_populates="laboratory")


class Equipment(Base):
    __tablename__ = "equipment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    inventory_number: Mapped[str] = mapped_column(String(50), unique=True)
    category: Mapped[str] = mapped_column(String(60))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[EquipmentStatus] = mapped_column(
        _enum(EquipmentStatus, "equipment_status"), default=EquipmentStatus.AVAILABLE
    )
    laboratory_id: Mapped[int] = mapped_column(ForeignKey("laboratories.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)

    laboratory: Mapped[Laboratory] = relationship(back_populates="equipment")
    bookings: Mapped[list["Booking"]] = relationship(back_populates="equipment")

    @property
    def laboratory_name(self) -> str | None:
        return self.laboratory.name if self.laboratory else None


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("end_time > start_time", name="ck_booking_time_order"),
        Index("ix_bookings_equipment_time", "equipment_id", "start_time", "end_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id", ondelete="RESTRICT"))
    start_time: Mapped[datetime] = mapped_column(DateTime)
    end_time: Mapped[datetime] = mapped_column(DateTime)
    purpose: Mapped[str] = mapped_column(String(255))
    status: Mapped[BookingStatus] = mapped_column(
        _enum(BookingStatus, "booking_status"), default=BookingStatus.PENDING, index=True
    )
    reviewed_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    review_comment: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, onupdate=now_local)

    user: Mapped[User] = relationship(back_populates="bookings", foreign_keys=[user_id])
    reviewed_by: Mapped[User | None] = relationship(foreign_keys=[reviewed_by_id])
    equipment: Mapped[Equipment] = relationship(back_populates="bookings")
    history: Mapped[list["BookingHistory"]] = relationship(
        back_populates="booking",
        order_by="BookingHistory.id",
        cascade="all, delete-orphan",
    )

    @property
    def equipment_name(self) -> str | None:
        return self.equipment.name if self.equipment else None

    @property
    def user_full_name(self) -> str | None:
        return self.user.full_name if self.user else None


class BookingHistory(Base):
    """Журнал изменений статуса брони (аудит)."""

    __tablename__ = "booking_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"))
    old_status: Mapped[BookingStatus | None] = mapped_column(
        _enum(BookingStatus, "booking_status"), nullable=True
    )
    new_status: Mapped[BookingStatus] = mapped_column(_enum(BookingStatus, "booking_status"))
    changed_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    comment: Mapped[str | None] = mapped_column(String(255), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)

    booking: Mapped[Booking] = relationship(back_populates="history")
    changed_by: Mapped[User | None] = relationship()

    @property
    def changed_by_name(self) -> str | None:
        return self.changed_by.full_name if self.changed_by else None


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    booking_id: Mapped[int | None] = mapped_column(
        ForeignKey("bookings.id", ondelete="SET NULL"), nullable=True
    )
    message: Mapped[str] = mapped_column(String(255))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)

    user: Mapped[User] = relationship(back_populates="notifications")
