from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Sale(Base):
    __tablename__ = "t_venta"
    __table_args__ = (
        ForeignKeyConstraint(
            ["id_empleado", "id_sucursal"],
            [
                "t_empleado_sucursal.id_empleado",
                "t_empleado_sucursal.id_sucursal",
            ],
            name="fk_venta_empleado_sucursal",
        ),
        UniqueConstraint("id_reserva", name="uq_venta_reserva"),
        CheckConstraint(
            "estado IN ('PENDIENTE', 'COMPLETADA', 'ANULADA')",
            name="ck_venta_estado",
        ),
        CheckConstraint("subtotal >= 0", name="ck_venta_subtotal"),
        CheckConstraint(
            "descuento_total >= 0 AND descuento_total <= subtotal",
            name="ck_venta_descuento_total",
        ),
        CheckConstraint("total >= 0", name="ck_venta_total"),
        CheckConstraint(
            "total = subtotal - descuento_total",
            name="ck_venta_calculo_total",
        ),
        Index("ix_venta_sucursal_fecha", "id_sucursal", "fecha_venta"),
        Index("ix_venta_cliente_fecha", "id_cliente", "fecha_venta"),
    )

    id_venta: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    id_sucursal: Mapped[int] = mapped_column(
        Integer, ForeignKey("t_sucursal.id_sucursal"), nullable=False
    )
    id_empleado: Mapped[int] = mapped_column(Integer, nullable=False)
    id_cliente: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("t_cliente.id_cliente"), nullable=True
    )
    id_reserva: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("t_reserva.id_reserva"), nullable=True
    )
    numero_venta: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True
    )
    estado: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PENDIENTE",
        server_default=text("'PENDIENTE'"),
    )
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    descuento_total: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    fecha_venta: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
