from sqlalchemy import ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ProductCollection(Base):
    __tablename__ = "t_producto_coleccion"
    __table_args__ = (UniqueConstraint("id_producto", "id_coleccion"),)

    id_producto_coleccion: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    id_producto: Mapped[int] = mapped_column(
        Integer, ForeignKey("t_producto.id_producto"), nullable=False
    )
    id_coleccion: Mapped[int] = mapped_column(
        Integer, ForeignKey("t_coleccion.id_coleccion"), nullable=False
    )
