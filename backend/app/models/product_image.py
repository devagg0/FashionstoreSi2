from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ProductImage(Base):
    __tablename__ = "t_imagen_producto"

    id_imagen_producto: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    id_producto: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("t_producto.id_producto", ondelete="CASCADE"),
        nullable=False,
    )
    url_imagen: Mapped[str] = mapped_column(Text, nullable=False)
    es_principal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
