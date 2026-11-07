"""Contratos Pydantic para PK08 - CU11: Registrar venta de contado y compra digital offline en FashionStore."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OfflineSaleLineRequest(BaseModel):
    """Línea de prenda incluida en una venta presencial o compra digital registrada offline."""

    model_config = ConfigDict(from_attributes=True)

    id_variante_producto: int = Field(gt=0, description="ID de la variante comercializable")
    cantidad: int = Field(gt=0, description="Cantidad de unidades de la variante")
    id_producto: int | None = Field(
        default=None, gt=0, description="ID del producto (opcional para validación cruzada)"
    )
    sku: str | None = Field(
        default=None, max_length=100, description="SKU referencial de la variante"
    )
    id_talla: int | None = Field(
        default=None, gt=0, description="ID de la talla (opcional para validación cruzada)"
    )
    id_color: int | None = Field(
        default=None, gt=0, description="ID del color (opcional para validación cruzada)"
    )
    precio_unitario: Decimal | None = Field(
        default=None, ge=0, description="Precio unitario capturado localmente en modo offline"
    )
    descuento_unitario: Decimal | None = Field(
        default=None, ge=0, description="Descuento unitario aplicado localmente"
    )
    subtotal_linea: Decimal | None = Field(
        default=None, ge=0, description="Subtotal de la línea capturado localmente"
    )
    id_promocion: int | None = Field(
        default=None, gt=0, description="ID de promoción vigente aplicada en la cotización"
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_price_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            copied = dict(data)
            if "precio_unitario" not in copied:
                if "precio_referencial" in copied:
                    copied["precio_unitario"] = copied.pop("precio_referencial")
                elif "precio_aplicado" in copied:
                    copied["precio_unitario"] = copied.pop("precio_aplicado")
                elif "precio" in copied:
                    copied["precio_unitario"] = copied.pop("precio")
            return copied
        return data


class OfflineSaleSyncRequest(BaseModel):
    """Solicitud de recepción/sincronización de venta de contado (POS) o compra digital creada offline."""

    model_config = ConfigDict(from_attributes=True)

    uuid_venta_offline: str = Field(
        ...,
        min_length=10,
        max_length=64,
        description="UUID idempotente generado en IndexedDB para la venta o compra offline",
    )
    canal: Literal["PRESENCIAL", "DIGITAL"] | None = Field(
        default=None,
        description="Canal comercial ('PRESENCIAL' para CAJERO, 'DIGITAL' para CLIENTE); se valida contra el rol",
    )
    id_empresa: int | None = Field(
        default=None,
        gt=0,
        description="Opcional; validado estrictamente contra el tenant de la sesión autenticada",
    )
    id_usuario: int | None = Field(
        default=None,
        gt=0,
        description="Opcional; validado estrictamente contra el usuario de la sesión autenticada",
    )
    id_sucursal: int = Field(
        gt=0,
        description="ID de la sucursal donde se realiza la venta presencial o el retiro/despacho digital",
    )
    id_cliente: int | None = Field(
        default=None,
        gt=0,
        description="ID del cliente (en DIGITAL se resuelve desde la sesión; en PRESENCIAL desde la reserva o opcional)",
    )
    id_carrito: int | None = Field(
        default=None,
        gt=0,
        description="ID del carrito activo del cliente en caso de provenir de un carrito persistido previamente",
    )
    id_reserva: int | None = Field(
        default=None,
        gt=0,
        description="ID de la reserva ATENDIDA cuando la venta presencial se origina desde 'Venta por reserva'",
    )
    codigo_reserva: str | None = Field(
        default=None,
        max_length=50,
        description="Código alfanumérico de la reserva ATENDIDA (alternativa o validación cruzada a id_reserva)",
    )
    uuid_reserva_offline: str | None = Field(
        default=None,
        max_length=64,
        description="UUID de la reserva offline (si la reserva fue creada en CU10 antes de sincronizarse)",
    )
    detalles: list[OfflineSaleLineRequest] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Lista de variantes y cantidades vendidas o compradas",
    )
    subtotal: Decimal | None = Field(
        default=None, ge=0, description="Subtotal capturado localmente antes de descuentos"
    )
    descuento_total: Decimal | None = Field(
        default=None, ge=0, description="Descuento total capturado localmente"
    )
    total: Decimal | None = Field(
        default=None, gt=0, description="Importe total de la operación capturado localmente"
    )
    moneda: Literal["BOB"] = Field(default="BOB", description="Moneda oficial de operación (BOB)")
    medio_pago: Literal["EFECTIVO", "QR", "TARJETA"] = Field(
        ...,
        description="Medio de pago utilizado ('EFECTIVO' exclusivo de CAJERO presencial; 'QR' y 'TARJETA' simulados offline)",
    )
    pago_simulado: bool | None = Field(
        default=None,
        description="Indica si el pago fue simulado offline; QR y TARJETA offline siempre quedan pendientes de validación externa",
    )
    referencia_pago_local: str | None = Field(
        default=None,
        max_length=255,
        description="Referencia local informativa del comprobante/simulación (nunca se asume como aprobación bancaria)",
    )
    fecha_venta_offline: datetime | None = Field(
        default=None,
        description="Fecha y hora de creación de la operación en el dispositivo local",
    )
    observaciones: str | None = Field(default=None, max_length=500)

    @model_validator(mode="before")
    @classmethod
    def _normalize_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            copied = dict(data)
            if "uuid_venta_offline" not in copied:
                if "uuid_operacion_offline" in copied:
                    copied["uuid_venta_offline"] = copied.pop("uuid_operacion_offline")
                elif "idempotency_key" in copied:
                    copied["uuid_venta_offline"] = str(copied.pop("idempotency_key"))
            if "detalles" not in copied and "items" in copied:
                copied["detalles"] = copied.pop("items")
            if "medio_pago" not in copied:
                if "metodo_pago" in copied:
                    copied["medio_pago"] = copied.pop("metodo_pago")
                elif "medio" in copied:
                    copied["medio_pago"] = copied.pop("medio")
            if "fecha_venta_offline" not in copied:
                if "fecha_operacion_offline" in copied:
                    copied["fecha_venta_offline"] = copied.pop("fecha_operacion_offline")
                elif "fecha_venta" in copied:
                    copied["fecha_venta_offline"] = copied.pop("fecha_venta")
            return copied
        return data


class OfflineSaleReleaseDetail(BaseModel):
    """Detalle de liberación de stock reservado cuando una venta por reserva es parcial."""

    model_config = ConfigDict(from_attributes=True)

    id_variante_producto: int
    cantidad_reservada: int
    cantidad_comprada: int
    cantidad_liberada: int


OfflineConflictType = Literal[
    "STOCK_INSUFICIENTE",
    "PRECIO_MODIFICADO",
    "HORARIO_VENCIDO",
    "HORARIO_NO_DISPONIBLE",
    "RESERVA_CANCELADA",
    "RESERVA_NO_ATENDIDA",
    "RESERVA_VENTA_DUPLICADA",
    "RESERVA_ESTADO_INVALIDO",
    "CARRITO_YA_CONVERTIDO",
    "OPERACION_DUPLICADA",
    "DEPENDENCIA_BLOQUEADA",
    "ERROR_REINTENTABLE",
    "CONCURRENCIA",
    "REGLA_NEGOCIO",
]


class OfflineConflictDetail(BaseModel):
    """Información estructurada y normalizada de conflicto para resolución en CU13 y CU14."""

    model_config = ConfigDict(from_attributes=True)

    tipo_conflicto: OfflineConflictType
    codigo_conflicto: str | None = Field(
        default=None,
        description="Código normalizado del conflicto (idéntico a tipo_conflicto por defecto)",
    )
    id_variante_producto: int | None = None
    sku: str | None = None
    valor_esperado: str | int | Decimal | None = None
    valor_actual_servidor: str | int | Decimal | None = None
    detalle: str
    corregible: bool = Field(
        default=True,
        description="True cuando el usuario puede corregir o reintentar la operación con consentimiento",
    )
    requiere_consentimiento: bool = Field(
        default=True,
        description="True cuando la resolución altera condiciones comerciales (precio, cantidad, horario) y exige consentimiento explícito",
    )
    datos_servidor: dict[str, Any] | None = Field(
        default=None,
        description="Estado autoritativo actual en PostgreSQL (stock disponible, precio vigente, estado de reserva, horario)",
    )
    acciones_permitidas: list[str] = Field(
        default_factory=list,
        description="Acciones de resolución permitidas según el rol autenticado (CLIENTE o CAJERO)",
    )

    @model_validator(mode="after")
    def _populate_conflict_code(self) -> "OfflineConflictDetail":
        if not self.codigo_conflicto:
            self.codigo_conflicto = self.tipo_conflicto
        return self


class OfflineSaleSyncResponse(BaseModel):
    """Respuesta estructurada de sincronización idempotente de venta presencial o compra digital offline."""

    model_config = ConfigDict(from_attributes=True)

    success: bool
    confirmada: bool = Field(
        description="True únicamente cuando la operación comercial quedó persistida en el servidor central"
    )
    uuid_venta_offline: str
    canal: Literal["PRESENCIAL", "DIGITAL"]
    estado_sincronizacion: Literal["SINCRONIZADA", "RECHAZADA", "CONFLICTO"]
    estado_resultado: Literal["CONFIRMADA", "RECHAZADA", "EN_CONFLICTO"]
    id_venta: int | None = None
    numero_venta: str | None = None
    estado_venta: Literal["PENDIENTE", "COMPLETADA", "ANULADA", "RECHAZADA"] | None = None
    id_pago: int | None = None
    medio_pago: Literal["EFECTIVO", "QR", "TARJETA"]
    estado_pago: (
        Literal["PENDIENTE", "APROBADO", "RECHAZADO", "CANCELADO", "EXPIRADO", "REEMBOLSADO"]
        | None
    ) = None
    pago_simulado: bool = Field(
        description="True cuando el pago corresponde a QR/TARJETA simulado offline"
    )
    pendiente_validacion_externa: bool = Field(
        description="True cuando el pago electrónico queda PENDIENTE de confirmación externa/pasarela"
    )
    stock_comprometido: bool = False
    id_reserva: int | None = None
    codigo_reserva: str | None = None
    estado_reserva: (
        Literal["PENDIENTE", "CONFIRMADA", "ATENDIDA", "CANCELADA", "EXPIRADA"] | None
    ) = None
    id_sucursal: int
    id_cliente: int | None = None
    id_empleado: int | None = None
    id_usuario: int
    id_empresa: int
    subtotal: Decimal | None = None
    descuento_total: Decimal | None = None
    total: Decimal | None = None
    moneda: str = "BOB"
    liberaciones_reserva: list[OfflineSaleReleaseDetail] = Field(default_factory=list)
    conflictos: list[OfflineConflictDetail] = Field(default_factory=list)
    conservar_operacion_pendiente: bool = Field(
        default=False,
        description="True en RECHAZADA o EN_CONFLICTO para que IndexedDB conserve la operación pendiente para CU13/CU14",
    )
    motivo: str | None = None
    fecha_operacion_offline: datetime
    fecha_sincronizacion: datetime
    mensaje: str


class OfflineReservationTransitionRequest(BaseModel):
    """Solicitud de transición offline de reserva por personal de sucursal (PENDIENTE -> CONFIRMADA -> ATENDIDA)."""

    model_config = ConfigDict(from_attributes=True)

    uuid_operacion_offline: str = Field(
        ...,
        min_length=10,
        max_length=64,
        description="UUID idempotente de la transición registrada en modo offline",
    )
    id_reserva: int | None = Field(default=None, gt=0, description="ID de la reserva en servidor")
    codigo_reserva: str | None = Field(
        default=None, max_length=50, description="Código de la reserva (ej. RSV-...)"
    )
    uuid_reserva_offline: str | None = Field(
        default=None, max_length=64, description="UUID offline de la reserva (si provino de CU10)"
    )
    accion: Literal["CONFIRM", "ATTEND", "CONFIRMAR", "ATENDER"] = Field(
        ...,
        description="Acción del flujo original CU18: CONFIRM (PENDIENTE -> CONFIRMADA) o ATTEND (CONFIRMADA -> ATENDIDA)",
    )
    id_sucursal: int | None = Field(
        default=None, gt=0, description="Sucursal donde el cajero o encargado atiende la reserva"
    )
    id_empresa: int | None = Field(default=None, gt=0)
    id_usuario: int | None = Field(default=None, gt=0)
    fecha_operacion_offline: datetime | None = Field(default=None)


class OfflineReservationTransitionResponse(BaseModel):
    """Respuesta estructurada de sincronización de transición de estado de reserva (CU18 offline)."""

    model_config = ConfigDict(from_attributes=True)

    success: bool
    confirmada: bool
    uuid_operacion_offline: str
    id_reserva: int | None = None
    codigo_reserva: str | None = None
    accion_aplicada: Literal["CONFIRM", "ATTEND"]
    estado_anterior: str | None = None
    estado_reserva: (
        Literal["PENDIENTE", "CONFIRMADA", "ATENDIDA", "CANCELADA", "EXPIRADA"] | None
    ) = None
    estado_sincronizacion: Literal["SINCRONIZADA", "RECHAZADA", "CONFLICTO"]
    estado_resultado: Literal["CONFIRMADA", "RECHAZADA", "EN_CONFLICTO"]
    id_sucursal: int | None = None
    id_empleado_atencion: int | None = None
    id_usuario: int
    id_empresa: int
    conflictos: list[OfflineConflictDetail] = Field(default_factory=list)
    conservar_operacion_pendiente: bool = False
    motivo: str | None = None
    fecha_sincronizacion: datetime
    mensaje: str


class OfflineBatchOperationItem(BaseModel):
    """Operación individual dentro de una secuencia ordenada para sincronización (ej. confirmar -> atender -> vender)."""

    model_config = ConfigDict(from_attributes=True)

    tipo_operacion: Literal["TRANSICION_RESERVA", "VENTA"]
    transicion: OfflineReservationTransitionRequest | None = None
    venta: OfflineSaleSyncRequest | None = None


class OfflineBatchSyncRequest(BaseModel):
    """Lote secuencial ordenado de operaciones offline dependientes (preparado para CU13)."""

    model_config = ConfigDict(from_attributes=True)

    operaciones: list[OfflineBatchOperationItem] = Field(..., min_length=1, max_length=50)


class OfflineBatchSyncResponse(BaseModel):
    """Resultado detallado de la ejecución secuencial de un lote de operaciones offline."""

    model_config = ConfigDict(from_attributes=True)

    success: bool
    total_operaciones: int
    confirmadas: int
    rechazadas: int
    en_conflicto: int
    resultados: list[OfflineReservationTransitionResponse | OfflineSaleSyncResponse]

