from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class InventoryMovement(Base):
    __tablename__ = "t_movimiento_inventario"
    __table_args__ = (
        UniqueConstraint("id_venta", name="uq_movimiento_inventario_venta"),
        CheckConstraint(
            "tipo_movimiento IN ("
            "'ENTRADA', 'SALIDA', 'TRANSFERENCIA', "
            "'AJUSTE_POSITIVO', 'AJUSTE_NEGATIVO', 'VENTA'"
            ")",
            name="ck_movimiento_inventario_tipo",
        ),
        CheckConstraint(
            "estado IN ('PENDIENTE', 'CONFIRMADO', 'ANULADO')",
            name="ck_movimiento_inventario_estado",
        ),
        CheckConstraint(
            "(tipo_movimiento = 'TRANSFERENCIA' "
            "AND id_sucursal_origen IS NOT NULL "
            "AND id_sucursal_destino IS NOT NULL "
            "AND id_sucursal_origen <> id_sucursal_destino) "
            "OR (tipo_movimiento IN ('ENTRADA', 'AJUSTE_POSITIVO') "
            "AND id_sucursal_origen IS NULL "
            "AND id_sucursal_destino IS NOT NULL) "
            "OR (tipo_movimiento IN ("
            "'SALIDA', 'AJUSTE_NEGATIVO', 'VENTA'"
            ") AND id_sucursal_origen IS NOT NULL "
            "AND id_sucursal_destino IS NULL)",
            name="ck_movimiento_inventario_sucursales",
        ),
        CheckConstraint(
            "(tipo_movimiento = 'VENTA' AND id_venta IS NOT NULL) "
            "OR (tipo_movimiento <> 'VENTA' AND id_venta IS NULL)",
            name="ck_movimiento_inventario_venta",
        ),
        Index(
            "ix_movimiento_inventario_origen_fecha",
            "id_sucursal_origen",
            "fecha_movimiento",
        ),
        Index(
            "ix_movimiento_inventario_destino_fecha",
            "id_sucursal_destino",
            "fecha_movimiento",
        ),
    )

    id_movimiento_inventario: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    id_sucursal_origen: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("t_sucursal.id_sucursal"),
        nullable=True,
    )
    id_sucursal_destino: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("t_sucursal.id_sucursal"),
        nullable=True,
    )
    id_empleado_sucursal: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("t_empleado_sucursal.id_empleado_sucursal"),
        nullable=False,
    )
    id_venta: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("t_venta.id_venta"),
        nullable=True,
    )
    tipo_movimiento: Mapped[str] = mapped_column(String(30), nullable=False)
    estado: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PENDIENTE",
        server_default=text("'PENDIENTE'"),
    )
    motivo: Mapped[str | None] = mapped_column(String(200), nullable=True)
    fecha_movimiento: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
