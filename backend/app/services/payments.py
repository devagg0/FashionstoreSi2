"""CU22: QR simulado, Checkout TEST y conciliacion transaccional idempotente."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import urlsplit

from sqlalchemy.exc import DBAPIError, IntegrityError

from app.repositories.client_cart import ClientCartRepository
from app.repositories.payments import PaymentsRepository
from app.repositories.staff_sales import StaffSalesRepository
from app.core.config import settings
from app.schemas.payments import CheckoutSessionData, ManualConfirmationRequest, PaymentData
from app.services.staff_sales import SaleError
from app.services.stripe_service import StripeConnectionError, StripeService


class PaymentError(SaleError):
    pass


class PaymentsService:
    def __init__(self, db, stripe_service=None):
        self.db = db
        self.repository = PaymentsRepository(db)
        self.staff = StaffSalesRepository(db)
        self.clients = ClientCartRepository(db)
        self._stripe = stripe_service

    @property
    def stripe(self):
        if self._stripe is None:
            self._stripe = StripeService()
        return self._stripe

    @staticmethod
    def now():
        return datetime.now(timezone.utc).replace(tzinfo=None)

    def _transaction(self, operation):
        try:
            result = operation()
            self.db.commit()
            return result
        except PaymentError:
            self.db.rollback()
            raise
        except StripeConnectionError:
            self.db.rollback()
            raise PaymentError(503, "Stripe TEST no disponible o resultado incierto; reintente el mismo pago") from None
        except IntegrityError:
            self.db.rollback()
            raise PaymentError(409, "Conflicto de pago o idempotencia; consulte el mismo intento") from None
        except DBAPIError:
            self.db.rollback()
            raise PaymentError(409, "No se pudo confirmar la transaccion; consulte y reintente el mismo pago") from None
        except Exception:
            self.db.rollback()
            raise PaymentError(500, "No fue posible procesar el pago") from None

    def _authorized_sale(self, user, sale_id):
        sale = self.repository.lock_sale(sale_id)
        if sale is None:
            raise PaymentError(404, "Venta no encontrada")
        role = user.rol.upper()
        if role == "CLIENTE":
            client = self.clients.get_client(user.id_usuario)
            if sale.canal != "DIGITAL" or client is None or sale.id_cliente != client.id_cliente:
                raise PaymentError(403, "Venta no autorizada")
        elif role == "CAJERO":
            employee = self.staff.get_employee(user.id_usuario)
            branches = self.staff.branches(employee.id_empleado, for_update=True) if employee else []
            if sale.canal != "PRESENCIAL" or not any(b["id_sucursal"] == sale.id_sucursal for b in branches):
                raise PaymentError(403, "Sucursal o venta no autorizada")
        else:
            raise PaymentError(403, "Se requiere rol CLIENTE o CAJERO")
        return sale

    def _context(self, user, payment_id):
        row = self.repository.payment(payment_id)
        if row is None:
            raise PaymentError(404, "Pago no encontrado")
        sale = self._authorized_sale(user, row.id_venta)
        return sale, self.repository.lock_payment(payment_id)

    @staticmethod
    def _pending(sale, *, new_charge=False):
        if sale.estado != "PENDIENTE":
            raise PaymentError(409, "Solo se puede pagar una venta PENDIENTE")
        if new_charge and sale.fecha_expiracion_pago is not None and sale.fecha_expiracion_pago <= PaymentsService.now():
            raise PaymentError(409, "El plazo de pago de la venta ha expirado")

    def _data(self, sale, payment):
        return PaymentData.model_validate({
            **{name: getattr(payment, name) for name in PaymentData.model_fields if name != "estado_venta"},
            "estado_venta": sale.estado,
        })

    def _stock_context(self, sale):
        items = self.repository.items(sale.id_venta)
        if not items or any(i.cantidad <= 0 for i in items):
            raise PaymentError(409, "La venta no tiene detalles validos")
        held = sale.canal == "DIGITAL" or sale.id_reserva is not None
        if sale.canal == "DIGITAL" and (not sale.stock_comprometido or sale.id_reserva is not None):
            raise PaymentError(409, "La venta digital no conserva su compromiso CU21")
        if sale.id_reserva is not None:
            reservation = self.staff.get_reservation(sale.id_reserva, for_update=True)
            if reservation is None or reservation.estado != "ATENDIDA" or reservation.id_sucursal != sale.id_sucursal:
                raise PaymentError(409, "La reserva asociada no esta ATENDIDA en esta sucursal")
            reserved = {i.id_variante_producto: i.cantidad for i in self.staff.reservation_details(sale.id_reserva)}
            if any(i.cantidad > reserved.get(i.id_variante_producto, 0) for i in items):
                raise PaymentError(409, "Detalles incompatibles con la reserva")
        inventories = {i.id_variante_producto: i for i in self.staff.inventories(
            sale.id_sucursal, [i.id_variante_producto for i in items], for_update=True)}
        for item in items:
            inventory = inventories.get(item.id_variante_producto)
            if inventory is None or inventory.stock_reservado > inventory.stock_actual:
                raise PaymentError(409, "Inventario inconsistente o inexistente")
            available = inventory.stock_reservado if held else inventory.stock_actual - inventory.stock_reservado
            if item.cantidad > available or item.cantidad > inventory.stock_actual:
                raise PaymentError(409, "Stock insuficiente para completar la venta")
        movement = self.repository.lock_movement(sale.id_venta)
        if movement is None and sale.canal == "PRESENCIAL":
            raise PaymentError(409, "Falta el movimiento pendiente CU20")
        if movement is not None:
            if (movement.estado != "PENDIENTE" or movement.tipo_movimiento != "VENTA"
                    or movement.id_sucursal_origen != sale.id_sucursal or movement.id_sucursal_destino is not None):
                raise PaymentError(409, "Movimiento de venta inconsistente")
            expected = {i.id_variante_producto: i.cantidad for i in items}
            actual = {i.id_variante_producto: i.cantidad for i in self.repository.movement_items(movement.id_movimiento_inventario)}
            if expected != actual:
                raise PaymentError(409, "El movimiento no coincide con la venta")
        return items, inventories, held, movement

    def _complete(self, sale, payment):
        self._pending(sale)
        self._assert_current_payment(sale, payment)
        items, inventories, held, movement = self._stock_context(sale)
        now = self.now()
        for item in items:
            inventory = inventories[item.id_variante_producto]
            inventory.stock_actual -= item.cantidad
            if held:
                inventory.stock_reservado -= item.cantidad
            inventory.updated_at = now
        if movement is None:
            movement = self.repository.create_digital_movement(sale, items, now)
        movement.estado = "CONFIRMADO"
        movement.updated_at = now
        sale.stock_comprometido = False
        sale.estado = "COMPLETADA"
        sale.fecha_completada = now
        sale.updated_at = now
        payment.estado = "APROBADO"
        payment.fecha_aprobacion = now
        payment.updated_at = now
        self.db.flush()

    def _assert_current_payment(self, sale, payment):
        if (payment.estado != "PENDIENTE" or payment.monto != sale.total
                or payment.moneda != sale.moneda
                or self.repository.conflicting_payment(sale.id_venta, payment.id_pago) is not None):
            raise PaymentError(409, "El pago no coincide con la venta o existe otro pago activo")

    def start(self, user, sale_id, payload, key):
        def prepare():
            sale = self._authorized_sale(user, sale_id)
            previous = self.repository.by_key(key)
            if previous is not None:
                if previous.id_venta != sale_id or previous.medio != payload.medio:
                    raise PaymentError(409, "La clave de idempotencia pertenece a otra solicitud")
                return self._data(sale, previous)
            self._pending(sale, new_charge=True)
            if self.repository.active_payment(sale_id) is not None:
                raise PaymentError(409, "La venta ya tiene un pago pendiente o aprobado")
            if payload.medio == "EFECTIVO" and sale.canal != "PRESENCIAL":
                raise PaymentError(422, "EFECTIVO solo esta disponible en ventas PRESENCIALES")
            if sale.total <= 0 or sale.moneda != "BOB":
                raise PaymentError(422, "Importe o moneda de venta no admitidos")
            self._stock_context(sale)
            now = self.now()
            payment = self.repository.create_payment(
                id_venta=sale_id, medio=payload.medio,
                proveedor="STRIPE" if payload.medio == "TARJETA" else "MANUAL",
                entorno="TEST" if payload.medio == "TARJETA" else "LOCAL",
                estado="PENDIENTE", monto=sale.total, moneda=sale.moneda,
                referencia_externa=None, clave_idempotencia=key,
                fecha_aprobacion=None, created_at=now, updated_at=now,
            )
            return self._data(sale, payment)
        # Persistir la intencion ANTES de la llamada remota. No existe transaccion
        # distribuida: un resultado incierto siempre conserva el mismo pago.
        data = self._transaction(prepare)
        return data

    def _validate_intent(self, sale, payment, intent):
        expected_metadata = {"id_venta": str(sale.id_venta), "id_pago": str(payment.id_pago),
                             "clave_idempotencia": str(payment.clave_idempotencia)}
        if ("livemode" not in intent or intent["livemode"] is not False
                or intent["amount"] != int(payment.monto * 100)
                or intent["currency"].lower() != payment.moneda.lower()
                or any(intent["metadata"][k] != v for k, v in expected_metadata.items())
                or payment.monto != sale.total or payment.moneda != sale.moneda
                or not intent["id"].startswith("pi_")
                or (payment.referencia_externa is not None and intent["id"] != payment.referencia_externa)):
            raise PaymentError(409, "PaymentIntent no corresponde a este pago TEST")

    def _ensure_intent(self, user, payment_id):
        sale, payment = self._context(user, payment_id)
        if payment.estado != "PENDIENTE":
            return self._data(sale, payment)
        self._pending(sale)
        self._assert_current_payment(sale, payment)
        if payment.referencia_externa is None:
            # Stripe puede podar claves despues de 24h. No recrear un resultado
            # remoto incierto fuera de la ventana segura: requiere conciliacion.
            if self.now() - payment.created_at >= timedelta(hours=23):
                raise PaymentError(409, "Intento remoto sin referencia requiere conciliacion; no crear otro pago")
            intent = self.stripe.create_payment_intent(
                amount=int(payment.monto * Decimal(100)), currency=payment.moneda,
                sale_id=sale.id_venta, payment_id=payment.id_pago, key=payment.clave_idempotencia,
            )
            self._validate_intent(sale, payment, intent)
            payment.referencia_externa = intent["id"]
            payment.updated_at = self.now()
            self.db.flush()
        return self._data(sale, payment)

    def get(self, user, payment_id):
        return self._transaction(lambda: self._data(*self._context(user, payment_id)))

    def confirm_qr(self, user, payment_id):
        # Resultado de simulacion academica configurado por el servidor; no banco.
        return self.confirm_manual(user, payment_id,
            ManualConfirmationRequest(resultado=settings.QR_SIMULATION_RESULT), _system_qr=True)

    def confirm_manual(self, user, payment_id, payload, *, _system_qr=False):
        def operation():
            sale, payment = self._context(user, payment_id)
            if (payment.proveedor != "MANUAL" or payment.entorno != "LOCAL"
                    or payment.medio not in {"EFECTIVO", "QR"}
                    or (_system_qr and payment.medio != "QR")
                    or (not _system_qr and (sale.canal != "PRESENCIAL" or user.rol.upper() != "CAJERO"))):
                raise PaymentError(403, "Este pago no admite confirmacion manual")
            if payment.estado == payload.resultado:
                return self._data(sale, payment)
            if payment.estado != "PENDIENTE":
                raise PaymentError(409, "El pago ya fue resuelto")
            self._pending(sale, new_charge=True)
            if payload.resultado == "APROBADO":
                self._complete(sale, payment)
            else:
                payment.estado = "RECHAZADO"
                payment.updated_at = self.now()
            return self._data(sale, payment)
        return self._transaction(operation)

    def _apply_intent(self, sale, payment, intent, *, attempted=False):
        self._validate_intent(sale, payment, intent)
        status = intent["status"]
        if status == "succeeded":
            if intent["amount_received"] != int(payment.monto * 100):
                raise PaymentError(409, "Stripe no recibio el importe completo")
            self._complete(sale, payment)
        elif status == "canceled":
            payment.estado = "CANCELADO"
        elif status == "requires_payment_method" and (attempted or (
                "last_payment_error" in intent and intent["last_payment_error"] is not None)):
            # Cerrar el PI rechazado antes de permitir otro intento: un PI aun
            # cobrable nunca deja libre la venta para un segundo pago.
            canceled = self.stripe.cancel_payment_intent(payment.referencia_externa, payment.clave_idempotencia)
            self._validate_intent(sale, payment, canceled)
            if canceled["status"] != "canceled":
                raise PaymentError(409, "El intento rechazado aun no pudo cerrarse")
            payment.estado = "RECHAZADO"
        payment.updated_at = self.now()
        return self._data(sale, payment)

    @staticmethod
    def _stripe_payment(payment):
        if (payment.medio, payment.proveedor, payment.entorno) != ("TARJETA", "STRIPE", "TEST"):
            raise PaymentError(422, "El pago no pertenece a TARJETA/STRIPE/TEST")

    @staticmethod
    def _field(obj, name, default=None):
        try:
            return obj[name]
        except (KeyError, TypeError):
            return default

    def _return_urls(self, sale, payment, *, return_target="web"):
        if return_target == "mobile":
            base = f"{settings.STRIPE_CHECKOUT_MOBILE_RETURN_BASE_URL}?payment_id={payment.id_pago}"
        else:
            path = f"/compra/{sale.id_venta}/pago" if sale.canal == "DIGITAL" else f"/staff/ventas/{sale.id_venta}/pago"
            base = f"{settings.STRIPE_CHECKOUT_RETURN_BASE_URL}{path}?payment_id={payment.id_pago}"
        return (base + "&checkout=success&session_id={CHECKOUT_SESSION_ID}", base + "&checkout=cancel")

    def _validate_checkout(self, sale, payment, session):
        metadata = self._field(session, "metadata", {}) or {}
        expected = {"id_venta": str(sale.id_venta), "id_pago": str(payment.id_pago),
                    "clave_idempotencia": str(payment.clave_idempotencia)}
        if (self._field(session, "livemode") is not False
                or self._field(session, "mode") != "payment"
                or self._field(session, "object") != "checkout.session"
                or not str(self._field(session, "id", "")).startswith("cs_test_")
                or self._field(session, "client_reference_id") != str(sale.id_venta)
                or self._field(session, "amount_total") != int(payment.monto * 100)
                or self._field(session, "currency") != payment.moneda.lower()
                or any(self._field(metadata, k) != v for k, v in expected.items())
                or payment.monto != sale.total or payment.moneda != sale.moneda
                or (payment.referencia_externa is not None
                    and payment.referencia_externa.startswith("cs_")
                    and session["id"] != payment.referencia_externa)):
            raise PaymentError(409, "Checkout Session no corresponde a este pago TEST")

    def checkout_session(self, user, payment_id, *, return_target="web"):
        def operation():
            sale, payment = self._context(user, payment_id)
            self._stripe_payment(payment)
            self._pending(sale, new_charge=True)
            self._assert_current_payment(sale, payment)
            self._stock_context(sale)
            reference = payment.referencia_externa
            if reference and reference.startswith("pi_"):
                # No permitir dos recursos cobrables para el mismo pago al
                # migrar un PI previo a Checkout. Cerrar primero el PI antiguo.
                intent = self.stripe.retrieve_payment_intent(reference)
                self._validate_intent(sale, payment, intent)
                if intent["status"] not in {"canceled", "requires_payment_method", "requires_confirmation"}:
                    raise PaymentError(409, "PaymentIntent previo requiere sincronizacion antes de usar Checkout")
                if intent["status"] != "canceled":
                    intent = self.stripe.cancel_payment_intent(reference, payment.clave_idempotencia)
                    self._validate_intent(sale, payment, intent)
                    if intent["status"] != "canceled":
                        raise PaymentError(409, "No se pudo cerrar el PaymentIntent anterior")
                reference = None
            if reference:
                if not reference.startswith("cs_test_"):
                    raise PaymentError(409, "Referencia Stripe no reconocida")
                session = self.stripe.retrieve_checkout_session(reference)
            else:
                if self.now() - payment.created_at >= timedelta(hours=23):
                    raise PaymentError(409, "Intento remoto sin referencia requiere conciliacion; no crear otra sesion")
                success_url, cancel_url = self._return_urls(
                    sale, payment, return_target=return_target,
                )
                session = self.stripe.create_checkout_session(
                    amount=int(payment.monto * 100), currency=payment.moneda,
                    sale_id=sale.id_venta, payment_id=payment.id_pago, key=payment.clave_idempotencia,
                    success_url=success_url, cancel_url=cancel_url,
                )
                self._validate_checkout(sale, payment, session)
                # referencia_externa es la referencia canonica CS. El PI asociado
                # se recupera expandido desde Stripe; no requiere nueva columna.
                payment.referencia_externa = session["id"]
                payment.updated_at = self.now()
            self._validate_checkout(sale, payment, session)
            if session["status"] != "open" or session["payment_status"] != "unpaid":
                raise PaymentError(409, "Checkout ya fue resuelto; sincronice este mismo pago")
            url = self._field(session, "url")
            parsed = urlsplit(url or "")
            if parsed.scheme != "https" or parsed.hostname != "checkout.stripe.com" or parsed.username or parsed.password:
                raise PaymentError(409, "Stripe no devolvio una URL de Checkout valida")
            self.db.flush()
            return CheckoutSessionData(payment=self._data(sale, payment), session_id=session["id"], url=url)
        return self._transaction(operation)

    def stripe_sync(self, user, payment_id):
        def operation():
            sale, payment = self._context(user, payment_id)
            self._stripe_payment(payment)
            if payment.estado != "PENDIENTE":
                return self._data(sale, payment)
            self._pending(sale)
            self._assert_current_payment(sale, payment)
            reference = payment.referencia_externa
            if reference is None:
                raise PaymentError(409, "El pago aun no tiene Checkout; solicite la sesion con el mismo id_pago")
            if reference.startswith("pi_"):
                intent = self.stripe.retrieve_payment_intent(reference)
                return self._apply_intent(sale, payment, intent)
            if not reference.startswith("cs_test_"):
                raise PaymentError(409, "Referencia Stripe no reconocida")
            session = self.stripe.retrieve_checkout_session(reference)
            self._validate_checkout(sale, payment, session)
            if session["payment_status"] == "paid":
                if session["status"] != "complete":
                    raise PaymentError(409, "Stripe no confirmo Checkout completo")
                intent = self._field(session, "payment_intent")
                if isinstance(intent, str):
                    intent = self.stripe.retrieve_payment_intent(intent)
                if not intent:
                    raise PaymentError(409, "Checkout pagado no tiene PaymentIntent verificable")
                # Validar PI sin comparar su ID con referencia_externa (que es CS).
                expected = {"id_venta": str(sale.id_venta), "id_pago": str(payment.id_pago),
                            "clave_idempotencia": str(payment.clave_idempotencia)}
                metadata = self._field(intent, "metadata", {}) or {}
                if (self._field(intent, "livemode") is not False
                        or self._field(intent, "object") != "payment_intent"
                        or not str(self._field(intent, "id", "")).startswith("pi_")
                        or self._field(intent, "status") != "succeeded"
                        or self._field(intent, "amount") != int(payment.monto * 100)
                        or self._field(intent, "amount_received") != int(payment.monto * 100)
                        or self._field(intent, "currency") != payment.moneda.lower()
                        or any(self._field(metadata, k) != v for k, v in expected.items())):
                    raise PaymentError(409, "PaymentIntent de Checkout no corresponde a este pago TEST")
                self._complete(sale, payment)
            elif session["status"] == "expired":
                payment.estado = "EXPIRADO"
            elif (session["status"] == "open" and session["payment_status"] == "unpaid" and sale.fecha_expiracion_pago is not None
                    and sale.fecha_expiracion_pago <= self.now()):
                expired = self.stripe.expire_checkout_session(reference, payment.clave_idempotencia)
                self._validate_checkout(sale, payment, expired)
                if expired["status"] != "expired" or expired["payment_status"] != "unpaid":
                    raise PaymentError(409, "Checkout aun no pudo cerrarse; sincronice el mismo pago")
                payment.estado = "EXPIRADO"
            payment.updated_at = self.now()
            return self._data(sale, payment)
        return self._transaction(operation)
