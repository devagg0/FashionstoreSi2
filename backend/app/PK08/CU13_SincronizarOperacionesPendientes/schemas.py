"""Contratos Pydantic para PK08 - CU13: Sincronizar operaciones pendientes de FashionStore."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.PK08.CU10_RegistrarReservaOffline.schemas import OfflineReservationSyncRequest
from app.PK08.CU11_RegistrarVentaOffline.schemas import (
    OfflineConflictDetail,
    OfflineReservationTransitionRequest,
    OfflineSaleReleaseDetail,
    OfflineSaleSyncRequest,
)
from app.PK08.CU12_ConsultarOperacionesPendientes.schemas import OfflineOperationItemSummary

OfflineSyncOperationType = Literal["RESERVA", "COMPRA", "VENTA", "TRANSICION_RESERVA"]
OfflineSyncResultStatus = Literal[
    "CONFIRMADA", "RECHAZADA", "EN_CONFLICTO", "REINTENTABLE"
]
OfflineSyncServerStatus = Literal[
    "SINCRONIZADA", "RECHAZADA", "CONFLICTO", "PENDIENTE_SINCRONIZACION"
]


class OfflineSyncOperationInput(BaseModel):
    """Operación individual de la cola offline de Angular (IndexedDB) enviada para sincronización central."""

    model_config = ConfigDict(from_attributes=True)

    uuid_operacion: str = Field(
        ...,
        min_length=6,
        max_length=128,
        description="UUID idempotente único de la operación en la cola local",
    )
    uuid_entidad: str | None = Field(
        default=None,
        max_length=128,
        description="UUID de la entidad comercial asociada (reserva o venta)",
    )
    tipo_operacion: OfflineSyncOperationType = Field(
        ...,
        description="Tipo de operación: RESERVA, COMPRA, VENTA o TRANSICION_RESERVA",
    )
    secuencia: int | None = Field(
        default=None,
        ge=0,
        description="Orden secuencial dentro del lote para preservar dependencias",
    )
    depende_de_uuid: str | None = Field(
        default=None,
        max_length=128,
        description="UUID de la operación previa de la cual depende esta operación",
    )
    codigo_local: str | None = Field(
        default=None,
        max_length=64,
        description="Código provisional asignado en modo offline (ej. RSV-LOC-001, DIG-LOC-001, VTA-LOC-001)",
    )
    fecha_operacion_offline: datetime | None = Field(
        default=None,
        description="Fecha y hora original en que se registró la operación sin conexión",
    )
    reserva: OfflineReservationSyncRequest | None = Field(
        default=None,
        description="Datos de reserva offline del CLIENTE (CU10)",
    )
    compra: OfflineSaleSyncRequest | None = Field(
        default=None,
        description="Datos de compra digital offline del CLIENTE (CU11)",
    )
    venta: OfflineSaleSyncRequest | None = Field(
        default=None,
        description="Datos de venta presencial POS offline del CAJERO (CU11)",
    )
    transicion: OfflineReservationTransitionRequest | None = Field(
        default=None,
        description="Datos de transición de atención de reserva del CAJERO (PENDIENTE -> CONFIRMADA -> ATENDIDA)",
    )
    payload: dict[str, Any] | None = Field(
        default=None,
        description="Payload crudo de OfflineSyncQueueItem desde IndexedDB (normalizado automáticamente)",
    )
    datos_originales: dict[str, Any] | None = Field(
        default=None,
        description="Alias de payload crudo desde cola_sincronizacion_offline de IndexedDB",
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_queue_item(cls, data: Any) -> Any:
        """Normaliza tanto formatos tipados como registros crudos de cola_sincronizacion_offline de Angular."""
        if not isinstance(data, dict):
            return data

        copied = dict(data)
        if not copied.get("uuid_operacion") and copied.get("id_operacion"):
            copied["uuid_operacion"] = copied.get("id_operacion")

        raw_type = str(copied.get("tipo_operacion") or "").strip().upper()
        raw_payload = copied.get("payload") if isinstance(copied.get("payload"), dict) else copied.get("datos_originales")
        has_payload_dict = isinstance(raw_payload, dict)

        # Inferir tipo TRANSICION_RESERVA si viene de IndexedDB como tipo_operacion='RESERVA' con payload.accion
        if raw_type == "RESERVA" and has_payload_dict and raw_payload.get("accion"):
            raw_type = "TRANSICION_RESERVA"
            copied["tipo_operacion"] = "TRANSICION_RESERVA"

        # Inferir COMPRA vs VENTA si viene con canal DIGITAL
        if raw_type == "VENTA":
            inner_sale = copied.get("venta") or (raw_payload if has_payload_dict else None)
            if isinstance(inner_sale, dict) and str(inner_sale.get("canal") or "").upper() == "DIGITAL":
                raw_type = "COMPRA"
                copied["tipo_operacion"] = "COMPRA"
                if "venta" in copied and "compra" not in copied:
                    copied["compra"] = copied.pop("venta")

        # Resolver uuid_operacion si no vino en la raíz
        if not copied.get("uuid_operacion"):
            if isinstance(copied.get("reserva"), dict) and copied["reserva"].get("uuid_reserva_offline"):
                copied["uuid_operacion"] = copied["reserva"]["uuid_reserva_offline"]
            elif isinstance(copied.get("compra"), dict) and copied["compra"].get("uuid_venta_offline"):
                copied["uuid_operacion"] = copied["compra"]["uuid_venta_offline"]
            elif isinstance(copied.get("venta"), dict) and copied["venta"].get("uuid_venta_offline"):
                copied["uuid_operacion"] = copied["venta"]["uuid_venta_offline"]
            elif isinstance(copied.get("transicion"), dict) and copied["transicion"].get("uuid_operacion_offline"):
                copied["uuid_operacion"] = copied["transicion"]["uuid_operacion_offline"]
            elif has_payload_dict:
                copied["uuid_operacion"] = (
                    raw_payload.get("uuid_operacion_offline")
                    or raw_payload.get("uuid_venta_offline")
                    or raw_payload.get("uuid_reserva_offline")
                    or copied.get("uuid_entidad")
                )

        uuid_op = str(copied.get("uuid_operacion") or "").strip()
        uuid_ent = str(copied.get("uuid_entidad") or uuid_op).strip()
        if not copied.get("uuid_entidad") and uuid_ent:
            copied["uuid_entidad"] = uuid_ent

        # Construir sub-modelos desde payload crudo de IndexedDB si no fueron provistos explícitamente
        if has_payload_dict:
            if not copied.get("codigo_local"):
                copied["codigo_local"] = (
                    raw_payload.get("codigo_local")
                    or raw_payload.get("numero_venta_local")
                    or raw_payload.get("codigo_reserva")
                )
            if not copied.get("depende_de_uuid") and raw_payload.get("depende_de_uuid"):
                copied["depende_de_uuid"] = raw_payload.get("depende_de_uuid")

            if raw_type == "RESERVA" and copied.get("reserva") is None:
                res_dict = dict(raw_payload)
                res_dict.setdefault("uuid_reserva_offline", uuid_ent or uuid_op)
                copied["reserva"] = res_dict

            elif raw_type == "TRANSICION_RESERVA" and copied.get("transicion") is None:
                trans_dict = dict(raw_payload)
                trans_dict.setdefault("uuid_operacion_offline", uuid_op)
                trans_dict.setdefault(
                    "uuid_reserva_offline",
                    raw_payload.get("uuid_reserva_offline") or uuid_ent,
                )
                raw_action = str(trans_dict.get("accion") or "").strip().upper()
                if raw_action in ("CONFIRM", "CONFIRMAR"):
                    trans_dict["accion"] = "CONFIRM"
                elif raw_action in ("ATTEND", "ATENDER"):
                    trans_dict["accion"] = "ATTEND"
                if "fecha_transicion" in trans_dict and "fecha_operacion_offline" not in trans_dict:
                    trans_dict["fecha_operacion_offline"] = trans_dict.get("fecha_transicion")
                copied["transicion"] = trans_dict

            elif raw_type == "COMPRA" and copied.get("compra") is None:
                buy_dict = dict(raw_payload)
                buy_dict.setdefault("uuid_venta_offline", uuid_ent or uuid_op)
                buy_dict["canal"] = "DIGITAL"
                copied["compra"] = buy_dict

            elif raw_type == "VENTA" and copied.get("venta") is None:
                sale_dict = dict(raw_payload)
                sale_dict.setdefault("uuid_venta_offline", uuid_ent or uuid_op)
                sale_dict.setdefault("canal", "PRESENCIAL")
                copied["venta"] = sale_dict

        # Asegurar que compra tenga canal DIGITAL y venta tenga canal PRESENCIAL si vienen como dict
        if isinstance(copied.get("compra"), dict):
            c_dict = dict(copied["compra"])
            c_dict.setdefault("uuid_venta_offline", uuid_ent or uuid_op)
            c_dict["canal"] = "DIGITAL"
            copied["compra"] = c_dict

        if isinstance(copied.get("venta"), dict):
            v_dict = dict(copied["venta"])
            v_dict.setdefault("uuid_venta_offline", uuid_ent or uuid_op)
            v_dict.setdefault("canal", "PRESENCIAL")
            copied["venta"] = v_dict

        if isinstance(copied.get("reserva"), dict):
            r_dict = dict(copied["reserva"])
            r_dict.setdefault("uuid_reserva_offline", uuid_ent or uuid_op)
            copied["reserva"] = r_dict

        if isinstance(copied.get("transicion"), dict):
            t_dict = dict(copied["transicion"])
            t_dict.setdefault("uuid_operacion_offline", uuid_op)
            raw_act = str(t_dict.get("accion") or "").strip().upper()
            if raw_act in ("CONFIRM", "CONFIRMAR"):
                t_dict["accion"] = "CONFIRM"
            elif raw_act in ("ATTEND", "ATENDER"):
                t_dict["accion"] = "ATTEND"
            copied["transicion"] = t_dict

        return copied


class OfflineCodeLinkItem(BaseModel):
    """Vinculación entre UUID/código local provisional y el ID/código oficial asignado en PostgreSQL."""

    model_config = ConfigDict(from_attributes=True)

    referencia_local: str
    tipo_operacion: OfflineSyncOperationType
    id_servidor: int
    codigo_servidor: str


class OfflineSyncOperationResult(BaseModel):
    """Resultado individual por UUID del procesamiento atómico de una operación offline en CU13."""

    model_config = ConfigDict(from_attributes=True)

    uuid_operacion: str
    uuid_entidad: str | None = None
    tipo_operacion: OfflineSyncOperationType
    secuencia: int
    confirmada: bool
    estado_resultado: OfflineSyncResultStatus = Field(
        ...,
        description="Resultado de sincronización: CONFIRMADA, RECHAZADA, EN_CONFLICTO o REINTENTABLE",
    )
    estado_sincronizacion: OfflineSyncServerStatus = Field(
        ...,
        description="Estado equivalente para CU12: SINCRONIZADA, RECHAZADA, CONFLICTO o PENDIENTE_SINCRONIZACION",
    )
    id_servidor: int | None = Field(
        default=None,
        description="ID oficial en PostgreSQL (id_reserva o id_venta)",
    )
    codigo_servidor: str | None = Field(
        default=None,
        description="Código oficial en PostgreSQL (codigo de reserva o numero_venta)",
    )
    codigo_local: str | None = Field(
        default=None,
        description="Código provisional que tenía la operación en IndexedDB",
    )
    estado_entidad_servidor: str | None = Field(
        default=None,
        description="Estado comercial de la reserva o venta en PostgreSQL (PENDIENTE, CONFIRMADA, ATENDIDA, COMPLETADA)",
    )
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
    id_cliente: int | None = None
    id_empleado: int | None = None
    id_usuario: int
    id_empresa: int
    reintentable: bool = Field(
        default=False,
        description="True cuando el fallo es transitorio y el cliente puede reintentar con el mismo UUID",
    )
    conservar_en_cola: bool = Field(
        default=False,
        description="True cuando la operación no fue confirmada y debe conservarse en IndexedDB para CU12/CU14",
    )
    conflictos: list[OfflineConflictDetail] = Field(default_factory=list)
    liberaciones_reserva: list[OfflineSaleReleaseDetail] = Field(default_factory=list)
    motivo: str | None = None
    mensaje: str
    fecha_sincronizacion: datetime
    resumen_cu12: OfflineOperationItemSummary | None = Field(
        default=None,
        description="Resumen canónico compatible con el contrato de consulta CU12",
    )


class OfflineQueueSyncRequest(BaseModel):
    """Solicitud de sincronización en lote de la cola de operaciones offline pendientes (CU13)."""

    model_config = ConfigDict(from_attributes=True)

    operaciones: list[OfflineSyncOperationInput] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Lista ordenada de operaciones locales pendientes a sincronizar",
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_batch_aliases(cls, data: Any) -> Any:
        """Acepta 'operaciones', 'cola' o 'items' como clave del lote."""
        if isinstance(data, dict) and "operaciones" not in data:
            copied = dict(data)
            if "cola" in copied:
                copied["operaciones"] = copied.pop("cola")
            elif "items" in copied:
                copied["operaciones"] = copied.pop("items")
            return copied
        return data


class OfflineQueueSyncResponse(BaseModel):
    """Respuesta consolidada por lote e individual por UUID para PK08 - CU13."""

    model_config = ConfigDict(from_attributes=True)

    success: bool = Field(
        description="True si todas las operaciones del lote fueron confirmadas; False si alguna quedó rechazada, en conflicto o reintentable"
    )
    empresa_id: int
    id_usuario: int
    rol: str
    total_operaciones: int
    confirmadas: int
    rechazadas: int
    en_conflicto: int
    reintentables: int
    resultados: list[OfflineSyncOperationResult]
    resultados_por_uuid: dict[str, OfflineSyncOperationResult] = Field(
        default_factory=dict,
        description="Mapa directo UUID -> Resultado individual para actualización atómica en IndexedDB",
    )
    vinculaciones_codigos: dict[str, OfflineCodeLinkItem] = Field(
        default_factory=dict,
        description="Mapa de UUID/código local provisional -> ID y código oficial de PostgreSQL",
    )
    fecha_sincronizacion: datetime
    mensaje: str
