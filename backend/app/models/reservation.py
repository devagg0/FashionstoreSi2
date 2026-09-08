from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Reservation(Base):
    __tablename__ = "t_reserva"
    __table_args__ = (
        ForeignKeyConstraint(
            ["id_empleado_atencion", "id_sucursal"],
            [
                "t_empleado_sucursal.id_empleado",
                "t_empleado_sucursal.id_sucursal",
            ],
            name="fk_reserva_empleado_sucursal",
        ),
        CheckConstraint(
            "estado IN ("
            "'PENDIENTE', 'CONFIRMADA', 'ATENDIDA', "
            "'CANCELADA', 'EXPIRADA'"
            ")",
            name="ck_reserva_estado",
        ),
        CheckConstraint(
            "fecha_expiracion > created_at",
            name="ck_reserva_fecha_expiracion",
        ),
        Index("ix_reserva_cliente_created_at", "id_cliente", "created_at"),
        Index("ix_reserva_sucursal_estado", "id_sucursal", "estado"),
    )

    id_reserva: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    id_cliente: Mapped[int] = mapped_column(
        Integer, ForeignKey("t_cliente.id_cliente"), nullable=False
    )
    id_sucursal: Mapped[int] = mapped_column(
        Integer, ForeignKey("t_sucursal.id_sucursal"), nullable=False
    )
    id_empleado_atencion: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    codigo: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    estado: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PENDIENTE",
        server_default=text("'PENDIENTE'"),
    )
    fecha_expiracion: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    fecha_atencion: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
