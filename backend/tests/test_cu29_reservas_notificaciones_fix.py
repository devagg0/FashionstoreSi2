"""Validación focalizada de corrección de error 500 en reservas y notificaciones CU29.

3 pruebas focalizadas requeridas:
1. Confirmar reserva online exitosa y verificar que se genere la notificación (RESERVA_CREADA).
2. Forzar un fallo controlado en el servicio de notificaciones y comprobar que la reserva se confirme sin error 500 ni pérdida de datos.
3. Registrar y sincronizar reservas offline verificando que no se creen registros duplicados ni fallen las transacciones.
"""

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

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
from app.models.product import Product
from app.models.product_image import ProductImage
from app.models.product_variant import ProductVariant
from app.models.reservation import Reservation
from app.models.reservation_detail import ReservationDetail
from app.models.role import Role
from app.models.season import Season
from app.models.size import Size
from app.models.user import User
from app.models.offline_reservation_sync import OfflineReservationSync
from app.schemas.auth import AuthenticatedUserData
from app.PK08.CU10_RegistrarReservaOffline.schemas import (
    OfflineReservationDetailRequest,
    OfflineReservationSyncRequest,
)
from app.PK08.CU10_RegistrarReservaOffline.service import OfflineReservationService
from app.schemas.client_reservations import ReservationCreateRequest
from app.services.client_reservations import ClientReservationService
from app.services.notification_service import NotificationService


class CU29ReservasNotificacionesFixTests(TestCase):
    """Validación de robustez transaccional e idempotencia entre reservas y notificaciones."""

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
            Notification,
            OfflineReservationSync,
        ):
            model.__table__.create(self.engine)

        self.db = Session(self.engine, autoflush=False)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)

        # Seed data
        set_tenant_context(self.db, 1)

        city = City(id_ciudad=1, nombre="La Paz")
        self.db.add(city)

        role = Role(id_rol=2, nombre="CLIENTE", descripcion="Cliente")
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
            nombre="Sucursal Central",
            direccion="Av. Principal 100",
            estado=True,
            hora_apertura=time(8, 0),
            hora_cierre=time(20, 0),
        )
        self.db.add(self.branch)

        category = Category(id_categoria=1, empresa_id=1, nombre="Poleras", estado=True)
        self.db.add(category)

        size = Size(id_talla=1, nombre="M")
        self.db.add(size)

        color = Color(id_color=1, nombre="Negro", codigo_hex="#000000")
        self.db.add(color)

        self.product = Product(
            id_producto=1,
            empresa_id=1,
            id_categoria=1,
            nombre="Polera Casual",
            seccion="UNISEX",
            precio=Decimal("120.00"),
            estado=True,
        )
        self.db.add(self.product)

        img = ProductImage(
            id_imagen_producto=1,
            id_producto=1,
            empresa_id=1,
            url_imagen="https://example.com/polera.jpg",
            es_principal=True,
        )
        self.db.add(img)

        self.variant = ProductVariant(
            id_variante_producto=1,
            id_producto=1,
            id_talla=1,
            id_color=1,
            sku="POL-CAS-M-NEG",
            estado=True,
        )
        self.db.add(self.variant)

        self.inventory = BranchInventory(
            id_inventario_sucursal=1,
            id_sucursal=1,
            id_variante_producto=1,
            empresa_id=1,
            stock_actual=15,
            stock_reservado=2,
            stock_minimo=1,
        )
        self.db.add(self.inventory)
        self.db.commit()

        # Slot futuro de atención en zona horaria boliviana (UTC-4)
        now_bolivia = datetime.now(timezone(timedelta(hours=-4)))
        self.scheduled_slot = (now_bolivia + timedelta(days=2)).replace(
            hour=10, minute=0, second=0, microsecond=0
        )

    def _setup_service(self) -> ClientReservationService:
        service = ClientReservationService(self.db)
        # Mock de serialización pg_advisory_xact_lock (específico de Postgres) y catálogo
        service.repository.lock_reservation_slots = lambda *args, **kwargs: None
        service.catalog.get_product = lambda *args, **kwargs: SimpleNamespace(
            precio_final=Decimal("120.00")
        )
        return service

    def test_1_online_reservation_success_generates_notification(self):
        """1. Confirmar reserva online exitosa y verificar que se genere la notificación (RESERVA_CREADA)."""
        service = self._setup_service()
        req = ReservationCreateRequest(
            id_sucursal=1,
            fecha_atencion_programada=self.scheduled_slot,
            items=[{"id_variante_producto": 1, "cantidad": 3}],
        )

        with patch("app.services.notification_service.BrevoEmailClient"):
            result = service.create_reservation(self.user.id_usuario, req)

        # Verificar respuesta de la reserva
        self.assertIsNotNone(result.id_reserva)
        self.assertTrue(result.codigo.startswith("RSV-"))
        self.assertEqual(result.cantidad_prendas, 3)
        self.assertEqual(result.total, Decimal("360.00"))

        # Verificar actualización del inventario
        inv = self.db.get(BranchInventory, self.inventory.id_inventario_sucursal)
        self.assertEqual(inv.stock_reservado, 5)  # 2 previos + 3

        # Verificar que se generó la notificación en la base de datos
        notif = self.db.query(Notification).filter(
            Notification.empresa_id == 1,
            Notification.id_usuario == self.user.id_usuario,
            Notification.tipo == "RESERVA_CREADA",
        ).first()

        self.assertIsNotNone(notif)
        self.assertEqual(notif.referencia_origen, "RESERVA")
        self.assertEqual(notif.referencia_id, result.id_reserva)
        self.assertEqual(notif.codigo_referencia, result.codigo)
        self.assertFalse(notif.leido)
        self.assertIn(result.codigo, notif.mensaje)

    def test_2_notification_failure_does_not_fail_reservation_confirmation(self):
        """2. Forzar un fallo controlado en el servicio de notificaciones y comprobar que la reserva se confirme sin error 500 ni pérdida de datos."""
        service = self._setup_service()
        req = ReservationCreateRequest(
            id_sucursal=1,
            fecha_atencion_programada=self.scheduled_slot,
            items=[{"id_variante_producto": 1, "cantidad": 2}],
        )

        # Forzar una excepción fatal / flush error dentro de la generación de notificación
        def broken_notify(db_session, reservation):
            # Provoca fallo de integridad en el savepoint
            db_session.add(
                Notification(
                    empresa_id=1,
                    id_usuario=10,
                    tipo="RESERVA_CREADA",
                    titulo=None,  # Violación NOT NULL intencional
                    mensaje="Error simulado",
                    clave_idempotencia=f"ERR:{reservation.id_reserva}",
                )
            )
            db_session.flush()

        with patch.object(
            NotificationService, "notify_reservation_created", side_effect=broken_notify
        ):
            # La reserva DEBE completarse sin lanzar ReservationPersistenceError ni HTTP 500
            result = service.create_reservation(self.user.id_usuario, req)

        # Comprobar que la reserva se guardó y confirmó válidamente
        self.assertIsNotNone(result.id_reserva)
        self.assertTrue(result.codigo.startswith("RSV-"))
        self.assertEqual(result.cantidad_prendas, 2)
        self.assertEqual(result.total, Decimal("240.00"))

        # El stock reservado debió incrementarse correctamente (2 previos + 2 = 4)
        inv = self.db.get(BranchInventory, self.inventory.id_inventario_sucursal)
        self.assertEqual(inv.stock_reservado, 4)

        # La reserva existe en la BD
        saved_res = self.db.get(Reservation, result.id_reserva)
        self.assertIsNotNone(saved_res)
        self.assertEqual(saved_res.estado, "PENDIENTE")

    def test_3_offline_reservation_sync_idempotent_without_duplicates_or_transaction_failure(self):
        """3. Registrar y sincronizar reservas offline verificando que no se creen registros duplicados ni fallen las transacciones."""
        client_user = AuthenticatedUserData(
            id_usuario=10,
            nombre="Valeria",
            apellido="Gomez",
            correo="valeria@cliente.com",
            rol="CLIENTE",
            id_empresa=1,
        )

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        offline_uuid = f"offline-{uuid4()}"

        sync_payload = OfflineReservationSyncRequest(
            uuid_reserva_offline=offline_uuid,
            id_sucursal=1,
            id_empresa=1,
            fecha_reserva_offline=now - timedelta(hours=1),
            fecha_atencion_programada=self.scheduled_slot,
            detalles=[
                OfflineReservationDetailRequest(
                    id_variante_producto=1,
                    cantidad=1,
                    precio_referencial=Decimal("120.00"),
                )
            ],
        )

        offline_svc = OfflineReservationService(self.db)
        # Mock de validaciones de plan SaaS y chequeo de slot horario para la prueba unitaria
        offline_svc._validate_saas = lambda *args, **kwargs: None
        offline_svc.repository.has_active_slot_conflict = lambda *args, **kwargs: False

        # Primera sincronización
        resp1 = offline_svc.sync_offline_reservation(
            client_user, sync_payload, requested_company_id=1, now=now
        )

        self.assertTrue(resp1.success)
        self.assertTrue(resp1.confirmada)
        self.assertEqual(resp1.estado_resultado, "CONFIRMADA")
        self.assertIsNotNone(resp1.id_reserva)
        first_reservation_id = resp1.id_reserva

        # Reintento idéntico (simulación de fallo de red / retry del cliente offline)
        resp2 = offline_svc.sync_offline_reservation(
            client_user, sync_payload, requested_company_id=1, now=now
        )

        self.assertTrue(resp2.success)
        self.assertTrue(resp2.confirmada)
        self.assertEqual(resp2.id_reserva, first_reservation_id)
        self.assertIn("idempotente", resp2.mensaje.lower())

        # Verificar que NO se crearon reservas duplicadas en base de datos
        total_reservations = (
            self.db.query(Reservation)
            .filter(Reservation.id_cliente == self.client.id_cliente)
            .count()
        )
        self.assertEqual(total_reservations, 1)
