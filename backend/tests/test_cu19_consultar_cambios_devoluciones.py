"""Pruebas unitarias focalizadas para CU19 — Consultar estado de cambios y devoluciones."""
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-12345678901234567890123456789012")
os.environ.setdefault("BREVO_API_KEY", "test-brevo-key")
os.environ.setdefault("BREVO_SENDER_EMAIL", "test@fashion.com")
os.environ.setdefault("BREVO_SENDER_NAME", "FashionStore")
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_fashionstore123456789")
os.environ.setdefault("STRIPE_PUBLISHABLE_KEY", "pk_test_fashionstore123456789")
os.environ.setdefault("STRIPE_MODE", "test")

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.tenant_context import set_tenant_context
from app.models.branch import Branch
from app.models.branch_inventory import BranchInventory
from app.models.city import City
from app.models.client import Client
from app.models.color import Color
from app.models.employee import Employee
from app.models.employee_branch import EmployeeBranch
from app.models.payment import Payment
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.returns import Refund, Return, ReturnDetail
from app.models.sale import Sale
from app.models.sale_detail import SaleDetail
from app.models.size import Size
from app.models.user import User
from app.services.payments import PaymentsService, PaymentError
from app.services.returns import ReturnsService


class TestCU19ConsultarCambiosDevoluciones(TestCase):
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
        ):
            model.__table__.create(self.engine)

        self.db = Session(self.engine)
        self.db.autoflush = False
        self.now = PaymentsService.now()
        self.mock_stripe = MagicMock()

        # 1. Entidades no-tenant (Ciudades y Usuarios)
        self.db.add_all([
            City(id_ciudad=1, nombre="Santa Cruz de la Sierra", estado=True),
            User(id_usuario=1, id_rol=1, correo="admin@fashion.com", nombre="Admin", apellido="General", password_hash="x", estado=True),
            User(id_usuario=11, id_rol=2, correo="cajero@fashion.com", nombre="Carlos", apellido="Cajero", password_hash="x", estado=True),
            User(id_usuario=20, id_rol=3, correo="cliente1@fashion.com", nombre="Ana", apellido="Cliente", password_hash="x", estado=True),
            User(id_usuario=21, id_rol=3, correo="cliente2@fashion.com", nombre="Beatriz", apellido="Cliente", password_hash="x", estado=True),
            User(id_usuario=30, id_rol=1, correo="admin_otro@empresa2.com", nombre="Admin2", apellido="Otro", password_hash="x", estado=True),
        ])
        self.db.commit()

        # 2. Entidades de Empresa 1
        set_tenant_context(self.db, 1)
        self.db.add_all([
            Client(id_cliente=1, id_usuario=20, empresa_id=1),
            Client(id_cliente=2, id_usuario=21, empresa_id=1),
            Branch(id_sucursal=2, id_ciudad=1, empresa_id=1, nombre="Sucursal Central", direccion="Av. Principal", telefono="70000000", estado=True),
            Branch(id_sucursal=3, id_ciudad=1, empresa_id=1, nombre="Sucursal Norte", direccion="Av. Norte", telefono="70000001", estado=True),
            Employee(id_empleado=1, id_usuario=11, empresa_id=1, cargo="Cajero"),
            EmployeeBranch(id_empleado_sucursal=10, id_empleado=1, id_sucursal=2, empresa_id=1, estado=True),
            Size(id_talla=1, empresa_id=1, nombre="M", estado=True),
            Size(id_talla=2, empresa_id=1, nombre="L", estado=True),
            Color(id_color=1, empresa_id=1, nombre="Negro", codigo_hex="#000000", estado=True),
            Product(id_producto=10, id_categoria=1, empresa_id=1, nombre="Chaqueta Cuero", seccion="MUJER", precio=Decimal("250.00"), estado=True),
            ProductVariant(id_variante_producto=101, id_producto=10, id_talla=1, id_color=1, empresa_id=1, sku="CHQ-M-NEG", estado=True),
            ProductVariant(id_variante_producto=102, id_producto=10, id_talla=2, id_color=1, empresa_id=1, sku="CHQ-L-NEG", estado=True),
            Sale(
                id_venta=101,
                id_cliente=1,
                id_sucursal=2,
                canal="DIGITAL",
                estado="COMPLETADA",
                subtotal=Decimal("250.00"),
                descuento_total=Decimal("0.00"),
                total=Decimal("250.00"),
                fecha_venta=self.now - timedelta(hours=5),
                fecha_completada=self.now - timedelta(hours=4),
                numero_venta=f"VTA-{uuid4().hex[:8].upper()}",
                empresa_id=1,
            ),
            Sale(
                id_venta=102,
                id_cliente=1,
                id_sucursal=2,
                id_empleado=1,
                canal="PRESENCIAL",
                estado="COMPLETADA",
                subtotal=Decimal("250.00"),
                descuento_total=Decimal("0.00"),
                total=Decimal("250.00"),
                fecha_venta=self.now - timedelta(hours=6),
                fecha_completada=self.now - timedelta(hours=5),
                numero_venta=f"VTA-{uuid4().hex[:8].upper()}",
                empresa_id=1,
            ),
            Sale(
                id_venta=103,
                id_cliente=2,
                id_sucursal=3,
                canal="DIGITAL",
                estado="COMPLETADA",
                subtotal=Decimal("250.00"),
                descuento_total=Decimal("0.00"),
                total=Decimal("250.00"),
                fecha_venta=self.now - timedelta(hours=3),
                fecha_completada=self.now - timedelta(hours=2),
                numero_venta=f"VTA-{uuid4().hex[:8].upper()}",
                empresa_id=1,
            ),
            Return(
                id_devolucion=11,
                id_venta=101,
                id_usuario_solicitante=20,
                clave_idempotencia=uuid4(),
                tipo="CAMBIO",
                estado="APROBADA",
                modalidad_entrega="DELIVERY_SIMULADO",
                motivo="Cambio de talla por L",
                fecha_evaluacion_inicial=self.now - timedelta(hours=3),
                id_usuario_evaluador=11,
                fecha_seleccion_modalidad=self.now - timedelta(hours=2),
                fecha_recepcion=self.now - timedelta(hours=1),
                id_usuario_receptor=11,
                fecha_inspeccion=self.now - timedelta(minutes=45),
                id_usuario_inspector=11,
                estado_fisico="OPTIMO",
                etiquetas_intactas=True,
                correspondencia_compra=True,
                observaciones_inspeccion="Prenda sin uso y con etiqueta",
                id_usuario_resolutor=11,
                fecha_resolucion=self.now - timedelta(minutes=30),
                diferencia_definitiva=Decimal("0.00"),
                estado_pago_adicional="NO_APLICA",
                created_at=self.now - timedelta(hours=4),
            ),
            Return(
                id_devolucion=12,
                id_venta=102,
                id_usuario_solicitante=20,
                clave_idempotencia=uuid4(),
                tipo="DEVOLUCION",
                estado="SOLICITADA",
                modalidad_entrega="ENTREGA_EN_TIENDA",
                motivo="Prenda no de mi agrado",
                created_at=self.now - timedelta(hours=2),
            ),
            Return(
                id_devolucion=13,
                id_venta=103,
                id_usuario_solicitante=21,
                clave_idempotencia=uuid4(),
                tipo="CAMBIO",
                estado="PROCESADA",
                modalidad_entrega="ENTREGA_EN_TIENDA",
                motivo="Cambio modelo",
                id_usuario_resolutor=11,
                fecha_resolucion=self.now - timedelta(minutes=20),
                fecha_procesamiento=self.now - timedelta(minutes=10),
                created_at=self.now - timedelta(hours=1),
            ),
            ReturnDetail(
                id_detalle_devolucion=1,
                id_devolucion=11,
                id_venta=101,
                id_variante_producto=101,
                cantidad=1,
                cantidad_reintegrar=1,
                importe_restitucion=Decimal("250.00"),
                id_variante_reemplazo=102,
                cantidad_reemplazo=1,
                precio_original_reconocido=Decimal("250.00"),
                precio_reemplazo_estimado=Decimal("250.00"),
                diferencia_precio_estimada=Decimal("0.00"),
            ),
        ])
        self.db.commit()

        # 3. Entidades de Empresa 2
        set_tenant_context(self.db, 2)
        self.db.add_all([
            Branch(id_sucursal=9, id_ciudad=1, empresa_id=2, nombre="Sucursal Otra Empresa", direccion="Av. Lejana", telefono="79999999", estado=True),
            Sale(
                id_venta=201,
                id_cliente=1,
                id_sucursal=9,
                canal="DIGITAL",
                estado="COMPLETADA",
                subtotal=Decimal("250.00"),
                descuento_total=Decimal("0.00"),
                total=Decimal("250.00"),
                fecha_venta=self.now - timedelta(hours=2),
                fecha_completada=self.now - timedelta(hours=1),
                numero_venta=f"VTA-{uuid4().hex[:8].upper()}",
                empresa_id=2,
            ),
            Return(
                id_devolucion=14,
                id_venta=201,
                id_usuario_solicitante=20,
                clave_idempotencia=uuid4(),
                tipo="DEVOLUCION",
                estado="SOLICITADA",
                motivo="Devolución en empresa 2",
                created_at=self.now,
            ),
        ])
        self.db.commit()

        # Restaurar contexto para Empresa 1 por defecto
        set_tenant_context(self.db, 1)

        self.admin_user = NS(id_usuario=1, rol="ADMINISTRADOR", empresa_id=1)
        self.cajero_user = NS(id_usuario=11, rol="CAJERO", empresa_id=1)
        self.cliente1_user = NS(id_usuario=20, rol="CLIENTE", empresa_id=1)
        self.cliente2_user = NS(id_usuario=21, rol="CLIENTE", empresa_id=1)
        self.admin_empresa2 = NS(id_usuario=30, rol="ADMINISTRADOR", empresa_id=2)

        self.service = ReturnsService(self.db, stripe_service=self.mock_stripe)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_client_queries_and_filters_own_returns_with_timeline(self):
        """1. El CLIENTE consulta sus solicitudes, filtra por tipo/estado/modalidad y ve su cronograma sin ver datos ajenos."""
        set_tenant_context(self.db, 1)

        # Consulta todas las solicitudes del cliente 1
        all_client1 = self.service.list_client_returns(self.cliente1_user)
        self.assertEqual(len(all_client1), 2)
        return_ids = {r["id_devolucion"] for r in all_client1}
        self.assertEqual(return_ids, {11, 12})

        # Privacidad: Cliente 2 solo ve su solicitud y no las de Cliente 1
        all_client2 = self.service.list_client_returns(self.cliente2_user)
        self.assertEqual(len(all_client2), 1)
        self.assertEqual(all_client2[0]["id_devolucion"], 13)

        # Intento de consultar detalle ajeno por el cliente 2: debe lanzar 404
        with self.assertRaises(PaymentError) as cm:
            self.service.get_return(self.cliente2_user, 11)
        self.assertEqual(cm.exception.status_code, 404)

        # Filtro por tipo: CAMBIO
        cambios = self.service.list_client_returns(self.cliente1_user, tipo="CAMBIO")
        self.assertEqual(len(cambios), 1)
        self.assertEqual(cambios[0]["id_devolucion"], 11)
        self.assertEqual(cambios[0]["tipo"], "CAMBIO")

        # Filtro por modalidad: DELIVERY_SIMULADO
        deliveries = self.service.list_client_returns(self.cliente1_user, modalidad_entrega="DELIVERY_SIMULADO")
        self.assertEqual(len(deliveries), 1)
        self.assertEqual(deliveries[0]["id_devolucion"], 11)
        self.assertEqual(deliveries[0]["modalidad_entrega"], "DELIVERY_SIMULADO")

        # Filtro por estado: SOLICITADA
        solicitadas = self.service.list_client_returns(self.cliente1_user, estado="SOLICITADA")
        self.assertEqual(len(solicitadas), 1)
        self.assertEqual(solicitadas[0]["id_devolucion"], 12)

        # Consulta de detalle con cronograma / historial de progreso (CU19)
        detail = self.service.get_return(self.cliente1_user, 11)
        self.assertEqual(detail["codigo_solicitud"], "SOL-00011")
        self.assertEqual(detail["estado"], "APROBADA")
        self.assertIn("historial_progreso", detail)
        timeline = detail["historial_progreso"]
        self.assertEqual(len(timeline), 7)

        # Verificar estados de los pasos del cronograma para solicitud APROBADA
        self.assertEqual(timeline[0]["clave"], "SOLICITUD_REGISTRADA")
        self.assertEqual(timeline[0]["estado"], "COMPLETADO")
        self.assertEqual(timeline[1]["clave"], "EVALUACION_INICIAL")
        self.assertEqual(timeline[1]["estado"], "COMPLETADO")
        self.assertEqual(timeline[2]["clave"], "MODALIDAD_ENTREGA")
        self.assertEqual(timeline[2]["estado"], "COMPLETADO")
        self.assertEqual(timeline[3]["clave"], "RECEPCION_PRENDA")
        self.assertEqual(timeline[3]["estado"], "COMPLETADO")
        self.assertEqual(timeline[4]["clave"], "INSPECCION_FISICA")
        self.assertEqual(timeline[4]["estado"], "COMPLETADO")
        self.assertEqual(timeline[6]["clave"], "PROCESAMIENTO_FINAL")
        self.assertEqual(timeline[6]["estado"], "ACTUAL")

    def test_staff_queries_and_branch_tenant_isolation(self):
        """2. CAJERO consulta solicitudes de sus sucursales asignadas y ADMINISTRADOR con aislamiento multitenant."""
        set_tenant_context(self.db, 1)

        # CAJERO asignado a Sucursal 2: ve SOL-11 y SOL-12 (de Sucursal 2), no SOL-13 (Sucursal 3)
        cajero_list = self.service.list_returns(self.cajero_user)
        self.assertEqual(len(cajero_list), 2)
        cajero_ids = {r["id_devolucion"] for r in cajero_list}
        self.assertEqual(cajero_ids, {11, 12})

        # CAJERO intentando filtrar por Sucursal 3 (no autorizada para él): debe lanzar 403
        with self.assertRaises(PaymentError) as cm:
            self.service.list_returns(self.cajero_user, id_sucursal=3)
        self.assertEqual(cm.exception.status_code, 403)

        # CAJERO intentando acceder a detalle de Sucursal 3 (SOL-13): debe lanzar 403
        with self.assertRaises(PaymentError) as cm:
            self.service.get_return(self.cajero_user, 13, staff=True)
        self.assertEqual(cm.exception.status_code, 403)

        # ADMINISTRADOR Empresa 1: ve todas las sucursales de Empresa 1 (SOL-11, 12, 13)
        admin_list = self.service.list_returns(self.admin_user)
        self.assertEqual(len(admin_list), 3)
        admin_ids = {r["id_devolucion"] for r in admin_list}
        self.assertEqual(admin_ids, {11, 12, 13})

        # ADMINISTRADOR filtrando por sucursal específica (id_sucursal=3)
        admin_branch3 = self.service.list_returns(self.admin_user, id_sucursal=3)
        self.assertEqual(len(admin_branch3), 1)
        self.assertEqual(admin_branch3[0]["id_devolucion"], 13)

        # Aislamiento multitenant: ADMINISTRADOR de Empresa 2 solo ve solicitudes de Empresa 2
        set_tenant_context(self.db, 2)
        empresa2_list = self.service.list_returns(self.admin_empresa2)
        self.assertEqual(len(empresa2_list), 1)
        self.assertEqual(empresa2_list[0]["id_devolucion"], 14)

        # Detalle de staff incluye trazabilidad completa (inspector, receptor, evaluador, timeline)
        set_tenant_context(self.db, 1)
        staff_detail = self.service.get_return(self.admin_user, 11, staff=True)
        self.assertEqual(staff_detail["codigo_solicitud"], "SOL-00011")
        self.assertIsNotNone(staff_detail["evaluador"])
        self.assertIsNotNone(staff_detail["receptor"])
        self.assertIsNotNone(staff_detail["inspector"])
        self.assertEqual(staff_detail["estado_fisico"], "OPTIMO")
        self.assertEqual(len(staff_detail["historial_progreso"]), 7)
