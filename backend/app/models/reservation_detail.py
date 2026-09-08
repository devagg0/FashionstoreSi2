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


class ReservationDetail(Base):
    __tablename__ = "t_detalle_reserva"
    __table_args__ = (
        UniqueConstraint(
            "id_reserva",
            "id_variante_producto",
            name="uq_detalle_reserva_variante",
        ),
        CheckConstraint(
            "cantidad > 0",
            name="ck_detalle_reserva_cantidad",
        ),
        CheckConstraint(
            "precio_unitario >= 0",
            name="ck_detalle_reserva_precio",
        ),
        Index(
            "ix_detalle_reserva_id_variante_producto",
            "id_variante_producto",
        ),
    )

    id_detalle_reserva: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    id_reserva: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("t_reserva.id_reserva", ondelete="CASCADE"),
        nullable=False,
    )
    id_variante_producto: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("t_variante_producto.id_variante_producto"),
        nullable=False,
    )
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False)
    precio_unitario: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False
    )
