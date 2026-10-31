from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Subscription(Base):
    __tablename__ = "t_suscripcion"
    __table_args__ = (
        CheckConstraint(
            "estado IN ('PRUEBA','ACTIVA','SUSPENDIDA','CANCELADA','EXPIRADA')",
            name="ck_suscripcion_estado",
        ),
        CheckConstraint("fecha_fin_periodo > fecha_inicio", name="ck_suscripcion_periodo"),
        CheckConstraint(
            "fecha_fin_prueba IS NULL OR fecha_fin_prueba >= fecha_inicio",
            name="ck_suscripcion_prueba",
        ),
        CheckConstraint(
            "estado <> 'CANCELADA' OR fecha_cancelacion IS NOT NULL",
            name="ck_suscripcion_cancelacion",
        ),
        CheckConstraint(
            "proveedor IS NULL OR proveedor IN ('MANUAL','STRIPE')",
            name="ck_suscripcion_proveedor",
        ),
        CheckConstraint(
            "referencia_externa IS NULL OR proveedor IS NOT NULL",
            name="ck_suscripcion_referencia",
        ),
        Index("ix_suscripcion_empresa_created_at", "id_empresa", "created_at"),
        Index("ix_suscripcion_estado_fin_periodo", "estado", "fecha_fin_periodo"),
        Index(
            "uq_suscripcion_referencia_externa",
            "proveedor",
            "referencia_externa",
            unique=True,
            postgresql_where=text("referencia_externa IS NOT NULL"),
        ),
        Index(
            "uq_suscripcion_empresa_vigente",
            "id_empresa",
            unique=True,
            postgresql_where=text("estado IN ('PRUEBA','ACTIVA','SUSPENDIDA')"),
        ),
    )

    id_suscripcion: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_empresa: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("t_empresa.id_empresa", name="fk_suscripcion_empresa", ondelete="RESTRICT"),
        nullable=False,
    )
    id_plan_saas: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("t_plan_saas.id_plan_saas", name="fk_suscripcion_plan", ondelete="RESTRICT"),
        nullable=False,
    )
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    fecha_inicio: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    fecha_fin_periodo: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    fecha_fin_prueba: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fecha_cancelacion: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    renovacion_automatica: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    proveedor: Mapped[str | None] = mapped_column(String(20), nullable=True)
    referencia_externa: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
