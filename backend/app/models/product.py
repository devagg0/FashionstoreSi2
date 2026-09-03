from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Product(Base):
    __tablename__ = "t_producto"
    __table_args__ = (
        CheckConstraint("precio >= 0"),
        CheckConstraint(
            "seccion IN ('HOMBRE', 'MUJER', 'UNISEX')",
            name="ck_producto_seccion",
        ),
    )

    id_producto: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    id_categoria: Mapped[int] = mapped_column(
        Integer, ForeignKey("t_categoria.id_categoria"), nullable=False
    )
    id_temporada: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("t_temporada.id_temporada"), nullable=True
    )
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    seccion: Mapped[str] = mapped_column(String(20), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    precio: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    estado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
