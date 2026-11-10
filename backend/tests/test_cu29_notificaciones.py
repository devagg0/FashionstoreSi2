"""CU29: Gestionar notificaciones de reservas y compras.
Batería de 3 pruebas focalizadas:
1. Generación automática e idempotente de notificaciones ante eventos reales (reservas, pagos, compras).
2. Consulta y lectura de notificaciones desde la cuenta CLIENTE (listado, contador y marcar leídas).
3. Seguridad multitenant y aislamiento estricto entre usuarios y empresas.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest import TestCase
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.tenant_context import set_tenant_context
from app.models.branch import Branch
from app.models.client import Client
from app.models.notification import Notification
from app.models.payment import Payment
from app.models.reservation import Reservation
from app.models.role import Role
from app.models.sale import Sale
from app.models.user import User
from app.services.notification_service import NotificationService


class CU29NotificationManagementTests(TestCase):
    """Pruebas unitarias para el servicio y flujos de notificación (CU29)."""

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
            Reservation,
            Sale,
            Payment,
            Notification,
        ):
            model.__table__.create(self.engine)
        self.db = Session(self.engine, autoflush=False)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)

    def _seed_user_and_client(self, empresa_id: int, user_id: int, email: str):
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
        return user, client

    def test_01_automatic_and_idempotent_notification_generation(self):
        """1. Valida la generación automática e idempotente de notificaciones ante eventos reales."""
        u1, c1 = self._seed_user_and_client(empresa_id=1, user_id=1, email="cliente1@fashionstore.test")
        now = datetime.now()

        # Sucursal y Reserva
        branch = Branch(
            empresa_id=1, id_ciudad=1, nombre="Sucursal Central", direccion="Dir 1", estado=True
        )
        self.db.add(branch)
        self.db.commit()

        reservation = Reservation(
            empresa_id=1,
            id_cliente=c1.id_cliente,
            id_sucursal=branch.id_sucursal,
            codigo="RES-2026-001",
            estado="PENDIENTE",
            fecha_expiracion=now + timedelta(days=2),
            fecha_atencion_programada=now + timedelta(days=1),
            created_at=now,
        )
        self.db.add(reservation)
        self.db.commit()

        # 1. Evento: Reserva Creada (sin enviar correo real en testing)
        n_created = NotificationService.notify_reservation_created(self.db, reservation)
        self.assertIsNotNone(n_created)
        self.assertEqual(n_created.tipo, "RESERVA_CREADA")
        self.assertEqual(n_created.id_usuario, u1.id_usuario)
        self.assertEqual(n_created.codigo_referencia, "RES-2026-001")
        self.assertFalse(n_created.leido)

        # Idempotencia: Llamar de nuevo con la misma reserva no debe duplicar la notificación
        n_duplicate = NotificationService.notify_reservation_created(self.db, reservation)
        self.assertEqual(n_created.id_notificacion, n_duplicate.id_notificacion)
        total_created = (
            self.db.query(Notification)
            .filter(Notification.tipo == "RESERVA_CREADA", Notification.id_usuario == u1.id_usuario)
            .count()
        )
        self.assertEqual(total_created, 1)

        # 2. Eventos posteriores de reservas: Confirmada, Cancelada, Expirada
        n_confirmed = NotificationService.notify_reservation_confirmed(self.db, reservation)
        self.assertEqual(n_confirmed.tipo, "RESERVA_CONFIRMADA")

        n_cancelled = NotificationService.notify_reservation_cancelled(self.db, reservation)
        self.assertEqual(n_cancelled.tipo, "RESERVA_CANCELADA")

        n_expired = NotificationService.notify_reservation_expired(self.db, reservation)
        self.assertEqual(n_expired.tipo, "RESERVA_EXPIRADA")

        # 3. Eventos de Ventas y Pagos
        sale = Sale(
            empresa_id=1,
            id_sucursal=branch.id_sucursal,
            id_cliente=c1.id_cliente,
            id_empleado=None,
            numero_venta="DIG-VTA-001",
            subtotal=Decimal("250.00"),
            descuento_total=Decimal("0.00"),
            total=Decimal("250.00"),
            canal="DIGITAL",
            moneda="BOB",
            estado="COMPLETADA",
            fecha_venta=now,
            fecha_completada=now,
        )
        self.db.add(sale)
        self.db.commit()

        payment = Payment(
            empresa_id=1,
            id_venta=sale.id_venta,
            medio="TARJETA",
            proveedor="STRIPE",
            entorno="TEST",
            monto=Decimal("250.00"),
            moneda="BOB",
            estado="APROBADO",
            referencia_externa="pi_test_123",
            clave_idempotencia=uuid4(),
            fecha_aprobacion=now,
        )
        self.db.add(payment)
        self.db.commit()

        n_pay = NotificationService.notify_payment_confirmed(self.db, sale, payment)
        self.assertEqual(n_pay.tipo, "PAGO_CONFIRMADO")

        n_purchase = NotificationService.notify_purchase_confirmed(self.db, sale)
        self.assertEqual(n_purchase.tipo, "COMPRA_CONFIRMADA")

        # Pago rechazado
        payment_fail = Payment(
            empresa_id=1,
            id_venta=sale.id_venta,
            medio="TARJETA",
            proveedor="STRIPE",
            entorno="TEST",
            monto=Decimal("250.00"),
            moneda="BOB",
            estado="RECHAZADO",
            referencia_externa="pi_test_fail_456",
            clave_idempotencia=uuid4(),
        )
        self.db.add(payment_fail)
        self.db.commit()

        n_rejected = NotificationService.notify_payment_rejected(self.db, sale, payment_fail)
        self.assertEqual(n_rejected.tipo, "PAGO_RECHAZADO")

    def test_02_client_query_unread_and_mark_as_read(self):
        """2. Valida la consulta de listado, conteo de no leídas y transición a leídas."""
        u1, c1 = self._seed_user_and_client(empresa_id=1, user_id=1, email="cliente1@fashionstore.test")

        # Sembrar 3 notificaciones para u1
        n1 = NotificationService.create_notification(
            self.db,
            empresa_id=1,
            usuario_id=u1.id_usuario,
            tipo="RESERVA_CREADA",
            titulo="Reserva #1",
            mensaje="Tu reserva ha sido creada",
            referencia_origen="RESERVA",
            referencia_id=10,
            send_email=False,
        )
        n2 = NotificationService.create_notification(
            self.db,
            empresa_id=1,
            usuario_id=u1.id_usuario,
            tipo="PAGO_CONFIRMADO",
            titulo="Pago aprobado",
            mensaje="Tu pago fue recibido",
            referencia_origen="PAGO",
            referencia_id=20,
            send_email=False,
        )
        n3 = NotificationService.create_notification(
            self.db,
            empresa_id=1,
            usuario_id=u1.id_usuario,
            tipo="COMPRA_CONFIRMADA",
            titulo="Compra lista",
            mensaje="Tu compra ha sido procesada",
            referencia_origen="VENTA",
            referencia_id=30,
            send_email=False,
        )

        # 1. Conteo inicial: 3 no leídas
        unread_res = NotificationService.get_unread_count(self.db, empresa_id=1, usuario_id=u1.id_usuario)
        self.assertEqual(unread_res.no_leidas, 3)

        # 2. Listado: 3 elementos paginados
        list_res = NotificationService.list_notifications(
            self.db, empresa_id=1, usuario_id=u1.id_usuario, page=1, page_size=10
        )
        self.assertEqual(list_res.total, 3)
        self.assertEqual(list_res.no_leidas, 3)
        self.assertEqual(len(list_res.items), 3)

        # 3. Marcar una como leída (n1)
        read_n1 = NotificationService.mark_as_read(
            self.db, empresa_id=1, usuario_id=u1.id_usuario, notification_id=n1.id_notificacion
        )
        self.assertTrue(read_n1.leido)
        self.assertIsNotNone(read_n1.fecha_lectura)

        # Conteo posterior: 2 no leídas
        unread_after = NotificationService.get_unread_count(self.db, empresa_id=1, usuario_id=u1.id_usuario)
        self.assertEqual(unread_after.no_leidas, 2)

        # 4. Marcar todas como leídas
        mark_all = NotificationService.mark_all_as_read(self.db, empresa_id=1, usuario_id=u1.id_usuario)
        self.assertTrue(mark_all.success)
        self.assertEqual(mark_all.marcadas, 2)

        # Conteo final: 0 no leídas
        final_unread = NotificationService.get_unread_count(self.db, empresa_id=1, usuario_id=u1.id_usuario)
        self.assertEqual(final_unread.no_leidas, 0)

    def test_03_multitenant_security_and_user_isolation(self):
        """3. Valida seguridad multitenant y aislamiento estricto entre usuarios y empresas."""
        # Empresa 1 con Usuario 1 y Usuario 2
        u1, c1 = self._seed_user_and_client(empresa_id=1, user_id=1, email="user1@e1.test")
        u2, c2 = self._seed_user_and_client(empresa_id=1, user_id=2, email="user2@e1.test")

        # Empresa 2 con Usuario 3
        u3, c3 = self._seed_user_and_client(empresa_id=2, user_id=3, email="user3@e2.test")

        # Crear notificación para u1 en Empresa 1
        n_u1 = NotificationService.create_notification(
            self.db,
            empresa_id=1,
            usuario_id=u1.id_usuario,
            tipo="RESERVA_CREADA",
            titulo="Notificación u1",
            mensaje="Mensaje u1",
            send_email=False,
        )

        # Crear notificación para u3 en Empresa 2
        n_u3 = NotificationService.create_notification(
            self.db,
            empresa_id=2,
            usuario_id=u3.id_usuario,
            tipo="RESERVA_CREADA",
            titulo="Notificación u3",
            mensaje="Mensaje u3",
            send_email=False,
        )

        # Aislamiento entre usuarios dentro de la misma empresa:
        # u2 consulta notificaciones -> debe recibir 0
        list_u2 = NotificationService.list_notifications(
            self.db, empresa_id=1, usuario_id=u2.id_usuario
        )
        self.assertEqual(list_u2.total, 0)
        self.assertEqual(len(list_u2.items), 0)

        # Intento de u2 de marcar como leída la notificación de u1 -> HTTP 404
        with self.assertRaises(HTTPException) as ctx_u2:
            NotificationService.mark_as_read(
                self.db,
                empresa_id=1,
                usuario_id=u2.id_usuario,
                notification_id=n_u1.id_notificacion,
            )
        self.assertEqual(ctx_u2.exception.status_code, 404)

        # Aislamiento multitenant entre empresas:
        # u1 (Empresa 1) no puede acceder a notificación de Empresa 2
        with self.assertRaises(HTTPException) as ctx_cross_tenant:
            NotificationService.mark_as_read(
                self.db,
                empresa_id=1,
                usuario_id=u1.id_usuario,
                notification_id=n_u3.id_notificacion,
            )
        self.assertEqual(ctx_cross_tenant.exception.status_code, 404)

        # u3 (Empresa 2) ve únicamente su propia notificación
        list_u3 = NotificationService.list_notifications(
            self.db, empresa_id=2, usuario_id=u3.id_usuario
        )
        self.assertEqual(list_u3.total, 1)
        self.assertEqual(list_u3.items[0].id_notificacion, n_u3.id_notificacion)
