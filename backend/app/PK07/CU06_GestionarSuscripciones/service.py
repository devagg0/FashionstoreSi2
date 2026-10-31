"""Lógica de negocio y orquestación para PK07 / CU06: Gestionar suscripciones empresariales."""

from datetime import datetime, timezone
from decimal import Decimal
import uuid

from dateutil.relativedelta import relativedelta
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.PK07.CU06_GestionarSuscripciones.repository import SaasSubscriptionRepository
from app.PK07.CU06_GestionarSuscripciones.schemas import (
    CheckoutSessionResponse,
    CommercialPlanData,
    CreateCheckoutRequest,
    CurrentSubscriptionResponse,
    PlanFeatureSummary,
    ScheduledChangeData,
    SubscriptionDetailData,
    SubscriptionHistoryItem,
    VerifyPaymentResponse,
)
from app.services.stripe_service import StripeService


class SubscriptionError(Exception):
    """Excepción base para operaciones de suscripciones SaaS."""


class PlanNotFoundError(SubscriptionError):
    """El plan SaaS solicitado no existe o no se encuentra activo."""


class CompanyNotFoundError(SubscriptionError):
    """La empresa especificada no existe o no se encuentra activa."""


class SubscriptionNotFoundError(SubscriptionError):
    """No se encontró una suscripción previa para la operación solicitada."""


class SubscriptionAlreadyActiveError(SubscriptionError):
    """La empresa ya cuenta con una suscripción activa vigente."""


class InvalidSubscriptionOperationError(SubscriptionError):
    """La operación de suscripción solicitada no es válida para el estado actual."""


class InvalidPlanChangeError(SubscriptionError):
    """El cambio de plan solicitado no es válido."""


class TenantMismatchError(SubscriptionError):
    """Intento de operar sobre una empresa distinta a la autorizada por el contexto de seguridad."""


class StripeValidationError(SubscriptionError):
    """La sesión de Stripe no cumple los criterios de validación o seguridad."""


class PaymentNotCompletedError(SubscriptionError):
    """El pago de Stripe no ha sido completado exitosamente."""


class SubscriptionPersistenceError(SubscriptionError):
    """Error al persistir cambios de suscripción en la base de datos."""


class SubscriptionStateTransitionError(SubscriptionError):
    """La transición de estado administrativa no es válida o infringe restricciones de integridad."""


class SaasSubscriptionService:
    """Orquesta las operaciones de suscripciones empresariales SaaS y su integración con Stripe TEST."""

    def __init__(self, db: Session, stripe_service: StripeService | None = None) -> None:
        self.db = db
        self.repository = SaasSubscriptionRepository(db)
        self.stripe = stripe_service or StripeService()

    def list_commercial_plans(self) -> list[CommercialPlanData]:
        """Retorna los planes comerciales vigentes (BÁSICO, PROFESIONAL) con sus límites parametrizados."""
        plans = self.repository.list_commercial_plans()
        results: list[CommercialPlanData] = []
        for plan in plans:
            features = self.repository.list_plan_features(plan.id_plan_saas)
            limite_sucursales = None
            tiene_ia = False
            feat_summaries: list[PlanFeatureSummary] = []
            for pf, sf in features:
                feat_summaries.append(
                    PlanFeatureSummary(
                        codigo=sf.codigo,
                        nombre=sf.nombre,
                        habilitada=pf.habilitada,
                        limite=pf.limite,
                    )
                )
                if sf.codigo == "SUCURSALES" and pf.habilitada:
                    limite_sucursales = pf.limite
                if sf.codigo == "REPORTES_IA" and pf.habilitada:
                    tiene_ia = True
            results.append(
                CommercialPlanData(
                    id_plan_saas=plan.id_plan_saas,
                    codigo=plan.codigo,
                    nombre=plan.nombre,
                    descripcion=plan.descripcion,
                    precio=plan.precio,
                    moneda=plan.moneda,
                    periodo_meses=plan.periodo_meses,
                    limite_sucursales=limite_sucursales,
                    tiene_ia=tiene_ia,
                    funcionalidades=feat_summaries,
                )
            )
        return results

    def get_current_subscription(self, company_id: int) -> CurrentSubscriptionResponse:
        """Obtiene la suscripción vigente de la empresa con días restantes y cambios programados."""
        company = self.repository.get_company_by_id(company_id)
        if company is None:
            raise CompanyNotFoundError(f"Empresa con id {company_id} no encontrada")

        # Recuperar y conciliar operaciones pendientes en Stripe antes de resolver estado
        self.reconcile_pending_operations_for_company(company_id)

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        sub = self.repository.get_active_subscription_by_company(company_id)

        if sub is None:
            return CurrentSubscriptionResponse(tiene_suscripcion_activa=False, data=None)

        # Aplicar cambio de plan programado si ya venció el período actual
        scheduled_op = self.repository.get_scheduled_plan_change(company_id)
        if (
            scheduled_op is not None
            and scheduled_op.fecha_ejecucion_programada is not None
            and scheduled_op.fecha_ejecucion_programada <= now
        ):
            new_plan = self.repository.get_plan_by_id(scheduled_op.id_plan_saas)
            if new_plan is not None:
                sub.id_plan_saas = new_plan.id_plan_saas
                sub.fecha_inicio = now
                sub.fecha_fin_periodo = now + relativedelta(months=new_plan.periodo_meses)
                sub.estado = "ACTIVA"
                sub.updated_at = now
                scheduled_op.estado = "COMPLETADA"
                scheduled_op.updated_at = now
                self.db.commit()
                scheduled_op = None

        # Verificar si expiró el ciclo actual
        if sub.estado == "ACTIVA" and sub.fecha_fin_periodo < now:
            sub.estado = "EXPIRADA"
            sub.updated_at = now
            self.db.commit()
            return CurrentSubscriptionResponse(tiene_suscripcion_activa=False, data=None)

        detail = self._build_subscription_detail(sub, company, scheduled_op)
        return CurrentSubscriptionResponse(tiene_suscripcion_activa=True, data=detail)

    def reconcile_pending_operations_for_company(self, company_id: int) -> None:
        """
        Recupera y concilia de forma idempotente las operaciones en estado PENDIENTE de la empresa.
        Verifica en Stripe si el pago fue efectivamente liquidado (paid) antes de completar la operación
        y activar la suscripción. Si la empresa cuenta con suscripción vigente activa, no concilia anticipadamente.
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        active_sub = self.repository.get_active_subscription_by_company(company_id)
        if active_sub is not None and active_sub.fecha_fin_periodo > now:
            return

        pending_ops = self.repository.get_pending_operations_by_company(company_id)
        for op in pending_ops:
            if not op.id_sesion_checkout:
                continue
            try:
                self.verify_and_sync_payment(
                    session_id=op.id_sesion_checkout,
                    authenticated_company_id=company_id,
                    is_superadmin=True,
                )
            except Exception:
                # Si el pago no está liquidado en Stripe o ocurre error de conexión, se mantiene PENDIENTE
                continue

    def get_subscription_history(self, company_id: int) -> list[SubscriptionHistoryItem]:
        """Retorna el historial completo de suscripciones de una empresa."""
        company = self.repository.get_company_by_id(company_id)
        if company is None:
            raise CompanyNotFoundError(f"Empresa con id {company_id} no encontrada")

        subs = self.repository.list_subscriptions_by_company(company_id)
        items: list[SubscriptionHistoryItem] = []
        for s in subs:
            plan = self.repository.get_plan_by_id(s.id_plan_saas)
            items.append(
                SubscriptionHistoryItem(
                    id_suscripcion=s.id_suscripcion,
                    id_plan_saas=s.id_plan_saas,
                    plan_codigo=plan.codigo if plan else "N/A",
                    plan_nombre=plan.nombre if plan else "Desconocido",
                    estado=s.estado,
                    fecha_inicio=s.fecha_inicio,
                    fecha_fin_periodo=s.fecha_fin_periodo,
                    fecha_cancelacion=s.fecha_cancelacion,
                    proveedor=s.proveedor,
                    referencia_externa=s.referencia_externa,
                    created_at=s.created_at,
                )
            )
        return items

    def create_checkout_session(
        self,
        *,
        company_id: int,
        payload: CreateCheckoutRequest,
        payment_method: str = "TARJETA",
    ) -> CheckoutSessionResponse:
        """Inicia una sesión de pago Stripe Checkout TEST para tarjeta o QR."""
        company = self.repository.get_company_by_id(company_id)
        if company is None or company.estado != "ACTIVA":
            raise CompanyNotFoundError("La empresa no existe o no se encuentra activa")

        plan = self.repository.get_plan_by_id(payload.id_plan_saas)
        if plan is None or not plan.estado:
            raise PlanNotFoundError("El plan solicitado no existe o no se encuentra activo")

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        active_sub = self.repository.get_active_subscription_by_company(company_id)

        # Reglas de negocio: Si existe suscripción activa y período vigente, bloquear CONTRATACION, RENOVACION y CAMBIO_PLAN
        if (
            active_sub is not None
            and active_sub.estado in ("ACTIVA", "PRUEBA", "SUSPENDIDA")
            and active_sub.fecha_fin_periodo > now
        ):
            if payload.tipo_operacion == "CONTRATACION":
                raise SubscriptionAlreadyActiveError(
                    "La empresa cuenta con una suscripción vigente. "
                    "Esta opción estará disponible al finalizar tu suscripción actual."
                )
            elif payload.tipo_operacion == "RENOVACION":
                raise InvalidPlanChangeError(
                    "No es posible renovar anticipadamente mientras exista una suscripción vigente. "
                    "Esta opción estará disponible al finalizar tu suscripción actual."
                )
            elif payload.tipo_operacion == "CAMBIO_PLAN":
                raise InvalidPlanChangeError(
                    "No es posible cambiar de plan mientras exista una suscripción vigente. "
                    "Esta opción estará disponible al finalizar tu suscripción actual."
                )
            else:
                raise InvalidPlanChangeError(
                    "Operación no permitida mientras exista una suscripción vigente. "
                    "Esta opción estará disponible al finalizar tu suscripción actual."
                )

        # Si el período ya venció o no hay suscripción activa:
        if payload.tipo_operacion == "RENOVACION":
            all_subs = self.repository.list_subscriptions_by_company(company_id)
            if not all_subs:
                raise SubscriptionNotFoundError(
                    "No existe una suscripción previa para renovar. Debe contratar un plan primero."
                )

        # Importe y moneda obtenidos exclusivamente desde la base de datos
        amount_cents = int(plan.precio * 100)
        currency = plan.moneda.lower()
        tracking_id = str(uuid.uuid4())

        success_url = payload.success_url or (
            "https://fashionstore.com/saas/suscripcion/confirmar?session_id={CHECKOUT_SESSION_ID}"
        )
        cancel_url = payload.cancel_url or "https://fashionstore.com/saas/suscripcion"

        # Crear sesión con el adaptador existente de Stripe TEST
        session = self.stripe.create_saas_checkout_session(
            amount=amount_cents,
            currency=currency,
            company_id=company_id,
            company_name=company.nombre,
            plan_id=plan.id_plan_saas,
            plan_name=plan.nombre,
            plan_code=plan.codigo,
            operation=payload.tipo_operacion,
            tracking_id=tracking_id,
            success_url=success_url,
            cancel_url=cancel_url,
        )

        session_id = session["id"] if isinstance(session, dict) else session.id
        checkout_url = session["url"] if isinstance(session, dict) else session.url

        # Registrar operación pendiente en tabla complementaria
        self.repository.record_operation(
            company_id=company_id,
            plan_id=plan.id_plan_saas,
            subscription_id=active_sub.id_suscripcion if active_sub else None,
            operation_type=payload.tipo_operacion,
            payment_method=payment_method,
            amount=plan.precio,
            currency=plan.moneda,
            provider="STRIPE",
            checkout_session_id=session_id,
            status="PENDIENTE",
            scheduled_date=active_sub.fecha_fin_periodo if payload.tipo_operacion == "CAMBIO_PLAN" and active_sub else None,
        )
        self.db.commit()

        # Para el endpoint de QR, se expone la misma URL del checkout para lectura óptica
        qr_data = checkout_url if payment_method == "QR" else None

        return CheckoutSessionResponse(
            success=True,
            message="Sesión de Checkout creada exitosamente",
            id_sesion=session_id,
            url_checkout=checkout_url,
            qr_data=qr_data,
            tipo_operacion=payload.tipo_operacion,
            metodo_pago=payment_method,
            monto=plan.precio,
            moneda=plan.moneda,
            id_plan_saas=plan.id_plan_saas,
            plan_codigo=plan.codigo,
            plan_nombre=plan.nombre,
        )

    def verify_and_sync_payment(
        self,
        session_id: str,
        authenticated_company_id: int | None,
        is_superadmin: bool = False,
    ) -> VerifyPaymentResponse:
        """
        Consulta y concilia el estado de la sesión directamente en Stripe TEST.
        Aplica validaciones estrictas y actualiza t_suscripcion de forma idempotente y transaccional.
        """
        # 1. Consultar sesión en Stripe
        session = self.stripe.retrieve_checkout_session(session_id)
        if hasattr(session, "to_dict"):
            session_data = session.to_dict()
        elif isinstance(session, dict):
            session_data = session
        else:
            session_data = {}

        livemode = session_data.get("livemode") if session_data else getattr(session, "livemode", None)
        payment_status = session_data.get("payment_status") if session_data else getattr(session, "payment_status", None)
        raw_metadata = session_data.get("metadata") if session_data else getattr(session, "metadata", {})
        amount_total = session_data.get("amount_total") if session_data else getattr(session, "amount_total", None)
        raw_currency = session_data.get("currency") if session_data else getattr(session, "currency", "")
        currency = (raw_currency or "").upper()
        payment_intent = session_data.get("payment_intent") if session_data else getattr(session, "payment_intent", None)

        if hasattr(raw_metadata, "to_dict"):
            meta_dict = raw_metadata.to_dict()
        elif isinstance(raw_metadata, dict):
            meta_dict = raw_metadata
        else:
            meta_dict = {}

        # 2. Validar modo TEST y estado de pago
        if livemode is not False:
            raise StripeValidationError("Stripe debe operar exclusivamente en modo TEST (livemode=false)")

        if payment_status != "paid":
            raise PaymentNotCompletedError(
                f"La sesión de pago no se encuentra liquidada (estado Stripe: '{payment_status}')"
            )

        # 3. Validar metadatos y aislamiento multitenant
        session_company_id = int(meta_dict.get("empresa_id", 0))
        plan_id = int(meta_dict.get("plan_id", 0))
        operation_type = meta_dict.get("operacion", "CONTRATACION")

        op_record = self.repository.get_operation_by_session(session_id)
        if session_company_id == 0 and op_record is not None:
            session_company_id = op_record.id_empresa
        if plan_id == 0 and op_record is not None:
            plan_id = op_record.id_plan_saas
        if "operacion" not in meta_dict and op_record is not None:
            operation_type = op_record.tipo_operacion

        if not is_superadmin and authenticated_company_id != session_company_id:
            raise TenantMismatchError(
                "La sesión de pago pertenece a otra empresa. Acceso denegado."
            )

        plan = self.repository.get_plan_by_id(plan_id)
        if plan is None:
            raise PlanNotFoundError("El plan especificado en la sesión de Stripe no existe")

        expected_amount_cents = int(plan.precio * 100)
        if amount_total is not None and amount_total != expected_amount_cents:
            raise StripeValidationError("El importe liquidado en Stripe no coincide con el precio oficial del plan")

        if currency and currency != plan.moneda.upper():
            raise StripeValidationError("La moneda liquidada en Stripe no coincide con la moneda del plan")

        # 4. IDEMPOTENCIA: Si la sesión ya fue aplicada previamente, responder sin duplicar
        existing_sub = self.repository.get_subscription_by_reference("STRIPE", session_id)
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        if existing_sub is not None:
            dias_restantes = max(0, (existing_sub.fecha_fin_periodo - now).days)
            return VerifyPaymentResponse(
                success=True,
                message="El pago ya fue confirmado previamente y la suscripción se encuentra activa.",
                id_suscripcion=existing_sub.id_suscripcion,
                estado=existing_sub.estado,
                plan_codigo=plan.codigo,
                tipo_operacion=operation_type,
                fecha_inicio=existing_sub.fecha_inicio,
                fecha_fin_periodo=existing_sub.fecha_fin_periodo,
                dias_restantes=dias_restantes,
                referencia_pago=session_id,
            )

        if op_record is not None and op_record.estado in ("COMPLETADA", "PROGRAMADA"):
            current_sub = self.repository.get_active_subscription_by_company(session_company_id)
            if current_sub:
                dias_restantes = max(0, (current_sub.fecha_fin_periodo - now).days)
                return VerifyPaymentResponse(
                    success=True,
                    message="Operación de pago ya procesada previamente.",
                    id_suscripcion=current_sub.id_suscripcion,
                    estado=current_sub.estado,
                    plan_codigo=plan.codigo,
                    tipo_operacion=operation_type,
                    fecha_inicio=current_sub.fecha_inicio,
                    fecha_fin_periodo=current_sub.fecha_fin_periodo,
                    dias_restantes=dias_restantes,
                    referencia_pago=session_id,
                )

        # 5. Aplicar la operación según el tipo
        pi_id = payment_intent if isinstance(payment_intent, str) else (
            payment_intent.get("id") if isinstance(payment_intent, dict) else getattr(payment_intent, "id", None)
        )

        current_active = self.repository.get_active_subscription_by_company(
            session_company_id, for_update=True
        )

        # Si existe suscripción activa y vigente, bloquear verificación de operaciones incompatibles
        if (
            current_active is not None
            and current_active.estado in ("ACTIVA", "PRUEBA", "SUSPENDIDA")
            and current_active.fecha_fin_periodo > now
            and current_active.referencia_externa != session_id
        ):
            # Preservar el pago confirmado en op_record para que no se pierda
            if op_record:
                op_record.id_pago_externo = pi_id
                op_record.updated_at = now
                self.db.commit()

            raise SubscriptionAlreadyActiveError(
                f"La empresa cuenta con una suscripción vigente hasta {current_active.fecha_fin_periodo.strftime('%d/%m/%Y')}. "
                f"El pago confirmado '{pi_id or session_id}' ha sido registrado de forma segura para conciliación al finalizar tu suscripción actual."
            )

        try:
            # Si la suscripción previa existía y ya venció, marcarla como EXPIRADA antes de activar el nuevo período
            if current_active is not None and current_active.fecha_fin_periodo <= now:
                current_active.estado = "EXPIRADA"
                current_active.updated_at = now

            if operation_type == "CONTRATACION":
                start_date = now
                end_date = now + relativedelta(months=plan.periodo_meses)
                sub = self.repository.create_subscription(
                    company_id=session_company_id,
                    plan_id=plan.id_plan_saas,
                    start_date=start_date,
                    end_date=end_date,
                    status="ACTIVA",
                    provider="STRIPE",
                    external_reference=session_id,
                    auto_renew=False,
                )
                if op_record:
                    op_record.estado = "COMPLETADA"
                    op_record.id_suscripcion = sub.id_suscripcion
                    op_record.id_pago_externo = pi_id
                    op_record.updated_at = now

                self.db.commit()
                dias_restantes = max(0, (end_date - now).days)
                return VerifyPaymentResponse(
                    success=True,
                    message=f"Plan {plan.nombre} contratado y activado exitosamente.",
                    id_suscripcion=sub.id_suscripcion,
                    estado=sub.estado,
                    plan_codigo=plan.codigo,
                    tipo_operacion="CONTRATACION",
                    fecha_inicio=sub.fecha_inicio,
                    fecha_fin_periodo=sub.fecha_fin_periodo,
                    dias_restantes=dias_restantes,
                    referencia_pago=session_id,
                )

            elif operation_type == "RENOVACION":
                current_sub = current_active
                if current_sub is None:
                    all_subs = self.repository.list_subscriptions_by_company(session_company_id)
                    if not all_subs:
                        raise SubscriptionNotFoundError("No existe una suscripción para renovar")
                    current_sub = all_subs[0]

                # Al vencer el período, se renueva desde ahora
                current_sub.fecha_inicio = now
                new_end = now + relativedelta(months=plan.periodo_meses)
                current_sub.fecha_fin_periodo = new_end
                current_sub.estado = "ACTIVA"
                current_sub.referencia_externa = session_id
                current_sub.updated_at = now

                if op_record:
                    op_record.estado = "COMPLETADA"
                    op_record.id_suscripcion = current_sub.id_suscripcion
                    op_record.id_pago_externo = pi_id
                    op_record.updated_at = now

                self.db.commit()
                dias_restantes = max(0, (new_end - now).days)
                return VerifyPaymentResponse(
                    success=True,
                    message=f"Suscripción renovada exitosamente hasta {new_end.strftime('%d/%m/%Y')}.",
                    id_suscripcion=current_sub.id_suscripcion,
                    estado=current_sub.estado,
                    plan_codigo=plan.codigo,
                    tipo_operacion="RENOVACION",
                    fecha_inicio=current_sub.fecha_inicio,
                    fecha_fin_periodo=current_sub.fecha_fin_periodo,
                    dias_restantes=dias_restantes,
                    referencia_pago=session_id,
                )

            elif operation_type == "CAMBIO_PLAN":
                start_date = now
                end_date = now + relativedelta(months=plan.periodo_meses)
                sub = self.repository.create_subscription(
                    company_id=session_company_id,
                    plan_id=plan.id_plan_saas,
                    start_date=start_date,
                    end_date=end_date,
                    status="ACTIVA",
                    provider="STRIPE",
                    external_reference=session_id,
                    auto_renew=False,
                )
                if op_record:
                    op_record.estado = "COMPLETADA"
                    op_record.id_suscripcion = sub.id_suscripcion
                    op_record.id_pago_externo = pi_id
                    op_record.updated_at = now

                self.db.commit()
                dias_restantes = max(0, (end_date - now).days)
                return VerifyPaymentResponse(
                    success=True,
                    message=f"Plan {plan.nombre} contratado exitosamente tras finalizar tu suscripción previa.",
                    id_suscripcion=sub.id_suscripcion,
                    estado=sub.estado,
                    plan_codigo=plan.codigo,
                    tipo_operacion="CAMBIO_PLAN",
                    fecha_inicio=sub.fecha_inicio,
                    fecha_fin_periodo=sub.fecha_fin_periodo,
                    dias_restantes=dias_restantes,
                    referencia_pago=session_id,
                )

            else:
                raise InvalidSubscriptionOperationError(f"Tipo de operación '{operation_type}' desconocida")

        except (SubscriptionError, IntegrityError) as err:
            self.db.rollback()
            if isinstance(err, SubscriptionError):
                raise
            raise SubscriptionPersistenceError("Error de integridad al confirmar la suscripción") from err
        except SQLAlchemyError as err:
            self.db.rollback()
            raise SubscriptionPersistenceError("Error al persistir la suscripción") from err

    def admin_list_all_subscriptions(
        self,
        *,
        company_id: int | None = None,
        status: str | None = None,
        plan_id: int | None = None,
    ) -> list[SubscriptionDetailData]:
        """Listado administrativo para SUPERADMIN de todas las suscripciones."""
        subs = self.repository.list_all_subscriptions(
            company_id=company_id, status=status, plan_id=plan_id
        )
        results: list[SubscriptionDetailData] = []
        for s in subs:
            company = self.repository.get_company_by_id(s.id_empresa)
            scheduled = self.repository.get_scheduled_plan_change(s.id_empresa)
            results.append(self._build_subscription_detail(s, company, scheduled))
        return results

    def admin_update_subscription_status(
        self,
        subscription_id: int,
        new_status: str,
        reason: str | None = None,
    ) -> SubscriptionDetailData:
        """Permite a SUPERADMIN suspender, reactivar o cancelar una suscripción administrativamente."""
        _ = reason
        sub = self.repository.get_subscription_by_id(subscription_id, for_update=True)
        if sub is None:
            raise SubscriptionNotFoundError(f"Suscripción con id {subscription_id} no encontrada")

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        if new_status == "CANCELADA":
            sub.estado = "CANCELADA"
            sub.fecha_cancelacion = now
            sub.renovacion_automatica = False
        elif new_status == "ACTIVA":
            # Validar que no haya otra activa en la misma empresa (uq_suscripcion_empresa_vigente)
            other_active = self.repository.get_active_subscription_by_company(sub.id_empresa)
            if other_active is not None and other_active.id_suscripcion != sub.id_suscripcion:
                raise SubscriptionStateTransitionError(
                    "La empresa ya cuenta con otra suscripción activa vigente"
                )
            sub.estado = "ACTIVA"
            sub.fecha_cancelacion = None
        elif new_status in ("SUSPENDIDA", "EXPIRADA"):
            sub.estado = new_status
        else:
            raise SubscriptionStateTransitionError(f"Estado '{new_status}' no permitido")

        sub.updated_at = now
        try:
            self.db.commit()
        except IntegrityError as err:
            self.db.rollback()
            raise SubscriptionStateTransitionError("Violación de restricciones al cambiar estado") from err

        company = self.repository.get_company_by_id(sub.id_empresa)
        scheduled = self.repository.get_scheduled_plan_change(sub.id_empresa)
        return self._build_subscription_detail(sub, company, scheduled)

    def _build_subscription_detail(
        self,
        sub,
        company,
        scheduled_op=None,
    ) -> SubscriptionDetailData:
        """Construye el DTO detallado de suscripción."""
        plan = self.repository.get_plan_by_id(sub.id_plan_saas)
        features = self.repository.list_plan_features(sub.id_plan_saas)

        limite_sucursales = None
        tiene_ia = False
        for pf, sf in features:
            if sf.codigo == "SUCURSALES" and pf.habilitada:
                limite_sucursales = pf.limite
            if sf.codigo == "REPORTES_IA" and pf.habilitada:
                tiene_ia = True

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        dias_restantes = max(0, (sub.fecha_fin_periodo - now).days)

        cambio_programado_data = None
        if scheduled_op is not None and scheduled_op.estado == "PROGRAMADA":
            target_plan = self.repository.get_plan_by_id(scheduled_op.id_plan_saas)
            if target_plan:
                cambio_programado_data = ScheduledChangeData(
                    id_plan_saas=target_plan.id_plan_saas,
                    codigo_plan=target_plan.codigo,
                    nombre_plan=target_plan.nombre,
                    fecha_programada=scheduled_op.fecha_ejecucion_programada or sub.fecha_fin_periodo,
                    monto_pagado=scheduled_op.monto,
                    moneda=scheduled_op.moneda,
                    estado=scheduled_op.estado,
                )

        return SubscriptionDetailData(
            id_suscripcion=sub.id_suscripcion,
            id_empresa=sub.id_empresa,
            empresa_codigo=getattr(company, "codigo", None),
            empresa_nombre=getattr(company, "nombre", None),
            id_plan_saas=sub.id_plan_saas,
            plan_codigo=plan.codigo if plan else "N/A",
            plan_nombre=plan.nombre if plan else "Desconocido",
            plan_precio=plan.precio if plan else Decimal("0.00"),
            plan_moneda=plan.moneda if plan else "BOB",
            plan_periodo_meses=plan.periodo_meses if plan else 1,
            limite_sucursales=limite_sucursales,
            tiene_ia=tiene_ia,
            estado=sub.estado,
            fecha_inicio=sub.fecha_inicio,
            fecha_fin_periodo=sub.fecha_fin_periodo,
            fecha_cancelacion=sub.fecha_cancelacion,
            dias_restantes=dias_restantes,
            renovacion_automatica=sub.renovacion_automatica,
            proveedor=sub.proveedor,
            referencia_externa=sub.referencia_externa,
            cambio_programado=cambio_programado_data,
        )

