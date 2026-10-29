from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.deps import AdminUser, DbSession
from app.models import Role, User
from app.schemas import UserOut, UserUpdate

router = APIRouter(prefix="/api/users", tags=["Пользователи (админ)"])


@router.get("", response_model=list[UserOut], summary="Список пользователей")
def list_users(db: DbSession, _: AdminUser, role: Role | None = None) -> list[User]:
    query = select(User).order_by(User.id)
    if role is not None:
        query = query.where(User.role == role)
    return list(db.scalars(query))


@router.patch("/{user_id}", response_model=UserOut, summary="Изменить роль или активность")
def update_user(user_id: int, data: UserUpdate, db: DbSession, admin: AdminUser) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден")
    if user.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Нельзя изменить собственную учётную запись")
    if data.role is not None:
        user.role = data.role
    if data.is_active is not None:
        user.is_active = data.is_active
    db.commit()
    db.refresh(user)
    return user
