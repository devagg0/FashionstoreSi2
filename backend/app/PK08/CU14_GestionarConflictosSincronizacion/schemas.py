"""Contratos Pydantic para PK08 - CU14: Gestionar conflictos y resultados de sincronización."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.PK08.CU10_RegistrarReservaOffline.schemas import OfflineReservationSyncRequest
from app.PK08.CU11_RegistrarVentaOffline.schemas import (
    OfflineConflictDetail,
    OfflineConflictType,
    OfflineReservationTransitionRequest,
    OfflineSaleReleaseDetail,
    OfflineSaleSyncRequest,
)
from app.PK08.CU12_ConsultarOperacionesPendientes.schemas import OfflineOperationItemSummary
from app.PK08.CU13_SincronizarOperacionesPendientes.schemas import (
    OfflineCodeLinkItem,
    OfflineSyncOperationInput,
    OfflineSyncOperationResult,
    OfflineSyncOperationType,
    OfflineSyncResultStatus,
    OfflineSyncServerStatus,
)

OfflineResolutionAction = Literal[
    "REINTENTAR_SIN_CAMBIOS",
    "ACEPTAR_PRECIO_SERVIDOR",
    "AJUSTAR_CANTIDAD_STOCK",
    "QUITAR_PRENDA",
    "REPROGRAMAR_HORARIO",
    "CAMBIAR_SUCURSAL",
    "COMPLETAR_TRANSICIONES_RESERVA",
    "CONFIRMAR_Y_ATENDER_RESERVA",
    "VINCULAR_OPERACION_EXISTENTE",
    "DESCARTAR_OPERACION",
]


class OfflineServerVariantSnapshot(BaseModel):
    """Estado actual en PostgreSQL de una variante involucrada en una operación offline."""

    model_config = ConfigDict(from_attributes=True)

    id_variante_producto: int
    id_producto: int | None = None
    sku: str | None = None
    nombre_producto: str | None = None
    activa: bool = True
    stock_actual: int = 0
    stock_reservado: int = 0
    stock_disponible: int = 0
    precio_base_servidor: Decimal = Decimal("0.00")
    descuento_unitario_servidor: Decimal = Decimal("0.00")
    precio_neto_servidor: Decimal = Decimal("0.00")
    id_promocion_activa: int | None = None
    cantidad_solicitada: int = 0
    precio_capturado_offline: Decimal | None = None


class OfflineServerCurrentData(BaseModel):
    """Datos actuales autoritativos del servidor para diagnóstico y resolución en CU14."""

    model_config = ConfigDict(from_attributes=True)

    id_sucursal: int
    sucursal_nombre: str | None = None
    sucursal_activa: bool = True
    hora_apertura_sucursal: str | None = None
    hora_cierre_sucursal: str | None = None
    horarios_sugeridos: list[str] = Field(default_factory=list)
    variantes: list[OfflineServerVariantSnapshot] = Field(default_factory=list)
    subtotal_servidor: Decimal | None = None
    descuento_total_servidor: Decimal | None = None
    total_servidor: Decimal | None = None
    id_reserva_servidor: int | None = None
    codigo_reserva_servidor: str | None = None
    estado_reserva_servidor: str | None = None
    fecha_expiracion_reserva: datetime | None = None
    id_venta_existente: int | None = None
    numero_venta_existente: str | None = None
    estado_venta_existente: str | None = None
    estado_pago_existente: str | None = None


class OfflineOperationConflictDiagnosis(BaseModel):
    """Diagnóstico detallado de una operación offline frente al estado actual de PostgreSQL (CU14)."""

    model_config = ConfigDict(from_attributes=True)

    uuid_operacion: str
    uuid_entidad: str | None = None
    tipo_operacion: OfflineSyncOperationType
    secuencia: int = 1
    depende_de_uuid: str | None = None
    codigo_local: str | None = None
    confirmada_en_servidor: bool = False
    id_servidor: int | None = None
    codigo_servidor: str | None = None
    estado_resultado: OfflineSyncResultStatus
    estado_sincronizacion: OfflineSyncServerStatus
    codigo_conflicto_principal: OfflineConflictType | None = None
    motivo: str | None = None
    corregible: bool = True
    requiere_consentimiento: bool = False
    bloqueada_por_dependencia: bool = False
    conflictos: list[OfflineConflictDetail] = Field(default_factory=list)
    datos_actuales_servidor: OfflineServerCurrentData
    acciones_permitidas: list[OfflineResolutionAction] = Field(default_factory=list)
    mensaje: str


class OfflineConflictDiagnoseRequest(BaseModel):
    """Solicitud de diagnóstico sin mutación de una o varias operaciones offline en conflicto o pendientes."""

    model_config = ConfigDict(from_attributes=True)

    operaciones: list[OfflineSyncOperationInput] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Lista de operaciones offline a diagnosticar contra PostgreSQL",
    )


class OfflineConflictDiagnoseResponse(BaseModel):
    """Respuesta consolidada de diagnóstico de conflictos de sincronización (CU14)."""

    model_config = ConfigDict(from_attributes=True)

    success: bool = True
    empresa_id: int
    id_usuario: int
    rol: str
    total_diagnosticadas: int
    ya_sincronizadas: int
    en_conflicto: int
    rechazadas: int
    listas_para_sincronizar: int
    diagnosticos: list[OfflineOperationConflictDiagnosis]
    diagnosticos_por_uuid: dict[str, OfflineOperationConflictDiagnosis]
    fecha_diagnostico: datetime
    mensaje: str


class OfflineOperationResolutionInput(BaseModel):
    """Instrucción de resolución para una operación offline específica con consentimiento del usuario (CU14)."""

    model_config = ConfigDict(from_attributes=True)

    uuid_operacion: str = Field(..., min_length=6, max_length=128)
    uuid_entidad: str | None = Field(default=None, max_length=128)
    tipo_operacion: OfflineSyncOperationType
    secuencia: int | None = Field(default=None, ge=0)
    depende_de_uuid: str | None = Field(default=None, max_length=128)
    codigo_local: str | None = Field(default=None, max_length=64)
    accion_resolucion: OfflineResolutionAction = Field(
        ...,
        description="Acción elegida por el usuario o cajero según las acciones_permitidas del rol",
    )
    consentimiento_usuario: bool = Field(
        default=False,
        description="Consentimiento explícito del usuario para aplicar cambios comerciales (precio, cantidad, horario, sucursal o descarte)",
    )
    nueva_fecha_atencion_programada: datetime | None = Field(
        default=None,
        description="Nuevo horario de recogida elegido por el CLIENTE al resolver HORARIO_VENCIDO o HORARIO_NO_DISPONIBLE",
    )
    nuevo_id_sucursal: int | None = Field(
        default=None,
        gt=0,
        description="Nueva sucursal elegida por el CLIENTE al resolver falta de stock en sucursal original",
    )
    cantidades_ajustadas: dict[int, int] | None = Field(
        default=None,
        description="Mapa opcional {id_variante_producto: nueva_cantidad} autorizado por el usuario",
    )
    variantes_excluidas: list[int] = Field(
        default_factory=list,
        description="IDs de variantes sin stock que el usuario autoriza retirar de la operación",
    )
    reserva: OfflineReservationSyncRequest | None = None
    compra: OfflineSaleSyncRequest | None = None
    venta: OfflineSaleSyncRequest | None = None
    transicion: OfflineReservationTransitionRequest | None = None
    payload: dict[str, Any] | None = None
    datos_originales: dict[str, Any] | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_embedded_operation(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = OfflineSyncOperationInput._normalize_queue_item(data)
        return normalized


class OfflineOperationResolutionResult(BaseModel):
    """Resultado de la resolución de una operación en CU14, compatible con CU12 y CU13."""

    model_config = ConfigDict(from_attributes=True)

    uuid_operacion: str
    uuid_entidad: str | None = None
    tipo_operacion: OfflineSyncOperationType
    secuencia: int
    accion_aplicada: OfflineResolutionAction
    consentimiento_verificado: bool
    resuelta: bool = Field(
        description="True cuando la operación quedó sincronizada o descartada voluntariamente con éxito"
    )
    descartada_por_usuario: bool = False
    confirmada: bool = Field(
        description="True únicamente cuando la operación comercial fue persistida/confirmada en PostgreSQL"
    )
    estado_resultado: OfflineSyncResultStatus
    estado_sincronizacion: OfflineSyncServerStatus
    id_servidor: int | None = None
    codigo_servidor: str | None = None
    codigo_local: str | None = None
    estado_entidad_servidor: str | None = None
    id_pago: int | None = None
    medio_pago: str | None = None
    estado_pago: str | None = None
    pago_simulado: bool = False
    pendiente_validacion_externa: bool = False
    subtotal: Decimal | None = None
    descuento_total: Decimal | None = None
    total: Decimal | None = None
    moneda: str = "BOB"
    id_reserva_asociada: int | None = None
    codigo_reserva_asociada: str | None = None
    id_sucursal: int | None = None
    id_usuario: int
    id_empresa: int
    reintentable: bool = False
    conservar_en_cola: bool = False
    conflictos: list[OfflineConflictDetail] = Field(default_factory=list)
    liberaciones_reserva: list[OfflineSaleReleaseDetail] = Field(default_factory=list)
    datos_actuales_servidor: OfflineServerCurrentData | None = None
    acciones_permitidas: list[OfflineResolutionAction] = Field(default_factory=list)
    motivo: str | None = None
    mensaje: str
    fecha_resolucion: datetime
    resumen_cu12: OfflineOperationItemSummary | None = None
    resultado_cu13: OfflineSyncOperationResult | None = None


class OfflineConflictResolveRequest(BaseModel):
    """Solicitud en lote o individual para resolver conflictos de sincronización (CU14)."""

    model_config = ConfigDict(from_attributes=True)

    resoluciones: list[OfflineOperationResolutionInput] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Lista ordenada de resoluciones autorizadas por el usuario",
    )

    @model_validator(mode="before")
    @classmethod
    def _accept_operaciones_alias(cls, data: Any) -> Any:
        if isinstance(data, dict) and "resoluciones" not in data and "operaciones" in data:
            copied = dict(data)
            copied["resoluciones"] = copied.pop("operaciones")
            return copied
        return data


class OfflineConflictResolveResponse(BaseModel):
    """Respuesta unificada de resolución de conflictos y resultados de sincronización (CU14)."""

    model_config = ConfigDict(from_attributes=True)

    success: bool
    empresa_id: int
    id_usuario: int
    rol: str
    total_procesadas: int
    confirmadas: int
    descartadas: int
    en_conflicto: int
    rechazadas: int
    reintentables: int
    resultados: list[OfflineOperationResolutionResult]
    resultados_por_uuid: dict[str, OfflineOperationResolutionResult]
    vinculaciones_codigos: dict[str, OfflineCodeLinkItem]
    fecha_resolucion: datetime
    mensaje: str

