"""Servicio de orquestación transaccional para PK08 - CU13: Sincronizar operaciones pendientes de FashionStore."""

from datetime import datetime, timezone
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
from app.PK08.CU10_RegistrarReservaOffline.schemas import OfflineReservationSyncResponse
from app.PK08.CU10_RegistrarReservaOffline.service import (
    OfflineReservationError,
    OfflineReservationService,
)
from app.PK08.CU11_RegistrarVentaOffline.schemas import (
    OfflineConflictDetail,
    OfflineReservationTransitionResponse,
    OfflineSaleSyncResponse,
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
    OfflineQueueSyncRequest,
    OfflineQueueSyncResponse,
    OfflineSyncOperationInput,
    OfflineSyncOperationResult,
    OfflineSyncResultStatus,
    OfflineSyncServerStatus,
)
from app.schemas.auth import AuthenticatedUserData

logger = logging.getLogger(__name__)

ALLOWED_SYNC_ROLES: set[str] = {"CLIENTE", "CAJERO", "ENCARGADO_SUCURSAL"}
CLIENT_ONLY_TYPES: set[str] = {"RESERVA", "COMPRA"}
STAFF_ONLY_TYPES: set[str] = {"VENTA", "TRANSICION_RESERVA"}


class OfflineQueueSyncError(Exception):
    """Excepción de nivel de sesión, tenant o suscripción SaaS para CU13."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class OfflineQueueSyncService:
    """Sincroniza de forma ordenada, atómica e idempotente los lotes de operaciones pendientes desde Angular PWA."""

    def __init__(
        self,
        db: Session,
        *,
        repository: OfflineSyncQueueRepository | None = None,
        reservation_service: OfflineReservationService | None = None,
        sale_service: OfflineSaleService | None = None,
        saas_service: SaasPlanLimitsService | None = None,
    ) -> None:
        self.db = db
        self.repository = repository or OfflineSyncQueueRepository(db)
        self.saas_service = saas_service or SaasPlanLimitsService(db)
        self.reservation_service = reservation_service or OfflineReservationService(
            db, saas_service=self.saas_service
        )
        self.sale_service = sale_service or OfflineSaleService(
            db, saas_service=self.saas_service
        )

    def _validate_session_and_tenant(
        self,
        user: AuthenticatedUserData,
        requested_company_id: int | None = None,
    ) -> tuple[int, str]:
        """Valida rol permitido y aislamiento estricto multitenant desde el JWT."""
        role = (user.rol or "").strip().upper()
        if role not in ALLOWED_SYNC_ROLES:
            raise OfflineQueueSyncError(
                status_code=403,
                message=(
                    f"El rol '{user.rol}' no está autorizado para sincronizar colas de operaciones offline. "
                    "Se requiere rol CLIENTE, CAJERO o ENCARGADO_SUCURSAL."
                ),
            )
        if not user.id_empresa:
            raise OfflineQueueSyncError(
                status_code=403,
                message="El usuario autenticado no tiene una empresa asociada en su sesión.",
            )
        if requested_company_id is not None and requested_company_id != user.id_empresa:
            raise OfflineQueueSyncError(
                status_code=403,
                message="Acceso denegado: no puede sincronizar operaciones de otra empresa.",
            )
        return user.id_empresa, role

    def _validate_saas_offline(
        self, company_id: int, now: datetime | None = None
    ) -> None:
        """Verifica que la empresa tenga suscripción activa y funcionalidad OFFLINE habilitada."""
        try:
            if hasattr(self.saas_service, "validate_feature_enabled"):
                self.saas_service.validate_feature_enabled(
                    company_id, "OFFLINE", now=now
                )
            elif hasattr(self.saas_service, "check_feature_enabled"):
                self.saas_service.check_feature_enabled(company_id, "OFFLINE")
        except (NoActiveSubscriptionError, FeatureNotEnabledError) as err:
            raise OfflineQueueSyncError(status_code=403, message=str(err)) from err
        except Exception as err:
            raise OfflineQueueSyncError(
                status_code=403,
                message=str(err)
                or "La empresa no cuenta con funcionalidad OFFLINE habilitada.",
            ) from err

    def sync_pending_operations(
        self,
        user: AuthenticatedUserData,
        payload: OfflineQueueSyncRequest,
        *,
        requested_company_id: int | None = None,
        now: datetime | None = None,
    ) -> OfflineQueueSyncResponse:
        """Procesa secuencialmente cada operación de la cola con aislamiento transaccional individual."""
        company_id, role = self._validate_session_and_tenant(
            user, requested_company_id
        )
        current_time = now or datetime.now(timezone.utc).replace(tzinfo=None)
        self._validate_saas_offline(company_id, now=current_time)

        # Ordenar respetando secuencia explícita si existe, preservando el orden original de llegada
        indexed_ops = list(enumerate(payload.operaciones))
        indexed_ops.sort(
            key=lambda pair: (
                pair[1].secuencia if pair[1].secuencia is not None else pair[0],
                pair[0],
            )
        )

        results: list[OfflineSyncOperationResult] = []
        results_by_uuid: dict[str, OfflineSyncOperationResult] = {}
        code_links: dict[str, OfflineCodeLinkItem] = {}

        # Mapa de referencias locales de reservas -> (id_reserva_oficial, codigo_reserva_oficial)
        reservation_links: dict[str, tuple[int, str]] = {}
        # Mapa de operaciones fallidas en este mismo lote -> (estado_resultado, motivo)
        failed_ops: dict[str, tuple[OfflineSyncResultStatus, str]] = {}

        for idx, (_, op) in enumerate(indexed_ops, start=1):
            seq_num = op.secuencia if op.secuencia is not None else idx
            op_result = self._process_single_operation(
                user=user,
                role=role,
                company_id=company_id,
                op=op,
                seq_num=seq_num,
                current_time=current_time,
                reservation_links=reservation_links,
                failed_ops=failed_ops,
            )

            results.append(op_result)
            results_by_uuid[op_result.uuid_operacion] = op_result

            if op_result.confirmada and op_result.id_servidor and op_result.codigo_servidor:
                # Registrar vinculación de UUID y código provisional -> ID y código oficial de PostgreSQL
                for ref_key in {
                    op.uuid_operacion,
                    op.uuid_entidad,
                    op.codigo_local,
                }:
                    if ref_key:
                        code_links[ref_key] = OfflineCodeLinkItem(
                            referencia_local=ref_key,
                            tipo_operacion=op.tipo_operacion,
                            id_servidor=op_result.id_servidor,
                            codigo_servidor=op_result.codigo_servidor,
                        )
                        if op.tipo_operacion in ("RESERVA", "TRANSICION_RESERVA"):
                            reservation_links[ref_key] = (
                                op_result.id_servidor,
                                op_result.codigo_servidor,
                            )
            elif not op_result.confirmada:
                reason_text = op_result.motivo or op_result.mensaje
                extra_fail_keys: set[str | None] = {
                    op.uuid_operacion,
                    op.uuid_entidad,
                    op.codigo_local,
                    op_result.codigo_reserva_asociada,
                    f"res-id:{op_result.id_reserva_asociada}"
                    if op_result.id_reserva_asociada is not None
                    else None,
                }
                if op.transicion is not None:
                    extra_fail_keys.add(op.transicion.uuid_reserva_offline)
                    extra_fail_keys.add(op.transicion.codigo_reserva)
                    if op.transicion.id_reserva is not None:
                        extra_fail_keys.add(f"res-id:{op.transicion.id_reserva}")
                if op.reserva is not None:
                    extra_fail_keys.add(op.reserva.uuid_reserva_offline)
                for fail_key in extra_fail_keys:
                    if fail_key:
                        failed_ops[fail_key] = (
                            op_result.estado_resultado,
                            reason_text,
                        )

        confirmed_count = sum(
            1 for r in results if r.estado_resultado == "CONFIRMADA"
        )
        rejected_count = sum(
            1 for r in results if r.estado_resultado == "RECHAZADA"
        )
        conflict_count = sum(
            1 for r in results if r.estado_resultado == "EN_CONFLICTO"
        )
        retryable_count = sum(
            1 for r in results if r.estado_resultado == "REINTENTABLE"
        )
        all_ok = confirmed_count == len(results)

        return OfflineQueueSyncResponse(
            success=all_ok,
            empresa_id=company_id,
            id_usuario=user.id_usuario,
            rol=role,
            total_operaciones=len(results),
            confirmadas=confirmed_count,
            rechazadas=rejected_count,
            en_conflicto=conflict_count,
            reintentables=retryable_count,
            resultados=results,
            resultados_por_uuid=results_by_uuid,
            vinculaciones_codigos=code_links,
            fecha_sincronizacion=current_time,
            mensaje=(
                f"Sincronización completada: {confirmed_count} de {len(results)} operaciones confirmadas."
                if all_ok
                else (
                    f"Sincronización procesada parcialmente: {confirmed_count} confirmadas, "
                    f"{conflict_count} en conflicto, {rejected_count} rechazadas, {retryable_count} reintentables."
                )
            ),
        )

    def _process_single_operation(
        self,
        *,
        user: AuthenticatedUserData,
        role: str,
        company_id: int,
        op: OfflineSyncOperationInput,
        seq_num: int,
        current_time: datetime,
        reservation_links: dict[str, tuple[int, str]],
        failed_ops: dict[str, tuple[OfflineSyncResultStatus, str]],
    ) -> OfflineSyncOperationResult:
        """Ejecuta una operación individual en transacción aislada garantizando que un error no bloquee el resto del lote."""
        op_type = op.tipo_operacion

        # 1. Verificar dependencia explícita fallida en el mismo lote
        if op.depende_de_uuid and op.depende_de_uuid in failed_ops:
            parent_status, parent_reason = failed_ops[op.depende_de_uuid]
            dep_status: OfflineSyncResultStatus = (
                "REINTENTABLE" if parent_status == "REINTENTABLE" else "EN_CONFLICTO"
            )
            reason = (
                f"La operación previa dependiente ('{op.depende_de_uuid}') no fue confirmada "
                f"({parent_status}: {parent_reason})."
            )
            return self._build_failed_result(
                op=op,
                seq_num=seq_num,
                user=user,
                company_id=company_id,
                current_time=current_time,
                result_status=dep_status,
                reason=reason,
                conflicts=[
                    OfflineConflictDetail(
                        tipo_conflicto="RESERVA_ESTADO_INVALIDO",
                        valor_esperado="CONFIRMADA",
                        valor_actual_servidor=parent_status,
                        detalle=reason,
                    )
                ]
                if dep_status == "EN_CONFLICTO"
                else [],
            )

        # 2. Validar correspondencia entre tipo de operación y rol del actor autenticado
        if op_type in CLIENT_ONLY_TYPES and role != "CLIENTE":
            return self._build_failed_result(
                op=op,
                seq_num=seq_num,
                user=user,
                company_id=company_id,
                current_time=current_time,
                result_status="RECHAZADA",
                reason=(
                    f"El rol '{role}' no tiene permisos para sincronizar operaciones de tipo '{op_type}'. "
                    "Únicamente el CLIENTE puede sincronizar reservas y compras digitales."
                ),
            )

        if op_type in STAFF_ONLY_TYPES and role not in ("CAJERO", "ENCARGADO_SUCURSAL"):
            return self._build_failed_result(
                op=op,
                seq_num=seq_num,
                user=user,
                company_id=company_id,
                current_time=current_time,
                result_status="RECHAZADA",
                reason=(
                    f"El rol '{role}' no tiene permisos para sincronizar operaciones de tipo '{op_type}'. "
                    "Se requiere rol CAJERO o ENCARGADO_SUCURSAL."
                ),
            )

        try:
            if op_type == "RESERVA":
                return self._execute_reservation_sync(
                    user=user,
                    company_id=company_id,
                    op=op,
                    seq_num=seq_num,
                    current_time=current_time,
                )

            if op_type == "TRANSICION_RESERVA":
                return self._execute_transition_sync(
                    user=user,
                    company_id=company_id,
                    op=op,
                    seq_num=seq_num,
                    current_time=current_time,
                    reservation_links=reservation_links,
                    failed_ops=failed_ops,
                )

            if op_type in ("COMPRA", "VENTA"):
                return self._execute_sale_or_purchase_sync(
                    user=user,
                    company_id=company_id,
                    op=op,
                    seq_num=seq_num,
                    current_time=current_time,
                    reservation_links=reservation_links,
                    failed_ops=failed_ops,
                )

            return self._build_failed_result(
                op=op,
                seq_num=seq_num,
                user=user,
                company_id=company_id,
                current_time=current_time,
                result_status="RECHAZADA",
                reason=f"Tipo de operación no soportado: {op_type}",
            )

        except (OfflineReservationError, OfflineSaleError) as domain_err:
            self.db.rollback()
            # Errores 5xx se marcan como REINTENTABLE; errores 4xx como RECHAZADA
            is_retryable = getattr(domain_err, "status_code", 400) >= 500
            return self._build_failed_result(
                op=op,
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
                "Fallo transitorio de base de datos al sincronizar operación %s: %s",
                op.uuid_operacion,
                db_err,
            )
            return self._build_failed_result(
                op=op,
                seq_num=seq_num,
                user=user,
                company_id=company_id,
                current_time=current_time,
                result_status="REINTENTABLE",
                reason="Fallo transitorio de concurrencia o conexión a base de datos; seguro para reintentar.",
            )
        except Exception as exc:
            self.db.rollback()
            logger.exception(
                "Error inesperado procesando operación offline %s: %s",
                op.uuid_operacion,
                exc,
            )
            return self._build_failed_result(
                op=op,
                seq_num=seq_num,
                user=user,
                company_id=company_id,
                current_time=current_time,
                result_status="REINTENTABLE",
                reason="Error interno temporal al procesar la operación; seguro para reintentar.",
            )

    def _execute_reservation_sync(
        self,
        *,
        user: AuthenticatedUserData,
        company_id: int,
        op: OfflineSyncOperationInput,
        seq_num: int,
        current_time: datetime,
    ) -> OfflineSyncOperationResult:
        """Sincroniza una reserva offline del CLIENTE reutilizando OfflineReservationService (CU10)."""
        if op.reserva is None:
            return self._build_failed_result(
                op=op,
                seq_num=seq_num,
                user=user,
                company_id=company_id,
                current_time=current_time,
                result_status="RECHAZADA",
                reason="Faltan los datos de la reserva ('reserva') para sincronizar la operación RESERVA.",
            )

        res_resp: OfflineReservationSyncResponse = (
            self.reservation_service.sync_offline_reservation(
                user,
                op.reserva,
                requested_company_id=company_id,
                now=current_time,
            )
        )

        cu12_summary = OfflineOperationItemSummary(
            uuid_operacion=op.uuid_operacion,
            tipo_operacion="RESERVA",
            id_sucursal=res_resp.id_sucursal,
            sucursal_nombre=self.repository.get_branch_name(
                company_id, res_resp.id_sucursal
            ),
            id_usuario=res_resp.id_usuario,
            rol_actor="CLIENTE",
            id_cliente=res_resp.id_cliente,
            fecha_operacion_offline=op.reserva.fecha_reserva_offline
            or op.fecha_operacion_offline,
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
        if res_resp.estado_resultado in ("EN_CONFLICTO", "RECHAZADA") and (
            res_resp.motivo or res_resp.mensaje
        ):
            reason_lower = (res_resp.motivo or "").lower()
            if "stock" in reason_lower or "inventario" in reason_lower:
                conflict_type = "STOCK_INSUFICIENTE"
                allowed_actions = [
                    "AJUSTAR_CANTIDAD_STOCK",
                    "QUITAR_PRENDA",
                    "CAMBIAR_SUCURSAL",
                    "DESCARTAR_OPERACION",
                ]
                is_fixable = True
            elif "ya está reservada" in reason_lower:
                conflict_type = "HORARIO_NO_DISPONIBLE"
                allowed_actions = ["REPROGRAMAR_HORARIO", "DESCARTAR_OPERACION"]
                is_fixable = True
            elif (
                "horario" in reason_lower
                or "fecha programada" in reason_lower
                or "bloque" in reason_lower
                or "hora" in reason_lower
            ):
                conflict_type = "HORARIO_VENCIDO"
                allowed_actions = ["REPROGRAMAR_HORARIO", "DESCARTAR_OPERACION"]
                is_fixable = True
            elif "precio" in reason_lower:
                conflict_type = "PRECIO_MODIFICADO"
                allowed_actions = ["ACEPTAR_PRECIO_SERVIDOR", "DESCARTAR_OPERACION"]
                is_fixable = True
            elif "concurrencia" in reason_lower:
                conflict_type = "CONCURRENCIA"
                allowed_actions = ["REINTENTAR_SIN_CAMBIOS"]
                is_fixable = True
            else:
                conflict_type = "REGLA_NEGOCIO"
                allowed_actions = ["DESCARTAR_OPERACION"]
                is_fixable = False

            res_conflicts.append(
                OfflineConflictDetail(
                    tipo_conflicto=conflict_type,
                    corregible=is_fixable,
                    requiere_consentimiento=conflict_type != "CONCURRENCIA",
                    acciones_permitidas=allowed_actions,
                    detalle=res_resp.motivo or res_resp.mensaje,
                )
            )

        return OfflineSyncOperationResult(
            uuid_operacion=op.uuid_operacion,
            uuid_entidad=res_resp.uuid_reserva_offline,
            tipo_operacion="RESERVA",
            secuencia=seq_num,
            confirmada=res_resp.confirmada,
            estado_resultado=res_resp.estado_resultado,
            estado_sincronizacion=res_resp.estado_sincronizacion,
            id_servidor=res_resp.id_reserva,
            codigo_servidor=res_resp.codigo_reserva,
            codigo_local=op.codigo_local,
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

    def _resolve_linked_reservation(
        self,
        *,
        company_id: int,
        uuid_offline: str | None,
        code: str | None,
        reservation_id: int | None,
        reservation_links: dict[str, tuple[int, str]],
    ) -> tuple[int | None, str | None]:
        """Vincula UUID o código local de reserva con su (id_reserva, codigo_oficial) en PostgreSQL."""
        for key in (uuid_offline, code):
            if key and key in reservation_links:
                return reservation_links[key]

        resolved = self.repository.resolve_reservation_reference(
            company_id,
            uuid_offline=uuid_offline,
            code=code,
            reservation_id=reservation_id,
        )
        if resolved is not None:
            return resolved

        # Si el ID enviado es un hash sintético local de Angular (>= 70000000), limpiarlo para que
        # el repositorio busque por código o UUID en lugar de fallar por ID inexistente
        clean_id = (
            None
            if (reservation_id is not None and reservation_id >= 70000000)
            else reservation_id
        )
        return (clean_id, code)

    def _execute_transition_sync(
        self,
        *,
        user: AuthenticatedUserData,
        company_id: int,
        op: OfflineSyncOperationInput,
        seq_num: int,
        current_time: datetime,
        reservation_links: dict[str, tuple[int, str]],
        failed_ops: dict[str, tuple[OfflineSyncResultStatus, str]],
    ) -> OfflineSyncOperationResult:
        """Sincroniza una transición de reserva del CAJERO (PENDIENTE -> CONFIRMADA -> ATENDIDA)."""
        if op.transicion is None:
            return self._build_failed_result(
                op=op,
                seq_num=seq_num,
                user=user,
                company_id=company_id,
                current_time=current_time,
                result_status="RECHAZADA",
                reason="Faltan los datos de transición ('transicion') para sincronizar TRANSICION_RESERVA.",
            )

        trans_req = op.transicion.model_copy(deep=True)

        # Verificar si la reserva referenciada falló previamente en este mismo lote
        for ref_candidate in (
            trans_req.uuid_reserva_offline,
            trans_req.codigo_reserva,
            op.uuid_entidad,
            f"res-id:{trans_req.id_reserva}" if trans_req.id_reserva is not None else None,
        ):
            if ref_candidate and ref_candidate in failed_ops:
                p_status, p_reason = failed_ops[ref_candidate]
                reason = (
                    f"No se puede aplicar la transición '{trans_req.accion}' porque una operación previa "
                    f"sobre la reserva '{ref_candidate}' falló ({p_status}: {p_reason})."
                )
                return self._build_failed_result(
                    op=op,
                    seq_num=seq_num,
                    user=user,
                    company_id=company_id,
                    current_time=current_time,
                    result_status="REINTENTABLE"
                    if p_status == "REINTENTABLE"
                    else "EN_CONFLICTO",
                    reason=reason,
                    conflicts=[
                        OfflineConflictDetail(
                            tipo_conflicto="RESERVA_ESTADO_INVALIDO",
                            valor_esperado="PENDIENTE"
                            if trans_req.accion in ("CONFIRM", "CONFIRMAR")
                            else "CONFIRMADA",
                            valor_actual_servidor=p_status,
                            detalle=reason,
                        )
                    ],
                )

        resolved_id, resolved_code = self._resolve_linked_reservation(
            company_id=company_id,
            uuid_offline=trans_req.uuid_reserva_offline or op.uuid_entidad,
            code=trans_req.codigo_reserva or op.codigo_local,
            reservation_id=trans_req.id_reserva,
            reservation_links=reservation_links,
        )
        if resolved_id is not None:
            trans_req.id_reserva = resolved_id
        else:
            trans_req.id_reserva = None
        if resolved_code is not None:
            trans_req.codigo_reserva = resolved_code

        trans_resp: OfflineReservationTransitionResponse = (
            self.sale_service.sync_reservation_transition(
                user,
                trans_req,
                requested_company_id=company_id,
                now=current_time,
            )
        )

        cu12_summary = OfflineOperationItemSummary(
            uuid_operacion=op.uuid_operacion,
            tipo_operacion="TRANSICION_RESERVA",
            id_sucursal=trans_resp.id_sucursal or 1,
            sucursal_nombre=self.repository.get_branch_name(
                company_id, trans_resp.id_sucursal
            ),
            id_usuario=trans_resp.id_usuario,
            rol_actor=user.rol.upper(),
            id_empleado=trans_resp.id_empleado_atencion,
            fecha_operacion_offline=trans_req.fecha_operacion_offline
            or op.fecha_operacion_offline,
            fecha_sincronizacion=trans_resp.fecha_sincronizacion,
            estado_local=trans_resp.accion_aplicada,
            estado_sincronizacion=trans_resp.estado_sincronizacion,
            confirmada=trans_resp.confirmada,
            id_servidor=trans_resp.id_reserva,
            codigo_servidor=trans_resp.codigo_reserva,
            estado_servidor=trans_resp.estado_reserva,
            motivo=trans_resp.motivo,
        )

        return OfflineSyncOperationResult(
            uuid_operacion=op.uuid_operacion,
            uuid_entidad=op.uuid_entidad or trans_req.uuid_reserva_offline,
            tipo_operacion="TRANSICION_RESERVA",
            secuencia=seq_num,
            confirmada=trans_resp.confirmada,
            estado_resultado=trans_resp.estado_resultado,
            estado_sincronizacion=trans_resp.estado_sincronizacion,
            id_servidor=trans_resp.id_reserva,
            codigo_servidor=trans_resp.codigo_reserva,
            codigo_local=op.codigo_local or trans_req.codigo_reserva,
            estado_entidad_servidor=trans_resp.estado_reserva,
            id_reserva_asociada=trans_resp.id_reserva,
            codigo_reserva_asociada=trans_resp.codigo_reserva,
            id_sucursal=trans_resp.id_sucursal,
            id_empleado=trans_resp.id_empleado_atencion,
            id_usuario=trans_resp.id_usuario,
            id_empresa=trans_resp.id_empresa,
            reintentable=False,
            conservar_en_cola=trans_resp.conservar_operacion_pendiente,
            conflictos=trans_resp.conflictos,
            motivo=trans_resp.motivo,
            mensaje=trans_resp.mensaje,
            fecha_sincronizacion=trans_resp.fecha_sincronizacion,
            resumen_cu12=cu12_summary,
        )

    def _execute_sale_or_purchase_sync(
        self,
        *,
        user: AuthenticatedUserData,
        company_id: int,
        op: OfflineSyncOperationInput,
        seq_num: int,
        current_time: datetime,
        reservation_links: dict[str, tuple[int, str]],
        failed_ops: dict[str, tuple[OfflineSyncResultStatus, str]],
    ) -> OfflineSyncOperationResult:
        """Sincroniza una compra digital del CLIENTE o una venta POS del CAJERO (directa o por reserva)."""
        is_digital = op.tipo_operacion == "COMPRA"
        raw_req = op.compra if is_digital else (op.venta or op.compra)

        if raw_req is None:
            return self._build_failed_result(
                op=op,
                seq_num=seq_num,
                user=user,
                company_id=company_id,
                current_time=current_time,
                result_status="RECHAZADA",
                reason=f"Faltan los datos comerciales para sincronizar la operación {op.tipo_operacion}.",
            )

        sale_req = raw_req.model_copy(deep=True)
        forced_channel = "DIGITAL" if is_digital else "PRESENCIAL"
        sale_req.canal = forced_channel

        # Si es una venta POS asociada a una reserva, verificar dependencias y vincular ID/código oficial
        has_reservation_ref = bool(
            sale_req.id_reserva is not None
            or sale_req.codigo_reserva
            or sale_req.uuid_reserva_offline
        )
        if has_reservation_ref:
            for ref_candidate in (
                sale_req.uuid_reserva_offline,
                sale_req.codigo_reserva,
                f"res-id:{sale_req.id_reserva}" if sale_req.id_reserva is not None else None,
            ):
                if ref_candidate and ref_candidate in failed_ops:
                    p_status, p_reason = failed_ops[ref_candidate]
                    reason = (
                        f"No se puede registrar la venta por reserva porque la atención previa de la reserva "
                        f"'{ref_candidate}' no se completó ({p_status}: {p_reason})."
                    )
                    return self._build_failed_result(
                        op=op,
                        seq_num=seq_num,
                        user=user,
                        company_id=company_id,
                        current_time=current_time,
                        result_status="REINTENTABLE"
                        if p_status == "REINTENTABLE"
                        else "EN_CONFLICTO",
                        reason=reason,
                        conflicts=[
                            OfflineConflictDetail(
                                tipo_conflicto="RESERVA_NO_ATENDIDA",
                                valor_esperado="ATENDIDA",
                                valor_actual_servidor=p_status,
                                detalle=reason,
                            )
                        ],
                    )

            resolved_id, resolved_code = self._resolve_linked_reservation(
                company_id=company_id,
                uuid_offline=sale_req.uuid_reserva_offline,
                code=sale_req.codigo_reserva,
                reservation_id=sale_req.id_reserva,
                reservation_links=reservation_links,
            )
            sale_req.id_reserva = resolved_id
            if resolved_code is not None:
                sale_req.codigo_reserva = resolved_code

        sale_resp: OfflineSaleSyncResponse = self.sale_service.sync_offline_sale(
            user,
            sale_req,
            requested_company_id=company_id,
            forced_channel=forced_channel,
            now=current_time,
        )

        cu12_summary = OfflineOperationItemSummary(
            uuid_operacion=op.uuid_operacion,
            tipo_operacion=op.tipo_operacion,
            id_sucursal=sale_resp.id_sucursal,
            sucursal_nombre=self.repository.get_branch_name(
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

        return OfflineSyncOperationResult(
            uuid_operacion=op.uuid_operacion,
            uuid_entidad=sale_resp.uuid_venta_offline,
            tipo_operacion=op.tipo_operacion,
            secuencia=seq_num,
            confirmada=sale_resp.confirmada,
            estado_resultado=sale_resp.estado_resultado,
            estado_sincronizacion=sale_resp.estado_sincronizacion,
            id_servidor=sale_resp.id_venta,
            codigo_servidor=sale_resp.numero_venta,
            codigo_local=op.codigo_local or getattr(sale_req, "numero_venta_local", None),
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

    def _build_failed_result(
        self,
        *,
        op: OfflineSyncOperationInput,
        seq_num: int,
        user: AuthenticatedUserData,
        company_id: int,
        current_time: datetime,
        result_status: OfflineSyncResultStatus,
        reason: str,
        conflicts: list[OfflineConflictDetail] | None = None,
    ) -> OfflineSyncOperationResult:
        """Construye un resultado individual de rechazo, conflicto o reintento sin abortar el lote."""
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
        if op.reserva and op.reserva.id_sucursal:
            branch_id = op.reserva.id_sucursal
        elif op.compra and op.compra.id_sucursal:
            branch_id = op.compra.id_sucursal
        elif op.venta and op.venta.id_sucursal:
            branch_id = op.venta.id_sucursal
        elif op.transicion and op.transicion.id_sucursal:
            branch_id = op.transicion.id_sucursal

        cu12_summary = OfflineOperationItemSummary(
            uuid_operacion=op.uuid_operacion,
            tipo_operacion=op.tipo_operacion,
            id_sucursal=branch_id,
            sucursal_nombre=self.repository.get_branch_name(company_id, branch_id),
            id_usuario=user.id_usuario,
            rol_actor=(user.rol or "").upper(),
            fecha_operacion_offline=op.fecha_operacion_offline,
            fecha_sincronizacion=current_time,
            estado_local="REGISTRADA_LOCAL",
            estado_sincronizacion=sync_status,
            confirmada=False,
            motivo=reason,
        )

        return OfflineSyncOperationResult(
            uuid_operacion=op.uuid_operacion,
            uuid_entidad=op.uuid_entidad or op.uuid_operacion,
            tipo_operacion=op.tipo_operacion,
            secuencia=seq_num,
            confirmada=False,
            estado_resultado=result_status,
            estado_sincronizacion=sync_status,
            id_servidor=None,
            codigo_servidor=None,
            codigo_local=op.codigo_local,
            estado_entidad_servidor=None,
            id_sucursal=branch_id,
            id_usuario=user.id_usuario,
            id_empresa=company_id,
            reintentable=(result_status == "REINTENTABLE"),
            conservar_en_cola=True,
            conflictos=conflicts or [],
            motivo=reason,
            mensaje=reason,
            fecha_sincronizacion=current_time,
            resumen_cu12=cu12_summary,
        )
