from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class InventoryMovementDetail(Base):
    __tablename__ = "t_detalle_movimiento_inventario"
    __table_args__ = (
        UniqueConstraint(
            "id_movimiento_inventario",
            "id_variante_producto",
            name="uq_detalle_movimiento_variante",
        ),
        CheckConstraint(
            "cantidad > 0",
            name="ck_detalle_movimiento_cantidad",
        ),
        CheckConstraint(
            "costo_unitario IS NULL OR costo_unitario >= 0",
            name="ck_detalle_movimiento_costo",
        ),
        Index(
            "ix_detalle_movimiento_id_variante_producto",
            "id_variante_producto",
        ),
    )

    id_detalle_movimiento_inventario: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    id_movimiento_inventario: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "t_movimiento_inventario.id_movimiento_inventario",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    id_variante_producto: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("t_variante_producto.id_variante_producto"),
        nullable=False,
    )
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False)
    costo_unitario: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
