from datetime import datetime, time

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Time, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Branch(Base):
    __tablename__ = "t_sucursal"

    id_sucursal: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    id_ciudad: Mapped[int] = mapped_column(
        Integer, ForeignKey("t_ciudad.id_ciudad"), nullable=False
    )
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    direccion: Mapped[str] = mapped_column(String(200), nullable=False)
    telefono: Mapped[str | None] = mapped_column(String(30), nullable=True)
    hora_apertura: Mapped[time | None] = mapped_column(Time, nullable=True)
    hora_cierre: Mapped[time | None] = mapped_column(Time, nullable=True)
    estado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
