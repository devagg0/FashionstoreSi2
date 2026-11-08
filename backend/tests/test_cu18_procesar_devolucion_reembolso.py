"""Pruebas unitarias focalizadas para CU18 — Procesar devolución y reembolso."""
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import MagicMock
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models.branch import Branch
from app.models.branch_inventory import BranchInventory
from app.models.city import City
from app.models.client import Client
from app.models.color import Color
from app.models.employee import Employee
from app.models.employee_branch import EmployeeBranch
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
from app.schemas.returns import ProcessRequest
from app.services.payments import PaymentError, PaymentsService
from app.services.returns import ReturnsService


class TestCU18ProcesarDevolucionReembolso(TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        for model in (
            User,
            Client,
            Employee,
            City,
            Branch,
            EmployeeBranch,
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
        self.mock_stripe = MagicMock()

        self.db.add_all([
            City(id_ciudad=1, nombre="Santa Cruz de la Sierra", estado=True),
            User(id_usuario=1, id_rol=1, correo="admin@fashion.com", nombre="Admin", apellido="General", password_hash="x", estado=True),
            User(id_usuario=11, id_rol=2, correo="cajero@fashion.com", nombre="Carlos", apellido="Cajero", password_hash="x", estado=True),
            User(id_usuario=15, id_rol=4, correo="encargado@fashion.com", nombre="Federica", apellido="Encargada", password_hash="x", estado=True),
            User(id_usuario=16, id_rol=4, correo="encargado_otra@fashion.com", nombre="Pedro", apellido="Otro", password_hash="x", estado=True),
            User(id_usuario=20, id_rol=3, correo="cliente@fashion.com", nombre="Ana", apellido="Cliente", password_hash="x", estado=True),
            Client(id_cliente=7, id_usuario=20, empresa_id=1),
            Branch(id_sucursal=2, id_ciudad=1, empresa_id=1, nombre="Sucursal Central", direccion="Av. Principal", telefono="70000000", estado=True),
            Branch(id_sucursal=3, id_ciudad=1, empresa_id=1, nombre="Sucursal Norte", direccion="Av. Norte", telefono="70000001", estado=True),
            Employee(id_empleado=1, id_usuario=11, empresa_id=1, cargo="Cajero"),
            Employee(id_empleado=5, id_usuario=15, empresa_id=1, cargo="Encargado"),
            Employee(id_empleado=6, id_usuario=16, empresa_id=1, cargo="Encargado"),
            EmployeeBranch(id_empleado_sucursal=10, id_empleado=1, id_sucursal=2, empresa_id=1, estado=True),
            EmployeeBranch(id_empleado_sucursal=15, id_empleado=5, id_sucursal=2, empresa_id=1, estado=True),
            EmployeeBranch(id_empleado_sucursal=16, id_empleado=6, id_sucursal=3, empresa_id=1, estado=True),
            Size(id_talla=1, empresa_id=1, nombre="M", estado=True),
            Color(id_color=1, empresa_id=1, nombre="Negro", codigo_hex="#000000", estado=True),
            Product(id_producto=10, id_categoria=1, empresa_id=1, nombre="Abrigo Lana", seccion="MUJER", precio=Decimal("200.00"), estado=True),
            ProductVariant(id_variante_producto=101, id_producto=10, id_talla=1, id_color=1, empresa_id=1, sku="ABR-M-NEG", estado=True),
            BranchInventory(id_sucursal=2, id_variante_producto=101, empresa_id=1, stock_actual=8, stock_reservado=0, stock_minimo=1),
        ])
        self.db.commit()

        self.admin_user = NS(id_usuario=1, rol="ADMINISTRADOR", empresa_id=1)
        self.cajero_user = NS(id_usuario=11, rol="CAJERO", empresa_id=1)
        self.encargado_user = NS(id_usuario=15, rol="ENCARGADO_SUCURSAL", empresa_id=1)
        self.encargado_other_branch = NS(id_usuario=16, rol="ENCARGADO_SUCURSAL", empresa_id=1)
        self.service = ReturnsService(self.db, stripe_service=self.mock_stripe)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_cu18_permisos_roles_reembolso_stripe_estados_e_idempotencia(self):
        payment_key = uuid4()
        self.db.add_all([
            Sale(
                id_venta=50,
                empresa_id=1,
                numero_venta="VTA-CU18-STRIPE",
                id_cliente=7,
                id_sucursal=2,
                id_empleado=1,
                canal="DIGITAL",
                estado="COMPLETADA",
                moneda="BOB",
                subtotal=Decimal("200.00"),
                descuento_total=Decimal("0.00"),
                total=Decimal("200.00"),
                stock_comprometido=False,
                fecha_venta=self.now - timedelta(hours=5),
                fecha_completada=self.now - timedelta(hours=5),
            ),
            SaleDetail(
                id_detalle_venta=501,
                empresa_id=1,
                id_venta=50,
                id_variante_producto=101,
                cantidad=1,
                precio_unitario=Decimal("200.00"),
                descuento_unitario=Decimal("0.00"),
                subtotal_linea=Decimal("200.00"),
            ),
            Payment(
                id_pago=60,
                empresa_id=1,
                id_venta=50,
                medio="TARJETA",
                proveedor="STRIPE",
                entorno="TEST",
                estado="APROBADO",
                monto=Decimal("200.00"),
                moneda="BOB",
                referencia_externa="pi_test_cu18_50",
                clave_idempotencia=payment_key,
                fecha_aprobacion=self.now - timedelta(hours=5),
                created_at=self.now - timedelta(hours=5),
                updated_at=self.now - timedelta(hours=5),
            ),
            InventoryMovement(
                id_movimiento_inventario=70,
                empresa_id=1,
                id_venta=50,
                id_sucursal_origen=2,
                id_empleado_sucursal=10,
                tipo_movimiento="VENTA",
                estado="CONFIRMADO",
                motivo="Venta digital 50",
                fecha_movimiento=self.now - timedelta(hours=5),
            ),
            InventoryMovementDetail(
                empresa_id=1,
                id_movimiento_inventario=70,
                id_variante_producto=101,
                cantidad=1,
            ),
            Return(
                id_devolucion=80,
                empresa_id=1,
                id_venta=50,
                tipo="DEVOLUCION",
                estado="APROBADA",
                modalidad_entrega="ENTREGA_EN_TIENDA",
                motivo="Prenda no me quedó bien",
                id_usuario_solicitante=20,
                id_usuario_evaluador=11,
                id_usuario_receptor=11,
                id_usuario_inspector=11,
                id_usuario_resolutor=11,
                clave_idempotencia=uuid4(),
                fecha_evaluacion_inicial=self.now - timedelta(hours=3),
                fecha_seleccion_modalidad=self.now - timedelta(hours=2),
                fecha_recepcion=self.now - timedelta(hours=1),
                estado_fisico="OPTIMO",
                etiquetas_intactas=True,
                correspondencia_compra=True,
                fecha_inspeccion=self.now - timedelta(minutes=30),
                fecha_resolucion=self.now - timedelta(minutes=30),
                created_at=self.now - timedelta(hours=4),
                updated_at=self.now - timedelta(minutes=30),
            ),
            ReturnDetail(
                id_detalle_devolucion=801,
                empresa_id=1,
                id_devolucion=80,
                id_venta=50,
                id_variante_producto=101,
                cantidad=1,
                cantidad_reintegrar=0,
                importe_restitucion=Decimal("200.00"),
                precio_original_reconocido=Decimal("200.00"),
            ),
        ])
        self.db.commit()

        # 1) CAJERO no puede procesar DEVOLUCION en CU18 (403)
        with self.assertRaises(PaymentError) as ctx_cajero:
            self.service.process(self.cajero_user, 80, ProcessRequest())
        self.assertEqual(ctx_cajero.exception.status_code, 403)

        # 2) ENCARGADO de otra sucursal no puede procesar (403)
        with self.assertRaises(PaymentError) as ctx_other:
            self.service.process(self.encargado_other_branch, 80, ProcessRequest())
        self.assertEqual(ctx_other.exception.status_code, 403)

        # Configurar mocks de Stripe para reembolso inicialmente PENDIENTE
        self.mock_stripe.retrieve_payment_intent.return_value = {
            "id": "pi_test_cu18_50",
            "livemode": False,
            "status": "succeeded",
            "amount_received": 20000,
            "currency": "bob",
            "latest_charge": "ch_test_cu18_50",
            "metadata": {
                "id_venta": "50",
                "id_pago": "60",
                "clave_idempotencia": str(payment_key),
            },
        }
        self.mock_stripe.retrieve_charge.return_value = {
            "id": "ch_test_cu18_50",
            "livemode": False,
            "payment_intent": "pi_test_cu18_50",
            "paid": True,
            "captured": True,
            "currency": "bob",
            "amount": 20000,
            "amount_refunded": 0,
        }
        self.mock_stripe.list_refunds.return_value = []
        self.mock_stripe.create_refund.return_value = {
            "id": "re_test_cu18_pending",
            "payment_intent": "pi_test_cu18_50",
            "charge": "ch_test_cu18_50",
            "amount": 20000,
            "currency": "bob",
            "status": "pending",
            "created": int(self.now.timestamp()),
        }

        # 3) Cuando Stripe devuelve 'pending', NO se marca PROCESADA ni se altera el inventario
        res_pending = self.service.process(self.admin_user, 80, ProcessRequest())
        self.assertEqual(res_pending["estado"], "APROBADA")
        self.assertEqual(res_pending["estado_reembolso"], "PENDIENTE")
        self.assertEqual(len(res_pending["reembolsos"]), 1)
        self.assertEqual(res_pending["reembolsos"][0]["estado"], "PENDIENTE")
        self.assertEqual(res_pending["reembolsos"][0]["referencia_externa"], "re_test_cu18_pending")
        inv_after_pending = self.db.get(BranchInventory, 1)
        self.assertEqual(inv_after_pending.stock_actual, 8)

        # 4) Cuando Stripe confirma 'succeeded', ADMINISTRADOR (sin fila en t_empleado) finaliza el reembolso y reintegra stock
        self.mock_stripe.retrieve_refund.return_value = {
            "id": "re_test_cu18_pending",
            "payment_intent": "pi_test_cu18_50",
            "charge": "ch_test_cu18_50",
            "amount": 20000,
            "currency": "bob",
            "status": "succeeded",
            "created": int(self.now.timestamp()),
        }
        res_done = self.service.process(self.admin_user, 80, ProcessRequest(reintegrar_stock_original=True))
        self.assertEqual(res_done["estado"], "PROCESADA")
        self.assertEqual(res_done["estado_reembolso"], "CONFIRMADO")
        self.assertEqual(res_done["reembolsos"][0]["estado"], "APROBADO")
        self.assertIsNotNone(res_done["id_movimiento_inventario"])
        inv_after_done = self.db.get(BranchInventory, 1)
        self.assertEqual(inv_after_done.stock_actual, 9)
        pay_after_done = self.db.get(Payment, 60)
        self.assertEqual(pay_after_done.estado, "REEMBOLSADO")

        # 5) Segunda llamada sobre solicitud ya PROCESADA es idempotente y no duplica movimientos ni reembolsos
        mov_id = res_done["id_movimiento_inventario"]
        res_idem = self.service.process(self.encargado_user, 80, ProcessRequest())
        self.assertEqual(res_idem["estado"], "PROCESADA")
        self.assertEqual(res_idem["id_movimiento_inventario"], mov_id)
        self.assertEqual(self.db.get(BranchInventory, 1).stock_actual, 9)
        entry_movements = self.db.scalars(
            select(InventoryMovement).where(InventoryMovement.tipo_movimiento == "ENTRADA")
        ).all()
        self.assertEqual(len(entry_movements), 1)

    def test_cu18_reembolso_manual_descuentos_devoluciones_previas_y_prenda_no_apta(self):
        # Compra presencial de 2 unidades (precio 200 c/u, descuento 25 c/u -> total pagado 350.00 en EFECTIVO)
        self.db.add_all([
            Sale(
                id_venta=51,
                empresa_id=1,
                numero_venta="VTA-CU18-MANUAL",
                id_cliente=7,
                id_sucursal=2,
                id_empleado=1,
                canal="PRESENCIAL",
                estado="COMPLETADA",
                moneda="BOB",
                subtotal=Decimal("400.00"),
                descuento_total=Decimal("50.00"),
                total=Decimal("350.00"),
                stock_comprometido=False,
                fecha_venta=self.now - timedelta(hours=6),
                fecha_completada=self.now - timedelta(hours=6),
            ),
            SaleDetail(
                id_detalle_venta=511,
                empresa_id=1,
                id_venta=51,
                id_variante_producto=101,
                cantidad=2,
                precio_unitario=Decimal("200.00"),
                descuento_unitario=Decimal("25.00"),
                subtotal_linea=Decimal("350.00"),
            ),
            Payment(
                id_pago=61,
                empresa_id=1,
                id_venta=51,
                medio="EFECTIVO",
                proveedor="MANUAL",
                entorno="LOCAL",
                estado="APROBADO",
                monto=Decimal("350.00"),
                moneda="BOB",
                referencia_externa=None,
                clave_idempotencia=uuid4(),
                fecha_aprobacion=self.now - timedelta(hours=6),
                created_at=self.now - timedelta(hours=6),
                updated_at=self.now - timedelta(hours=6),
            ),
            InventoryMovement(
                id_movimiento_inventario=71,
                empresa_id=1,
                id_venta=51,
                id_sucursal_origen=2,
                id_empleado_sucursal=10,
                tipo_movimiento="VENTA",
                estado="CONFIRMADO",
                motivo="Venta presencial 51",
                fecha_movimiento=self.now - timedelta(hours=6),
            ),
            InventoryMovementDetail(
                empresa_id=1,
                id_movimiento_inventario=71,
                id_variante_producto=101,
                cantidad=2,
            ),
            # Primera devolución parcial (1 unidad apta para la venta, Bs 175.00)
            Return(
                id_devolucion=81,
                empresa_id=1,
                id_venta=51,
                tipo="DEVOLUCION",
                estado="APROBADA",
                modalidad_entrega="ENTREGA_EN_TIENDA",
                motivo="Devolución parcial unidad 1",
                id_usuario_solicitante=20,
                id_usuario_evaluador=11,
                id_usuario_receptor=11,
                id_usuario_inspector=11,
                id_usuario_resolutor=11,
                clave_idempotencia=uuid4(),
                fecha_evaluacion_inicial=self.now - timedelta(hours=4),
                fecha_seleccion_modalidad=self.now - timedelta(hours=3),
                fecha_recepcion=self.now - timedelta(hours=2),
                estado_fisico="OPTIMO",
                etiquetas_intactas=True,
                correspondencia_compra=True,
                fecha_inspeccion=self.now - timedelta(hours=1),
                fecha_resolucion=self.now - timedelta(hours=1),
                created_at=self.now - timedelta(hours=5),
                updated_at=self.now - timedelta(hours=1),
            ),
            ReturnDetail(
                id_detalle_devolucion=811,
                empresa_id=1,
                id_devolucion=81,
                id_venta=51,
                id_variante_producto=101,
                cantidad=1,
                cantidad_reintegrar=0,
                importe_restitucion=Decimal("175.00"),
                precio_original_reconocido=Decimal("175.00"),
            ),
        ])
        self.db.commit()

        # 1) Pago manual sin referencia_manual debe fallar con 422
        with self.assertRaises(PaymentError) as ctx_no_ref:
            self.service.process(self.encargado_user, 81, ProcessRequest())
        self.assertEqual(ctx_no_ref.exception.status_code, 422)

        # 2) ENCARGADO_SUCURSAL procesa primera devolución parcial con referencia manual y reintegra 1 unidad apta
        res1 = self.service.process(
            self.encargado_user,
            81,
            ProcessRequest(referencia_manual="REC-CAJA-001", reintegrar_stock_original=True),
        )
        self.assertEqual(res1["estado"], "PROCESADA")
        self.assertEqual(res1["estado_reembolso"], "CONFIRMADO")
        self.assertEqual(Decimal(str(res1["reembolsos"][0]["monto"])), Decimal("175.00"))
        self.assertEqual(res1["reembolsos"][0]["referencia_externa"], "REC-CAJA-001")
        self.assertIsNotNone(res1["id_movimiento_inventario"])
        self.assertEqual(self.db.get(BranchInventory, 1).stock_actual, 9)
        self.assertEqual(self.db.get(Payment, 61).estado, "APROBADO")

        # 3) Segunda devolución por la 2da unidad, pero inspeccionada como DANADO (no apta para reintegro a stock)
        self.db.add_all([
            Return(
                id_devolucion=82,
                empresa_id=1,
                id_venta=51,
                tipo="DEVOLUCION",
                estado="APROBADA",
                modalidad_entrega="DELIVERY_SIMULADO",
                motivo="Devolución unidad 2 con falla de fábrica",
                id_usuario_solicitante=20,
                id_usuario_evaluador=11,
                id_usuario_receptor=11,
                id_usuario_inspector=11,
                id_usuario_resolutor=11,
                clave_idempotencia=uuid4(),
                fecha_evaluacion_inicial=self.now - timedelta(hours=2),
                fecha_seleccion_modalidad=self.now - timedelta(hours=2),
                fecha_recepcion=self.now - timedelta(hours=1),
                estado_fisico="DANADO",
                etiquetas_intactas=False,
                correspondencia_compra=True,
                fecha_inspeccion=self.now - timedelta(minutes=20),
                fecha_resolucion=self.now - timedelta(minutes=20),
                created_at=self.now - timedelta(hours=3),
                updated_at=self.now - timedelta(minutes=20),
            ),
            ReturnDetail(
                id_detalle_devolucion=821,
                empresa_id=1,
                id_devolucion=82,
                id_venta=51,
                id_variante_producto=101,
                cantidad=1,
                cantidad_reintegrar=0,
                importe_restitucion=Decimal("200.00"),  # Excede el saldo reembolsable restante (175.00)
                precio_original_reconocido=Decimal("175.00"),
            ),
        ])
        self.db.commit()

        # Verificar que nunca permita reembolsar más de lo efectivamente pagado/reembolsable (175.00 restante)
        with self.assertRaises(PaymentError) as ctx_excess:
            self.service.process(self.admin_user, 82, ProcessRequest(referencia_manual="REC-CAJA-002"))
        self.assertEqual(ctx_excess.exception.status_code, 409)

        # Ajustar importe al valor neto real (175.00) y procesar: debe reembolsar pero NO sumar stock por ser prenda DANADO
        det2 = self.db.get(ReturnDetail, 821)
        det2.importe_restitucion = Decimal("175.00")
        self.db.commit()

        res2 = self.service.process(
            self.admin_user,
            82,
            ProcessRequest(referencia_manual="REC-CAJA-002", reintegrar_stock_original=True),
        )
        self.assertEqual(res2["estado"], "PROCESADA")
        self.assertEqual(res2["estado_reembolso"], "CONFIRMADO")
        self.assertIsNone(res2["id_movimiento_inventario"])
        self.assertEqual(res2["lineas"][0]["cantidad_reintegrar"], 0)
        # El stock permanece en 9 (no sumó la prenda dañada) y el pago queda totalmente REEMBOLSADO (175 + 175 = 350)
        self.assertEqual(self.db.get(BranchInventory, 1).stock_actual, 9)
        self.assertEqual(self.db.get(Payment, 61).estado, "REEMBOLSADO")
