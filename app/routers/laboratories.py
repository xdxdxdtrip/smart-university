from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.deps import AdminUser, CurrentUser, DbSession
from app.models import Equipment, Laboratory
from app.schemas import LaboratoryCreate, LaboratoryOut, LaboratoryUpdate

router = APIRouter(prefix="/api/laboratories", tags=["Лаборатории"])


def _get_or_404(db, lab_id: int) -> Laboratory:
    lab = db.get(Laboratory, lab_id)
    if lab is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Лаборатория не найдена")
    return lab


@router.get("", response_model=list[LaboratoryOut], summary="Список лабораторий")
def list_laboratories(db: DbSession, _: CurrentUser) -> list[Laboratory]:
    return list(db.scalars(select(Laboratory).order_by(Laboratory.name)))


@router.get("/{lab_id}", response_model=LaboratoryOut, summary="Лаборатория по id")
def get_laboratory(lab_id: int, db: DbSession, _: CurrentUser) -> Laboratory:
    return _get_or_404(db, lab_id)


@router.post("", response_model=LaboratoryOut, status_code=status.HTTP_201_CREATED, summary="Создать")
def create_laboratory(data: LaboratoryCreate, db: DbSession, _: AdminUser) -> Laboratory:
    lab = Laboratory(**data.model_dump())
    db.add(lab)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Лаборатория с таким названием уже есть") from None
    db.refresh(lab)
    return lab


@router.patch("/{lab_id}", response_model=LaboratoryOut, summary="Изменить")
def update_laboratory(lab_id: int, data: LaboratoryUpdate, db: DbSession, _: AdminUser) -> Laboratory:
    lab = _get_or_404(db, lab_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(lab, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Лаборатория с таким названием уже есть") from None
    db.refresh(lab)
    return lab


@router.delete("/{lab_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить")
def delete_laboratory(lab_id: int, db: DbSession, _: AdminUser) -> Response:
    lab = _get_or_404(db, lab_id)
    if db.scalar(select(Equipment.id).where(Equipment.laboratory_id == lab_id).limit(1)):
        raise HTTPException(status.HTTP_409_CONFLICT, "В лаборатории есть оборудование")
    db.delete(lab)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
