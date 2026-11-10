"""Pruebas unitarias con mocks para PK08 - CU10: Registrar reserva de prendas offline en FashionStore.

Pruebas estrictamente locales sin conexión a Supabase ni mutaciones en base de datos.
Verifica:
1. CLIENTE autorizado sincroniza reserva offline e integra en t_reserva / t_detalle_reserva (PENDIENTE).
2. CAJERO (y otros roles no-CLIENTE) rechazado al crear reserva offline, conservando atención en CU18.
3. Validación de horario de atención de sucursal y bloques de 30 minutos (reglas CU17).
4. Manejo de conflicto por stock insuficiente sin dar por confirmada la reserva local.
5. Aislamiento multitenant estricto y bloqueo de manipulación de id_cliente / id_empresa / id_usuario.
6. Idempotencia estricta por UUID (reintento y colisión concurrente IntegrityError).
7. Validación de suscripción SaaS y funcionalidad OFFLINE (CU07).
"""

from datetime import datetime, time, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock

from sqlalchemy.exc import IntegrityError

from app.PK07.CU07_ConsultarPlanLimites.service import FeatureNotEnabledError
from app.PK08.CU10_RegistrarReservaOffline.schemas import (
    OfflineReservationDetailRequest,
    OfflineReservationSyncRequest,
)
from app.PK08.CU10_RegistrarReservaOffline.service import (
    OfflineReservationError,
    OfflineReservationService,
)
from app.schemas.auth import AuthenticatedUserData
from app.services.staff_reservations import StaffReservationService

NOW = datetime(2026, 11, 1, 10, 0, 0)


def dummy_company(id_empresa: int = 1, nombre: str = "Moda Oriente"):
    return SimpleNamespace(id_empresa=id_empresa, nombre=nombre, estado="ACTIVA")


def dummy_subscription(id_empresa: int = 1):
    return SimpleNamespace(
        id_suscripcion=1,
        id_empresa=id_empresa,
        id_plan_saas=2,
        estado="ACTIVA",
        fecha_fin_periodo=datetime(2027, 1, 1, 0, 0, 0),
    )


def dummy_branch(
    id_sucursal: int = 10,
    empresa_id: int = 1,
    estado: bool = True,
    hora_apertura: time | None = time(8, 0),
    hora_cierre: time | None = time(20, 0),
):
    return SimpleNamespace(
        id_sucursal=id_sucursal,
        empresa_id=empresa_id,
        nombre="Sucursal Central",
        direccion="Av. San Martín 123",
        hora_apertura=hora_apertura,
        hora_cierre=hora_cierre,
        estado=estado,
    )


def dummy_client(id_cliente: int = 7, id_usuario: int = 50, empresa_id: int = 1):
    return SimpleNamespace(
        id_cliente=id_cliente,
        empresa_id=empresa_id,
        id_usuario=id_usuario,
    )


def dummy_product(
    id_producto: int = 100,
    empresa_id: int = 1,
    precio: Decimal = Decimal("250.00"),
    estado: bool = True,
):
    return SimpleNamespace(
        id_producto=id_producto,
        empresa_id=empresa_id,
        nombre="Chaqueta Denim",
        precio=precio,
        estado=estado,
    )


def dummy_variant(
    id_variante: int = 201,
    id_producto: int = 100,
    id_talla: int = 2,
    id_color: int = 4,
    sku: str = "CHA-DEN-M",
    empresa_id: int = 1,
    estado: bool = True,
):
    return SimpleNamespace(
        id_variante_producto=id_variante,
        id_producto=id_producto,
        id_talla=id_talla,
        id_color=id_color,
        sku=sku,
        estado=estado,
        empresa_id=empresa_id,
    )


def dummy_inventory(
    id_inventario: int = 501,
    id_sucursal: int = 10,
    id_variante: int = 201,
    stock_actual: int = 20,
    stock_reservado: int = 5,
    empresa_id: int = 1,
):
    return SimpleNamespace(
        id_inventario_sucursal=id_inventario,
        id_sucursal=id_sucursal,
        id_variante_producto=id_variante,
        stock_actual=stock_actual,
        stock_reservado=stock_reservado,
        stock_minimo=2,
        empresa_id=empresa_id,
        updated_at=NOW,
    )


class TestCU10SyncOfflineReservation(TestCase):
    """Suite de 7 pruebas unitarias enfocadas con mocks para PK08 - CU10."""

    def setUp(self):
        self.mock_db = MagicMock()
        self.mock_repo = MagicMock()
        self.mock_saas = MagicMock()
        self.service = OfflineReservationService(
            self.mock_db,
            repository=self.mock_repo,
            saas_service=self.mock_saas,
        )

        self.company = dummy_company(id_empresa=1)
        self.sub = dummy_subscription(id_empresa=1)
        self.mock_saas.validate_feature_enabled.return_value = self.sub
        self.mock_repo.has_active_slot_conflict.return_value = False
        self.mock_repo.code_exists.return_value = False

        self.client_user = AuthenticatedUserData(
            id_usuario=50,
            nombre="Valeria",
            apellido="Gómez",
            correo="valeria@cliente.com",
            rol="CLIENTE",
            id_empresa=1,
        )
        self.client_profile = dummy_client(id_cliente=7, id_usuario=50, empresa_id=1)
        self.mock_repo.get_client_by_user.return_value = self.client_profile

    def test_1_authorized_client_registers_and_integrates_with_original_reservations(self):
        """Verifica que el CLIENTE autenticado sincronice su reserva offline y se integre en t_reserva como PENDIENTE para atención del CAJERO."""
        payload = OfflineReservationSyncRequest(
            uuid_reserva_offline="a1b2c3d4-e5f6-7890-abcd-112233445566",
            id_sucursal=10,
            fecha_reserva_offline=NOW - timedelta(minutes=30),
            fecha_atencion_programada=NOW + timedelta(hours=4),  # 14:00 (slot válido de 30 min dentro de 08:00-20:00)
            detalles=[
                OfflineReservationDetailRequest(
                    id_variante_producto=201,
                    id_producto=100,
                    id_talla=2,
                    id_color=4,
                    cantidad=2,
                    precio_referencial=Decimal("250.00"),
                )
            ],
            observaciones="Reserva creada por cliente desde catálogo sin conexión.",
        )

        self.mock_repo.get_sync_record.return_value = None
        self.mock_repo.get_branch.return_value = dummy_branch(id_sucursal=10, empresa_id=1)

        v201 = dummy_variant(id_variante=201, id_producto=100, id_talla=2, id_color=4)
        p100 = dummy_product(id_producto=100, precio=Decimal("250.00"))
        self.mock_repo.get_variants_with_products.return_value = {201: (v201, p100)}

        inv201 = dummy_inventory(stock_actual=10, stock_reservado=2)  # disponible = 8
        self.mock_repo.lock_inventories.return_value = {201: inv201}

        res_obj = SimpleNamespace(
            id_reserva=105,
            id_sucursal=10,
            id_cliente=7,
            codigo="RSV-20261101-ABCDEF1234",
            estado="PENDIENTE",
            id_empleado_atencion=None,
            fecha_expiracion=NOW + timedelta(hours=5),
            fecha_atencion_programada=NOW + timedelta(hours=4),
            fecha_atencion=None,
            updated_at=NOW,
        )
        self.mock_repo.create_reservation.return_value = res_obj

        sync_obj = SimpleNamespace(
            uuid_reserva_offline=payload.uuid_reserva_offline,
            id_reserva=105,
            codigo_reserva="RSV-20261101-ABCDEF1234",
            estado_sincronizacion="SINCRONIZADA",
            motivo=None,
            id_sucursal=10,
            id_cliente=7,
            id_usuario=50,
            empresa_id=1,
            created_at=NOW,
        )
        self.mock_repo.create_sync_record.return_value = sync_obj

        response = self.service.sync_offline_reservation(self.client_user, payload, now=NOW)

        self.assertTrue(response.success)
        self.assertTrue(response.confirmada)
        self.assertEqual(response.estado_sincronizacion, "SINCRONIZADA")
        self.assertEqual(response.estado_resultado, "CONFIRMADA")
        self.assertEqual(response.estado_reserva, "PENDIENTE")
        self.assertEqual(response.id_reserva, 105)
        self.assertEqual(response.id_cliente, 7)
        self.assertEqual(response.id_usuario, 50)
        self.assertEqual(response.id_empresa, 1)
        self.assertEqual(inv201.stock_reservado, 4)
        self.mock_repo.create_reservation.assert_called_once()
        _, kwargs = self.mock_repo.create_reservation.call_args
        self.assertIsNone(kwargs["employee_id"])
        self.assertEqual(kwargs["client_id"], 7)
        self.mock_db.commit.assert_called_once()

    def test_2_cashier_rejected_on_create_but_can_attend_reservation_in_original_flow(self):
        """Verifica que el CAJERO sea rechazado (403) al intentar crear/sincronizar reservas offline, pero pueda confirmar y atender la reserva del cliente en CU18."""
        cashier_user = AuthenticatedUserData(
            id_usuario=15,
            nombre="Carlos",
            apellido="Cajero",
            correo="cajero@empresa.com",
            rol="CAJERO",
            id_empresa=1,
        )
        payload = OfflineReservationSyncRequest(
            uuid_reserva_offline="uuid-intento-cajero-001",
            id_sucursal=10,
            fecha_atencion_programada=NOW + timedelta(hours=2),
            detalles=[OfflineReservationDetailRequest(id_variante_producto=201, cantidad=1)],
        )

        # 1. El CAJERO NO puede crear ni sincronizar reservas offline
        with self.assertRaises(OfflineReservationError) as ctx:
            self.service.sync_offline_reservation(cashier_user, payload, now=NOW)

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("CLIENTE", ctx.exception.message)
        self.mock_repo.create_reservation.assert_not_called()

        # 2. El CAJERO conserva su capacidad original en StaffReservationService (CU18) para confirmar y atender la reserva creada por el CLIENTE
        staff_service = StaffReservationService(self.mock_db)
        staff_service.repository = MagicMock()
        staff_service._now = MagicMock(return_value=NOW)
        staff_service.repository.get_employee_by_user.return_value = SimpleNamespace(
            id_empleado=8, id_usuario=15
        )
        staff_service.repository.list_active_branch_ids.return_value = [10]
        synced_reservation = SimpleNamespace(
            id_reserva=105,
            id_sucursal=10,
            estado="PENDIENTE",
            fecha_expiracion=NOW + timedelta(hours=3),
            fecha_atencion=None,
            id_empleado_atencion=None,
            updated_at=NOW,
        )
        staff_service.repository.get_scoped_reservation.return_value = synced_reservation
        staff_service._get_detail = MagicMock(return_value={"id_reserva": 105})

        staff_service.confirm_reservation(15, 105)
        self.assertEqual(synced_reservation.estado, "CONFIRMADA")

        staff_service.attend_reservation(15, 105)
        self.assertEqual(synced_reservation.estado, "ATENDIDA")
        self.assertEqual(synced_reservation.id_empleado_atencion, 8)

    def test_3_schedule_validation_rejects_outside_branch_hours_or_invalid_slot(self):
        """Verifica que un horario fuera de apertura/cierre de sucursal o que no sea bloque de 30 min sea rechazado."""
        # La sucursal abre de 08:00 a 20:00; el cliente solicita recogida a las 21:00
        outside_hours_payload = OfflineReservationSyncRequest(
            uuid_reserva_offline="uuid-horario-fuera-rango",
            id_sucursal=10,
            fecha_reserva_offline=NOW,
            fecha_atencion_programada=datetime(2026, 11, 1, 21, 0, 0),
            detalles=[OfflineReservationDetailRequest(id_variante_producto=201, cantidad=1)],
        )

        self.mock_repo.get_sync_record.return_value = None
        self.mock_repo.get_branch.return_value = dummy_branch(
            id_sucursal=10, hora_apertura=time(8, 0), hora_cierre=time(20, 0)
        )

        rejection_sync = SimpleNamespace(
            uuid_reserva_offline=outside_hours_payload.uuid_reserva_offline,
            id_reserva=None,
            codigo_reserva=None,
            estado_sincronizacion="RECHAZADA",
            motivo="El horario de recogida seleccionado está fuera del horario de atención de la sucursal o no corresponde a un bloque válido de 30 minutos.",
            id_sucursal=10,
            id_cliente=7,
            id_usuario=50,
            empresa_id=1,
            created_at=NOW,
        )
        self.mock_repo.create_sync_record.return_value = rejection_sync

        response = self.service.sync_offline_reservation(
            self.client_user, outside_hours_payload, now=NOW
        )

        self.assertFalse(response.success)
        self.assertFalse(response.confirmada)
        self.assertEqual(response.estado_sincronizacion, "RECHAZADA")
        self.assertEqual(response.estado_resultado, "RECHAZADA")
        self.assertIsNone(response.id_reserva)
        self.assertIn("horario de atención", response.motivo)
        self.mock_repo.lock_inventories.assert_not_called()
        self.mock_repo.create_reservation.assert_not_called()

    def test_4_insufficient_stock_returns_conflict_without_confirming(self):
        """Verifica que si el stock real en PostgreSQL es insuficiente al sincronizar, devuelva EN_CONFLICTO sin confirmar ni reservar."""
        payload = OfflineReservationSyncRequest(
            uuid_reserva_offline="uuid-conflicto-stock-789",
            id_sucursal=10,
            fecha_reserva_offline=NOW - timedelta(minutes=15),
            fecha_atencion_programada=NOW + timedelta(hours=2),
            detalles=[OfflineReservationDetailRequest(id_variante_producto=201, cantidad=5)],
        )

        self.mock_repo.get_sync_record.return_value = None
        self.mock_repo.get_branch.return_value = dummy_branch(id_sucursal=10)
        v201 = dummy_variant(id_variante=201, sku="CHA-DEN-M")
        p100 = dummy_product(id_producto=100)
        self.mock_repo.get_variants_with_products.return_value = {201: (v201, p100)}

        # Stock disponible: 10 - 8 = 2. Solicitado: 5
        inv201 = dummy_inventory(stock_actual=10, stock_reservado=8)
        self.mock_repo.lock_inventories.return_value = {201: inv201}

        conflict_sync = SimpleNamespace(
            uuid_reserva_offline=payload.uuid_reserva_offline,
            id_reserva=None,
            codigo_reserva=None,
            estado_sincronizacion="CONFLICTO",
            motivo="Stock insuficiente para la variante 'CHA-DEN-M' en la sucursal seleccionada. Disponible: 2, Solicitado: 5.",
            id_sucursal=10,
            id_cliente=7,
            id_usuario=50,
            empresa_id=1,
            created_at=NOW,
        )
        self.mock_repo.create_sync_record.return_value = conflict_sync

        response = self.service.sync_offline_reservation(self.client_user, payload, now=NOW)

        self.assertFalse(response.success)
        self.assertFalse(response.confirmada)
        self.assertEqual(response.estado_sincronizacion, "CONFLICTO")
        self.assertEqual(response.estado_resultado, "EN_CONFLICTO")
        self.assertIsNone(response.id_reserva)
        self.assertIn("Stock insuficiente", response.motivo)
        self.assertEqual(inv201.stock_reservado, 8)
        self.mock_repo.create_reservation.assert_not_called()
        self.mock_db.commit.assert_called_once()

    def test_5_strict_multitenancy_and_anti_spoofing_validation(self):
        """Verifica el aislamiento multitenant y que no se pueda manipular id_cliente, id_empresa ni id_usuario."""
        # 1. Intento de sincronizar hacia otra empresa
        payload_cross_tenant = OfflineReservationSyncRequest(
            uuid_reserva_offline="uuid-cruce-empresas-01",
            id_sucursal=10,
            fecha_atencion_programada=NOW + timedelta(hours=2),
            detalles=[OfflineReservationDetailRequest(id_variante_producto=201, cantidad=1)],
        )
        with self.assertRaises(OfflineReservationError) as ctx_tenant:
            self.service.sync_offline_reservation(
                self.client_user, payload_cross_tenant, requested_company_id=2, now=NOW
            )
        self.assertEqual(ctx_tenant.exception.status_code, 403)
        self.assertIn("otra empresa", ctx_tenant.exception.message)

        # 2. Intento de suplantar otro id_cliente en el payload (cliente real es 7, envía 999)
        payload_spoof_client = OfflineReservationSyncRequest(
            uuid_reserva_offline="uuid-spoof-cliente-02",
            id_sucursal=10,
            id_cliente=999,
            fecha_atencion_programada=NOW + timedelta(hours=2),
            detalles=[OfflineReservationDetailRequest(id_variante_producto=201, cantidad=1)],
        )
        with self.assertRaises(OfflineReservationError) as ctx_spoof:
            self.service.sync_offline_reservation(
                self.client_user, payload_spoof_client, now=NOW
            )
        self.assertEqual(ctx_spoof.exception.status_code, 403)
        self.assertIn("otro cliente", ctx_spoof.exception.message)

    def test_6_idempotency_prevents_duplicates_on_retry_and_concurrent_race(self):
        """Verifica que reintentos con el mismo UUID nunca dupliquen la reserva ni el stock reservado."""
        payload = OfflineReservationSyncRequest(
            uuid_reserva_offline="uuid-idempotente-12345",
            id_sucursal=10,
            fecha_reserva_offline=NOW - timedelta(hours=1),
            fecha_atencion_programada=NOW + timedelta(hours=3),
            detalles=[OfflineReservationDetailRequest(id_variante_producto=201, cantidad=1)],
        )

        existing_sync = SimpleNamespace(
            uuid_reserva_offline="uuid-idempotente-12345",
            id_reserva=99,
            codigo_reserva="RSV-20261101-PREV99",
            estado_sincronizacion="SINCRONIZADA",
            motivo=None,
            id_sucursal=10,
            id_cliente=7,
            id_usuario=50,
            empresa_id=1,
            created_at=NOW - timedelta(minutes=45),
        )
        self.mock_repo.get_sync_record.return_value = existing_sync

        response = self.service.sync_offline_reservation(self.client_user, payload, now=NOW)

        self.assertTrue(response.success)
        self.assertTrue(response.confirmada)
        self.assertEqual(response.estado_resultado, "CONFIRMADA")
        self.assertEqual(response.id_reserva, 99)
        self.assertIn("idempotente", response.mensaje)
        self.mock_repo.lock_inventories.assert_not_called()
        self.mock_repo.create_reservation.assert_not_called()

        # Simulación de carrera concurrente (IntegrityError en uq_reserva_offline_empresa_uuid)
        self.mock_repo.get_sync_record.side_effect = [None, existing_sync]
        self.mock_repo.get_branch.return_value = dummy_branch(id_sucursal=10)
        self.mock_repo.get_variants_with_products.return_value = {
            201: (dummy_variant(id_variante=201), dummy_product(id_producto=100))
        }
        self.mock_repo.lock_inventories.return_value = {
            201: dummy_inventory(stock_actual=10, stock_reservado=1)
        }
        self.mock_repo.create_reservation.return_value = SimpleNamespace(
            id_reserva=99, codigo="RSV-20261101-PREV99", estado="PENDIENTE"
        )
        self.mock_repo.create_sync_record.side_effect = IntegrityError(
            "duplicate key value violates unique constraint 'uq_reserva_offline_empresa_uuid'",
            params={},
            orig=Exception("duplicate key"),
        )

        race_response = self.service.sync_offline_reservation(self.client_user, payload, now=NOW)
        self.mock_db.rollback.assert_called()
        self.assertTrue(race_response.confirmada)
        self.assertEqual(race_response.id_reserva, 99)

        # Reintento de una reserva que previamente estuvo en CONFLICTO (sin id_reserva) cuando el horario ya se liberó
        conflict_sync = SimpleNamespace(
            uuid_reserva_offline="uuid-conflicto-liberado-01",
            id_reserva=None,
            codigo_reserva=None,
            estado_sincronizacion="CONFLICTO",
            motivo="Una de las prendas seleccionadas ya está reservada para esa sucursal, fecha y hora.",
            id_sucursal=10,
            id_cliente=7,
            id_usuario=50,
            empresa_id=1,
            created_at=NOW - timedelta(minutes=30),
        )
        self.mock_repo.get_sync_record.side_effect = None
        self.mock_repo.get_sync_record.return_value = conflict_sync
        self.mock_repo.has_active_slot_conflict.return_value = False
        self.mock_repo.create_sync_record.side_effect = None
        self.mock_repo.create_sync_record.return_value = conflict_sync
        self.mock_repo.create_reservation.return_value = SimpleNamespace(
            id_reserva=105, codigo="RSV-20261101-LIB105", estado="PENDIENTE"
        )

        retry_conflict_payload = OfflineReservationSyncRequest(
            uuid_reserva_offline="uuid-conflicto-liberado-01",
            id_sucursal=10,
            fecha_reserva_offline=NOW - timedelta(minutes=30),
            fecha_atencion_programada=NOW + timedelta(hours=3),
            detalles=[OfflineReservationDetailRequest(id_variante_producto=201, cantidad=1)],
        )
        re_evaluated = self.service.sync_offline_reservation(
            self.client_user, retry_conflict_payload, now=NOW
        )
        self.assertTrue(re_evaluated.confirmada)
        self.assertEqual(re_evaluated.estado_sincronizacion, "SINCRONIZADA")
        self.assertEqual(re_evaluated.id_reserva, 105)

    def test_7_saas_subscription_and_offline_feature_required(self):
        """Verifica que sin funcionalidad OFFLINE habilitada en el plan SaaS se bloquee la sincronización."""
        payload = OfflineReservationSyncRequest(
            uuid_reserva_offline="uuid-sin-saas-offline",
            id_sucursal=10,
            fecha_atencion_programada=NOW + timedelta(hours=2),
            detalles=[OfflineReservationDetailRequest(id_variante_producto=201, cantidad=1)],
        )

        self.mock_saas.validate_feature_enabled.side_effect = FeatureNotEnabledError(
            "El plan contratado no incluye la funcionalidad 'OFFLINE'."
        )

        with self.assertRaises(OfflineReservationError) as ctx:
            self.service.sync_offline_reservation(self.client_user, payload, now=NOW)

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("funcionalidad 'OFFLINE'", ctx.exception.message)
