"""Modelo SQLAlchemy para registro y control idempotente de reservas offline (PK08 - CU10)."""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.tenant import TenantMixin


class OfflineReservationSync(TenantMixin, Base):
    """Registro de sincronización idempotente de reservas creadas offline en Angular PWA."""

    __tablename__ = "t_reserva_offline_sync"
    __table_args__ = (
        UniqueConstraint(
            "empresa_id",
            "uuid_reserva_offline",
            name="uq_reserva_offline_empresa_uuid",
        ),
        CheckConstraint(
            "estado_sincronizacion IN ('SINCRONIZADA', 'RECHAZADA', 'CONFLICTO')",
            name="ck_reserva_offline_estado",
        ),
    )

    id_sync: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    uuid_reserva_offline: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    id_reserva: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("t_reserva.id_reserva", ondelete="SET NULL"),
        nullable=True,
    )
    codigo_reserva: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    id_sucursal: Mapped[int] = mapped_column(
        Integer, ForeignKey("t_sucursal.id_sucursal"), nullable=False
    )
    id_cliente: Mapped[int] = mapped_column(
        Integer, ForeignKey("t_cliente.id_cliente"), nullable=False
    )
    id_usuario: Mapped[int] = mapped_column(
        Integer, ForeignKey("t_usuario.id_usuario"), nullable=False
    )
    estado_sincronizacion: Mapped[str] = mapped_column(
        String(20), nullable=False
    )
    motivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    detalles_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    fecha_reserva_offline: Mapped[datetime] = mapped_column(
        DateTime, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

