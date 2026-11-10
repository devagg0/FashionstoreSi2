"""Validación focalizada de CU29 — Notificaciones (máximo 2 pruebas).

1. Generación automática ante eventos reales (reserva y compra), consulta de «Mis notificaciones»,
   contador de no leídas y marcado individual y masivo como leída.
2. Aislamiento estricto multitenant y por usuario, idempotencia contra duplicados y resiliencia
   transaccional ante fallos de notificación.
"""

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.tenant_context import set_tenant_context
from app.models.branch import Branch
from app.models.branch_inventory import BranchInventory
from app.models.category import Category
from app.models.city import City
from app.models.client import Client
from app.models.color import Color
from app.models.notification import Notification
from app.models.payment import Payment
from app.models.product import Product
from app.models.product_image import ProductImage
from app.models.product_variant import ProductVariant
from app.models.reservation import Reservation
from app.models.reservation_detail import ReservationDetail
from app.models.role import Role
from app.models.sale import Sale
from app.models.season import Season
from app.models.size import Size
from app.models.user import User
from app.schemas.client_reservations import ReservationCreateRequest
from app.services.client_reservations import ClientReservationService
from app.services.notification_service import NotificationService
from app.services.payments import PaymentsService


class CU29NotificacionesValidacionTests(TestCase):
    """Batería de validación focalizada para el CU29."""

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
            City,
            Branch,
            Category,
            Season,
            Size,
            Color,
            Product,
            ProductImage,
            ProductVariant,
            BranchInventory,
            Reservation,
            ReservationDetail,
            Sale,
            Payment,
            Notification,
        ):
            model.__table__.create(self.engine)

        self.db = Session(self.engine, autoflush=False)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)

        set_tenant_context(self.db, 1)

        city = City(id_ciudad=1, nombre="La Paz")
        self.db.add(city)

        role = Role(id_rol=2, nombre="CLIENTE", descripcion="Cliente regular")
        self.db.add(role)

        self.user = User(
            id_usuario=10,
            id_rol=2,
            nombre="Valeria",
            apellido="Gomez",
            correo="valeria@cliente.com",
            password_hash="hash123",
            estado=True,
        )
        self.db.add(self.user)

        self.client = Client(id_cliente=5, id_usuario=10, empresa_id=1)
        self.db.add(self.client)

        self.branch = Branch(
            id_sucursal=1,
            id_ciudad=1,
            empresa_id=1,
            nombre="Sucursal Principal",
            direccion="Av. Principal 100",
            estado=True,
            hora_apertura=time(8, 0),
            hora_cierre=time(20, 0),
        )
        self.db.add(self.branch)

        cat = Category(id_categoria=1, empresa_id=1, nombre="Poleras", estado=True)
        self.db.add(cat)

        size = Size(id_talla=1, nombre="M")
        self.db.add(size)

        color = Color(id_color=1, nombre="Negro", codigo_hex="#000000")
        self.db.add(color)

        prod = Product(
            id_producto=1,
            empresa_id=1,
            id_categoria=1,
            nombre="Polera Casual",
            seccion="UNISEX",
            precio=Decimal("120.00"),
            estado=True,
        )
        self.db.add(prod)

        img = ProductImage(
            id_imagen_producto=1,
            id_producto=1,
            empresa_id=1,
            url_imagen="https://example.com/polera.jpg",
            es_principal=True,
        )
        self.db.add(img)

        variant = ProductVariant(
            id_variante_producto=1,
            id_producto=1,
            id_talla=1,
            id_color=1,
            sku="POL-CAS-M-NEG",
            estado=True,
        )
        self.db.add(variant)

        inv = BranchInventory(
            id_inventario_sucursal=1,
            id_sucursal=1,
            id_variante_producto=1,
            empresa_id=1,
            stock_actual=15,
            stock_reservado=0,
            stock_minimo=1,
        )
        self.db.add(inv)
        self.db.commit()

        now_bolivia = datetime.now(timezone(timedelta(hours=-4)))
        self.scheduled_slot = (now_bolivia + timedelta(days=2)).replace(
            hour=10, minute=0, second=0, microsecond=0
        )

    def test_1_event_generation_and_client_notifications_workflow(self):
        """1. Generación automática ante eventos reales (reserva y compra), listado, conteo y marcado como leída."""
        # 1.1 Crear reserva online válida
        res_svc = ClientReservationService(self.db)
        res_svc.repository.lock_reservation_slots = lambda *args, **kwargs: None
        res_svc.catalog.get_product = lambda *args, **kwargs: SimpleNamespace(
            precio_final=Decimal("120.00")
        )

        req = ReservationCreateRequest(
            id_sucursal=1,
            fecha_atencion_programada=self.scheduled_slot,
            items=[{"id_variante_producto": 1, "cantidad": 2}],
        )

        with patch("app.services.notification_service.BrevoEmailClient"):
            res_result = res_svc.create_reservation(self.user.id_usuario, req)

        self.assertIsNotNone(res_result.id_reserva)

        # 1.2 Crear y confirmar compra/pago
        now = datetime.now()
        sale = Sale(
            empresa_id=1,
            id_sucursal=1,
            id_cliente=self.client.id_cliente,
            id_empleado=None,
            numero_venta="VTA-2026-001",
            subtotal=Decimal("240.00"),
            descuento_total=Decimal("0.00"),
            total=Decimal("240.00"),
            canal="DIGITAL",
            moneda="BOB",
            estado="PENDIENTE",
            fecha_venta=now,
        )
        self.db.add(sale)
        self.db.commit()

        payment = Payment(
            empresa_id=1,
            id_venta=sale.id_venta,
            medio="TARJETA",
            proveedor="STRIPE",
            entorno="TEST",
            monto=Decimal("240.00"),
            moneda="BOB",
            estado="APROBADO",
            referencia_externa="pi_test_12345",
            clave_idempotencia=uuid4(),
            fecha_aprobacion=now,
        )
        self.db.add(payment)
        self.db.commit()

        with patch("app.services.notification_service.BrevoEmailClient"):
            NotificationService.notify_payment_confirmed(self.db, sale, payment)
            NotificationService.notify_purchase_confirmed(self.db, sale)

        # 1.3 Consultar listado de «Mis notificaciones»
        notif_list = NotificationService.list_notifications(
            self.db, empresa_id=1, usuario_id=self.user.id_usuario
        )
        self.assertEqual(notif_list.total, 3)
        self.assertEqual(notif_list.no_leidas, 3)
        tipos = {item.tipo for item in notif_list.items}
        self.assertIn("RESERVA_CREADA", tipos)
        self.assertIn("PAGO_CONFIRMADO", tipos)
        self.assertIn("COMPRA_CONFIRMADA", tipos)

        # 1.4 Consultar contador de no leídas
        unread_before = NotificationService.get_unread_count(
            self.db, empresa_id=1, usuario_id=self.user.id_usuario
        )
        self.assertEqual(unread_before.no_leidas, 3)

        # 1.5 Marcar una notificación como leída
        first_id = notif_list.items[0].id_notificacion
        marked_single = NotificationService.mark_as_read(
            self.db,
            empresa_id=1,
            usuario_id=self.user.id_usuario,
            notification_id=first_id,
        )
        self.assertTrue(marked_single.leido)

        unread_mid = NotificationService.get_unread_count(
            self.db, empresa_id=1, usuario_id=self.user.id_usuario
        )
        self.assertEqual(unread_mid.no_leidas, 2)

        # 1.6 Marcar todas como leídas
        marked_all = NotificationService.mark_all_as_read(
            self.db, empresa_id=1, usuario_id=self.user.id_usuario
        )
        self.assertTrue(marked_all.success)
        self.assertEqual(marked_all.marcadas, 2)

        unread_final = NotificationService.get_unread_count(
            self.db, empresa_id=1, usuario_id=self.user.id_usuario
        )
        self.assertEqual(unread_final.no_leidas, 0)

    def test_2_multitenant_isolation_idempotency_and_failure_resilience(self):
        """2. Aislamiento por tenant/usuario, prevención de duplicados y resiliencia ante fallo de notificación."""
        # 2.1 Aislamiento entre usuarios de la misma empresa
        user2 = User(
            id_usuario=20,
            id_rol=2,
            nombre="Carlos",
            apellido="Perez",
            correo="carlos@cliente.com",
            password_hash="hash456",
            estado=True,
        )
        self.db.add(user2)
        client2 = Client(id_cliente=6, id_usuario=20, empresa_id=1)
        self.db.add(client2)
        self.db.commit()

        # Usuario en Empresa 2 (Tenant diferente con su propio contexto)
        set_tenant_context(self.db, 2)
        user3 = User(
            id_usuario=30,
            id_rol=2,
            nombre="Elena",
            apellido="Torres",
            correo="elena@otrotenant.com",
            password_hash="hash789",
            estado=True,
        )
        self.db.add(user3)
        client3 = Client(id_cliente=7, id_usuario=30, empresa_id=2)
        self.db.add(client3)
        self.db.commit()

        set_tenant_context(self.db, 1)

        # Sembrar notificación para Usuario 1 en Empresa 1
        n1 = NotificationService.create_notification(
            self.db,
            empresa_id=1,
            usuario_id=self.user.id_usuario,
            tipo="RESERVA_CREADA",
            titulo="Reserva Valeria",
            mensaje="Mensaje Valeria",
            clave_idempotencia="KEY:U1:RES1",
            send_email=False,
        )
        # Sembrar notificación para Usuario 3 en Empresa 2
        n3 = NotificationService.create_notification(
            self.db,
            empresa_id=2,
            usuario_id=user3.id_usuario,
            tipo="RESERVA_CREADA",
            titulo="Reserva Elena",
            mensaje="Mensaje Elena",
            clave_idempotencia="KEY:U3:RES1",
            send_email=False,
        )

        # Usuario 2 no ve notificaciones de Usuario 1
        list_u2 = NotificationService.list_notifications(
            self.db, empresa_id=1, usuario_id=user2.id_usuario
        )
        self.assertEqual(list_u2.total, 0)

        # Usuario 1 no puede marcar ni ver notificaciones de Empresa 2
        with self.assertRaises(HTTPException) as ctx:
            NotificationService.mark_as_read(
                self.db,
                empresa_id=1,
                usuario_id=self.user.id_usuario,
                notification_id=n3.id_notificacion,
            )
        self.assertEqual(ctx.exception.status_code, 404)

        # 2.2 Idempotencia estricta: reintento con la misma clave no duplica
        n1_dup = NotificationService.create_notification(
            self.db,
            empresa_id=1,
            usuario_id=self.user.id_usuario,
            tipo="RESERVA_CREADA",
            titulo="Reserva Valeria",
            mensaje="Mensaje Valeria",
            clave_idempotencia="KEY:U1:RES1",
            send_email=False,
        )
        self.assertEqual(n1.id_notificacion, n1_dup.id_notificacion)
        count_u1 = (
            self.db.query(Notification)
            .filter(
                Notification.empresa_id == 1,
                Notification.id_usuario == self.user.id_usuario,
            )
            .count()
        )
        self.assertEqual(count_u1, 1)

        # 2.3 Resiliencia transaccional: una falla en el servicio de notificación no aborta la reserva comercial
        res_svc = ClientReservationService(self.db)
        res_svc.repository.lock_reservation_slots = lambda *args, **kwargs: None
        res_svc.catalog.get_product = lambda *args, **kwargs: SimpleNamespace(
            precio_final=Decimal("120.00")
        )

        req = ReservationCreateRequest(
            id_sucursal=1,
            fecha_atencion_programada=self.scheduled_slot,
            items=[{"id_variante_producto": 1, "cantidad": 1}],
        )

        def failing_notify(*args, **kwargs):
            raise RuntimeError("Falla inducida de notificación externa")

        with patch.object(
            NotificationService, "notify_reservation_created", side_effect=failing_notify
        ):
            # La reserva se confirma exitosamente sin arrojar error 500
            res = res_svc.create_reservation(self.user.id_usuario, req)

        self.assertIsNotNone(res.id_reserva)
        self.assertTrue(res.codigo.startswith("RSV-"))
        saved = self.db.get(Reservation, res.id_reserva)
        self.assertIsNotNone(saved)
        self.assertEqual(saved.estado, "PENDIENTE")
