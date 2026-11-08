"""Pruebas focalizadas para PK09 - CU15: Solicitar cambio o devolucion de prenda."""
import json
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models
from app.models.branch import Branch
from app.models.branch_inventory import BranchInventory
from app.models.client import Client
from app.models.color import Color
from app.models.inventory_movement import InventoryMovement
from app.models.inventory_movement_detail import InventoryMovementDetail
from app.models.payment import Payment
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.reservation import Reservation
from app.models.reservation_detail import ReservationDetail
from app.models.returns import Refund, Return, ReturnDetail
from app.models.sale import Sale
from app.models.sale_detail import SaleDetail
from app.models.size import Size
from app.routers import returns as returns_router
from app.schemas.returns import ExchangeRequest, ProcessRequest, ReturnRequest, ReviewRequest
from app.services.payments import PaymentsService
from app.services.returns import ReturnsService


def _unwrap(resp):
    if isinstance(resp, JSONResponse):
        return resp.status_code, json.loads(resp.body.decode())
    return 200, resp.model_dump(mode="json")


class TestPK09CU15ExchangeReturnRequest(TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        for model in (
            Client,
            Branch,
            Product,
            Size,
            Color,
            ProductVariant,
            Reservation,
            ReservationDetail,
            Sale,
            SaleDetail,
            BranchInventory,
            InventoryMovement,
            InventoryMovementDetail,
            Payment,
            Return,
            ReturnDetail,
            Refund,
        ):
            model.__table__.create(self.engine)

        self.db = Session(self.engine)
        self.db.autoflush = False
        self.now = PaymentsService.now()

        # Clientes y sucursal (empresa_id = 1)
        self.db.add_all(
            [
                Client(id_cliente=7, id_usuario=12, empresa_id=1),
                Client(id_cliente=8, id_usuario=13, empresa_id=1),
                Branch(
                    id_sucursal=2,
                    id_ciudad=1,
                    empresa_id=1,
                    nombre="Sucursal Centro",
                    direccion="Av. Principal 123",
                    telefono="70000000",
                ),
            ]
        )

        # Catalogo: tallas, colores, productos y variantes
        self.db.add_all(
            [
                Size(id_talla=1, empresa_id=1, nombre="S", estado=True),
                Size(id_talla=2, empresa_id=1, nombre="M", estado=True),
                Size(id_talla=3, empresa_id=1, nombre="L", estado=True),
                Color(id_color=1, empresa_id=1, nombre="Negro", codigo_hex="#000000", estado=True),
                Color(id_color=2, empresa_id=1, nombre="Azul", codigo_hex="#0000FF", estado=True),
                Product(
                    id_producto=10,
                    id_categoria=1,
                    empresa_id=1,
                    nombre="Chaqueta Denim",
                    seccion="UNISEX",
                    precio=Decimal("100.00"),
                    estado=True,
                ),
                Product(
                    id_producto=11,
                    id_categoria=1,
                    empresa_id=1,
                    nombre="Abrigo Premium",
                    seccion="UNISEX",
                    precio=Decimal("110.00"),
                    estado=True,
                ),
                Product(
                    id_producto=12,
                    id_categoria=1,
                    empresa_id=1,
                    nombre="Polera Clasica",
                    seccion="UNISEX",
                    precio=Decimal("80.00"),
                    estado=True,
                ),
                Product(
                    id_producto=13,
                    id_categoria=1,
                    empresa_id=1,
                    nombre="Camiseta Basica",
                    seccion="UNISEX",
                    precio=Decimal("65.00"),
                    estado=True,
                ),
            ]
        )
        self.db.add_all(
            [
                ProductVariant(
                    id_variante_producto=101,
                    id_producto=10,
                    id_talla=1,
                    id_color=1,
                    empresa_id=1,
                    sku="CHQ-S-NEG",
                    estado=True,
                ),
                ProductVariant(
                    id_variante_producto=102,
                    id_producto=10,
                    id_talla=2,
                    id_color=2,
                    empresa_id=1,
                    sku="CHQ-M-AZU",
                    estado=True,
                ),
                ProductVariant(
                    id_variante_producto=201,
                    id_producto=11,
                    id_talla=2,
                    id_color=1,
                    empresa_id=1,
                    sku="ABR-M-NEG",
                    estado=True,
                ),
                ProductVariant(
                    id_variante_producto=301,
                    id_producto=12,
                    id_talla=2,
                    id_color=1,
                    empresa_id=1,
                    sku="POL-M-NEG",
                    estado=True,
                ),
                ProductVariant(
                    id_variante_producto=401,
                    id_producto=13,
                    id_talla=3,
                    id_color=2,
                    empresa_id=1,
                    sku="CAM-L-AZU",
                    estado=True,
                ),
                ProductVariant(
                    id_variante_producto=501,
                    id_producto=11,
                    id_talla=3,
                    id_color=1,
                    empresa_id=1,
                    sku="ABR-L-SIN-STOCK",
                    estado=True,
                ),
            ]
        )

        # Inventario en sucursal 2
        self.db.add_all(
            [
                BranchInventory(
                    id_sucursal=2,
                    id_variante_producto=101,
                    empresa_id=1,
                    stock_actual=10,
                    stock_reservado=2,
                    stock_minimo=1,
                ),
                BranchInventory(
                    id_sucursal=2,
                    id_variante_producto=102,
                    empresa_id=1,
                    stock_actual=8,
                    stock_reservado=1,
                    stock_minimo=1,
                ),
                BranchInventory(
                    id_sucursal=2,
                    id_variante_producto=201,
                    empresa_id=1,
                    stock_actual=6,
                    stock_reservado=1,
                    stock_minimo=1,
                ),
                BranchInventory(
                    id_sucursal=2,
                    id_variante_producto=301,
                    empresa_id=1,
                    stock_actual=5,
                    stock_reservado=0,
                    stock_minimo=1,
                ),
                BranchInventory(
                    id_sucursal=2,
                    id_variante_producto=401,
                    empresa_id=1,
                    stock_actual=4,
                    stock_reservado=1,
                    stock_minimo=1,
                ),
                BranchInventory(
                    id_sucursal=2,
                    id_variante_producto=501,
                    empresa_id=1,
                    stock_actual=2,
                    stock_reservado=2,
                    stock_minimo=1,
                ),
            ]
        )

        # Venta COMPLETADA hace 2 horas: 3 unidades de variante 101
        # Precio unitario 100.00, descuento unitario 20.00 -> pagado 80.00 c/u (total 240.00)
        completed_time = self.now - timedelta(hours=2)
        self.db.add(
            Sale(
                id_venta=1,
                empresa_id=1,
                numero_venta="VTA-CU15-001",
                id_sucursal=2,
                id_empleado=5,
                id_cliente=7,
                canal="PRESENCIAL",
                moneda="BOB",
                estado="COMPLETADA",
                subtotal=Decimal("240.00"),
                descuento_total=Decimal("0.00"),
                total=Decimal("240.00"),
                stock_comprometido=False,
                fecha_venta=completed_time - timedelta(minutes=10),
                fecha_completada=completed_time,
                created_at=completed_time,
                updated_at=completed_time,
            )
        )
        self.db.add(
            SaleDetail(
                id_detalle_venta=1,
                empresa_id=1,
                id_venta=1,
                id_variante_producto=101,
                cantidad=3,
                precio_unitario=Decimal("100.00"),
                descuento_unitario=Decimal("20.00"),
                subtotal_linea=Decimal("240.00"),
            )
        )
        self.db.add(
            Payment(
                id_pago=1,
                empresa_id=1,
                id_venta=1,
                medio="EFECTIVO",
                proveedor="MANUAL",
                entorno="LOCAL",
                estado="APROBADO",
                monto=Decimal("240.00"),
                moneda="BOB",
                clave_idempotencia=uuid4(),
                fecha_aprobacion=completed_time,
                created_at=completed_time,
                updated_at=completed_time,
            )
        )
        self.db.add(
            InventoryMovement(
                id_movimiento_inventario=1,
                empresa_id=1,
                id_venta=1,
                id_sucursal_origen=2,
                id_sucursal_destino=None,
                id_empleado_sucursal=8,
                tipo_movimiento="VENTA",
                estado="CONFIRMADO",
            )
        )
        self.db.add(
            InventoryMovementDetail(
                id_movimiento_inventario=1,
                empresa_id=1,
                id_variante_producto=101,
                cantidad=3,
            )
        )
        self.db.commit()

        self.current_user = NS(id_usuario=12, rol="CLIENTE", empresa_id=1)
        self.staff_user = NS(id_usuario=11, rol="CAJERO", empresa_id=1)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_1_plazo_72_horas_y_registro_inicial_sin_modalidad(self):
        """Valida ventana de 72 horas y registro inicial sin obligatoriedad de modalidad de entrega."""
        status, body = _unwrap(
            returns_router.get_exchange_options(1, self.current_user, self.db)
        )
        self.assertEqual(status, 200)
        data = body["data"]
        self.assertTrue(data["dentro_plazo_72h"])
        self.assertTrue(data["elegible_cambio_devolucion"])
        self.assertEqual(data["plazo_horas"], 72)
        self.assertGreater(data["horas_restantes"], 69.0)
        self.assertTrue(data.get("modalidad_entrega_pendiente"))

        # Registro inicial de CAMBIO sin indicar modalidad_entrega (queda None/pendiente hasta CU16)
        st_cam, body_cam = _unwrap(
            returns_router.request_exchange(
                1,
                ExchangeRequest(
                    motivo="Cambio inicial por otra talla",
                    lineas=[{"id_detalle_venta": 1, "cantidad": 1, "id_variante_reemplazo": 102}],
                ),
                self.current_user,
                uuid4(),
                self.db,
            )
        )
        self.assertEqual(st_cam, 200)
        d_cam = body_cam["data"]
        self.assertEqual(d_cam["tipo"], "CAMBIO")
        self.assertEqual(d_cam["estado"], "SOLICITADA")
        self.assertIsNone(d_cam["modalidad_entrega"])

        # Rechazar solicitud previa para liberar la linea para la prueba de DEVOLUCION
        row_cam = self.db.get(Return, d_cam["id_devolucion"])
        row_cam.estado = "RECHAZADA"
        row_cam.id_usuario_resolutor = 11
        row_cam.fecha_resolucion = PaymentsService.now()
        self.db.commit()

        # Registro inicial de DEVOLUCION sin indicar modalidad_entrega
        st_dev, body_dev = _unwrap(
            returns_router.request_return(
                1,
                ReturnRequest(
                    motivo="Devolución inicial",
                    lineas=[{"id_detalle_venta": 1, "cantidad": 1}],
                ),
                self.current_user,
                uuid4(),
                self.db,
            )
        )
        self.assertEqual(st_dev, 200)
        d_dev = body_dev["data"]
        self.assertEqual(d_dev["tipo"], "DEVOLUCION")
        self.assertEqual(d_dev["estado"], "SOLICITADA")
        self.assertIsNone(d_dev["modalidad_entrega"])

        # Vencer el plazo de 72 horas (72h + 1 minuto atras) en venta 2
        sale = self.db.get(Sale, 1)
        expired_time = PaymentsService.now() - timedelta(hours=72, minutes=1)
        sale.fecha_venta = expired_time - timedelta(minutes=5)
        sale.fecha_completada = expired_time
        self.db.commit()

        # Intento fuera de las 72h -> 409
        status_expired, body_expired = _unwrap(
            returns_router.request_return(
                1,
                ReturnRequest(motivo="Fuera de plazo", lineas=[{"id_detalle_venta": 1, "cantidad": 1}]),
                self.current_user,
                uuid4(),
                self.db,
            )
        )
        self.assertEqual(status_expired, 409)
        self.assertIn("72 horas", body_expired["message"])

        # exchange-options refleja que el plazo vencio
        _, opts_expired = _unwrap(
            returns_router.get_exchange_options(1, self.current_user, self.db)
        )
        self.assertFalse(opts_expired["data"]["dentro_plazo_72h"])
        self.assertFalse(opts_expired["data"]["elegible_cambio_devolucion"])

    def test_2_cambio_talla_color_producto_diferencia_precios_y_stock_sin_descontar(self):
        """Valida CAMBIO con calculo de diferencia (mas caro, igual, mas barato) sin tocar stock ni cobrar/reembolsar."""
        # Misma variante original -> 422
        st_same, _ = _unwrap(
            returns_router.request_exchange(
                1,
                ExchangeRequest(
                    motivo="Misma variante",
                    lineas=[{"id_detalle_venta": 1, "cantidad": 1, "id_variante_reemplazo": 101}],
                ),
                self.current_user,
                uuid4(),
                self.db,
            )
        )
        self.assertEqual(st_same, 422)

        # Variante sin stock disponible -> 409
        st_nostock, _ = _unwrap(
            returns_router.request_exchange(
                1,
                ExchangeRequest(
                    motivo="Variante agotada",
                    lineas=[{"id_detalle_venta": 1, "cantidad": 1, "id_variante_reemplazo": 501}],
                ),
                self.current_user,
                uuid4(),
                self.db,
            )
        )
        self.assertEqual(st_nostock, 409)

        # Caso A: Reemplazo mas caro (Variante 201 = Bs 110.00 vs Bs 80.00 reconocido con descuento -> +30.00 adicional)
        st_more, body_more = _unwrap(
            returns_router.request_exchange(
                1,
                ExchangeRequest(
                    motivo="Cambio por abrigo mas caro",
                    lineas=[{"id_detalle_venta": 1, "cantidad": 1, "id_variante_reemplazo": 201}],
                ),
                self.current_user,
                uuid4(),
                self.db,
            )
        )
        self.assertEqual(st_more, 200)
        d_more = body_more["data"]
        self.assertEqual(d_more["tipo"], "CAMBIO")
        self.assertEqual(d_more["estado"], "SOLICITADA")
        self.assertEqual(Decimal(str(d_more["diferencia_precio_estimada"])), Decimal("30.00"))
        self.assertEqual(Decimal(str(d_more["importe_adicional_estimado"])), Decimal("30.00"))
        self.assertEqual(Decimal(str(d_more["saldo_a_favor_estimado"])), Decimal("0.00"))
        self.assertEqual(d_more["resumen_economico"]["resultado_economico"], "IMPORTE_ADICIONAL")
        self.assertEqual(d_more["reembolsos"], [])

        # Rechazar la anterior para probar los siguientes escenarios de precio sobre la misma linea
        row_more = self.db.get(Return, d_more["id_devolucion"])
        row_more.estado = "RECHAZADA"
        row_more.id_usuario_resolutor = 11
        row_more.fecha_resolucion = PaymentsService.now()
        self.db.commit()

        # Caso B: Reemplazo de igual valor al precio neto pagado (Variante 301 = Bs 80.00 vs Bs 80.00 -> 0.00)
        st_eq, body_eq = _unwrap(
            returns_router.request_return(
                1,
                ReturnRequest(
                    tipo="CAMBIO",
                    motivo="Cambio por prenda de igual valor neto",
                    lineas=[{"id_detalle_venta": 1, "cantidad": 1, "id_variante_reemplazo": 301}],
                ),
                self.current_user,
                uuid4(),
                self.db,
            )
        )
        self.assertEqual(st_eq, 200)
        d_equal = body_eq["data"]
        self.assertEqual(Decimal(str(d_equal["diferencia_precio_estimada"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(d_equal["importe_adicional_estimado"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(d_equal["saldo_a_favor_estimado"])), Decimal("0.00"))
        self.assertEqual(d_equal["resumen_economico"]["resultado_economico"], "SIN_DIFERENCIA")

        row_eq = self.db.get(Return, d_equal["id_devolucion"])
        row_eq.estado = "RECHAZADA"
        row_eq.id_usuario_resolutor = 11
        row_eq.fecha_resolucion = PaymentsService.now()
        self.db.commit()

        # Caso C: Reemplazo mas barato (Variante 401 = Bs 65.00 vs Bs 80.00 -> -15.00, saldo a favor 15.00)
        st_cheap, body_cheap = _unwrap(
            returns_router.request_exchange(
                1,
                ExchangeRequest(
                    motivo="Cambio por prenda mas economica",
                    lineas=[{"id_detalle_venta": 1, "cantidad": 1, "id_variante_reemplazo": 401}],
                ),
                self.current_user,
                uuid4(),
                self.db,
            )
        )
        self.assertEqual(st_cheap, 200)
        d_cheap = body_cheap["data"]
        self.assertEqual(Decimal(str(d_cheap["diferencia_precio_estimada"])), Decimal("-15.00"))
        self.assertEqual(Decimal(str(d_cheap["importe_adicional_estimado"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(d_cheap["saldo_a_favor_estimado"])), Decimal("15.00"))
        self.assertEqual(d_cheap["resumen_economico"]["resultado_economico"], "SALDO_A_FAVOR")

        # Verificar que el inventario de todas las variantes permanece intacto (sin reservar ni descontar)
        inv_101 = self.db.scalar(select(BranchInventory).where(BranchInventory.id_variante_producto == 101))
        inv_201 = self.db.scalar(select(BranchInventory).where(BranchInventory.id_variante_producto == 201))
        inv_401 = self.db.scalar(select(BranchInventory).where(BranchInventory.id_variante_producto == 401))
        self.assertEqual((inv_101.stock_actual, inv_101.stock_reservado), (10, 2))
        self.assertEqual((inv_201.stock_actual, inv_201.stock_reservado), (6, 1))
        self.assertEqual((inv_401.stock_actual, inv_401.stock_reservado), (4, 1))

    def test_3_visibilidad_cajero_seguridad_multitenant_idempotencia_y_compatibilidad(self):
        """Valida visibilidad para CAJERO sin procesar, seguridad multitenant, idempotencia y compatibilidad CU24."""
        req_min = ReturnRequest(motivo="Ajena", lineas=[{"id_detalle_venta": 1, "cantidad": 1}])

        # 1. Seguridad multitenant: otro cliente -> 404, otra empresa -> 404
        other_client = NS(id_usuario=13, rol="CLIENTE", empresa_id=1)
        st_other, _ = _unwrap(
            returns_router.request_return(1, req_min, other_client, uuid4(), self.db)
        )
        self.assertEqual(st_other, 404)

        other_tenant = NS(id_usuario=12, rol="CLIENTE", empresa_id=2)
        st_tenant, _ = _unwrap(
            returns_router.request_return(1, req_min, other_tenant, uuid4(), self.db)
        )
        self.assertEqual(st_tenant, 404)

        # 2. Cliente registra solicitud válida con idempotencia
        idem_key = uuid4()
        payload = ReturnRequest(
            tipo="CAMBIO",
            motivo="Cambio talla M sin modalidad inicial",
            lineas=[{"id_detalle_venta": 1, "cantidad": 2, "id_variante_reemplazo": 102}],
        )
        st_first, first = _unwrap(
            returns_router.request_return(1, payload, self.current_user, idem_key, self.db)
        )
        self.assertEqual(st_first, 200)
        created_id = first["data"]["id_devolucion"]

        # Reintento con misma clave de idempotencia devuelve la misma solicitud
        st_retry, retry = _unwrap(
            returns_router.request_return(1, payload, self.current_user, idem_key, self.db)
        )
        self.assertEqual(st_retry, 200)
        self.assertEqual(retry["data"]["id_devolucion"], created_id)

        # Validar rechazo de cantidad excesiva (disponible es 1, solicita 2) -> 422
        excess_payload = ReturnRequest(
            tipo="DEVOLUCION",
            motivo="Cantidad excesiva",
            lineas=[{"id_detalle_venta": 1, "cantidad": 2}],
        )
        st_excess, body_excess = _unwrap(
            returns_router.request_return(1, excess_payload, self.current_user, uuid4(), self.db)
        )
        self.assertEqual(st_excess, 422)
        self.assertIn("supera las unidades disponibles", body_excess["message"])

        # Validar conflicto de idempotencia (misma clave con payload diferente) -> 409
        diff_payload = ReturnRequest(
            tipo="CAMBIO",
            motivo="Diferente motivo",
            lineas=[{"id_detalle_venta": 1, "cantidad": 1, "id_variante_reemplazo": 102}],
        )
        st_conflict, body_conflict = _unwrap(
            returns_router.request_return(1, diff_payload, self.current_user, idem_key, self.db)
        )
        self.assertEqual(st_conflict, 409)
        self.assertIn("idempotencia", body_conflict["message"].lower())

        # 3. Visibilidad para CAJERO en GET /api/staff/returns en estado SOLICITADA
        with patch.object(ReturnsService, "_assignment", return_value=8), patch(
            "app.repositories.staff_sales.StaffSalesRepository.get_employee",
            return_value=NS(id_empleado=5),
        ), patch(
            "app.repositories.staff_sales.StaffSalesRepository.branches",
            return_value=[{"id_sucursal": 2, "id_empleado_sucursal": 8}],
        ):
            st_staff, staff_list = _unwrap(
                returns_router.list_returns(
                    self.staff_user,
                    self.db,
                    estado="SOLICITADA",
                )
            )
            self.assertEqual(st_staff, 200)
            items = staff_list["data"]
            found = next((x for x in items if x["id_devolucion"] == created_id), None)
            self.assertIsNotNone(found)
            self.assertEqual(found["estado"], "SOLICITADA")
            self.assertIsNone(found["modalidad_entrega"])
            # Sin movimientos de inventario, reembolsos ni pagos procesados todavia
            self.assertIsNone(found["id_movimiento_inventario"])
            self.assertEqual(found["reembolsos"], [])

            # 4. Compatibilidad con flujo de resolución y procesamiento posterior (CU24)
            st_rev, rev = _unwrap(
                returns_router.review(
                    created_id,
                    ReviewRequest(
                        resultado="APROBADA",
                        lineas=[
                            {
                                "id_variante_producto": 101,
                                "cantidad_reintegrar": 0,
                                "importe_restitucion": Decimal("0.00"),
                            }
                        ],
                    ),
                    self.staff_user,
                    self.db,
                )
            )
            self.assertEqual(st_rev, 200)
            self.assertEqual(rev["data"]["estado"], "APROBADA")
