from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Integer, Numeric, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SaasPlan(Base):
    __tablename__ = "t_plan_saas"
    __table_args__ = (
        CheckConstraint("length(trim(codigo)) > 0", name="ck_plan_saas_codigo"),
        CheckConstraint("length(trim(nombre)) > 0", name="ck_plan_saas_nombre"),
        CheckConstraint("precio >= 0", name="ck_plan_saas_precio"),
        CheckConstraint("moneda = 'BOB'", name="ck_plan_saas_moneda"),
        CheckConstraint("periodo_meses > 0", name="ck_plan_saas_periodo"),
        Index("ix_plan_saas_estado_precio", "estado", "precio"),
    )

    id_plan_saas: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(String(300), nullable=True)
    precio: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    moneda: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'BOB'"))
    periodo_meses: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    estado: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
