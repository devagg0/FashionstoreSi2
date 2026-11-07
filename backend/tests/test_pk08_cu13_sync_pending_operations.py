"""Pruebas unitarias con mocks para PK08 - CU13: Sincronizar operaciones pendientes de FashionStore.

Batería focalizada de 4 pruebas unitarias sin conexión a Supabase ni mutaciones reales en BD:
1. Sincronización de reserva offline del CLIENTE (vinculación de código local/UUID -> ID y código oficial de PostgreSQL).
2. Secuencia CONFIRM -> ATTEND -> VENTA por reserva del CAJERO vinculando código/UUID local (e ID sintético local) con ID oficial, más venta directa independiente.
3. Compra digital del CLIENTE y venta directa POS del CAJERO verificando las reglas de pago (EFECTIVO vs QR/TARJETA simulado pendiente de validación externa).
4. Idempotencia persistente por UUID, aislamiento por rol/tenant y manejo de conflictos/errores individuales sin bloquear el resto del lote.
"""

from datetime import datetime, time
from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock

from sqlalchemy.exc import OperationalError

from app.PK08.CU10_RegistrarReservaOffline.service import OfflineReservationService
from app.PK08.CU11_RegistrarVentaOffline.service import OfflineSaleService
from app.PK08.CU13_SincronizarOperacionesPendientes.schemas import (
    OfflineQueueSyncRequest,
    OfflineSyncOperationInput,
)
from app.PK08.CU13_SincronizarOperacionesPendientes.service import (
    OfflineQueueSyncError,
    OfflineQueueSyncService,
)
from app.schemas.auth import AuthenticatedUserData

NOW = datetime(2026, 11, 5, 11, 0, 0)
SCHEDULED_AT = datetime(2026, 11, 6, 15, 0, 0)


def make_user(
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
        correo=f"user{id_usuario}@fashionstore.bo",
    )


class TestPK08CU13SyncPendingOperations(TestCase):
    """4 pruebas unitarias focalizadas para PK08 - CU13."""

    def setUp(self) -> None:
        self.mock_db = MagicMock()
        self.mock_cu13_repo = MagicMock()
        self.mock_cu10_repo = MagicMock()
        self.mock_cu11_repo = MagicMock()
        self.mock_saas = MagicMock()
        self.mock_saas.validate_feature_enabled.return_value = True
        self.mock_saas.check_feature_enabled.return_value = True

        self.mock_cu13_repo.get_branch_name.return_value = "Sucursal Central"
        self.mock_cu13_repo.resolve_reservation_reference.return_value = None

        self.reservation_service = OfflineReservationService(
            db=self.mock_db,
            repository=self.mock_cu10_repo,
            saas_service=self.mock_saas,
        )
        self.sale_service = OfflineSaleService(
            db=self.mock_db,
            repository=self.mock_cu11_repo,
            saas_service=self.mock_saas,
        )
        self.sync_service = OfflineQueueSyncService(
            db=self.mock_db,
            repository=self.mock_cu13_repo,
            reservation_service=self.reservation_service,
            sale_service=self.sale_service,
            saas_service=self.mock_saas,
        )

    def test_1_sync_client_offline_reservation(self) -> None:
        """1. Sincronización de reserva offline del CLIENTE vinculando UUID/código local con ID y código oficial de PostgreSQL."""
        client_user = make_user(id_usuario=10, rol="CLIENTE", id_empresa=1)

        self.mock_cu10_repo.get_client_by_user.return_value = SimpleNamespace(
            id_cliente=4, id_usuario=10, empresa_id=1
        )
        self.mock_cu10_repo.get_sync_record.return_value = None
        self.mock_cu10_repo.get_branch.return_value = SimpleNamespace(
            id_sucursal=2,
            empresa_id=1,
            nombre="Sucursal Central",
            estado=True,
            hora_apertura=time(9, 0),
            hora_cierre=time(20, 0),
        )
        variant_obj = SimpleNamespace(
            id_variante_producto=101,
            id_producto=50,
            id_talla=1,
            id_color=2,
            sku="CAM-AZ-M",
            estado=True,
            empresa_id=1,
        )
        product_obj = SimpleNamespace(
            id_producto=50,
            nombre="Camisa Oxford",
            precio=Decimal("180.00"),
            precio_final=Decimal("180.00"),
            estado=True,
            empresa_id=1,
        )
        self.mock_cu10_repo.get_variants_with_products.return_value = {
            101: (variant_obj, product_obj)
        }
        self.mock_cu10_repo.has_active_slot_conflict.return_value = False
        inv_obj = SimpleNamespace(
            id_variante_producto=101,
            id_sucursal=2,
            empresa_id=1,
            stock_actual=10,
            stock_reservado=1,
            updated_at=NOW,
        )
        self.mock_cu10_repo.lock_inventories.return_value = {101: inv_obj}
        self.mock_cu10_repo.create_reservation.return_value = SimpleNamespace(
            id_reserva=77,
            codigo="RSV-20261105-OFICIAL77",
            estado="PENDIENTE",
            id_sucursal=2,
            id_cliente=4,
            empresa_id=1,
        )
        self.mock_cu10_repo.create_sync_record.side_effect = lambda **kw: SimpleNamespace(
            uuid_reserva_offline=kw["uuid_offline"],
            id_reserva=kw["reservation_id"],
            codigo_reserva=kw["reservation_code"],
            id_sucursal=kw["branch_id"],
            id_cliente=kw["client_id"],
            id_usuario=kw["user_id"],
            empresa_id=kw["company_id"],
            estado_sincronizacion=kw["status"],
            motivo=kw["reason"],
            created_at=kw["now"],
            updated_at=kw["now"],
        )

        # Enviar formato compatible con la cola de Angular IndexedDB (datos_originales)
        request = OfflineQueueSyncRequest(
            operaciones=[
                OfflineSyncOperationInput(
                    id_operacion="op-res-uuid-001",
                    tipo_operacion="RESERVA",
                    uuid_entidad="uuid-reserva-local-001",
                    codigo_local="RSV-LOCAL-PROV-001",
                    secuencia=1,
                    datos_originales={
                        "uuid_reserva_offline": "uuid-reserva-local-001",
                        "id_sucursal": 2,
                        "fecha_atencion_programada": SCHEDULED_AT.isoformat(),
                        "fecha_reserva_offline": NOW.isoformat(),
                        "detalles": [
                            {
                                "id_variante_producto": 101,
                                "id_producto": 50,
                                "id_talla": 1,
                                "id_color": 2,
                                "cantidad": 2,
                                "precio_referencial": "180.00",
                            }
                        ],
                    },
                )
            ]
        )

        response = self.sync_service.sync_pending_operations(
            client_user, request, now=NOW
        )

        self.assertTrue(response.success)
        self.assertEqual(response.total_operaciones, 1)
        self.assertEqual(response.confirmadas, 1)
        self.assertEqual(inv_obj.stock_reservado, 3)  # 1 inicial + 2 reservados

        res_item = response.resultados_por_uuid["op-res-uuid-001"]
        self.assertTrue(res_item.confirmada)
        self.assertEqual(res_item.estado_resultado, "CONFIRMADA")
        self.assertEqual(res_item.estado_sincronizacion, "SINCRONIZADA")
        self.assertEqual(res_item.id_servidor, 77)
        self.assertEqual(res_item.codigo_servidor, "RSV-20261105-OFICIAL77")
        self.assertEqual(res_item.estado_entidad_servidor, "PENDIENTE")
        self.assertIsNotNone(res_item.resumen_cu12)
        self.assertEqual(res_item.resumen_cu12.codigo_servidor, "RSV-20261105-OFICIAL77")

        # Verificar vinculación de UUID y código provisional local -> ID y código oficial de PostgreSQL
        self.assertEqual(
            response.vinculaciones_codigos["RSV-LOCAL-PROV-001"].id_servidor, 77
        )
        self.assertEqual(
            response.vinculaciones_codigos["uuid-reserva-local-001"].codigo_servidor,
            "RSV-20261105-OFICIAL77",
        )

        # Verificar que un fallo transitorio retorna REINTENTABLE / PENDIENTE_SINCRONIZACION (nunca RECHAZADA)
        self.mock_cu10_repo.get_sync_record.side_effect = OperationalError(
            "SELECT 1", {}, Exception("connection reset")
        )
        retryable_resp = self.sync_service.sync_pending_operations(
            client_user, request, now=NOW
        )
        retry_item = retryable_resp.resultados_por_uuid["op-res-uuid-001"]
        self.assertEqual(retry_item.estado_resultado, "REINTENTABLE")
        self.assertEqual(retry_item.estado_sincronizacion, "PENDIENTE_SINCRONIZACION")
        self.assertNotEqual(retry_item.estado_resultado, "RECHAZADA")
        self.assertTrue(retry_item.reintentable)

        # Verificar reintento idempotente: no vuelve a descontar stock ni duplica la reserva
        self.mock_cu10_repo.get_sync_record.side_effect = None
        self.mock_cu10_repo.get_sync_record.return_value = SimpleNamespace(
            uuid_reserva_offline="uuid-reserva-local-001",
            id_reserva=77,
            id_cliente=4,
            id_sucursal=2,
            id_usuario=10,
            empresa_id=1,
            codigo_reserva="RSV-20261105-OFICIAL77",
            estado_sincronizacion="SINCRONIZADA",
            motivo=None,
            created_at=NOW,
            updated_at=NOW,
        )
        idemp_resp = self.sync_service.sync_pending_operations(
            client_user, request, now=NOW
        )
        self.assertTrue(idemp_resp.resultados_por_uuid["op-res-uuid-001"].confirmada)
        self.assertEqual(inv_obj.stock_reservado, 3)  # Sin doble reserva de stock

    def test_2_sequence_confirm_attend_reservation_sale_and_independent_direct_sale(
        self,
    ) -> None:
        """2. Secuencia CONFIRM -> ATTEND -> VENTA por reserva vinculando código/UUID local con ID oficial, más venta directa independiente."""
        cashier_user = make_user(id_usuario=25, rol="CAJERO", id_empresa=1)

        # Configurar empleado y sucursal autorizada
        self.mock_cu11_repo.get_employee_by_user.return_value = SimpleNamespace(
            id_empleado=8, id_usuario=25, empresa_id=1
        )
        self.mock_cu11_repo.get_employee_active_branch_ids.return_value = [2]
        self.mock_cu11_repo.get_employee_branch_assignment.return_value = SimpleNamespace(
            id_empleado_sucursal=12, id_empleado=8, id_sucursal=2, estado=True
        )
        self.mock_cu11_repo.get_branch.return_value = SimpleNamespace(
            id_sucursal=2, empresa_id=1, nombre="Sucursal Central", estado=True
        )
        self.mock_cu11_repo.get_payment_by_key.return_value = None
        self.mock_cu11_repo.get_sale_by_number.return_value = None
        self.mock_cu11_repo.get_sale_for_reservation.return_value = None

        # Reserva previamente sincronizada en PostgreSQL con ID oficial 55, pero referenciada desde Angular
        # mediante su UUID offline "uuid-res-offline-55" e ID hash sintético local 74500123
        official_reservation = SimpleNamespace(
            id_reserva=55,
            codigo="RSV-20261105-OFICIAL55",
            empresa_id=1,
            id_sucursal=2,
            id_cliente=4,
            estado="PENDIENTE",
            fecha_expiracion=datetime(2026, 11, 6, 18, 0, 0),
            id_empleado_atencion=None,
        )
        self.mock_cu13_repo.resolve_reservation_reference.return_value = (
            55,
            "RSV-20261105-OFICIAL55",
        )
        self.mock_cu11_repo.get_reservation.return_value = official_reservation
        self.mock_cu11_repo.get_reservation_details.return_value = [
            SimpleNamespace(
                id_variante_producto=101,
                cantidad=2,
                precio_unitario=Decimal("150.00"),
            )
        ]

        variant_101 = SimpleNamespace(
            id_variante_producto=101,
            id_producto=50,
            sku="VEST-ROJ-S",
            estado=True,
            empresa_id=1,
        )
        product_50 = SimpleNamespace(
            id_producto=50,
            nombre="Vestido Rojo",
            precio_base=Decimal("150.00"),
            precio=Decimal("150.00"),
            precio_final=Decimal("150.00"),
            estado=True,
            empresa_id=1,
        )
        self.mock_cu11_repo.get_variants_with_products.return_value = {
            101: (variant_101, product_50)
        }
        self.mock_cu11_repo.get_active_promotions_for_products.return_value = {}

        inv_101 = SimpleNamespace(
            id_variante_producto=101,
            id_sucursal=2,
            empresa_id=1,
            stock_actual=10,
            stock_reservado=2,
            updated_at=NOW,
        )
        self.mock_cu11_repo.lock_inventories.return_value = {101: inv_101}

        created_sales: list[SimpleNamespace] = []

        def fake_create_sale(**kwargs):
            sale_obj = SimpleNamespace(
                id_venta=900 + len(created_sales) + 1,
                numero_venta=kwargs["sale_number"],
                estado=kwargs["estado"],
                canal=kwargs["canal"],
                id_sucursal=kwargs["branch_id"],
                id_cliente=kwargs["client_id"],
                id_empleado=kwargs["employee_id"],
                id_reserva=kwargs["reservation_id"],
                subtotal=kwargs["subtotal"],
                descuento_total=kwargs["descuento_total"],
                total=kwargs["total"],
                empresa_id=kwargs["company_id"],
            )
            created_sales.append(sale_obj)
            return sale_obj

        def fake_create_payment(**kwargs):
            return SimpleNamespace(
                id_pago=800 + len(created_sales),
                id_venta=kwargs["sale_id"],
                medio=kwargs["medio"],
                estado=kwargs["estado"],
                monto=kwargs["monto"],
            )

        self.mock_cu11_repo.create_sale.side_effect = fake_create_sale
        self.mock_cu11_repo.create_payment.side_effect = fake_create_payment

        # Lote con 4 operaciones: CONFIRM -> ATTEND -> VENTA por reserva (parcial: compra 1 de 2 reservadas) -> VENTA directa independiente
        batch_request = OfflineQueueSyncRequest(
            operaciones=[
                OfflineSyncOperationInput(
                    uuid_operacion="op-trans-confirm-1",
                    tipo_operacion="TRANSICION_RESERVA",
                    secuencia=1,
                    datos_originales={
                        "uuid_operacion_offline": "op-trans-confirm-1",
                        "id_reserva": 74500123,  # ID sintético local de Angular
                        "uuid_reserva_offline": "uuid-res-offline-55",
                        "codigo_reserva": "RSV-LOCAL-55",
                        "accion": "CONFIRM",
                        "id_sucursal": 2,
                    },
                ),
                OfflineSyncOperationInput(
                    uuid_operacion="op-trans-attend-2",
                    tipo_operacion="TRANSICION_RESERVA",
                    secuencia=2,
                    depende_de_uuid="op-trans-confirm-1",
                    datos_originales={
                        "uuid_operacion_offline": "op-trans-attend-2",
                        "id_reserva": 74500123,
                        "uuid_reserva_offline": "uuid-res-offline-55",
                        "codigo_reserva": "RSV-LOCAL-55",
                        "accion": "ATTEND",
                        "id_sucursal": 2,
                    },
                ),
                OfflineSyncOperationInput(
                    uuid_operacion="550e8400-e29b-41d4-a716-446655440001",
                    tipo_operacion="VENTA",
                    codigo_local="POS-LOC-001",
                    secuencia=3,
                    depende_de_uuid="op-trans-attend-2",
                    datos_originales={
                        "uuid_venta_offline": "550e8400-e29b-41d4-a716-446655440001",
                        "canal": "PRESENCIAL",
                        "id_sucursal": 2,
                        "id_reserva": 74500123,
                        "uuid_reserva_offline": "uuid-res-offline-55",
                        "codigo_reserva": "RSV-LOCAL-55",
                        "medio_pago": "EFECTIVO",
                        "pago_simulado": False,
                        "total": "150.00",
                        "detalles": [
                            {
                                "id_variante_producto": 101,
                                "id_producto": 50,
                                "cantidad": 1,
                                "precio_unitario": "150.00",
                            }
                        ],
                    },
                ),
                OfflineSyncOperationInput(
                    uuid_operacion="550e8400-e29b-41d4-a716-446655440002",
                    tipo_operacion="VENTA",
                    codigo_local="POS-DIRECTA-002",
                    secuencia=4,
                    datos_originales={
                        "uuid_venta_offline": "550e8400-e29b-41d4-a716-446655440002",
                        "canal": "PRESENCIAL",
                        "id_sucursal": 2,
                        "medio_pago": "EFECTIVO",
                        "pago_simulado": False,
                        "total": "300.00",
                        "detalles": [
                            {
                                "id_variante_producto": 101,
                                "id_producto": 50,
                                "cantidad": 2,
                                "precio_unitario": "150.00",
                            }
                        ],
                    },
                ),
            ]
        )

        resp = self.sync_service.sync_pending_operations(
            cashier_user, batch_request, now=NOW
        )

        self.assertTrue(resp.success)
        self.assertEqual(resp.confirmadas, 4)

        # 1. Reserva pasó por CONFIRMADA y quedó ATENDIDA
        self.assertEqual(official_reservation.estado, "ATENDIDA")
        self.assertEqual(official_reservation.id_empleado_atencion, 8)

        # 2. Venta por reserva quedó vinculada al id_reserva oficial 55 y liberó 1 prenda no comprada
        res_sale = resp.resultados_por_uuid["550e8400-e29b-41d4-a716-446655440001"]
        self.assertTrue(res_sale.confirmada)
        self.assertEqual(res_sale.id_reserva_asociada, 55)
        self.assertEqual(res_sale.codigo_reserva_asociada, "RSV-20261105-OFICIAL55")
        self.assertEqual(res_sale.estado_entidad_servidor, "COMPLETADA")
        self.assertEqual(res_sale.estado_pago, "APROBADO")
        self.assertEqual(len(res_sale.liberaciones_reserva), 1)
        self.assertEqual(res_sale.liberaciones_reserva[0].cantidad_liberada, 1)

        # 3. Venta directa independiente en el mismo lote también fue confirmada
        direct_sale = resp.resultados_por_uuid["550e8400-e29b-41d4-a716-446655440002"]
        self.assertTrue(direct_sale.confirmada)
        self.assertIsNone(direct_sale.id_reserva_asociada)
        self.assertEqual(direct_sale.id_servidor, 902)
        self.assertEqual(
            resp.vinculaciones_codigos["POS-DIRECTA-002"].id_servidor, 902
        )

        # Inventario final: 10 inicial - 1 (venta reserva) - 2 (venta directa) = 7; reservado: 2 - 1 (liberada) - 1 (vendida) = 0
        self.assertEqual(inv_101.stock_actual, 7)
        self.assertEqual(inv_101.stock_reservado, 0)

    def test_3_payment_rules_digital_purchase_vs_pos_cash_and_simulated_qr_card(
        self,
    ) -> None:
        """3. Compra digital y venta directa respetando reglas de pago: EFECTIVO completado vs QR/TARJETA simulado pendiente de validación."""
        variant_202 = SimpleNamespace(
            id_variante_producto=202,
            id_producto=60,
            sku="CHAQ-NEG-L",
            estado=True,
            empresa_id=1,
        )
        product_60 = SimpleNamespace(
            id_producto=60,
            nombre="Chaqueta Cuero",
            precio_base=Decimal("400.00"),
            precio=Decimal("400.00"),
            precio_final=Decimal("400.00"),
            estado=True,
            empresa_id=1,
        )
        self.mock_cu11_repo.get_variants_with_products.return_value = {
            202: (variant_202, product_60)
        }
        self.mock_cu11_repo.get_active_promotions_for_products.return_value = {}
        self.mock_cu11_repo.get_branch.return_value = SimpleNamespace(
            id_sucursal=2, empresa_id=1, nombre="Sucursal Central", estado=True
        )
        self.mock_cu11_repo.get_payment_by_key.return_value = None
        self.mock_cu11_repo.get_sale_by_number.return_value = None

        inv_202 = SimpleNamespace(
            id_variante_producto=202,
            id_sucursal=2,
            empresa_id=1,
            stock_actual=8,
            stock_reservado=0,
            updated_at=NOW,
        )
        self.mock_cu11_repo.lock_inventories.return_value = {202: inv_202}
        self.mock_cu11_repo.create_sale.side_effect = lambda **kw: SimpleNamespace(
            id_venta=301,
            numero_venta=kw["sale_number"],
            estado=kw["estado"],
            canal=kw["canal"],
            id_sucursal=kw["branch_id"],
            id_cliente=kw["client_id"],
            id_empleado=kw["employee_id"],
            id_reserva=kw["reservation_id"],
            subtotal=kw["subtotal"],
            descuento_total=kw["descuento_total"],
            total=kw["total"],
            empresa_id=kw["company_id"],
        )
        self.mock_cu11_repo.create_payment.side_effect = lambda **kw: SimpleNamespace(
            id_pago=401,
            id_venta=kw["sale_id"],
            medio=kw["medio"],
            estado=kw["estado"],
            monto=kw["monto"],
        )

        # A) CLIENTE sincroniza COMPRA digital con TARJETA simulada offline
        client_user = make_user(id_usuario=10, rol="CLIENTE", id_empresa=1)
        self.mock_cu11_repo.get_client_by_user.return_value = SimpleNamespace(
            id_cliente=4, id_usuario=10, empresa_id=1
        )

        digital_req = OfflineQueueSyncRequest(
            operaciones=[
                OfflineSyncOperationInput(
                    uuid_operacion="660e8400-e29b-41d4-a716-446655440010",
                    tipo_operacion="COMPRA",
                    codigo_local="DIG-LOC-010",
                    datos_originales={
                        "uuid_venta_offline": "660e8400-e29b-41d4-a716-446655440010",
                        "canal": "DIGITAL",
                        "id_sucursal": 2,
                        "medio_pago": "TARJETA",
                        "pago_simulado": True,
                        "total": "400.00",
                        "detalles": [
                            {
                                "id_variante_producto": 202,
                                "id_producto": 60,
                                "cantidad": 1,
                                "precio_unitario": "400.00",
                            }
                        ],
                    },
                )
            ]
        )

        digital_resp = self.sync_service.sync_pending_operations(
            client_user, digital_req, now=NOW
        )
        dig_res = digital_resp.resultados_por_uuid[
            "660e8400-e29b-41d4-a716-446655440010"
        ]
        self.assertTrue(dig_res.confirmada)
        self.assertEqual(dig_res.estado_entidad_servidor, "PENDIENTE")
        self.assertEqual(dig_res.estado_pago, "PENDIENTE")
        self.assertTrue(dig_res.pago_simulado)
        self.assertTrue(dig_res.pendiente_validacion_externa)
        # Stock reservado temporalmente sin descontar stock_actual definitivo hasta validación bancaria
        self.assertEqual(inv_202.stock_actual, 8)
        self.assertEqual(inv_202.stock_reservado, 1)

        # B) CAJERO sincroniza VENTA presencial con QR simulado vs VENTA presencial en EFECTIVO
        cashier_user = make_user(id_usuario=25, rol="CAJERO", id_empresa=1)
        self.mock_cu11_repo.get_employee_by_user.return_value = SimpleNamespace(
            id_empleado=8, id_usuario=25, empresa_id=1
        )
        self.mock_cu11_repo.get_employee_active_branch_ids.return_value = [2]
        self.mock_cu11_repo.get_employee_branch_assignment.return_value = SimpleNamespace(
            id_empleado_sucursal=12, id_empleado=8, id_sucursal=2, estado=True
        )

        pos_req = OfflineQueueSyncRequest(
            operaciones=[
                OfflineSyncOperationInput(
                    uuid_operacion="660e8400-e29b-41d4-a716-446655440011",
                    tipo_operacion="VENTA",
                    datos_originales={
                        "uuid_venta_offline": "660e8400-e29b-41d4-a716-446655440011",
                        "canal": "PRESENCIAL",
                        "id_sucursal": 2,
                        "medio_pago": "QR",
                        "pago_simulado": True,
                        "total": "400.00",
                        "detalles": [
                            {
                                "id_variante_producto": 202,
                                "id_producto": 60,
                                "cantidad": 1,
                                "precio_unitario": "400.00",
                            }
                        ],
                    },
                ),
                OfflineSyncOperationInput(
                    uuid_operacion="660e8400-e29b-41d4-a716-446655440012",
                    tipo_operacion="VENTA",
                    datos_originales={
                        "uuid_venta_offline": "660e8400-e29b-41d4-a716-446655440012",
                        "canal": "PRESENCIAL",
                        "id_sucursal": 2,
                        "medio_pago": "EFECTIVO",
                        "pago_simulado": False,
                        "total": "400.00",
                        "detalles": [
                            {
                                "id_variante_producto": 202,
                                "id_producto": 60,
                                "cantidad": 1,
                                "precio_unitario": "400.00",
                            }
                        ],
                    },
                ),
            ]
        )

        pos_resp = self.sync_service.sync_pending_operations(
            cashier_user, pos_req, now=NOW
        )
        qr_res = pos_resp.resultados_por_uuid["660e8400-e29b-41d4-a716-446655440011"]
        cash_res = pos_resp.resultados_por_uuid["660e8400-e29b-41d4-a716-446655440012"]

        # QR en POS offline es simulado -> venta PENDIENTE y pago PENDIENTE de validación externa
        self.assertTrue(qr_res.confirmada)
        self.assertEqual(qr_res.estado_entidad_servidor, "PENDIENTE")
        self.assertEqual(qr_res.estado_pago, "PENDIENTE")
        self.assertTrue(qr_res.pago_simulado)
        self.assertTrue(qr_res.pendiente_validacion_externa)

        # EFECTIVO en POS offline es cobro físico real -> venta COMPLETADA y pago APROBADO
        self.assertTrue(cash_res.confirmada)
        self.assertEqual(cash_res.estado_entidad_servidor, "COMPLETADA")
        self.assertEqual(cash_res.estado_pago, "APROBADO")
        self.assertFalse(cash_res.pago_simulado)
        self.assertFalse(cash_res.pendiente_validacion_externa)

    def test_4_idempotency_security_and_non_blocking_batch_conflicts(self) -> None:
        """4. Idempotencia por UUID en reintentos, seguridad por rol/tenant y conflictos individuales sin bloquear el lote."""
        client_user = make_user(id_usuario=10, rol="CLIENTE", id_empresa=1)

        # 4.1 Aislamiento multitenant: rechazar si empresa_id solicitada no coincide con el JWT
        with self.assertRaises(OfflineQueueSyncError) as ctx:
            self.sync_service.sync_pending_operations(
                client_user,
                OfflineQueueSyncRequest(
                    operaciones=[
                        OfflineSyncOperationInput(
                            uuid_operacion="op-uuid-001",
                            tipo_operacion="RESERVA",
                            datos_originales={
                                "uuid_reserva_offline": "op-uuid-001",
                                "id_sucursal": 2,
                                "fecha_atencion_programada": SCHEDULED_AT.isoformat(),
                                "detalles": [
                                    {"id_variante_producto": 101, "cantidad": 1}
                                ],
                            },
                        )
                    ]
                ),
                requested_company_id=999,
                now=NOW,
            )
        self.assertEqual(ctx.exception.status_code, 403)

        # 4.2 Lote mixto en sesión de CAJERO:
        # - Op 1: RESERVA enviada por CAJERO -> RECHAZADA por rol (sin abortar el lote)
        # - Op 2: VENTA con fallo transitorio OperationalError -> REINTENTABLE (rollback limpio)
        # - Op 3: VENTA con stock insuficiente -> EN_CONFLICTO (con detalle STOCK_INSUFICIENTE)
        # - Op 4: VENTA previamente sincronizada (reintento con mismo UUID) -> CONFIRMADA idempotente sin doble cobro ni descuento
        cashier_user = make_user(id_usuario=25, rol="CAJERO", id_empresa=1)
        self.mock_cu11_repo.get_employee_by_user.return_value = SimpleNamespace(
            id_empleado=8, id_usuario=25, empresa_id=1
        )
        self.mock_cu11_repo.get_employee_active_branch_ids.return_value = [2]
        self.mock_cu11_repo.get_employee_branch_assignment.return_value = SimpleNamespace(
            id_empleado_sucursal=12, id_empleado=8, id_sucursal=2, estado=True
        )
        self.mock_cu11_repo.get_branch.return_value = SimpleNamespace(
            id_sucursal=2, empresa_id=1, nombre="Sucursal Central", estado=True
        )

        variant_101 = SimpleNamespace(
            id_variante_producto=101,
            id_producto=50,
            sku="PANT-NEG-32",
            estado=True,
            empresa_id=1,
        )
        product_50 = SimpleNamespace(
            id_producto=50,
            nombre="Pantalon Vestir",
            precio_base=Decimal("200.00"),
            precio=Decimal("200.00"),
            precio_final=Decimal("200.00"),
            estado=True,
            empresa_id=1,
        )
        self.mock_cu11_repo.get_variants_with_products.return_value = {
            101: (variant_101, product_50)
        }
        self.mock_cu11_repo.get_active_promotions_for_products.return_value = {}

        # Configurar comportamiento por llamada para simular:
        # - En Op 2 (uuid ...0021): OperationalError transitorio al consultar pago
        # - En Op 3 (uuid ...0022): No existe pago previo, pero stock disponible = 0 (conflicto de stock)
        # - En Op 4 (uuid ...0023): Pago y venta ya existen en PostgreSQL (reintento idempotente)
        existing_payment = SimpleNamespace(
            id_pago=700,
            id_venta=500,
            medio="EFECTIVO",
            estado="APROBADO",
            monto=Decimal("200.00"),
        )
        existing_sale = SimpleNamespace(
            id_venta=500,
            numero_venta="VTA-25-770E8400E29B41D4A716446655440023",
            estado="COMPLETADA",
            canal="PRESENCIAL",
            id_sucursal=2,
            id_cliente=None,
            id_empleado=8,
            id_reserva=None,
            subtotal=Decimal("200.00"),
            descuento_total=Decimal("0.00"),
            total=Decimal("200.00"),
            empresa_id=1,
        )

        self.mock_cu11_repo.get_payment_by_key.side_effect = [
            OperationalError("SELECT 1", {}, Exception("deadlock detected")),
            None,
            existing_payment,
        ]
        self.mock_cu11_repo.get_payment_for_sale.return_value = existing_payment
        self.mock_cu11_repo.get_sale_by_number.return_value = None
        self.mock_cu11_repo.get_sale_by_id.return_value = existing_sale

        # Inventario sin stock para Op 3
        inv_zero = SimpleNamespace(
            id_variante_producto=101,
            id_sucursal=2,
            empresa_id=1,
            stock_actual=1,
            stock_reservado=1,
            updated_at=NOW,
        )
        self.mock_cu11_repo.lock_inventories.return_value = {101: inv_zero}

        mixed_batch = OfflineQueueSyncRequest(
            operaciones=[
                OfflineSyncOperationInput(
                    uuid_operacion="770e8400-e29b-41d4-a716-446655440020",
                    tipo_operacion="RESERVA",
                    secuencia=1,
                    datos_originales={
                        "uuid_reserva_offline": "770e8400-e29b-41d4-a716-446655440020",
                        "id_sucursal": 2,
                        "fecha_atencion_programada": SCHEDULED_AT.isoformat(),
                        "detalles": [{"id_variante_producto": 101, "cantidad": 1}],
                    },
                ),
                OfflineSyncOperationInput(
                    uuid_operacion="770e8400-e29b-41d4-a716-446655440021",
                    tipo_operacion="VENTA",
                    secuencia=2,
                    datos_originales={
                        "uuid_venta_offline": "770e8400-e29b-41d4-a716-446655440021",
                        "canal": "PRESENCIAL",
                        "id_sucursal": 2,
                        "medio_pago": "EFECTIVO",
                        "total": "200.00",
                        "detalles": [
                            {
                                "id_variante_producto": 101,
                                "id_producto": 50,
                                "cantidad": 1,
                                "precio_unitario": "200.00",
                            }
                        ],
                    },
                ),
                OfflineSyncOperationInput(
                    uuid_operacion="770e8400-e29b-41d4-a716-446655440022",
                    tipo_operacion="VENTA",
                    secuencia=3,
                    datos_originales={
                        "uuid_venta_offline": "770e8400-e29b-41d4-a716-446655440022",
                        "canal": "PRESENCIAL",
                        "id_sucursal": 2,
                        "medio_pago": "EFECTIVO",
                        "total": "400.00",
                        "detalles": [
                            {
                                "id_variante_producto": 101,
                                "id_producto": 50,
                                "cantidad": 2,
                                "precio_unitario": "200.00",
                            }
                        ],
                    },
                ),
                OfflineSyncOperationInput(
                    uuid_operacion="770e8400-e29b-41d4-a716-446655440023",
                    tipo_operacion="VENTA",
                    secuencia=4,
                    datos_originales={
                        "uuid_venta_offline": "770e8400-e29b-41d4-a716-446655440023",
                        "canal": "PRESENCIAL",
                        "id_sucursal": 2,
                        "medio_pago": "EFECTIVO",
                        "total": "200.00",
                        "detalles": [
                            {
                                "id_variante_producto": 101,
                                "id_producto": 50,
                                "cantidad": 1,
                                "precio_unitario": "200.00",
                            }
                        ],
                    },
                ),
            ]
        )

        mixed_resp = self.sync_service.sync_pending_operations(
            cashier_user, mixed_batch, now=NOW
        )

        self.assertFalse(mixed_resp.success)
        self.assertEqual(mixed_resp.total_operaciones, 4)
        self.assertEqual(mixed_resp.rechazadas, 1)
        self.assertEqual(mixed_resp.reintentables, 1)
        self.assertEqual(mixed_resp.en_conflicto, 1)
        self.assertEqual(mixed_resp.confirmadas, 1)

        op1 = mixed_resp.resultados_por_uuid["770e8400-e29b-41d4-a716-446655440020"]
        self.assertEqual(op1.estado_resultado, "RECHAZADA")
        self.assertFalse(op1.confirmada)

        op2 = mixed_resp.resultados_por_uuid["770e8400-e29b-41d4-a716-446655440021"]
        self.assertEqual(op2.estado_resultado, "REINTENTABLE")
        self.assertTrue(op2.reintentable)
        self.assertTrue(op2.conservar_en_cola)

        op3 = mixed_resp.resultados_por_uuid["770e8400-e29b-41d4-a716-446655440022"]
        self.assertEqual(op3.estado_resultado, "EN_CONFLICTO")
        self.assertEqual(op3.conflictos[0].tipo_conflicto, "STOCK_INSUFICIENTE")

        op4 = mixed_resp.resultados_por_uuid["770e8400-e29b-41d4-a716-446655440023"]
        self.assertEqual(op4.estado_resultado, "CONFIRMADA")
        self.assertTrue(op4.confirmada)
        self.assertEqual(op4.id_servidor, 500)
        # Garantizar que el reintento idempotente nunca invocó create_sale ni descontó inventario de nuevo
        self.mock_cu11_repo.create_sale.assert_not_called()
        self.assertEqual(inv_zero.stock_actual, 1)
