"""Mapeos de las tablas existentes CU24; sin DDL en produccion."""
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from sqlalchemy import Integer, String, Numeric, DateTime, Uuid, ForeignKeyConstraint, UniqueConstraint, CheckConstraint, Index, text, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class Return(Base):
    __tablename__ = "t_devolucion"
    __table_args__ = (
        CheckConstraint("tipo IN ('DEVOLUCION','CANCELACION')", name='ck_devolucion_tipo'),
        CheckConstraint("estado IN ('SOLICITADA','APROBADA','RECHAZADA','PROCESADA')", name='ck_devolucion_estado'),
        CheckConstraint('length(trim(motivo)) > 0', name='ck_devolucion_motivo'),
        CheckConstraint("tipo <> 'CANCELACION' OR id_movimiento_inventario IS NULL", name='ck_devolucion_cancelacion'),
        CheckConstraint("estado = 'SOLICITADA' OR (id_usuario_resolutor IS NOT NULL AND fecha_resolucion IS NOT NULL)", name='ck_devolucion_resolucion'),
        CheckConstraint("estado <> 'PROCESADA' OR fecha_procesamiento IS NOT NULL", name='ck_devolucion_procesamiento'),
        CheckConstraint('fecha_resolucion IS NULL OR fecha_resolucion >= created_at', name='ck_devolucion_fecha_resolucion'),
        CheckConstraint('fecha_procesamiento IS NULL OR (fecha_resolucion IS NOT NULL AND fecha_procesamiento >= fecha_resolucion)', name='ck_devolucion_fecha_procesamiento'),
        Index('ix_devolucion_venta_created_at', 'id_venta', 'created_at'),
        Index('ix_devolucion_estado_created_at', 'estado', 'created_at'),
        Index('uq_devolucion_cancelacion_activa', 'id_venta', unique=True, postgresql_where=text("tipo = 'CANCELACION' AND estado IN ('SOLICITADA','APROBADA','PROCESADA')"), sqlite_where=text("tipo = 'CANCELACION' AND estado IN ('SOLICITADA','APROBADA','PROCESADA')")),
        ForeignKeyConstraint(["id_venta"], ["t_venta.id_venta"]),
        ForeignKeyConstraint(["id_usuario_solicitante"], ["t_usuario.id_usuario"]),
        ForeignKeyConstraint(["id_usuario_resolutor"], ["t_usuario.id_usuario"]),
        ForeignKeyConstraint(["id_movimiento_inventario"], ["t_movimiento_inventario.id_movimiento_inventario"]),
        UniqueConstraint("id_devolucion", "id_venta"), UniqueConstraint("clave_idempotencia"),
        UniqueConstraint("id_movimiento_inventario"),
    )
    id_devolucion: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_venta: Mapped[int] = mapped_column(Integer)
    tipo: Mapped[str] = mapped_column(String(20))
    estado: Mapped[str] = mapped_column(String(20))
    motivo: Mapped[str] = mapped_column(String(500))
    id_usuario_solicitante: Mapped[int] = mapped_column(Integer)
    id_usuario_resolutor: Mapped[int | None] = mapped_column(Integer)
    id_movimiento_inventario: Mapped[int | None] = mapped_column(Integer)
    clave_idempotencia: Mapped[UUID] = mapped_column(Uuid)
    fecha_resolucion: Mapped[datetime | None] = mapped_column(DateTime)
    fecha_procesamiento: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

class ReturnDetail(Base):
    __tablename__ = "t_detalle_devolucion"
    __table_args__ = (
        CheckConstraint('cantidad > 0', name='ck_detalle_devolucion_cantidad'),
        CheckConstraint('cantidad_reintegrar >= 0 AND cantidad_reintegrar <= cantidad', name='ck_detalle_devolucion_reintegro'),
        CheckConstraint('importe_restitucion >= 0', name='ck_detalle_devolucion_importe'),
        Index('ix_detalle_devolucion_linea_venta', 'id_venta', 'id_variante_producto'),
        ForeignKeyConstraint(["id_devolucion", "id_venta"], ["t_devolucion.id_devolucion", "t_devolucion.id_venta"]),
        ForeignKeyConstraint(["id_venta", "id_variante_producto"], ["t_detalle_venta.id_venta", "t_detalle_venta.id_variante_producto"]),
        UniqueConstraint("id_devolucion", "id_variante_producto"),
    )
    id_detalle_devolucion: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_devolucion: Mapped[int] = mapped_column(Integer)
    id_venta: Mapped[int] = mapped_column(Integer)
    id_variante_producto: Mapped[int] = mapped_column(Integer)
    cantidad: Mapped[int] = mapped_column(Integer)
    cantidad_reintegrar: Mapped[int] = mapped_column(Integer, default=0)
    importe_restitucion: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

class Refund(Base):
    __tablename__ = "t_reembolso"
    __table_args__ = (
        CheckConstraint("estado IN ('PENDIENTE','APROBADO','RECHAZADO')", name='ck_reembolso_estado'),
        CheckConstraint('monto > 0', name='ck_reembolso_monto'),
        CheckConstraint('referencia_externa IS NULL OR length(trim(referencia_externa)) > 0', name='ck_reembolso_referencia'),
        CheckConstraint("estado <> 'APROBADO' OR fecha_aprobacion IS NOT NULL", name='ck_reembolso_aprobacion'),
        Index('ix_reembolso_pago_estado', 'id_pago', 'estado'),
        Index('ix_reembolso_devolucion_created_at', 'id_devolucion', 'created_at'),
        Index('uq_reembolso_devolucion_pendiente', 'id_devolucion', unique=True, postgresql_where=text("estado = 'PENDIENTE'"), sqlite_where=text("estado = 'PENDIENTE'")),
        ForeignKeyConstraint(["id_pago", "id_venta"], ["t_pago.id_pago", "t_pago.id_venta"]),
        ForeignKeyConstraint(["id_devolucion", "id_venta"], ["t_devolucion.id_devolucion", "t_devolucion.id_venta"]),
        ForeignKeyConstraint(["id_usuario_responsable"], ["t_usuario.id_usuario"]),
        UniqueConstraint("clave_idempotencia"), UniqueConstraint("id_pago", "referencia_externa"),
    )
    id_reembolso: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_venta: Mapped[int] = mapped_column(Integer)
    id_pago: Mapped[int] = mapped_column(Integer)
    id_devolucion: Mapped[int] = mapped_column(Integer)
    estado: Mapped[str] = mapped_column(String(20))
    monto: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    referencia_externa: Mapped[str | None] = mapped_column(String(255))
    clave_idempotencia: Mapped[UUID] = mapped_column(Uuid)
    id_usuario_responsable: Mapped[int | None] = mapped_column(Integer)
    fecha_aprobacion: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
