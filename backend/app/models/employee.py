from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.tenant import TenantMixin


class Employee(TenantMixin, Base):
    __tablename__ = "t_empleado"

    id_empleado: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    id_usuario: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("t_usuario.id_usuario"),
        nullable=False,
    )
    ci: Mapped[str | None] = mapped_column(String(30), nullable=True)
    cargo: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
