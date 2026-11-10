"""CU30: Consultar estado de compras, reservas y pagos.
Batería de 2 pruebas focalizadas:
1. Listado, detalle y resumen de operaciones con datos reales a través del router y servicio.
2. Estados de pago, operaciones offline sincronizadas, aislamiento multitenant y manejo de errores.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest import TestCase
from uuid import uuid4

from fastapi.responses import JSONResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.tenant_context import set_tenant_context
from app.models.branch import Branch
from app.models.category import Category
from app.models.client import Client
from app.models.color import Color
from app.models.offline_reservation_sync import OfflineReservationSync
from app.models.payment import Payment
from app.models.product import Product
from app.models.product_image import ProductImage
from app.models.product_variant import ProductVariant
from app.models.reservation import Reservation
from app.models.reservation_detail import ReservationDetail
from app.models.role import Role
from app.models.sale import Sale
from app.models.sale_detail import SaleDetail
from app.models.size import Size
from app.models.user import User
from app.routers.client_operations import (
    get_operation_detail,
    get_operations_summary,
    list_operations,
)
from app.schemas.auth import AuthenticatedUserData


class CU30ClientOperationsTests(TestCase):
    """Pruebas focalizadas para el CU30: Consulta unificada de operaciones del cliente."""

    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        for model in (
            Role,
            User,
            Client,
            Branch,
            Category,
            Product,
            Size,
            Color,
            ProductVariant,
            ProductImage,
            Reservation,
            ReservationDetail,
            Sale,
            SaleDetail,
            Payment,
            OfflineReservationSync,
        ):
            model.__table__.create(self.engine)
        self.db = Session(self.engine, autoflush=False)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)

    def _seed_user_and_client(
        self, empresa_id: int, user_id: int, email: str
    ) -> tuple[AuthenticatedUserData, Client]:
        set_tenant_context(self.db, empresa_id)

        role = self.db.query(Role).filter(Role.id_rol == 2).first()
        if not role:
            role = Role(id_rol=2, nombre="CLIENTE", descripcion="Cliente regular")
            self.db.add(role)
            self.db.commit()

        user = User(
            id_usuario=user_id,
            id_rol=2,
            nombre=f"Cliente{user_id}",
            apellido="Fashion",
            correo=email,
            password_hash="hash123",
            estado=True,
        )
        self.db.add(user)
        self.db.commit()

        client = Client(
            empresa_id=empresa_id,
            id_usuario=user.id_usuario,
        )
        self.db.add(client)
        self.db.commit()

        auth_user = AuthenticatedUserData(
            id_usuario=user.id_usuario,
            nombre=user.nombre,
            apellido=user.apellido,
            correo=user.correo,
            rol="CLIENTE",
            id_empresa=empresa_id,
        )
        return auth_user, client

    def _seed_branch_and_product(self, empresa_id: int) -> tuple[Branch, ProductVariant]:
        set_tenant_context(self.db, empresa_id)
        branch = Branch(
            empresa_id=empresa_id,
            id_ciudad=1,
            nombre="Sucursal Central",
            direccion="Av. Principal 123",
            telefono="70000001",
            estado=True,
        )
        self.db.add(branch)

        cat = Category(
            empresa_id=empresa_id,
            nombre="Vestidos",
            descripcion="Vestidos elegantes",
            estado=True,
        )
        self.db.add(cat)
        self.db.commit()

        product = Product(
            empresa_id=empresa_id,
            id_categoria=cat.id_categoria,
            nombre="Vestido Seda",
            seccion="MUJER",
            precio=Decimal("150.00"),
            estado=True,
        )
        self.db.add(product)

        size = Size(empresa_id=empresa_id, nombre="M")
        color = Color(empresa_id=empresa_id, nombre="Negro", codigo_hex="#000000")
        self.db.add_all([size, color])
        self.db.commit()

        variant = ProductVariant(
            empresa_id=empresa_id,
            id_producto=product.id_producto,
            id_talla=size.id_talla,
            id_color=color.id_color,
            sku="VES-SEDA-M-NEG",
            estado=True,
        )
        self.db.add(variant)
        self.db.commit()
        return branch, variant

    def test_01_listado_y_resumen_operaciones_con_datos_reales(self):
        """1. Listado paginado, resumen y detalle de compras, reservas, pagos y sync offline vía router."""
        empresa_id = 1
        set_tenant_context(self.db, empresa_id)
        auth_user, client = self._seed_user_and_client(empresa_id, 101, "cliente101@test.com")
        branch, variant = self._seed_branch_and_product(empresa_id)

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # 1. Compra completada con pago aprobado
        sale = Sale(
            empresa_id=empresa_id,
            id_cliente=client.id_cliente,
            id_sucursal=branch.id_sucursal,
            numero_venta="VTA-2026-0001",
            subtotal=Decimal("150.00"),
            descuento_total=Decimal("0.00"),
            total=Decimal("150.00"),
            moneda="BOB",
            canal="DIGITAL",
            estado="COMPLETADA",
            fecha_venta=now,
            fecha_completada=now,
        )
        self.db.add(sale)
        self.db.commit()

        self.db.add(
            SaleDetail(
                empresa_id=empresa_id,
                id_venta=sale.id_venta,
                id_variante_producto=variant.id_variante_producto,
                cantidad=1,
                precio_unitario=Decimal("150.00"),
                descuento_unitario=Decimal("0.00"),
                subtotal_linea=Decimal("150.00"),
            )
        )
        self.db.add(
            Payment(
                empresa_id=empresa_id,
                id_venta=sale.id_venta,
                medio="TARJETA",
                proveedor="STRIPE",
                entorno="TEST",
                estado="APROBADO",
                monto=Decimal("150.00"),
                moneda="BOB",
                referencia_externa="ch_stripe_test_123",
                clave_idempotencia=uuid4(),
                fecha_aprobacion=now,
                created_at=now,
            )
        )

        # 2. Reserva originada offline y sincronizada
        reservation = Reservation(
            empresa_id=empresa_id,
            id_cliente=client.id_cliente,
            id_sucursal=branch.id_sucursal,
            codigo="RSV-2026-0001",
            estado="CONFIRMADA",
            fecha_atencion_programada=now + timedelta(days=2),
            fecha_expiracion=now + timedelta(days=5),
            created_at=now,
        )
        self.db.add(reservation)
        self.db.commit()

        self.db.add(
            ReservationDetail(
                empresa_id=empresa_id,
                id_reserva=reservation.id_reserva,
                id_variante_producto=variant.id_variante_producto,
                cantidad=2,
                precio_unitario=Decimal("150.00"),
            )
        )
        self.db.add(
            OfflineReservationSync(
                empresa_id=empresa_id,
                uuid_reserva_offline="off-uuid-res-001",
                id_reserva=reservation.id_reserva,
                codigo_reserva="RSV-2026-0001",
                id_sucursal=branch.id_sucursal,
                id_cliente=client.id_cliente,
                id_usuario=auth_user.id_usuario,
                estado_sincronizacion="SINCRONIZADA",
                fecha_reserva_offline=now,
            )
        )
        self.db.commit()

        # Invocar endpoints del router tal como los consume Angular (page=1, page_size=15)
        res_list = list_operations(client=auth_user, db=self.db, page=1, page_size=15)
        self.assertNotIsInstance(res_list, JSONResponse)
        self.assertTrue(res_list.success)
        self.assertEqual(res_list.total, 3)  # 1 Compra + 1 Reserva + 1 Pago sin duplicar la reserva offline

        compra_op = next(op for op in res_list.items if op.tipo == "COMPRA")
        self.assertEqual(compra_op.codigo, "VTA-2026-0001")
        self.assertTrue(compra_op.confirmada)
        self.assertIsNotNone(compra_op.pago)
        self.assertTrue(compra_op.pago.confirmado)

        reserva_op = next(op for op in res_list.items if op.tipo == "RESERVA")
        self.assertEqual(reserva_op.origen, "OFFLINE_SYNC")
        self.assertEqual(reserva_op.uuid_offline, "off-uuid-res-001")
        self.assertEqual(reserva_op.importe, Decimal("300.00"))

        # Resumen vía router (/api/client/operations/summary)
        summary = get_operations_summary(client=auth_user, db=self.db)
        self.assertNotIsInstance(summary, JSONResponse)
        self.assertTrue(summary.success)
        self.assertEqual(summary.total_operaciones, 3)
        self.assertEqual(summary.total_compras, 1)
        self.assertEqual(summary.total_reservas, 1)
        self.assertEqual(summary.total_pagos, 1)
        self.assertEqual(summary.confirmadas, 3)
        self.assertEqual(summary.importe_total_compras, Decimal("150.00"))

        # Detalle vía router (/api/client/operations/COMPRA/{id})
        compra_det = get_operation_detail(
            tipo="COMPRA", id_referencia=sale.id_venta, client=auth_user, db=self.db
        )
        self.assertNotIsInstance(compra_det, JSONResponse)
        self.assertEqual(len(compra_det.data.detalles), 1)
        self.assertEqual(compra_det.data.detalles[0].producto, "Vestido Seda")

    def test_02_estados_pago_aislamiento_multitenant_y_manejo_errores(self):
        """2. Estados de pago reales, aislamiento multitenant por empresa/usuario y manejo de errores."""
        empresa_a = 1
        empresa_b = 2

        auth_a, client_a = self._seed_user_and_client(empresa_a, 201, "cliente_a@emp1.com")
        auth_b, _ = self._seed_user_and_client(empresa_a, 202, "cliente_b@emp1.com")
        branch_a, _ = self._seed_branch_and_product(empresa_a)
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        set_tenant_context(self.db, empresa_a)
        # Venta y pago rechazado de Cliente A
        sale_rechazada = Sale(
            empresa_id=empresa_a,
            id_cliente=client_a.id_cliente,
            id_sucursal=branch_a.id_sucursal,
            numero_venta="VTA-RECHAZADA-01",
            subtotal=Decimal("80.00"),
            descuento_total=Decimal("0.00"),
            total=Decimal("80.00"),
            moneda="BOB",
            canal="DIGITAL",
            estado="RECHAZADA",
            fecha_venta=now,
        )
        self.db.add(sale_rechazada)
        self.db.commit()

        pago_rechazado = Payment(
            empresa_id=empresa_a,
            id_venta=sale_rechazada.id_venta,
            medio="TARJETA",
            proveedor="STRIPE",
            entorno="TEST",
            estado="RECHAZADO",
            monto=Decimal("80.00"),
            moneda="BOB",
            referencia_externa="ch_declined_123",
            clave_idempotencia=uuid4(),
            created_at=now,
        )
        self.db.add(pago_rechazado)
        self.db.commit()

        # Cliente C en otra empresa (Empresa B)
        auth_c, _ = self._seed_user_and_client(empresa_b, 203, "cliente_c@emp2.com")

        # 1. Cliente A ve su pago RECHAZADO como no confirmado
        set_tenant_context(self.db, empresa_a)
        ops_a = list_operations(client=auth_a, db=self.db, page=1, page_size=15)
        pago_item = next(op for op in ops_a.items if op.tipo == "PAGO")
        self.assertFalse(pago_item.confirmada)
        self.assertFalse(pago_item.pago.confirmado)
        self.assertEqual(pago_item.estado, "RECHAZADO")
        self.assertEqual(pago_item.estado_etiqueta, "RECHAZADO")

        # 2. Cliente B (misma empresa, otro cliente) no ve operaciones de Cliente A y recibe 404 en detalle
        ops_b = list_operations(client=auth_b, db=self.db, page=1, page_size=15)
        self.assertEqual(ops_b.total, 0)
        det_b = get_operation_detail(
            tipo="COMPRA", id_referencia=sale_rechazada.id_venta, client=auth_b, db=self.db
        )
        self.assertIsInstance(det_b, JSONResponse)
        self.assertEqual(det_b.status_code, 404)

        # 3. Cliente C (otra empresa) recibe 404 al intentar acceder a la compra de Empresa A
        set_tenant_context(self.db, empresa_b)
        det_c = get_operation_detail(
            tipo="COMPRA", id_referencia=sale_rechazada.id_venta, client=auth_c, db=self.db
        )
        self.assertIsInstance(det_c, JSONResponse)
        self.assertEqual(det_c.status_code, 404)

        # 4. Usuario sin perfil de cliente en la empresa recibe 403
        spoofed_auth = AuthenticatedUserData(
            id_usuario=auth_c.id_usuario,
            nombre="Spoof",
            apellido="User",
            correo="cliente_c@emp2.com",
            rol="CLIENTE",
            id_empresa=empresa_a,
        )
        res_forbidden = list_operations(client=spoofed_auth, db=self.db, page=1, page_size=15)
        self.assertIsInstance(res_forbidden, JSONResponse)
        self.assertEqual(res_forbidden.status_code, 403)
