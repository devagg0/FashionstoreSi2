"""Pruebas unitarias con mocks para PK08 - CU12: Consultar operaciones locales pendientes y su estado en el servidor.

Pruebas estrictamente locales sin conexión a Supabase ni mutaciones en base de datos.
Verifica:
1. Consulta de estado de reserva sincronizada en PostgreSQL por su UUID offline.
2. Consulta de estado de venta POS o compra digital sincronizada por UUID determinístico.
3. Consulta de operación que aún no ha sido sincronizada (pendiente en dispositivo local).
4. Aislamiento multitenant y control de permisos por rol (CLIENTE intentando ver operación ajena).
"""

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock
from uuid import UUID

from app.PK08.CU12_ConsultarOperacionesPendientes.service import (
    OfflineOperationError,
    OfflineOperationStatusService,
)
from app.schemas.auth import AuthenticatedUserData

NOW = datetime(2026, 11, 4, 18, 0, 0)


def dummy_user(
    id_usuario: int = 10,
    rol: str = "CLIENTE",
    id_empresa: int = 1,
    nombre: str = "Ana",
    apellido: str = "Lopez",
) -> AuthenticatedUserData:
    return AuthenticatedUserData(
        id_usuario=id_usuario,
        id_empresa=id_empresa,
        rol=rol,
        nombre=nombre,
        apellido=apellido,
        correo="ana@test.com",
    )


class TestPK08CU12QueryPendingOperations(TestCase):
    """Batería focalizada de 4 pruebas unitarias para CU12."""

    def setUp(self) -> None:
        self.mock_db = MagicMock()
        self.mock_repo = MagicMock()
        self.mock_saas = MagicMock()
        self.mock_saas.check_feature_enabled.return_value = True

        self.service = OfflineOperationStatusService(
            db=self.mock_db,
            repository=self.mock_repo,
            saas_service=self.mock_saas,
        )

    def test_1_query_synced_reservation_status(self) -> None:
        """1. Consulta de reserva sincronizada en PostgreSQL retorna estado CONFIRMADA y datos del servidor."""
        user = dummy_user(id_usuario=10, rol="CLIENTE", id_empresa=1)
        uuid_reserva = "RSV-20261104-7B44CEA067"

        # Mock de registro de sincronización
        sync_record = SimpleNamespace(
            id_sync=1,
            empresa_id=1,
            uuid_reserva_offline=uuid_reserva,
            id_reserva=55,
            codigo_reserva="RSV-20261104-7B44CEA067",
            id_sucursal=2,
            id_cliente=4,
            id_usuario=10,
            estado_sincronizacion="SINCRONIZADA",
            motivo=None,
            detalles_json=None,
            fecha_reserva_offline=NOW,
            created_at=NOW,
        )
        self.mock_repo.get_reservation_sync.return_value = sync_record

        # Mock de reserva central
        reservation = SimpleNamespace(
            id_reserva=55,
            empresa_id=1,
            codigo_reserva="RSV-20261104-7B44CEA067",
            id_sucursal=2,
            id_cliente=4,
            estado="PENDIENTE",
            total_referencial=Decimal("350.00"),
        )
        self.mock_repo.get_reservation.return_value = reservation

        # Mock de sucursal
        self.mock_repo.get_branch.return_value = SimpleNamespace(
            id_sucursal=2, nombre="Sucursal Norte"
        )
        self.mock_repo.get_reservation_details.return_value = []

        resp = self.service.get_operation_status(user, uuid_reserva)

        self.assertTrue(resp.success)
        self.assertEqual(resp.data.uuid_operacion, uuid_reserva)
        self.assertEqual(resp.data.tipo_operacion, "RESERVA")
        self.assertEqual(resp.data.estado_sincronizacion, "SINCRONIZADA")
        self.assertTrue(resp.data.confirmada)
        self.assertEqual(resp.data.id_servidor, 55)
        self.assertEqual(resp.data.codigo_servidor, "RSV-20261104-7B44CEA067")
        self.assertEqual(resp.data.sucursal_nombre, "Sucursal Norte")
        self.assertEqual(resp.data.monto_total, Decimal("350.00"))

    def test_2_query_synced_sale_status(self) -> None:
        """2. Consulta de venta presencial o compra digital sincronizada por UUID retorna VENTA confirmada."""
        user = dummy_user(id_usuario=20, rol="CAJERO", id_empresa=1)
        uuid_venta = "550e8400-e29b-41d4-a716-446655440000"

        # No es reserva
        self.mock_repo.get_reservation_sync.return_value = None

        # Mock de pago idempotente y venta
        uuid_obj = UUID(uuid_venta)
        mock_payment = SimpleNamespace(
            id_pago=99,
            empresa_id=1,
            id_venta=101,
            monto=Decimal("500.00"),
            medio_pago="EFECTIVO",
            clave_idempotencia=uuid_obj,
            estado="APROBADO",
        )
        self.mock_repo.get_payment_by_key.return_value = mock_payment

        mock_sale = SimpleNamespace(
            id_venta=101,
            empresa_id=1,
            id_sucursal=1,
            id_usuario=20,
            id_cliente=None,
            id_empleado=8,
            numero_venta=f"VTA-{uuid_obj.hex.upper()}",
            total=Decimal("500.00"),
            estado="COMPLETADA",
            canal="PRESENCIAL",
            created_at=NOW,
        )
        self.mock_repo.get_sale.return_value = mock_sale
        self.mock_repo.get_branch.return_value = SimpleNamespace(
            id_sucursal=1, nombre="Sucursal Central"
        )
        self.mock_repo.get_sale_details.return_value = []

        resp = self.service.get_operation_status(user, uuid_venta)

        self.assertTrue(resp.success)
        self.assertEqual(resp.data.tipo_operacion, "VENTA")
        self.assertEqual(resp.data.estado_sincronizacion, "SINCRONIZADA")
        self.assertTrue(resp.data.confirmada)
        self.assertEqual(resp.data.id_servidor, 101)
        self.assertEqual(resp.data.codigo_servidor, f"VTA-{uuid_obj.hex.upper()}")
        self.assertEqual(resp.data.medio_pago, "EFECTIVO")
        self.assertEqual(resp.data.monto_total, Decimal("500.00"))

    def test_3_query_non_synced_operation_status(self) -> None:
        """3. Operación aún no sincronizada en servidor retorna PENDIENTE_SINCRONIZACION sin fallar."""
        user = dummy_user(id_usuario=10, rol="CLIENTE", id_empresa=1)
        uuid_offline = "local-pending-uuid-999"

        # Ningún registro encontrado en PostgreSQL
        self.mock_repo.get_reservation_sync.return_value = None
        self.mock_repo.get_payment_by_key.return_value = None
        self.mock_repo.get_sale_by_number.return_value = None
        self.mock_repo.get_branch.return_value = SimpleNamespace(
            id_sucursal=1, nombre="Sucursal Central"
        )

        resp = self.service.get_operation_status(user, uuid_offline)

        self.assertTrue(resp.success)
        self.assertEqual(resp.data.uuid_operacion, uuid_offline)
        self.assertFalse(resp.data.confirmada)
        self.assertEqual(
            resp.data.estado_sincronizacion, "PENDIENTE_SINCRONIZACION"
        )
        self.assertIsNone(resp.data.id_servidor)
        self.assertIsNone(resp.data.codigo_servidor)

    def test_4_multitenant_and_actor_authorization(self) -> None:
        """4. CLIENTE no puede consultar operaciones de sincronización de otro cliente (403 Forbidden)."""
        cliente_a = dummy_user(id_usuario=10, rol="CLIENTE", id_empresa=1)
        uuid_reserva_otro = "reserva-otro-cliente-uuid"

        # La reserva pertenece al usuario 99 (otro cliente)
        sync_otro = SimpleNamespace(
            id_sync=2,
            empresa_id=1,
            uuid_reserva_offline=uuid_reserva_otro,
            id_reserva=60,
            codigo_reserva="RSV-OTRO-001",
            id_sucursal=1,
            id_cliente=9,
            id_usuario=99,  # Usuario distinto
            estado_sincronizacion="SINCRONIZADA",
            motivo=None,
            detalles_json=None,
            fecha_reserva_offline=NOW,
            created_at=NOW,
        )
        self.mock_repo.get_reservation_sync.return_value = sync_otro

        with self.assertRaises(OfflineOperationError) as ctx:
            self.service.get_operation_status(cliente_a, uuid_reserva_otro)

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("pertenece a otro cliente", ctx.exception.message)

