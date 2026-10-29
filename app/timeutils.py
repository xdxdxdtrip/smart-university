"""Работа со временем университета (все даты хранятся как локальное время кампуса)."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.config import settings


def _campus_tz():
    try:
        return ZoneInfo(settings.app_timezone)
    except ZoneInfoNotFoundError:  # pragma: no cover - если в образе нет tzdata
        return timezone(timedelta(hours=5))


def now_local() -> datetime:
    """Текущее локальное время кампуса без tzinfo (как хранится в БД)."""
    return datetime.now(_campus_tz()).replace(tzinfo=None, microsecond=0)
