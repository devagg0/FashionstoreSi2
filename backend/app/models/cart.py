from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Cart(Base):
    __tablename__ = "t_carrito"
    __table_args__ = (
        CheckConstraint(
            "estado IN ('ACTIVO', 'CONVERTIDO', 'ABANDONADO')",
            name="ck_carrito_estado",
        ),
        Index(
            "uq_carrito_cliente_activo",
            "id_cliente",
            unique=True,
            postgresql_where=text("estado = 'ACTIVO'"),
        ),
    )

    id_carrito: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    id_cliente: Mapped[int] = mapped_column(
        Integer, ForeignKey("t_cliente.id_cliente"), nullable=False
    )
    estado: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="ACTIVO",
        server_default=text("'ACTIVO'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
