"""CU24. Orden de bloqueos: venta, devolucion, pagos, inventarios."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
from uuid import uuid4
from sqlalchemy import select, func
from app.models.returns import Return, ReturnDetail, Refund
from app.models.payment import Payment
from app.models.sale import Sale
from app.models.inventory_movement import InventoryMovement
from app.models.inventory_movement_detail import InventoryMovementDetail
from app.repositories.returns import ReturnsRepository
from app.services.payments import PaymentsService, PaymentError

class ReturnsService(PaymentsService):
    def __init__(self, db, stripe_service=None):
        super().__init__(db, stripe_service)
        self.returns = ReturnsRepository(db)

    def _sale(self, user, sale_id, staff=False):
        sale = self.repository.lock_sale(sale_id)
        if sale is None:
            raise PaymentError(404, "Compra no encontrada")
        if not staff:
            client = self.clients.get_client(user.id_usuario)
            if user.rol.upper() != "CLIENTE" or client is None or sale.id_cliente != client.id_cliente:
                raise PaymentError(404, "Compra no encontrada")
        else:
            self._assignment(user, sale.id_sucursal)
        return sale

    def _assignment(self, user, branch_id):
        if user.rol.upper() not in {"CAJERO", "ADMINISTRADOR"}:
            raise PaymentError(403, "Se requiere personal autorizado")
        employee = self.staff.get_employee(user.id_usuario)
        branches = self.staff.branches(employee.id_empleado, for_update=True) if employee else []
        assignment = next((b for b in branches if b["id_sucursal"] == branch_id), None)
        if assignment is None:
            raise PaymentError(403, "Se requiere asignacion activa a la sucursal")
        return assignment["id_empleado_sucursal"]

    def _context_return(self, user, return_id, staff=False):
        row = self.db.get(Return, return_id)
        if row is None:
            raise PaymentError(404, "Devolucion no encontrada")
        sale = self._sale(user, row.id_venta, staff)
        return sale, self.returns.lock(return_id)

    def _data_return(self, row):
        def data(obj):
            return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
        payment = self._original_payment(row.id_venta)
        safe_payment = {name: getattr(payment, name) for name in (
            "id_pago", "medio", "proveedor", "entorno", "estado", "monto", "moneda"
        )} if payment else None
        return {**data(row), "pago": safe_payment, "lineas": [data(x) for x in self.returns.details(row.id_devolucion)],
                "reembolsos": [data(x) for x in self.returns.refunds(row.id_devolucion)]}

    def get_return(self, user, return_id, staff=False):
        return self._transaction(lambda: self._data_return(self._context_return(user, return_id, staff)[1]))

    def list_returns(self, user, estado=None, limit=20, offset=0):
        def operation():
            if user.rol.upper() not in {"CAJERO", "ADMINISTRADOR"}:
                raise PaymentError(403, "Se requiere personal autorizado")
            employee = self.staff.get_employee(user.id_usuario)
            branches = self.staff.branches(employee.id_empleado) if employee else []
            stmt = select(Return).join(Sale, Sale.id_venta == Return.id_venta).where(
                Sale.id_sucursal.in_([b["id_sucursal"] for b in branches]))
            if estado:
                stmt = stmt.where(Return.estado == estado)
            rows = self.db.scalars(stmt.order_by(Return.created_at.desc(), Return.id_devolucion.desc())
                .limit(limit).offset(offset)).all()
            return [self._data_return(row) for row in rows]
        return self._transaction(operation)

    @staticmethod
    def _line_limit(sale, item, items, quantity, previous=0):
        # Incluye descuento global: repartir centavos por linea y unidad;
        # la ultima porcion recupera el residuo para una devolucion total exacta.
        total_lines = sum((x.subtotal_linea for x in items), Decimal(0))
        if total_lines <= 0 or sale.total < 0 or sale.total > total_lines:
            raise PaymentError(409, "Importes de venta inconsistentes")
        before = sum((x.subtotal_linea for x in items if x.id_variante_producto < item.id_variante_producto), Decimal(0))
        def prefix(value):
            return (sale.total * value / total_lines).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        allocation = prefix(before + item.subtotal_linea) - prefix(before)
        def units(n):
            return (allocation * n / item.cantidad).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        return allocation, units(previous + quantity) - units(previous)

    def request(self, user, sale_id, payload, key, cancellation=False):
        def operation():
            sale = self._sale(user, sale_id)
            kind = "CANCELACION" if cancellation else "DEVOLUCION"
            previous = self.db.scalar(select(Return).where(Return.clave_idempotencia == key))
            if previous:
                if (previous.id_venta != sale_id or previous.tipo != kind or previous.motivo != payload.motivo
                        or previous.id_usuario_solicitante != user.id_usuario):
                    raise PaymentError(409, "Clave de idempotencia usada por otra solicitud")
                expected = sorted((x.id_detalle_venta, x.cantidad) for x in payload.lineas) if not cancellation else []
                items = self.repository.items(sale_id)
                ids = {x.id_variante_producto: x.id_detalle_venta for x in items}
                actual = sorted((ids[x.id_variante_producto], x.cantidad) for x in self.returns.details(previous.id_devolucion))
                if (previous.id_venta != sale_id or previous.tipo != kind or previous.motivo != payload.motivo
                        or previous.id_usuario_solicitante != user.id_usuario or expected != actual):
                    raise PaymentError(409, "Clave de idempotencia usada por otra solicitud")
                return self._data_return(previous)
            if cancellation:
                if sale.estado != "PENDIENTE":
                    raise PaymentError(409, "Solo puede cancelarse una venta PENDIENTE")
                active = self.db.scalar(select(Return).where(Return.id_venta == sale_id,
                    Return.tipo == kind, Return.estado != "RECHAZADA"))
                if active:
                    raise PaymentError(409, "La venta ya tiene una cancelacion activa")
                movement = self.repository.lock_movement(sale_id)
                if movement and movement.estado == "CONFIRMADO":
                    raise PaymentError(409, "Ya existe una salida fisica; corresponde devolucion")
            elif sale.estado != "COMPLETADA":
                raise PaymentError(409, "Solo puede devolverse una venta COMPLETADA")
            items = self.repository.items(sale_id)
            selected = []
            if not cancellation:
                by_id = {x.id_detalle_venta: x for x in items}
                for line in payload.lineas:
                    item = by_id.get(line.id_detalle_venta)
                    if item is None or line.cantidad <= 0 or line.cantidad > item.cantidad - self.returns.used(sale_id, item.id_variante_producto):
                        raise PaymentError(422, "Linea o cantidad no disponible para devolucion")
                    selected.append((item, line.cantidad))
            if not cancellation:
                desired = sorted((item.id_variante_producto, quantity) for item, quantity in selected)
                active_rows = self.db.scalars(select(Return).where(Return.id_venta == sale_id,
                    Return.tipo == "DEVOLUCION", Return.estado.in_(("SOLICITADA", "APROBADA")))).all()
                for active_row in active_rows:
                    actual = sorted((d.id_variante_producto, d.cantidad) for d in self.returns.details(active_row.id_devolucion))
                    if desired == actual:
                        raise PaymentError(409, "Ya existe una solicitud activa para estas lineas y cantidades")
            now = self.now()
            row = self.returns.add(Return, id_venta=sale_id, tipo=kind, estado="SOLICITADA",
                motivo=payload.motivo, id_usuario_solicitante=user.id_usuario, clave_idempotencia=key,
                created_at=now, updated_at=now)
            for item, quantity in selected:
                _, maximum = self._line_limit(sale, item, items, quantity, self.returns.used(sale_id, item.id_variante_producto))
                self.returns.add(ReturnDetail, id_devolucion=row.id_devolucion, id_venta=sale_id,
                    id_variante_producto=item.id_variante_producto, cantidad=quantity,
                    cantidad_reintegrar=0, importe_restitucion=maximum, created_at=now, updated_at=now)
            return self._data_return(row)
        return self._transaction(operation)

    def _original_payment(self, sale_id, *, lock=False):
        statement = select(Payment).where(Payment.id_venta == sale_id,
            Payment.estado.in_(("APROBADO", "REEMBOLSADO")))
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        rows = self.db.scalars(statement).all()
        if len(rows) > 1:
            raise PaymentError(409, "La venta tiene varios pagos cobrados; requiere conciliacion")
        return rows[0] if rows else None

    def _paid(self, sale):
        return self._original_payment(sale.id_venta, lock=True)

    def review(self, user, return_id, payload):
        def operation():
            sale, row = self._context_return(user, return_id, True)
            if row.id_usuario_solicitante == user.id_usuario:
                raise PaymentError(403, "No puede resolver su propia solicitud")
            if row.estado != "SOLICITADA":
                raise PaymentError(409, "La solicitud ya fue revisada")
            details = self.returns.details(return_id)
            if payload.resultado == "RECHAZADA":
                if payload.lineas:
                    raise PaymentError(422, "Un rechazo no admite importes ni reintegros")
            elif row.tipo == "CANCELACION":
                if payload.lineas or sale.estado != "PENDIENTE":
                    raise PaymentError(409, "Cancelacion incompatible con la venta")
            else:
                if sale.estado != "COMPLETADA":
                    raise PaymentError(409, "Venta no completada")
                approved = {x.id_variante_producto: x for x in payload.lineas}
                if len(approved) != len(payload.lineas) or set(approved) != {x.id_variante_producto for x in details}:
                    raise PaymentError(422, "Debe revisar todas las lineas exactamente una vez")
                for detail in details:
                    line = approved[detail.id_variante_producto]
                    # Preservar el limite calculado por el servidor al solicitar;
                    # el personal solo puede reducirlo, nunca redistribuirlo.
                    maximum = detail.importe_restitucion
                    if line.cantidad_reintegrar > detail.cantidad or line.importe_restitucion > maximum:
                        raise PaymentError(422, "Reintegro o importe supera lo autorizado por la compra")
                    detail.cantidad_reintegrar = line.cantidad_reintegrar
                    detail.importe_restitucion = line.importe_restitucion
                    detail.updated_at = self.now()
            now = self.now()
            row.estado = payload.resultado
            row.id_usuario_resolutor = user.id_usuario
            row.fecha_resolucion = now
            row.updated_at = now
            if row.estado == "APROBADA":
                payment = self._paid(sale)
                amount = sale.total if row.tipo == "CANCELACION" else sum((d.importe_restitucion for d in details), Decimal(0))
                if amount > 0 and payment is None and row.tipo != "CANCELACION":
                    raise PaymentError(409, "No existe pago aprobado para reembolsar")
                if payment and amount > 0:
                    if payment.moneda != sale.moneda or amount + self.returns.reserved_money(payment.id_pago) > payment.monto:
                        raise PaymentError(409, "El reembolso supera el saldo pagado")
                    self.returns.add(Refund, id_venta=sale.id_venta, id_pago=payment.id_pago,
                        id_devolucion=return_id, estado="PENDIENTE", monto=amount,
                        clave_idempotencia=uuid4(), created_at=now, updated_at=now)
            self.db.flush()
            return self._data_return(row)
        return self._transaction(operation)

    def _close_pending_payments(self, sale):
        for payment in self.db.scalars(select(Payment).where(Payment.id_venta == sale.id_venta,
                Payment.estado == "PENDIENTE").with_for_update()).all():
            if payment.proveedor == "STRIPE":
                self._stripe_payment(payment)
                ref = payment.referencia_externa
                if ref is None:
                    raise PaymentError(409, "Pago Stripe sin referencia requiere conciliacion antes de cancelar")
                if ref.startswith("cs_test_"):
                    session = self.stripe.retrieve_checkout_session(ref)
                    self._validate_checkout(sale, payment, session)
                    if session["status"] == "open":
                        session = self.stripe.expire_checkout_session(ref, payment.clave_idempotencia)
                        self._validate_checkout(sale, payment, session)
                    if session["status"] != "expired" or session["payment_status"] != "unpaid":
                        raise PaymentError(409, "Checkout cobrado o incierto; sincronice el pago")
                elif ref.startswith("pi_"):
                    intent = self.stripe.retrieve_payment_intent(ref)
                    self._validate_intent(sale, payment, intent)
                    if intent["status"] != "canceled":
                        intent = self.stripe.cancel_payment_intent(ref, payment.clave_idempotencia)
                        self._validate_intent(sale, payment, intent)
                    if intent["status"] != "canceled":
                        raise PaymentError(409, "PaymentIntent aun cobrable")
                else:
                    raise PaymentError(409, "Referencia Stripe invalida")
            payment.estado = "CANCELADO"
            payment.updated_at = self.now()

    def _refund_intent(self, sale, payment):
        self._stripe_payment(payment)
        reference = payment.referencia_externa or ""
        if reference.startswith("cs_test_"):
            session = self.stripe.retrieve_checkout_session(reference)
            self._validate_checkout(sale, payment, session)
            if session["status"] != "complete" or session["payment_status"] != "paid":
                raise PaymentError(409, "Checkout no cobrado")
            intent = self._field(session, "payment_intent")
            reference = intent if isinstance(intent, str) else self._field(intent, "id", "")
        if not reference.startswith("pi_"):
            raise PaymentError(409, "PaymentIntent no verificable")
        intent = self.stripe.retrieve_payment_intent(reference)
        metadata = self._field(intent, "metadata", {})
        expected = {"id_venta": str(sale.id_venta), "id_pago": str(payment.id_pago),
                    "clave_idempotencia": str(payment.clave_idempotencia)}
        if (self._field(intent, "livemode") is not False or self._field(intent, "id") != reference
                or self._field(intent, "status") != "succeeded" or self._field(intent, "amount_received") != int(payment.monto * 100)
                or self._field(intent, "currency") != payment.moneda.lower()
                or any(self._field(metadata, k) != v for k, v in expected.items())):
            raise PaymentError(409, "Pago Stripe TEST no verificable")
        return reference

    def _stripe_refund(self, sale, payment, refund):
        intent_id = self._refund_intent(sale, payment)
        intent = self.stripe.retrieve_payment_intent(intent_id)
        if self._field(intent, "livemode") is not False:
            raise PaymentError(409, "PaymentIntent debe pertenecer a TEST")
        charge_id = self._field(intent, "latest_charge")
        if not isinstance(charge_id, str) or not charge_id.startswith("ch_"):
            raise PaymentError(409, "Cargo original no verificable")
        charge = self.stripe.retrieve_charge(charge_id)
        if (self._field(charge, "livemode") is not False or self._field(charge, "id") != charge_id
                or self._field(charge, "payment_intent") != intent_id
                or self._field(charge, "paid") is not True or self._field(charge, "captured") is not True
                or self._field(charge, "currency") != payment.moneda.lower()
                or self._field(charge, "amount") != int(payment.monto * 100)
                or not isinstance(self._field(charge, "amount_refunded"), int)
                or not 0 <= self._field(charge, "amount_refunded") <= int(payment.monto * 100)):
            raise PaymentError(409, "Cargo Stripe TEST no verificable")
        def valid(remote):
            return (str(self._field(remote, "id", "")).startswith("re_")
                and self._field(remote, "payment_intent") == intent_id
                and self._field(remote, "charge") == charge_id
                and self._field(remote, "amount") == int(refund.monto * 100)
                and self._field(remote, "currency") == payment.moneda.lower()
                and self._field(remote, "status") in {"succeeded", "pending", "requires_action", "failed", "canceled"})
        if refund.referencia_externa:
            remote = self.stripe.retrieve_refund(refund.referencia_externa)
            if not valid(remote) or self._field(remote, "id") != refund.referencia_externa:
                raise PaymentError(409, "Reembolso Stripe TEST no verificable")
            return remote
        existing = self.stripe.list_refunds(intent_id)
        candidates = []
        accounted_total = 0
        unaccounted = False
        for remote in existing:
            claimed = self.db.scalar(select(Refund).where(Refund.id_pago == payment.id_pago,
                Refund.referencia_externa == self._field(remote, "id"), Refund.id_reembolso != refund.id_reembolso))
            if claimed is not None:
                if (claimed.estado == "APROBADO" and self._field(remote, "status") == "succeeded"
                        and self._field(remote, "payment_intent") == intent_id
                        and self._field(remote, "charge") == charge_id
                        and self._field(remote, "currency") == payment.moneda.lower()
                        and self._field(remote, "amount") == int(claimed.monto * 100)):
                    accounted_total += self._field(remote, "amount")
                else:
                    unaccounted = True
                continue
            if not valid(remote):
                unaccounted = True
                continue
            metadata = self._field(remote, "metadata", {})
            linked = (self._field(metadata, "id_reembolso") == str(refund.id_reembolso)
                and self._field(metadata, "clave_idempotencia") == str(refund.clave_idempotencia))
            # Recuperacion legacy inequivoca: unico refund total del pago y
            # ninguna otra autorizacion local que pueda ser su propietaria.
            legacy = (len(existing) == 1 and refund.monto == payment.monto
                and self._field(remote, "status") == "succeeded"
                and self._field(charge, "amount_refunded") == int(payment.monto * 100)
                and self.returns.reserved_money(payment.id_pago, refund.id_reembolso) == 0)
            if linked or legacy:
                candidates.append(remote)
            else:
                unaccounted = True
        if len(candidates) == 1:
            if (self._field(candidates[0], "status") == "succeeded"
                    and self._field(charge, "amount_refunded") < int(refund.monto * 100)):
                raise PaymentError(409, "Refund succeeded no coincide con el saldo reembolsado del cargo")
            return candidates[0]
        refunded = self._field(charge, "amount_refunded")
        if (candidates or unaccounted or refunded != accounted_total
                or refunded + int(refund.monto * 100) > int(payment.monto * 100)):
            # Nunca adivinar la atribucion ni recrear ante un cargo ya reembolsado.
            raise PaymentError(409, "Reembolsos existentes requieren conciliacion; no crear otro Refund")
        if self.now() - refund.created_at >= timedelta(hours=23):
            raise PaymentError(409, "Reembolso sin referencia requiere conciliacion; no recrear")
        remote = self.stripe.create_refund(payment_intent=intent_id,
            amount=int(refund.monto * 100), key=refund.clave_idempotencia, refund_id=refund.id_reembolso)
        if not valid(remote):
            raise PaymentError(409, "Reembolso Stripe TEST no verificable")
        return remote

    def _validate_inventory(self, sale, row, details):
        if row.tipo == "CANCELACION":
            held = sale.stock_comprometido or sale.id_reserva is not None
            items = self.repository.items(sale.id_venta) if held else []
            if held and not items:
                raise PaymentError(409, "Venta comprometida sin detalles")
            if sale.id_reserva is not None:
                reservation = self.staff.get_reservation(sale.id_reserva, for_update=True)
                if reservation is None or reservation.estado != "ATENDIDA" or reservation.id_sucursal != sale.id_sucursal:
                    raise PaymentError(409, "Reserva asociada inconsistente")
            expected = {x.id_variante_producto: x.cantidad for x in items}
        else:
            sold = {x.id_variante_producto: x for x in self.repository.items(sale.id_venta)}
            for detail in details:
                item = sold.get(detail.id_variante_producto)
                if (item is None or detail.cantidad <= 0 or detail.cantidad_reintegrar < 0
                        or detail.cantidad_reintegrar > detail.cantidad
                        or self.returns.used(sale.id_venta, detail.id_variante_producto) > item.cantidad):
                    raise PaymentError(409, "Unidades devueltas inconsistentes")
            expected = {x.id_variante_producto: x.cantidad_reintegrar for x in details if x.cantidad_reintegrar > 0}
            if expected:
                outbound = self.repository.lock_movement(sale.id_venta)
                if (outbound is None or outbound.estado != "CONFIRMADO" or outbound.tipo_movimiento != "VENTA"
                        or outbound.id_sucursal_origen != sale.id_sucursal):
                    raise PaymentError(409, "No existe salida fisica confirmada")
                movement_items = {x.id_variante_producto: x.cantidad for x in self.repository.movement_items(outbound.id_movimiento_inventario)}
                if movement_items != {k: v.cantidad for k, v in sold.items()}:
                    raise PaymentError(409, "Salida fisica incompatible con la venta")
        inventories = {i.id_variante_producto: i for i in self.staff.inventories(
            sale.id_sucursal, list(expected), for_update=True)} if expected else {}
        for variant, quantity in expected.items():
            inv = inventories.get(variant)
            if (inv is None or inv.stock_actual < inv.stock_reservado
                    or (row.tipo == "CANCELACION" and inv.stock_reservado < quantity)):
                raise PaymentError(409, "Inventario inexistente o inconsistente")

    def process(self, user, return_id, payload):
        def operation():
            sale, row = self._context_return(user, return_id, True)
            if row.id_usuario_solicitante == user.id_usuario:
                raise PaymentError(403, "No puede procesar su propia solicitud")
            if row.estado == "PROCESADA":
                return self._data_return(row)
            if row.estado != "APROBADA":
                raise PaymentError(409, "Debe aprobar la solicitud antes de procesar")
            details = self.returns.details(return_id)
            assignment = self._assignment(user, sale.id_sucursal)
            if row.tipo == "CANCELACION":
                if sale.estado != "PENDIENTE":
                    raise PaymentError(409, "La venta ya no puede cancelarse")
                movement = self.repository.lock_movement(sale.id_venta)
                if movement and movement.estado == "CONFIRMADO":
                    raise PaymentError(409, "Ya hubo salida fisica")
                self._close_pending_payments(sale)
            elif sale.estado != "COMPLETADA":
                raise PaymentError(409, "Venta no completada")
            self._validate_inventory(sale, row, details)
            payment = self._paid(sale)
            refunds = self.returns.refunds(return_id)
            if len(refunds) > 1:
                raise PaymentError(409, "Multiples reembolsos requieren conciliacion")
            refund = refunds[0] if refunds else None
            required_amount = sale.total if row.tipo == "CANCELACION" else sum(
                (d.importe_restitucion for d in details), Decimal(0))
            if required_amount > 0 and payment is None and (refund or row.tipo == "DEVOLUCION"):
                raise PaymentError(409, "No existe pago aprobado asociado a la venta para reembolsar")
            if refund:
                authorized = sale.total if row.tipo == "CANCELACION" else sum((d.importe_restitucion for d in details), Decimal(0))
                if (payment is None or refund.id_pago != payment.id_pago or refund.monto > authorized
                        or refund.monto + self.returns.reserved_money(payment.id_pago, refund.id_reembolso) > payment.monto
                        or refund.estado == "RECHAZADO"):
                    raise PaymentError(409, "Reembolso incompatible o saldo insuficiente")
                if refund.estado == "PENDIENTE":
                    if payment.proveedor == "STRIPE":
                        if payload.referencia_manual:
                            raise PaymentError(422, "Stripe no admite referencia manual")
                        remote = self._stripe_refund(sale, payment, refund)
                        refund.referencia_externa = remote["id"]
                        refund.updated_at = self.now()
                        if remote["status"] != "succeeded":
                            # Persistir referencia incluso si sigue pendiente o fallo.
                            # No crear un segundo reembolso para esta autorizacion.
                            if remote["status"] in {"failed", "canceled"}:
                                refund.estado = "RECHAZADO"
                            self.db.flush()
                            return self._data_return(row)
                    elif (payment.proveedor, payment.entorno, payment.medio) in {
                            ("MANUAL", "LOCAL", "EFECTIVO"), ("MANUAL", "LOCAL", "QR")}:
                        if not payload.referencia_manual:
                            raise PaymentError(422, "Debe registrar comprobante de reembolso manual")
                        refund.referencia_externa = payload.referencia_manual
                    else:
                        raise PaymentError(409, "Medio de reembolso no admitido")
                    refund.estado = "APROBADO"
                    refund.fecha_aprobacion = (datetime.fromtimestamp(self._field(remote, "created"), timezone.utc).replace(tzinfo=None)
                        if payment.proveedor == "STRIPE" and isinstance(self._field(remote, "created"), (int, float)) else self.now())
                    refund.id_usuario_responsable = user.id_usuario
                    refund.updated_at = self.now()
                # SessionLocal usa autoflush=False: persistir el estado antes
                # de consultar sumas y marcar el pago totalmente reembolsado.
                self.db.flush()
                if self.returns.reserved_money(payment.id_pago) == payment.monto:
                    # Solo los importes ya APROBADOS cuentan como dinero devuelto.
                    approved = self.db.scalar(select(func.coalesce(
                        func.sum(Refund.monto), 0)).where(
                            Refund.id_pago == payment.id_pago, Refund.estado == "APROBADO"))
                    if approved == payment.monto:
                        payment.estado = "REEMBOLSADO"
                        payment.updated_at = self.now()
            elif payment and (sale.total if row.tipo == "CANCELACION" else sum(d.importe_restitucion for d in details)) > 0:
                raise PaymentError(409, "Falta el reembolso autorizado")
            now = self.now()
            if row.tipo == "CANCELACION":
                if sale.stock_comprometido or sale.id_reserva is not None:
                    items = self.repository.items(sale.id_venta)
                    inventories = {i.id_variante_producto: i for i in self.staff.inventories(
                        sale.id_sucursal, [x.id_variante_producto for x in items], for_update=True)}
                    if not items:
                        raise PaymentError(409, "Venta sin detalles")
                    for item in items:
                        inv = inventories.get(item.id_variante_producto)
                        if inv is None or inv.stock_reservado < item.cantidad or inv.stock_reservado > inv.stock_actual:
                            raise PaymentError(409, "Stock comprometido inconsistente")
                        inv.stock_reservado -= item.cantidad
                        inv.updated_at = now
                if movement:
                    movement.estado = "ANULADO"
                    movement.updated_at = now
                sale.stock_comprometido = False
                sale.estado = "ANULADA"
                sale.updated_at = now
            else:
                sold = {x.id_variante_producto: x for x in self.repository.items(sale.id_venta)}
                for detail in details:
                    if self.returns.used(sale.id_venta, detail.id_variante_producto) > sold[detail.id_variante_producto].cantidad:
                        raise PaymentError(409, "Unidades devueltas inconsistentes")
                reintegrate = [x for x in details if x.cantidad_reintegrar > 0]
                if reintegrate:
                    outbound = self.repository.lock_movement(sale.id_venta)
                    if outbound is None or outbound.estado != "CONFIRMADO" or outbound.tipo_movimiento != "VENTA":
                        raise PaymentError(409, "No existe salida fisica confirmada")
                    inventories = {i.id_variante_producto: i for i in self.staff.inventories(
                        sale.id_sucursal, [x.id_variante_producto for x in reintegrate], for_update=True)}
                    for detail in reintegrate:
                        inv = inventories.get(detail.id_variante_producto)
                        if inv is None or inv.stock_actual < inv.stock_reservado:
                            raise PaymentError(409, "Inventario inexistente o inconsistente")
                        inv.stock_actual += detail.cantidad_reintegrar
                        inv.updated_at = now
                    entry = self.returns.add(InventoryMovement, id_sucursal_destino=sale.id_sucursal,
                        id_empleado_sucursal=assignment, tipo_movimiento="ENTRADA", estado="CONFIRMADO",
                        motivo=f"Devolucion CU24 {return_id}", fecha_movimiento=now, created_at=now, updated_at=now)
                    for detail in reintegrate:
                        self.returns.add(InventoryMovementDetail, id_movimiento_inventario=entry.id_movimiento_inventario,
                            id_variante_producto=detail.id_variante_producto, cantidad=detail.cantidad_reintegrar)
                    row.id_movimiento_inventario = entry.id_movimiento_inventario
            row.estado = "PROCESADA"
            row.fecha_procesamiento = now
            row.updated_at = now
            self.db.flush()
            return self._data_return(row)
        return self._transaction(operation)
