"""Mapeo de t_pago existente del Ciclo 3; no crea ni altera tablas."""
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Payment(Base):
    __tablename__ = "t_pago"
    __table_args__ = (
        UniqueConstraint("clave_idempotencia", name="uq_pago_idempotencia"),
        UniqueConstraint("proveedor", "entorno", "referencia_externa", name="uq_pago_referencia"),
        UniqueConstraint("id_pago", "id_venta", name="uq_pago_venta_pertenencia"),
        CheckConstraint("estado IN ('PENDIENTE','APROBADO','RECHAZADO','CANCELADO','EXPIRADO','REEMBOLSADO')", name="ck_pago_estado"),
        CheckConstraint("medio IN ('EFECTIVO','QR','TARJETA')", name="ck_pago_medio"),
        CheckConstraint("proveedor IN ('MANUAL','STRIPE')", name="ck_pago_proveedor"),
        CheckConstraint("entorno IN ('LOCAL','TEST')", name="ck_pago_entorno"),
        CheckConstraint("(proveedor = 'MANUAL' AND entorno = 'LOCAL' AND medio IN ('EFECTIVO','QR')) OR (proveedor = 'STRIPE' AND entorno = 'TEST' AND medio = 'TARJETA')", name="ck_pago_combinacion"),
        CheckConstraint("monto > 0", name="ck_pago_monto"),
        CheckConstraint("moneda = 'BOB'", name="ck_pago_moneda"),
        CheckConstraint("referencia_externa IS NULL OR length(trim(referencia_externa)) > 0", name="ck_pago_referencia"),
        CheckConstraint("estado NOT IN ('APROBADO','REEMBOLSADO') OR fecha_aprobacion IS NOT NULL", name="ck_pago_aprobacion"),
        CheckConstraint("proveedor <> 'STRIPE' OR estado NOT IN ('APROBADO','REEMBOLSADO') OR referencia_externa IS NOT NULL", name="ck_pago_stripe_referencia"),
        Index("ix_pago_venta_created_at", "id_venta", "created_at"),
        Index("uq_pago_venta_cobrado", "id_venta", unique=True,
              postgresql_where=text("estado IN ('APROBADO','REEMBOLSADO')"),
              sqlite_where=text("estado IN ('APROBADO','REEMBOLSADO')")),
        Index("uq_pago_venta_pendiente", "id_venta", unique=True,
              postgresql_where=text("estado = 'PENDIENTE'"), sqlite_where=text("estado = 'PENDIENTE'")),
    )

    id_pago: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_venta: Mapped[int] = mapped_column(Integer, ForeignKey("t_venta.id_venta", name="fk_pago_venta", ondelete="RESTRICT"))
    medio: Mapped[str] = mapped_column(String(20))
    proveedor: Mapped[str] = mapped_column(String(20))
    entorno: Mapped[str] = mapped_column(String(20))
    estado: Mapped[str] = mapped_column(String(20), default="PENDIENTE", server_default=text("'PENDIENTE'"))
    monto: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    moneda: Mapped[str] = mapped_column(String(3))
    referencia_externa: Mapped[str | None] = mapped_column(String(255), nullable=True)
    clave_idempotencia: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    fecha_aprobacion: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
