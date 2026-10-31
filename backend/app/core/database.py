from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.core.config import settings


engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True
)


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


class Base(DeclarativeBase):
    pass


# Registra filtros/asignación empresarial para todas las sesiones, incluidas
# las creadas directamente por pruebas y scripts.
from app.core import tenant_context as _tenant_context  # noqa: E402,F401


def get_db():
    db = SessionLocal()

    try:
        from app.core.tenant_context import bind_initial_company

        bind_initial_company(db)
        yield db
    finally:
        db.close()
