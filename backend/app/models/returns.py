"""Mapeos de las tablas existentes CU24; sin DDL en produccion."""
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from sqlalchemy import Integer, String, Numeric, DateTime, Boolean, Uuid, ForeignKeyConstraint, UniqueConstraint, CheckConstraint, Index, text, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from app.models.tenant import TenantMixin

class Return(TenantMixin, Base):
    __tablename__ = "t_devolucion"
    __table_args__ = (
        CheckConstraint("tipo IN ('DEVOLUCION','CANCELACION','CAMBIO')", name='ck_devolucion_tipo'),
        CheckConstraint("estado IN ('SOLICITADA','ACEPTADA_INICIALMENTE','PENDIENTE_ENTREGA','RECIBIDA','APROBADA','RECHAZADA','PROCESADA')", name='ck_devolucion_estado'),
        CheckConstraint("modalidad_entrega IS NULL OR modalidad_entrega IN ('ENTREGA_EN_TIENDA','DELIVERY_SIMULADO')", name='ck_devolucion_modalidad_entrega'),
        CheckConstraint('length(trim(motivo)) > 0', name='ck_devolucion_motivo'),
        CheckConstraint("tipo <> 'CANCELACION' OR id_movimiento_inventario IS NULL", name='ck_devolucion_cancelacion'),
        CheckConstraint("estado NOT IN ('APROBADA','RECHAZADA','PROCESADA') OR (id_usuario_resolutor IS NOT NULL AND fecha_resolucion IS NOT NULL)", name='ck_devolucion_resolucion'),
        CheckConstraint("estado <> 'PROCESADA' OR fecha_procesamiento IS NOT NULL", name='ck_devolucion_procesamiento'),
        CheckConstraint('fecha_resolucion IS NULL OR fecha_resolucion >= created_at', name='ck_devolucion_fecha_resolucion'),
        CheckConstraint('fecha_procesamiento IS NULL OR (fecha_resolucion IS NOT NULL AND fecha_procesamiento >= fecha_resolucion)', name='ck_devolucion_fecha_procesamiento'),
        CheckConstraint("estado_pago_adicional IS NULL OR estado_pago_adicional IN ('PENDIENTE', 'CONFIRMADO', 'NO_APLICA')", name='ck_devolucion_estado_pago_adicional'),
        Index('ix_devolucion_venta_created_at', 'id_venta', 'created_at'),
        Index('ix_devolucion_estado_created_at', 'estado', 'created_at'),
        Index('uq_devolucion_cancelacion_activa', 'id_venta', unique=True, postgresql_where=text("tipo = 'CANCELACION' AND estado IN ('SOLICITADA','APROBADA','PROCESADA')"), sqlite_where=text("tipo = 'CANCELACION' AND estado IN ('SOLICITADA','APROBADA','PROCESADA')")),
        ForeignKeyConstraint(["id_venta"], ["t_venta.id_venta"], name="fk_devolucion_venta", ondelete="RESTRICT"),
        ForeignKeyConstraint(["id_usuario_solicitante"], ["t_usuario.id_usuario"], name="fk_devolucion_solicitante", ondelete="RESTRICT"),
        ForeignKeyConstraint(["id_usuario_resolutor"], ["t_usuario.id_usuario"], name="fk_devolucion_resolutor", ondelete="RESTRICT"),
        ForeignKeyConstraint(["id_usuario_evaluador"], ["t_usuario.id_usuario"], name="fk_devolucion_evaluador", ondelete="RESTRICT"),
        ForeignKeyConstraint(["id_usuario_receptor"], ["t_usuario.id_usuario"], name="fk_devolucion_receptor", ondelete="RESTRICT"),
        ForeignKeyConstraint(["id_usuario_inspector"], ["t_usuario.id_usuario"], name="fk_devolucion_inspector", ondelete="RESTRICT"),
        ForeignKeyConstraint(["id_movimiento_inventario"], ["t_movimiento_inventario.id_movimiento_inventario"], name="fk_devolucion_movimiento", ondelete="RESTRICT"),
        UniqueConstraint("id_devolucion", "id_venta"), UniqueConstraint("clave_idempotencia"),
        UniqueConstraint("id_movimiento_inventario"),
    )
    id_devolucion: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_venta: Mapped[int] = mapped_column(Integer)
    tipo: Mapped[str] = mapped_column(String(20))
    estado: Mapped[str] = mapped_column(String(30))
    modalidad_entrega: Mapped[str | None] = mapped_column(String(30), nullable=True, default=None)
    motivo: Mapped[str] = mapped_column(String(500))
    motivo_rechazo: Mapped[str | None] = mapped_column(String(500), nullable=True, default=None)
    id_usuario_solicitante: Mapped[int] = mapped_column(Integer)
    id_usuario_resolutor: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    id_usuario_evaluador: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    id_usuario_receptor: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    id_usuario_inspector: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    id_movimiento_inventario: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    clave_idempotencia: Mapped[UUID] = mapped_column(Uuid)
    fecha_evaluacion_inicial: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    fecha_seleccion_modalidad: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    fecha_recepcion: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    estado_fisico: Mapped[str | None] = mapped_column(String(50), nullable=True, default=None)
    etiquetas_intactas: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=None)
    correspondencia_compra: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=None)
    observaciones_inspeccion: Mapped[str | None] = mapped_column(String(500), nullable=True, default=None)
    fecha_inspeccion: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    fecha_resolucion: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    fecha_procesamiento: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    diferencia_definitiva: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True, default=None)
    monto_adicional_cobrado: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True, default=None)
    medio_pago_adicional: Mapped[str | None] = mapped_column(String(20), nullable=True, default=None)
    referencia_pago_adicional: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    estado_pago_adicional: Mapped[str | None] = mapped_column(String(20), nullable=True, default=None)
    stripe_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    fecha_entrega_reemplazo: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

class ReturnDetail(TenantMixin, Base):
    __tablename__ = "t_detalle_devolucion"
    __table_args__ = (
        CheckConstraint('cantidad > 0', name='ck_detalle_devolucion_cantidad'),
        CheckConstraint('cantidad_reintegrar >= 0 AND cantidad_reintegrar <= cantidad', name='ck_detalle_devolucion_reintegro'),
        CheckConstraint('importe_restitucion >= 0', name='ck_detalle_devolucion_importe'),
        CheckConstraint('cantidad_reemplazo >= 0', name='ck_detalle_devolucion_cantidad_reemplazo'),
        CheckConstraint('(id_variante_reemplazo IS NULL AND cantidad_reemplazo = 0) OR (id_variante_reemplazo IS NOT NULL AND cantidad_reemplazo = cantidad)', name='ck_detalle_devolucion_reemplazo_consistente'),
        CheckConstraint('precio_original_reconocido >= 0 AND precio_reemplazo_estimado >= 0', name='ck_detalle_devolucion_precios_estimados'),
        Index('ix_detalle_devolucion_linea_venta', 'id_venta', 'id_variante_producto'),
        ForeignKeyConstraint(["id_devolucion", "id_venta"], ["t_devolucion.id_devolucion", "t_devolucion.id_venta"], name="fk_detalle_devolucion_cabecera", ondelete="RESTRICT"),
        ForeignKeyConstraint(["id_venta", "id_variante_producto"], ["t_detalle_venta.id_venta", "t_detalle_venta.id_variante_producto"], name="fk_detalle_devolucion_linea_venta", ondelete="RESTRICT"),
        ForeignKeyConstraint(["id_variante_reemplazo"], ["t_variante_producto.id_variante_producto"], name="fk_detalle_devolucion_variante_reemplazo", ondelete="RESTRICT"),
        UniqueConstraint("id_devolucion", "id_variante_producto"),
    )
    id_detalle_devolucion: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_devolucion: Mapped[int] = mapped_column(Integer)
    id_venta: Mapped[int] = mapped_column(Integer)
    id_variante_producto: Mapped[int] = mapped_column(Integer)
    cantidad: Mapped[int] = mapped_column(Integer)
    cantidad_reintegrar: Mapped[int] = mapped_column(Integer, default=0)
    importe_restitucion: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    id_variante_reemplazo: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cantidad_reemplazo: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    precio_original_reconocido: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), server_default=text("0"))
    precio_reemplazo_estimado: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), server_default=text("0"))
    diferencia_precio_estimada: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

class Refund(TenantMixin, Base):
    __tablename__ = "t_reembolso"
    __table_args__ = (
        CheckConstraint("estado IN ('PENDIENTE','APROBADO','RECHAZADO')", name='ck_reembolso_estado'),
        CheckConstraint('monto > 0', name='ck_reembolso_monto'),
        CheckConstraint('referencia_externa IS NULL OR length(trim(referencia_externa)) > 0', name='ck_reembolso_referencia'),
        CheckConstraint("estado <> 'APROBADO' OR fecha_aprobacion IS NOT NULL", name='ck_reembolso_aprobacion'),
        Index('ix_reembolso_pago_estado', 'id_pago', 'estado'),
        Index('ix_reembolso_devolucion_created_at', 'id_devolucion', 'created_at'),
        Index('uq_reembolso_devolucion_pendiente', 'id_devolucion', unique=True, postgresql_where=text("estado = 'PENDIENTE'"), sqlite_where=text("estado = 'PENDIENTE'")),
        ForeignKeyConstraint(["id_pago", "id_venta"], ["t_pago.id_pago", "t_pago.id_venta"], name="fk_reembolso_pago_venta", ondelete="RESTRICT"),
        ForeignKeyConstraint(["id_devolucion", "id_venta"], ["t_devolucion.id_devolucion", "t_devolucion.id_venta"], name="fk_reembolso_devolucion_venta", ondelete="RESTRICT"),
        ForeignKeyConstraint(["id_usuario_responsable"], ["t_usuario.id_usuario"], name="fk_reembolso_responsable", ondelete="RESTRICT"),
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
