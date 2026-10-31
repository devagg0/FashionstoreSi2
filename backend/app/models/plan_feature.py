from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PlanFeature(Base):
    __tablename__ = "t_plan_funcionalidad"
    __table_args__ = (
        CheckConstraint("limite IS NULL OR limite >= 0", name="ck_plan_funcionalidad_limite"),
    )

    id_plan_saas: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("t_plan_saas.id_plan_saas", name="fk_plan_funcionalidad_plan", ondelete="CASCADE"),
        primary_key=True,
    )
    id_funcionalidad_saas: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "t_funcionalidad_saas.id_funcionalidad_saas",
            name="fk_plan_funcionalidad_funcionalidad",
            ondelete="RESTRICT",
        ),
        primary_key=True,
    )
    habilitada: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    limite: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
