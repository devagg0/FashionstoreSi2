"""Servicio de negocio para PK08 - CU12: Consultar operaciones locales offline y su estado en el servidor central."""

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal
from uuid import NAMESPACE_OID, UUID, uuid5

from sqlalchemy.orm import Session

from app.PK07.CU07_ConsultarPlanLimites.service import SaasPlanLimitsService
from app.PK08.CU12_ConsultarOperacionesPendientes.repository import (
    OfflineOperationStatusRepository,
)
from app.PK08.CU12_ConsultarOperacionesPendientes.schemas import (
    OfflineBatchStatusQueryResponse,
    OfflineOperationItemSummary,
    OfflineOperationsListResponse,
    OfflineOperationStatusResponse,
    OfflineOperationType,
    OfflineSyncStatus,
)
from app.schemas.auth import AuthenticatedUserData
from app.services.admin_user_service import EMPLOYEE_ROLE_NAMES


class OfflineOperationError(Exception):
    """Excepción de negocio para operaciones offline de CU12."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(message)


class OfflineOperationStatusService:
    """Orquesta la consulta de solo lectura de estados de operaciones offline en PostgreSQL."""

    def __init__(
        self,
        db: Session,
        repository: OfflineOperationStatusRepository | None = None,
        saas_service: SaasPlanLimitsService | None = None,
    ) -> None:
        self.db = db
        self.repository = repository or OfflineOperationStatusRepository(db)
        self.saas_service = saas_service or SaasPlanLimitsService(db)

    @staticmethod
    def _normalize_uuid(company_id: int, raw_uuid: str) -> UUID:
        cleaned = raw_uuid.strip()
        try:
            return UUID(cleaned)
        except ValueError:
            return uuid5(NAMESPACE_OID, f"fashionstore:{company_id}:{cleaned}")

    def _resolve_company_id(
        self, user: AuthenticatedUserData, requested_company_id: int | None
    ) -> int:
        user_company_id = user.id_empresa
        role = user.rol.upper()
        if role == "SUPERADMIN":
            if not requested_company_id:
                raise OfflineOperationError(
                    status_code=400,
                    message="SUPERADMIN debe proporcionar empresa_id para consultar operaciones offline.",
                )
            return requested_company_id

        if not user_company_id:
            raise OfflineOperationError(
                status_code=403,
                message="Usuario sin empresa asignada.",
            )

        if requested_company_id and requested_company_id != user_company_id:
            raise OfflineOperationError(
                status_code=403,
                message="Acceso denegado a datos de otra empresa.",
            )
        return user_company_id

    def _validate_saas_offline_feature(self, company_id: int) -> None:
        try:
            if hasattr(self.saas_service, "check_feature_enabled"):
                self.saas_service.check_feature_enabled(company_id, "OFFLINE")
            elif hasattr(self.saas_service, "validate_feature_enabled"):
                self.saas_service.validate_feature_enabled(company_id, "OFFLINE")
        except Exception as exc:
            raise OfflineOperationError(
                status_code=403,
                message=str(exc) or "La empresa no cuenta con funcionalidad OFFLINE activa en su suscripción.",
            ) from exc

    def get_operation_status(
        self,
        user: AuthenticatedUserData,
        uuid_str: str,
        *,
        requested_company_id: int | None = None,
    ) -> OfflineOperationStatusResponse:
        """Consulta el estado en PostgreSQL de una operación offline identificada por su UUID."""
        company_id = self._resolve_company_id(user, requested_company_id)
        self._validate_saas_offline_feature(company_id)

        clean_uuid = uuid_str.strip()
        summary = self._resolve_single_operation(user, company_id, clean_uuid)

        return OfflineOperationStatusResponse(
            success=True,
            data=summary,
            mensaje="Estado de operación consultado correctamente.",
        )

    def query_batch_status(
        self,
        user: AuthenticatedUserData,
        uuids: list[str],
        *,
        requested_company_id: int | None = None,
    ) -> OfflineBatchStatusQueryResponse:
        """Verifica en lote el estado en PostgreSQL para una lista de UUIDs offline."""
        company_id = self._resolve_company_id(user, requested_company_id)
        self._validate_saas_offline_feature(company_id)

        results: dict[str, OfflineOperationItemSummary] = {}
        synced_count = 0

        for raw_uuid in uuids:
            clean = raw_uuid.strip()
            if not clean:
                continue
            try:
                op_summary = self._resolve_single_operation(user, company_id, clean)
                results[clean] = op_summary
                if op_summary.confirmada or op_summary.estado_sincronizacion in ("SINCRONIZADA", "CONFLICTO", "RECHAZADA"):
                    synced_count += 1
            except OfflineOperationError:
                # Operación de otra empresa o no autorizada para el usuario
                continue

        return OfflineBatchStatusQueryResponse(
            success=True,
            operaciones=results,
            total_consultados=len(results),
            total_sincronizados=synced_count,
            mensaje="Verificación de estados completada correctamente.",
        )

    def list_synced_operations(
        self,
        user: AuthenticatedUserData,
        *,
        branch_id: int | None = None,
        requested_company_id: int | None = None,
        limit: int = 50,
    ) -> OfflineOperationsListResponse:
        """Lista las operaciones offline sincronizadas en el servidor para el actor o sucursal."""
        company_id = self._resolve_company_id(user, requested_company_id)
        self._validate_saas_offline_feature(company_id)

        role = user.rol.upper()
        summaries: list[OfflineOperationItemSummary] = []

        if role == "CLIENTE":
            # Reservas sincronizadas del cliente
            sync_reservas = self.repository.list_synced_reservations_for_user(
                company_id, user.id_usuario, limit=limit
            )
            for sr in sync_reservas:
                summaries.append(self._build_reservation_summary(company_id, sr))

            # Compras digitales sincronizadas del cliente
            sales = self.repository.list_synced_sales_for_user(
                company_id, user.id_usuario, limit=limit
            )
            for sale in sales:
                payment = self.repository.get_payment_for_sale(company_id, sale.id_venta)
                summaries.append(self._build_sale_summary(company_id, sale, payment))

        elif role in EMPLOYEE_ROLE_NAMES:
            employee = self.repository.get_employee_by_user(company_id, user.id_usuario)
            if not employee:
                raise OfflineOperationError(status_code=403, message="Perfil de empleado no encontrado.")

            target_branch = branch_id
            if target_branch:
                assignment = self.repository.get_employee_branch_assignment(
                    company_id, employee.id_empleado, target_branch
                )
                if not assignment or not getattr(assignment, "estado", True):
                    raise OfflineOperationError(
                        status_code=403,
                        message="El empleado no tiene asignación activa en la sucursal indicada.",
                    )
            else:
                target_branch = getattr(employee, "id_sucursal", None)

            if target_branch:
                # Reservas sincronizadas en la sucursal
                sync_reservas = self.repository.list_synced_reservations_for_branch(
                    company_id, target_branch, limit=limit
                )
                for sr in sync_reservas:
                    summaries.append(self._build_reservation_summary(company_id, sr))

                # Ventas sincronizadas en la sucursal
                sales = self.repository.list_synced_sales_for_branch(
                    company_id, target_branch, limit=limit
                )
                for sale in sales:
                    payment = self.repository.get_payment_for_sale(company_id, sale.id_venta)
                    summaries.append(self._build_sale_summary(company_id, sale, payment))
        else:
            # SUPERADMIN o ADMINISTRADOR: lista general
            target_branch = branch_id
            if target_branch:
                sync_reservas = self.repository.list_synced_reservations_for_branch(
                    company_id, target_branch, limit=limit
                )
                sales = self.repository.list_synced_sales_for_branch(
                    company_id, target_branch, limit=limit
                )
            else:
                sync_reservas = self.repository.list_synced_reservations_for_user(
                    company_id, user.id_usuario, limit=limit
                )
                sales = self.repository.list_synced_sales_for_user(
                    company_id, user.id_usuario, limit=limit
                )

            for sr in sync_reservas:
                summaries.append(self._build_reservation_summary(company_id, sr))
            for sale in sales:
                payment = self.repository.get_payment_for_sale(company_id, sale.id_venta)
                summaries.append(self._build_sale_summary(company_id, sale, payment))

        return OfflineOperationsListResponse(
            success=True,
            data=summaries[:limit],
            total=len(summaries),
            empresa_id=company_id,
            mensaje="Operaciones offline consultadas correctamente.",
        )

    def _resolve_single_operation(
        self,
        user: AuthenticatedUserData,
        company_id: int,
        uuid_str: str,
    ) -> OfflineOperationItemSummary:
        """Determina el estado en PostgreSQL de una operación por su UUID."""
        role = user.rol.upper()

        # 1. Intentar buscar en sincronizaciones de reservas (t_reserva_offline_sync)
        sync_reserva = self.repository.get_reservation_sync(company_id, uuid_str)
        if sync_reserva is not None:
            # Control de permisos por rol
            if role == "CLIENTE" and sync_reserva.id_usuario != user.id_usuario:
                raise OfflineOperationError(
                    status_code=403,
                    message="Acceso denegado: la reserva offline pertenece a otro cliente.",
                )
            return self._build_reservation_summary(company_id, sync_reserva)

        # 2. Intentar buscar en ventas o compras por clave de idempotencia o número determinístico
        uuid_obj = self._normalize_uuid(company_id, uuid_str)
        sale_digital = f"DIG-{uuid_obj.hex.upper()}"
        sale_pos = f"VTA-{uuid_obj.hex.upper()}"

        payment = self.repository.get_payment_by_key(company_id, uuid_obj)
        sale: Any = None
        if payment is not None:
            sale = self.repository.get_sale(company_id, payment.id_venta)

        if sale is None:
            sale = self.repository.get_sale_by_number(company_id, sale_digital)
        if sale is None:
            sale = self.repository.get_sale_by_number(company_id, sale_pos)

        if sale is not None:
            # Control de permisos por rol
            if role == "CLIENTE":
                sale_user_id = getattr(sale, "id_usuario", None)
                if sale_user_id is not None and sale_user_id != user.id_usuario:
                    raise OfflineOperationError(
                        status_code=403,
                        message="Acceso denegado: la compra offline pertenece a otro cliente.",
                    )
                if sale_user_id is None and hasattr(self.repository, "get_client_by_user"):
                    client_obj = self.repository.get_client_by_user(company_id, user.id_usuario)
                    if (
                        client_obj is not None
                        and getattr(sale, "id_cliente", None) is not None
                        and getattr(sale, "id_cliente", None) != getattr(client_obj, "id_cliente", None)
                    ):
                        raise OfflineOperationError(
                            status_code=403,
                            message="Acceso denegado: la compra offline pertenece a otro cliente.",
                        )
            if payment is None:
                payment = self.repository.get_payment_for_sale(company_id, sale.id_venta)
            return self._build_sale_summary(
                company_id, sale, payment, client_uuid=uuid_str, fallback_user_id=user.id_usuario
            )

        # 3. Intentar verificar si corresponde a una transición (ej. trans-confirm-... o trans-attend-...)
        if uuid_str.startswith("trans-"):
            summary_trans = self._resolve_transition_operation(user, company_id, uuid_str)
            if summary_trans is not None:
                return summary_trans

        # 4. No encontrada en el servidor central -> sigue pendiente de sincronización en el cliente local
        branch = self.repository.get_branch(company_id, 1)
        inferred_type: OfflineOperationType = (
            "RESERVA"
            if uuid_str.startswith("RSV-") or "res" in uuid_str.lower()
            else ("TRANSICION_RESERVA" if uuid_str.startswith("trans-") else "VENTA")
        )

        return OfflineOperationItemSummary(
            uuid_operacion=uuid_str,
            tipo_operacion=inferred_type,
            id_sucursal=1,
            sucursal_nombre=getattr(branch, "nombre", "Sucursal Central"),
            id_usuario=user.id_usuario,
            rol_actor=role,
            estado_local="REGISTRADA_LOCAL",
            estado_sincronizacion="PENDIENTE_SINCRONIZACION",
            confirmada=False,
            mensaje="Operación no sincronizada en el servidor central (pendiente en almacenamiento local).",
        )

    def _resolve_transition_operation(
        self,
        user: AuthenticatedUserData,
        company_id: int,
        uuid_str: str,
    ) -> OfflineOperationItemSummary | None:
        """Verifica si la reserva referenciada en una transición ya alcanzó el estado deseado en el servidor."""
        parts = uuid_str.split("-")
        action = parts[1].upper() if len(parts) > 1 else "UNKNOWN"
        target_state = "CONFIRMADA" if action in ("CONFIRM", "CONFIRMAR") else ("ATENDIDA" if action in ("ATTEND", "ATENDER") else None)

        if not target_state:
            return None

        # El sufijo del UUID suele contener el código o UUID de la reserva
        possible_code = "-".join(parts[2:5]) if len(parts) >= 5 else (parts[2] if len(parts) > 2 else "")
        reservation = None
        if possible_code:
            reservation = self.repository.get_reservation_by_code(company_id, possible_code)
            if reservation is None:
                sync_r = self.repository.get_reservation_sync(company_id, possible_code)
                if sync_r and sync_r.id_reserva:
                    reservation = self.repository.get_reservation(company_id, sync_r.id_reserva)

        if reservation is not None:
            branch = self.repository.get_branch(company_id, reservation.id_sucursal)
            is_synced = reservation.estado == target_state
            return OfflineOperationItemSummary(
                uuid_operacion=uuid_str,
                tipo_operacion="TRANSICION_RESERVA",
                id_sucursal=reservation.id_sucursal,
                sucursal_nombre=getattr(branch, "nombre", f"Sucursal #{reservation.id_sucursal}"),
                id_usuario=user.id_usuario,
                rol_actor=user.rol.upper(),
                id_cliente=reservation.id_cliente,
                estado_local=target_state,
                estado_sincronizacion="SINCRONIZADA" if is_synced else "PENDIENTE_SINCRONIZACION",
                confirmada=is_synced,
                id_servidor=reservation.id_reserva,
                codigo_servidor=getattr(reservation, "codigo", None) or getattr(reservation, "codigo_reserva", None),
                estado_servidor=reservation.estado,
                motivo=None if is_synced else f"La reserva aún se encuentra en estado '{reservation.estado}' en el servidor.",
            )
        return None

    def _build_reservation_summary(
        self,
        company_id: int,
        sr: Any,
    ) -> OfflineOperationItemSummary:
        """Construye el resumen de una reserva offline persistida en PostgreSQL."""
        branch = self.repository.get_branch(company_id, sr.id_sucursal)
        reservation = (
            self.repository.get_reservation(company_id, sr.id_reserva)
            if getattr(sr, "id_reserva", None)
            else None
        )

        detalles_list: list[dict[str, Any]] = []
        if getattr(sr, "detalles_json", None):
            try:
                parsed = json.loads(sr.detalles_json)
                if isinstance(parsed, list):
                    detalles_list = parsed
            except Exception:
                pass

        if not detalles_list and reservation:
            res_details = self.repository.get_reservation_details(company_id, reservation.id_reserva)
            for d, v, p in res_details:
                detalles_list.append({
                    "id_variante_producto": d.id_variante_producto,
                    "cantidad": d.cantidad,
                    "precio": float(getattr(d, "precio_unitario", 0) or 0),
                    "producto": getattr(p, "nombre", f"Prenda #{d.id_variante_producto}"),
                    "sku": getattr(v, "sku", ""),
                })

        is_confirmed = sr.estado_sincronizacion == "SINCRONIZADA"
        sync_status: OfflineSyncStatus = (
            "SINCRONIZADA"
            if sr.estado_sincronizacion == "SINCRONIZADA"
            else ("CONFLICTO" if sr.estado_sincronizacion == "CONFLICTO" else "RECHAZADA")
        )

        total_val = None
        if reservation and getattr(reservation, "total_referencial", None):
            total_val = Decimal(str(reservation.total_referencial))

        return OfflineOperationItemSummary(
            uuid_operacion=sr.uuid_reserva_offline,
            tipo_operacion="RESERVA",
            id_sucursal=sr.id_sucursal,
            sucursal_nombre=getattr(branch, "nombre", f"Sucursal #{sr.id_sucursal}"),
            id_usuario=sr.id_usuario,
            rol_actor="CLIENTE",
            id_cliente=sr.id_cliente,
            fecha_operacion_offline=sr.fecha_reserva_offline,
            fecha_sincronizacion=sr.created_at,
            estado_local="PENDIENTE",
            estado_sincronizacion=sync_status,
            confirmada=is_confirmed,
            id_servidor=sr.id_reserva,
            codigo_servidor=sr.codigo_reserva,
            estado_servidor=getattr(reservation, "estado", sr.estado_sincronizacion),
            monto_total=total_val,
            motivo=sr.motivo,
            detalles_resumen=detalles_list or None,
        )

    def _build_sale_summary(
        self,
        company_id: int,
        sale: Any,
        payment: Any | None,
        client_uuid: str | None = None,
        fallback_user_id: int | None = None,
    ) -> OfflineOperationItemSummary:
        """Construye el resumen de una venta presencial o compra digital persistida en PostgreSQL."""
        branch = self.repository.get_branch(company_id, sale.id_sucursal)
        channel = getattr(sale, "canal", None) or ("DIGITAL" if (sale.numero_venta or "").startswith("DIG-") else "PRESENCIAL")
        op_type: OfflineOperationType = "COMPRA" if channel == "DIGITAL" else "VENTA"
        actor_role = "CLIENTE" if channel == "DIGITAL" else "CAJERO"

        detalles_list: list[dict[str, Any]] = []
        sale_details = self.repository.get_sale_details(company_id, sale.id_venta)
        for sd, v, p in sale_details:
            sub_val = getattr(sd, "subtotal_linea", None)
            if sub_val is None:
                sub_val = getattr(sd, "subtotal", 0)
            detalles_list.append({
                "id_variante_producto": sd.id_variante_producto,
                "cantidad": sd.cantidad,
                "precio_unitario": float(sd.precio_unitario or 0),
                "subtotal": float(sub_val or 0),
                "producto": getattr(p, "nombre", f"Prenda #{sd.id_variante_producto}"),
                "sku": getattr(v, "sku", ""),
            })

        uuid_val = client_uuid or (
            str(payment.clave_idempotencia)
            if payment and payment.clave_idempotencia
            else sale.numero_venta
        )
        medio_val = getattr(payment, "medio", None) or getattr(payment, "medio_pago", None)
        user_id_val = getattr(sale, "id_usuario", None) or fallback_user_id or 1

        return OfflineOperationItemSummary(
            uuid_operacion=uuid_val,
            tipo_operacion=op_type,
            id_sucursal=sale.id_sucursal,
            sucursal_nombre=getattr(branch, "nombre", f"Sucursal #{sale.id_sucursal}"),
            id_usuario=user_id_val,
            rol_actor=actor_role,
            id_cliente=sale.id_cliente,
            id_empleado=getattr(sale, "id_empleado", None),
            fecha_operacion_offline=getattr(sale, "fecha_venta", None) or getattr(sale, "created_at", None),
            fecha_sincronizacion=getattr(sale, "created_at", None),
            estado_local="COMPLETADA" if sale.estado == "COMPLETADA" else "PENDIENTE_VALIDACION",
            estado_sincronizacion="SINCRONIZADA",
            confirmada=True,
            id_servidor=sale.id_venta,
            codigo_servidor=sale.numero_venta,
            estado_servidor=sale.estado,
            monto_total=Decimal(str(sale.total or 0)),
            medio_pago=medio_val,
            pago_simulado=medio_val in ("QR", "TARJETA"),
            detalles_resumen=detalles_list or None,
        )

