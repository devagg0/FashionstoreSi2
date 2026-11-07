"""Lógica de negocio y orquestación transaccional para PK08 - CU11: Registrar venta de contado y compra digital offline."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
from typing import Any, Literal
from uuid import NAMESPACE_OID, UUID, uuid5

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.PK07.CU07_ConsultarPlanLimites.service import (
    FeatureNotEnabledError,
    NoActiveSubscriptionError,
    SaasPlanLimitsService,
)
from app.PK08.CU11_RegistrarVentaOffline.repository import OfflineSaleRepository
from app.PK08.CU11_RegistrarVentaOffline.schemas import (
    OfflineBatchSyncRequest,
    OfflineBatchSyncResponse,
    OfflineConflictDetail,
    OfflineReservationTransitionRequest,
    OfflineReservationTransitionResponse,
    OfflineSaleReleaseDetail,
    OfflineSaleSyncRequest,
    OfflineSaleSyncResponse,
)
from app.schemas.auth import AuthenticatedUserData
from app.services.catalog import CatalogService

logger = logging.getLogger(__name__)

ALLOWED_RESERVATION_STAFF_ROLES: set[str] = {"CAJERO", "ENCARGADO_SUCURSAL"}


class OfflineSaleError(Exception):
    """Excepción para errores de autenticación, permisos, aislamiento multitenant o plan SaaS en CU11."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class OfflineSaleService:
    """Orquesta la recepción, validación y persistencia transaccional de ventas POS, compras digitales y atención de reservas offline."""

    def __init__(
        self,
        db: Session,
        repository: OfflineSaleRepository | None = None,
        saas_service: SaasPlanLimitsService | None = None,
    ) -> None:
        self.db = db
        self.repository = repository or OfflineSaleRepository(db)
        self.saas_service = saas_service or SaasPlanLimitsService(db)

    @staticmethod
    def _money(value: Decimal | int | float | str) -> Decimal:
        return CatalogService._money(Decimal(str(value)))

    @staticmethod
    def _normalize_uuid(company_id: int, raw_uuid: str) -> UUID:
        """Convierte el UUID offline en un objeto UUID determinístico apto para clave de idempotencia."""
        cleaned = raw_uuid.strip()
        try:
            return UUID(cleaned)
        except ValueError:
            return uuid5(NAMESPACE_OID, f"fashionstore:{company_id}:{cleaned}")

    @staticmethod
    def _sale_number(canal: str, user_id: int, uuid_obj: UUID) -> str:
        """Genera un número de venta determinístico y compatible con CU20 (VTA-...) y CU21 (DIG-...)."""
        if canal == "DIGITAL":
            return f"DIG-{uuid_obj.hex.upper()}"
        return f"VTA-{user_id}-{uuid_obj.hex.upper()}"

    def _resolve_company_id(
        self,
        user: AuthenticatedUserData,
        requested_company_id: int | None = None,
        payload_company_id: int | None = None,
    ) -> int:
        """Resuelve la empresa desde la sesión autenticada y bloquea accesos cruzados entre tenants."""
        if not user.id_empresa:
            raise OfflineSaleError(
                status_code=403,
                message="El usuario autenticado no tiene una empresa asociada en su sesión.",
            )
        if (
            requested_company_id is not None
            and requested_company_id != user.id_empresa
        ):
            raise OfflineSaleError(
                status_code=403,
                message="Acceso denegado: no puede sincronizar operaciones de otra empresa.",
            )
        if (
            payload_company_id is not None
            and payload_company_id != user.id_empresa
        ):
            raise OfflineSaleError(
                status_code=403,
                message="Acceso denegado: la empresa indicada en la solicitud no coincide con su sesión autenticada.",
            )
        return user.id_empresa

    @staticmethod
    def _validate_user_identity(
        user: AuthenticatedUserData, payload_user_id: int | None
    ) -> int:
        """Verifica que el usuario del payload coincida con el usuario autenticado en el JWT."""
        if payload_user_id is not None and payload_user_id != user.id_usuario:
            raise OfflineSaleError(
                status_code=403,
                message="Acceso denegado: el identificador de usuario enviado no coincide con la sesión autenticada.",
            )
        return user.id_usuario

    def _validate_saas_features(
        self,
        company_id: int,
        *,
        require_sales_feature: bool = False,
        now: datetime | None = None,
    ) -> None:
        """Valida suscripción activa y funcionalidad OFFLINE (más VENTAS en operaciones POS)."""
        try:
            self.saas_service.validate_feature_enabled(
                company_id, "OFFLINE", now=now
            )
            if require_sales_feature:
                self.saas_service.validate_feature_enabled(
                    company_id, "VENTAS", now=now
                )
        except (NoActiveSubscriptionError, FeatureNotEnabledError) as err:
            raise OfflineSaleError(status_code=403, message=str(err)) from err

    def _resolve_channel_and_validate_role(
        self,
        user: AuthenticatedUserData,
        payload_channel: Literal["PRESENCIAL", "DIGITAL"] | None,
        forced_channel: Literal["PRESENCIAL", "DIGITAL"] | None = None,
    ) -> Literal["PRESENCIAL", "DIGITAL"]:
        """Valida que CLIENTE opere exclusivamente en DIGITAL y CAJERO exclusivamente en PRESENCIAL."""
        role = (user.rol or "").strip().upper()
        target_channel = forced_channel or payload_channel
        if target_channel is None:
            if role == "CLIENTE":
                target_channel = "DIGITAL"
            elif role == "CAJERO":
                target_channel = "PRESENCIAL"
            else:
                raise OfflineSaleError(
                    status_code=403,
                    message=(
                        f"El rol '{user.rol}' no tiene permisos para registrar ventas presenciales ni compras digitales offline."
                    ),
                )

        if (
            forced_channel is not None
            and payload_channel is not None
            and payload_channel != forced_channel
        ):
            raise OfflineSaleError(
                status_code=403,
                message=f"El endpoint requiere canal '{forced_channel}', pero se recibió '{payload_channel}'.",
            )

        if target_channel == "DIGITAL" and role != "CLIENTE":
            raise OfflineSaleError(
                status_code=403,
                message="Únicamente el CLIENTE autenticado puede registrar y sincronizar compras digitales offline.",
            )

        if target_channel == "PRESENCIAL" and role != "CAJERO":
            raise OfflineSaleError(
                status_code=403,
                message="Se requiere rol CAJERO para registrar y sincronizar ventas presenciales desde el POS.",
            )

        return target_channel

    def sync_offline_sale(
        self,
        user: AuthenticatedUserData,
        payload: OfflineSaleSyncRequest,
        *,
        requested_company_id: int | None = None,
        forced_channel: Literal["PRESENCIAL", "DIGITAL"] | None = None,
        now: datetime | None = None,
        accept_server_prices: bool = False,
    ) -> OfflineSaleSyncResponse:
        """Sincroniza de forma atómica e idempotente una compra digital del CLIENTE o una venta POS del CAJERO."""
        canal = self._resolve_channel_and_validate_role(
            user, payload.canal, forced_channel=forced_channel
        )
        company_id = self._resolve_company_id(
            user, requested_company_id, payload.id_empresa
        )
        user_id = self._validate_user_identity(user, payload.id_usuario)
        current_time = now or datetime.now(timezone.utc).replace(tzinfo=None)
        self._validate_saas_features(
            company_id,
            require_sales_feature=(canal == "PRESENCIAL"),
            now=current_time,
        )

        raw_offline_dt = payload.fecha_venta_offline
        if raw_offline_dt is not None and raw_offline_dt.tzinfo is not None:
            offline_date = raw_offline_dt.astimezone(timezone.utc).replace(tzinfo=None)
        else:
            offline_date = raw_offline_dt or current_time
        if offline_date > current_time:
            offline_date = current_time

        # Resolver perfil según el canal
        client_id: int | None = None
        employee_id: int | None = None
        employee_branch_id: int | None = None

        if canal == "DIGITAL":
            client = self.repository.get_client_by_user(company_id, user_id)
            if not client or getattr(client, "empresa_id", company_id) != company_id:
                raise OfflineSaleError(
                    status_code=403,
                    message="No se encontró un perfil de cliente activo vinculado al usuario autenticado en esta empresa.",
                )
            if payload.id_cliente is not None and payload.id_cliente != client.id_cliente:
                raise OfflineSaleError(
                    status_code=403,
                    message="Acceso denegado: no puede registrar ni sincronizar compras digitales a nombre de otro cliente.",
                )
            client_id = client.id_cliente
        else:
            employee = self.repository.get_employee_by_user(company_id, user_id)
            if not employee or getattr(employee, "empresa_id", company_id) != company_id:
                raise OfflineSaleError(
                    status_code=403,
                    message="Perfil de empleado no encontrado para el cajero autenticado.",
                )
            branch_row = self.repository.get_branch(company_id, payload.id_sucursal)
            if not branch_row or getattr(branch_row, "empresa_id", company_id) != company_id:
                raise OfflineSaleError(
                    status_code=403,
                    message="La sucursal indicada no pertenece a la empresa del cajero.",
                )
            assignment = self.repository.get_employee_branch_assignment(
                company_id, employee.id_empleado, payload.id_sucursal
            )
            if not assignment or not getattr(assignment, "estado", True):
                raise OfflineSaleError(
                    status_code=403,
                    message="El cajero no tiene una asignación activa en la sucursal de la venta.",
                )
            employee_id = employee.id_empleado
            employee_branch_id = assignment.id_empleado_sucursal
            client_id = payload.id_cliente

        # 1. Control de idempotencia por UUID
        uuid_obj = self._normalize_uuid(company_id, payload.uuid_venta_offline)
        sale_number = self._sale_number(canal, user_id, uuid_obj)

        existing_sale = self.repository.get_sale_by_number(company_id, sale_number)
        if existing_sale is None:
            existing_payment_by_key = self.repository.get_payment_by_key(
                company_id, uuid_obj
            )
            if existing_payment_by_key is not None:
                existing_sale = self.repository.get_sale_by_id(
                    company_id, existing_payment_by_key.id_venta
                )

        if existing_sale is not None:
            if getattr(existing_sale, "empresa_id", company_id) != company_id:
                raise OfflineSaleError(
                    status_code=403,
                    message="Acceso denegado: el UUID de operación pertenece a otra empresa.",
                )
            if canal == "DIGITAL" and existing_sale.id_cliente != client_id:
                raise OfflineSaleError(
                    status_code=403,
                    message="Acceso denegado: el UUID de compra offline pertenece a otro cliente.",
                )
            existing_payment = self.repository.get_payment_for_sale(
                company_id, existing_sale.id_venta
            )
            return self._build_confirmed_response(
                sale=existing_sale,
                payment=existing_payment,
                payload=payload,
                canal=canal,
                user_id=user_id,
                company_id=company_id,
                offline_date=offline_date,
                now=current_time,
                is_retry=True,
            )

        # 2. Validación de sucursal activa perteneciente al tenant
        branch = self.repository.get_branch(company_id, payload.id_sucursal)
        if (
            not branch
            or getattr(branch, "empresa_id", company_id) != company_id
            or not getattr(branch, "estado", False)
        ):
            return self._build_non_confirmed_response(
                payload=payload,
                canal=canal,
                user_id=user_id,
                company_id=company_id,
                client_id=client_id,
                employee_id=employee_id,
                offline_date=offline_date,
                now=current_time,
                status="RECHAZADA",
                reason="La sucursal especificada no pertenece a la empresa o se encuentra inactiva.",
            )

        # 3. Validación de medio de pago y canal
        if canal == "DIGITAL":
            if payload.medio_pago == "EFECTIVO":
                return self._build_non_confirmed_response(
                    payload=payload,
                    canal=canal,
                    user_id=user_id,
                    company_id=company_id,
                    client_id=client_id,
                    employee_id=employee_id,
                    offline_date=offline_date,
                    now=current_time,
                    status="RECHAZADA",
                    reason="EFECTIVO solo está disponible en ventas PRESENCIALES registradas por CAJERO.",
                )
            if (
                payload.id_reserva is not None
                or payload.codigo_reserva is not None
                or payload.uuid_reserva_offline is not None
            ):
                return self._build_non_confirmed_response(
                    payload=payload,
                    canal=canal,
                    user_id=user_id,
                    company_id=company_id,
                    client_id=client_id,
                    employee_id=employee_id,
                    offline_date=offline_date,
                    now=current_time,
                    status="RECHAZADA",
                    reason="Las ventas asociadas a una reserva deben registrarse desde el POS por el CAJERO.",
                )

        # 4. Validación de líneas sin duplicados
        req_variant_ids = [line.id_variante_producto for line in payload.detalles]
        if len(req_variant_ids) != len(set(req_variant_ids)):
            return self._build_non_confirmed_response(
                payload=payload,
                canal=canal,
                user_id=user_id,
                company_id=company_id,
                client_id=client_id,
                employee_id=employee_id,
                offline_date=offline_date,
                now=current_time,
                status="RECHAZADA",
                reason="La solicitud contiene variantes repetidas; consolide la cantidad por variante.",
            )

        try:
            return self._execute_sale_transaction(
                company_id=company_id,
                user_id=user_id,
                canal=canal,
                branch=branch,
                client_id=client_id,
                employee_id=employee_id,
                employee_branch_id=employee_branch_id,
                payload=payload,
                uuid_obj=uuid_obj,
                sale_number=sale_number,
                offline_date=offline_date,
                now=current_time,
                accept_server_prices=accept_server_prices,
            )
        except IntegrityError as err:
            self.db.rollback()
            existing_after_race = self.repository.get_sale_by_number(
                company_id, sale_number
            )
            if existing_after_race is not None:
                existing_payment = self.repository.get_payment_for_sale(
                    company_id, existing_after_race.id_venta
                )
                return self._build_confirmed_response(
                    sale=existing_after_race,
                    payment=existing_payment,
                    payload=payload,
                    canal=canal,
                    user_id=user_id,
                    company_id=company_id,
                    offline_date=offline_date,
                    now=current_time,
                    is_retry=True,
                )
            logger.exception("Conflicto de integridad concurrente en CU11: %s", err)
            return self._build_non_confirmed_response(
                payload=payload,
                canal=canal,
                user_id=user_id,
                company_id=company_id,
                client_id=client_id,
                employee_id=employee_id,
                offline_date=offline_date,
                now=current_time,
                status="CONFLICTO",
                reason="Conflicto de concurrencia al procesar la venta; por favor reintente.",
                conflicts=[
                    OfflineConflictDetail(
                        tipo_conflicto="CONCURRENCIA",
                        detalle="Conflicto concurrente en base de datos al registrar la venta o pago.",
                    )
                ],
            )
        except OfflineSaleError:
            self.db.rollback()
            raise
        except Exception as exc:
            self.db.rollback()
            logger.exception("Error inesperado en sincronización de venta offline: %s", exc)
            raise OfflineSaleError(
                status_code=500,
                message="Error interno al procesar la venta o compra offline.",
            ) from exc

    def _execute_sale_transaction(
        self,
        *,
        company_id: int,
        user_id: int,
        canal: Literal["PRESENCIAL", "DIGITAL"],
        branch: Any,
        client_id: int | None,
        employee_id: int | None,
        employee_branch_id: int | None,
        payload: OfflineSaleSyncRequest,
        uuid_obj: UUID,
        sale_number: str,
        offline_date: datetime,
        now: datetime,
        accept_server_prices: bool = False,
    ) -> OfflineSaleSyncResponse:
        """Ejecuta validaciones transaccionales de reserva, precios e inventario y persiste venta, movimiento y pago."""
        has_reservation_ref = (
            payload.id_reserva is not None
            or payload.codigo_reserva is not None
            or payload.uuid_reserva_offline is not None
        )
        reservation = None
        reserved_map: dict[int, Any] = {}

        if has_reservation_ref:
            reservation = self.repository.get_reservation(
                company_id,
                reservation_id=payload.id_reserva,
                code=payload.codigo_reserva,
                uuid_offline=payload.uuid_reserva_offline,
                for_update=True,
            )
            if (
                reservation is None
                or getattr(reservation, "empresa_id", company_id) != company_id
            ):
                self.db.rollback()
                return self._build_non_confirmed_response(
                    payload=payload,
                    canal=canal,
                    user_id=user_id,
                    company_id=company_id,
                    client_id=client_id,
                    employee_id=employee_id,
                    offline_date=offline_date,
                    now=now,
                    status="RECHAZADA",
                    reason="La reserva asociada no fue encontrada en esta empresa.",
                )

            if reservation.id_sucursal != branch.id_sucursal:
                self.db.rollback()
                return self._build_non_confirmed_response(
                    payload=payload,
                    canal=canal,
                    user_id=user_id,
                    company_id=company_id,
                    client_id=client_id,
                    employee_id=employee_id,
                    offline_date=offline_date,
                    now=now,
                    status="RECHAZADA",
                    reason="La reserva no pertenece a la sucursal de la venta.",
                    reservation=reservation,
                )

            # Validar secuencia obligatoria: PENDIENTE -> CONFIRMADA -> ATENDIDA antes de la venta
            if reservation.estado != "ATENDIDA":
                self.db.rollback()
                is_cancelled_or_expired = reservation.estado in ("CANCELADA", "EXPIRADA")
                conflict_code: Literal["RESERVA_CANCELADA", "RESERVA_NO_ATENDIDA"] = (
                    "RESERVA_CANCELADA" if is_cancelled_or_expired else "RESERVA_NO_ATENDIDA"
                )
                return self._build_non_confirmed_response(
                    payload=payload,
                    canal=canal,
                    user_id=user_id,
                    company_id=company_id,
                    client_id=reservation.id_cliente,
                    employee_id=employee_id,
                    offline_date=offline_date,
                    now=now,
                    status="CONFLICTO",
                    reason=(
                        f"No se puede confirmar una venta sobre la reserva '{reservation.codigo}' porque se encuentra en estado {reservation.estado}."
                        if is_cancelled_or_expired
                        else (
                            f"La reserva '{reservation.codigo}' debe estar en estado ATENDIDA antes de registrar la venta asociada "
                            f"(estado actual: {reservation.estado})."
                        )
                    ),
                    reservation=reservation,
                    conflicts=[
                        OfflineConflictDetail(
                            tipo_conflicto=conflict_code,
                            valor_esperado="ATENDIDA",
                            valor_actual_servidor=reservation.estado,
                            corregible=not is_cancelled_or_expired,
                            datos_servidor={
                                "id_reserva": reservation.id_reserva,
                                "codigo_reserva": reservation.codigo,
                                "estado_reserva": reservation.estado,
                            },
                            acciones_permitidas=(
                                ["DESCARTAR_OPERACION"]
                                if is_cancelled_or_expired
                                else [
                                    "COMPLETAR_TRANSICIONES_RESERVA",
                                    "REINTENTAR_SECUENCIA",
                                    "DESCARTAR_OPERACION",
                                ]
                            ),
                            detalle=(
                                f"La reserva '{reservation.codigo}' fue {reservation.estado.lower()} y no puede venderse."
                                if is_cancelled_or_expired
                                else f"Se requiere completar la secuencia PENDIENTE -> CONFIRMADA -> ATENDIDA antes de vender la reserva '{reservation.codigo}'."
                            ),
                        )
                    ],
                )

            existing_res_sale = self.repository.get_sale_for_reservation(
                company_id, reservation.id_reserva
            )
            if existing_res_sale is not None:
                if existing_res_sale.numero_venta == sale_number:
                    existing_payment = self.repository.get_payment_for_sale(
                        company_id, existing_res_sale.id_venta
                    )
                    return self._build_confirmed_response(
                        sale=existing_res_sale,
                        payment=existing_payment,
                        payload=payload,
                        canal=canal,
                        user_id=user_id,
                        company_id=company_id,
                        offline_date=offline_date,
                        now=now,
                        is_retry=True,
                        reservation=reservation,
                    )
                self.db.rollback()
                return self._build_non_confirmed_response(
                    payload=payload,
                    canal=canal,
                    user_id=user_id,
                    company_id=company_id,
                    client_id=reservation.id_cliente,
                    employee_id=employee_id,
                    offline_date=offline_date,
                    now=now,
                    status="CONFLICTO",
                    reason=f"La reserva '{reservation.codigo}' ya tiene una venta asociada ({existing_res_sale.numero_venta}).",
                    reservation=reservation,
                    conflicts=[
                        OfflineConflictDetail(
                            tipo_conflicto="RESERVA_VENTA_DUPLICADA",
                            valor_esperado=sale_number,
                            valor_actual_servidor=existing_res_sale.numero_venta,
                            detalle=f"La reserva '{reservation.codigo}' ya fue facturada previamente.",
                        )
                    ],
                )

            res_details = self.repository.get_reservation_details(
                company_id, reservation.id_reserva
            )
            reserved_map = {row.id_variante_producto: row for row in res_details}
            for line in payload.detalles:
                if line.id_variante_producto not in reserved_map:
                    self.db.rollback()
                    return self._build_non_confirmed_response(
                        payload=payload,
                        canal=canal,
                        user_id=user_id,
                        company_id=company_id,
                        client_id=reservation.id_cliente,
                        employee_id=employee_id,
                        offline_date=offline_date,
                        now=now,
                        status="RECHAZADA",
                        reason=f"La variante {line.id_variante_producto} no pertenece a la reserva '{reservation.codigo}'.",
                        reservation=reservation,
                    )
                if line.cantidad > reserved_map[line.id_variante_producto].cantidad:
                    self.db.rollback()
                    return self._build_non_confirmed_response(
                        payload=payload,
                        canal=canal,
                        user_id=user_id,
                        company_id=company_id,
                        client_id=reservation.id_cliente,
                        employee_id=employee_id,
                        offline_date=offline_date,
                        now=now,
                        status="RECHAZADA",
                        reason=(
                            f"La cantidad de compra ({line.cantidad}) supera la cantidad reservada "
                            f"({reserved_map[line.id_variante_producto].cantidad}) para la variante {line.id_variante_producto}."
                        ),
                        reservation=reservation,
                    )
            client_id = reservation.id_cliente
        elif canal == "PRESENCIAL" and client_id is not None:
            client_obj = self.repository.get_client_by_id(company_id, client_id)
            if not client_obj or getattr(client_obj, "empresa_id", company_id) != company_id:
                self.db.rollback()
                return self._build_non_confirmed_response(
                    payload=payload,
                    canal=canal,
                    user_id=user_id,
                    company_id=company_id,
                    client_id=client_id,
                    employee_id=employee_id,
                    offline_date=offline_date,
                    now=now,
                    status="RECHAZADA",
                    reason="El cliente especificado no pertenece a la empresa.",
                )

        # Validar variantes y productos
        quantities_by_variant = {
            line.id_variante_producto: line.cantidad for line in payload.detalles
        }
        all_variant_ids = sorted(
            reserved_map.keys() if reservation is not None else quantities_by_variant.keys()
        )
        variants_dict = self.repository.get_variants_with_products(
            company_id, all_variant_ids
        )
        missing_variants = set(all_variant_ids) - set(variants_dict.keys())
        if missing_variants:
            self.db.rollback()
            return self._build_non_confirmed_response(
                payload=payload,
                canal=canal,
                user_id=user_id,
                company_id=company_id,
                client_id=client_id,
                employee_id=employee_id,
                offline_date=offline_date,
                now=now,
                status="RECHAZADA",
                reason=f"Una o más variantes no existen o no pertenecen a la empresa: {sorted(missing_variants)}.",
                reservation=reservation,
            )

        # Consultar promociones vigentes si no es venta por reserva
        promotions_by_product: dict[int, tuple[int, Decimal]] = {}
        if reservation is None:
            product_ids = sorted(
                {variants_dict[v_id][1].id_producto for v_id in quantities_by_variant}
            )
            if hasattr(self.repository, "get_active_promotions_for_products"):
                raw_promos = self.repository.get_active_promotions_for_products(
                    company_id, product_ids, now
                )
                if isinstance(raw_promos, dict):
                    promotions_by_product = raw_promos

        # Construir líneas y validar precios contra el servidor
        prepared_lines: list[dict[str, Any]] = []
        for line in sorted(payload.detalles, key=lambda item: item.id_variante_producto):
            v_id = line.id_variante_producto
            variant_obj, product_obj = variants_dict[v_id]

            if (
                getattr(variant_obj, "empresa_id", company_id) != company_id
                or getattr(product_obj, "empresa_id", company_id) != company_id
            ):
                self.db.rollback()
                return self._build_non_confirmed_response(
                    payload=payload,
                    canal=canal,
                    user_id=user_id,
                    company_id=company_id,
                    client_id=client_id,
                    employee_id=employee_id,
                    offline_date=offline_date,
                    now=now,
                    status="RECHAZADA",
                    reason="Una o más variantes no pertenecen a la empresa.",
                    reservation=reservation,
                )

            if reservation is None and (
                not getattr(variant_obj, "estado", True)
                or not getattr(product_obj, "estado", True)
            ):
                self.db.rollback()
                return self._build_non_confirmed_response(
                    payload=payload,
                    canal=canal,
                    user_id=user_id,
                    company_id=company_id,
                    client_id=client_id,
                    employee_id=employee_id,
                    offline_date=offline_date,
                    now=now,
                    status="RECHAZADA",
                    reason=f"La variante '{getattr(variant_obj, 'sku', v_id)}' o su producto se encuentran inactivos.",
                )

            if (
                line.id_producto is not None
                and getattr(variant_obj, "id_producto", None) != line.id_producto
            ):
                self.db.rollback()
                return self._build_non_confirmed_response(
                    payload=payload,
                    canal=canal,
                    user_id=user_id,
                    company_id=company_id,
                    client_id=client_id,
                    employee_id=employee_id,
                    offline_date=offline_date,
                    now=now,
                    status="RECHAZADA",
                    reason=f"La variante '{getattr(variant_obj, 'sku', v_id)}' no corresponde al producto indicado.",
                    reservation=reservation,
                )

            if reservation is not None:
                unit_price = self._money(reserved_map[v_id].precio_unitario)
                unit_discount = Decimal("0.00")
                promo_id = None
            else:
                base_price = self._money(
                    getattr(product_obj, "precio_base", None)
                    or getattr(product_obj, "precio", Decimal("0.00"))
                )
                if product_obj.id_producto in promotions_by_product:
                    promo_id, unit_discount = promotions_by_product[
                        product_obj.id_producto
                    ]
                elif getattr(product_obj, "precio_final", None) is not None:
                    final_p = self._money(product_obj.precio_final)
                    unit_discount = max(Decimal("0.00"), base_price - final_p)
                    promo_id = line.id_promocion if unit_discount > 0 else None
                else:
                    unit_discount = Decimal("0.00")
                    promo_id = None
                unit_price = base_price

            server_net_unit = self._money(unit_price - unit_discount)
            if not accept_server_prices and line.precio_unitario is not None:
                captured_unit = self._money(line.precio_unitario)
                captured_disc = self._money(line.descuento_unitario or Decimal("0.00"))
                captured_net = self._money(captured_unit - captured_disc)
                if captured_net != server_net_unit and captured_unit != server_net_unit:
                    self.db.rollback()
                    sku_str = getattr(variant_obj, "sku", str(v_id))
                    return self._build_non_confirmed_response(
                        payload=payload,
                        canal=canal,
                        user_id=user_id,
                        company_id=company_id,
                        client_id=client_id,
                        employee_id=employee_id,
                        offline_date=offline_date,
                        now=now,
                        status="CONFLICTO",
                        reason=(
                            f"El precio unitario de la prenda '{sku_str}' cambió en el servidor "
                            f"(capturado offline: Bs {captured_net}, actual servidor: Bs {server_net_unit})."
                        ),
                        reservation=reservation,
                        conflicts=[
                            OfflineConflictDetail(
                                tipo_conflicto="PRECIO_MODIFICADO",
                                id_variante_producto=v_id,
                                sku=sku_str,
                                valor_esperado=captured_net,
                                valor_actual_servidor=server_net_unit,
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
                                detalle=f"Diferencia de precio en variante '{sku_str}'.",
                            )
                        ],
                    )

            line_subtotal = self._money(line.cantidad * server_net_unit)
            prepared_lines.append(
                {
                    "id_variante_producto": v_id,
                    "cantidad": line.cantidad,
                    "precio_unitario": unit_price,
                    "descuento_unitario": unit_discount,
                    "id_promocion": promo_id,
                    "subtotal_linea": line_subtotal,
                }
            )

        subtotal = sum(
            (self._money(item["cantidad"] * item["precio_unitario"]) for item in prepared_lines),
            Decimal("0.00"),
        )
        descuento_total = sum(
            (
                self._money(item["cantidad"] * item["descuento_unitario"])
                for item in prepared_lines
            ),
            Decimal("0.00"),
        )
        total = self._money(subtotal - descuento_total)

        if not accept_server_prices and payload.total is not None and self._money(payload.total) != total:
            self.db.rollback()
            return self._build_non_confirmed_response(
                payload=payload,
                canal=canal,
                user_id=user_id,
                company_id=company_id,
                client_id=client_id,
                employee_id=employee_id,
                offline_date=offline_date,
                now=now,
                status="CONFLICTO",
                reason=(
                    f"El importe total calculado en el servidor (Bs {total}) no coincide "
                    f"con el total registrado offline (Bs {self._money(payload.total)})."
                ),
                reservation=reservation,
                conflicts=[
                    OfflineConflictDetail(
                        tipo_conflicto="PRECIO_MODIFICADO",
                        valor_esperado=self._money(payload.total),
                        valor_actual_servidor=total,
                        detalle="El total de la operación difiere del precio vigente en el servidor.",
                    )
                ],
            )

        # Validar carrito si se envió id_carrito en canal DIGITAL
        cart = None
        if canal == "DIGITAL" and payload.id_carrito is not None and client_id is not None:
            cart = self.repository.get_cart(
                company_id, payload.id_carrito, client_id, for_update=True
            )
            if cart is None:
                self.db.rollback()
                return self._build_non_confirmed_response(
                    payload=payload,
                    canal=canal,
                    user_id=user_id,
                    company_id=company_id,
                    client_id=client_id,
                    employee_id=employee_id,
                    offline_date=offline_date,
                    now=now,
                    status="RECHAZADA",
                    reason="El carrito especificado no existe o no pertenece al cliente.",
                )
            existing_cart_sale = self.repository.get_sale_for_cart(
                company_id, cart.id_carrito
            )
            if (
                existing_cart_sale is not None
                or getattr(cart, "estado", "ACTIVO") != "ACTIVO"
            ):
                self.db.rollback()
                return self._build_non_confirmed_response(
                    payload=payload,
                    canal=canal,
                    user_id=user_id,
                    company_id=company_id,
                    client_id=client_id,
                    employee_id=employee_id,
                    offline_date=offline_date,
                    now=now,
                    status="CONFLICTO",
                    reason="El carrito asociado ya fue convertido en una compra previa.",
                    conflicts=[
                        OfflineConflictDetail(
                            tipo_conflicto="CARRITO_YA_CONVERTIDO",
                            valor_esperado="ACTIVO",
                            valor_actual_servidor=getattr(cart, "estado", "CONVERTIDO"),
                            detalle="El carrito ya no se encuentra activo.",
                        )
                    ],
                )

        # Bloquear y validar inventario en la sucursal
        inventories = self.repository.lock_inventories(
            company_id, branch.id_sucursal, all_variant_ids
        )
        releases: list[OfflineSaleReleaseDetail] = []

        if reservation is not None:
            for v_id in all_variant_ids:
                inv = inventories.get(v_id)
                original_qty = reserved_map[v_id].cantidad
                sku_str = getattr(variants_dict[v_id][0], "sku", str(v_id))
                if (
                    inv is None
                    or getattr(inv, "empresa_id", company_id) != company_id
                    or inv.stock_reservado < original_qty
                    or inv.stock_actual < inv.stock_reservado
                ):
                    self.db.rollback()
                    return self._build_non_confirmed_response(
                        payload=payload,
                        canal=canal,
                        user_id=user_id,
                        company_id=company_id,
                        client_id=client_id,
                        employee_id=employee_id,
                        offline_date=offline_date,
                        now=now,
                        status="CONFLICTO",
                        reason=f"El stock reservado en la sucursal para '{sku_str}' es inconsistente o insuficiente.",
                        reservation=reservation,
                        conflicts=[
                            OfflineConflictDetail(
                                tipo_conflicto="STOCK_INSUFICIENTE",
                                id_variante_producto=v_id,
                                sku=sku_str,
                                valor_esperado=original_qty,
                                valor_actual_servidor=getattr(inv, "stock_reservado", 0)
                                if inv
                                else 0,
                                detalle=f"Inconsistencia en stock reservado para '{sku_str}'.",
                            )
                        ],
                    )
                buy_qty = quantities_by_variant.get(v_id, 0)
                releases.append(
                    OfflineSaleReleaseDetail(
                        id_variante_producto=v_id,
                        cantidad_reservada=original_qty,
                        cantidad_comprada=buy_qty,
                        cantidad_liberada=original_qty - buy_qty,
                    )
                )
        else:
            for v_id, buy_qty in quantities_by_variant.items():
                inv = inventories.get(v_id)
                sku_str = getattr(variants_dict[v_id][0], "sku", str(v_id))
                if inv is None or getattr(inv, "empresa_id", company_id) != company_id:
                    self.db.rollback()
                    return self._build_non_confirmed_response(
                        payload=payload,
                        canal=canal,
                        user_id=user_id,
                        company_id=company_id,
                        client_id=client_id,
                        employee_id=employee_id,
                        offline_date=offline_date,
                        now=now,
                        status="CONFLICTO",
                        reason=f"No existe registro de inventario para la variante '{sku_str}' en la sucursal.",
                        conflicts=[
                            OfflineConflictDetail(
                                tipo_conflicto="STOCK_INSUFICIENTE",
                                id_variante_producto=v_id,
                                sku=sku_str,
                                valor_esperado=buy_qty,
                                valor_actual_servidor=0,
                                detalle=f"Sin inventario configurado para '{sku_str}' en la sucursal.",
                            )
                        ],
                    )
                available = inv.stock_actual - inv.stock_reservado
                if available < buy_qty:
                    self.db.rollback()
                    return self._build_non_confirmed_response(
                        payload=payload,
                        canal=canal,
                        user_id=user_id,
                        company_id=company_id,
                        client_id=client_id,
                        employee_id=employee_id,
                        offline_date=offline_date,
                        now=now,
                        status="CONFLICTO",
                        reason=(
                            f"Stock disponible insuficiente para la variante '{sku_str}' en la sucursal seleccionada. "
                            f"Disponible: {max(0, available)}, Solicitado: {buy_qty}."
                        ),
                        conflicts=[
                            OfflineConflictDetail(
                                tipo_conflicto="STOCK_INSUFICIENTE",
                                id_variante_producto=v_id,
                                sku=sku_str,
                                valor_esperado=buy_qty,
                                valor_actual_servidor=max(0, available),
                                detalle=(
                                    f"Stock insuficiente para '{sku_str}': disponible {max(0, available)}, requerido {buy_qty}."
                                ),
                            )
                        ],
                    )

        # Diferenciación estricta entre EFECTIVO cobrado físicamente y QR/TARJETA simulados offline
        is_physical_cash = canal == "PRESENCIAL" and payload.medio_pago == "EFECTIVO"

        if is_physical_cash:
            sale_state = "COMPLETADA"
            stock_comprometido = False
            fecha_completada = now
            fecha_expiracion_pago = None
            payment_state = "APROBADO"
            payment_provider = "MANUAL"
            payment_env = "LOCAL"
            fecha_aprobacion = now
            movement_state = "CONFIRMADO"
            movement_reason = (
                "Venta presencial offline por reserva (efectivo)"
                if reservation is not None
                else "Venta presencial offline (efectivo)"
            )
        else:
            # Pagos QR y TARJETA offline son SIMULADOS: nunca se registran falsamente como APROBADO
            sale_state = "PENDIENTE"
            stock_comprometido = canal == "DIGITAL"
            fecha_completada = None
            ttl_minutes = getattr(settings, "DIGITAL_CHECKOUT_TTL_MINUTES", 15)
            fecha_expiracion_pago = (
                now + timedelta(minutes=ttl_minutes) if canal == "DIGITAL" else None
            )
            payment_state = "PENDIENTE"
            payment_provider = "STRIPE" if payload.medio_pago == "TARJETA" else "MANUAL"
            payment_env = "TEST" if payload.medio_pago == "TARJETA" else "LOCAL"
            fecha_aprobacion = None
            movement_state = "PENDIENTE"
            movement_reason = (
                "Venta presencial offline pendiente de validación de pago electrónico"
            )

        # Aplicar mutaciones de inventario sin doble descuento
        if reservation is not None:
            for rel in releases:
                if rel.cantidad_liberada > 0:
                    inv = inventories[rel.id_variante_producto]
                    inv.stock_reservado -= rel.cantidad_liberada
                    inv.updated_at = now
            if is_physical_cash:
                for v_id, buy_qty in quantities_by_variant.items():
                    inv = inventories[v_id]
                    inv.stock_actual -= buy_qty
                    inv.stock_reservado -= buy_qty
                    inv.updated_at = now
        else:
            if canal == "DIGITAL":
                for v_id, buy_qty in quantities_by_variant.items():
                    inv = inventories[v_id]
                    inv.stock_reservado += buy_qty
                    inv.updated_at = now
            elif is_physical_cash:
                for v_id, buy_qty in quantities_by_variant.items():
                    inv = inventories[v_id]
                    inv.stock_actual -= buy_qty
                    inv.updated_at = now

        # Persistir venta, detalles, movimiento (si presencial) y pago
        sale = self.repository.create_sale(
            company_id=company_id,
            branch_id=branch.id_sucursal,
            employee_id=employee_id,
            client_id=client_id,
            reservation_id=reservation.id_reserva if reservation is not None else None,
            cart_id=cart.id_carrito if cart is not None else None,
            canal=canal,
            sale_number=sale_number,
            estado=sale_state,
            stock_comprometido=stock_comprometido,
            subtotal=subtotal,
            descuento_total=descuento_total,
            total=total,
            fecha_venta=offline_date,
            fecha_completada=fecha_completada,
            fecha_expiracion_pago=fecha_expiracion_pago,
            now=now,
        )

        self.repository.create_sale_details(company_id, sale.id_venta, prepared_lines)

        if canal == "PRESENCIAL" or is_physical_cash:
            self.repository.create_inventory_movement(
                company_id=company_id,
                sale_id=sale.id_venta,
                branch_id=branch.id_sucursal,
                employee_branch_id=employee_branch_id,
                estado=movement_state,
                motivo=movement_reason,
                lines=prepared_lines,
                now=now,
            )

        if cart is not None:
            cart.estado = "CONVERTIDO"
            cart.updated_at = now

        payment = self.repository.create_payment(
            company_id=company_id,
            sale_id=sale.id_venta,
            medio=payload.medio_pago,
            proveedor=payment_provider,
            entorno=payment_env,
            estado=payment_state,
            monto=total,
            idempotency_key=uuid_obj,
            fecha_aprobacion=fecha_aprobacion,
            referencia_externa=None,
            now=now,
        )

        self.db.commit()

        return self._build_confirmed_response(
            sale=sale,
            payment=payment,
            payload=payload,
            canal=canal,
            user_id=user_id,
            company_id=company_id,
            offline_date=offline_date,
            now=now,
            is_retry=False,
            reservation=reservation,
            releases=releases,
        )

    def sync_reservation_transition(
        self,
        user: AuthenticatedUserData,
        payload: OfflineReservationTransitionRequest,
        *,
        requested_company_id: int | None = None,
        now: datetime | None = None,
    ) -> OfflineReservationTransitionResponse:
        """Sincroniza de forma idempotente las transiciones de reserva realizadas por el CAJERO (PENDIENTE -> CONFIRMADA -> ATENDIDA)."""
        role = (user.rol or "").strip().upper()
        if role not in ALLOWED_RESERVATION_STAFF_ROLES:
            raise OfflineSaleError(
                status_code=403,
                message="Se requiere rol CAJERO o ENCARGADO_SUCURSAL para confirmar o atender reservas.",
            )

        company_id = self._resolve_company_id(
            user, requested_company_id, payload.id_empresa
        )
        user_id = self._validate_user_identity(user, payload.id_usuario)
        current_time = now or datetime.now(timezone.utc).replace(tzinfo=None)
        self._validate_saas_features(
            company_id, require_sales_feature=False, now=current_time
        )

        employee = self.repository.get_employee_by_user(company_id, user_id)
        if not employee or getattr(employee, "empresa_id", company_id) != company_id:
            raise OfflineSaleError(
                status_code=403,
                message="Perfil de empleado no encontrado para el personal autenticado.",
            )

        branch_ids = self.repository.get_employee_active_branch_ids(
            company_id, employee.id_empleado
        )
        if not branch_ids:
            raise OfflineSaleError(
                status_code=403,
                message="El empleado no tiene asignaciones activas a sucursales activas.",
            )

        if payload.id_sucursal is not None and payload.id_sucursal not in branch_ids:
            raise OfflineSaleError(
                status_code=403,
                message="El empleado no está autorizado para gestionar reservas en la sucursal indicada.",
            )

        normalized_action: Literal["CONFIRM", "ATTEND"] = (
            "CONFIRM"
            if payload.accion in ("CONFIRM", "CONFIRMAR")
            else "ATTEND"
        )

        reservation = self.repository.get_reservation(
            company_id,
            reservation_id=payload.id_reserva,
            code=payload.codigo_reserva,
            uuid_offline=payload.uuid_reserva_offline,
            for_update=True,
        )
        if (
            reservation is None
            or getattr(reservation, "empresa_id", company_id) != company_id
        ):
            self.db.rollback()
            return OfflineReservationTransitionResponse(
                success=False,
                confirmada=False,
                uuid_operacion_offline=payload.uuid_operacion_offline,
                id_reserva=payload.id_reserva,
                codigo_reserva=payload.codigo_reserva,
                accion_aplicada=normalized_action,
                estado_anterior=None,
                estado_reserva=None,
                estado_sincronizacion="RECHAZADA",
                estado_resultado="RECHAZADA",
                id_sucursal=payload.id_sucursal,
                id_empleado_atencion=None,
                id_usuario=user_id,
                id_empresa=company_id,
                conservar_operacion_pendiente=True,
                motivo="Reserva no encontrada en la empresa.",
                fecha_sincronizacion=current_time,
                mensaje="La reserva solicitada no existe.",
            )

        if reservation.id_sucursal not in branch_ids or (
            payload.id_sucursal is not None
            and reservation.id_sucursal != payload.id_sucursal
        ):
            self.db.rollback()
            raise OfflineSaleError(
                status_code=403,
                message="La reserva no pertenece a una sucursal autorizada para el empleado.",
            )

        previous_state = reservation.estado

        # Verificar expiración si la reserva aún está en PENDIENTE o CONFIRMADA
        if (
            reservation.estado in ("PENDIENTE", "CONFIRMADA")
            and getattr(reservation, "fecha_expiracion", None) is not None
            and reservation.fecha_expiracion <= current_time
        ):
            res_details = self.repository.get_reservation_details(
                company_id, reservation.id_reserva
            )
            v_ids = [d.id_variante_producto for d in res_details]
            inventories = self.repository.lock_inventories(
                company_id, reservation.id_sucursal, v_ids
            )
            for detail in res_details:
                inv = inventories.get(detail.id_variante_producto)
                if inv is not None and inv.stock_reservado >= detail.cantidad:
                    inv.stock_reservado -= detail.cantidad
                    inv.updated_at = current_time
            reservation.estado = "EXPIRADA"
            reservation.updated_at = current_time
            self.db.commit()
            return OfflineReservationTransitionResponse(
                success=False,
                confirmada=False,
                uuid_operacion_offline=payload.uuid_operacion_offline,
                id_reserva=reservation.id_reserva,
                codigo_reserva=reservation.codigo,
                accion_aplicada=normalized_action,
                estado_anterior=previous_state,
                estado_reserva="EXPIRADA",
                estado_sincronizacion="CONFLICTO",
                estado_resultado="EN_CONFLICTO",
                id_sucursal=reservation.id_sucursal,
                id_empleado_atencion=getattr(reservation, "id_empleado_atencion", None),
                id_usuario=user_id,
                id_empresa=company_id,
                conflictos=[
                    OfflineConflictDetail(
                        tipo_conflicto="RESERVA_ESTADO_INVALIDO",
                        valor_esperado="PENDIENTE"
                        if normalized_action == "CONFIRM"
                        else "CONFIRMADA",
                        valor_actual_servidor="EXPIRADA",
                        detalle=f"La reserva '{reservation.codigo}' venció y fue marcada como EXPIRADA.",
                    )
                ],
                conservar_operacion_pendiente=True,
                motivo="La reserva venció y fue marcada como EXPIRADA.",
                fecha_sincronizacion=current_time,
                mensaje="Conflicto al actualizar la reserva: la reserva ha expirado.",
            )

        # Acción CONFIRM: PENDIENTE -> CONFIRMADA
        if normalized_action == "CONFIRM":
            if reservation.estado == "PENDIENTE":
                reservation.estado = "CONFIRMADA"
                reservation.updated_at = current_time
                self.db.commit()
                return OfflineReservationTransitionResponse(
                    success=True,
                    confirmada=True,
                    uuid_operacion_offline=payload.uuid_operacion_offline,
                    id_reserva=reservation.id_reserva,
                    codigo_reserva=reservation.codigo,
                    accion_aplicada="CONFIRM",
                    estado_anterior=previous_state,
                    estado_reserva="CONFIRMADA",
                    estado_sincronizacion="SINCRONIZADA",
                    estado_resultado="CONFIRMADA",
                    id_sucursal=reservation.id_sucursal,
                    id_empleado_atencion=getattr(reservation, "id_empleado_atencion", None),
                    id_usuario=user_id,
                    id_empresa=company_id,
                    conservar_operacion_pendiente=False,
                    motivo=None,
                    fecha_sincronizacion=current_time,
                    mensaje="Reserva confirmada correctamente.",
                )

            if reservation.estado in ("CONFIRMADA", "ATENDIDA"):
                return OfflineReservationTransitionResponse(
                    success=True,
                    confirmada=True,
                    uuid_operacion_offline=payload.uuid_operacion_offline,
                    id_reserva=reservation.id_reserva,
                    codigo_reserva=reservation.codigo,
                    accion_aplicada="CONFIRM",
                    estado_anterior=previous_state,
                    estado_reserva=reservation.estado,
                    estado_sincronizacion="SINCRONIZADA",
                    estado_resultado="CONFIRMADA",
                    id_sucursal=reservation.id_sucursal,
                    id_empleado_atencion=getattr(reservation, "id_empleado_atencion", None),
                    id_usuario=user_id,
                    id_empresa=company_id,
                    conservar_operacion_pendiente=False,
                    motivo=None,
                    fecha_sincronizacion=current_time,
                    mensaje="Reserva previamente confirmada (respuesta idempotente).",
                )

            self.db.rollback()
            return OfflineReservationTransitionResponse(
                success=False,
                confirmada=False,
                uuid_operacion_offline=payload.uuid_operacion_offline,
                id_reserva=reservation.id_reserva,
                codigo_reserva=reservation.codigo,
                accion_aplicada="CONFIRM",
                estado_anterior=previous_state,
                estado_reserva=reservation.estado,
                estado_sincronizacion="CONFLICTO",
                estado_resultado="EN_CONFLICTO",
                id_sucursal=reservation.id_sucursal,
                id_empleado_atencion=getattr(reservation, "id_empleado_atencion", None),
                id_usuario=user_id,
                id_empresa=company_id,
                conflictos=[
                    OfflineConflictDetail(
                        tipo_conflicto="RESERVA_ESTADO_INVALIDO",
                        valor_esperado="PENDIENTE",
                        valor_actual_servidor=reservation.estado,
                        detalle=f"No se puede confirmar una reserva en estado {reservation.estado}.",
                    )
                ],
                conservar_operacion_pendiente=True,
                motivo=f"Transición inválida: la reserva se encuentra en estado {reservation.estado}.",
                fecha_sincronizacion=current_time,
                mensaje=f"Conflicto de estado en la reserva ({reservation.estado}).",
            )

        # Acción ATTEND: CONFIRMADA -> ATENDIDA
        if reservation.estado == "CONFIRMADA":
            reservation.estado = "ATENDIDA"
            reservation.id_empleado_atencion = employee.id_empleado
            reservation.fecha_atencion = current_time
            reservation.updated_at = current_time
            self.db.commit()
            return OfflineReservationTransitionResponse(
                success=True,
                confirmada=True,
                uuid_operacion_offline=payload.uuid_operacion_offline,
                id_reserva=reservation.id_reserva,
                codigo_reserva=reservation.codigo,
                accion_aplicada="ATTEND",
                estado_anterior=previous_state,
                estado_reserva="ATENDIDA",
                estado_sincronizacion="SINCRONIZADA",
                estado_resultado="CONFIRMADA",
                id_sucursal=reservation.id_sucursal,
                id_empleado_atencion=employee.id_empleado,
                id_usuario=user_id,
                id_empresa=company_id,
                conservar_operacion_pendiente=False,
                motivo=None,
                fecha_sincronizacion=current_time,
                mensaje="Reserva atendida correctamente.",
            )

        if reservation.estado == "ATENDIDA":
            return OfflineReservationTransitionResponse(
                success=True,
                confirmada=True,
                uuid_operacion_offline=payload.uuid_operacion_offline,
                id_reserva=reservation.id_reserva,
                codigo_reserva=reservation.codigo,
                accion_aplicada="ATTEND",
                estado_anterior=previous_state,
                estado_reserva="ATENDIDA",
                estado_sincronizacion="SINCRONIZADA",
                estado_resultado="CONFIRMADA",
                id_sucursal=reservation.id_sucursal,
                id_empleado_atencion=getattr(reservation, "id_empleado_atencion", None),
                id_usuario=user_id,
                id_empresa=company_id,
                conservar_operacion_pendiente=False,
                motivo=None,
                fecha_sincronizacion=current_time,
                mensaje="Reserva previamente atendida (respuesta idempotente).",
            )

        self.db.rollback()
        return OfflineReservationTransitionResponse(
            success=False,
            confirmada=False,
            uuid_operacion_offline=payload.uuid_operacion_offline,
            id_reserva=reservation.id_reserva,
            codigo_reserva=reservation.codigo,
            accion_aplicada="ATTEND",
            estado_anterior=previous_state,
            estado_reserva=reservation.estado,
            estado_sincronizacion="CONFLICTO",
            estado_resultado="EN_CONFLICTO",
            id_sucursal=reservation.id_sucursal,
            id_empleado_atencion=getattr(reservation, "id_empleado_atencion", None),
            id_usuario=user_id,
            id_empresa=company_id,
            conflictos=[
                OfflineConflictDetail(
                    tipo_conflicto="RESERVA_ESTADO_INVALIDO",
                    valor_esperado="CONFIRMADA",
                    valor_actual_servidor=reservation.estado,
                    detalle=(
                        f"Transición inválida: se requiere estado CONFIRMADA antes de atender la reserva (actual: {reservation.estado})."
                    ),
                )
            ],
            conservar_operacion_pendiente=True,
            motivo=f"Transición inválida: se requiere estado CONFIRMADA (actual: {reservation.estado}).",
            fecha_sincronizacion=current_time,
            mensaje="La reserva debe confirmarse antes de marcarse como atendida.",
        )

    def sync_batch_operations(
        self,
        user: AuthenticatedUserData,
        payload: OfflineBatchSyncRequest,
        *,
        requested_company_id: int | None = None,
        now: datetime | None = None,
    ) -> OfflineBatchSyncResponse:
        """Ejecuta en orden estricto una secuencia de operaciones offline dependientes (ej. confirmar -> atender -> vender)."""
        results: list[OfflineReservationTransitionResponse | OfflineSaleSyncResponse] = []
        confirmed_count = 0
        rejected_count = 0
        conflict_count = 0

        for item in payload.operaciones:
            if item.tipo_operacion == "TRANSICION_RESERVA" and item.transicion is not None:
                res = self.sync_reservation_transition(
                    user,
                    item.transicion,
                    requested_company_id=requested_company_id,
                    now=now,
                )
            elif item.tipo_operacion == "VENTA" and item.venta is not None:
                res = self.sync_offline_sale(
                    user,
                    item.venta,
                    requested_company_id=requested_company_id,
                    now=now,
                )
            else:
                raise OfflineSaleError(
                    status_code=400,
                    message="Cada operación del lote debe incluir el payload correspondiente a su tipo_operacion.",
                )

            results.append(res)
            if res.estado_resultado == "CONFIRMADA":
                confirmed_count += 1
            elif res.estado_resultado == "EN_CONFLICTO":
                conflict_count += 1
            else:
                rejected_count += 1

        return OfflineBatchSyncResponse(
            success=(rejected_count == 0 and conflict_count == 0),
            total_operaciones=len(results),
            confirmadas=confirmed_count,
            rechazadas=rejected_count,
            en_conflicto=conflict_count,
            resultados=results,
        )

    def _build_confirmed_response(
        self,
        *,
        sale: Any,
        payment: Any | None,
        payload: OfflineSaleSyncRequest,
        canal: Literal["PRESENCIAL", "DIGITAL"],
        user_id: int,
        company_id: int,
        offline_date: datetime,
        now: datetime,
        is_retry: bool,
        reservation: Any | None = None,
        releases: list[OfflineSaleReleaseDetail] | None = None,
    ) -> OfflineSaleSyncResponse:
        medio = getattr(payment, "medio", payload.medio_pago)
        estado_pago = getattr(
            payment,
            "estado",
            "APROBADO" if (canal == "PRESENCIAL" and medio == "EFECTIVO") else "PENDIENTE",
        )
        is_simulated = medio in ("QR", "TARJETA") and estado_pago == "PENDIENTE"

        if reservation is None and getattr(sale, "id_reserva", None) is not None:
            reservation = self.repository.get_reservation(
                company_id, reservation_id=sale.id_reserva
            )

        if is_retry:
            msg = "Operación comercial offline previamente registrada (respuesta idempotente)."
        elif is_simulated:
            msg = (
                "Operación registrada en servidor central con estado PENDIENTE; "
                "el pago electrónico simulado requiere validación externa."
            )
        else:
            msg = "Venta presencial en efectivo completada y confirmada exitosamente en el servidor central."

        return OfflineSaleSyncResponse(
            success=True,
            confirmada=True,
            uuid_venta_offline=payload.uuid_venta_offline,
            canal=canal,
            estado_sincronizacion="SINCRONIZADA",
            estado_resultado="CONFIRMADA",
            id_venta=sale.id_venta,
            numero_venta=sale.numero_venta,
            estado_venta=sale.estado,
            id_pago=getattr(payment, "id_pago", None),
            medio_pago=medio,
            estado_pago=estado_pago,
            pago_simulado=is_simulated,
            pendiente_validacion_externa=is_simulated,
            stock_comprometido=bool(getattr(sale, "stock_comprometido", False)),
            id_reserva=getattr(sale, "id_reserva", None),
            codigo_reserva=getattr(reservation, "codigo", payload.codigo_reserva),
            estado_reserva=getattr(reservation, "estado", None),
            id_sucursal=sale.id_sucursal,
            id_cliente=getattr(sale, "id_cliente", None),
            id_empleado=getattr(sale, "id_empleado", None),
            id_usuario=user_id,
            id_empresa=company_id,
            subtotal=self._money(sale.subtotal),
            descuento_total=self._money(sale.descuento_total),
            total=self._money(sale.total),
            moneda=getattr(sale, "moneda", "BOB"),
            liberaciones_reserva=releases or [],
            conflictos=[],
            conservar_operacion_pendiente=False,
            motivo=None,
            fecha_operacion_offline=getattr(sale, "fecha_venta", offline_date),
            fecha_sincronizacion=now,
            mensaje=msg,
        )

    def _build_non_confirmed_response(
        self,
        *,
        payload: OfflineSaleSyncRequest,
        canal: Literal["PRESENCIAL", "DIGITAL"],
        user_id: int,
        company_id: int,
        client_id: int | None,
        employee_id: int | None,
        offline_date: datetime,
        now: datetime,
        status: Literal["RECHAZADA", "CONFLICTO"],
        reason: str,
        reservation: Any | None = None,
        conflicts: list[OfflineConflictDetail] | None = None,
    ) -> OfflineSaleSyncResponse:
        estado_resultado: Literal["RECHAZADA", "EN_CONFLICTO"] = (
            "EN_CONFLICTO" if status == "CONFLICTO" else "RECHAZADA"
        )
        is_simulated = payload.medio_pago in ("QR", "TARJETA")
        return OfflineSaleSyncResponse(
            success=False,
            confirmada=False,
            uuid_venta_offline=payload.uuid_venta_offline,
            canal=canal,
            estado_sincronizacion=status,
            estado_resultado=estado_resultado,
            id_venta=None,
            numero_venta=None,
            estado_venta=None,
            id_pago=None,
            medio_pago=payload.medio_pago,
            estado_pago=None,
            pago_simulado=is_simulated,
            pendiente_validacion_externa=is_simulated,
            stock_comprometido=False,
            id_reserva=getattr(reservation, "id_reserva", payload.id_reserva),
            codigo_reserva=getattr(reservation, "codigo", payload.codigo_reserva),
            estado_reserva=getattr(reservation, "estado", None),
            id_sucursal=payload.id_sucursal,
            id_cliente=client_id,
            id_empleado=employee_id,
            id_usuario=user_id,
            id_empresa=company_id,
            subtotal=payload.subtotal,
            descuento_total=payload.descuento_total,
            total=payload.total,
            moneda=payload.moneda,
            liberaciones_reserva=[],
            conflictos=conflicts or [],
            conservar_operacion_pendiente=True,
            motivo=reason,
            fecha_operacion_offline=offline_date,
            fecha_sincronizacion=now,
            mensaje=(
                f"Conflicto al sincronizar la operación offline: {reason}"
                if status == "CONFLICTO"
                else f"Operación offline rechazada por reglas de negocio: {reason}"
            ),
        )

