from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SaleDetail(Base):
    __tablename__ = "t_detalle_venta"
    __table_args__ = (
        UniqueConstraint(
            "id_venta",
            "id_variante_producto",
            name="uq_detalle_venta_variante",
        ),
        CheckConstraint(
            "cantidad > 0",
            name="ck_detalle_venta_cantidad",
        ),
        CheckConstraint(
            "precio_unitario >= 0",
            name="ck_detalle_venta_precio",
        ),
        CheckConstraint(
            "descuento_unitario >= 0 "
            "AND descuento_unitario <= precio_unitario",
            name="ck_detalle_venta_descuento",
        ),
        CheckConstraint(
            "subtotal_linea >= 0",
            name="ck_detalle_venta_subtotal",
        ),
        CheckConstraint(
            "subtotal_linea = cantidad * "
            "(precio_unitario - descuento_unitario)",
            name="ck_detalle_venta_calculo_subtotal",
        ),
        Index(
            "ix_detalle_venta_id_variante_producto",
            "id_variante_producto",
        ),
    )

    id_detalle_venta: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    id_venta: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("t_venta.id_venta", ondelete="CASCADE"),
        nullable=False,
    )
    id_variante_producto: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("t_variante_producto.id_variante_producto"),
        nullable=False,
    )
    id_promocion: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("t_promocion.id_promocion"), nullable=True
    )
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False)
    precio_unitario: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False
    )
    descuento_unitario: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    subtotal_linea: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False
    )
