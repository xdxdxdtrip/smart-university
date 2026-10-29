from fastapi import APIRouter
from sqlalchemy import func, select

from app.deps import AdminUser, DbSession
from app.models import Booking, BookingStatus, Equipment, Laboratory, Role, User
from app.schemas import StatsOut

router = APIRouter(prefix="/api/stats", tags=["Статистика (админ)"])


@router.get("", response_model=StatsOut, summary="Сводная статистика использования")
def stats(db: DbSession, _: AdminUser) -> StatsOut:
    by_role = dict(db.execute(select(User.role, func.count()).group_by(User.role)).all())
    by_status = dict(db.execute(select(Booking.status, func.count()).group_by(Booking.status)).all())
    top = db.execute(
        select(Equipment.id, Equipment.name, func.count(Booking.id).label("cnt"))
        .join(Booking, Booking.equipment_id == Equipment.id)
        .where(Booking.status != BookingStatus.CANCELLED)
        .group_by(Equipment.id, Equipment.name)
        .order_by(func.count(Booking.id).desc(), Equipment.name)
        .limit(5)
    ).all()
    return StatsOut(
        users_total=sum(by_role.values()),
        users_by_role={r.value: by_role.get(r, 0) for r in Role},
        laboratories_total=db.scalar(select(func.count(Laboratory.id))) or 0,
        equipment_total=db.scalar(select(func.count(Equipment.id))) or 0,
        bookings_total=sum(by_status.values()),
        bookings_by_status={s.value: by_status.get(s, 0) for s in BookingStatus},
        top_equipment=[{"equipment_id": i, "name": n, "bookings": c} for i, n, c in top],
    )
