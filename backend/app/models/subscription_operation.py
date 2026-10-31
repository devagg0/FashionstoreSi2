"""Modelo SQLAlchemy para registrar operaciones, pagos y cambios programados de suscripciones SaaS."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SubscriptionOperation(Base):
    __tablename__ = "t_operacion_suscripcion"
    __table_args__ = (
        CheckConstraint(
            "tipo_operacion IN ('CONTRATACION','RENOVACION','CAMBIO_PLAN')",
            name="ck_operacion_suscripcion_tipo",
        ),
        CheckConstraint(
            "estado IN ('PENDIENTE','COMPLETADA','FALLIDA','CANCELADA','PROGRAMADA')",
            name="ck_operacion_suscripcion_estado",
        ),
        CheckConstraint(
            "metodo_pago IN ('TARJETA','QR')",
            name="ck_operacion_suscripcion_metodo",
        ),
        Index("ix_operacion_suscripcion_empresa", "id_empresa", "created_at"),
        Index("ix_operacion_suscripcion_sesion", "id_sesion_checkout"),
    )

    id_operacion: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_empresa: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("t_empresa.id_empresa", name="fk_operacion_suscripcion_empresa", ondelete="CASCADE"),
        nullable=False,
    )
    id_plan_saas: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("t_plan_saas.id_plan_saas", name="fk_operacion_suscripcion_plan", ondelete="RESTRICT"),
        nullable=False,
    )
    id_suscripcion: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("t_suscripcion.id_suscripcion", name="fk_operacion_suscripcion_sub", ondelete="SET NULL"),
        nullable=True,
    )
    tipo_operacion: Mapped[str] = mapped_column(String(30), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'PENDIENTE'"))
    metodo_pago: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'TARJETA'"))
    monto: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    moneda: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'BOB'"))
    proveedor: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'STRIPE'"))
    id_sesion_checkout: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    id_pago_externo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fecha_ejecucion_programada: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

