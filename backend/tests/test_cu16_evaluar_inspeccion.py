"""Pruebas unitarias focalizadas para CU16 — Evaluar solicitud y verificar estado de la prenda."""
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models.branch import Branch
from app.models.branch_inventory import BranchInventory
from app.models.client import Client
from app.models.color import Color
from app.models.payment import Payment
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.returns import Refund, Return, ReturnDetail
from app.models.sale import Sale
from app.models.sale_detail import SaleDetail
from app.models.size import Size
from app.models.user import User
from app.schemas.returns import (
    DeliveryModalitySelectionRequest,
    InitialReviewRequest,
    InspectionRequest,
    ReceiveItemRequest,
    ReturnRequest,
    ReturnLine,
)
from app.services.payments import PaymentError, PaymentsService
from app.services.returns import ReturnsService


class TestCU16EvaluarInspeccion(TestCase):
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
        ):
            model.__table__.create(self.engine)

        self.db = Session(self.engine)
        self.db.autoflush = False
        self.now = PaymentsService.now()

        # Usuarios: Cliente (12), Cajero (11), Cajero ajeno (99)
        self.db.add_all(
            [
                User(id_usuario=11, id_rol=2, correo="cajero@store.com", nombre="Carlos", apellido="Cajero", password_hash="x", estado=True),
                User(id_usuario=12, id_rol=3, correo="cliente@store.com", nombre="Ana", apellido="Cliente", password_hash="x", estado=True),
                User(id_usuario=99, id_rol=2, correo="otro@store.com", nombre="Pedro", apellido="Otro", password_hash="x", estado=True),
                Client(id_cliente=7, id_usuario=12, empresa_id=1),
                Branch(
                    id_sucursal=2,
                    id_ciudad=1,
                    empresa_id=1,
                    nombre="Sucursal Centro",
                    direccion="Av. Principal 123",
                    telefono="70000000",
                ),
                Branch(
                    id_sucursal=3,
                    id_ciudad=1,
                    empresa_id=1,
                    nombre="Sucursal Norte",
                    direccion="Av. Norte 456",
                    telefono="70000001",
                ),
            ]
        )

        # Catalogo
        self.db.add_all(
            [
                Size(id_talla=1, empresa_id=1, nombre="M", estado=True),
                Color(id_color=1, empresa_id=1, nombre="Negro", codigo_hex="#000000", estado=True),
                Product(
                    id_producto=10,
                    id_categoria=1,
                    empresa_id=1,
                    nombre="Vestido Floral",
                    seccion="MUJER",
                    precio=Decimal("150.00"),
                    estado=True,
                ),
            ]
        )
        self.db.add(
            ProductVariant(
                id_variante_producto=101,
                id_producto=10,
                id_talla=1,
                id_color=1,
                empresa_id=1,
                sku="VES-M-NEG",
                estado=True,
            )
        )
        self.db.add(
            BranchInventory(
                id_sucursal=2,
                id_variante_producto=101,
                empresa_id=1,
                stock_actual=10,
                stock_reservado=0,
                stock_minimo=1,
            )
        )

        # Venta completada hace 5 horas
        completed_time = self.now - timedelta(hours=5)
        self.db.add(
            Sale(
                id_venta=10,
                empresa_id=1,
                numero_venta="VTA-CU16-001",
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
                fecha_venta=completed_time - timedelta(minutes=15),
                fecha_completada=completed_time,
                created_at=completed_time,
                updated_at=completed_time,
            )
        )
        self.db.add(
            SaleDetail(
                id_detalle_venta=101,
                empresa_id=1,
                id_venta=10,
                id_variante_producto=101,
                cantidad=1,
                precio_unitario=Decimal("150.00"),
                descuento_unitario=Decimal("0.00"),
                subtotal_linea=Decimal("150.00"),
            )
        )
        self.db.add(
            Payment(
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
            )
        )
        self.db.commit()

        self.client_user = NS(id_usuario=12, rol="CLIENTE", empresa_id=1)
        self.cashier_user = NS(id_usuario=11, rol="CAJERO", empresa_id=1)
        self.other_cashier = NS(id_usuario=99, rol="CAJERO", empresa_id=1)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _create_return_request(self) -> int:
        service = ReturnsService(self.db)
        payload = ReturnRequest(
            tipo="DEVOLUCION",
            motivo="Talla no adecuada",
            lineas=[ReturnLine(id_detalle_venta=101, cantidad=1)],
        )
        res = service.request(self.client_user, 10, payload, uuid4())
        return res["id_devolucion"]

    def test_cu16_full_happy_path(self):
        """Prueba el ciclo de vida completo de CU16:
        SOLICITADA -> ACEPTADA_INICIALMENTE -> PENDIENTE_ENTREGA -> RECIBIDA -> APROBADA
        Sin reservar inventario ni generar reembolsos antes de CU17/CU18."""
        service = ReturnsService(self.db)
        return_id = self._create_return_request()
        self.assertGreaterEqual(Return.__table__.c.estado.type.length, len("ACEPTADA_INICIALMENTE"))

        with patch.object(service, "_assignment", return_value=1):
            # 1. Cajero evalúa y acepta inicialmente la solicitud
            initial_req = InitialReviewRequest(resultado="ACEPTADA")
            data_accepted = service.initial_review(self.cashier_user, return_id, initial_req)
            self.assertEqual(data_accepted["estado"], "ACEPTADA_INICIALMENTE")
            self.assertEqual(data_accepted["id_usuario_evaluador"], 11)
            self.assertIsNotNone(data_accepted["fecha_evaluacion_inicial"])
            # Verificar que NO se crearon reembolsos
            refunds = self.db.query(Refund).filter_by(id_devolucion=return_id).all()
            self.assertEqual(len(refunds), 0)

            # 2. Cliente selecciona modalidad de entrega (Delivery simulado)
            mod_req = DeliveryModalitySelectionRequest(modalidad_entrega="DELIVERY_SIMULADO")
            data_mod = service.select_delivery_modality(self.client_user, return_id, mod_req)
            self.assertEqual(data_mod["estado"], "PENDIENTE_ENTREGA")
            self.assertEqual(data_mod["modalidad_entrega"], "DELIVERY_SIMULADO")
            self.assertIsNotNone(data_mod["fecha_seleccion_modalidad"])

            # 3. Cajero confirma que la prenda llegó físicamente a tienda ("Prenda recibida en tienda")
            recv_req = ReceiveItemRequest(observaciones="Paquete recibido en recepción")
            data_recv = service.receive_item(self.cashier_user, return_id, recv_req)
            self.assertEqual(data_recv["estado"], "RECIBIDA")
            self.assertEqual(data_recv["id_usuario_receptor"], 11)
            self.assertIsNotNone(data_recv["fecha_recepcion"])

            # 4. Cajero realiza inspección física básica y aprueba definitivamente
            inspect_req = InspectionRequest(
                resultado="APROBADA",
                estado_fisico="OPTIMO",
                etiquetas_intactas=True,
                correspondencia_compra=True,
                observaciones="Prenda en perfecto estado con etiquetas originales",
            )
            data_inspected = service.inspect_item(self.cashier_user, return_id, inspect_req)
            self.assertEqual(data_inspected["estado"], "APROBADA")
            self.assertEqual(data_inspected["estado_fisico"], "OPTIMO")
            self.assertTrue(data_inspected["etiquetas_intactas"])
            self.assertTrue(data_inspected["correspondencia_compra"])
            self.assertEqual(data_inspected["id_usuario_inspector"], 11)
            self.assertEqual(data_inspected["id_usuario_resolutor"], 11)
            self.assertIsNotNone(data_inspected["fecha_inspeccion"])
            self.assertIsNotNone(data_inspected["fecha_resolucion"])

            # Verificar que en CU16 aún NO se genera reembolso ni modifica inventario
            refunds_final = self.db.query(Refund).filter_by(id_devolucion=return_id).all()
            self.assertEqual(len(refunds_final), 0)
            inv = self.db.query(BranchInventory).filter_by(id_sucursal=2, id_variante_producto=101).one()
            self.assertEqual(inv.stock_actual, 10)  # Sin cambios de stock

    def test_cu16_rejections_and_validations(self):
        """Prueba rechazos con motivo obligatorio y validación estricta de transiciones."""
        service = ReturnsService(self.db)
        return_id = self._create_return_request()
        self.assertGreaterEqual(Return.__table__.c.estado.type.length, len("ACEPTADA_INICIALMENTE"))

        with patch.object(service, "_assignment", return_value=1):
            # Rechazo inicial sin motivo debe fallar en Pydantic / validación
            with self.assertRaises(ValueError):
                InitialReviewRequest(resultado="RECHAZADA", motivo_rechazo="   ")

            # Cliente no puede elegir modalidad si aún no está ACEPTADA_INICIALMENTE
            with self.assertRaises(PaymentError) as ctx:
                service.select_delivery_modality(
                    self.client_user,
                    return_id,
                    DeliveryModalitySelectionRequest(modalidad_entrega="ENTREGA_EN_TIENDA"),
                )
            self.assertEqual(ctx.exception.status_code, 409)

            # Cajero no puede confirmar recepción si no está PENDIENTE_ENTREGA
            with self.assertRaises(PaymentError) as ctx:
                service.receive_item(self.cashier_user, return_id)
            self.assertEqual(ctx.exception.status_code, 409)

            # Cajero no puede inspeccionar si no está RECIBIDA
            with self.assertRaises(PaymentError) as ctx:
                service.inspect_item(
                    self.cashier_user,
                    return_id,
                    InspectionRequest(
                        resultado="APROBADA",
                        estado_fisico="OPTIMO",
                        etiquetas_intactas=True,
                        correspondencia_compra=True,
                    ),
                )
            self.assertEqual(ctx.exception.status_code, 409)

            # Probar rechazo inicial con motivo válido
            reject_req = InitialReviewRequest(
                resultado="RECHAZADA",
                motivo_rechazo="Prenda solicitada fuera de las condiciones iniciales",
            )
            data_rejected = service.initial_review(self.cashier_user, return_id, reject_req)
            self.assertEqual(data_rejected["estado"], "RECHAZADA")
            self.assertEqual(data_rejected["motivo_rechazo"], "Prenda solicitada fuera de las condiciones iniciales")
            self.assertEqual(data_rejected["id_usuario_resolutor"], 11)
            self.assertIsNotNone(data_rejected["fecha_resolucion"])
