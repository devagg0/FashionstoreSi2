"""Modelo SQLAlchemy para notificaciones transaccionales (CU29)."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.tenant import TenantMixin


class Notification(TenantMixin, Base):
    """Almacena notificaciones transaccionales dirigidas a clientes."""

    __tablename__ = "t_notificacion"
    __table_args__ = (
        UniqueConstraint("empresa_id", "clave_idempotencia", name="uq_notificacion_empresa_idempotencia"),
    )

    id_notificacion: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    empresa_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("t_empresa.id_empresa"), nullable=False, index=True
    )
    id_usuario: Mapped[int] = mapped_column(
        Integer, ForeignKey("t_usuario.id_usuario"), nullable=False, index=True
    )
    tipo: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )
    titulo: Mapped[str] = mapped_column(
        String(150), nullable=False
    )
    mensaje: Mapped[str] = mapped_column(
        String(500), nullable=False
    )
    referencia_origen: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    referencia_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    codigo_referencia: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    clave_idempotencia: Mapped[str] = mapped_column(
        String(150), nullable=False, index=True
    )
    leido: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false"), index=True
    )
    fecha_lectura: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    usuario = relationship("User", foreign_keys=[id_usuario])

