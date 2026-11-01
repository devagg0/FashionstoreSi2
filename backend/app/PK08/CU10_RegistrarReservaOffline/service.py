"""Lógica de negocio y orquestación transaccional para PK08 - CU10: Registrar reserva de prendas offline."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import logging
import secrets
from typing import Any

from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.PK07.CU07_ConsultarPlanLimites.service import (
    FeatureNotEnabledError,
    NoActiveSubscriptionError,
    SaasPlanLimitsService,
)
from app.PK08.CU10_RegistrarReservaOffline.repository import OfflineReservationRepository
from app.PK08.CU10_RegistrarReservaOffline.schemas import (
    OfflineReservationSyncRequest,
    OfflineReservationSyncResponse,
)
from app.schemas.auth import AuthenticatedUserData

logger = logging.getLogger(__name__)

ALLOWED_OFFLINE_RESERVATION_ROLES: set[str] = {
    "SUPERADMIN",
    "ADMINISTRADOR",
    "ADMIN",
    "CAJERO",
    "ENCARGADO_SUCURSAL",
}


class OfflineReservationError(Exception):
    """Excepción base para errores de CU10."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class OfflineReservationService:
    """Gestiona la sincronización idempotente, validación de stock y persistencia atómica de reservas offline."""

    def __init__(
        self,
        db: Session,
        repository: OfflineReservationRepository | None = None,
        saas_service: SaasPlanLimitsService | None = None,
    ) -> None:
        self.db = db
        self.repository = repository or OfflineReservationRepository(db)
        self.saas_service = saas_service or SaasPlanLimitsService(db)

    def _validate_role(self, user: AuthenticatedUserData) -> str:
        role = user.rol.upper()
        if role not in ALLOWED_OFFLINE_RESERVATION_ROLES:
            raise OfflineReservationError(
                status_code=403,
                message=f"El rol '{user.rol}' no tiene permisos para sincronizar reservas offline.",
            )
        return role

    def _validate_saas(self, company_id: int, now: datetime | None = None) -> Any:
        try:
            return self.saas_service.validate_feature_enabled(
                company_id, "OFFLINE", now=now
            )
        except (NoActiveSubscriptionError, FeatureNotEnabledError) as err:
            raise OfflineReservationError(status_code=403, message=str(err)) from err

    def _resolve_company_id(
        self, user: AuthenticatedUserData, requested_company_id: int | None
    ) -> int:
        role = user.rol.upper()
        if role == "SUPERADMIN":
            target_id = requested_company_id or user.id_empresa
            if not target_id:
                raise OfflineReservationError(
                    status_code=400,
                    message="Debe especificar 'empresa_id' para sincronizar reservas como SUPERADMIN.",
                )
            return target_id

        if not user.id_empresa:
            raise OfflineReservationError(
                status_code=403,
                message="El usuario no tiene una empresa asociada en su token.",
            )
        if (
            requested_company_id is not None
            and requested_company_id != user.id_empresa
        ):
            raise OfflineReservationError(
                status_code=403,
                message="Acceso denegado: no puede sincronizar reservas de otra empresa.",
            )
        return user.id_empresa

    def sync_offline_reservation(
        self,
        user: AuthenticatedUserData,
        payload: OfflineReservationSyncRequest,
        *,
        requested_company_id: int | None = None,
        now: datetime | None = None,
    ) -> OfflineReservationSyncResponse:
        """Procesa de forma atómica e idempotente la sincronización de una reserva creada offline."""
        self._validate_role(user)
        company_id = self._resolve_company_id(user, requested_company_id)
        current_time = now or datetime.now(timezone.utc).replace(tzinfo=None)
        self._validate_saas(company_id, now=current_time)

        # 1. Comprobación de idempotencia: si el UUID ya existe, retornar el resultado previo
        existing = self.repository.get_sync_record(company_id, payload.uuid_reserva_offline)
        if existing:
            return self._build_response_from_sync(existing, is_retry=True)

        # 2. Validación de sucursal
        branch = self.repository.get_branch(company_id, payload.id_sucursal)
        if not branch or not branch.estado:
            return self._record_and_return_rejection(
                company_id=company_id,
                user_id=user.id_usuario,
                payload=payload,
                reason="La sucursal especificada no pertenece a la empresa o se encuentra inactiva.",
                now=current_time,
            )

        # 3. Validación de permisos de sucursal para personal de tienda
        role = user.rol.upper()
        employee = self.repository.get_employee_for_user(company_id, user.id_usuario)
        if role in {"CAJERO", "ENCARGADO_SUCURSAL"}:
            if not employee or not self.repository.is_employee_assigned_to_branch(
                company_id, employee.id_empleado, payload.id_sucursal
            ):
                return self._record_and_return_rejection(
                    company_id=company_id,
                    user_id=user.id_usuario,
                    payload=payload,
                    reason="El usuario no tiene asignación activa para operar en la sucursal de la reserva.",
                    now=current_time,
                )

        # 4. Validación de cliente en la empresa
        client = self.repository.get_client(company_id, payload.id_cliente)
        if not client:
            return self._record_and_return_rejection(
                company_id=company_id,
                user_id=user.id_usuario,
                payload=payload,
                reason=f"El cliente con ID {payload.id_cliente} no existe en la empresa.",
                now=current_time,
            )

        # 5. Validación de variantes y productos pertenecientes a la empresa
        req_variant_ids = [d.id_variante_producto for d in payload.detalles]
        variants_dict = self.repository.get_variants_with_products(
            company_id, req_variant_ids
        )
        missing_variants = set(req_variant_ids) - set(variants_dict.keys())
        if missing_variants:
            return self._record_and_return_rejection(
                company_id=company_id,
                user_id=user.id_usuario,
                payload=payload,
                reason=f"Una o más variantes no pertenecen a la empresa o están inactivas: {sorted(missing_variants)}.",
                now=current_time,
            )

        # 6. Agrupar cantidades por variante para comprobar existencias consolidadas
        quantities_by_variant: dict[int, int] = {}
        prices_by_variant: dict[int, Decimal] = {}
        for detail in payload.detalles:
            v_id = detail.id_variante_producto
            quantities_by_variant[v_id] = quantities_by_variant.get(v_id, 0) + detail.cantidad
            prod = variants_dict[v_id][1]
            prices_by_variant[v_id] = (
                detail.precio_referencial if detail.precio_referencial is not None else prod.precio
            )

        # 7. Ejecutar transacción atómica con bloqueo de inventario
        try:
            return self._execute_reservation_transaction(
                company_id=company_id,
                user_id=user.id_usuario,
                employee_id=employee.id_empleado if employee else None,
                payload=payload,
                variants_dict=variants_dict,
                quantities_by_variant=quantities_by_variant,
                prices_by_variant=prices_by_variant,
                now=current_time,
            )
        except IntegrityError as err:
            self.db.rollback()
            # En caso de envío concurrente con el mismo UUID, la restricción única uq_reserva_offline_empresa_uuid
            # garantiza que solo uno se registre. Reconsultamos el registro ganador para responder de forma idempotente.
            existing_after_race = self.repository.get_sync_record(
                company_id, payload.uuid_reserva_offline
            )
            if existing_after_race:
                return self._build_response_from_sync(existing_after_race, is_retry=True)
            logger.exception("Error de integridad concurrente en reserva offline: %s", err)
            return OfflineReservationSyncResponse(
                success=False,
                uuid_reserva_offline=payload.uuid_reserva_offline,
                id_reserva=None,
                codigo_reserva=None,
                estado_sincronizacion="CONFLICTO",
                motivo="Conflicto de concurrencia al procesar la reserva; por favor reintente.",
                id_sucursal=payload.id_sucursal,
                id_cliente=payload.id_cliente,
                id_usuario=user.id_usuario,
                id_empresa=company_id,
                fecha_sincronizacion=current_time,
                mensaje="Conflicto concurrente en el servidor.",
            )
        except Exception as exc:
            self.db.rollback()
            logger.exception("Error inesperado en transacción de reserva offline: %s", exc)
            raise OfflineReservationError(
                status_code=500,
                message="Error interno al procesar la transacción de reserva offline.",
            ) from exc

    def _execute_reservation_transaction(
        self,
        *,
        company_id: int,
        user_id: int,
        employee_id: int | None,
        payload: OfflineReservationSyncRequest,
        variants_dict: dict[int, tuple[Any, Any]],
        quantities_by_variant: dict[int, int],
        prices_by_variant: dict[int, Decimal],
        now: datetime,
    ) -> OfflineReservationSyncResponse:
        """Bloquea inventario, valida disponibilidad real y persiste reserva y sync en una única transacción."""
        variant_ids = sorted(quantities_by_variant.keys())
        inventories = self.repository.lock_inventories(
            company_id, payload.id_sucursal, variant_ids
        )

        # Validar disponibilidad real en PostgreSQL para cada variante
        for v_id, needed_qty in quantities_by_variant.items():
            inv = inventories.get(v_id)
            variant_obj, _ = variants_dict[v_id]
            if not inv:
                self.db.rollback()
                return self._record_and_return_rejection(
                    company_id=company_id,
                    user_id=user_id,
                    payload=payload,
                    reason=f"No existe registro de inventario para la variante '{variant_obj.sku}' en la sucursal.",
                    now=now,
                )

            available_stock = inv.stock_actual - inv.stock_reservado
            if available_stock < needed_qty:
                self.db.rollback()
                return self._record_and_return_rejection(
                    company_id=company_id,
                    user_id=user_id,
                    payload=payload,
                    reason=(
                        f"Stock insuficiente para la variante '{variant_obj.sku}' en la sucursal seleccionada. "
                        f"Disponible: {max(0, available_stock)}, Solicitado: {needed_qty}."
                    ),
                    now=now,
                )

        # Si todo el stock está disponible, incrementar stock reservado
        for v_id, needed_qty in quantities_by_variant.items():
            inv = inventories[v_id]
            inv.stock_reservado += needed_qty
            inv.updated_at = now

        # Fechas de expiración y atención programada
        scheduled_at = payload.fecha_atencion_programada
        grace_minutes = getattr(settings, "RESERVATION_GRACE_MINUTES", 60)
        base_time = max(scheduled_at, now)
        expires_at = base_time + timedelta(minutes=grace_minutes)

        code_suffix = secrets.token_hex(4).upper()
        reservation_code = f"RES-OFF-{company_id}-{code_suffix}"

        # 1. Crear encabezado de reserva en t_reserva
        reservation = self.repository.create_reservation(
            company_id=company_id,
            client_id=payload.id_cliente,
            branch_id=payload.id_sucursal,
            employee_id=employee_id,
            code=reservation_code,
            scheduled_at=scheduled_at,
            expires_at=expires_at,
            now=now,
        )

        # 2. Crear líneas de detalle en t_detalle_reserva
        for v_id, qty in quantities_by_variant.items():
            unit_price = prices_by_variant[v_id]
            self.repository.create_reservation_detail(
                company_id=company_id,
                reservation_id=reservation.id_reserva,
                variant_id=v_id,
                quantity=qty,
                unit_price=unit_price,
            )

        # 3. Crear registro de sincronización para control de idempotencia
        details_payload = [d.model_dump() for d in payload.detalles]
        for item in details_payload:
            if "precio_referencial" in item and item["precio_referencial"] is not None:
                item["precio_referencial"] = str(item["precio_referencial"])

        sync_record = self.repository.create_sync_record(
            company_id=company_id,
            uuid_offline=payload.uuid_reserva_offline,
            reservation_id=reservation.id_reserva,
            reservation_code=reservation.codigo,
            branch_id=payload.id_sucursal,
            client_id=payload.id_cliente,
            user_id=user_id,
            status="SINCRONIZADA",
            reason=None,
            details_json=json.dumps(details_payload),
            offline_date=payload.fecha_reserva_offline,
            now=now,
        )

        self.db.commit()
        return self._build_response_from_sync(sync_record, is_retry=False)

    def _record_and_return_rejection(
        self,
        *,
        company_id: int,
        user_id: int,
        payload: OfflineReservationSyncRequest,
        reason: str,
        now: datetime,
    ) -> OfflineReservationSyncResponse:
        """Persiste el rechazo de negocio de forma idempotente para que reintentos futuros no se dupliquen."""
        details_payload = [d.model_dump() for d in payload.detalles]
        for item in details_payload:
            if "precio_referencial" in item and item["precio_referencial"] is not None:
                item["precio_referencial"] = str(item["precio_referencial"])

        try:
            sync_record = self.repository.create_sync_record(
                company_id=company_id,
                uuid_offline=payload.uuid_reserva_offline,
                reservation_id=None,
                reservation_code=None,
                branch_id=payload.id_sucursal,
                client_id=payload.id_cliente,
                user_id=user_id,
                status="RECHAZADA",
                reason=reason,
                details_json=json.dumps(details_payload),
                offline_date=payload.fecha_reserva_offline,
                now=now,
            )
            self.db.commit()
            return self._build_response_from_sync(sync_record, is_retry=False)
        except IntegrityError:
            self.db.rollback()
            existing = self.repository.get_sync_record(company_id, payload.uuid_reserva_offline)
            if existing:
                return self._build_response_from_sync(existing, is_retry=True)
            raise

    def _build_response_from_sync(
        self, sync_record: Any, is_retry: bool = False
    ) -> OfflineReservationSyncResponse:
        """Construye el DTO estandarizado a partir del registro persistido de sincronización."""
        is_synced = sync_record.estado_sincronizacion == "SINCRONIZADA"
        if is_synced:
            msg = (
                "Reserva offline previamente sincronizada (respuesta idempotente)."
                if is_retry
                else "Reserva offline sincronizada exitosamente con el servidor central."
            )
        else:
            msg = (
                f"Reserva offline previamente rechazada: {sync_record.motivo}"
                if is_retry
                else f"La reserva offline fue rechazada por reglas de negocio: {sync_record.motivo}"
            )

        return OfflineReservationSyncResponse(
            success=is_synced,
            uuid_reserva_offline=sync_record.uuid_reserva_offline,
            id_reserva=sync_record.id_reserva,
            codigo_reserva=sync_record.codigo_reserva,
            estado_sincronizacion=sync_record.estado_sincronizacion,
            motivo=sync_record.motivo,
            id_sucursal=sync_record.id_sucursal,
            id_cliente=sync_record.id_cliente,
            id_usuario=sync_record.id_usuario,
            id_empresa=sync_record.empresa_id,
            fecha_sincronizacion=sync_record.created_at,
            mensaje=msg,
        )

