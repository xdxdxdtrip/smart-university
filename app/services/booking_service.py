"""Бизнес-логика бронирования: проверки времени, поиск конфликтов, смена статусов."""

from collections.abc import Iterable
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, settings
from app.models import (
    Booking,
    BookingHistory,
    BookingStatus,
    Equipment,
    EquipmentStatus,
    Notification,
    Role,
    User,
)
from app.services.errors import (
    BookingConflictError,
    BookingValidationError,
    NotFoundError,
    PermissionDeniedError,
)
from app.timeutils import now_local

# Брони в этих статусах занимают оборудование.
ACTIVE_STATUSES = (BookingStatus.PENDING, BookingStatus.APPROVED)

# Допустимые переходы статусов (конечный автомат).
ALLOWED_TRANSITIONS: dict[BookingStatus, set[BookingStatus]] = {
    BookingStatus.PENDING: {BookingStatus.APPROVED, BookingStatus.REJECTED, BookingStatus.CANCELLED},
    BookingStatus.APPROVED: {BookingStatus.CANCELLED},
    BookingStatus.REJECTED: set(),
    BookingStatus.CANCELLED: set(),
}

STATUS_RU = {
    BookingStatus.PENDING: "ожидает подтверждения",
    BookingStatus.APPROVED: "одобрена",
    BookingStatus.REJECTED: "отклонена",
    BookingStatus.CANCELLED: "отменена",
}


# ---------- Чистые функции (покрыты unit-тестами) ----------


def intervals_overlap(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    """Два полуинтервала [start, end) пересекаются. Соседние интервалы (10–11 и 11–12) — нет."""
    return a_start < b_end and b_start < a_end


def validate_time_window(start: datetime, end: datetime, now: datetime, cfg: Settings = settings) -> None:
    """Проверяет правила бронирования и бросает BookingValidationError при нарушении."""
    if end <= start:
        raise BookingValidationError("Время окончания должно быть позже времени начала")
    if start < now:
        raise BookingValidationError("Нельзя забронировать время в прошлом")
    if start.date() != end.date():
        raise BookingValidationError("Бронь должна начинаться и заканчиваться в один день")
    if start > now + timedelta(days=cfg.max_days_ahead):
        raise BookingValidationError(f"Бронировать можно не более чем на {cfg.max_days_ahead} дней вперёд")

    duration = end - start
    if duration < timedelta(minutes=cfg.min_booking_minutes):
        raise BookingValidationError(f"Минимальная длительность брони — {cfg.min_booking_minutes} минут")
    if duration > timedelta(hours=cfg.max_booking_hours):
        raise BookingValidationError(f"Максимальная длительность брони — {cfg.max_booking_hours} ч")

    work_start = datetime.combine(start.date(), time(cfg.work_day_start_hour))
    work_end = datetime.combine(start.date(), time(cfg.work_day_end_hour))
    if start < work_start or end > work_end:
        raise BookingValidationError(
            f"Лаборатории работают с {cfg.work_day_start_hour:02d}:00 до {cfg.work_day_end_hour:02d}:00"
        )


def compute_free_slots(
    work_start: datetime, work_end: datetime, busy: Iterable[tuple[datetime, datetime]]
) -> list[tuple[datetime, datetime]]:
    """Возвращает свободные промежутки рабочего дня между занятыми интервалами."""
    free: list[tuple[datetime, datetime]] = []
    cursor = work_start
    for b_start, b_end in sorted(busy):
        b_start, b_end = max(b_start, work_start), min(b_end, work_end)
        if b_end <= cursor:
            continue
        if b_start > cursor:
            free.append((cursor, b_start))
        cursor = max(cursor, b_end)
    if cursor < work_end:
        free.append((cursor, work_end))
    return free


def can_review(reviewer: User, booking: Booking) -> bool:
    """Администратор рассматривает любые заявки, преподаватель — только заявки студентов."""
    if reviewer.role == Role.ADMIN:
        return True
    return reviewer.role == Role.TEACHER and booking.user.role == Role.STUDENT


# ---------- Операции с базой данных ----------


def find_conflicts(
    db: Session,
    equipment_id: int,
    start: datetime,
    end: datetime,
    exclude_booking_id: int | None = None,
    statuses: tuple[BookingStatus, ...] = ACTIVE_STATUSES,
) -> list[Booking]:
    query = select(Booking).where(
        Booking.equipment_id == equipment_id,
        Booking.status.in_(statuses),
        Booking.start_time < end,
        Booking.end_time > start,
    )
    if exclude_booking_id is not None:
        query = query.where(Booking.id != exclude_booking_id)
    return list(db.scalars(query.order_by(Booking.start_time)))


def get_day_availability(db: Session, equipment: Equipment, day: date) -> dict:
    work_start = datetime.combine(day, time(settings.work_day_start_hour))
    work_end = datetime.combine(day, time(settings.work_day_end_hour))
    bookings = find_conflicts(db, equipment.id, work_start, work_end)
    busy = [
        {"start": b.start_time, "end": b.end_time, "status": b.status, "booking_id": b.id} for b in bookings
    ]
    free = compute_free_slots(work_start, work_end, [(b.start_time, b.end_time) for b in bookings])
    if equipment.status != EquipmentStatus.AVAILABLE:
        free = []
    return {
        "equipment_id": equipment.id,
        "day": day,
        "work_start": work_start,
        "work_end": work_end,
        "busy": busy,
        "free": [{"start": s, "end": e} for s, e in free],
    }


def notify(db: Session, user_id: int, message: str, booking_id: int | None = None) -> None:
    db.add(Notification(user_id=user_id, message=message, booking_id=booking_id))


def _log(
    db: Session,
    booking: Booking,
    old: BookingStatus | None,
    new: BookingStatus,
    actor: User,
    comment: str | None = None,
) -> None:
    db.add(
        BookingHistory(
            booking=booking, old_status=old, new_status=new, changed_by_id=actor.id, comment=comment
        )
    )


def _fmt(booking: Booking) -> str:
    return f"«{booking.equipment.name}» {booking.start_time:%d.%m.%Y %H:%M}–{booking.end_time:%H:%M}"


def create_booking(
    db: Session,
    user: User,
    equipment_id: int,
    start: datetime,
    end: datetime,
    purpose: str,
) -> Booking:
    # Блокируем строку оборудования, чтобы две параллельные заявки не прошли проверку одновременно.
    equipment = db.scalar(select(Equipment).where(Equipment.id == equipment_id).with_for_update())
    if equipment is None:
        raise NotFoundError("Оборудование не найдено")
    if equipment.status != EquipmentStatus.AVAILABLE:
        raise BookingValidationError("Оборудование недоступно (на обслуживании или списано)")

    validate_time_window(start, end, now_local())

    conflicts = find_conflicts(db, equipment.id, start, end)
    if conflicts:
        c = conflicts[0]
        raise BookingConflictError(
            f"Время пересекается с бронью #{c.id} "
            f"({c.start_time:%H:%M}–{c.end_time:%H:%M}, {STATUS_RU[c.status]})"
        )

    booking = Booking(
        user=user,
        equipment=equipment,
        start_time=start,
        end_time=end,
        purpose=purpose.strip(),
        status=BookingStatus.PENDING,
    )
    db.add(booking)
    db.flush()
    _log(db, booking, None, BookingStatus.PENDING, user, "Заявка создана")
    notify(db, user.id, f"Заявка #{booking.id} на {_fmt(booking)} создана и ждёт подтверждения", booking.id)

    admins = db.scalars(select(User).where(User.role == Role.ADMIN, User.is_active.is_(True)))
    for admin in admins:
        notify(
            db,
            admin.id,
            f"Новая заявка #{booking.id} от {user.full_name}: {_fmt(booking)}",
            booking.id,
        )
    db.commit()
    db.refresh(booking)
    return booking


def change_status(
    db: Session,
    booking: Booking,
    new_status: BookingStatus,
    actor: User,
    comment: str | None = None,
) -> Booking:
    old_status = booking.status
    if new_status not in ALLOWED_TRANSITIONS[old_status]:
        raise BookingValidationError(
            f"Нельзя перевести бронь из статуса «{STATUS_RU[old_status]}» в «{STATUS_RU[new_status]}»"
        )

    if new_status in (BookingStatus.APPROVED, BookingStatus.REJECTED):
        if not can_review(actor, booking):
            raise PermissionDeniedError("Преподаватель может рассматривать только заявки студентов")
        booking.reviewed_by_id = actor.id
        booking.review_comment = comment

    if new_status == BookingStatus.APPROVED:
        if booking.start_time < now_local():
            raise BookingValidationError("Время брони уже прошло — одобрить нельзя")
        conflicts = find_conflicts(
            db,
            booking.equipment_id,
            booking.start_time,
            booking.end_time,
            exclude_booking_id=booking.id,
            statuses=(BookingStatus.APPROVED,),
        )
        if conflicts:
            raise BookingConflictError(f"Уже есть одобренная бронь #{conflicts[0].id} на это время")

    if new_status == BookingStatus.CANCELLED and actor.id != booking.user_id and actor.role != Role.ADMIN:
        raise PermissionDeniedError("Отменить бронь может только её владелец или администратор")

    booking.status = new_status
    _log(db, booking, old_status, new_status, actor, comment)

    if actor.id != booking.user_id:
        text = f"Ваша заявка #{booking.id} на {_fmt(booking)} {STATUS_RU[new_status]}"
        if comment:
            text += f". Комментарий: {comment}"
        notify(db, booking.user_id, text[:255], booking.id)

    db.commit()
    db.refresh(booking)
    return booking
