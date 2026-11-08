"""Pruebas unitarias focalizadas para CU17 — Procesar cambio de talla o producto con pago online y presencial."""
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import MagicMock, patch
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models.branch import Branch
from app.models.branch_inventory import BranchInventory
from app.models.client import Client
from app.models.color import Color
from app.models.inventory_movement import InventoryMovement
from app.models.inventory_movement_detail import InventoryMovementDetail
from app.models.payment import Payment
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.returns import Refund, Return, ReturnDetail
from app.models.sale import Sale
from app.models.sale_detail import SaleDetail
from app.models.size import Size
from app.models.user import User
from app.schemas.returns import ConfirmPaymentRequest, ProcessExchangeRequest
from app.services.payments import PaymentError, PaymentsService
from app.services.returns import ReturnsService


class TestCU17ProcesarCambio(TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        for model in (
            User,
            Client,
            Branch,
            Product,
            Size,
            Color,
            ProductVariant,
            Sale,
            SaleDetail,
            BranchInventory,
            Payment,
            Return,
            ReturnDetail,
            Refund,
            InventoryMovement,
            InventoryMovementDetail,
        ):
            model.__table__.create(self.engine)

        self.db = Session(self.engine)
        self.db.autoflush = False
        self.now = PaymentsService.now()

        # Mock de Stripe Service
        self.mock_stripe = MagicMock()

        # Usuarios
        self.db.add_all([
            User(id_usuario=11, id_rol=2, correo="cajero@store.com", nombre="Carlos", apellido="Cajero", password_hash="x", estado=True),
            User(id_usuario=12, id_rol=3, correo="cliente@store.com", nombre="Ana", apellido="Cliente", password_hash="x", estado=True),
            Client(id_cliente=7, id_usuario=12, empresa_id=1),
            Branch(id_sucursal=2, id_ciudad=1, empresa_id=1, nombre="Sucursal Central", direccion="Calle 1", telefono="70000000"),
            Size(id_talla=1, empresa_id=1, nombre="M", estado=True),
            Size(id_talla=2, empresa_id=1, nombre="L", estado=True),
            Color(id_color=1, empresa_id=1, nombre="Negro", codigo_hex="#000000", estado=True),
            Color(id_color=2, empresa_id=1, nombre="Azul", codigo_hex="#0000FF", estado=True),
        ])

        # Productos:
        # P10: Vestido base (150.00)
        # P20: Chaqueta mayor precio (200.00)
        # P30: Blusa menor precio (100.00)
        self.db.add_all([
            Product(id_producto=10, id_categoria=1, empresa_id=1, nombre="Vestido Floral", seccion="MUJER", precio=Decimal("150.00"), estado=True),
            Product(id_producto=20, id_categoria=1, empresa_id=1, nombre="Chaqueta Cuero", seccion="MUJER", precio=Decimal("200.00"), estado=True),
            Product(id_producto=30, id_categoria=1, empresa_id=1, nombre="Blusa Seda", seccion="MUJER", precio=Decimal("100.00"), estado=True),
        ])

        # Variantes:
        # 101: Original P10 M Negro
        # 102: Reemplazo mismo precio P10 L Azul (150.00)
        # 201: Reemplazo mayor precio P20 M Negro (200.00)
        # 202: Reemplazo sin stock P20 L Negro (200.00)
        # 301: Reemplazo menor precio P30 M Azul (100.00)
        self.db.add_all([
            ProductVariant(id_variante_producto=101, id_producto=10, id_talla=1, id_color=1, empresa_id=1, sku="VES-M-NEG", estado=True),
            ProductVariant(id_variante_producto=102, id_producto=10, id_talla=2, id_color=2, empresa_id=1, sku="VES-L-AZU", estado=True),
            ProductVariant(id_variante_producto=201, id_producto=20, id_talla=1, id_color=1, empresa_id=1, sku="CHQ-M-NEG", estado=True),
            ProductVariant(id_variante_producto=202, id_producto=20, id_talla=2, id_color=1, empresa_id=1, sku="CHQ-L-NEG", estado=True),
            ProductVariant(id_variante_producto=301, id_producto=30, id_talla=1, id_color=2, empresa_id=1, sku="BLU-M-AZU", estado=True),
        ])

        # Inventarios en sucursal 2
        self.db.add_all([
            BranchInventory(id_sucursal=2, id_variante_producto=101, empresa_id=1, stock_actual=10, stock_reservado=0, stock_minimo=1),
            BranchInventory(id_sucursal=2, id_variante_producto=102, empresa_id=1, stock_actual=5, stock_reservado=0, stock_minimo=1),
            BranchInventory(id_sucursal=2, id_variante_producto=201, empresa_id=1, stock_actual=5, stock_reservado=0, stock_minimo=1),
            BranchInventory(id_sucursal=2, id_variante_producto=202, empresa_id=1, stock_actual=0, stock_reservado=0, stock_minimo=1),
            BranchInventory(id_sucursal=2, id_variante_producto=301, empresa_id=1, stock_actual=5, stock_reservado=0, stock_minimo=1),
        ])

        # Venta completada
        completed_time = self.now - timedelta(hours=4)
        self.db.add(Sale(
            id_venta=10,
            empresa_id=1,
            numero_venta="VTA-CU17-001",
            id_sucursal=2,
            id_empleado=5,
            id_cliente=7,
            canal="PRESENCIAL",
            moneda="BOB",
            estado="COMPLETADA",
            subtotal=Decimal("150.00"),
            descuento_total=Decimal("0.00"),
            total=Decimal("150.00"),
            stock_comprometido=False,
            fecha_venta=completed_time - timedelta(minutes=10),
            fecha_completada=completed_time,
            created_at=completed_time,
            updated_at=completed_time,
        ))
        self.db.add(SaleDetail(
            id_detalle_venta=101,
            empresa_id=1,
            id_venta=10,
            id_variante_producto=101,
            cantidad=1,
            precio_unitario=Decimal("150.00"),
            descuento_unitario=Decimal("0.00"),
            subtotal_linea=Decimal("150.00"),
        ))
        self.db.add(Payment(
            id_pago=10,
            empresa_id=1,
            id_venta=10,
            medio="EFECTIVO",
            proveedor="MANUAL",
            entorno="LOCAL",
            estado="APROBADO",
            monto=Decimal("150.00"),
            moneda="BOB",
            clave_idempotencia=uuid4(),
            fecha_aprobacion=completed_time,
            created_at=completed_time,
            updated_at=completed_time,
        ))
        self.db.commit()

        self.cashier = NS(id_usuario=11, rol="CAJERO", empresa_id=1)
        self.client = NS(id_usuario=12, rol="CLIENTE", empresa_id=1)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _create_approved_exchange(self, ret_id: int, repl_variant_id: int, cant=1, precio_orig="150.00", estado_fisico="OPTIMO", etiquetas_intactas=True) -> Return:
        ret = Return(
            id_devolucion=ret_id,
            id_venta=10,
            empresa_id=1,
            id_usuario_solicitante=12,
            tipo="CAMBIO",
            motivo="Cambio por otra prenda/talla",
            estado="APROBADA",
            modalidad_entrega="ENTREGA_EN_TIENDA",
            id_usuario_evaluador=11,
            fecha_evaluacion_inicial=self.now,
            fecha_seleccion_modalidad=self.now,
            id_usuario_receptor=11,
            fecha_recepcion=self.now,
            id_usuario_inspector=11,
            fecha_inspeccion=self.now,
            estado_fisico=estado_fisico,
            etiquetas_intactas=etiquetas_intactas,
            correspondencia_compra=True,
            id_usuario_resolutor=11,
            fecha_resolucion=self.now,
            clave_idempotencia=uuid4(),
            created_at=self.now,
            updated_at=self.now,
        )
        self.db.add(ret)
        self.db.flush()
        detail = ReturnDetail(
            id_detalle_devolucion=ret_id * 10,
            id_devolucion=ret_id,
            id_venta=10,
            empresa_id=1,
            id_variante_producto=101,
            id_variante_reemplazo=repl_variant_id,
            cantidad=cant,
            cantidad_reintegrar=0,
            importe_restitucion=Decimal("0.00"),
            cantidad_reemplazo=cant,
            precio_original_reconocido=Decimal(precio_orig),
            precio_reemplazo_estimado=Decimal(precio_orig),
            diferencia_precio_estimada=Decimal("0.00"),
            created_at=self.now,
            updated_at=self.now,
        )
        self.db.add(detail)
        self.db.commit()
        return ret

    def test_cu17_flujo_pago_online_stripe_pago_pendiente_y_finalizacion_unica(self):
        """Prueba 1: Verificación de pago pendiente, pago online con Stripe Checkout TEST,
        verificación segura de servidor, finalización del cambio e idempotencia sin duplicar inventario."""
        service = ReturnsService(self.db, self.mock_stripe)

        with patch.object(service, "_assignment", return_value=1):
            # 1. Crear solicitud aprobada con diferencia positiva (P20 precio 200 vs P10 150 -> dif +50)
            self._create_approved_exchange(ret_id=1, repl_variant_id=201)

            # 2. Cajero confirma la diferencia económica definitiva
            diff_res = service.confirm_exchange_difference(self.cashier, 1)
            self.assertEqual(diff_res["diferencia_definitiva"], Decimal("50.00"))
            self.assertEqual(diff_res["estado_pago_adicional"], "PENDIENTE")
            # Verificar que NO se crearon movimientos de inventario todavía
            movements = self.db.scalars(select(InventoryMovement)).all()
            self.assertEqual(len(movements), 0)

            # 3. Intentar finalizar sin haber confirmado el pago debe fallar
            with self.assertRaises(PaymentError) as ctx_nopay:
                service.process_exchange(self.cashier, 1, ProcessExchangeRequest())
            self.assertIn(ctx_nopay.exception.status_code, (409, 422))
            self.assertEqual(len(self.db.scalars(select(InventoryMovement)).all()), 0)

            # 4. Cliente inicia sesión de Stripe Checkout TEST
            self.mock_stripe.create_exchange_checkout_session.return_value = {
                "id": "cs_test_cu17_exchange_001",
                "url": "https://checkout.stripe.com/c/pay/cs_test_cu17_exchange_001",
            }
            checkout_res = service.create_exchange_stripe_checkout(self.client, 1)
            self.assertEqual(checkout_res["session_id"], "cs_test_cu17_exchange_001")
            self.assertIn("checkout.stripe.com", checkout_res["url"])
            call_kwargs = self.mock_stripe.create_exchange_checkout_session.call_args.kwargs
            self.assertIn("/mis-compras/10?return_id=1", call_kwargs["success_url"])
            self.assertIn("checkout=success", call_kwargs["success_url"])
            self.assertIn("/mis-compras/10?return_id=1", call_kwargs["cancel_url"])
            self.assertIn("checkout=cancel", call_kwargs["cancel_url"])

            # 5. Verificación segura del servidor: si el pago aún está UNPAID, debe rechazarse (usando StripeObject real)
            from stripe.checkout import Session as StripeCheckoutSession
            self.mock_stripe.retrieve_checkout_session.return_value = StripeCheckoutSession.construct_from({
                "id": "cs_test_cu17_exchange_001",
                "object": "checkout.session",
                "livemode": False,
                "status": "open",
                "payment_status": "unpaid",
                "amount_total": 5000,
                "currency": "bob",
                "metadata": {"id_devolucion": "1", "id_venta": "10"},
            }, "sk_test_123")
            with self.assertRaises(PaymentError) as ctx_unpaid:
                service.confirm_exchange_stripe_payment(self.client, 1)
            self.assertEqual(ctx_unpaid.exception.status_code, 409)

            # 6. Verificación exitosa en el servidor tras pago confirmado en Stripe (con PaymentIntent expandido como StripeObject)
            self.mock_stripe.retrieve_checkout_session.return_value = StripeCheckoutSession.construct_from({
                "id": "cs_test_cu17_exchange_001",
                "object": "checkout.session",
                "livemode": False,
                "status": "complete",
                "payment_status": "paid",
                "amount_total": 5000,
                "currency": "bob",
                "payment_intent": {
                    "id": "pi_test_cu17_success_001",
                    "object": "payment_intent",
                    "status": "succeeded",
                    "amount_received": 5000,
                },
                "metadata": {"id_devolucion": "1", "id_venta": "10"},
            }, "sk_test_123")
            # Bloquear creación de nueva sesión cuando la sesión existente ya está pagada pero pendiente de conciliar
            with self.assertRaises(PaymentError) as ctx_already_paid_session:
                service.create_exchange_stripe_checkout(self.client, 1)
            self.assertEqual(ctx_already_paid_session.exception.status_code, 409)

            confirm_res = service.confirm_exchange_stripe_payment(self.client, 1)
            self.assertEqual(confirm_res["estado_pago_adicional"], "CONFIRMADO")
            self.assertEqual(confirm_res["monto_adicional_cobrado"], Decimal("50.00"))
            self.assertEqual(confirm_res["medio_pago_adicional"], "TARJETA")
            self.assertEqual(confirm_res["referencia_pago_adicional"], "pi_test_cu17_success_001")

            # Segunda verificación idempotente recupera el pago confirmado sin duplicarlo
            confirm_res_2 = service.confirm_exchange_stripe_payment(self.client, 1)
            self.assertEqual(confirm_res_2["estado_pago_adicional"], "CONFIRMADO")
            self.assertEqual(confirm_res_2["referencia_pago_adicional"], "pi_test_cu17_success_001")

            # 7. Cajero finaliza el cambio de prenda (revalida stock, registra movimientos y entrega física)
            inv_orig_before = self.db.query(BranchInventory).filter_by(id_sucursal=2, id_variante_producto=101).one().stock_actual
            inv_repl_before = self.db.query(BranchInventory).filter_by(id_sucursal=2, id_variante_producto=201).one().stock_actual
            self.assertEqual(inv_orig_before, 10)
            self.assertEqual(inv_repl_before, 5)

            final_res = service.process_exchange(self.cashier, 1, ProcessExchangeRequest(reintegrar_stock_original=True))
            self.assertEqual(final_res["estado"], "PROCESADA")
            self.assertIsNotNone(final_res["fecha_entrega_reemplazo"])
            self.assertIsNotNone(final_res["fecha_procesamiento"])

            # Inventario verificado: original reingresó (+1), reemplazo salió (-1)
            inv_orig_after = self.db.query(BranchInventory).filter_by(id_sucursal=2, id_variante_producto=101).one().stock_actual
            inv_repl_after = self.db.query(BranchInventory).filter_by(id_sucursal=2, id_variante_producto=201).one().stock_actual
            self.assertEqual(inv_orig_after, 11)
            self.assertEqual(inv_repl_after, 4)

            # Movimientos registrados: ENTRADA y SALIDA
            movements = self.db.scalars(select(InventoryMovement)).all()
            self.assertEqual(len(movements), 2)
            self.assertEqual({m.tipo_movimiento for m in movements}, {"ENTRADA", "SALIDA"})

            # 8. Idempotencia y finalización única: reprocesar no duplica inventario ni movimientos
            idemp_res = service.process_exchange(self.cashier, 1, ProcessExchangeRequest())
            self.assertEqual(idemp_res["estado"], "PROCESADA")
            inv_orig_idemp = self.db.query(BranchInventory).filter_by(id_sucursal=2, id_variante_producto=101).one().stock_actual
            inv_repl_idemp = self.db.query(BranchInventory).filter_by(id_sucursal=2, id_variante_producto=201).one().stock_actual
            self.assertEqual(inv_orig_idemp, 11)
            self.assertEqual(inv_repl_idemp, 4)
            self.assertEqual(len(self.db.scalars(select(InventoryMovement)).all()), 2)

    def test_cu17_cobro_presencial_sin_diferencia_saldo_a_favor_y_stock_insuficiente(self):
        """Prueba 2: Cobro presencial en tienda (EFECTIVO/POS/QR), cambio sin diferencia (Bs 0.00),
        saldo a favor y validación estricta de stock insuficiente."""
        service = ReturnsService(self.db, self.mock_stripe)

        with patch.object(service, "_assignment", return_value=1):
            # PARTE A: Cobro presencial en tienda para diferencia mayor
            self._create_approved_exchange(ret_id=2, repl_variant_id=201)
            service.confirm_exchange_difference(self.cashier, 2)

            # QR o TARJETA requiere comprobante verificado
            with self.assertRaises(PaymentError) as ctx_qr_noref:
                service.confirm_exchange_store_payment(self.cashier, 2, ConfirmPaymentRequest(medio_pago="QR"))
            self.assertEqual(ctx_qr_noref.exception.status_code, 422)

            # Cobro presencial en efectivo confirmado por el cajero
            store_res = service.confirm_exchange_store_payment(
                self.cashier, 2, ConfirmPaymentRequest(medio_pago="EFECTIVO", referencia_manual="REC-CAJA-0045")
            )
            self.assertEqual(store_res["estado_pago_adicional"], "CONFIRMADO")
            self.assertEqual(store_res["monto_adicional_cobrado"], Decimal("50.00"))
            self.assertEqual(store_res["medio_pago_adicional"], "EFECTIVO")
            self.assertEqual(store_res["referencia_pago_adicional"], "REC-CAJA-0045")

            # Finalizar cambio en tienda
            proc_store = service.process_exchange(self.cashier, 2, ProcessExchangeRequest())
            self.assertEqual(proc_store["estado"], "PROCESADA")

            # PARTE B: Cambio sin diferencia económica (mismo precio 150 vs 150)
            self._create_approved_exchange(ret_id=3, repl_variant_id=102)
            diff_zero = service.confirm_exchange_difference(self.cashier, 3)
            self.assertEqual(diff_zero["diferencia_definitiva"], Decimal("0.00"))
            self.assertEqual(diff_zero["estado_pago_adicional"], "NO_APLICA")

            # Permite finalizar directamente sin requerir pago
            proc_zero = service.process_exchange(self.cashier, 3, ProcessExchangeRequest())
            self.assertEqual(proc_zero["estado"], "PROCESADA")
            self.assertEqual(proc_zero["diferencia_definitiva"], Decimal("0.00"))

            # PARTE C: Stock insuficiente de reemplazo en sucursal (variante 202 tiene stock 0)
            self._create_approved_exchange(ret_id=4, repl_variant_id=202)
            with self.assertRaises(PaymentError) as ctx_stock:
                service.confirm_exchange_difference(self.cashier, 4)
            self.assertEqual(ctx_stock.exception.status_code, 409)
            self.assertIn("Stock insuficiente", str(ctx_stock.exception))

            # PARTE D: Saldo a favor (P30 precio 100 vs original 150 -> diferencia -50)
            self._create_approved_exchange(ret_id=5, repl_variant_id=301)
            service.confirm_exchange_difference(self.cashier, 5)

            req_favor = ProcessExchangeRequest(referencia_manual="RECIBO-EGRESO-777")
            res_favor = service.process_exchange(self.cashier, 5, req_favor)
            self.assertEqual(res_favor["estado"], "PROCESADA")
            self.assertEqual(res_favor["diferencia_definitiva"], Decimal("-50.00"))

            # Reembolso registrado y aprobado sin duplicados
            refunds = self.db.scalars(select(Refund).where(Refund.id_devolucion == 5)).all()
            self.assertEqual(len(refunds), 1)
            self.assertEqual(refunds[0].estado, "APROBADO")
            self.assertEqual(refunds[0].monto, Decimal("50.00"))
            self.assertEqual(refunds[0].referencia_externa, "RECIBO-EGRESO-777")
