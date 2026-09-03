from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ProductVariant(Base):
    __tablename__ = "t_variante_producto"
    __table_args__ = (
        UniqueConstraint("id_producto", "id_talla", "id_color"),
    )

    id_variante_producto: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    id_producto: Mapped[int] = mapped_column(
        Integer, ForeignKey("t_producto.id_producto"), nullable=False
    )
    id_talla: Mapped[int] = mapped_column(
        Integer, ForeignKey("t_talla.id_talla"), nullable=False
    )
    id_color: Mapped[int] = mapped_column(
        Integer, ForeignKey("t_color.id_color"), nullable=False
    )
    sku: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    estado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
