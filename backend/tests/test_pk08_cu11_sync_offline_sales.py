"""Pruebas unitarias focalizadas con mocks para PK08 - CU11: Registrar venta de contado y compra digital offline.

Pruebas estrictamente locales con mocks, sin conexión a Supabase ni mutaciones reales en base de datos.
Verifica:
1. Flujo 1 (CLIENTE): Carrito -> Checkout -> Sucursal -> Compra digital con pago QR/Tarjeta simulado offline (PENDIENTE, stock comprometido) y rechazo de EFECTIVO.
2. Flujo 2 (CAJERO): POS Venta directa en EFECTIVO (COMPLETADA/APROBADO, descuento físico) vs QR/Tarjeta simulados (PENDIENTE de validación externa).
3. Flujo 3 (CAJERO): Reserva PENDIENTE -> CONFIRMADA -> ATENDIDA -> POS Venta por reserva parcial con liberación de remanente sin doble descuento de stock.
4. Respeto de secuencia obligatoria de reserva (bloqueo de atención sin confirmación previa, bloqueo de venta sin reserva ATENDIDA y bloqueo de doble venta sobre la misma reserva).
5. Detección de EN_CONFLICTO por stock insuficiente o cambio de precio en servidor conservando la operación pendiente del cliente.
6. Aislamiento multitenant, validación de rol/canal, bloqueo de suplantación de cliente/usuario y validación de sucursal asignada al cajero.
7. Idempotencia estricta por UUID en reintentos y ante colisión concurrente (IntegrityError) sin duplicar ventas ni descontar stock dos veces.
8. Ejecución de lote secuencial ordenado para CU13 y validación de plan SaaS (OFFLINE y VENTAS en CU07).
"""

from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock

from sqlalchemy.exc import IntegrityError

from app.PK07.CU07_ConsultarPlanLimites.service import FeatureNotEnabledError
from app.PK08.CU11_RegistrarVentaOffline.schemas import (
    OfflineBatchOperationItem,
    OfflineBatchSyncRequest,
    OfflineReservationTransitionRequest,
    OfflineSaleLineRequest,
    OfflineSaleSyncRequest,
)
from app.PK08.CU11_RegistrarVentaOffline.service import (
    OfflineSaleError,
    OfflineSaleService,
)
from app.schemas.auth import AuthenticatedUserData

NOW = datetime(2026, 11, 2, 15, 0, 0)


def dummy_branch(id_sucursal: int = 10, empresa_id: int = 1, estado: bool = True):
    return SimpleNamespace(
        id_sucursal=id_sucursal,
        empresa_id=empresa_id,
        nombre="Sucursal Equipetrol",
        direccion="Av. San Martín 456",
        estado=estado,
    )


def dummy_client(id_cliente: int = 7, id_usuario: int = 50, empresa_id: int = 1):
    return SimpleNamespace(
        id_cliente=id_cliente,
        id_usuario=id_usuario,
        empresa_id=empresa_id,
    )


def dummy_employee(id_empleado: int = 20, id_usuario: int = 80, empresa_id: int = 1):
    return SimpleNamespace(
        id_empleado=id_empleado,
        id_usuario=id_usuario,
        empresa_id=empresa_id,
    )


def dummy_assignment(
    id_empleado_sucursal: int = 300,
    id_empleado: int = 20,
    id_sucursal: int = 10,
    empresa_id: int = 1,
    estado: bool = True,
):
    return SimpleNamespace(
        id_empleado_sucursal=id_empleado_sucursal,
        id_empleado=id_empleado,
        id_sucursal=id_sucursal,
        empresa_id=empresa_id,
        estado=estado,
    )


def dummy_product(
    id_producto: int = 100,
    empresa_id: int = 1,
    precio: Decimal = Decimal("150.00"),
    estado: bool = True,
):
    return SimpleNamespace(
        id_producto=id_producto,
        empresa_id=empresa_id,
        nombre="Blazer Ejecutivo",
        precio=precio,
        precio_base=precio,
        precio_final=precio,
        estado=estado,
    )


def dummy_variant(
    id_variante: int = 201,
    id_producto: int = 100,
    sku: str = "BLZ-EJE-M-NEG",
    empresa_id: int = 1,
    estado: bool = True,
):
    return SimpleNamespace(
        id_variante_producto=id_variante,
        id_producto=id_producto,
        id_talla=2,
        id_color=4,
        sku=sku,
        empresa_id=empresa_id,
        estado=estado,
    )


def dummy_inventory(
    id_sucursal: int = 10,
    id_variante: int = 201,
    stock_actual: int = 10,
    stock_reservado: int = 0,
    empresa_id: int = 1,
):
    return SimpleNamespace(
        id_inventario_sucursal=901,
        id_sucursal=id_sucursal,
        id_variante_producto=id_variante,
        stock_actual=stock_actual,
        stock_reservado=stock_reservado,
        stock_minimo=2,
        empresa_id=empresa_id,
        updated_at=NOW,
    )


class TestCU11SyncOfflineSales(TestCase):
    """Suite de 8 pruebas unitarias focalizadas con mocks para PK08 - CU11."""

    def setUp(self):
        self.mock_db = MagicMock()
        self.mock_repo = MagicMock()
        self.mock_saas = MagicMock()
        self.service = OfflineSaleService(
            self.mock_db,
            repository=self.mock_repo,
            saas_service=self.mock_saas,
        )

        self.client_user = AuthenticatedUserData(
            id_usuario=50,
            nombre="Valeria",
            apellido="Gómez",
            correo="valeria@cliente.com",
            rol="CLIENTE",
            id_empresa=1,
        )
        self.cashier_user = AuthenticatedUserData(
            id_usuario=80,
            nombre="Carlos",
            apellido="Rojas",
            correo="carlos@tienda.com",
            rol="CAJERO",
            id_empresa=1,
        )

        self.branch = dummy_branch(id_sucursal=10, empresa_id=1)
        self.client_profile = dummy_client(id_cliente=7, id_usuario=50, empresa_id=1)
        self.employee_profile = dummy_employee(id_empleado=20, id_usuario=80, empresa_id=1)
        self.assignment = dummy_assignment(
            id_empleado_sucursal=300, id_empleado=20, id_sucursal=10, empresa_id=1
        )

        self.mock_repo.get_branch.return_value = self.branch
        self.mock_repo.get_client_by_user.return_value = self.client_profile
        self.mock_repo.get_employee_by_user.return_value = self.employee_profile
        self.mock_repo.get_employee_branch_assignment.return_value = self.assignment
        self.mock_repo.get_employee_active_branch_ids.return_value = [10]
        self.mock_repo.get_sale_by_number.return_value = None
        self.mock_repo.get_payment_by_key.return_value = None
        self.mock_repo.get_active_promotions_for_products.return_value = {}

        def _create_sale_side_effect(**kwargs):
            return SimpleNamespace(
                id_venta=700,
                empresa_id=kwargs["company_id"],
                id_sucursal=kwargs["branch_id"],
                id_empleado=kwargs["employee_id"],
                id_cliente=kwargs["client_id"],
                id_reserva=kwargs["reservation_id"],
                id_carrito=kwargs["cart_id"],
                canal=kwargs["canal"],
                moneda="BOB",
                numero_venta=kwargs["sale_number"],
                estado=kwargs["estado"],
                stock_comprometido=kwargs["stock_comprometido"],
                subtotal=kwargs["subtotal"],
                descuento_total=kwargs["descuento_total"],
                total=kwargs["total"],
                fecha_venta=kwargs["fecha_venta"],
                fecha_completada=kwargs["fecha_completada"],
                fecha_expiracion_pago=kwargs["fecha_expiracion_pago"],
            )

        def _create_payment_side_effect(**kwargs):
            return SimpleNamespace(
                id_pago=800,
                empresa_id=kwargs["company_id"],
                id_venta=kwargs["sale_id"],
                medio=kwargs["medio"],
                proveedor=kwargs["proveedor"],
                entorno=kwargs["entorno"],
                estado=kwargs["estado"],
                monto=kwargs["monto"],
                moneda="BOB",
                clave_idempotencia=kwargs["idempotency_key"],
                fecha_aprobacion=kwargs["fecha_aprobacion"],
            )

        self.mock_repo.create_sale.side_effect = _create_sale_side_effect
        self.mock_repo.create_payment.side_effect = _create_payment_side_effect

    def test_01_flujo1_cliente_compra_digital_pago_simulado_qr_y_tarjeta(self):
        """Flujo 1: CLIENTE sincroniza compra digital con QR/Tarjeta simulado (PENDIENTE, stock comprometido) y rechaza EFECTIVO."""
        variant = dummy_variant(id_variante=201, id_producto=100)
        product = dummy_product(id_producto=100, precio=Decimal("150.00"))
        inventory = dummy_inventory(id_sucursal=10, id_variante=201, stock_actual=10, stock_reservado=2)
        cart = SimpleNamespace(id_carrito=45, id_cliente=7, empresa_id=1, estado="ACTIVO")

        self.mock_repo.get_variants_with_products.return_value = {201: (variant, product)}
        self.mock_repo.lock_inventories.return_value = {201: inventory}
        self.mock_repo.get_cart.return_value = cart
        self.mock_repo.get_sale_for_cart.return_value = None

        payload_qr = OfflineSaleSyncRequest(
            uuid_venta_offline="550e8400-e29b-41d4-a716-446655440001",
            canal="DIGITAL",
            id_sucursal=10,
            id_carrito=45,
            medio_pago="QR",
            pago_simulado=True,
            detalles=[
                OfflineSaleLineRequest(
                    id_variante_producto=201,
                    cantidad=2,
                    precio_unitario=Decimal("150.00"),
                )
            ],
            total=Decimal("300.00"),
        )

        response = self.service.sync_offline_sale(self.client_user, payload_qr, now=NOW)

        self.assertTrue(response.success)
        self.assertTrue(response.confirmada)
        self.assertEqual(response.estado_resultado, "CONFIRMADA")
        self.assertEqual(response.canal, "DIGITAL")
        # El pago electrónico simulado NUNCA se registra falsamente como APROBADO
        self.assertEqual(response.estado_venta, "PENDIENTE")
        self.assertEqual(response.estado_pago, "PENDIENTE")
        self.assertTrue(response.pago_simulado)
        self.assertTrue(response.pendiente_validacion_externa)
        self.assertTrue(response.stock_comprometido)
        # El stock queda comprometido en stock_reservado (2 + 2 = 4) y el carrito pasa a CONVERTIDO
        self.assertEqual(inventory.stock_reservado, 4)
        self.assertEqual(inventory.stock_actual, 10)
        self.assertEqual(cart.estado, "CONVERTIDO")

        # Subcaso: CLIENTE intentando pagar con EFECTIVO en canal DIGITAL es rechazado
        payload_cash = OfflineSaleSyncRequest(
            uuid_venta_offline="550e8400-e29b-41d4-a716-446655440002",
            canal="DIGITAL",
            id_sucursal=10,
            medio_pago="EFECTIVO",
            detalles=[OfflineSaleLineRequest(id_variante_producto=201, cantidad=1)],
        )
        res_cash = self.service.sync_offline_sale(self.client_user, payload_cash, now=NOW)
        self.assertFalse(res_cash.confirmada)
        self.assertEqual(res_cash.estado_resultado, "RECHAZADA")
        self.assertTrue(res_cash.conservar_operacion_pendiente)

    def test_02_flujo2_cajero_pos_venta_directa_efectivo_vs_qr_tarjeta_simulados(self):
        """Flujo 2: CAJERO registra venta directa en EFECTIVO (COMPLETADA/APROBADO, descuento físico) vs TARJETA simulada (PENDIENTE)."""
        variant = dummy_variant(id_variante=201, id_producto=100)
        product = dummy_product(id_producto=100, precio=Decimal("200.00"))
        inventory_cash = dummy_inventory(id_sucursal=10, id_variante=201, stock_actual=12, stock_reservado=2)

        self.mock_repo.get_variants_with_products.return_value = {201: (variant, product)}
        self.mock_repo.lock_inventories.return_value = {201: inventory_cash}

        # Caso A: Cobro físico en EFECTIVO
        payload_cash = OfflineSaleSyncRequest(
            uuid_venta_offline="550e8400-e29b-41d4-a716-446655440010",
            canal="PRESENCIAL",
            id_sucursal=10,
            medio_pago="EFECTIVO",
            detalles=[
                OfflineSaleLineRequest(
                    id_variante_producto=201,
                    cantidad=3,
                    precio_unitario=Decimal("200.00"),
                )
            ],
            total=Decimal("600.00"),
        )
        res_cash = self.service.sync_offline_sale(self.cashier_user, payload_cash, now=NOW)

        self.assertTrue(res_cash.confirmada)
        self.assertEqual(res_cash.estado_resultado, "CONFIRMADA")
        self.assertEqual(res_cash.estado_venta, "COMPLETADA")
        self.assertEqual(res_cash.estado_pago, "APROBADO")
        self.assertFalse(res_cash.pago_simulado)
        self.assertFalse(res_cash.pendiente_validacion_externa)
        # Stock físico descontado de inmediato: 12 - 3 = 9
        self.assertEqual(inventory_cash.stock_actual, 9)
        self.assertEqual(inventory_cash.stock_reservado, 2)

        # Caso B: Cobro en POS con TARJETA simulada offline (queda PENDIENTE de validación externa)
        inventory_card = dummy_inventory(id_sucursal=10, id_variante=201, stock_actual=9, stock_reservado=2)
        self.mock_repo.lock_inventories.return_value = {201: inventory_card}

        payload_card = OfflineSaleSyncRequest(
            uuid_venta_offline="550e8400-e29b-41d4-a716-446655440011",
            canal="PRESENCIAL",
            id_sucursal=10,
            medio_pago="TARJETA",
            detalles=[OfflineSaleLineRequest(id_variante_producto=201, cantidad=1)],
        )
        res_card = self.service.sync_offline_sale(self.cashier_user, payload_card, now=NOW)

        self.assertTrue(res_card.confirmada)
        self.assertEqual(res_card.estado_venta, "PENDIENTE")
        self.assertEqual(res_card.estado_pago, "PENDIENTE")
        self.assertTrue(res_card.pago_simulado)
        self.assertTrue(res_card.pendiente_validacion_externa)
        # No descuenta stock físico antes de validar el pago con pasarela externa
        self.assertEqual(inventory_card.stock_actual, 9)

    def test_03_flujo3_cajero_secuencia_reserva_pendiente_confirmada_atendida_y_venta_parcial(self):
        """Flujo 3: CAJERO ejecuta PENDIENTE -> CONFIRMADA -> ATENDIDA -> POS Venta por reserva parcial liberando remanente."""
        reservation = SimpleNamespace(
            id_reserva=55,
            empresa_id=1,
            id_sucursal=10,
            id_cliente=7,
            id_empleado_atencion=None,
            codigo="RSV-20261102-ABC12",
            estado="PENDIENTE",
            fecha_atencion_programada=NOW + timedelta(hours=1),
            fecha_expiracion=NOW + timedelta(hours=2),
            fecha_atencion=None,
            updated_at=NOW,
        )
        res_detail = SimpleNamespace(
            id_detalle_reserva=1,
            id_reserva=55,
            id_variante_producto=201,
            cantidad=3,
            precio_unitario=Decimal("140.00"),
            empresa_id=1,
        )
        variant = dummy_variant(id_variante=201, id_producto=100)
        product = dummy_product(id_producto=100, precio=Decimal("150.00"))
        # Inventario inicial con 3 unidades reservadas por la reserva #55
        inventory = dummy_inventory(id_sucursal=10, id_variante=201, stock_actual=10, stock_reservado=3)

        self.mock_repo.get_reservation.return_value = reservation
        self.mock_repo.get_reservation_details.return_value = [res_detail]
        self.mock_repo.get_sale_for_reservation.return_value = None
        self.mock_repo.get_variants_with_products.return_value = {201: (variant, product)}
        self.mock_repo.lock_inventories.return_value = {201: inventory}

        # Paso 1: Confirmar preparación (PENDIENTE -> CONFIRMADA)
        res_confirm = self.service.sync_reservation_transition(
            self.cashier_user,
            OfflineReservationTransitionRequest(
                uuid_operacion_offline="op-confirm-001",
                id_reserva=55,
                accion="CONFIRM",
                id_sucursal=10,
            ),
            now=NOW,
        )
        self.assertTrue(res_confirm.confirmada)
        self.assertEqual(res_confirm.estado_reserva, "CONFIRMADA")
        self.assertEqual(reservation.estado, "CONFIRMADA")

        # Paso 2: Marcar como atendida (CONFIRMADA -> ATENDIDA)
        res_attend = self.service.sync_reservation_transition(
            self.cashier_user,
            OfflineReservationTransitionRequest(
                uuid_operacion_offline="op-attend-002",
                id_reserva=55,
                accion="ATTEND",
                id_sucursal=10,
            ),
            now=NOW,
        )
        self.assertTrue(res_attend.confirmada)
        self.assertEqual(res_attend.estado_reserva, "ATENDIDA")
        self.assertEqual(reservation.estado, "ATENDIDA")
        self.assertEqual(reservation.id_empleado_atencion, 20)

        # Paso 3: POS «Venta por reserva» parcial (cliente compra 2 de las 3 reservadas, paga en EFECTIVO)
        sale_res = self.service.sync_offline_sale(
            self.cashier_user,
            OfflineSaleSyncRequest(
                uuid_venta_offline="550e8400-e29b-41d4-a716-446655440033",
                canal="PRESENCIAL",
                id_sucursal=10,
                id_reserva=55,
                codigo_reserva="RSV-20261102-ABC12",
                medio_pago="EFECTIVO",
                detalles=[
                    OfflineSaleLineRequest(
                        id_variante_producto=201,
                        cantidad=2,
                        precio_unitario=Decimal("140.00"),
                    )
                ],
                total=Decimal("280.00"),
            ),
            now=NOW,
        )

        self.assertTrue(sale_res.confirmada)
        self.assertEqual(sale_res.estado_venta, "COMPLETADA")
        self.assertEqual(sale_res.estado_pago, "APROBADO")
        self.assertEqual(sale_res.id_reserva, 55)
        self.assertEqual(sale_res.estado_reserva, "ATENDIDA")
        self.assertEqual(len(sale_res.liberaciones_reserva), 1)
        self.assertEqual(sale_res.liberaciones_reserva[0].cantidad_reservada, 3)
        self.assertEqual(sale_res.liberaciones_reserva[0].cantidad_comprada, 2)
        self.assertEqual(sale_res.liberaciones_reserva[0].cantidad_liberada, 1)
        # Stock físico descontado una sola vez por las 2 compradas (10 - 2 = 8) y stock_reservado liberado (3 - 1 - 2 = 0)
        self.assertEqual(inventory.stock_actual, 8)
        self.assertEqual(inventory.stock_reservado, 0)

    def test_04_secuencia_reserva_bloquea_salto_de_estado_y_venta_sin_atencion_previa(self):
        """Verifica que no se pueda atender una reserva PENDIENTE ni vender una reserva que no esté ATENDIDA o ya tenga venta."""
        reservation = SimpleNamespace(
            id_reserva=60,
            empresa_id=1,
            id_sucursal=10,
            id_cliente=7,
            codigo="RSV-20261102-PEND1",
            estado="PENDIENTE",
            fecha_expiracion=NOW + timedelta(hours=2),
        )
        self.mock_repo.get_reservation.return_value = reservation

        # 1. Intentar ATTEND directamente desde PENDIENTE -> EN_CONFLICTO
        jump_res = self.service.sync_reservation_transition(
            self.cashier_user,
            OfflineReservationTransitionRequest(
                uuid_operacion_offline="op-jump-001",
                id_reserva=60,
                accion="ATTEND",
                id_sucursal=10,
            ),
            now=NOW,
        )
        self.assertFalse(jump_res.confirmada)
        self.assertEqual(jump_res.estado_resultado, "EN_CONFLICTO")
        self.assertTrue(jump_res.conservar_operacion_pendiente)

        # 2. Intentar vender en POS una reserva en estado CONFIRMADA (aún no ATENDIDA) -> EN_CONFLICTO
        reservation.estado = "CONFIRMADA"
        sale_unattended = self.service.sync_offline_sale(
            self.cashier_user,
            OfflineSaleSyncRequest(
                uuid_venta_offline="550e8400-e29b-41d4-a716-446655440044",
                canal="PRESENCIAL",
                id_sucursal=10,
                id_reserva=60,
                medio_pago="EFECTIVO",
                detalles=[OfflineSaleLineRequest(id_variante_producto=201, cantidad=1)],
            ),
            now=NOW,
        )
        self.assertFalse(sale_unattended.confirmada)
        self.assertEqual(sale_unattended.estado_resultado, "EN_CONFLICTO")
        self.assertEqual(sale_unattended.conflictos[0].tipo_conflicto, "RESERVA_NO_ATENDIDA")
        self.assertTrue(sale_unattended.conservar_operacion_pendiente)

        # 3. Intentar vender una reserva ATENDIDA que ya tiene otra venta asociada -> EN_CONFLICTO
        reservation.estado = "ATENDIDA"
        self.mock_repo.get_sale_for_reservation.return_value = SimpleNamespace(
            id_venta=999, numero_venta="VTA-80-OTRAVENTA"
        )
        dup_sale = self.service.sync_offline_sale(
            self.cashier_user,
            OfflineSaleSyncRequest(
                uuid_venta_offline="550e8400-e29b-41d4-a716-446655440045",
                canal="PRESENCIAL",
                id_sucursal=10,
                id_reserva=60,
                medio_pago="EFECTIVO",
                detalles=[OfflineSaleLineRequest(id_variante_producto=201, cantidad=1)],
            ),
            now=NOW,
        )
        self.assertFalse(dup_sale.confirmada)
        self.assertEqual(dup_sale.estado_resultado, "EN_CONFLICTO")
        self.assertEqual(dup_sale.conflictos[0].tipo_conflicto, "RESERVA_VENTA_DUPLICADA")

    def test_05_conflicto_stock_insuficiente_y_cambio_de_precio_conservan_operacion_pendiente(self):
        """Verifica que stock insuficiente o cambio de precio devuelvan EN_CONFLICTO con detalle para CU13/CU14."""
        variant = dummy_variant(id_variante=201, id_producto=100, sku="BLZ-EJE-M-NEG")
        product = dummy_product(id_producto=100, precio=Decimal("150.00"))
        low_inventory = dummy_inventory(id_sucursal=10, id_variante=201, stock_actual=3, stock_reservado=2)

        self.mock_repo.get_variants_with_products.return_value = {201: (variant, product)}
        self.mock_repo.lock_inventories.return_value = {201: low_inventory}

        # Caso 1: Stock disponible es 1 (3 - 2), pero solicita 2 -> STOCK_INSUFICIENTE
        res_stock = self.service.sync_offline_sale(
            self.cashier_user,
            OfflineSaleSyncRequest(
                uuid_venta_offline="550e8400-e29b-41d4-a716-446655440051",
                canal="PRESENCIAL",
                id_sucursal=10,
                medio_pago="EFECTIVO",
                detalles=[OfflineSaleLineRequest(id_variante_producto=201, cantidad=2)],
            ),
            now=NOW,
        )
        self.assertFalse(res_stock.confirmada)
        self.assertEqual(res_stock.estado_resultado, "EN_CONFLICTO")
        self.assertTrue(res_stock.conservar_operacion_pendiente)
        self.assertEqual(res_stock.conflictos[0].tipo_conflicto, "STOCK_INSUFICIENTE")
        self.assertEqual(res_stock.conflictos[0].valor_actual_servidor, 1)

        # Caso 2: Precio capturado offline (Bs 120.00) difiere del precio vigente en servidor (Bs 150.00) -> PRECIO_MODIFICADO
        res_price = self.service.sync_offline_sale(
            self.client_user,
            OfflineSaleSyncRequest(
                uuid_venta_offline="550e8400-e29b-41d4-a716-446655440052",
                canal="DIGITAL",
                id_sucursal=10,
                medio_pago="QR",
                detalles=[
                    OfflineSaleLineRequest(
                        id_variante_producto=201,
                        cantidad=1,
                        precio_unitario=Decimal("120.00"),
                    )
                ],
                total=Decimal("120.00"),
            ),
            now=NOW,
        )
        self.assertFalse(res_price.confirmada)
        self.assertEqual(res_price.estado_resultado, "EN_CONFLICTO")
        self.assertEqual(res_price.conflictos[0].tipo_conflicto, "PRECIO_MODIFICADO")
        self.assertTrue(res_price.conservar_operacion_pendiente)

    def test_06_aislamiento_multitenant_permisos_rol_y_sucursal_autorizada(self):
        """Verifica bloqueo de cruce de empresa, cruce de rol/canal, suplantación de cliente y sucursal no asignada."""
        base_payload = OfflineSaleSyncRequest(
            uuid_venta_offline="550e8400-e29b-41d4-a716-446655440061",
            id_sucursal=10,
            medio_pago="QR",
            detalles=[OfflineSaleLineRequest(id_variante_producto=201, cantidad=1)],
        )

        # 1. CLIENTE intentando registrar una venta PRESENCIAL -> 403
        with self.assertRaises(OfflineSaleError) as ctx_role:
            self.service.sync_offline_sale(
                self.client_user, base_payload, forced_channel="PRESENCIAL", now=NOW
            )
        self.assertEqual(ctx_role.exception.status_code, 403)

        # 2. CAJERO intentando registrar una compra DIGITAL -> 403
        with self.assertRaises(OfflineSaleError) as ctx_cashier_dig:
            self.service.sync_offline_sale(
                self.cashier_user, base_payload, forced_channel="DIGITAL", now=NOW
            )
        self.assertEqual(ctx_cashier_dig.exception.status_code, 403)

        # 3. Intento de sincronizar en otra empresa (tenant_id=99 vs sesión=1) -> 403
        with self.assertRaises(OfflineSaleError) as ctx_tenant:
            self.service.sync_offline_sale(
                self.client_user, base_payload, requested_company_id=99, now=NOW
            )
        self.assertEqual(ctx_tenant.exception.status_code, 403)

        # 4. CLIENTE intentando suplantar otro id_cliente -> 403
        spoof_payload = OfflineSaleSyncRequest(
            uuid_venta_offline="550e8400-e29b-41d4-a716-446655440062",
            canal="DIGITAL",
            id_sucursal=10,
            id_cliente=999,
            medio_pago="QR",
            detalles=[OfflineSaleLineRequest(id_variante_producto=201, cantidad=1)],
        )
        with self.assertRaises(OfflineSaleError) as ctx_spoof:
            self.service.sync_offline_sale(self.client_user, spoof_payload, now=NOW)
        self.assertEqual(ctx_spoof.exception.status_code, 403)

        # 5. CAJERO intentando vender en una sucursal no asignada -> 403
        self.mock_repo.get_employee_branch_assignment.return_value = None
        with self.assertRaises(OfflineSaleError) as ctx_branch:
            self.service.sync_offline_sale(
                self.cashier_user, base_payload, forced_channel="PRESENCIAL", now=NOW
            )
        self.assertEqual(ctx_branch.exception.status_code, 403)

    def test_07_idempotencia_por_uuid_y_colision_concurrente_sin_doble_descuento(self):
        """Verifica que reintentar el mismo UUID o sufrir IntegrityError retorne la venta existente sin duplicar descuento."""
        existing_sale = SimpleNamespace(
            id_venta=777,
            empresa_id=1,
            id_sucursal=10,
            id_empleado=20,
            id_cliente=None,
            id_reserva=None,
            canal="PRESENCIAL",
            moneda="BOB",
            numero_venta="VTA-80-550E8400E29B41D4A716446655440077",
            estado="COMPLETADA",
            stock_comprometido=False,
            subtotal=Decimal("150.00"),
            descuento_total=Decimal("0.00"),
            total=Decimal("150.00"),
            fecha_venta=NOW,
        )
        existing_payment = SimpleNamespace(
            id_pago=888,
            id_venta=777,
            medio="EFECTIVO",
            estado="APROBADO",
        )
        self.mock_repo.get_sale_by_number.return_value = existing_sale
        self.mock_repo.get_payment_for_sale.return_value = existing_payment

        payload = OfflineSaleSyncRequest(
            uuid_venta_offline="550e8400-e29b-41d4-a716-446655440077",
            canal="PRESENCIAL",
            id_sucursal=10,
            medio_pago="EFECTIVO",
            detalles=[OfflineSaleLineRequest(id_variante_producto=201, cantidad=1)],
        )

        retry_res = self.service.sync_offline_sale(self.cashier_user, payload, now=NOW)
        self.assertTrue(retry_res.confirmada)
        self.assertEqual(retry_res.id_venta, 777)
        self.assertEqual(retry_res.id_pago, 888)
        self.mock_repo.create_sale.assert_not_called()

        # Colisión concurrente IntegrityError durante commit
        self.mock_repo.get_sale_by_number.side_effect = [None, existing_sale]
        variant = dummy_variant(id_variante=201, id_producto=100)
        product = dummy_product(id_producto=100, precio=Decimal("150.00"))
        inv = dummy_inventory(id_sucursal=10, id_variante=201, stock_actual=5, stock_reservado=0)
        self.mock_repo.get_variants_with_products.return_value = {201: (variant, product)}
        self.mock_repo.lock_inventories.return_value = {201: inv}
        self.mock_db.commit.side_effect = IntegrityError("uq_venta", {}, Exception("duplicate"))

        race_res = self.service.sync_offline_sale(self.cashier_user, payload, now=NOW)
        self.assertTrue(race_res.confirmada)
        self.assertEqual(race_res.id_venta, 777)

    def test_08_lote_secuencial_ordenado_y_validacion_plan_saas_cu07(self):
        """Verifica ejecución secuencial de lote para CU13 y bloqueo cuando el plan SaaS no incluye OFFLINE o VENTAS."""
        reservation = SimpleNamespace(
            id_reserva=90,
            empresa_id=1,
            id_sucursal=10,
            id_cliente=7,
            id_empleado_atencion=None,
            codigo="RSV-20261102-BATCH",
            estado="PENDIENTE",
            fecha_expiracion=NOW + timedelta(hours=3),
            fecha_atencion=None,
            updated_at=NOW,
        )
        res_detail = SimpleNamespace(
            id_detalle_reserva=10,
            id_reserva=90,
            id_variante_producto=201,
            cantidad=1,
            precio_unitario=Decimal("150.00"),
            empresa_id=1,
        )
        variant = dummy_variant(id_variante=201, id_producto=100)
        product = dummy_product(id_producto=100, precio=Decimal("150.00"))
        inventory = dummy_inventory(id_sucursal=10, id_variante=201, stock_actual=5, stock_reservado=1)

        self.mock_repo.get_reservation.return_value = reservation
        self.mock_repo.get_reservation_details.return_value = [res_detail]
        self.mock_repo.get_sale_for_reservation.return_value = None
        self.mock_repo.get_variants_with_products.return_value = {201: (variant, product)}
        self.mock_repo.lock_inventories.return_value = {201: inventory}

        batch_req = OfflineBatchSyncRequest(
            operaciones=[
                OfflineBatchOperationItem(
                    tipo_operacion="TRANSICION_RESERVA",
                    transicion=OfflineReservationTransitionRequest(
                        uuid_operacion_offline="batch-op-1-confirm",
                        id_reserva=90,
                        accion="CONFIRM",
                        id_sucursal=10,
                    ),
                ),
                OfflineBatchOperationItem(
                    tipo_operacion="TRANSICION_RESERVA",
                    transicion=OfflineReservationTransitionRequest(
                        uuid_operacion_offline="batch-op-2-attend",
                        id_reserva=90,
                        accion="ATTEND",
                        id_sucursal=10,
                    ),
                ),
                OfflineBatchOperationItem(
                    tipo_operacion="VENTA",
                    venta=OfflineSaleSyncRequest(
                        uuid_venta_offline="550e8400-e29b-41d4-a716-446655440090",
                        canal="PRESENCIAL",
                        id_sucursal=10,
                        id_reserva=90,
                        medio_pago="EFECTIVO",
                        detalles=[OfflineSaleLineRequest(id_variante_producto=201, cantidad=1)],
                    ),
                ),
            ]
        )

        batch_res = self.service.sync_batch_operations(self.cashier_user, batch_req, now=NOW)
        self.assertTrue(batch_res.success)
        self.assertEqual(batch_res.total_operaciones, 3)
        self.assertEqual(batch_res.confirmadas, 3)
        self.assertEqual(batch_res.en_conflicto, 0)
        self.assertEqual(inventory.stock_actual, 4)
        self.assertEqual(inventory.stock_reservado, 0)

        # Validación SaaS: plan sin funcionalidad OFFLINE habilitada lanza 403
        self.mock_saas.validate_feature_enabled.side_effect = FeatureNotEnabledError(
            "El plan actual no incluye la funcionalidad OFFLINE."
        )
        with self.assertRaises(OfflineSaleError) as ctx_saas:
            self.service.sync_offline_sale(
                self.client_user,
                OfflineSaleSyncRequest(
                    uuid_venta_offline="550e8400-e29b-41d4-a716-446655440099",
                    canal="DIGITAL",
                    id_sucursal=10,
                    medio_pago="QR",
                    detalles=[OfflineSaleLineRequest(id_variante_producto=201, cantidad=1)],
                ),
                now=NOW,
            )
        self.assertEqual(ctx_saas.exception.status_code, 403)

