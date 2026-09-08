from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Promotion(Base):
    __tablename__ = "t_promocion"
    __table_args__ = (
        CheckConstraint(
            "tipo_descuento IN ('PORCENTAJE', 'MONTO_FIJO')",
            name="ck_promocion_tipo_descuento",
        ),
        CheckConstraint("valor > 0", name="ck_promocion_valor_positivo"),
        CheckConstraint(
            "tipo_descuento <> 'PORCENTAJE' OR valor <= 100",
            name="ck_promocion_porcentaje_valido",
        ),
        CheckConstraint(
            "fecha_fin >= fecha_inicio",
            name="ck_promocion_rango_fechas",
        ),
        Index(
            "ix_promocion_vigencia",
            "estado",
            "fecha_inicio",
            "fecha_fin",
        ),
    )

    id_promocion: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    codigo: Mapped[str | None] = mapped_column(
        String(50), nullable=True, unique=True
    )
    descripcion: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tipo_descuento: Mapped[str] = mapped_column(String(20), nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    fecha_inicio: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    fecha_fin: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    acumulable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    estado: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
