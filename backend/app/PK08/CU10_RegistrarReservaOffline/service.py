"""Lógica de negocio y orquestación transaccional para PK08 - CU10: Registrar reserva de prendas offline."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import logging
import secrets
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.exc import IntegrityError
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
from app.services.client_reservations import (
    RESERVATION_WINDOW_DAYS,
    ClientReservationService,
)

logger = logging.getLogger(__name__)

# En FashionStore, el único actor que crea y sincroniza reservas de prendas es el CLIENTE.
# El CAJERO conserva su capacidad original de consultar, confirmar y atender reservas desde CU18.
ALLOWED_OFFLINE_RESERVATION_ROLES: set[str] = {"CLIENTE"}


class OfflineReservationError(Exception):
    """Excepción base para errores de autorización, sesión o configuración en CU10."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class OfflineReservationService:
    """Gestiona la sincronización idempotente, validación de horario/stock y persistencia atómica de reservas offline del CLIENTE."""

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
        """Garantiza que únicamente el CLIENTE autenticado pueda crear/sincronizar reservas offline."""
        role = (user.rol or "").strip().upper()
        if role not in ALLOWED_OFFLINE_RESERVATION_ROLES:
            raise OfflineReservationError(
                status_code=403,
                message=(
                    f"El rol '{user.rol}' no tiene permisos para crear ni sincronizar reservas offline. "
                    "Únicamente el CLIENTE puede registrar reservas de prendas."
                ),
            )
        return role

    def _validate_saas(self, company_id: int, now: datetime | None = None) -> Any:
        """Verifica que la empresa cuente con suscripción activa y la funcionalidad OFFLINE habilitada."""
        try:
            return self.saas_service.validate_feature_enabled(
                company_id, "OFFLINE", now=now
            )
        except (NoActiveSubscriptionError, FeatureNotEnabledError) as err:
            raise OfflineReservationError(status_code=403, message=str(err)) from err

    def _resolve_company_id(
        self,
        user: AuthenticatedUserData,
        requested_company_id: int | None,
        payload_company_id: int | None = None,
    ) -> int:
        """Obtiene la empresa exclusivamente desde la sesión autenticada del CLIENTE, rechazando manipulaciones."""
        if not user.id_empresa:
            raise OfflineReservationError(
                status_code=403,
                message="El cliente autenticado no tiene una empresa asociada en su sesión.",
            )
        if (
            requested_company_id is not None
            and requested_company_id != user.id_empresa
        ):
            raise OfflineReservationError(
                status_code=403,
                message="Acceso denegado: no puede sincronizar reservas de otra empresa.",
            )
        if (
            payload_company_id is not None
            and payload_company_id != user.id_empresa
        ):
            raise OfflineReservationError(
                status_code=403,
                message="Acceso denegado: la empresa indicada en la solicitud no coincide con su sesión autenticada.",
            )
        return user.id_empresa

    def _resolve_authenticated_client(
        self,
        company_id: int,
        user: AuthenticatedUserData,
        payload: OfflineReservationSyncRequest,
    ) -> Any:
        """Resuelve el cliente desde la sesión autenticada y bloquea suplantación de identidad."""
        if payload.id_usuario is not None and payload.id_usuario != user.id_usuario:
            raise OfflineReservationError(
                status_code=403,
                message="Acceso denegado: el identificador de usuario enviado no coincide con la sesión autenticada.",
            )

        client = self.repository.get_client_by_user(company_id, user.id_usuario)
        if not client:
            raise OfflineReservationError(
                status_code=403,
                message="No se encontró un perfil de cliente activo vinculado al usuario autenticado en esta empresa.",
            )

        if getattr(client, "empresa_id", company_id) != company_id:
            raise OfflineReservationError(
                status_code=403,
                message="Acceso denegado: el perfil de cliente no pertenece a la empresa de la sesión.",
            )

        if payload.id_cliente is not None and payload.id_cliente != client.id_cliente:
            raise OfflineReservationError(
                status_code=403,
                message="Acceso denegado: no puede registrar ni sincronizar reservas a nombre de otro cliente.",
            )

        return client

    def _validate_and_normalize_schedule(
        self,
        branch: Any,
        scheduled_input: datetime,
        now: datetime,
    ) -> tuple[datetime | None, str | None]:
        """Valida la fecha y hora de recogida reutilizando las reglas del módulo original de reservas (CU17)."""
        opening = getattr(branch, "hora_apertura", None)
        closing = getattr(branch, "hora_cierre", None)
        if opening is None or closing is None:
            return (
                None,
                "La sucursal no tiene un horario de atención completo configurado.",
            )
        if opening == closing:
            return (
                None,
                "El horario de atención configurado en la sucursal es ambiguo.",
            )

        if scheduled_input.tzinfo is not None and scheduled_input.utcoffset() is not None:
            try:
                app_tz = ZoneInfo(settings.APP_TIMEZONE)
            except ZoneInfoNotFoundError as exc:
                raise OfflineReservationError(
                    status_code=500,
                    message="La zona horaria de la aplicación no está configurada correctamente.",
                ) from exc

            local_value = scheduled_input.astimezone(app_tz)
            if scheduled_input.utcoffset() != local_value.utcoffset():
                return (
                    None,
                    "La fecha de atención debe utilizar la zona horaria de Bolivia.",
                )
            local_now = now.replace(tzinfo=timezone.utc).astimezone(app_tz)
            local_date = local_value.date()
            local_now_date = local_now.date()
            local_time = local_value.timetz().replace(tzinfo=None)
            scheduled_utc = local_value.astimezone(timezone.utc).replace(tzinfo=None)
        else:
            scheduled_utc = scheduled_input
            local_date = scheduled_input.date()
            local_now_date = now.date()
            local_time = scheduled_input.time()

        if scheduled_utc <= now:
            return (
                None,
                "La fecha y hora de recogida programada debe ser futura.",
            )

        last_allowed_date = local_now_date + timedelta(days=RESERVATION_WINDOW_DAYS - 1)
        if not (local_now_date <= local_date <= last_allowed_date):
            return (
                None,
                f"La fecha de recogida debe estar dentro de los próximos {RESERVATION_WINDOW_DAYS} días.",
            )

        if not ClientReservationService._valid_slot(local_time, opening, closing):
            return (
                None,
                "El horario de recogida seleccionado está fuera del horario de atención de la sucursal "
                "o no corresponde a un bloque válido de 30 minutos.",
            )

        return scheduled_utc, None

    def _generate_reservation_code(self, company_id: int, now: datetime) -> str:
        """Genera un código único de reserva compatible con el módulo de atención de cajero."""
        for _ in range(10):
            code = f"RSV-{now:%Y%m%d}-{secrets.token_hex(5).upper()}"
            if self.repository.code_exists(code) is not True:
                return code
        return f"RES-OFF-{company_id}-{secrets.token_hex(4).upper()}"

    def sync_offline_reservation(
        self,
        user: AuthenticatedUserData,
        payload: OfflineReservationSyncRequest,
        *,
        requested_company_id: int | None = None,
        now: datetime | None = None,
        allow_conflict_resolution: bool = False,
    ) -> OfflineReservationSyncResponse:
        """Procesa de forma atómica e idempotente la sincronización de una reserva creada offline por el CLIENTE."""
        self._validate_role(user)
        company_id = self._resolve_company_id(
            user, requested_company_id, payload.id_empresa
        )
        current_time = now or datetime.now(timezone.utc).replace(tzinfo=None)
        self._validate_saas(company_id, now=current_time)

        client = self._resolve_authenticated_client(company_id, user, payload)
        client_id = client.id_cliente
        offline_created_at = (
            payload.fecha_reserva_offline.astimezone(timezone.utc).replace(tzinfo=None)
            if payload.fecha_reserva_offline is not None
            and payload.fecha_reserva_offline.tzinfo is not None
            else (payload.fecha_reserva_offline or current_time)
        )

        # 1. Comprobación de idempotencia: si el UUID ya fue procesado para esta empresa, retornar sin duplicar
        existing = self.repository.get_sync_record(
            company_id, payload.uuid_reserva_offline
        )
        if existing:
            if existing.id_cliente != client_id:
                raise OfflineReservationError(
                    status_code=403,
                    message="Acceso denegado: el UUID de reserva offline pertenece a otro cliente.",
                )
            # Si ya fue SINCRONIZADA (tiene id_reserva) o no se está ejecutando resolución explícita CU14, retornar idempotente
            if (
                existing.estado_sincronizacion == "SINCRONIZADA"
                or existing.id_reserva is not None
                or not allow_conflict_resolution
            ):
                res_obj = (
                    self.repository.get_reservation_by_id(company_id, existing.id_reserva)
                    if existing.id_reserva
                    else None
                )
                res_state = getattr(res_obj, "estado", None)
                return self._build_response_from_sync(
                    existing,
                    is_retry=True,
                    reservation_state=res_state if isinstance(res_state, str) else None,
                )

        # 2. Validación de sucursal activa perteneciente a la empresa
        branch = self.repository.get_branch(company_id, payload.id_sucursal)
        if not branch or not getattr(branch, "estado", False) or getattr(branch, "empresa_id", company_id) != company_id:
            return self._record_and_return_non_confirmed(
                company_id=company_id,
                user_id=user.id_usuario,
                client_id=client_id,
                payload=payload,
                offline_date=offline_created_at,
                status="RECHAZADA",
                reason="La sucursal especificada no pertenece a la empresa o se encuentra inactiva.",
                now=current_time,
            )

        # 3. Validación de fecha y horario de recogida en sucursal (reglas CU17)
        scheduled_at, schedule_error = self._validate_and_normalize_schedule(
            branch, payload.fecha_atencion_programada, current_time
        )
        if schedule_error or scheduled_at is None:
            return self._record_and_return_non_confirmed(
                company_id=company_id,
                user_id=user.id_usuario,
                client_id=client_id,
                payload=payload,
                offline_date=offline_created_at,
                status="RECHAZADA",
                reason=schedule_error or "Horario de recogida inválido.",
                now=current_time,
            )

        # 4. Validación de productos, variantes (talla/color) y cantidades
        req_variant_ids = [d.id_variante_producto for d in payload.detalles]
        if len(req_variant_ids) != len(set(req_variant_ids)):
            return self._record_and_return_non_confirmed(
                company_id=company_id,
                user_id=user.id_usuario,
                client_id=client_id,
                payload=payload,
                offline_date=offline_created_at,
                status="RECHAZADA",
                reason="La solicitud contiene variantes repetidas; consolide la cantidad por prenda.",
                now=current_time,
            )

        variants_dict = self.repository.get_variants_with_products(
            company_id, req_variant_ids
        )
        missing_variants = set(req_variant_ids) - set(variants_dict.keys())
        if missing_variants:
            return self._record_and_return_non_confirmed(
                company_id=company_id,
                user_id=user.id_usuario,
                client_id=client_id,
                payload=payload,
                offline_date=offline_created_at,
                status="RECHAZADA",
                reason=f"Una o más variantes no pertenecen a la empresa o no existen: {sorted(missing_variants)}.",
                now=current_time,
            )

        quantities_by_variant: dict[int, int] = {}
        prices_by_variant: dict[int, Decimal] = {}
        for detail in payload.detalles:
            v_id = detail.id_variante_producto
            variant_obj, product_obj = variants_dict[v_id]

            if (
                getattr(variant_obj, "empresa_id", company_id) != company_id
                or getattr(product_obj, "empresa_id", company_id) != company_id
            ):
                return self._record_and_return_non_confirmed(
                    company_id=company_id,
                    user_id=user.id_usuario,
                    client_id=client_id,
                    payload=payload,
                    offline_date=offline_created_at,
                    status="RECHAZADA",
                    reason="Una o más prendas no pertenecen a la empresa del cliente.",
                    now=current_time,
                )

            if not getattr(variant_obj, "estado", True) or not getattr(
                product_obj, "estado", True
            ):
                return self._record_and_return_non_confirmed(
                    company_id=company_id,
                    user_id=user.id_usuario,
                    client_id=client_id,
                    payload=payload,
                    offline_date=offline_created_at,
                    status="RECHAZADA",
                    reason=f"La variante '{getattr(variant_obj, 'sku', v_id)}' o su producto se encuentran inactivos.",
                    now=current_time,
                )

            if (
                detail.id_producto is not None
                and getattr(variant_obj, "id_producto", None) != detail.id_producto
            ):
                return self._record_and_return_non_confirmed(
                    company_id=company_id,
                    user_id=user.id_usuario,
                    client_id=client_id,
                    payload=payload,
                    offline_date=offline_created_at,
                    status="RECHAZADA",
                    reason=f"La variante '{getattr(variant_obj, 'sku', v_id)}' no corresponde al producto seleccionado.",
                    now=current_time,
                )

            if (
                detail.id_talla is not None
                and getattr(variant_obj, "id_talla", None) is not None
                and getattr(variant_obj, "id_talla", None) != detail.id_talla
            ):
                return self._record_and_return_non_confirmed(
                    company_id=company_id,
                    user_id=user.id_usuario,
                    client_id=client_id,
                    payload=payload,
                    offline_date=offline_created_at,
                    status="RECHAZADA",
                    reason=f"La talla indicada no corresponde a la variante '{getattr(variant_obj, 'sku', v_id)}'.",
                    now=current_time,
                )

            if (
                detail.id_color is not None
                and getattr(variant_obj, "id_color", None) is not None
                and getattr(variant_obj, "id_color", None) != detail.id_color
            ):
                return self._record_and_return_non_confirmed(
                    company_id=company_id,
                    user_id=user.id_usuario,
                    client_id=client_id,
                    payload=payload,
                    offline_date=offline_created_at,
                    status="RECHAZADA",
                    reason=f"El color indicado no corresponde a la variante '{getattr(variant_obj, 'sku', v_id)}'.",
                    now=current_time,
                )

            quantities_by_variant[v_id] = detail.cantidad
            authoritative_price = getattr(
                product_obj, "precio_final", None
            ) or getattr(product_obj, "precio", Decimal("0.00"))
            prices_by_variant[v_id] = ClientReservationService._money(
                authoritative_price
            )

        # 5. Ejecutar transacción atómica con bloqueo de inventario e integración con t_reserva / t_detalle_reserva
        try:
            return self._execute_reservation_transaction(
                company_id=company_id,
                user_id=user.id_usuario,
                client_id=client_id,
                payload=payload,
                scheduled_at=scheduled_at,
                offline_date=offline_created_at,
                variants_dict=variants_dict,
                quantities_by_variant=quantities_by_variant,
                prices_by_variant=prices_by_variant,
                now=current_time,
                existing_sync=existing,
            )
        except IntegrityError as err:
            self.db.rollback()
            existing_after_race = self.repository.get_sync_record(
                company_id, payload.uuid_reserva_offline
            )
            if existing_after_race and existing_after_race.id_cliente == client_id:
                return self._build_response_from_sync(
                    existing_after_race, is_retry=True
                )
            logger.exception(
                "Error de integridad concurrente en reserva offline: %s", err
            )
            return OfflineReservationSyncResponse(
                success=False,
                confirmada=False,
                uuid_reserva_offline=payload.uuid_reserva_offline,
                id_reserva=None,
                codigo_reserva=None,
                estado_sincronizacion="CONFLICTO",
                estado_resultado="EN_CONFLICTO",
                estado_reserva=None,
                motivo="Conflicto de concurrencia al procesar la reserva; por favor reintente.",
                id_sucursal=payload.id_sucursal,
                id_cliente=client_id,
                id_usuario=user.id_usuario,
                id_empresa=company_id,
                fecha_sincronizacion=current_time,
                mensaje="Conflicto concurrente en el servidor.",
            )
        except OfflineReservationError:
            self.db.rollback()
            raise
        except Exception as exc:
            self.db.rollback()
            logger.exception(
                "Error inesperado en transacción de reserva offline: %s", exc
            )
            raise OfflineReservationError(
                status_code=500,
                message="Error interno al procesar la transacción de reserva offline.",
            ) from exc

    def _execute_reservation_transaction(
        self,
        *,
        company_id: int,
        user_id: int,
        client_id: int,
        payload: OfflineReservationSyncRequest,
        scheduled_at: datetime,
        offline_date: datetime,
        variants_dict: dict[int, tuple[Any, Any]],
        quantities_by_variant: dict[int, int],
        prices_by_variant: dict[int, Decimal],
        now: datetime,
        existing_sync: Any = None,
    ) -> OfflineReservationSyncResponse:
        """Bloquea inventario, valida disponibilidad real y persiste en t_reserva, t_detalle_reserva y t_reserva_offline_sync."""
        variant_ids = sorted(quantities_by_variant.keys())

        if (
            self.repository.has_active_slot_conflict(
                company_id=company_id,
                branch_id=payload.id_sucursal,
                scheduled_at=scheduled_at,
                variant_ids=variant_ids,
                now=now,
            )
            is True
        ):
            self.db.rollback()
            return self._record_and_return_non_confirmed(
                company_id=company_id,
                user_id=user_id,
                client_id=client_id,
                payload=payload,
                offline_date=offline_date,
                status="CONFLICTO",
                reason="Una de las prendas ya está reservada en la sucursal, fecha y hora seleccionadas.",
                now=now,
            )

        inventories = self.repository.lock_inventories(
            company_id, payload.id_sucursal, variant_ids
        )

        # Validar disponibilidad real en PostgreSQL para cada variante
        for v_id, needed_qty in quantities_by_variant.items():
            inv = inventories.get(v_id)
            variant_obj, _ = variants_dict[v_id]
            if not inv or getattr(inv, "empresa_id", company_id) != company_id:
                self.db.rollback()
                return self._record_and_return_non_confirmed(
                    company_id=company_id,
                    user_id=user_id,
                    client_id=client_id,
                    payload=payload,
                    offline_date=offline_date,
                    status="CONFLICTO",
                    reason=f"No existe registro de inventario para la variante '{variant_obj.sku}' en la sucursal.",
                    now=now,
                )

            available_stock = inv.stock_actual - inv.stock_reservado
            if available_stock < needed_qty:
                self.db.rollback()
                return self._record_and_return_non_confirmed(
                    company_id=company_id,
                    user_id=user_id,
                    client_id=client_id,
                    payload=payload,
                    offline_date=offline_date,
                    status="CONFLICTO",
                    reason=(
                        f"Stock insuficiente para la variante '{variant_obj.sku}' en la sucursal seleccionada. "
                        f"Disponible: {max(0, available_stock)}, Solicitado: {needed_qty}."
                    ),
                    now=now,
                )

        # Incrementar stock reservado atómicamente
        for v_id, needed_qty in quantities_by_variant.items():
            inv = inventories[v_id]
            inv.stock_reservado += needed_qty
            inv.updated_at = now

        grace_minutes = getattr(settings, "RESERVATION_GRACE_MINUTES", 60)
        base_time = max(scheduled_at, now)
        expires_at = base_time + timedelta(minutes=grace_minutes)
        reservation_code = self._generate_reservation_code(company_id, now)

        # 1. Crear encabezado de reserva en t_reserva (estado PENDIENTE y sin empleado asignado para que CAJERO la atienda en CU18)
        reservation = self.repository.create_reservation(
            company_id=company_id,
            client_id=client_id,
            branch_id=payload.id_sucursal,
            employee_id=None,
            code=reservation_code,
            scheduled_at=scheduled_at,
            expires_at=expires_at,
            now=now,
        )

        # 2. Crear líneas de detalle en t_detalle_reserva
        for v_id in variant_ids:
            self.repository.create_reservation_detail(
                company_id=company_id,
                reservation_id=reservation.id_reserva,
                variant_id=v_id,
                quantity=quantities_by_variant[v_id],
                unit_price=prices_by_variant[v_id],
            )

        # 3. Crear o actualizar registro de sincronización para control de idempotencia
        details_payload = [d.model_dump() for d in payload.detalles]
        for item in details_payload:
            if (
                "precio_referencial" in item
                and item["precio_referencial"] is not None
            ):
                item["precio_referencial"] = str(item["precio_referencial"])

        if existing_sync is None and not hasattr(self, "_avoid_sync_lookup"):
            # Solo buscar si no fue provisto
            pass
        if existing_sync is not None and getattr(existing_sync, "id_reserva", None) is None:
            existing_sync.id_reserva = reservation.id_reserva
            existing_sync.codigo_reserva = reservation.codigo
            existing_sync.id_sucursal = payload.id_sucursal
            existing_sync.estado_sincronizacion = "SINCRONIZADA"
            existing_sync.motivo = None
            existing_sync.detalles_json = json.dumps(details_payload)
            existing_sync.updated_at = now
            if hasattr(self.repository, "update_sync_record"):
                self.repository.update_sync_record(
                    existing_sync,
                    reservation_id=reservation.id_reserva,
                    reservation_code=reservation.codigo,
                    branch_id=payload.id_sucursal,
                    status="SINCRONIZADA",
                    reason=None,
                    details_json=json.dumps(details_payload),
                    now=now,
                )
            sync_record = existing_sync
        else:
            sync_record = self.repository.create_sync_record(
                company_id=company_id,
                uuid_offline=payload.uuid_reserva_offline,
                reservation_id=reservation.id_reserva,
                reservation_code=reservation.codigo,
                branch_id=payload.id_sucursal,
                client_id=client_id,
                user_id=user_id,
                status="SINCRONIZADA",
                reason=None,
                details_json=json.dumps(details_payload),
                offline_date=offline_date,
                now=now,
            )

        self.db.commit()
        return self._build_response_from_sync(
            sync_record,
            is_retry=False,
            reservation_state=getattr(reservation, "estado", "PENDIENTE"),
        )

    def _record_and_return_non_confirmed(
        self,
        *,
        company_id: int,
        user_id: int,
        client_id: int,
        payload: OfflineReservationSyncRequest,
        offline_date: datetime,
        status: Literal["RECHAZADA", "CONFLICTO"],
        reason: str,
        now: datetime,
    ) -> OfflineReservationSyncResponse:
        """Persiste el rechazo o conflicto de negocio de forma idempotente sin dar por confirmada la reserva."""
        details_payload = [d.model_dump() for d in payload.detalles]
        for item in details_payload:
            if (
                "precio_referencial" in item
                and item["precio_referencial"] is not None
            ):
                item["precio_referencial"] = str(item["precio_referencial"])

        try:
            existing_sync = self.repository.get_sync_record(
                company_id, payload.uuid_reserva_offline
            )
            if existing_sync is not None and getattr(existing_sync, "id_reserva", None) is None:
                existing_sync.id_sucursal = payload.id_sucursal
                existing_sync.estado_sincronizacion = status
                existing_sync.motivo = reason
                existing_sync.detalles_json = json.dumps(details_payload)
                existing_sync.updated_at = now
                if hasattr(self.repository, "update_sync_record"):
                    self.repository.update_sync_record(
                        existing_sync,
                        reservation_id=None,
                        reservation_code=None,
                        branch_id=payload.id_sucursal,
                        status=status,
                        reason=reason,
                        details_json=json.dumps(details_payload),
                        now=now,
                    )
                sync_record = existing_sync
            else:
                sync_record = self.repository.create_sync_record(
                    company_id=company_id,
                    uuid_offline=payload.uuid_reserva_offline,
                    reservation_id=None,
                    reservation_code=None,
                    branch_id=payload.id_sucursal,
                    client_id=client_id,
                    user_id=user_id,
                    status=status,
                    reason=reason,
                    details_json=json.dumps(details_payload),
                    offline_date=offline_date,
                    now=now,
                )
            self.db.commit()
            return self._build_response_from_sync(sync_record, is_retry=False)
        except IntegrityError:
            self.db.rollback()
            existing = self.repository.get_sync_record(
                company_id, payload.uuid_reserva_offline
            )
            if existing and existing.id_cliente == client_id:
                return self._build_response_from_sync(existing, is_retry=True)
            raise

    def _build_response_from_sync(
        self,
        sync_record: Any,
        is_retry: bool = False,
        reservation_state: str | None = None,
    ) -> OfflineReservationSyncResponse:
        """Construye el DTO estandarizado a partir del registro persistido de sincronización."""
        sync_status = sync_record.estado_sincronizacion
        is_synced = sync_status == "SINCRONIZADA"

        if is_synced:
            estado_resultado: Literal["CONFIRMADA", "RECHAZADA", "EN_CONFLICTO"] = (
                "CONFIRMADA"
            )
            resolved_res_state = reservation_state or "PENDIENTE"
            msg = (
                "Reserva offline previamente confirmada y sincronizada (respuesta idempotente)."
                if is_retry
                else "Reserva offline confirmada y registrada exitosamente en el servidor central."
            )
        elif sync_status == "CONFLICTO":
            estado_resultado = "EN_CONFLICTO"
            resolved_res_state = None
            msg = (
                f"Reserva offline previamente en conflicto: {sync_record.motivo}"
                if is_retry
                else f"Conflicto al sincronizar la reserva offline: {sync_record.motivo}"
            )
        else:
            estado_resultado = "RECHAZADA"
            resolved_res_state = None
            msg = (
                f"Reserva offline previamente rechazada: {sync_record.motivo}"
                if is_retry
                else f"La reserva offline fue rechazada por reglas de negocio: {sync_record.motivo}"
            )

        return OfflineReservationSyncResponse(
            success=is_synced,
            confirmada=is_synced,
            uuid_reserva_offline=sync_record.uuid_reserva_offline,
            id_reserva=sync_record.id_reserva,
            codigo_reserva=sync_record.codigo_reserva,
            estado_sincronizacion=sync_status,
            estado_resultado=estado_resultado,
            estado_reserva=resolved_res_state,
            motivo=sync_record.motivo,
            id_sucursal=sync_record.id_sucursal,
            id_cliente=sync_record.id_cliente,
            id_usuario=sync_record.id_usuario,
            id_empresa=sync_record.empresa_id,
            fecha_sincronizacion=sync_record.created_at,
            mensaje=msg,
        )
