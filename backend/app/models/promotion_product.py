from sqlalchemy import ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PromotionProduct(Base):
    __tablename__ = "t_promocion_producto"
    __table_args__ = (
        UniqueConstraint(
            "id_promocion",
            "id_producto",
            name="uq_promocion_producto",
        ),
        Index("ix_promocion_producto_id_producto", "id_producto"),
    )

    id_promocion_producto: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    id_promocion: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("t_promocion.id_promocion", ondelete="CASCADE"),
        nullable=False,
    )
    id_producto: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("t_producto.id_producto", ondelete="CASCADE"),
        nullable=False,
    )
