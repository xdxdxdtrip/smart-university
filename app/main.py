"""Точка входа FastAPI-приложения Smart University."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app import __version__
from app.config import settings
from app.database import engine
from app.routers import auth, bookings, equipment, laboratories, notifications, stats, users
from app.services.errors import DomainError

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.init_db_on_startup:
        from app.seed import init_db

        init_db()
    yield


app = FastAPI(
    title="Smart University API",
    version=__version__,
    description=(
        "Система бронирования лабораторного оборудования университета. "
        "Роли: студент, преподаватель, администратор. "
        "Авторизация — JWT (кнопка **Authorize**, username = email)."
    ),
    lifespan=lifespan,
)


@app.exception_handler(DomainError)
async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


for router in (
    auth.router,
    users.router,
    laboratories.router,
    equipment.router,
    bookings.router,
    notifications.router,
    stats.router,
):
    app.include_router(router)


@app.get("/api/health", tags=["Служебное"], summary="Проверка работоспособности")
def health() -> dict:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok", "version": __version__}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
