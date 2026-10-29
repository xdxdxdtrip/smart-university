from datetime import date

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.deps import AdminUser, CurrentUser, DbSession
from app.models import Booking, Equipment, EquipmentStatus, Laboratory
from app.schemas import AvailabilityOut, EquipmentCreate, EquipmentOut, EquipmentUpdate
from app.services.booking_service import get_day_availability
from app.timeutils import now_local

router = APIRouter(prefix="/api/equipment", tags=["Оборудование"])


def _get_or_404(db, equipment_id: int) -> Equipment:
    equipment = db.get(Equipment, equipment_id)
    if equipment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Оборудование не найдено")
    return equipment


def _check_lab(db, lab_id: int) -> None:
    if db.get(Laboratory, lab_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Лаборатория не найдена")


@router.get("", response_model=list[EquipmentOut], summary="Список оборудования с фильтрами")
def list_equipment(
    db: DbSession,
    _: CurrentUser,
    laboratory_id: int | None = None,
    status_filter: EquipmentStatus | None = Query(default=None, alias="status"),
    category: str | None = None,
    q: str | None = Query(default=None, description="Поиск по названию или инв. номеру"),
) -> list[Equipment]:
    query = select(Equipment).options(selectinload(Equipment.laboratory)).order_by(Equipment.name)
    if laboratory_id is not None:
        query = query.where(Equipment.laboratory_id == laboratory_id)
    if status_filter is not None:
        query = query.where(Equipment.status == status_filter)
    if category:
        query = query.where(Equipment.category.ilike(category))
    if q:
        pattern = f"%{q.strip()}%"
        query = query.where(or_(Equipment.name.ilike(pattern), Equipment.inventory_number.ilike(pattern)))
    return list(db.scalars(query))


@router.get("/{equipment_id}", response_model=EquipmentOut, summary="Оборудование по id")
def get_equipment(equipment_id: int, db: DbSession, _: CurrentUser) -> Equipment:
    return _get_or_404(db, equipment_id)


@router.get(
    "/{equipment_id}/availability",
    response_model=AvailabilityOut,
    summary="Занятые и свободные интервалы на выбранный день",
)
def availability(equipment_id: int, db: DbSession, _: CurrentUser, day: date | None = None) -> dict:
    equipment = _get_or_404(db, equipment_id)
    return get_day_availability(db, equipment, day or now_local().date())


@router.post("", response_model=EquipmentOut, status_code=status.HTTP_201_CREATED, summary="Добавить")
def create_equipment(data: EquipmentCreate, db: DbSession, _: AdminUser) -> Equipment:
    _check_lab(db, data.laboratory_id)
    equipment = Equipment(**data.model_dump())
    db.add(equipment)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Инвентарный номер уже используется") from None
    db.refresh(equipment)
    return equipment


@router.patch("/{equipment_id}", response_model=EquipmentOut, summary="Изменить")
def update_equipment(equipment_id: int, data: EquipmentUpdate, db: DbSession, _: AdminUser) -> Equipment:
    equipment = _get_or_404(db, equipment_id)
    changes = data.model_dump(exclude_unset=True)
    if "laboratory_id" in changes:
        _check_lab(db, changes["laboratory_id"])
    for field, value in changes.items():
        setattr(equipment, field, value)
    db.commit()
    db.refresh(equipment)
    return equipment


@router.delete("/{equipment_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить")
def delete_equipment(equipment_id: int, db: DbSession, _: AdminUser) -> Response:
    equipment = _get_or_404(db, equipment_id)
    if db.scalar(select(Booking.id).where(Booking.equipment_id == equipment_id).limit(1)):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "У оборудования есть история броней — переведите его в статус decommissioned",
        )
    db.delete(equipment)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
