from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ProductSupplier(Base):
    __tablename__ = "t_producto_proveedor"
    __table_args__ = (
        CheckConstraint(
            "costo_referencia IS NULL OR costo_referencia >= 0"
        ),
        UniqueConstraint("id_producto", "id_proveedor"),
    )

    id_producto_proveedor: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    id_producto: Mapped[int] = mapped_column(
        Integer, ForeignKey("t_producto.id_producto"), nullable=False
    )
    id_proveedor: Mapped[int] = mapped_column(
        Integer, ForeignKey("t_proveedor.id_proveedor"), nullable=False
    )
    costo_referencia: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    estado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
