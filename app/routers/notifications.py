from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select, update

from app.deps import CurrentUser, DbSession
from app.models import Notification
from app.schemas import NotificationOut

router = APIRouter(prefix="/api/notifications", tags=["Уведомления"])


@router.get("", response_model=list[NotificationOut], summary="Мои уведомления")
def list_notifications(db: DbSession, user: CurrentUser, unread_only: bool = False) -> list[Notification]:
    query = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        query = query.where(Notification.is_read.is_(False))
    return list(db.scalars(query.order_by(Notification.id.desc())))


@router.post("/{notification_id}/read", response_model=NotificationOut, summary="Прочитано")
def mark_read(notification_id: int, db: DbSession, user: CurrentUser) -> Notification:
    notification = db.get(Notification, notification_id)
    if notification is None or notification.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Уведомление не найдено")
    notification.is_read = True
    db.commit()
    db.refresh(notification)
    return notification


@router.post("/read-all", summary="Отметить все как прочитанные")
def mark_all_read(db: DbSession, user: CurrentUser) -> dict:
    result = db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.is_read.is_(False))
        .values(is_read=True)
    )
    db.commit()
    return {"updated": result.rowcount}
