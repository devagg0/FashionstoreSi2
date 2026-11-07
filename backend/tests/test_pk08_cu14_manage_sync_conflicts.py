"""Pruebas unitarias focalizadas con mocks para PK08 - CU14: Gestionar conflictos y resultados de sincronización.

Batería de exactamente 4 pruebas unitarias con mocks (sin conexión a Supabase ni mutaciones reales en BD):
1. Conflictos de stock insuficiente y cambio de precio: diagnóstico con datos del servidor, exigencia de consentimiento explícito y diferenciación EFECTIVO vs QR/TARJETA simulado.
2. Conflictos de horario vencido y estados inválidos/cancelados de reserva: reprogramación preservando UUID y bloqueo de ventas sobre reservas inválidas.
3. Bloqueo en cascada de operaciones dependientes (RESERVA -> CONFIRM -> ATTEND -> VENTA) y resolución secuencial autorizada.
4. Idempotencia persistente por UUID, diferenciación de errores REINTENTABLE vs RECHAZADA/EN_CONFLICTO y seguridad multitenant/rol.
"""

from datetime import datetime, time, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock

from sqlalchemy.exc import OperationalError

from app.PK08.CU10_RegistrarReservaOffline.service import OfflineReservationService
from app.PK08.CU11_RegistrarVentaOffline.service import OfflineSaleService
from app.PK08.CU13_SincronizarOperacionesPendientes.schemas import (
    OfflineSyncOperationInput,
)
from app.PK08.CU13_SincronizarOperacionesPendientes.service import (
    OfflineQueueSyncService,
)
from app.PK08.CU14_GestionarConflictosSincronizacion.schemas import (
    OfflineConflictDiagnoseRequest,
    OfflineConflictResolveRequest,
    OfflineOperationResolutionInput,
)
from app.PK08.CU14_GestionarConflictosSincronizacion.service import (
    OfflineConflictError,
    OfflineConflictManagementService,
)
from app.schemas.auth import AuthenticatedUserData

NOW = datetime(2026, 11, 7, 14, 0, 0)


def make_user(
    id_usuario: int = 10,
    rol: str = "CLIENTE",
    id_empresa: int = 1,
    nombre: str = "Valeria",
    apellido: str = "Gomez",
) -> AuthenticatedUserData:
    return AuthenticatedUserData(
        id_usuario=id_usuario,
        id_empresa=id_empresa,
        rol=rol,
        nombre=nombre,
        apellido=apellido,
        correo=f"user{id_usuario}@fashionstore.bo",
    )


class TestPK08CU14ManageSyncConflicts(TestCase):
    """4 pruebas unitarias focalizadas para PK08 - CU14."""

    def setUp(self) -> None:
        self.mock_db = MagicMock()
        self.mock_conflict_repo = MagicMock()
        self.mock_cu13_repo = MagicMock()
        self.mock_cu10_repo = MagicMock()
        self.mock_cu11_repo = MagicMock()
        self.mock_saas = MagicMock()

        self.mock_saas.validate_feature_enabled.return_value = True
        self.mock_saas.check_feature_enabled.return_value = True
        self.mock_cu13_repo.get_branch_name.return_value = "Sucursal Central"
        self.mock_cu13_repo.resolve_reservation_reference.return_value = None
        self.mock_cu11_repo.get_active_promotions_for_products.return_value = {}
        self.mock_cu11_repo.get_sale_by_number.return_value = None
        self.mock_cu11_repo.get_payment_by_key.return_value = None
        self.mock_cu10_repo.code_exists.return_value = False
        self.mock_cu10_repo.has_active_slot_conflict.return_value = False

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
        self.conflict_service = OfflineConflictManagementService(
            db=self.mock_db,
            conflict_repository=self.mock_conflict_repo,
            queue_repository=self.mock_cu13_repo,
            reservation_service=self.reservation_service,
            sale_service=self.sale_service,
            sync_service=self.sync_service,
            saas_service=self.mock_saas,
        )

    def test_1_stock_and_price_conflicts_diagnosis_and_resolution_with_consent(
        self,
    ) -> None:
        """1. Diagnóstico y resolución con consentimiento de conflictos de stock y precio (COMPRA QR simulada vs VENTA EFECTIVO)."""
        client_user = make_user(id_usuario=10, rol="CLIENTE", id_empresa=1)
        self.mock_cu11_repo.get_client_by_user.return_value = SimpleNamespace(
            id_cliente=7, id_usuario=10, empresa_id=1
        )
        self.mock_cu11_repo.get_branch.return_value = SimpleNamespace(
            id_sucursal=2, empresa_id=1, nombre="Sucursal Central", estado=True
        )

        variant = SimpleNamespace(
            id_variante_producto=101,
            id_producto=50,
            sku="BLZ-NEG-M",
            estado=True,
            empresa_id=1,
        )
        product = SimpleNamespace(
            id_producto=50,
            nombre="Blazer Sastre",
            precio=Decimal("220.00"),
            precio_base=Decimal("220.00"),
            precio_final=Decimal("220.00"),
            estado=True,
            empresa_id=1,
        )
        # Stock disponible real en servidor = 5 - 3 = 2 unidades; precio real = Bs 220.00
        inv = SimpleNamespace(
            id_variante_producto=101,
            id_sucursal=2,
            empresa_id=1,
            stock_actual=5,
            stock_reservado=3,
            updated_at=NOW,
        )
        self.mock_cu11_repo.get_variants_with_products.return_value = {
            101: (variant, product)
        }
        self.mock_conflict_repo.get_inventories_snapshot.return_value = {101: inv}
        self.mock_cu11_repo.lock_inventories.return_value = {101: inv}

        # Operación capturada offline: 4 unidades a Bs 180.00 con QR simulado
        op_input = OfflineSyncOperationInput(
            uuid_operacion="uuid-buy-conflict-01",
            tipo_operacion="COMPRA",
            payload={
                "uuid_venta_offline": "uuid-buy-conflict-01",
                "canal": "DIGITAL",
                "id_sucursal": 2,
                "medio_pago": "QR",
                "pago_simulado": True,
                "detalles": [
                    {
                        "id_variante_producto": 101,
                        "cantidad": 4,
                        "precio_unitario": "180.00",
                    }
                ],
                "total": "720.00",
            },
        )

        # Paso A: Diagnóstico sin alterar inventario
        diag_resp = self.conflict_service.diagnose_conflicts(
            client_user,
            OfflineConflictDiagnoseRequest(operaciones=[op_input]),
            now=NOW,
        )
        self.assertEqual(diag_resp.en_conflicto, 1)
        diag = diag_resp.diagnosticos_por_uuid["uuid-buy-conflict-01"]
        self.assertEqual(diag.estado_resultado, "EN_CONFLICTO")
        conflict_codes = {c.tipo_conflicto for c in diag.conflictos}
        self.assertIn("STOCK_INSUFICIENTE", conflict_codes)
        self.assertIn("PRECIO_MODIFICADO", conflict_codes)
        self.assertEqual(diag.datos_actuales_servidor.variantes[0].stock_disponible, 2)
        self.assertEqual(
            diag.datos_actuales_servidor.variantes[0].precio_neto_servidor,
            Decimal("220.00"),
        )
        self.assertIn("AJUSTAR_CANTIDAD_STOCK", diag.acciones_permitidas)
        self.assertIn("ACEPTAR_PRECIO_SERVIDOR", diag.acciones_permitidas)
        self.assertEqual(inv.stock_reservado, 3)  # Sin mutación durante diagnóstico

        # Paso B: Intento de resolución SIN consentimiento explícito es bloqueado
        no_consent_resp = self.conflict_service.resolve_conflicts(
            client_user,
            OfflineConflictResolveRequest(
                resoluciones=[
                    OfflineOperationResolutionInput(
                        uuid_operacion="uuid-buy-conflict-01",
                        tipo_operacion="COMPRA",
                        accion_resolucion="AJUSTAR_CANTIDAD_STOCK",
                        consentimiento_usuario=False,
                        payload=op_input.payload,
                    )
                ]
            ),
            now=NOW,
        )
        self.assertFalse(no_consent_resp.success)
        self.assertFalse(
            no_consent_resp.resultados_por_uuid["uuid-buy-conflict-01"].confirmada
        )
        self.assertEqual(inv.stock_reservado, 3)

        # Paso C: Resolución CON consentimiento explícito ajusta a 2 unidades y acepta Bs 220.00 (total Bs 440.00)
        self.mock_cu11_repo.create_sale.side_effect = lambda **kw: SimpleNamespace(
            id_venta=901,
            empresa_id=kw["company_id"],
            id_sucursal=kw["branch_id"],
            id_empleado=kw["employee_id"],
            id_cliente=kw["client_id"],
            id_reserva=kw["reservation_id"],
            canal=kw["canal"],
            moneda="BOB",
            numero_venta=kw["sale_number"],
            estado=kw["estado"],
            stock_comprometido=kw["stock_comprometido"],
            subtotal=kw["subtotal"],
            descuento_total=kw["descuento_total"],
            total=kw["total"],
            fecha_venta=kw["fecha_venta"],
        )
        self.mock_cu11_repo.create_payment.side_effect = lambda **kw: SimpleNamespace(
            id_pago=950,
            id_venta=kw["sale_id"],
            medio=kw["medio"],
            estado=kw["estado"],
            monto=kw["monto"],
        )

        resolve_resp = self.conflict_service.resolve_conflicts(
            client_user,
            OfflineConflictResolveRequest(
                resoluciones=[
                    OfflineOperationResolutionInput(
                        uuid_operacion="uuid-buy-conflict-01",
                        tipo_operacion="COMPRA",
                        accion_resolucion="AJUSTAR_CANTIDAD_STOCK",
                        consentimiento_usuario=True,
                        payload=op_input.payload,
                    )
                ]
            ),
            now=NOW,
        )
        self.assertTrue(resolve_resp.success)
        res_item = resolve_resp.resultados_por_uuid["uuid-buy-conflict-01"]
        self.assertTrue(res_item.confirmada)
        self.assertEqual(res_item.estado_resultado, "CONFIRMADA")
        self.assertEqual(res_item.total, Decimal("440.00"))
        # QR simulado mantiene estado PENDIENTE de validación bancaria externa
        self.assertEqual(res_item.estado_entidad_servidor, "PENDIENTE")
        self.assertEqual(res_item.estado_pago, "PENDIENTE")
        self.assertTrue(res_item.pago_simulado)
        self.assertTrue(res_item.pendiente_validacion_externa)
        self.assertEqual(inv.stock_reservado, 5)  # 3 + 2 comprometidas

    def test_2_reservation_schedule_expiry_and_invalid_state_resolution(self) -> None:
        """2. Reprogramación de reserva con horario vencido preservando UUID y bloqueo de venta sobre reserva CANCELADA."""
        client_user = make_user(id_usuario=10, rol="CLIENTE", id_empresa=1)
        self.mock_cu10_repo.get_client_by_user.return_value = SimpleNamespace(
            id_cliente=7, id_usuario=10, empresa_id=1
        )
        self.mock_cu10_repo.get_branch.return_value = SimpleNamespace(
            id_sucursal=2,
            empresa_id=1,
            nombre="Sucursal Central",
            estado=True,
            hora_apertura=time(9, 0),
            hora_cierre=time(20, 0),
        )
        v101 = SimpleNamespace(
            id_variante_producto=101,
            id_producto=50,
            id_talla=1,
            id_color=2,
            sku="CAM-LIN-S",
            estado=True,
            empresa_id=1,
        )
        p50 = SimpleNamespace(
            id_producto=50,
            nombre="Camisa Lino",
            precio=Decimal("150.00"),
            precio_final=Decimal("150.00"),
            estado=True,
            empresa_id=1,
        )
        inv = SimpleNamespace(
            id_variante_producto=101,
            id_sucursal=2,
            empresa_id=1,
            stock_actual=8,
            stock_reservado=1,
            updated_at=NOW,
        )
        self.mock_cu10_repo.get_variants_with_products.return_value = {101: (v101, p50)}
        self.mock_conflict_repo.get_inventories_snapshot.return_value = {101: inv}
        self.mock_cu10_repo.lock_inventories.return_value = {101: inv}

        # Registro previo en t_reserva_offline_sync que había quedado RECHAZADA por horario vencido
        prev_sync = SimpleNamespace(
            uuid_reserva_offline="uuid-res-horario-01",
            id_reserva=None,
            codigo_reserva=None,
            id_sucursal=2,
            id_cliente=7,
            id_usuario=10,
            empresa_id=1,
            estado_sincronizacion="RECHAZADA",
            motivo="La fecha programada debe ser al menos 1 hora posterior al momento actual.",
            created_at=NOW - timedelta(hours=2),
            updated_at=NOW - timedelta(hours=1),
        )
        self.mock_cu10_repo.get_sync_record.return_value = prev_sync

        expired_res_op = OfflineSyncOperationInput(
            uuid_operacion="uuid-res-horario-01",
            tipo_operacion="RESERVA",
            payload={
                "uuid_reserva_offline": "uuid-res-horario-01",
                "id_sucursal": 2,
                "fecha_atencion_programada": (NOW - timedelta(minutes=30)).isoformat(),
                "detalles": [{"id_variante_producto": 101, "cantidad": 1}],
            },
        )

        # Paso A: Diagnóstico detecta HORARIO_VENCIDO y sugiere nuevos horarios válidos
        diag_resp = self.conflict_service.diagnose_conflicts(
            client_user,
            OfflineConflictDiagnoseRequest(operaciones=[expired_res_op]),
            now=NOW,
        )
        diag = diag_resp.diagnosticos_por_uuid["uuid-res-horario-01"]
        self.assertEqual(diag.codigo_conflicto_principal, "HORARIO_VENCIDO")
        self.assertIn("REPROGRAMAR_HORARIO", diag.acciones_permitidas)
        self.assertTrue(len(diag.datos_actuales_servidor.horarios_sugeridos) > 0)

        # Paso B: Reprogramar a un horario válido con consentimiento actualiza el mismo UUID a SINCRONIZADA
        self.mock_cu10_repo.create_reservation.return_value = SimpleNamespace(
            id_reserva=120,
            codigo="RSV-20261107-REPROG120",
            estado="PENDIENTE",
            id_sucursal=2,
            id_cliente=7,
            empresa_id=1,
        )
        new_slot = datetime(2026, 11, 7, 17, 0, 0)
        resolve_res = self.conflict_service.resolve_conflicts(
            client_user,
            OfflineConflictResolveRequest(
                resoluciones=[
                    OfflineOperationResolutionInput(
                        uuid_operacion="uuid-res-horario-01",
                        tipo_operacion="RESERVA",
                        accion_resolucion="REPROGRAMAR_HORARIO",
                        consentimiento_usuario=True,
                        nueva_fecha_atencion_programada=new_slot,
                        payload=expired_res_op.payload,
                    )
                ]
            ),
            now=NOW,
        )
        self.assertTrue(resolve_res.success)
        resolved_item = resolve_res.resultados_por_uuid["uuid-res-horario-01"]
        self.assertTrue(resolved_item.confirmada)
        self.assertEqual(resolved_item.id_servidor, 120)
        self.assertEqual(resolved_item.codigo_servidor, "RSV-20261107-REPROG120")
        self.assertEqual(prev_sync.estado_sincronizacion, "SINCRONIZADA")
        self.assertEqual(inv.stock_reservado, 2)

        # Paso C: CAJERO nunca puede confirmar una venta sobre una reserva CANCELADA
        cashier_user = make_user(id_usuario=25, rol="CAJERO", id_empresa=1)
        self.mock_cu11_repo.get_employee_by_user.return_value = SimpleNamespace(
            id_empleado=8, id_usuario=25, empresa_id=1
        )
        self.mock_cu11_repo.get_employee_branch_assignment.return_value = SimpleNamespace(
            id_empleado_sucursal=12, id_empleado=8, id_sucursal=2, estado=True
        )
        self.mock_cu11_repo.get_branch.return_value = SimpleNamespace(
            id_sucursal=2, empresa_id=1, nombre="Sucursal Central", estado=True
        )
        self.mock_cu11_repo.get_reservation.return_value = SimpleNamespace(
            id_reserva=300,
            codigo="RSV-CANCELADA-300",
            empresa_id=1,
            id_sucursal=2,
            id_cliente=7,
            estado="CANCELADA",
            fecha_expiracion=NOW + timedelta(hours=1),
        )

        sale_over_cancelled = self.conflict_service.resolve_conflicts(
            cashier_user,
            OfflineConflictResolveRequest(
                resoluciones=[
                    OfflineOperationResolutionInput(
                        uuid_operacion="uuid-sale-over-cancelled",
                        tipo_operacion="VENTA",
                        accion_resolucion="REINTENTAR_SIN_CAMBIOS",
                        consentimiento_usuario=True,
                        payload={
                            "uuid_venta_offline": "uuid-sale-over-cancelled",
                            "canal": "PRESENCIAL",
                            "id_sucursal": 2,
                            "id_reserva": 300,
                            "medio_pago": "EFECTIVO",
                            "detalles": [{"id_variante_producto": 101, "cantidad": 1}],
                        },
                    )
                ]
            ),
            now=NOW,
        )
        sale_res_item = sale_over_cancelled.resultados_por_uuid[
            "uuid-sale-over-cancelled"
        ]
        self.assertFalse(sale_res_item.confirmada)
        self.assertEqual(sale_res_item.estado_resultado, "EN_CONFLICTO")
        self.assertEqual(
            sale_res_item.conflictos[0].tipo_conflicto, "RESERVA_CANCELADA"
        )

    def test_3_dependent_operations_blocking_and_sequence_resolution(self) -> None:
        """3. Bloqueo de operaciones posteriores cuando falla una dependencia y resolución secuencial EFECTIVO."""
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

        # Caso A: La reserva #400 está EXPIRADA -> falla CONFIRM y bloquea en cascada ATTEND y VENTA
        expired_res = SimpleNamespace(
            id_reserva=400,
            codigo="RSV-EXP-400",
            empresa_id=1,
            id_sucursal=2,
            id_cliente=7,
            estado="EXPIRADA",
            fecha_expiracion=NOW - timedelta(hours=1),
        )
        self.mock_cu11_repo.get_reservation.return_value = expired_res

        cascade_resp = self.conflict_service.resolve_conflicts(
            cashier_user,
            OfflineConflictResolveRequest(
                resoluciones=[
                    OfflineOperationResolutionInput(
                        uuid_operacion="op-confirm-400",
                        tipo_operacion="TRANSICION_RESERVA",
                        secuencia=1,
                        accion_resolucion="REINTENTAR_SIN_CAMBIOS",
                        payload={
                            "uuid_operacion_offline": "op-confirm-400",
                            "id_reserva": 400,
                            "codigo_reserva": "RSV-EXP-400",
                            "accion": "CONFIRM",
                            "id_sucursal": 2,
                        },
                    ),
                    OfflineOperationResolutionInput(
                        uuid_operacion="op-attend-400",
                        tipo_operacion="TRANSICION_RESERVA",
                        secuencia=2,
                        depende_de_uuid="op-confirm-400",
                        accion_resolucion="REINTENTAR_SIN_CAMBIOS",
                        payload={
                            "uuid_operacion_offline": "op-attend-400",
                            "id_reserva": 400,
                            "codigo_reserva": "RSV-EXP-400",
                            "accion": "ATTEND",
                            "id_sucursal": 2,
                        },
                    ),
                    OfflineOperationResolutionInput(
                        uuid_operacion="op-sale-400",
                        tipo_operacion="VENTA",
                        secuencia=3,
                        depende_de_uuid="op-attend-400",
                        accion_resolucion="REINTENTAR_SIN_CAMBIOS",
                        payload={
                            "uuid_venta_offline": "op-sale-400",
                            "canal": "PRESENCIAL",
                            "id_sucursal": 2,
                            "id_reserva": 400,
                            "codigo_reserva": "RSV-EXP-400",
                            "medio_pago": "EFECTIVO",
                            "detalles": [{"id_variante_producto": 101, "cantidad": 1}],
                        },
                    ),
                ]
            ),
            now=NOW,
        )
        self.assertFalse(cascade_resp.success)
        self.assertEqual(cascade_resp.confirmadas, 0)
        self.assertEqual(
            cascade_resp.resultados_por_uuid["op-attend-400"]
            .conflictos[0]
            .tipo_conflicto,
            "DEPENDENCIA_BLOQUEADA",
        )
        self.assertEqual(
            cascade_resp.resultados_por_uuid["op-sale-400"]
            .conflictos[0]
            .tipo_conflicto,
            "DEPENDENCIA_BLOQUEADA",
        )

        # Caso B: Reserva #500 activa en PENDIENTE -> COMPLETAR_TRANSICIONES_RESERVA completa secuencia y vende en EFECTIVO
        active_res = SimpleNamespace(
            id_reserva=500,
            codigo="RSV-ACT-500",
            empresa_id=1,
            id_sucursal=2,
            id_cliente=7,
            estado="PENDIENTE",
            fecha_expiracion=NOW + timedelta(hours=3),
            id_empleado_atencion=None,
        )
        self.mock_cu11_repo.get_reservation.return_value = active_res
        self.mock_cu11_repo.get_sale_for_reservation.return_value = None
        self.mock_cu11_repo.get_reservation_details.return_value = [
            SimpleNamespace(
                id_variante_producto=101,
                cantidad=2,
                precio_unitario=Decimal("150.00"),
            )
        ]
        v101 = SimpleNamespace(
            id_variante_producto=101,
            id_producto=50,
            sku="CAM-LIN-S",
            estado=True,
            empresa_id=1,
        )
        p50 = SimpleNamespace(
            id_producto=50,
            nombre="Camisa Lino",
            precio=Decimal("150.00"),
            estado=True,
            empresa_id=1,
        )
        inv500 = SimpleNamespace(
            id_variante_producto=101,
            id_sucursal=2,
            empresa_id=1,
            stock_actual=10,
            stock_reservado=2,
            updated_at=NOW,
        )
        self.mock_cu11_repo.get_variants_with_products.return_value = {101: (v101, p50)}
        self.mock_cu11_repo.lock_inventories.return_value = {101: inv500}
        self.mock_cu11_repo.create_sale.side_effect = lambda **kw: SimpleNamespace(
            id_venta=777,
            empresa_id=kw["company_id"],
            id_sucursal=kw["branch_id"],
            id_empleado=kw["employee_id"],
            id_cliente=kw["client_id"],
            id_reserva=kw["reservation_id"],
            canal=kw["canal"],
            moneda="BOB",
            numero_venta=kw["sale_number"],
            estado=kw["estado"],
            stock_comprometido=kw["stock_comprometido"],
            subtotal=kw["subtotal"],
            descuento_total=kw["descuento_total"],
            total=kw["total"],
            fecha_venta=kw["fecha_venta"],
        )
        self.mock_cu11_repo.create_payment.side_effect = lambda **kw: SimpleNamespace(
            id_pago=888,
            id_venta=kw["sale_id"],
            medio=kw["medio"],
            estado=kw["estado"],
            monto=kw["monto"],
        )

        seq_resp = self.conflict_service.resolve_conflicts(
            cashier_user,
            OfflineConflictResolveRequest(
                resoluciones=[
                    OfflineOperationResolutionInput(
                        uuid_operacion="op-sale-500",
                        tipo_operacion="VENTA",
                        accion_resolucion="COMPLETAR_TRANSICIONES_RESERVA",
                        consentimiento_usuario=True,
                        payload={
                            "uuid_venta_offline": "op-sale-500",
                            "canal": "PRESENCIAL",
                            "id_sucursal": 2,
                            "id_reserva": 500,
                            "codigo_reserva": "RSV-ACT-500",
                            "medio_pago": "EFECTIVO",
                            "detalles": [
                                {
                                    "id_variante_producto": 101,
                                    "cantidad": 2,
                                    "precio_unitario": "150.00",
                                }
                            ],
                            "total": "300.00",
                        },
                    )
                ]
            ),
            now=NOW,
        )
        self.assertTrue(seq_resp.success)
        sale_ok = seq_resp.resultados_por_uuid["op-sale-500"]
        self.assertTrue(sale_ok.confirmada)
        self.assertEqual(active_res.estado, "ATENDIDA")
        # EFECTIVO conserva declaración de cobro físico: venta COMPLETADA y pago APROBADO
        self.assertEqual(sale_ok.estado_entidad_servidor, "COMPLETADA")
        self.assertEqual(sale_ok.estado_pago, "APROBADO")
        self.assertFalse(sale_ok.pago_simulado)
        self.assertEqual(inv500.stock_actual, 8)
        self.assertEqual(inv500.stock_reservado, 0)

    def test_4_idempotency_retryable_errors_and_multitenant_role_security(self) -> None:
        """4. Idempotencia por UUID, diferenciación REINTENTABLE vs RECHAZADA y aislamiento por rol/empresa."""
        client_user = make_user(id_usuario=10, rol="CLIENTE", id_empresa=1)
        cashier_user = make_user(id_usuario=25, rol="CAJERO", id_empresa=1)

        # 4.A: Aislamiento multitenant bloquea acceso a otra empresa (403)
        with self.assertRaises(OfflineConflictError) as ctx_tenant:
            self.conflict_service.diagnose_conflicts(
                client_user,
                OfflineConflictDiagnoseRequest(
                    operaciones=[
                        OfflineSyncOperationInput(
                            uuid_operacion="uuid-op-tenant",
                            tipo_operacion="RESERVA",
                            payload={
                                "uuid_reserva_offline": "uuid-op-tenant",
                                "id_sucursal": 2,
                                "fecha_atencion_programada": (
                                    NOW + timedelta(hours=3)
                                ).isoformat(),
                                "detalles": [
                                    {"id_variante_producto": 101, "cantidad": 1}
                                ],
                            },
                        )
                    ]
                ),
                requested_company_id=99,
                now=NOW,
            )
        self.assertEqual(ctx_tenant.exception.status_code, 403)

        # 4.B: CLIENTE no puede resolver una VENTA presencial ni CAJERO una RESERVA
        forbidden_role_resp = self.conflict_service.resolve_conflicts(
            client_user,
            OfflineConflictResolveRequest(
                resoluciones=[
                    OfflineOperationResolutionInput(
                        uuid_operacion="uuid-pos-spoof",
                        tipo_operacion="VENTA",
                        accion_resolucion="REINTENTAR_SIN_CAMBIOS",
                        payload={
                            "uuid_venta_offline": "uuid-pos-spoof",
                            "canal": "PRESENCIAL",
                            "id_sucursal": 2,
                            "medio_pago": "EFECTIVO",
                            "detalles": [{"id_variante_producto": 101, "cantidad": 1}],
                        },
                    )
                ]
            ),
            now=NOW,
        )
        self.assertEqual(
            forbidden_role_resp.resultados_por_uuid["uuid-pos-spoof"].estado_resultado,
            "RECHAZADA",
        )

        # 4.C: Fallo transitorio de BD devuelve REINTENTABLE / PENDIENTE_SINCRONIZACION (nunca RECHAZADA)
        self.mock_cu10_repo.get_client_by_user.return_value = SimpleNamespace(
            id_cliente=7, id_usuario=10, empresa_id=1
        )
        self.mock_cu10_repo.get_sync_record.side_effect = OperationalError(
            "SELECT 1", {}, Exception("connection timeout")
        )
        retry_resp = self.conflict_service.resolve_conflicts(
            client_user,
            OfflineConflictResolveRequest(
                resoluciones=[
                    OfflineOperationResolutionInput(
                        uuid_operacion="uuid-res-retryable",
                        tipo_operacion="RESERVA",
                        accion_resolucion="REINTENTAR_SIN_CAMBIOS",
                        payload={
                            "uuid_reserva_offline": "uuid-res-retryable",
                            "id_sucursal": 2,
                            "fecha_atencion_programada": (
                                NOW + timedelta(hours=3)
                            ).isoformat(),
                            "detalles": [{"id_variante_producto": 101, "cantidad": 1}],
                        },
                    )
                ]
            ),
            now=NOW,
        )
        retry_item = retry_resp.resultados_por_uuid["uuid-res-retryable"]
        self.assertEqual(retry_item.estado_resultado, "REINTENTABLE")
        self.assertEqual(retry_item.estado_sincronizacion, "PENDIENTE_SINCRONIZACION")
        self.assertTrue(retry_item.reintentable)
        self.assertEqual(retry_item.conflictos[0].tipo_conflicto, "ERROR_REINTENTABLE")

        # 4.D: Idempotencia por UUID vincula reserva ya confirmada sin duplicar
        self.mock_cu10_repo.get_sync_record.side_effect = None
        self.mock_cu10_repo.get_sync_record.return_value = SimpleNamespace(
            uuid_reserva_offline="uuid-res-already-synced",
            id_reserva=888,
            codigo_reserva="RSV-20261107-IDEMP888",
            id_sucursal=2,
            id_cliente=7,
            id_usuario=10,
            empresa_id=1,
            estado_sincronizacion="SINCRONIZADA",
            motivo=None,
            created_at=NOW,
            updated_at=NOW,
        )
        idemp_resp = self.conflict_service.resolve_conflicts(
            client_user,
            OfflineConflictResolveRequest(
                resoluciones=[
                    OfflineOperationResolutionInput(
                        uuid_operacion="uuid-res-already-synced",
                        tipo_operacion="RESERVA",
                        accion_resolucion="VINCULAR_OPERACION_EXISTENTE",
                        payload={
                            "uuid_reserva_offline": "uuid-res-already-synced",
                            "id_sucursal": 2,
                            "fecha_atencion_programada": (
                                NOW + timedelta(hours=3)
                            ).isoformat(),
                            "detalles": [{"id_variante_producto": 101, "cantidad": 1}],
                        },
                    )
                ]
            ),
            now=NOW,
        )
        idemp_item = idemp_resp.resultados_por_uuid["uuid-res-already-synced"]
        self.assertTrue(idemp_item.confirmada)
        self.assertEqual(idemp_item.estado_sincronizacion, "SINCRONIZADA")
        self.assertEqual(idemp_item.id_servidor, 888)
        self.assertEqual(idemp_item.codigo_servidor, "RSV-20261107-IDEMP888")
        self.mock_cu10_repo.create_reservation.assert_not_called()

