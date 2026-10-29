from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.deps import BookerUser, CurrentUser, DbSession, StaffUser
from app.models import Booking, BookingStatus, Role, User
from app.schemas import BookingCreate, BookingHistoryOut, BookingOut, Message, ReviewIn
from app.services import booking_service

router = APIRouter(prefix="/api/bookings", tags=["Бронирование"])

_LOAD = (selectinload(Booking.equipment), selectinload(Booking.user))


def _get_or_404(db, booking_id: int) -> Booking:
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Бронь не найдена")
    return booking


def _ensure_can_view(user: User, booking: Booking) -> None:
    if user.role == Role.STUDENT and booking.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Это чужая бронь")


@router.post(
    "",
    response_model=BookingOut,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"model": Message}, 404: {"model": Message}, 409: {"model": Message}},
    summary="Создать заявку на бронирование (с автоматической проверкой конфликтов)",
)
def create_booking(data: BookingCreate, db: DbSession, user: BookerUser) -> Booking:
    return booking_service.create_booking(
        db, user, data.equipment_id, data.start_time, data.end_time, data.purpose
    )


@router.get("/my", response_model=list[BookingOut], summary="Мои брони (история)")
def my_bookings(
    db: DbSession,
    user: CurrentUser,
    status_filter: BookingStatus | None = Query(default=None, alias="status"),
) -> list[Booking]:
    query = select(Booking).options(*_LOAD).where(Booking.user_id == user.id)
    if status_filter is not None:
        query = query.where(Booking.status == status_filter)
    return list(db.scalars(query.order_by(Booking.start_time.desc())))


@router.get("", response_model=list[BookingOut], summary="Все заявки (преподаватель/админ)")
def list_bookings(
    db: DbSession,
    _: StaffUser,
    status_filter: BookingStatus | None = Query(default=None, alias="status"),
    equipment_id: int | None = None,
    day: date | None = None,
) -> list[Booking]:
    query = select(Booking).options(*_LOAD)
    if status_filter is not None:
        query = query.where(Booking.status == status_filter)
    if equipment_id is not None:
        query = query.where(Booking.equipment_id == equipment_id)
    if day is not None:
        start = datetime.combine(day, time.min)
        query = query.where(Booking.start_time >= start, Booking.start_time < start + timedelta(days=1))
    return list(db.scalars(query.order_by(Booking.start_time)))


@router.get("/{booking_id}", response_model=BookingOut, summary="Бронь по id")
def get_booking(booking_id: int, db: DbSession, user: CurrentUser) -> Booking:
    booking = _get_or_404(db, booking_id)
    _ensure_can_view(user, booking)
    return booking


@router.get(
    "/{booking_id}/history",
    response_model=list[BookingHistoryOut],
    summary="Журнал изменений статуса брони",
)
def booking_history(booking_id: int, db: DbSession, user: CurrentUser):
    booking = _get_or_404(db, booking_id)
    _ensure_can_view(user, booking)
    return booking.history


@router.post("/{booking_id}/approve", response_model=BookingOut, summary="Одобрить заявку")
def approve(booking_id: int, db: DbSession, reviewer: StaffUser, data: ReviewIn | None = None) -> Booking:
    booking = _get_or_404(db, booking_id)
    comment = data.comment if data else None
    return booking_service.change_status(db, booking, BookingStatus.APPROVED, reviewer, comment)


@router.post("/{booking_id}/reject", response_model=BookingOut, summary="Отклонить заявку")
def reject(booking_id: int, db: DbSession, reviewer: StaffUser, data: ReviewIn | None = None) -> Booking:
    booking = _get_or_404(db, booking_id)
    comment = data.comment if data else None
    return booking_service.change_status(db, booking, BookingStatus.REJECTED, reviewer, comment)


@router.post("/{booking_id}/cancel", response_model=BookingOut, summary="Отменить бронь")
def cancel(booking_id: int, db: DbSession, user: CurrentUser, data: ReviewIn | None = None) -> Booking:
    booking = _get_or_404(db, booking_id)
    comment = data.comment if data else None
    return booking_service.change_status(db, booking, BookingStatus.CANCELLED, user, comment)
