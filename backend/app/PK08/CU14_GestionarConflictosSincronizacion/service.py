"""Servicio de negocio transaccional para PK08 - CU14: Gestionar conflictos y resultados de sincronización."""

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
import logging
from typing import Any

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.PK07.CU07_ConsultarPlanLimites.service import (
    FeatureNotEnabledError,
    NoActiveSubscriptionError,
    SaasPlanLimitsService,
)
from app.PK08.CU10_RegistrarReservaOffline.schemas import OfflineReservationSyncRequest
from app.PK08.CU10_RegistrarReservaOffline.service import (
    OfflineReservationError,
    OfflineReservationService,
)
from app.PK08.CU11_RegistrarVentaOffline.schemas import (
    OfflineConflictDetail,
    OfflineReservationTransitionRequest,
    OfflineSaleSyncRequest,
)
from app.PK08.CU11_RegistrarVentaOffline.service import (
    OfflineSaleError,
    OfflineSaleService,
)
from app.PK08.CU12_ConsultarOperacionesPendientes.schemas import (
    OfflineOperationItemSummary,
)
from app.PK08.CU13_SincronizarOperacionesPendientes.repository import (
    OfflineSyncQueueRepository,
)
from app.PK08.CU13_SincronizarOperacionesPendientes.schemas import (
    OfflineCodeLinkItem,
    OfflineSyncOperationInput,
    OfflineSyncOperationResult,
    OfflineSyncResultStatus,
    OfflineSyncServerStatus,
)
from app.PK08.CU13_SincronizarOperacionesPendientes.service import (
    ALLOWED_SYNC_ROLES,
    CLIENT_ONLY_TYPES,
    STAFF_ONLY_TYPES,
    OfflineQueueSyncService,
)
from app.PK08.CU14_GestionarConflictosSincronizacion.repository import (
    OfflineConflictRepository,
)
from app.PK08.CU14_GestionarConflictosSincronizacion.schemas import (
    OfflineConflictDiagnoseRequest,
    OfflineConflictDiagnoseResponse,
    OfflineConflictResolveRequest,
    OfflineConflictResolveResponse,
    OfflineOperationConflictDiagnosis,
    OfflineOperationResolutionInput,
    OfflineOperationResolutionResult,
    OfflineResolutionAction,
    OfflineServerCurrentData,
    OfflineServerVariantSnapshot,
)
from app.schemas.auth import AuthenticatedUserData

logger = logging.getLogger(__name__)

ACTIONS_REQUIRING_CONSENT: set[str] = {
    "ACEPTAR_PRECIO_SERVIDOR",
    "AJUSTAR_CANTIDAD_STOCK",
    "QUITAR_PRENDA",
    "REPROGRAMAR_HORARIO",
    "CAMBIAR_SUCURSAL",
    "COMPLETAR_TRANSICIONES_RESERVA",
    "CONFIRMAR_Y_ATENDER_RESERVA",
    "DESCARTAR_OPERACION",
}

CLIENT_ALLOWED_ACTIONS: set[str] = {
    "REINTENTAR_SIN_CAMBIOS",
    "ACEPTAR_PRECIO_SERVIDOR",
    "AJUSTAR_CANTIDAD_STOCK",
    "QUITAR_PRENDA",
    "REPROGRAMAR_HORARIO",
    "CAMBIAR_SUCURSAL",
    "VINCULAR_OPERACION_EXISTENTE",
    "DESCARTAR_OPERACION",
}

STAFF_ALLOWED_ACTIONS: set[str] = {
    "REINTENTAR_SIN_CAMBIOS",
    "ACEPTAR_PRECIO_SERVIDOR",
    "AJUSTAR_CANTIDAD_STOCK",
    "QUITAR_PRENDA",
    "COMPLETAR_TRANSICIONES_RESERVA",
    "CONFIRMAR_Y_ATENDER_RESERVA",
    "VINCULAR_OPERACION_EXISTENTE",
    "DESCARTAR_OPERACION",
}


class OfflineConflictError(Exception):
    """Excepción de nivel de sesión, permisos, tenant o suscripción SaaS en CU14."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class OfflineConflictManagementService:
    """Diagnostica, normaliza y resuelve conflictos de sincronización offline (PK08 - CU14)."""

    def __init__(
        self,
        db: Session,
        *,
        conflict_repository: OfflineConflictRepository | None = None,
        queue_repository: OfflineSyncQueueRepository | None = None,
        reservation_service: OfflineReservationService | None = None,
        sale_service: OfflineSaleService | None = None,
        sync_service: OfflineQueueSyncService | None = None,
        saas_service: SaasPlanLimitsService | None = None,
    ) -> None:
        self.db = db
        self.conflict_repo = conflict_repository or OfflineConflictRepository(db)
        self.queue_repo = queue_repository or OfflineSyncQueueRepository(db)
        self.saas_service = saas_service or SaasPlanLimitsService(db)
        self.reservation_service = reservation_service or OfflineReservationService(
            db, saas_service=self.saas_service
        )
        self.sale_service = sale_service or OfflineSaleService(
            db, saas_service=self.saas_service
        )
        self.sync_service = sync_service or OfflineQueueSyncService(
            db,
            repository=self.queue_repo,
            reservation_service=self.reservation_service,
            sale_service=self.sale_service,
            saas_service=self.saas_service,
        )

    def _validate_session_and_tenant(
        self,
        user: AuthenticatedUserData,
        requested_company_id: int | None = None,
    ) -> tuple[int, str]:
        role = (user.rol or "").strip().upper()
        if role not in ALLOWED_SYNC_ROLES:
            raise OfflineConflictError(
                status_code=403,
                message=(
                    f"El rol '{user.rol}' no está autorizado para gestionar conflictos de operaciones offline. "
                    "Se requiere rol CLIENTE, CAJERO o ENCARGADO_SUCURSAL."
                ),
            )
        if not user.id_empresa:
            raise OfflineConflictError(
                status_code=403,
                message="El usuario autenticado no tiene una empresa asociada en su sesión.",
            )
        if requested_company_id is not None and requested_company_id != user.id_empresa:
            raise OfflineConflictError(
                status_code=403,
                message="Acceso denegado: no puede gestionar conflictos de otra empresa.",
            )
        return user.id_empresa, role

    def _validate_saas_offline(
        self, company_id: int, now: datetime | None = None
    ) -> None:
        try:
            if hasattr(self.saas_service, "validate_feature_enabled"):
                self.saas_service.validate_feature_enabled(
                    company_id, "OFFLINE", now=now
                )
            elif hasattr(self.saas_service, "check_feature_enabled"):
                self.saas_service.check_feature_enabled(company_id, "OFFLINE")
        except (NoActiveSubscriptionError, FeatureNotEnabledError) as err:
            raise OfflineConflictError(status_code=403, message=str(err)) from err
        except Exception as err:
            raise OfflineConflictError(
                status_code=403,
                message=str(err)
                or "La empresa no cuenta con funcionalidad OFFLINE habilitada.",
            ) from err

    @staticmethod
    def _suggest_pickup_slots(
        branch: Any, now: datetime, count: int = 3
    ) -> list[str]:
        """Genera próximos bloques válidos de 30 minutos dentro del horario de apertura/cierre de la sucursal."""
        open_t: time = getattr(branch, "hora_apertura", None) or time(9, 0)
        close_t: time = getattr(branch, "hora_cierre", None) or time(20, 0)
        earliest = now + timedelta(hours=1, minutes=5)
        candidate = earliest.replace(second=0, microsecond=0)
        if candidate.minute in (0, 30):
            pass
        elif candidate.minute < 30:
            candidate = candidate.replace(minute=30)
        else:
            candidate = (candidate + timedelta(hours=1)).replace(minute=0)

        slots: list[str] = []
        max_time = now + timedelta(hours=72)
        while len(slots) < count and candidate <= max_time:
            slot_time = candidate.time()
            if open_t <= slot_time <= close_t:
                slots.append(candidate.isoformat())
            candidate += timedelta(minutes=30)
        return slots

    def _get_inventory_map(
        self, company_id: int, branch_id: int, variant_ids: list[int], is_reserva: bool
    ) -> dict[int, Any]:
        """Obtiene el mapa de inventario sin bloqueo (con fallback al mock de lock_inventories en pruebas unitarias)."""
        try:
            inv_map = self.conflict_repo.get_inventories_snapshot(
                company_id, branch_id, variant_ids
            )
            if isinstance(inv_map, dict) and inv_map:
                return inv_map
        except Exception:
            pass

        repo = (
            self.reservation_service.repository
            if is_reserva
            else self.sale_service.repository
        )
        if hasattr(repo, "lock_inventories"):
            locked = repo.lock_inventories(company_id, branch_id, variant_ids)
            if isinstance(locked, dict):
                return locked
        return {}

    # =========================================================================
    # 1. DIAGNÓSTICO DE CONFLICTOS SIN MUTACIÓN DE INVENTARIO
    # =========================================================================
    def diagnose_conflicts(
        self,
        user: AuthenticatedUserData,
        payload: OfflineConflictDiagnoseRequest,
        *,
        requested_company_id: int | None = None,
        now: datetime | None = None,
    ) -> OfflineConflictDiagnoseResponse:
        """Evalúa el estado real en PostgreSQL para cada operación y devuelve código, motivo, datos actuales y acciones permitidas."""
        company_id, role = self._validate_session_and_tenant(
            user, requested_company_id
        )
        current_time = now or datetime.now(timezone.utc).replace(tzinfo=None)
        self._validate_saas_offline(company_id, now=current_time)

        indexed_ops = list(enumerate(payload.operaciones))
        indexed_ops.sort(
            key=lambda pair: (
                pair[1].secuencia if pair[1].secuencia is not None else pair[0],
                pair[0],
            )
        )

        diagnoses: list[OfflineOperationConflictDiagnosis] = []
        by_uuid: dict[str, OfflineOperationConflictDiagnosis] = {}
        failed_in_batch: dict[str, tuple[OfflineSyncResultStatus, str]] = {}

        for idx, (_, op) in enumerate(indexed_ops, start=1):
            seq_num = op.secuencia if op.secuencia is not None else idx
            diag = self._diagnose_single_operation(
                user=user,
                role=role,
                company_id=company_id,
                op=op,
                seq_num=seq_num,
                current_time=current_time,
                failed_in_batch=failed_in_batch,
            )
            diagnoses.append(diag)
            by_uuid[diag.uuid_operacion] = diag

            if not diag.confirmada_en_servidor and diag.estado_resultado in (
                "EN_CONFLICTO",
                "RECHAZADA",
            ):
                reason_str = diag.motivo or diag.mensaje
                keys_to_mark: set[str | None] = {
                    op.uuid_operacion,
                    op.uuid_entidad,
                    op.codigo_local,
                }
                if op.transicion is not None:
                    keys_to_mark.add(op.transicion.uuid_reserva_offline)
                    keys_to_mark.add(op.transicion.codigo_reserva)
                    if op.transicion.id_reserva is not None:
                        keys_to_mark.add(f"res-id:{op.transicion.id_reserva}")
                if op.reserva is not None:
                    keys_to_mark.add(op.reserva.uuid_reserva_offline)
                for k in keys_to_mark:
                    if k:
                        failed_in_batch[k] = (diag.estado_resultado, reason_str)

        already_synced = sum(1 for d in diagnoses if d.confirmada_en_servidor)
        in_conflict = sum(
            1
            for d in diagnoses
            if not d.confirmada_en_servidor and d.estado_resultado == "EN_CONFLICTO"
        )
        rejected = sum(
            1
            for d in diagnoses
            if not d.confirmada_en_servidor and d.estado_resultado == "RECHAZADA"
        )
        ready = sum(
            1
            for d in diagnoses
            if not d.confirmada_en_servidor and d.estado_resultado == "REINTENTABLE"
        )

        return OfflineConflictDiagnoseResponse(
            success=True,
            empresa_id=company_id,
            id_usuario=user.id_usuario,
            rol=role,
            total_diagnosticadas=len(diagnoses),
            ya_sincronizadas=already_synced,
            en_conflicto=in_conflict,
            rechazadas=rejected,
            listas_para_sincronizar=ready,
            diagnosticos=diagnoses,
            diagnosticos_por_uuid=by_uuid,
            fecha_diagnostico=current_time,
            mensaje=(
                f"Diagnóstico completado: {in_conflict} en conflicto, {rejected} rechazadas, "
                f"{already_synced} ya sincronizadas, {ready} listas para sincronizar."
            ),
        )

    def _diagnose_single_operation(
        self,
        *,
        user: AuthenticatedUserData,
        role: str,
        company_id: int,
        op: OfflineSyncOperationInput,
        seq_num: int,
        current_time: datetime,
        failed_in_batch: dict[str, tuple[OfflineSyncResultStatus, str]],
    ) -> OfflineOperationConflictDiagnosis:
        op_type = op.tipo_operacion
        branch_id = 1
        if op.reserva and op.reserva.id_sucursal:
            branch_id = op.reserva.id_sucursal
        elif op.compra and op.compra.id_sucursal:
            branch_id = op.compra.id_sucursal
        elif op.venta and op.venta.id_sucursal:
            branch_id = op.venta.id_sucursal
        elif op.transicion and op.transicion.id_sucursal:
            branch_id = op.transicion.id_sucursal

        server_data = OfflineServerCurrentData(
            id_sucursal=branch_id,
            sucursal_nombre=self.queue_repo.get_branch_name(company_id, branch_id),
        )

        # 1. Validar rol frente a tipo de operación
        if op_type in CLIENT_ONLY_TYPES and role != "CLIENTE":
            reason = f"El rol '{role}' no tiene autorización para operar sobre '{op_type}'."
            return OfflineOperationConflictDiagnosis(
                uuid_operacion=op.uuid_operacion,
                uuid_entidad=op.uuid_entidad,
                tipo_operacion=op_type,
                secuencia=seq_num,
                depende_de_uuid=op.depende_de_uuid,
                codigo_local=op.codigo_local,
                estado_resultado="RECHAZADA",
                estado_sincronizacion="RECHAZADA",
                codigo_conflicto_principal="REGLA_NEGOCIO",
                motivo=reason,
                corregible=False,
                requiere_consentimiento=False,
                conflictos=[
                    OfflineConflictDetail(
                        tipo_conflicto="REGLA_NEGOCIO",
                        corregible=False,
                        requiere_consentimiento=False,
                        acciones_permitidas=["DESCARTAR_OPERACION"],
                        detalle=reason,
                    )
                ],
                datos_actuales_servidor=server_data,
                acciones_permitidas=["DESCARTAR_OPERACION"],
                mensaje=reason,
            )

        if op_type in STAFF_ONLY_TYPES and role not in ("CAJERO", "ENCARGADO_SUCURSAL"):
            reason = f"El rol '{role}' no tiene autorización para operar sobre '{op_type}'."
            return OfflineOperationConflictDiagnosis(
                uuid_operacion=op.uuid_operacion,
                uuid_entidad=op.uuid_entidad,
                tipo_operacion=op_type,
                secuencia=seq_num,
                depende_de_uuid=op.depende_de_uuid,
                codigo_local=op.codigo_local,
                estado_resultado="RECHAZADA",
                estado_sincronizacion="RECHAZADA",
                codigo_conflicto_principal="REGLA_NEGOCIO",
                motivo=reason,
                corregible=False,
                requiere_consentimiento=False,
                conflictos=[
                    OfflineConflictDetail(
                        tipo_conflicto="REGLA_NEGOCIO",
                        corregible=False,
                        requiere_consentimiento=False,
                        acciones_permitidas=["DESCARTAR_OPERACION"],
                        detalle=reason,
                    )
                ],
                datos_actuales_servidor=server_data,
                acciones_permitidas=["DESCARTAR_OPERACION"],
                mensaje=reason,
            )

        # 2. Verificar bloqueo por operación dependiente fallida en el lote
        dep_candidates: list[str | None] = [op.depende_de_uuid]
        if op.transicion is not None:
            dep_candidates.extend(
                [
                    op.transicion.uuid_reserva_offline,
                    op.transicion.codigo_reserva,
                    f"res-id:{op.transicion.id_reserva}"
                    if op.transicion.id_reserva is not None
                    else None,
                ]
            )
        if op.venta is not None:
            dep_candidates.extend(
                [
                    op.venta.uuid_reserva_offline,
                    op.venta.codigo_reserva,
                    f"res-id:{op.venta.id_reserva}"
                    if op.venta.id_reserva is not None
                    else None,
                ]
            )

        for dep_key in dep_candidates:
            if dep_key and dep_key in failed_in_batch:
                p_status, p_reason = failed_in_batch[dep_key]
                reason = (
                    f"Operación bloqueada: la operación previa dependiente ('{dep_key}') "
                    f"se encuentra en estado {p_status} ({p_reason})."
                )
                return OfflineOperationConflictDiagnosis(
                    uuid_operacion=op.uuid_operacion,
                    uuid_entidad=op.uuid_entidad,
                    tipo_operacion=op_type,
                    secuencia=seq_num,
                    depende_de_uuid=op.depende_de_uuid or dep_key,
                    codigo_local=op.codigo_local,
                    estado_resultado="EN_CONFLICTO",
                    estado_sincronizacion="CONFLICTO",
                    codigo_conflicto_principal="DEPENDENCIA_BLOQUEADA",
                    motivo=reason,
                    corregible=True,
                    requiere_consentimiento=False,
                    bloqueada_por_dependencia=True,
                    conflictos=[
                        OfflineConflictDetail(
                            tipo_conflicto="DEPENDENCIA_BLOQUEADA",
                            valor_esperado="CONFIRMADA",
                            valor_actual_servidor=p_status,
                            corregible=True,
                            requiere_consentimiento=False,
                            datos_servidor={"dependencia_uuid": dep_key, "estado_dependencia": p_status},
                            acciones_permitidas=["DESCARTAR_OPERACION"],
                            detalle=reason,
                        )
                    ],
                    datos_actuales_servidor=server_data,
                    acciones_permitidas=["DESCARTAR_OPERACION"],
                    mensaje=reason,
                )

        if op_type == "RESERVA" and op.reserva is not None:
            return self._diagnose_reservation(
                user=user,
                company_id=company_id,
                op=op,
                res_req=op.reserva,
                seq_num=seq_num,
                current_time=current_time,
                server_data=server_data,
            )

        if op_type == "TRANSICION_RESERVA" and op.transicion is not None:
            return self._diagnose_transition(
                user=user,
                company_id=company_id,
                op=op,
                trans_req=op.transicion,
                seq_num=seq_num,
                current_time=current_time,
                server_data=server_data,
            )

        if op_type in ("COMPRA", "VENTA"):
            sale_req = op.compra if op_type == "COMPRA" else (op.venta or op.compra)
            if sale_req is not None:
                return self._diagnose_sale_or_purchase(
                    user=user,
                    role=role,
                    company_id=company_id,
                    op=op,
                    sale_req=sale_req,
                    seq_num=seq_num,
                    current_time=current_time,
                    server_data=server_data,
                )

        reason = f"Datos insuficientes para diagnosticar operación {op_type}."
        return OfflineOperationConflictDiagnosis(
            uuid_operacion=op.uuid_operacion,
            uuid_entidad=op.uuid_entidad,
            tipo_operacion=op_type,
            secuencia=seq_num,
            codigo_local=op.codigo_local,
            estado_resultado="RECHAZADA",
            estado_sincronizacion="RECHAZADA",
            codigo_conflicto_principal="REGLA_NEGOCIO",
            motivo=reason,
            corregible=False,
            conflictos=[
                OfflineConflictDetail(
                    tipo_conflicto="REGLA_NEGOCIO",
                    corregible=False,
                    requiere_consentimiento=False,
                    acciones_permitidas=["DESCARTAR_OPERACION"],
                    detalle=reason,
                )
            ],
            datos_actuales_servidor=server_data,
            acciones_permitidas=["DESCARTAR_OPERACION"],
            mensaje=reason,
        )

    def _diagnose_reservation(
        self,
        *,
        user: AuthenticatedUserData,
        company_id: int,
        op: OfflineSyncOperationInput,
        res_req: OfflineReservationSyncRequest,
        seq_num: int,
        current_time: datetime,
        server_data: OfflineServerCurrentData,
    ) -> OfflineOperationConflictDiagnosis:
        res_repo = self.reservation_service.repository
        client = self.reservation_service._resolve_authenticated_client(
            company_id, user, res_req
        )

        # 1. Verificar si ya fue sincronizada previamente en PostgreSQL
        existing_sync = res_repo.get_sync_record(company_id, res_req.uuid_reserva_offline)
        if existing_sync is not None:
            if existing_sync.id_cliente != client.id_cliente:
                raise OfflineConflictError(
                    status_code=403,
                    message="Acceso denegado: el UUID de reserva offline pertenece a otro cliente.",
                )
            if (
                existing_sync.estado_sincronizacion == "SINCRONIZADA"
                and existing_sync.id_reserva is not None
            ):
                server_data.id_reserva_servidor = existing_sync.id_reserva
                server_data.codigo_reserva_servidor = existing_sync.codigo_reserva
                server_data.estado_reserva_servidor = "PENDIENTE"
                return OfflineOperationConflictDiagnosis(
                    uuid_operacion=op.uuid_operacion,
                    uuid_entidad=res_req.uuid_reserva_offline,
                    tipo_operacion="RESERVA",
                    secuencia=seq_num,
                    codigo_local=op.codigo_local,
                    confirmada_en_servidor=True,
                    id_servidor=existing_sync.id_reserva,
                    codigo_servidor=existing_sync.codigo_reserva,
                    estado_resultado="CONFIRMADA",
                    estado_sincronizacion="SINCRONIZADA",
                    codigo_conflicto_principal="OPERACION_DUPLICADA",
                    motivo="La reserva ya se encuentra registrada y confirmada en PostgreSQL.",
                    corregible=False,
                    requiere_consentimiento=False,
                    conflictos=[
                        OfflineConflictDetail(
                            tipo_conflicto="OPERACION_DUPLICADA",
                            valor_actual_servidor=existing_sync.codigo_reserva,
                            corregible=False,
                            requiere_consentimiento=False,
                            datos_servidor={
                                "id_reserva": existing_sync.id_reserva,
                                "codigo_reserva": existing_sync.codigo_reserva,
                            },
                            acciones_permitidas=["VINCULAR_OPERACION_EXISTENTE"],
                            detalle=f"Reserva previamente confirmada con código oficial {existing_sync.codigo_reserva}.",
                        )
                    ],
                    datos_actuales_servidor=server_data,
                    acciones_permitidas=["VINCULAR_OPERACION_EXISTENTE"],
                    mensaje="Reserva ya sincronizada en el servidor central.",
                )

        # 2. Validar sucursal y horario
        branch = res_repo.get_branch(company_id, res_req.id_sucursal)
        if not branch or not getattr(branch, "estado", False) or getattr(branch, "empresa_id", company_id) != company_id:
            server_data.sucursal_activa = False
            reason = "La sucursal seleccionada no existe o se encuentra inactiva."
            return OfflineOperationConflictDiagnosis(
                uuid_operacion=op.uuid_operacion,
                uuid_entidad=res_req.uuid_reserva_offline,
                tipo_operacion="RESERVA",
                secuencia=seq_num,
                codigo_local=op.codigo_local,
                estado_resultado="EN_CONFLICTO",
                estado_sincronizacion="CONFLICTO",
                codigo_conflicto_principal="REGLA_NEGOCIO",
                motivo=reason,
                corregible=True,
                requiere_consentimiento=True,
                conflictos=[
                    OfflineConflictDetail(
                        tipo_conflicto="REGLA_NEGOCIO",
                        corregible=True,
                        requiere_consentimiento=True,
                        acciones_permitidas=["CAMBIAR_SUCURSAL", "DESCARTAR_OPERACION"],
                        detalle=reason,
                    )
                ],
                datos_actuales_servidor=server_data,
                acciones_permitidas=["CAMBIAR_SUCURSAL", "DESCARTAR_OPERACION"],
                mensaje=reason,
            )

        open_t = getattr(branch, "hora_apertura", None)
        close_t = getattr(branch, "hora_cierre", None)
        server_data.hora_apertura_sucursal = str(open_t) if open_t else "09:00:00"
        server_data.hora_cierre_sucursal = str(close_t) if close_t else "20:00:00"
        server_data.horarios_sugeridos = self._suggest_pickup_slots(branch, current_time)

        conflicts: list[OfflineConflictDetail] = []
        allowed_actions: list[OfflineResolutionAction] = []

        scheduled_at, schedule_error = (
            self.reservation_service._validate_and_normalize_schedule(
                branch, res_req.fecha_atencion_programada, current_time
            )
        )
        if schedule_error or scheduled_at is None:
            conflicts.append(
                OfflineConflictDetail(
                    tipo_conflicto="HORARIO_VENCIDO",
                    valor_esperado=res_req.fecha_atencion_programada.isoformat(),
                    valor_actual_servidor=current_time.isoformat(),
                    corregible=True,
                    requiere_consentimiento=True,
                    datos_servidor={
                        "hora_apertura": server_data.hora_apertura_sucursal,
                        "hora_cierre": server_data.hora_cierre_sucursal,
                        "horarios_sugeridos": server_data.horarios_sugeridos,
                    },
                    acciones_permitidas=["REPROGRAMAR_HORARIO", "DESCARTAR_OPERACION"],
                    detalle=schedule_error or "El horario programado venció o es inválido.",
                )
            )
            allowed_actions.extend(["REPROGRAMAR_HORARIO", "DESCARTAR_OPERACION"])

        req_variant_ids = [d.id_variante_producto for d in res_req.detalles]
        variants_dict = res_repo.get_variants_with_products(company_id, req_variant_ids)
        inv_map = self._get_inventory_map(
            company_id, res_req.id_sucursal, req_variant_ids, is_reserva=True
        )

        if scheduled_at is not None and res_repo.has_active_slot_conflict(
            company_id=company_id,
            branch_id=res_req.id_sucursal,
            scheduled_at=scheduled_at,
            variant_ids=req_variant_ids,
            now=current_time,
        ) is True:
            conflicts.append(
                OfflineConflictDetail(
                    tipo_conflicto="HORARIO_NO_DISPONIBLE",
                    valor_esperado=scheduled_at.isoformat(),
                    valor_actual_servidor="OCUPADO",
                    corregible=True,
                    requiere_consentimiento=True,
                    datos_servidor={"horarios_sugeridos": server_data.horarios_sugeridos},
                    acciones_permitidas=["REPROGRAMAR_HORARIO", "DESCARTAR_OPERACION"],
                    detalle="Una de las prendas ya tiene una reserva activa en la sucursal y horario seleccionados.",
                )
            )
            if "REPROGRAMAR_HORARIO" not in allowed_actions:
                allowed_actions.append("REPROGRAMAR_HORARIO")

        total_server = Decimal("0.00")
        for detail in res_req.detalles:
            v_id = detail.id_variante_producto
            if v_id not in variants_dict:
                conflicts.append(
                    OfflineConflictDetail(
                        tipo_conflicto="REGLA_NEGOCIO",
                        id_variante_producto=v_id,
                        corregible=len(res_req.detalles) > 1,
                        requiere_consentimiento=True,
                        acciones_permitidas=(
                            ["QUITAR_PRENDA", "DESCARTAR_OPERACION"]
                            if len(res_req.detalles) > 1
                            else ["DESCARTAR_OPERACION"]
                        ),
                        detalle=f"La variante #{v_id} no existe o no pertenece a la empresa.",
                    )
                )
                continue

            variant_obj, product_obj = variants_dict[v_id]
            sku_str = getattr(variant_obj, "sku", str(v_id))
            auth_price = Decimal(
                str(
                    getattr(product_obj, "precio_final", None)
                    or getattr(product_obj, "precio", Decimal("0.00"))
                )
            ).quantize(Decimal("0.01"))
            inv_obj = inv_map.get(v_id)
            s_actual = int(getattr(inv_obj, "stock_actual", 0)) if inv_obj else 0
            s_res = int(getattr(inv_obj, "stock_reservado", 0)) if inv_obj else 0
            s_disp = max(0, s_actual - s_res)

            server_data.variantes.append(
                OfflineServerVariantSnapshot(
                    id_variante_producto=v_id,
                    id_producto=getattr(product_obj, "id_producto", None),
                    sku=sku_str,
                    nombre_producto=getattr(product_obj, "nombre", None),
                    activa=bool(
                        getattr(variant_obj, "estado", True)
                        and getattr(product_obj, "estado", True)
                    ),
                    stock_actual=s_actual,
                    stock_reservado=s_res,
                    stock_disponible=s_disp,
                    precio_base_servidor=auth_price,
                    descuento_unitario_servidor=Decimal("0.00"),
                    precio_neto_servidor=auth_price,
                    cantidad_solicitada=detail.cantidad,
                    precio_capturado_offline=detail.precio_referencial,
                )
            )
            total_server += auth_price * detail.cantidad

            if s_disp < detail.cantidad:
                item_actions: list[OfflineResolutionAction] = []
                if s_disp > 0:
                    item_actions.append("AJUSTAR_CANTIDAD_STOCK")
                if len(res_req.detalles) > 1:
                    item_actions.append("QUITAR_PRENDA")
                item_actions.extend(["CAMBIAR_SUCURSAL", "DESCARTAR_OPERACION"])
                for act in item_actions:
                    if act not in allowed_actions:
                        allowed_actions.append(act)

                conflicts.append(
                    OfflineConflictDetail(
                        tipo_conflicto="STOCK_INSUFICIENTE",
                        id_variante_producto=v_id,
                        sku=sku_str,
                        valor_esperado=detail.cantidad,
                        valor_actual_servidor=s_disp,
                        corregible=True,
                        requiere_consentimiento=True,
                        datos_servidor={
                            "id_variante_producto": v_id,
                            "sku": sku_str,
                            "stock_actual": s_actual,
                            "stock_reservado": s_res,
                            "stock_disponible": s_disp,
                            "cantidad_solicitada": detail.cantidad,
                        },
                        acciones_permitidas=item_actions,
                        detalle=(
                            f"Stock disponible insuficiente para '{sku_str}'. "
                            f"Disponible: {s_disp}, Solicitado: {detail.cantidad}."
                        ),
                    )
                )

            if (
                detail.precio_referencial is not None
                and Decimal(str(detail.precio_referencial)).quantize(Decimal("0.01"))
                != auth_price
            ):
                if "ACEPTAR_PRECIO_SERVIDOR" not in allowed_actions:
                    allowed_actions.append("ACEPTAR_PRECIO_SERVIDOR")
                conflicts.append(
                    OfflineConflictDetail(
                        tipo_conflicto="PRECIO_MODIFICADO",
                        id_variante_producto=v_id,
                        sku=sku_str,
                        valor_esperado=Decimal(str(detail.precio_referencial)).quantize(
                            Decimal("0.01")
                        ),
                        valor_actual_servidor=auth_price,
                        corregible=True,
                        requiere_consentimiento=True,
                        datos_servidor={
                            "id_variante_producto": v_id,
                            "sku": sku_str,
                            "precio_neto_servidor": str(auth_price),
                            "precio_capturado_offline": str(detail.precio_referencial),
                        },
                        acciones_permitidas=[
                            "ACEPTAR_PRECIO_SERVIDOR",
                            "DESCARTAR_OPERACION",
                        ],
                        detalle=(
                            f"El precio referencial de '{sku_str}' cambió en el servidor "
                            f"(offline: Bs {detail.precio_referencial}, actual: Bs {auth_price})."
                        ),
                    )
                )

        server_data.subtotal_servidor = total_server
        server_data.descuento_total_servidor = Decimal("0.00")
        server_data.total_servidor = total_server

        if "DESCARTAR_OPERACION" not in allowed_actions:
            allowed_actions.append("DESCARTAR_OPERACION")

        if conflicts:
            primary = conflicts[0]
            return OfflineOperationConflictDiagnosis(
                uuid_operacion=op.uuid_operacion,
                uuid_entidad=res_req.uuid_reserva_offline,
                tipo_operacion="RESERVA",
                secuencia=seq_num,
                codigo_local=op.codigo_local,
                estado_resultado="EN_CONFLICTO",
                estado_sincronizacion="CONFLICTO",
                codigo_conflicto_principal=primary.tipo_conflicto,
                motivo=primary.detalle,
                corregible=any(c.corregible for c in conflicts),
                requiere_consentimiento=True,
                conflictos=conflicts,
                datos_actuales_servidor=server_data,
                acciones_permitidas=allowed_actions,
                mensaje=f"Se detectaron {len(conflicts)} conflicto(s) en la reserva offline.",
            )

        return OfflineOperationConflictDiagnosis(
            uuid_operacion=op.uuid_operacion,
            uuid_entidad=res_req.uuid_reserva_offline,
            tipo_operacion="RESERVA",
            secuencia=seq_num,
            codigo_local=op.codigo_local,
            estado_resultado="REINTENTABLE",
            estado_sincronizacion="PENDIENTE_SINCRONIZACION",
            motivo=None,
            corregible=True,
            requiere_consentimiento=False,
            conflictos=[],
            datos_actuales_servidor=server_data,
            acciones_permitidas=["REINTENTAR_SIN_CAMBIOS", "DESCARTAR_OPERACION"],
            mensaje="La reserva offline cumple todas las validaciones y está lista para sincronizarse.",
        )

    def _diagnose_transition(
        self,
        *,
        user: AuthenticatedUserData,
        company_id: int,
        op: OfflineSyncOperationInput,
        trans_req: OfflineReservationTransitionRequest,
        seq_num: int,
        current_time: datetime,
        server_data: OfflineServerCurrentData,
    ) -> OfflineOperationConflictDiagnosis:
        sale_repo = self.sale_service.repository
        resolved_id, resolved_code = self.sync_service._resolve_linked_reservation(
            company_id=company_id,
            uuid_offline=trans_req.uuid_reserva_offline or op.uuid_entidad,
            code=trans_req.codigo_reserva or op.codigo_local,
            reservation_id=trans_req.id_reserva,
            reservation_links={},
        )
        reservation = sale_repo.get_reservation(
            company_id,
            reservation_id=resolved_id,
            code=resolved_code or trans_req.codigo_reserva,
            uuid_offline=trans_req.uuid_reserva_offline,
            for_update=False,
        )
        action = (
            "CONFIRM"
            if trans_req.accion in ("CONFIRM", "CONFIRMAR")
            else "ATTEND"
        )

        if reservation is None:
            reason = "La reserva asociada a la transición no existe o aún no fue sincronizada en PostgreSQL."
            return OfflineOperationConflictDiagnosis(
                uuid_operacion=op.uuid_operacion,
                uuid_entidad=op.uuid_entidad,
                tipo_operacion="TRANSICION_RESERVA",
                secuencia=seq_num,
                codigo_local=op.codigo_local,
                estado_resultado="EN_CONFLICTO",
                estado_sincronizacion="CONFLICTO",
                codigo_conflicto_principal="RESERVA_ESTADO_INVALIDO",
                motivo=reason,
                corregible=False,
                requiere_consentimiento=True,
                conflictos=[
                    OfflineConflictDetail(
                        tipo_conflicto="RESERVA_ESTADO_INVALIDO",
                        valor_esperado="PENDIENTE" if action == "CONFIRM" else "CONFIRMADA",
                        valor_actual_servidor="NO_ENCONTRADA",
                        corregible=False,
                        requiere_consentimiento=True,
                        acciones_permitidas=["DESCARTAR_OPERACION"],
                        detalle=reason,
                    )
                ],
                datos_actuales_servidor=server_data,
                acciones_permitidas=["DESCARTAR_OPERACION"],
                mensaje=reason,
            )

        res_state = getattr(reservation, "estado", "PENDIENTE")
        exp_dt = getattr(reservation, "fecha_expiracion", None)
        if res_state in ("PENDIENTE", "CONFIRMADA") and exp_dt is not None and exp_dt <= current_time:
            res_state = "EXPIRADA"

        server_data.id_reserva_servidor = reservation.id_reserva
        server_data.codigo_reserva_servidor = reservation.codigo
        server_data.estado_reserva_servidor = res_state
        server_data.fecha_expiracion_reserva = exp_dt

        # Si ya alcanzó el estado objetivo, es idempotente
        if (action == "CONFIRM" and res_state in ("CONFIRMADA", "ATENDIDA")) or (
            action == "ATTEND" and res_state == "ATENDIDA"
        ):
            return OfflineOperationConflictDiagnosis(
                uuid_operacion=op.uuid_operacion,
                uuid_entidad=op.uuid_entidad,
                tipo_operacion="TRANSICION_RESERVA",
                secuencia=seq_num,
                codigo_local=op.codigo_local,
                confirmada_en_servidor=True,
                id_servidor=reservation.id_reserva,
                codigo_servidor=reservation.codigo,
                estado_resultado="CONFIRMADA",
                estado_sincronizacion="SINCRONIZADA",
                motivo=None,
                corregible=False,
                requiere_consentimiento=False,
                datos_actuales_servidor=server_data,
                acciones_permitidas=["VINCULAR_OPERACION_EXISTENTE"],
                mensaje=f"La reserva {reservation.codigo} ya se encuentra en estado {res_state}.",
            )

        # Si está en el estado previo exacto requerido, está lista para sincronizarse
        if (action == "CONFIRM" and res_state == "PENDIENTE") or (
            action == "ATTEND" and res_state == "CONFIRMADA"
        ):
            return OfflineOperationConflictDiagnosis(
                uuid_operacion=op.uuid_operacion,
                uuid_entidad=op.uuid_entidad,
                tipo_operacion="TRANSICION_RESERVA",
                secuencia=seq_num,
                codigo_local=op.codigo_local,
                estado_resultado="REINTENTABLE",
                estado_sincronizacion="PENDIENTE_SINCRONIZACION",
                motivo=None,
                corregible=True,
                requiere_consentimiento=False,
                datos_actuales_servidor=server_data,
                acciones_permitidas=["REINTENTAR_SIN_CAMBIOS", "DESCARTAR_OPERACION"],
                mensaje=f"La transición {action} sobre la reserva {reservation.codigo} está lista para aplicarse.",
            )

        # Si se intenta ATTEND sobre PENDIENTE, el cajero puede autorizar CONFIRMAR_Y_ATENDER_RESERVA
        if action == "ATTEND" and res_state == "PENDIENTE":
            reason = (
                f"La reserva '{reservation.codigo}' aún está en estado PENDIENTE; "
                "se requiere confirmarla antes de marcarla como ATENDIDA."
            )
            return OfflineOperationConflictDiagnosis(
                uuid_operacion=op.uuid_operacion,
                uuid_entidad=op.uuid_entidad,
                tipo_operacion="TRANSICION_RESERVA",
                secuencia=seq_num,
                codigo_local=op.codigo_local,
                estado_resultado="EN_CONFLICTO",
                estado_sincronizacion="CONFLICTO",
                codigo_conflicto_principal="RESERVA_ESTADO_INVALIDO",
                motivo=reason,
                corregible=True,
                requiere_consentimiento=True,
                conflictos=[
                    OfflineConflictDetail(
                        tipo_conflicto="RESERVA_ESTADO_INVALIDO",
                        valor_esperado="CONFIRMADA",
                        valor_actual_servidor="PENDIENTE",
                        corregible=True,
                        requiere_consentimiento=True,
                        datos_servidor={
                            "id_reserva": reservation.id_reserva,
                            "codigo_reserva": reservation.codigo,
                            "estado_reserva": "PENDIENTE",
                        },
                        acciones_permitidas=[
                            "CONFIRMAR_Y_ATENDER_RESERVA",
                            "DESCARTAR_OPERACION",
                        ],
                        detalle=reason,
                    )
                ],
                datos_actuales_servidor=server_data,
                acciones_permitidas=[
                    "CONFIRMAR_Y_ATENDER_RESERVA",
                    "DESCARTAR_OPERACION",
                ],
                mensaje=reason,
            )

        # Reserva CANCELADA o EXPIRADA -> no corregible
        reason = f"La reserva '{reservation.codigo}' se encuentra en estado {res_state} y no admite transiciones."
        return OfflineOperationConflictDiagnosis(
            uuid_operacion=op.uuid_operacion,
            uuid_entidad=op.uuid_entidad,
            tipo_operacion="TRANSICION_RESERVA",
            secuencia=seq_num,
            codigo_local=op.codigo_local,
            estado_resultado="EN_CONFLICTO",
            estado_sincronizacion="CONFLICTO",
            codigo_conflicto_principal="RESERVA_CANCELADA",
            motivo=reason,
            corregible=False,
            requiere_consentimiento=True,
            conflictos=[
                OfflineConflictDetail(
                    tipo_conflicto="RESERVA_CANCELADA",
                    valor_esperado="PENDIENTE" if action == "CONFIRM" else "CONFIRMADA",
                    valor_actual_servidor=res_state,
                    corregible=False,
                    requiere_consentimiento=True,
                    datos_servidor={
                        "id_reserva": reservation.id_reserva,
                        "codigo_reserva": reservation.codigo,
                        "estado_reserva": res_state,
                    },
                    acciones_permitidas=["DESCARTAR_OPERACION"],
                    detalle=reason,
                )
            ],
            datos_actuales_servidor=server_data,
            acciones_permitidas=["DESCARTAR_OPERACION"],
            mensaje=reason,
        )

    def _diagnose_sale_or_purchase(
        self,
        *,
        user: AuthenticatedUserData,
        role: str,
        company_id: int,
        op: OfflineSyncOperationInput,
        sale_req: OfflineSaleSyncRequest,
        seq_num: int,
        current_time: datetime,
        server_data: OfflineServerCurrentData,
    ) -> OfflineOperationConflictDiagnosis:
        sale_repo = self.sale_service.repository
        canal = "DIGITAL" if op.tipo_operacion == "COMPRA" else "PRESENCIAL"

        # 1. Verificar idempotencia por UUID
        uuid_obj = self.sale_service._normalize_uuid(
            company_id, sale_req.uuid_venta_offline
        )
        sale_num = self.sale_service._sale_number(canal, user.id_usuario, uuid_obj)
        existing_sale = sale_repo.get_sale_by_number(company_id, sale_num)
        if existing_sale is None:
            pay_by_key = sale_repo.get_payment_by_key(company_id, uuid_obj)
            if pay_by_key is not None:
                existing_sale = sale_repo.get_sale_by_id(company_id, pay_by_key.id_venta)

        if existing_sale is not None:
            server_data.id_venta_existente = existing_sale.id_venta
            server_data.numero_venta_existente = existing_sale.numero_venta
            server_data.estado_venta_existente = getattr(existing_sale, "estado", None)
            return OfflineOperationConflictDiagnosis(
                uuid_operacion=op.uuid_operacion,
                uuid_entidad=sale_req.uuid_venta_offline,
                tipo_operacion=op.tipo_operacion,
                secuencia=seq_num,
                codigo_local=op.codigo_local,
                confirmada_en_servidor=True,
                id_servidor=existing_sale.id_venta,
                codigo_servidor=existing_sale.numero_venta,
                estado_resultado="CONFIRMADA",
                estado_sincronizacion="SINCRONIZADA",
                codigo_conflicto_principal="OPERACION_DUPLICADA",
                motivo=f"La operación ya fue registrada con código {existing_sale.numero_venta}.",
                corregible=False,
                requiere_consentimiento=False,
                conflictos=[
                    OfflineConflictDetail(
                        tipo_conflicto="OPERACION_DUPLICADA",
                        valor_actual_servidor=existing_sale.numero_venta,
                        corregible=False,
                        requiere_consentimiento=False,
                        datos_servidor={
                            "id_venta": existing_sale.id_venta,
                            "numero_venta": existing_sale.numero_venta,
                        },
                        acciones_permitidas=["VINCULAR_OPERACION_EXISTENTE"],
                        detalle=f"Operación ya registrada en servidor ({existing_sale.numero_venta}).",
                    )
                ],
                datos_actuales_servidor=server_data,
                acciones_permitidas=["VINCULAR_OPERACION_EXISTENTE"],
                mensaje="Operación previamente sincronizada en el servidor central.",
            )

        conflicts: list[OfflineConflictDetail] = []
        allowed_actions: list[OfflineResolutionAction] = []

        # 2. Si es venta por reserva, verificar estado de la reserva
        has_res_ref = bool(
            sale_req.id_reserva is not None
            or sale_req.codigo_reserva
            or sale_req.uuid_reserva_offline
        )
        reservation = None
        if has_res_ref:
            resolved_id, resolved_code = self.sync_service._resolve_linked_reservation(
                company_id=company_id,
                uuid_offline=sale_req.uuid_reserva_offline,
                code=sale_req.codigo_reserva,
                reservation_id=sale_req.id_reserva,
                reservation_links={},
            )
            reservation = sale_repo.get_reservation(
                company_id,
                reservation_id=resolved_id,
                code=resolved_code or sale_req.codigo_reserva,
                uuid_offline=sale_req.uuid_reserva_offline,
                for_update=False,
            )
            if reservation is None:
                conflicts.append(
                    OfflineConflictDetail(
                        tipo_conflicto="RESERVA_ESTADO_INVALIDO",
                        valor_esperado="ATENDIDA",
                        valor_actual_servidor="NO_ENCONTRADA",
                        corregible=False,
                        requiere_consentimiento=True,
                        acciones_permitidas=["DESCARTAR_OPERACION"],
                        detalle="La reserva asociada a la venta no existe en el servidor.",
                    )
                )
            else:
                res_state = getattr(reservation, "estado", "PENDIENTE")
                exp_dt = getattr(reservation, "fecha_expiracion", None)
                if (
                    res_state in ("PENDIENTE", "CONFIRMADA")
                    and exp_dt is not None
                    and exp_dt <= current_time
                ):
                    res_state = "EXPIRADA"

                server_data.id_reserva_servidor = reservation.id_reserva
                server_data.codigo_reserva_servidor = reservation.codigo
                server_data.estado_reserva_servidor = res_state
                server_data.fecha_expiracion_reserva = exp_dt

                existing_res_sale = sale_repo.get_sale_for_reservation(
                    company_id, reservation.id_reserva
                )
                if existing_res_sale is not None:
                    server_data.id_venta_existente = existing_res_sale.id_venta
                    server_data.numero_venta_existente = existing_res_sale.numero_venta
                    conflicts.append(
                        OfflineConflictDetail(
                            tipo_conflicto="RESERVA_VENTA_DUPLICADA",
                            valor_esperado=sale_num,
                            valor_actual_servidor=existing_res_sale.numero_venta,
                            corregible=False,
                            requiere_consentimiento=False,
                            datos_servidor={
                                "id_venta": existing_res_sale.id_venta,
                                "numero_venta": existing_res_sale.numero_venta,
                            },
                            acciones_permitidas=[
                                "VINCULAR_OPERACION_EXISTENTE",
                                "DESCARTAR_OPERACION",
                            ],
                            detalle=f"La reserva '{reservation.codigo}' ya tiene una venta registrada ({existing_res_sale.numero_venta}).",
                        )
                    )
                    allowed_actions.append("VINCULAR_OPERACION_EXISTENTE")
                elif res_state in ("CANCELADA", "EXPIRADA"):
                    conflicts.append(
                        OfflineConflictDetail(
                            tipo_conflicto="RESERVA_CANCELADA",
                            valor_esperado="ATENDIDA",
                            valor_actual_servidor=res_state,
                            corregible=False,
                            requiere_consentimiento=True,
                            datos_servidor={
                                "id_reserva": reservation.id_reserva,
                                "codigo_reserva": reservation.codigo,
                                "estado_reserva": res_state,
                            },
                            acciones_permitidas=["DESCARTAR_OPERACION"],
                            detalle=f"La reserva '{reservation.codigo}' está {res_state} y no puede facturarse.",
                        )
                    )
                elif res_state != "ATENDIDA":
                    conflicts.append(
                        OfflineConflictDetail(
                            tipo_conflicto="RESERVA_NO_ATENDIDA",
                            valor_esperado="ATENDIDA",
                            valor_actual_servidor=res_state,
                            corregible=True,
                            requiere_consentimiento=True,
                            datos_servidor={
                                "id_reserva": reservation.id_reserva,
                                "codigo_reserva": reservation.codigo,
                                "estado_reserva": res_state,
                            },
                            acciones_permitidas=[
                                "COMPLETAR_TRANSICIONES_RESERVA",
                                "DESCARTAR_OPERACION",
                            ],
                            detalle=(
                                f"La reserva '{reservation.codigo}' se encuentra en estado {res_state} "
                                "y debe estar ATENDIDA antes de confirmar la venta."
                            ),
                        )
                    )
                    allowed_actions.append("COMPLETAR_TRANSICIONES_RESERVA")

        # 3. Evaluar variantes, precios y stock actual
        req_variant_ids = [line.id_variante_producto for line in sale_req.detalles]
        variants_dict = sale_repo.get_variants_with_products(company_id, req_variant_ids)
        inv_map = self._get_inventory_map(
            company_id, sale_req.id_sucursal, req_variant_ids, is_reserva=False
        )

        promotions_by_product: dict[int, tuple[int, Decimal]] = {}
        if reservation is None and variants_dict:
            product_ids = sorted(
                {variants_dict[v_id][1].id_producto for v_id in variants_dict}
            )
            if hasattr(sale_repo, "get_active_promotions_for_products"):
                raw_promos = sale_repo.get_active_promotions_for_products(
                    company_id, product_ids, current_time
                )
                if isinstance(raw_promos, dict):
                    promotions_by_product = raw_promos

        reserved_map: dict[int, Any] = {}
        if reservation is not None:
            res_details = sale_repo.get_reservation_details(
                company_id, reservation.id_reserva
            )
            if isinstance(res_details, list):
                reserved_map = {r.id_variante_producto: r for r in res_details}

        subtotal_srv = Decimal("0.00")
        discount_srv = Decimal("0.00")

        for line in sale_req.detalles:
            v_id = line.id_variante_producto
            if v_id not in variants_dict:
                conflicts.append(
                    OfflineConflictDetail(
                        tipo_conflicto="REGLA_NEGOCIO",
                        id_variante_producto=v_id,
                        corregible=len(sale_req.detalles) > 1,
                        requiere_consentimiento=True,
                        acciones_permitidas=(
                            ["QUITAR_PRENDA", "DESCARTAR_OPERACION"]
                            if len(sale_req.detalles) > 1
                            else ["DESCARTAR_OPERACION"]
                        ),
                        detalle=f"La variante #{v_id} no existe en la empresa.",
                    )
                )
                continue

            variant_obj, product_obj = variants_dict[v_id]
            sku_str = getattr(variant_obj, "sku", str(v_id))

            if reservation is not None and v_id in reserved_map:
                unit_price = self.sale_service._money(reserved_map[v_id].precio_unitario)
                unit_discount = Decimal("0.00")
                promo_id = None
            else:
                base_price = self.sale_service._money(
                    getattr(product_obj, "precio_base", None)
                    or getattr(product_obj, "precio", Decimal("0.00"))
                )
                if product_obj.id_producto in promotions_by_product:
                    promo_id, unit_discount = promotions_by_product[
                        product_obj.id_producto
                    ]
                elif getattr(product_obj, "precio_final", None) is not None:
                    final_p = self.sale_service._money(product_obj.precio_final)
                    unit_discount = max(Decimal("0.00"), base_price - final_p)
                    promo_id = line.id_promocion if unit_discount > 0 else None
                else:
                    unit_discount = Decimal("0.00")
                    promo_id = None
                unit_price = base_price

            server_net_unit = self.sale_service._money(unit_price - unit_discount)
            subtotal_srv += self.sale_service._money(line.cantidad * unit_price)
            discount_srv += self.sale_service._money(line.cantidad * unit_discount)

            inv_obj = inv_map.get(v_id)
            s_actual = int(getattr(inv_obj, "stock_actual", 0)) if inv_obj else 0
            s_res = int(getattr(inv_obj, "stock_reservado", 0)) if inv_obj else 0
            s_disp = (
                s_res
                if reservation is not None
                else max(0, s_actual - s_res)
            )

            server_data.variantes.append(
                OfflineServerVariantSnapshot(
                    id_variante_producto=v_id,
                    id_producto=getattr(product_obj, "id_producto", None),
                    sku=sku_str,
                    nombre_producto=getattr(product_obj, "nombre", None),
                    activa=bool(
                        getattr(variant_obj, "estado", True)
                        and getattr(product_obj, "estado", True)
                    ),
                    stock_actual=s_actual,
                    stock_reservado=s_res,
                    stock_disponible=s_disp,
                    precio_base_servidor=unit_price,
                    descuento_unitario_servidor=unit_discount,
                    precio_neto_servidor=server_net_unit,
                    id_promocion_activa=promo_id,
                    cantidad_solicitada=line.cantidad,
                    precio_capturado_offline=line.precio_unitario,
                )
            )

            if line.precio_unitario is not None:
                captured_unit = self.sale_service._money(line.precio_unitario)
                captured_disc = self.sale_service._money(
                    line.descuento_unitario or Decimal("0.00")
                )
                captured_net = self.sale_service._money(captured_unit - captured_disc)
                if captured_net != server_net_unit and captured_unit != server_net_unit:
                    if "ACEPTAR_PRECIO_SERVIDOR" not in allowed_actions:
                        allowed_actions.append("ACEPTAR_PRECIO_SERVIDOR")
                    conflicts.append(
                        OfflineConflictDetail(
                            tipo_conflicto="PRECIO_MODIFICADO",
                            id_variante_producto=v_id,
                            sku=sku_str,
                            valor_esperado=captured_net,
                            valor_actual_servidor=server_net_unit,
                            corregible=True,
                            requiere_consentimiento=True,
                            datos_servidor={
                                "id_variante_producto": v_id,
                                "sku": sku_str,
                                "precio_base_servidor": str(unit_price),
                                "descuento_unitario_servidor": str(unit_discount),
                                "precio_neto_servidor": str(server_net_unit),
                                "precio_capturado_offline": str(captured_net),
                            },
                            acciones_permitidas=[
                                "ACEPTAR_PRECIO_SERVIDOR",
                                "DESCARTAR_OPERACION",
                            ],
                            detalle=(
                                f"El precio de '{sku_str}' cambió en el servidor "
                                f"(capturado: Bs {captured_net}, actual: Bs {server_net_unit})."
                            ),
                        )
                    )

            if reservation is None and s_disp < line.cantidad:
                item_actions: list[OfflineResolutionAction] = []
                if s_disp > 0:
                    item_actions.append("AJUSTAR_CANTIDAD_STOCK")
                if len(sale_req.detalles) > 1:
                    item_actions.append("QUITAR_PRENDA")
                if role == "CLIENTE":
                    item_actions.append("CAMBIAR_SUCURSAL")
                item_actions.append("DESCARTAR_OPERACION")
                for act in item_actions:
                    if act not in allowed_actions:
                        allowed_actions.append(act)

                conflicts.append(
                    OfflineConflictDetail(
                        tipo_conflicto="STOCK_INSUFICIENTE",
                        id_variante_producto=v_id,
                        sku=sku_str,
                        valor_esperado=line.cantidad,
                        valor_actual_servidor=s_disp,
                        corregible=s_disp > 0 or len(sale_req.detalles) > 1 or role == "CLIENTE",
                        requiere_consentimiento=True,
                        datos_servidor={
                            "id_variante_producto": v_id,
                            "sku": sku_str,
                            "stock_actual": s_actual,
                            "stock_reservado": s_res,
                            "stock_disponible": s_disp,
                            "cantidad_solicitada": line.cantidad,
                        },
                        acciones_permitidas=item_actions,
                        detalle=(
                            f"Stock disponible insuficiente para '{sku_str}'. "
                            f"Disponible: {s_disp}, Solicitado: {line.cantidad}."
                        ),
                    )
                )

        total_srv = self.sale_service._money(subtotal_srv - discount_srv)
        server_data.subtotal_servidor = subtotal_srv
        server_data.descuento_total_servidor = discount_srv
        server_data.total_servidor = total_srv

        if "DESCARTAR_OPERACION" not in allowed_actions:
            allowed_actions.append("DESCARTAR_OPERACION")

        if conflicts:
            primary = conflicts[0]
            return OfflineOperationConflictDiagnosis(
                uuid_operacion=op.uuid_operacion,
                uuid_entidad=sale_req.uuid_venta_offline,
                tipo_operacion=op.tipo_operacion,
                secuencia=seq_num,
                codigo_local=op.codigo_local,
                estado_resultado="EN_CONFLICTO",
                estado_sincronizacion="CONFLICTO",
                codigo_conflicto_principal=primary.tipo_conflicto,
                motivo=primary.detalle,
                corregible=any(c.corregible for c in conflicts),
                requiere_consentimiento=any(c.requiere_consentimiento for c in conflicts),
                conflictos=conflicts,
                datos_actuales_servidor=server_data,
                acciones_permitidas=allowed_actions,
                mensaje=f"Se detectaron {len(conflicts)} conflicto(s) en la operación {op.tipo_operacion}.",
            )

        return OfflineOperationConflictDiagnosis(
            uuid_operacion=op.uuid_operacion,
            uuid_entidad=sale_req.uuid_venta_offline,
            tipo_operacion=op.tipo_operacion,
            secuencia=seq_num,
            codigo_local=op.codigo_local,
            estado_resultado="REINTENTABLE",
            estado_sincronizacion="PENDIENTE_SINCRONIZACION",
            motivo=None,
            corregible=True,
            requiere_consentimiento=False,
            conflictos=[],
            datos_actuales_servidor=server_data,
            acciones_permitidas=["REINTENTAR_SIN_CAMBIOS", "DESCARTAR_OPERACION"],
            mensaje=f"La operación {op.tipo_operacion} está validada y lista para sincronizarse.",
        )

    # =========================================================================
    # 2. RESOLUCIÓN TRANSACCIONAL CON CONSENTIMIENTO EXPLÍCITO E IDEMPOTENCIA
    # =========================================================================
    def resolve_conflicts(
        self,
        user: AuthenticatedUserData,
        payload: OfflineConflictResolveRequest,
        *,
        requested_company_id: int | None = None,
        now: datetime | None = None,
    ) -> OfflineConflictResolveResponse:
        """Ejecuta las acciones de resolución autorizadas por el usuario preservando UUID, dependencias e inventario."""
        company_id, role = self._validate_session_and_tenant(
            user, requested_company_id
        )
        current_time = now or datetime.now(timezone.utc).replace(tzinfo=None)
        self._validate_saas_offline(company_id, now=current_time)

        indexed_items = list(enumerate(payload.resoluciones))
        indexed_items.sort(
            key=lambda pair: (
                pair[1].secuencia if pair[1].secuencia is not None else pair[0],
                pair[0],
            )
        )

        results: list[OfflineOperationResolutionResult] = []
        results_by_uuid: dict[str, OfflineOperationResolutionResult] = {}
        code_links: dict[str, OfflineCodeLinkItem] = {}
        reservation_links: dict[str, tuple[int, str]] = {}
        failed_ops: dict[str, tuple[OfflineSyncResultStatus, str]] = {}

        for idx, (_, res_input) in enumerate(indexed_items, start=1):
            seq_num = res_input.secuencia if res_input.secuencia is not None else idx
            res_result = self._process_single_resolution(
                user=user,
                role=role,
                company_id=company_id,
                res_input=res_input,
                seq_num=seq_num,
                current_time=current_time,
                reservation_links=reservation_links,
                failed_ops=failed_ops,
            )
            results.append(res_result)
            results_by_uuid[res_result.uuid_operacion] = res_result

            if (
                res_result.confirmada
                and res_result.id_servidor
                and res_result.codigo_servidor
            ):
                for ref_key in {
                    res_input.uuid_operacion,
                    res_input.uuid_entidad,
                    res_input.codigo_local,
                }:
                    if ref_key:
                        code_links[ref_key] = OfflineCodeLinkItem(
                            referencia_local=ref_key,
                            tipo_operacion=res_input.tipo_operacion,
                            id_servidor=res_result.id_servidor,
                            codigo_servidor=res_result.codigo_servidor,
                        )
                        if res_input.tipo_operacion in ("RESERVA", "TRANSICION_RESERVA"):
                            reservation_links[ref_key] = (
                                res_result.id_servidor,
                                res_result.codigo_servidor,
                            )
            elif not res_result.confirmada:
                reason_text = res_result.motivo or res_result.mensaje
                fail_keys: set[str | None] = {
                    res_input.uuid_operacion,
                    res_input.uuid_entidad,
                    res_input.codigo_local,
                    res_result.codigo_reserva_asociada,
                    f"res-id:{res_result.id_reserva_asociada}"
                    if res_result.id_reserva_asociada is not None
                    else None,
                }
                if res_input.transicion is not None:
                    fail_keys.add(res_input.transicion.uuid_reserva_offline)
                    fail_keys.add(res_input.transicion.codigo_reserva)
                    if res_input.transicion.id_reserva is not None:
                        fail_keys.add(f"res-id:{res_input.transicion.id_reserva}")
                if res_input.reserva is not None:
                    fail_keys.add(res_input.reserva.uuid_reserva_offline)
                for fk in fail_keys:
                    if fk:
                        failed_ops[fk] = (res_result.estado_resultado, reason_text)

        confirmed_count = sum(1 for r in results if r.confirmada)
        discarded_count = sum(1 for r in results if r.descartada_por_usuario)
        conflict_count = sum(
            1 for r in results if r.estado_resultado == "EN_CONFLICTO"
        )
        rejected_count = sum(
            1
            for r in results
            if r.estado_resultado == "RECHAZADA" and not r.descartada_por_usuario
        )
        retryable_count = sum(
            1 for r in results if r.estado_resultado == "REINTENTABLE"
        )
        all_resolved = all(r.resuelta for r in results)

        return OfflineConflictResolveResponse(
            success=all_resolved,
            empresa_id=company_id,
            id_usuario=user.id_usuario,
            rol=role,
            total_procesadas=len(results),
            confirmadas=confirmed_count,
            descartadas=discarded_count,
            en_conflicto=conflict_count,
            rechazadas=rejected_count,
            reintentables=retryable_count,
            resultados=results,
            resultados_por_uuid=results_by_uuid,
            vinculaciones_codigos=code_links,
            fecha_resolucion=current_time,
            mensaje=(
                f"Resolución completada con éxito: {confirmed_count} confirmadas, {discarded_count} descartadas."
                if all_resolved
                else (
                    f"Resolución parcial: {confirmed_count} confirmadas, {discarded_count} descartadas, "
                    f"{conflict_count} en conflicto, {rejected_count} rechazadas, {retryable_count} reintentables."
                )
            ),
        )

    def _process_single_resolution(
        self,
        *,
        user: AuthenticatedUserData,
        role: str,
        company_id: int,
        res_input: OfflineOperationResolutionInput,
        seq_num: int,
        current_time: datetime,
        reservation_links: dict[str, tuple[int, str]],
        failed_ops: dict[str, tuple[OfflineSyncResultStatus, str]],
    ) -> OfflineOperationResolutionResult:
        op_type = res_input.tipo_operacion
        action = res_input.accion_resolucion

        # 1. Validar correspondencia rol <-> tipo de operación y acción permitida
        if op_type in CLIENT_ONLY_TYPES and role != "CLIENTE":
            reason = (
                f"El rol '{role}' no tiene permisos para resolver operaciones de tipo '{op_type}'. "
                "Únicamente el CLIENTE puede resolver reservas y compras digitales."
            )
            return self._build_failed_resolution(
                res_input=res_input,
                seq_num=seq_num,
                user=user,
                company_id=company_id,
                current_time=current_time,
                result_status="RECHAZADA",
                reason=reason,
            )

        if op_type in STAFF_ONLY_TYPES and role not in ("CAJERO", "ENCARGADO_SUCURSAL"):
            reason = (
                f"El rol '{role}' no tiene permisos para resolver operaciones de tipo '{op_type}'. "
                "Se requiere rol CAJERO o ENCARGADO_SUCURSAL."
            )
            return self._build_failed_resolution(
                res_input=res_input,
                seq_num=seq_num,
                user=user,
                company_id=company_id,
                current_time=current_time,
                result_status="RECHAZADA",
                reason=reason,
            )

        allowed_set = CLIENT_ALLOWED_ACTIONS if role == "CLIENTE" else STAFF_ALLOWED_ACTIONS
        if action not in allowed_set:
            reason = f"La acción '{action}' no está permitida para el rol '{role}'."
            return self._build_failed_resolution(
                res_input=res_input,
                seq_num=seq_num,
                user=user,
                company_id=company_id,
                current_time=current_time,
                result_status="RECHAZADA",
                reason=reason,
            )

        # 2. Verificar bloqueo por dependencia previa no resuelta (excepto si el usuario descarta la operación)
        if action != "DESCARTAR_OPERACION":
            dep_candidates: list[str | None] = [res_input.depende_de_uuid]
            if res_input.transicion is not None:
                dep_candidates.extend(
                    [
                        res_input.transicion.uuid_reserva_offline,
                        res_input.transicion.codigo_reserva,
                        f"res-id:{res_input.transicion.id_reserva}"
                        if res_input.transicion.id_reserva is not None
                        else None,
                    ]
                )
            if res_input.venta is not None:
                dep_candidates.extend(
                    [
                        res_input.venta.uuid_reserva_offline,
                        res_input.venta.codigo_reserva,
                        f"res-id:{res_input.venta.id_reserva}"
                        if res_input.venta.id_reserva is not None
                        else None,
                    ]
                )

            for dep_key in dep_candidates:
                if dep_key and dep_key in failed_ops:
                    p_status, p_reason = failed_ops[dep_key]
                    dep_res_status: OfflineSyncResultStatus = (
                        "REINTENTABLE"
                        if p_status == "REINTENTABLE"
                        else "EN_CONFLICTO"
                    )
                    reason = (
                        f"Operación bloqueada: la operación previa dependiente ('{dep_key}') "
                        f"no pudo confirmarse ({p_status}: {p_reason}). Resuelva primero la operación previa."
                    )
                    return self._build_failed_resolution(
                        res_input=res_input,
                        seq_num=seq_num,
                        user=user,
                        company_id=company_id,
                        current_time=current_time,
                        result_status=dep_res_status,
                        reason=reason,
                        conflicts=[
                            OfflineConflictDetail(
                                tipo_conflicto="DEPENDENCIA_BLOQUEADA",
                                valor_esperado="CONFIRMADA",
                                valor_actual_servidor=p_status,
                                corregible=True,
                                requiere_consentimiento=False,
                                datos_servidor={
                                    "dependencia_uuid": dep_key,
                                    "estado_dependencia": p_status,
                                },
                                acciones_permitidas=["DESCARTAR_OPERACION"],
                                detalle=reason,
                            )
                        ],
                    )

        # 3. Validar consentimiento explícito del usuario para acciones que modifican condiciones comerciales
        if action in ACTIONS_REQUIRING_CONSENT and not res_input.consentimiento_usuario:
            reason = (
                f"La acción de resolución '{action}' requiere consentimiento explícito del usuario "
                "('consentimiento_usuario': true) para aplicarse."
            )
            return self._build_failed_resolution(
                res_input=res_input,
                seq_num=seq_num,
                user=user,
                company_id=company_id,
                current_time=current_time,
                result_status="EN_CONFLICTO",
                reason=reason,
                conflicts=[
                    OfflineConflictDetail(
                        tipo_conflicto="REGLA_NEGOCIO",
                        corregible=True,
                        requiere_consentimiento=True,
                        acciones_permitidas=[action, "DESCARTAR_OPERACION"],
                        detalle=reason,
                    )
                ],
            )

        # 4. Manejo de DESCARTAR_OPERACION
        if action == "DESCARTAR_OPERACION":
            return self._execute_discard_operation(
                user=user,
                company_id=company_id,
                res_input=res_input,
                seq_num=seq_num,
                current_time=current_time,
            )

        # 5. Ejecutar resolución según el tipo de operación
        try:
            if op_type == "RESERVA":
                return self._resolve_reservation_operation(
                    user=user,
                    company_id=company_id,
                    res_input=res_input,
                    seq_num=seq_num,
                    current_time=current_time,
                )

            if op_type == "TRANSICION_RESERVA":
                return self._resolve_transition_operation(
                    user=user,
                    company_id=company_id,
                    res_input=res_input,
                    seq_num=seq_num,
                    current_time=current_time,
                    reservation_links=reservation_links,
                    failed_ops=failed_ops,
                )

            if op_type in ("COMPRA", "VENTA"):
                return self._resolve_sale_or_purchase_operation(
                    user=user,
                    company_id=company_id,
                    res_input=res_input,
                    seq_num=seq_num,
                    current_time=current_time,
                    reservation_links=reservation_links,
                    failed_ops=failed_ops,
                )

            return self._build_failed_resolution(
                res_input=res_input,
                seq_num=seq_num,
                user=user,
                company_id=company_id,
                current_time=current_time,
                result_status="RECHAZADA",
                reason=f"Tipo de operación no soportado: {op_type}",
            )
        except (OfflineReservationError, OfflineSaleError) as domain_err:
            self.db.rollback()
            is_retryable = getattr(domain_err, "status_code", 400) >= 500
            return self._build_failed_resolution(
                res_input=res_input,
                seq_num=seq_num,
                user=user,
                company_id=company_id,
                current_time=current_time,
                result_status="REINTENTABLE" if is_retryable else "RECHAZADA",
                reason=domain_err.message,
            )
        except OperationalError as db_err:
            self.db.rollback()
            logger.warning(
                "Error transitorio de BD resolviendo operación %s: %s",
                res_input.uuid_operacion,
                db_err,
            )
            return self._build_failed_resolution(
                res_input=res_input,
                seq_num=seq_num,
                user=user,
                company_id=company_id,
                current_time=current_time,
                result_status="REINTENTABLE",
                reason="Fallo transitorio de concurrencia o conexión a base de datos; seguro para reintentar.",
                conflicts=[
                    OfflineConflictDetail(
                        tipo_conflicto="ERROR_REINTENTABLE",
                        corregible=True,
                        requiere_consentimiento=False,
                        acciones_permitidas=["REINTENTAR_SIN_CAMBIOS"],
                        detalle="Fallo transitorio de base de datos; seguro para reintentar.",
                    )
                ],
            )
        except Exception as exc:
            self.db.rollback()
            logger.exception(
                "Error inesperado resolviendo operación %s: %s",
                res_input.uuid_operacion,
                exc,
            )
            return self._build_failed_resolution(
                res_input=res_input,
                seq_num=seq_num,
                user=user,
                company_id=company_id,
                current_time=current_time,
                result_status="REINTENTABLE",
                reason="Error interno temporal al procesar la resolución; seguro para reintentar.",
                conflicts=[
                    OfflineConflictDetail(
                        tipo_conflicto="ERROR_REINTENTABLE",
                        corregible=True,
                        requiere_consentimiento=False,
                        acciones_permitidas=["REINTENTAR_SIN_CAMBIOS"],
                        detalle="Error interno temporal; seguro para reintentar.",
                    )
                ],
            )

    def _execute_discard_operation(
        self,
        *,
        user: AuthenticatedUserData,
        company_id: int,
        res_input: OfflineOperationResolutionInput,
        seq_num: int,
        current_time: datetime,
    ) -> OfflineOperationResolutionResult:
        branch_id = 1
        if res_input.reserva and res_input.reserva.id_sucursal:
            branch_id = res_input.reserva.id_sucursal
        elif res_input.compra and res_input.compra.id_sucursal:
            branch_id = res_input.compra.id_sucursal
        elif res_input.venta and res_input.venta.id_sucursal:
            branch_id = res_input.venta.id_sucursal
        elif res_input.transicion and res_input.transicion.id_sucursal:
            branch_id = res_input.transicion.id_sucursal

        reason = "Operación descartada voluntariamente por el usuario tras conflicto de sincronización."
        if res_input.tipo_operacion == "RESERVA" and res_input.reserva is not None:
            try:
                client = self.reservation_service.repository.get_client_by_user(
                    company_id, user.id_usuario
                )
                if client is not None and getattr(client, "id_cliente", None):
                    self.conflict_repo.mark_reservation_sync_discarded(
                        company_id=company_id,
                        uuid_offline=res_input.reserva.uuid_reserva_offline,
                        branch_id=branch_id,
                        client_id=client.id_cliente,
                        user_id=user.id_usuario,
                        reason=reason,
                        now=current_time,
                    )
                    self.db.commit()
            except Exception:
                self.db.rollback()

        cu12_summary = OfflineOperationItemSummary(
            uuid_operacion=res_input.uuid_operacion,
            tipo_operacion=res_input.tipo_operacion,
            id_sucursal=branch_id,
            sucursal_nombre=self.queue_repo.get_branch_name(company_id, branch_id),
            id_usuario=user.id_usuario,
            rol_actor=(user.rol or "").upper(),
            fecha_sincronizacion=current_time,
            estado_local="CANCELADA",
            estado_sincronizacion="RECHAZADA",
            confirmada=False,
            motivo=reason,
        )

        return OfflineOperationResolutionResult(
            uuid_operacion=res_input.uuid_operacion,
            uuid_entidad=res_input.uuid_entidad or res_input.uuid_operacion,
            tipo_operacion=res_input.tipo_operacion,
            secuencia=seq_num,
            accion_aplicada="DESCARTAR_OPERACION",
            consentimiento_verificado=True,
            resuelta=True,
            descartada_por_usuario=True,
            confirmada=False,
            estado_resultado="RECHAZADA",
            estado_sincronizacion="RECHAZADA",
            codigo_local=res_input.codigo_local,
            id_sucursal=branch_id,
            id_usuario=user.id_usuario,
            id_empresa=company_id,
            reintentable=False,
            conservar_en_cola=False,
            motivo=reason,
            mensaje=reason,
            fecha_resolucion=current_time,
            resumen_cu12=cu12_summary,
        )

    def _resolve_reservation_operation(
        self,
        *,
        user: AuthenticatedUserData,
        company_id: int,
        res_input: OfflineOperationResolutionInput,
        seq_num: int,
        current_time: datetime,
    ) -> OfflineOperationResolutionResult:
        if res_input.reserva is None:
            return self._build_failed_resolution(
                res_input=res_input,
                seq_num=seq_num,
                user=user,
                company_id=company_id,
                current_time=current_time,
                result_status="RECHAZADA",
                reason="Faltan los datos de la reserva ('reserva') para ejecutar la resolución.",
            )

        res_req = res_input.reserva.model_copy(deep=True)
        action = res_input.accion_resolucion

        if res_input.nuevo_id_sucursal is not None:
            res_req.id_sucursal = res_input.nuevo_id_sucursal

        if res_input.nueva_fecha_atencion_programada is not None:
            res_req.fecha_atencion_programada = res_input.nueva_fecha_atencion_programada

        # Filtrar variantes excluidas si aplica
        if res_input.variantes_excluidas:
            excluded = set(res_input.variantes_excluidas)
            res_req.detalles = [
                d for d in res_req.detalles if d.id_variante_producto not in excluded
            ]

        # Aplicar ajustes de cantidad explícitos o ajustar automáticamente al stock disponible
        if res_input.cantidades_ajustadas:
            new_details = []
            for d in res_req.detalles:
                if d.id_variante_producto in res_input.cantidades_ajustadas:
                    new_qty = res_input.cantidades_ajustadas[d.id_variante_producto]
                    if new_qty > 0:
                        d.cantidad = new_qty
                        new_details.append(d)
                else:
                    new_details.append(d)
            res_req.detalles = new_details
        elif action == "AJUSTAR_CANTIDAD_STOCK":
            req_v_ids = [d.id_variante_producto for d in res_req.detalles]
            inv_map = self._get_inventory_map(
                company_id, res_req.id_sucursal, req_v_ids, is_reserva=True
            )
            adjusted_details = []
            for d in res_req.detalles:
                inv = inv_map.get(d.id_variante_producto)
                avail = (
                    max(0, int(inv.stock_actual) - int(inv.stock_reservado))
                    if inv is not None
                    else d.cantidad
                )
                if avail > 0:
                    d.cantidad = min(d.cantidad, avail)
                    adjusted_details.append(d)
            res_req.detalles = adjusted_details

        if not res_req.detalles:
            return self._build_failed_resolution(
                res_input=res_input,
                seq_num=seq_num,
                user=user,
                company_id=company_id,
                current_time=current_time,
                result_status="EN_CONFLICTO",
                reason="No quedaron prendas con stock disponible tras aplicar el ajuste; puede cambiar de sucursal o descartar la reserva.",
                conflicts=[
                    OfflineConflictDetail(
                        tipo_conflicto="STOCK_INSUFICIENTE",
                        valor_actual_servidor=0,
                        corregible=True,
                        requiere_consentimiento=True,
                        acciones_permitidas=["CAMBIAR_SUCURSAL", "DESCARTAR_OPERACION"],
                        detalle="Ninguna prenda cuenta con stock disponible en la sucursal.",
                    )
                ],
            )

        res_resp = self.reservation_service.sync_offline_reservation(
            user,
            res_req,
            requested_company_id=company_id,
            now=current_time,
            allow_conflict_resolution=True,
        )

        op_input = OfflineSyncOperationInput(
            uuid_operacion=res_input.uuid_operacion,
            uuid_entidad=res_req.uuid_reserva_offline,
            tipo_operacion="RESERVA",
            secuencia=seq_num,
            codigo_local=res_input.codigo_local,
            reserva=res_req,
        )

        cu12_summary = OfflineOperationItemSummary(
            uuid_operacion=res_input.uuid_operacion,
            tipo_operacion="RESERVA",
            id_sucursal=res_resp.id_sucursal,
            sucursal_nombre=self.queue_repo.get_branch_name(
                company_id, res_resp.id_sucursal
            ),
            id_usuario=res_resp.id_usuario,
            rol_actor="CLIENTE",
            id_cliente=res_resp.id_cliente,
            fecha_operacion_offline=res_req.fecha_reserva_offline,
            fecha_sincronizacion=res_resp.fecha_sincronizacion,
            estado_local="REGISTRADA_LOCAL",
            estado_sincronizacion=res_resp.estado_sincronizacion,
            confirmada=res_resp.confirmada,
            id_servidor=res_resp.id_reserva,
            codigo_servidor=res_resp.codigo_reserva,
            estado_servidor=res_resp.estado_reserva,
            motivo=res_resp.motivo,
        )

        res_conflicts: list[OfflineConflictDetail] = []
        if not res_resp.confirmada and (res_resp.motivo or res_resp.mensaje):
            diag = self._diagnose_reservation(
                user=user,
                company_id=company_id,
                op=op_input,
                res_req=res_req,
                seq_num=seq_num,
                current_time=current_time,
                server_data=OfflineServerCurrentData(id_sucursal=res_req.id_sucursal),
            )
            res_conflicts = diag.conflictos

        cu13_result = OfflineSyncOperationResult(
            uuid_operacion=res_input.uuid_operacion,
            uuid_entidad=res_resp.uuid_reserva_offline,
            tipo_operacion="RESERVA",
            secuencia=seq_num,
            confirmada=res_resp.confirmada,
            estado_resultado=res_resp.estado_resultado,
            estado_sincronizacion=res_resp.estado_sincronizacion,
            id_servidor=res_resp.id_reserva,
            codigo_servidor=res_resp.codigo_reserva,
            codigo_local=res_input.codigo_local,
            estado_entidad_servidor=res_resp.estado_reserva,
            id_reserva_asociada=res_resp.id_reserva,
            codigo_reserva_asociada=res_resp.codigo_reserva,
            id_sucursal=res_resp.id_sucursal,
            id_cliente=res_resp.id_cliente,
            id_usuario=res_resp.id_usuario,
            id_empresa=res_resp.id_empresa,
            reintentable=False,
            conservar_en_cola=not res_resp.confirmada,
            conflictos=res_conflicts,
            motivo=res_resp.motivo,
            mensaje=res_resp.mensaje,
            fecha_sincronizacion=res_resp.fecha_sincronizacion,
            resumen_cu12=cu12_summary,
        )

        return OfflineOperationResolutionResult(
            uuid_operacion=res_input.uuid_operacion,
            uuid_entidad=res_resp.uuid_reserva_offline,
            tipo_operacion="RESERVA",
            secuencia=seq_num,
            accion_aplicada=action,
            consentimiento_verificado=res_input.consentimiento_usuario,
            resuelta=res_resp.confirmada,
            confirmada=res_resp.confirmada,
            estado_resultado=res_resp.estado_resultado,
            estado_sincronizacion=res_resp.estado_sincronizacion,
            id_servidor=res_resp.id_reserva,
            codigo_servidor=res_resp.codigo_reserva,
            codigo_local=res_input.codigo_local,
            estado_entidad_servidor=res_resp.estado_reserva,
            id_reserva_asociada=res_resp.id_reserva,
            codigo_reserva_asociada=res_resp.codigo_reserva,
            id_sucursal=res_resp.id_sucursal,
            id_usuario=res_resp.id_usuario,
            id_empresa=res_resp.id_empresa,
            reintentable=False,
            conservar_en_cola=not res_resp.confirmada,
            conflictos=res_conflicts,
            motivo=res_resp.motivo,
            mensaje=res_resp.mensaje,
            fecha_resolucion=res_resp.fecha_sincronizacion,
            resumen_cu12=cu12_summary,
            resultado_cu13=cu13_result,
        )

    def _resolve_transition_operation(
        self,
        *,
        user: AuthenticatedUserData,
        company_id: int,
        res_input: OfflineOperationResolutionInput,
        seq_num: int,
        current_time: datetime,
        reservation_links: dict[str, tuple[int, str]],
        failed_ops: dict[str, tuple[OfflineSyncResultStatus, str]],
    ) -> OfflineOperationResolutionResult:
        if res_input.transicion is None:
            return self._build_failed_resolution(
                res_input=res_input,
                seq_num=seq_num,
                user=user,
                company_id=company_id,
                current_time=current_time,
                result_status="RECHAZADA",
                reason="Faltan los datos de transición ('transicion') para resolver la operación.",
            )

        trans_req = res_input.transicion.model_copy(deep=True)
        action = res_input.accion_resolucion

        resolved_id, resolved_code = self.sync_service._resolve_linked_reservation(
            company_id=company_id,
            uuid_offline=trans_req.uuid_reserva_offline or res_input.uuid_entidad,
            code=trans_req.codigo_reserva or res_input.codigo_local,
            reservation_id=trans_req.id_reserva,
            reservation_links=reservation_links,
        )
        if resolved_id is not None:
            trans_req.id_reserva = resolved_id
        if resolved_code is not None:
            trans_req.codigo_reserva = resolved_code

        # Si el cajero autorizó CONFIRMAR_Y_ATENDER_RESERVA o COMPLETAR_TRANSICIONES_RESERVA
        # sobre una transición ATTEND cuya reserva sigue en PENDIENTE, primero confirmar la reserva
        if action in (
            "CONFIRMAR_Y_ATENDER_RESERVA",
            "COMPLETAR_TRANSICIONES_RESERVA",
        ) and trans_req.accion in ("ATTEND", "ATENDER"):
            confirm_step = trans_req.model_copy(
                update={
                    "uuid_operacion_offline": f"{trans_req.uuid_operacion_offline}-autoconfirm",
                    "accion": "CONFIRM",
                }
            )
            confirm_resp = self.sale_service.sync_reservation_transition(
                user,
                confirm_step,
                requested_company_id=company_id,
                now=current_time,
            )
            if not confirm_resp.confirmada:
                return self._build_failed_resolution(
                    res_input=res_input,
                    seq_num=seq_num,
                    user=user,
                    company_id=company_id,
                    current_time=current_time,
                    result_status=confirm_resp.estado_resultado,
                    reason=confirm_resp.motivo or confirm_resp.mensaje,
                    conflicts=confirm_resp.conflictos,
                )

        op_input = OfflineSyncOperationInput(
            uuid_operacion=res_input.uuid_operacion,
            uuid_entidad=res_input.uuid_entidad or trans_req.uuid_reserva_offline,
            tipo_operacion="TRANSICION_RESERVA",
            secuencia=seq_num,
            codigo_local=res_input.codigo_local,
            transicion=trans_req,
        )
        cu13_res = self.sync_service._execute_transition_sync(
            user=user,
            company_id=company_id,
            op=op_input,
            seq_num=seq_num,
            current_time=current_time,
            reservation_links=reservation_links,
            failed_ops=failed_ops,
        )

        return OfflineOperationResolutionResult(
            uuid_operacion=cu13_res.uuid_operacion,
            uuid_entidad=cu13_res.uuid_entidad,
            tipo_operacion="TRANSICION_RESERVA",
            secuencia=seq_num,
            accion_aplicada=action,
            consentimiento_verificado=res_input.consentimiento_usuario,
            resuelta=cu13_res.confirmada,
            confirmada=cu13_res.confirmada,
            estado_resultado=cu13_res.estado_resultado,
            estado_sincronizacion=cu13_res.estado_sincronizacion,
            id_servidor=cu13_res.id_servidor,
            codigo_servidor=cu13_res.codigo_servidor,
            codigo_local=cu13_res.codigo_local,
            estado_entidad_servidor=cu13_res.estado_entidad_servidor,
            id_reserva_asociada=cu13_res.id_reserva_asociada,
            codigo_reserva_asociada=cu13_res.codigo_reserva_asociada,
            id_sucursal=cu13_res.id_sucursal,
            id_usuario=cu13_res.id_usuario,
            id_empresa=cu13_res.id_empresa,
            reintentable=cu13_res.reintentable,
            conservar_en_cola=cu13_res.conservar_en_cola,
            conflictos=cu13_res.conflictos,
            motivo=cu13_res.motivo,
            mensaje=cu13_res.mensaje,
            fecha_resolucion=cu13_res.fecha_sincronizacion,
            resumen_cu12=cu13_res.resumen_cu12,
            resultado_cu13=cu13_res,
        )

    def _resolve_sale_or_purchase_operation(
        self,
        *,
        user: AuthenticatedUserData,
        company_id: int,
        res_input: OfflineOperationResolutionInput,
        seq_num: int,
        current_time: datetime,
        reservation_links: dict[str, tuple[int, str]],
        failed_ops: dict[str, tuple[OfflineSyncResultStatus, str]],
    ) -> OfflineOperationResolutionResult:
        is_digital = res_input.tipo_operacion == "COMPRA"
        raw_req = res_input.compra if is_digital else (res_input.venta or res_input.compra)
        if raw_req is None:
            return self._build_failed_resolution(
                res_input=res_input,
                seq_num=seq_num,
                user=user,
                company_id=company_id,
                current_time=current_time,
                result_status="RECHAZADA",
                reason=f"Faltan los datos comerciales para resolver {res_input.tipo_operacion}.",
            )

        sale_req = raw_req.model_copy(deep=True)
        forced_channel = "DIGITAL" if is_digital else "PRESENCIAL"
        sale_req.canal = forced_channel
        action = res_input.accion_resolucion

        if res_input.nuevo_id_sucursal is not None and is_digital:
            sale_req.id_sucursal = res_input.nuevo_id_sucursal

        # Excluir variantes si el usuario lo solicitó
        if res_input.variantes_excluidas:
            excluded = set(res_input.variantes_excluidas)
            sale_req.detalles = [
                line
                for line in sale_req.detalles
                if line.id_variante_producto not in excluded
            ]

        # Aplicar ajustes de cantidad explícitos o ajustar automáticamente al stock disponible
        if res_input.cantidades_ajustadas:
            adjusted_lines = []
            for line in sale_req.detalles:
                if line.id_variante_producto in res_input.cantidades_ajustadas:
                    new_qty = res_input.cantidades_ajustadas[line.id_variante_producto]
                    if new_qty > 0:
                        line.cantidad = new_qty
                        adjusted_lines.append(line)
                else:
                    adjusted_lines.append(line)
            sale_req.detalles = adjusted_lines
        elif action == "AJUSTAR_CANTIDAD_STOCK":
            req_v_ids = [line.id_variante_producto for line in sale_req.detalles]
            inv_map = self._get_inventory_map(
                company_id, sale_req.id_sucursal, req_v_ids, is_reserva=False
            )
            adjusted_lines = []
            for line in sale_req.detalles:
                inv = inv_map.get(line.id_variante_producto)
                avail = (
                    max(0, int(inv.stock_actual) - int(inv.stock_reservado))
                    if inv is not None
                    else line.cantidad
                )
                if avail > 0:
                    line.cantidad = min(line.cantidad, avail)
                    adjusted_lines.append(line)
            sale_req.detalles = adjusted_lines

        if not sale_req.detalles:
            return self._build_failed_resolution(
                res_input=res_input,
                seq_num=seq_num,
                user=user,
                company_id=company_id,
                current_time=current_time,
                result_status="EN_CONFLICTO",
                reason="No quedaron prendas con stock disponible tras aplicar el ajuste.",
                conflicts=[
                    OfflineConflictDetail(
                        tipo_conflicto="STOCK_INSUFICIENTE",
                        valor_actual_servidor=0,
                        corregible=False,
                        requiere_consentimiento=True,
                        acciones_permitidas=["DESCARTAR_OPERACION"],
                        detalle="Sin stock disponible para las prendas de la operación.",
                    )
                ],
            )

        # Si se modificaron cantidades o variantes, limpiar total/subtotal para que el servidor calcule el total exacto
        if (
            action in ("AJUSTAR_CANTIDAD_STOCK", "QUITAR_PRENDA", "ACEPTAR_PRECIO_SERVIDOR")
            or res_input.cantidades_ajustadas
            or res_input.variantes_excluidas
        ):
            sale_req.subtotal = None
            sale_req.descuento_total = None
            sale_req.total = None

        # Si es venta POS por reserva, resolver referencia y, si la acción es COMPLETAR_TRANSICIONES_RESERVA,
        # aplicar las transiciones faltantes siempre que la reserva sea válida (no CANCELADA ni EXPIRADA)
        has_reservation_ref = bool(
            sale_req.id_reserva is not None
            or sale_req.codigo_reserva
            or sale_req.uuid_reserva_offline
        )
        if has_reservation_ref:
            resolved_id, resolved_code = self.sync_service._resolve_linked_reservation(
                company_id=company_id,
                uuid_offline=sale_req.uuid_reserva_offline,
                code=sale_req.codigo_reserva,
                reservation_id=sale_req.id_reserva,
                reservation_links=reservation_links,
            )
            sale_req.id_reserva = resolved_id
            if resolved_code is not None:
                sale_req.codigo_reserva = resolved_code

            if action in (
                "COMPLETAR_TRANSICIONES_RESERVA",
                "CONFIRMAR_Y_ATENDER_RESERVA",
            ):
                reservation = self.sale_service.repository.get_reservation(
                    company_id,
                    reservation_id=sale_req.id_reserva,
                    code=sale_req.codigo_reserva,
                    uuid_offline=sale_req.uuid_reserva_offline,
                    for_update=True,
                )
                if reservation is not None:
                    if reservation.estado == "PENDIENTE":
                        conf_res = self.sale_service.sync_reservation_transition(
                            user,
                            OfflineReservationTransitionRequest(
                                uuid_operacion_offline=f"{res_input.uuid_operacion}-step-confirm",
                                id_reserva=reservation.id_reserva,
                                codigo_reserva=reservation.codigo,
                                accion="CONFIRM",
                                id_sucursal=sale_req.id_sucursal,
                            ),
                            requested_company_id=company_id,
                            now=current_time,
                        )
                        if not conf_res.confirmada:
                            return self._build_failed_resolution(
                                res_input=res_input,
                                seq_num=seq_num,
                                user=user,
                                company_id=company_id,
                                current_time=current_time,
                                result_status=conf_res.estado_resultado,
                                reason=conf_res.motivo or conf_res.mensaje,
                                conflicts=conf_res.conflictos,
                            )
                    if reservation.estado == "CONFIRMADA":
                        att_res = self.sale_service.sync_reservation_transition(
                            user,
                            OfflineReservationTransitionRequest(
                                uuid_operacion_offline=f"{res_input.uuid_operacion}-step-attend",
                                id_reserva=reservation.id_reserva,
                                codigo_reserva=reservation.codigo,
                                accion="ATTEND",
                                id_sucursal=sale_req.id_sucursal,
                            ),
                            requested_company_id=company_id,
                            now=current_time,
                        )
                        if not att_res.confirmada:
                            return self._build_failed_resolution(
                                res_input=res_input,
                                seq_num=seq_num,
                                user=user,
                                company_id=company_id,
                                current_time=current_time,
                                result_status=att_res.estado_resultado,
                                reason=att_res.motivo or att_res.mensaje,
                                conflicts=att_res.conflictos,
                            )

        accept_prices = action in (
            "ACEPTAR_PRECIO_SERVIDOR",
            "AJUSTAR_CANTIDAD_STOCK",
            "QUITAR_PRENDA",
        )
        sale_resp = self.sale_service.sync_offline_sale(
            user,
            sale_req,
            requested_company_id=company_id,
            forced_channel=forced_channel,
            now=current_time,
            accept_server_prices=accept_prices,
        )

        cu12_summary = OfflineOperationItemSummary(
            uuid_operacion=res_input.uuid_operacion,
            tipo_operacion=res_input.tipo_operacion,
            id_sucursal=sale_resp.id_sucursal,
            sucursal_nombre=self.queue_repo.get_branch_name(
                company_id, sale_resp.id_sucursal
            ),
            id_usuario=sale_resp.id_usuario,
            rol_actor="CLIENTE" if is_digital else "CAJERO",
            id_cliente=sale_resp.id_cliente,
            id_empleado=sale_resp.id_empleado,
            fecha_operacion_offline=sale_resp.fecha_operacion_offline,
            fecha_sincronizacion=sale_resp.fecha_sincronizacion,
            estado_local="REGISTRADA_LOCAL",
            estado_sincronizacion=sale_resp.estado_sincronizacion,
            confirmada=sale_resp.confirmada,
            id_servidor=sale_resp.id_venta,
            codigo_servidor=sale_resp.numero_venta,
            estado_servidor=sale_resp.estado_venta,
            monto_total=sale_resp.total,
            moneda=sale_resp.moneda,
            medio_pago=sale_resp.medio_pago,
            pago_simulado=sale_resp.pago_simulado,
            motivo=sale_resp.motivo,
        )

        cu13_result = OfflineSyncOperationResult(
            uuid_operacion=res_input.uuid_operacion,
            uuid_entidad=sale_resp.uuid_venta_offline,
            tipo_operacion=res_input.tipo_operacion,
            secuencia=seq_num,
            confirmada=sale_resp.confirmada,
            estado_resultado=sale_resp.estado_resultado,
            estado_sincronizacion=sale_resp.estado_sincronizacion,
            id_servidor=sale_resp.id_venta,
            codigo_servidor=sale_resp.numero_venta,
            codigo_local=res_input.codigo_local,
            estado_entidad_servidor=sale_resp.estado_venta,
            id_pago=sale_resp.id_pago,
            medio_pago=sale_resp.medio_pago,
            estado_pago=sale_resp.estado_pago,
            pago_simulado=sale_resp.pago_simulado,
            pendiente_validacion_externa=sale_resp.pendiente_validacion_externa,
            subtotal=sale_resp.subtotal,
            descuento_total=sale_resp.descuento_total,
            total=sale_resp.total,
            moneda=sale_resp.moneda,
            id_reserva_asociada=sale_resp.id_reserva,
            codigo_reserva_asociada=sale_resp.codigo_reserva,
            id_sucursal=sale_resp.id_sucursal,
            id_cliente=sale_resp.id_cliente,
            id_empleado=sale_resp.id_empleado,
            id_usuario=sale_resp.id_usuario,
            id_empresa=sale_resp.id_empresa,
            reintentable=False,
            conservar_en_cola=sale_resp.conservar_operacion_pendiente,
            conflictos=sale_resp.conflictos,
            liberaciones_reserva=sale_resp.liberaciones_reserva,
            motivo=sale_resp.motivo,
            mensaje=sale_resp.mensaje,
            fecha_sincronizacion=sale_resp.fecha_sincronizacion,
            resumen_cu12=cu12_summary,
        )

        return OfflineOperationResolutionResult(
            uuid_operacion=res_input.uuid_operacion,
            uuid_entidad=sale_resp.uuid_venta_offline,
            tipo_operacion=res_input.tipo_operacion,
            secuencia=seq_num,
            accion_aplicada=action,
            consentimiento_verificado=res_input.consentimiento_usuario,
            resuelta=sale_resp.confirmada,
            confirmada=sale_resp.confirmada,
            estado_resultado=sale_resp.estado_resultado,
            estado_sincronizacion=sale_resp.estado_sincronizacion,
            id_servidor=sale_resp.id_venta,
            codigo_servidor=sale_resp.numero_venta,
            codigo_local=res_input.codigo_local,
            estado_entidad_servidor=sale_resp.estado_venta,
            id_pago=sale_resp.id_pago,
            medio_pago=sale_resp.medio_pago,
            estado_pago=sale_resp.estado_pago,
            pago_simulado=sale_resp.pago_simulado,
            pendiente_validacion_externa=sale_resp.pendiente_validacion_externa,
            subtotal=sale_resp.subtotal,
            descuento_total=sale_resp.descuento_total,
            total=sale_resp.total,
            moneda=sale_resp.moneda,
            id_reserva_asociada=sale_resp.id_reserva,
            codigo_reserva_asociada=sale_resp.codigo_reserva,
            id_sucursal=sale_resp.id_sucursal,
            id_usuario=sale_resp.id_usuario,
            id_empresa=sale_resp.id_empresa,
            reintentable=False,
            conservar_en_cola=sale_resp.conservar_operacion_pendiente,
            conflictos=sale_resp.conflictos,
            liberaciones_reserva=sale_resp.liberaciones_reserva,
            motivo=sale_resp.motivo,
            mensaje=sale_resp.mensaje,
            fecha_resolucion=sale_resp.fecha_sincronizacion,
            resumen_cu12=cu12_summary,
            resultado_cu13=cu13_result,
        )

    def _build_failed_resolution(
        self,
        *,
        res_input: OfflineOperationResolutionInput,
        seq_num: int,
        user: AuthenticatedUserData,
        company_id: int,
        current_time: datetime,
        result_status: OfflineSyncResultStatus,
        reason: str,
        conflicts: list[OfflineConflictDetail] | None = None,
    ) -> OfflineOperationResolutionResult:
        sync_status: OfflineSyncServerStatus = (
            "CONFLICTO"
            if result_status == "EN_CONFLICTO"
            else (
                "PENDIENTE_SINCRONIZACION"
                if result_status == "REINTENTABLE"
                else "RECHAZADA"
            )
        )
        branch_id = 1
        if res_input.reserva and res_input.reserva.id_sucursal:
            branch_id = res_input.reserva.id_sucursal
        elif res_input.compra and res_input.compra.id_sucursal:
            branch_id = res_input.compra.id_sucursal
        elif res_input.venta and res_input.venta.id_sucursal:
            branch_id = res_input.venta.id_sucursal
        elif res_input.transicion and res_input.transicion.id_sucursal:
            branch_id = res_input.transicion.id_sucursal

        cu12_summary = OfflineOperationItemSummary(
            uuid_operacion=res_input.uuid_operacion,
            tipo_operacion=res_input.tipo_operacion,
            id_sucursal=branch_id,
            sucursal_nombre=self.queue_repo.get_branch_name(company_id, branch_id),
            id_usuario=user.id_usuario,
            rol_actor=(user.rol or "").upper(),
            fecha_sincronizacion=current_time,
            estado_local="REGISTRADA_LOCAL",
            estado_sincronizacion=sync_status,
            confirmada=False,
            motivo=reason,
        )

        return OfflineOperationResolutionResult(
            uuid_operacion=res_input.uuid_operacion,
            uuid_entidad=res_input.uuid_entidad or res_input.uuid_operacion,
            tipo_operacion=res_input.tipo_operacion,
            secuencia=seq_num,
            accion_aplicada=res_input.accion_resolucion,
            consentimiento_verificado=res_input.consentimiento_usuario,
            resuelta=False,
            confirmada=False,
            estado_resultado=result_status,
            estado_sincronizacion=sync_status,
            codigo_local=res_input.codigo_local,
            id_sucursal=branch_id,
            id_usuario=user.id_usuario,
            id_empresa=company_id,
            reintentable=(result_status == "REINTENTABLE"),
            conservar_en_cola=True,
            conflictos=conflicts or [],
            motivo=reason,
            mensaje=reason,
            fecha_resolucion=current_time,
            resumen_cu12=cu12_summary,
        )

