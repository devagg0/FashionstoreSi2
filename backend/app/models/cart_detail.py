from sqlalchemy import CheckConstraint, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CartDetail(Base):
    __tablename__ = "t_detalle_carrito"
    __table_args__ = (
        UniqueConstraint(
            "id_carrito",
            "id_variante_producto",
            name="uq_detalle_carrito_variante",
        ),
        CheckConstraint(
            "cantidad > 0",
            name="ck_detalle_carrito_cantidad",
        ),
    )

    id_detalle_carrito: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    id_carrito: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("t_carrito.id_carrito", ondelete="CASCADE"),
        nullable=False,
    )
    id_variante_producto: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("t_variante_producto.id_variante_producto"),
        nullable=False,
    )
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False)
