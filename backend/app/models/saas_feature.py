from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SaasFeature(Base):
    __tablename__ = "t_funcionalidad_saas"
    __table_args__ = (
        CheckConstraint("length(trim(codigo)) > 0", name="ck_funcionalidad_saas_codigo"),
        CheckConstraint("length(trim(nombre)) > 0", name="ck_funcionalidad_saas_nombre"),
    )

    id_funcionalidad_saas: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(String(300), nullable=True)
    estado: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
