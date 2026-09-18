from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
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
        UniqueConstraint("id_carrito", name="uq_venta_carrito"),
        CheckConstraint("canal IN ('PRESENCIAL','DIGITAL')", name="ck_venta_canal"),
        CheckConstraint("moneda = 'BOB'", name="ck_venta_moneda"),
        CheckConstraint("canal = 'DIGITAL' OR id_empleado IS NOT NULL", name="ck_venta_empleado_canal"),
        CheckConstraint("canal <> 'DIGITAL' OR id_cliente IS NOT NULL", name="ck_venta_cliente_digital"),
        CheckConstraint("id_carrito IS NULL OR canal = 'DIGITAL'", name="ck_venta_carrito_canal"),
        CheckConstraint(
            "(estado <> 'PENDIENTE' OR fecha_completada IS NULL) AND "
            "(estado <> 'COMPLETADA' OR fecha_completada IS NOT NULL) AND "
            "(fecha_completada IS NULL OR fecha_completada >= fecha_venta)",
            name="ck_venta_fecha_completada",
        ),
        CheckConstraint(
            "fecha_expiracion_pago IS NULL OR fecha_expiracion_pago > created_at",
            name="ck_venta_expiracion_pago",
        ),
        CheckConstraint(
            "NOT stock_comprometido OR (canal = 'DIGITAL' AND estado = 'PENDIENTE')",
            name="ck_venta_stock_comprometido",
        ),
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
        Index("ix_venta_expiracion_comprometida", "fecha_expiracion_pago",
              postgresql_where=text("estado = 'PENDIENTE' AND stock_comprometido")),
        Index("ix_venta_fecha_completada", "fecha_completada",
              postgresql_where=text("fecha_completada IS NOT NULL")),
    )

    id_venta: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    id_sucursal: Mapped[int] = mapped_column(
        Integer, ForeignKey("t_sucursal.id_sucursal"), nullable=False
    )
    id_empleado: Mapped[int | None] = mapped_column(Integer, nullable=True)
    id_cliente: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("t_cliente.id_cliente"), nullable=True
    )
    id_reserva: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("t_reserva.id_reserva"), nullable=True
    )
    canal: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PRESENCIAL",
        server_default=text("'PRESENCIAL'"),
    )
    moneda: Mapped[str] = mapped_column(String(3), nullable=False, default="BOB")
    id_carrito: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("t_carrito.id_carrito", name="fk_venta_carrito", ondelete="RESTRICT"),
        nullable=True,
    )
    fecha_completada: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fecha_expiracion_pago: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    stock_comprometido: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
        server_default=text("false"),
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
