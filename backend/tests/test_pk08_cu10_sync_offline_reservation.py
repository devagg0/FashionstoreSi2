"""Pruebas unitarias con mocks para PK08 - CU10: Registrar reserva de prendas offline en FashionStore.

Pruebas estrictamente locales sin conexión a Supabase ni mutaciones en base de datos.
Verifica:
1. Registro válido y reserva atómica de inventario.
2. Reintentos idempotentes con el mismo UUID.
3. Rechazo por stock insuficiente persistido idempotentemente.
4. Aislamiento multi-tenant estricto.
5. Permisos por sucursal para cajeros/encargados.
6. Validación de suscripción SaaS y funcionalidad OFFLINE (CU07).
7. Transacción atómica y resolución de conflicto concurrente (IntegrityError).
"""

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock

from sqlalchemy.exc import IntegrityError

from app.PK07.CU07_ConsultarPlanLimites.service import (
    FeatureNotEnabledError,
    NoActiveSubscriptionError,
)
from app.PK08.CU10_RegistrarReservaOffline.schemas import (
    OfflineReservationDetailRequest,
    OfflineReservationSyncRequest,
)
from app.PK08.CU10_RegistrarReservaOffline.service import (
    OfflineReservationError,
    OfflineReservationService,
)
from app.schemas.auth import AuthenticatedUserData

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


def dummy_branch(id_sucursal: int = 10, empresa_id: int = 1, estado: bool = True):
    return SimpleNamespace(
        id_sucursal=id_sucursal,
        empresa_id=empresa_id,
        nombre="Sucursal Central",
        direccion="Av. San Martín 123",
        estado=estado,
    )


def dummy_client(id_cliente: int = 1, empresa_id: int = 1):
    return SimpleNamespace(
        id_cliente=id_cliente,
        empresa_id=empresa_id,
        id_usuario=50,
    )


def dummy_product(id_producto: int = 100, precio: Decimal = Decimal("250.00")):
    return SimpleNamespace(
        id_producto=id_producto,
        nombre="Chaqueta Denim",
        precio=precio,
        estado=True,
    )


def dummy_variant(id_variante: int = 201, id_producto: int = 100, sku: str = "CHA-DEN-M"):
    return SimpleNamespace(
        id_variante_producto=id_variante,
        id_producto=id_producto,
        sku=sku,
        estado=True,
        empresa_id=1,
    )


def dummy_inventory(
    id_inventario: int = 501,
    id_sucursal: int = 10,
    id_variante: int = 201,
    stock_actual: int = 20,
    stock_reservado: int = 5,
):
    return SimpleNamespace(
        id_inventario_sucursal=id_inventario,
        id_sucursal=id_sucursal,
        id_variante_producto=id_variante,
        stock_actual=stock_actual,
        stock_reservado=stock_reservado,
        stock_minimo=2,
        empresa_id=1,
        updated_at=NOW,
    )


class TestCU10SyncOfflineReservation(TestCase):
    """Suite de 7 pruebas unitarias con mocks para PK08 - CU10."""

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

    def test_1_valid_offline_reservation_registration(self):
        """Verifica el registro atómico exitoso de una reserva offline con reserva de stock."""
        user = AuthenticatedUserData(
            id_usuario=10,
            nombre="Encargada",
            apellido="Tienda",
            correo="encargada@empresa.com",
            rol="ENCARGADO_SUCURSAL",
            id_empresa=1,
        )

        payload = OfflineReservationSyncRequest(
            uuid_reserva_offline="a1b2c3d4-e5f6-7890-abcd-112233445566",
            id_sucursal=10,
            id_cliente=1,
            fecha_reserva_offline=NOW - timedelta(minutes=30),
            fecha_atencion_programada=NOW + timedelta(hours=4),
            detalles=[
                OfflineReservationDetailRequest(
                    id_variante_producto=201,
                    cantidad=2,
                    precio_referencial=Decimal("250.00"),
                )
            ],
            observaciones="Reserva generada sin conexión en tablet sucursal.",
        )

        # Mocks
        self.mock_repo.get_sync_record.return_value = None
        self.mock_repo.get_branch.return_value = dummy_branch(id_sucursal=10, empresa_id=1)
        self.mock_repo.get_employee_for_user.return_value = SimpleNamespace(id_empleado=8)
        self.mock_repo.is_employee_assigned_to_branch.return_value = True
        self.mock_repo.get_client.return_value = dummy_client(id_cliente=1, empresa_id=1)

        v201 = dummy_variant(id_variante=201)
        p100 = dummy_product(id_producto=100)
        self.mock_repo.get_variants_with_products.return_value = {201: (v201, p100)}

        inv201 = dummy_inventory(stock_actual=10, stock_reservado=2)  # disponible = 8
        self.mock_repo.lock_inventories.return_value = {201: inv201}

        res_obj = SimpleNamespace(
            id_reserva=105,
            codigo="RES-OFF-1-ABCDEF12",
        )
        self.mock_repo.create_reservation.return_value = res_obj

        sync_obj = SimpleNamespace(
            uuid_reserva_offline=payload.uuid_reserva_offline,
            id_reserva=105,
            codigo_reserva="RES-OFF-1-ABCDEF12",
            estado_sincronizacion="SINCRONIZADA",
            motivo=None,
            id_sucursal=10,
            id_cliente=1,
            id_usuario=10,
            empresa_id=1,
            created_at=NOW,
        )
        self.mock_repo.create_sync_record.return_value = sync_obj

        response = self.service.sync_offline_reservation(user, payload, now=NOW)

        # Verificaciones
        self.assertTrue(response.success)
        self.assertEqual(response.estado_sincronizacion, "SINCRONIZADA")
        self.assertEqual(response.id_reserva, 105)
        self.assertEqual(response.codigo_reserva, "RES-OFF-1-ABCDEF12")
        self.assertEqual(response.uuid_reserva_offline, payload.uuid_reserva_offline)
        # El stock reservado debió incrementarse de 2 a 4
        self.assertEqual(inv201.stock_reservado, 4)
        self.mock_db.commit.assert_called_once()

    def test_2_idempotent_retransmission_returns_previous_result(self):
        """Verifica que el reenvío del mismo UUID devuelva el resultado previo sin duplicar reservas ni alterar stock."""
        user = AuthenticatedUserData(
            id_usuario=10,
            nombre="Encargada",
            apellido="Tienda",
            correo="encargada@empresa.com",
            rol="ENCARGADO_SUCURSAL",
            id_empresa=1,
        )

        payload = OfflineReservationSyncRequest(
            uuid_reserva_offline="uuid-existente-12345",
            id_sucursal=10,
            id_cliente=1,
            fecha_reserva_offline=NOW - timedelta(hours=1),
            fecha_atencion_programada=NOW + timedelta(hours=3),
            detalles=[
                OfflineReservationDetailRequest(id_variante_producto=201, cantidad=1)
            ],
        )

        existing_sync = SimpleNamespace(
            uuid_reserva_offline="uuid-existente-12345",
            id_reserva=99,
            codigo_reserva="RES-OFF-1-PREV99",
            estado_sincronizacion="SINCRONIZADA",
            motivo=None,
            id_sucursal=10,
            id_cliente=1,
            id_usuario=10,
            empresa_id=1,
            created_at=NOW - timedelta(minutes=45),
        )
        self.mock_repo.get_sync_record.return_value = existing_sync

        response = self.service.sync_offline_reservation(user, payload, now=NOW)

        self.assertTrue(response.success)
        self.assertEqual(response.estado_sincronizacion, "SINCRONIZADA")
        self.assertEqual(response.id_reserva, 99)
        self.assertIn("previamente sincronizada", response.mensaje)
        # No debe haber llamado a crear reserva ni bloquear inventario
        self.mock_repo.lock_inventories.assert_not_called()
        self.mock_repo.create_reservation.assert_not_called()

    def test_3_insufficient_stock_rejects_and_persists_idempotently(self):
        """Verifica que si no hay stock real suficiente en PostgreSQL, la reserva se rechace y se registre como RECHAZADA."""
        user = AuthenticatedUserData(
            id_usuario=10,
            nombre="Cajero",
            apellido="Turno",
            correo="cajero@empresa.com",
            rol="CAJERO",
            id_empresa=1,
        )

        payload = OfflineReservationSyncRequest(
            uuid_reserva_offline="uuid-sin-stock-789",
            id_sucursal=10,
            id_cliente=1,
            fecha_reserva_offline=NOW - timedelta(minutes=10),
            fecha_atencion_programada=NOW + timedelta(hours=2),
            detalles=[
                OfflineReservationDetailRequest(id_variante_producto=201, cantidad=5)
            ],
        )

        self.mock_repo.get_sync_record.return_value = None
        self.mock_repo.get_branch.return_value = dummy_branch(id_sucursal=10)
        self.mock_repo.get_employee_for_user.return_value = SimpleNamespace(id_empleado=2)
        self.mock_repo.is_employee_assigned_to_branch.return_value = True
        self.mock_repo.get_client.return_value = dummy_client(id_cliente=1)

        v201 = dummy_variant(id_variante=201, sku="CHA-DEN-M")
        p100 = dummy_product(id_producto=100)
        self.mock_repo.get_variants_with_products.return_value = {201: (v201, p100)}

        # Stock disponible: 10 - 8 = 2. Solicitado: 5 (insuficiente)
        inv201 = dummy_inventory(stock_actual=10, stock_reservado=8)
        self.mock_repo.lock_inventories.return_value = {201: inv201}

        rejection_sync = SimpleNamespace(
            uuid_reserva_offline=payload.uuid_reserva_offline,
            id_reserva=None,
            codigo_reserva=None,
            estado_sincronizacion="RECHAZADA",
            motivo="Stock insuficiente para la variante 'CHA-DEN-M' en la sucursal seleccionada. Disponible: 2, Solicitado: 5.",
            id_sucursal=10,
            id_cliente=1,
            id_usuario=10,
            empresa_id=1,
            created_at=NOW,
        )
        self.mock_repo.create_sync_record.return_value = rejection_sync

        response = self.service.sync_offline_reservation(user, payload, now=NOW)

        self.assertFalse(response.success)
        self.assertEqual(response.estado_sincronizacion, "RECHAZADA")
        self.assertIsNone(response.id_reserva)
        self.assertIn("Stock insuficiente", response.motivo)
        # El stock reservado NO debió incrementarse
        self.assertEqual(inv201.stock_reservado, 8)
        # No se creó registro en t_reserva
        self.mock_repo.create_reservation.assert_not_called()
        # Se persistió el registro de rechazo en t_reserva_offline_sync
        self.mock_repo.create_sync_record.assert_called_once()
        self.mock_db.commit.assert_called_once()

    def test_4_strict_multitenant_isolation(self):
        """Verifica que un usuario de la empresa 1 no pueda sincronizar reservas para la empresa 2."""
        user = AuthenticatedUserData(
            id_usuario=1,
            nombre="Admin",
            apellido="Empresa 1",
            correo="admin@emp1.com",
            rol="ADMINISTRADOR",
            id_empresa=1,
        )

        payload = OfflineReservationSyncRequest(
            uuid_reserva_offline="uuid-cruce-empresas",
            id_sucursal=10,
            id_cliente=1,
            fecha_reserva_offline=NOW,
            fecha_atencion_programada=NOW + timedelta(hours=2),
            detalles=[OfflineReservationDetailRequest(id_variante_producto=201, cantidad=1)],
        )

        with self.assertRaises(OfflineReservationError) as ctx:
            self.service.sync_offline_reservation(user, payload, requested_company_id=2)

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("no puede sincronizar reservas de otra empresa", ctx.exception.message)

    def test_5_staff_branch_permission_validation(self):
        """Verifica que un cajero no asignado a la sucursal de la reserva sea rechazado."""
        cashier = AuthenticatedUserData(
            id_usuario=15,
            nombre="Cajero",
            apellido="Sucursal 20",
            correo="cajero@empresa.com",
            rol="CAJERO",
            id_empresa=1,
        )

        payload = OfflineReservationSyncRequest(
            uuid_reserva_offline="uuid-sucursal-no-autorizada",
            id_sucursal=10,  # Intenta en sucursal 10
            id_cliente=1,
            fecha_reserva_offline=NOW,
            fecha_atencion_programada=NOW + timedelta(hours=2),
            detalles=[OfflineReservationDetailRequest(id_variante_producto=201, cantidad=1)],
        )

        self.mock_repo.get_sync_record.return_value = None
        self.mock_repo.get_branch.return_value = dummy_branch(id_sucursal=10)
        self.mock_repo.get_employee_for_user.return_value = SimpleNamespace(id_empleado=15)
        # Cajero NO está asignado a la sucursal 10
        self.mock_repo.is_employee_assigned_to_branch.return_value = False

        rejection_sync = SimpleNamespace(
            uuid_reserva_offline=payload.uuid_reserva_offline,
            id_reserva=None,
            codigo_reserva=None,
            estado_sincronizacion="RECHAZADA",
            motivo="El usuario no tiene asignación activa para operar en la sucursal de la reserva.",
            id_sucursal=10,
            id_cliente=1,
            id_usuario=15,
            empresa_id=1,
            created_at=NOW,
        )
        self.mock_repo.create_sync_record.return_value = rejection_sync

        response = self.service.sync_offline_reservation(cashier, payload, now=NOW)

        self.assertFalse(response.success)
        self.assertEqual(response.estado_sincronizacion, "RECHAZADA")
        self.assertIn("no tiene asignación activa", response.motivo)

    def test_6_saas_subscription_and_feature_offline_required(self):
        """Verifica que sin suscripción activa o sin funcionalidad OFFLINE contratada se bloquee la sincronización."""
        admin = AuthenticatedUserData(
            id_usuario=1,
            nombre="Admin",
            apellido="General",
            correo="admin@empresa.com",
            rol="ADMINISTRADOR",
            id_empresa=1,
        )

        payload = OfflineReservationSyncRequest(
            uuid_reserva_offline="uuid-sin-saas",
            id_sucursal=10,
            id_cliente=1,
            fecha_reserva_offline=NOW,
            fecha_atencion_programada=NOW + timedelta(hours=2),
            detalles=[OfflineReservationDetailRequest(id_variante_producto=201, cantidad=1)],
        )

        self.mock_saas.validate_feature_enabled.side_effect = FeatureNotEnabledError(
            "El plan contratado no incluye la funcionalidad 'OFFLINE'."
        )

        with self.assertRaises(OfflineReservationError) as ctx:
            self.service.sync_offline_reservation(admin, payload)

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("funcionalidad 'OFFLINE'", ctx.exception.message)

    def test_7_atomic_transaction_rollback_and_concurrent_integrity_error(self):
        """Verifica que ante colisión concurrente de UUID (IntegrityError), se ejecute rollback y se retorne el registro ganador."""
        user = AuthenticatedUserData(
            id_usuario=10,
            nombre="Admin",
            apellido="General",
            correo="admin@empresa.com",
            rol="ADMINISTRADOR",
            id_empresa=1,
        )

        payload = OfflineReservationSyncRequest(
            uuid_reserva_offline="uuid-carrera-concurrente",
            id_sucursal=10,
            id_cliente=1,
            fecha_reserva_offline=NOW,
            fecha_atencion_programada=NOW + timedelta(hours=2),
            detalles=[OfflineReservationDetailRequest(id_variante_producto=201, cantidad=1)],
        )

        # En la primera comprobación no existía
        self.mock_repo.get_sync_record.side_effect = [
            None,  # 1. Chequeo inicial
            SimpleNamespace(  # 2. Re-consulta tras IntegrityError
                uuid_reserva_offline=payload.uuid_reserva_offline,
                id_reserva=120,
                codigo_reserva="RES-OFF-1-WINNER",
                estado_sincronizacion="SINCRONIZADA",
                motivo=None,
                id_sucursal=10,
                id_cliente=1,
                id_usuario=99,
                empresa_id=1,
                created_at=NOW,
            ),
        ]

        self.mock_repo.get_branch.return_value = dummy_branch(id_sucursal=10)
        self.mock_repo.get_client.return_value = dummy_client(id_cliente=1)
        v201 = dummy_variant(id_variante=201)
        p100 = dummy_product(id_producto=100)
        self.mock_repo.get_variants_with_products.return_value = {201: (v201, p100)}

        inv201 = dummy_inventory(stock_actual=10, stock_reservado=1)
        self.mock_repo.lock_inventories.return_value = {201: inv201}
        self.mock_repo.create_reservation.return_value = SimpleNamespace(id_reserva=120, codigo="RES-OFF-1-WINNER")

        # Simular que al insertar sync_record la restricción de base de datos uq_reserva_offline_empresa_uuid lanza IntegrityError
        self.mock_repo.create_sync_record.side_effect = IntegrityError(
            "duplicate key value violates unique constraint 'uq_reserva_offline_empresa_uuid'",
            params={},
            orig=Exception("duplicate key"),
        )

        response = self.service.sync_offline_reservation(user, payload, now=NOW)

        # Debe haber hecho rollback para limpiar la transacción fallida
        self.mock_db.rollback.assert_called()
        # Debe haber devuelto el resultado de la transacción ganadora
        self.assertTrue(response.success)
        self.assertEqual(response.id_reserva, 120)
        self.assertEqual(response.codigo_reserva, "RES-OFF-1-WINNER")
        self.assertIn("previamente sincronizada", response.mensaje)

