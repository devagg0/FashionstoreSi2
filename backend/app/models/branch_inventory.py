from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BranchInventory(Base):
    __tablename__ = "t_inventario_sucursal"
    __table_args__ = (
        UniqueConstraint(
            "id_sucursal",
            "id_variante_producto",
            name="uq_inventario_sucursal_variante",
        ),
        CheckConstraint(
            "stock_actual >= 0",
            name="ck_inventario_stock_actual",
        ),
        CheckConstraint(
            "stock_reservado >= 0",
            name="ck_inventario_stock_reservado",
        ),
        CheckConstraint(
            "stock_minimo >= 0",
            name="ck_inventario_stock_minimo",
        ),
        CheckConstraint(
            "stock_reservado <= stock_actual",
            name="ck_inventario_reservado_disponible",
        ),
        Index(
            "ix_inventario_sucursal_id_variante_producto",
            "id_variante_producto",
        ),
    )

    id_inventario_sucursal: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    id_sucursal: Mapped[int] = mapped_column(
        Integer, ForeignKey("t_sucursal.id_sucursal"), nullable=False
    )
    id_variante_producto: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("t_variante_producto.id_variante_producto"),
        nullable=False,
    )
    stock_actual: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    stock_reservado: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    stock_minimo: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
