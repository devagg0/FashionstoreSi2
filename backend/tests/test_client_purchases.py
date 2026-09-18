"""CU23: consultas reales en SQLite aislado; nunca conecta servicios externos."""
import asyncio
import json
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from sqlalchemy import Column, MetaData, Table, create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models
from app.core.database import get_db
from app.models.branch import Branch
from app.models.client import Client
from app.models.color import Color
from app.models.payment import Payment
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.sale import Sale
from app.models.sale_detail import SaleDetail
from app.models.size import Size
from app.repositories.client_purchases import returns, refunds
from app.routers import client_purchases as routes
from app.routers.client_reservations import require_client
from app.services.client_cart import CartAccessError, CartNotFoundError
from app.services.client_purchases import ClientPurchasesService
from app.services.auth_service import InactiveAccountError, InvalidAccessTokenError


def request(app, path, token=False):
    messages = []
    path, _, query = path.partition('?')
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}
    async def send(message):
        messages.append(message)
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET",
        "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": query.encode(),
        "root_path": "", "server": ("test", 80), "client": ("test", 1),
        "headers": [(b"authorization", b"Bearer fake")] if token else []}
    asyncio.run(app(scope, receive, send))
    return next(m['status'] for m in messages if m['type'] == 'http.response.start'), json.loads(
        b''.join(m.get('body', b'') for m in messages if m['type'] == 'http.response.body'))


class ClientPurchaseTests(TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={"check_same_thread": False})
        for model in (Client, Branch, Product, Size, Color, ProductVariant, Sale, SaleDetail, Payment):
            model.__table__.create(self.engine)
        metadata = MetaData()
        # DDL exclusivamente SQLite en memoria para las proyecciones de consulta.
        self.return_table = Table(returns.name, metadata, *(Column(c.name, c.type) for c in returns.c))
        self.refund_table = Table(refunds.name, metadata, *(Column(c.name, c.type) for c in refunds.c))
        metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.now = datetime(2026, 9, 17, 12)
        self.db.add_all([Client(id_cliente=7, id_usuario=12), Client(id_cliente=8, id_usuario=13),
            Client(id_cliente=9, id_usuario=14), Branch(id_sucursal=2, id_ciudad=1, nombre='Centro', direccion='Calle A'),
            Product(id_producto=4, id_categoria=1, nombre='Camisa', seccion='UNISEX', precio=999, estado=False),
            Size(id_talla=1, nombre='M'), Color(id_color=1, nombre='Blanco'),
            ProductVariant(id_variante_producto=3, id_producto=4, id_talla=1, id_color=1, sku='TEST', estado=False)])
        for sale_id, owner, canal, state, when in ((1,7,'DIGITAL','COMPLETADA',self.now),
                (2,7,'PRESENCIAL','PENDIENTE',self.now+timedelta(days=1)),
                (3,8,'DIGITAL','COMPLETADA',self.now+timedelta(days=2))):
            self.db.add(Sale(id_venta=sale_id, numero_venta=f'VTA-{sale_id}', id_sucursal=2,
                id_empleado=5 if canal=='PRESENCIAL' else None, id_cliente=owner, canal=canal,
                estado=state, subtotal=24, descuento_total=4, total=20, moneda='BOB', fecha_venta=when,
                fecha_completada=when if state=='COMPLETADA' else None))
            self.db.add(SaleDetail(id_venta=sale_id, id_variante_producto=3, cantidad=2,
                precio_unitario=12, descuento_unitario=2, subtotal_linea=20))
        self.db.add_all([Payment(id_pago=1,id_venta=1,medio='TARJETA',proveedor='STRIPE',entorno='TEST',estado='APROBADO',
                monto=20,moneda='BOB',referencia_externa='cs_test_private',clave_idempotencia=uuid4(),fecha_aprobacion=self.now,created_at=self.now),
            Payment(id_pago=2,id_venta=2,medio='QR',proveedor='MANUAL',entorno='LOCAL',estado='PENDIENTE',
                monto=20,moneda='BOB',clave_idempotencia=uuid4(),created_at=self.now)])
        self.db.commit()
        self.service = ClientPurchasesService(self.db)
        self.app = FastAPI()
        self.app.include_router(routes.router)
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.app.dependency_overrides[require_client] = lambda: NS(id_usuario=12,rol='CLIENTE')

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_client_history_only_owned_and_newest_first(self):
        data = self.service.list(12)
        self.assertEqual([s.id_venta for s in data.items], [2,1])
        self.assertEqual(data.total,2)
        self.assertEqual(data.items[0].sucursal.nombre,'Centro')
        self.assertEqual(data.items[1].numero_venta,'VTA-1')

    def test_client_without_purchases(self):
        self.assertEqual(self.service.list(14).items,[])
        self.assertEqual(self.service.list(14).total,0)

    def test_client_id_query_cannot_override_authenticated_owner(self):
        status, body = request(self.app, '/api/client/purchases?id_cliente=8')
        self.assertEqual(status, 200)
        self.assertEqual([sale['id_venta'] for sale in body['data']['items']], [2, 1])

    def test_same_date_has_stable_order_for_pagination(self):
        self.db.get(Sale, 2).fecha_venta = self.now
        self.db.commit()
        self.assertEqual([s.id_venta for s in self.service.list(12).items], [2, 1])
        self.assertEqual(self.service.list(12, limit=1, offset=1).items[0].id_venta, 1)

    def test_detail_historical_prices_and_inactive_catalog(self):
        data = self.service.detail(12,1)
        item = data.productos[0]
        self.assertEqual((item.nombre,item.talla,item.color,item.cantidad),('Camisa','M','Blanco',2))
        self.assertEqual((item.precio_unitario,item.descuento_unitario,item.subtotal_linea),
            (Decimal('12.00'),Decimal('2.00'),Decimal('20.00')))
        self.assertEqual((data.subtotal,data.descuento_total,data.total),(24,4,20))

    def test_foreign_and_nonexistent_same_not_found(self):
        for sale_id in (3,99):
            with self.assertRaises(CartNotFoundError):
                self.service.detail(12,sale_id)
            status,body = request(self.app,f'/api/client/purchases/{sale_id}')
            self.assertEqual(status,404)
            self.assertEqual(body['message'],'Compra no encontrada')

    def test_digital_approved_payment(self):
        data = self.service.detail(12,1)
        self.assertEqual((data.canal,data.estado,data.pago.medio,data.pago.estado),('DIGITAL','COMPLETADA','TARJETA','APROBADO'))
        self.assertEqual(len(data.pagos),1)

    def test_presencial_pending_payment(self):
        data = self.service.detail(12,2)
        self.assertEqual((data.canal,data.estado,data.pago.medio,data.pago.estado),('PRESENCIAL','PENDIENTE','QR','PENDIENTE'))
        self.assertEqual(data.devoluciones, [])
        self.assertEqual(data.reembolsos, [])

    def test_purchase_without_payment(self):
        self.db.delete(self.db.get(Payment,2)); self.db.commit()
        self.assertIsNone(self.service.detail(12,2).pago)
        self.assertEqual(self.service.detail(12,2).pagos,[])

    def test_return_and_refund_safe_public_data(self):
        self.db.execute(self.return_table.insert().values(id_devolucion=5,id_venta=1,tipo='DEVOLUCION',
            estado='PROCESADA',motivo='Talla incorrecta',created_at=self.now,fecha_resolucion=self.now,fecha_procesamiento=self.now))
        self.db.execute(self.refund_table.insert().values(id_reembolso=6,id_venta=1,id_pago=1,id_devolucion=5,
            estado='APROBADO',monto=10,created_at=self.now,fecha_aprobacion=self.now))
        self.db.execute(self.return_table.insert().values(id_devolucion=7,id_venta=3,tipo='DEVOLUCION',
            estado='SOLICITADA',motivo='Ajena',created_at=self.now))
        self.db.commit()
        status,body=request(self.app,'/api/client/purchases/1')
        self.assertEqual(status,200)
        self.assertEqual(body['data']['devoluciones'][0]['id_devolucion'],5)
        self.assertEqual(body['data']['reembolsos'][0]['monto'],'10.00')
        self.assertEqual(len(body['data']['devoluciones']),1)

    def test_no_sensitive_or_internal_fields(self):
        status,body=request(self.app,'/api/client/purchases/1')
        self.assertEqual(status,200)
        encoded=json.dumps(body)
        for field in ('referencia_externa','clave_idempotencia','client_secret','id_cliente','id_empleado','cs_test_private'):
            self.assertNotIn(field,encoded)
        self.assertEqual(set(body['data']['pago']),{'id_pago','medio','estado','monto','moneda','fecha_aprobacion'})

    def test_filters_and_pagination(self):
        status,body=request(self.app,'/api/client/purchases?estado=COMPLETADA&canal=DIGITAL&limit=1&offset=0')
        self.assertEqual(status,200)
        self.assertEqual([s['id_venta'] for s in body['data']['items']],[1])
        self.assertEqual(body['data']['total'],1)
        self.assertEqual(self.service.list(12,limit=1,offset=1).items[0].id_venta,1)
        self.assertEqual(self.service.list(12,estado='ANULADA').items,[])

    def test_invalid_filters_and_ids(self):
        for path in ('?estado=BAD','?canal=BAD','?limit=0','?limit=101','?offset=-1','/0','/-1','/2147483648'):
            with self.subTest(path=path):
                self.assertEqual(request(self.app,'/api/client/purchases'+path)[0],422)

    def test_missing_client_profile(self):
        with self.assertRaises(CartAccessError): self.service.list(99)
        self.app.dependency_overrides[require_client]=lambda:NS(id_usuario=99,rol='CLIENTE')
        self.assertEqual(request(self.app,'/api/client/purchases')[0],403)

    def test_readonly_selects_no_commit_or_flush(self):
        statements=[]
        event.listen(self.engine,'before_cursor_execute',lambda conn,cursor,statement,params,context,many: statements.append(statement))
        with patch.object(self.db,'commit',side_effect=AssertionError('write')), patch.object(self.db,'flush',side_effect=AssertionError('write')):
            # Production get_db uses autoflush=False; disable it here as well.
            self.db.autoflush=False
            self.service.list(12)
            self.service.detail(12,1)
        self.assertTrue(all(s.lstrip().upper().startswith('SELECT') for s in statements))
        self.assertTrue(statements)

    def test_multiple_attempts_latest_payment_no_duplicate_sales(self):
        self.db.delete(self.db.get(Payment,2)); self.db.commit()
        self.db.add_all([Payment(id_pago=i,id_venta=2,medio='QR',proveedor='MANUAL',entorno='LOCAL',estado=state,
            monto=20,moneda='BOB',clave_idempotencia=uuid4(),created_at=self.now+timedelta(minutes=i)) for i,state in ((4,'RECHAZADO'),(5,'PENDIENTE'))])
        self.db.commit()
        data=self.service.detail(12,2)
        self.assertEqual(data.pago.id_pago,5)
        self.assertEqual([p.id_pago for p in data.pagos],[5,4])
        self.assertEqual(self.service.list(12).total,2)

    def test_auth_required_role_and_inactive_account(self):
        self.app.dependency_overrides.pop(require_client)
        for path in ('/api/client/purchases','/api/client/purchases/1'):
            self.assertEqual(request(self.app,path)[0],401)
            with patch('app.routers.client_reservations.AuthService') as factory:
                factory.return_value.get_current_user.return_value=NS(id_usuario=12,rol='CAJERO')
                self.assertEqual(request(self.app,path,True)[0],403)
                for error,status in ((InactiveAccountError(),403),(InvalidAccessTokenError(),401)):
                    factory.return_value.get_current_user.side_effect=error
                    self.assertEqual(request(self.app,path,True)[0],status)

    def test_backend_error_sanitized(self):
        with patch.object(ClientPurchasesService,'list',side_effect=RuntimeError('sensitive trace')):
            status,body=request(self.app,'/api/client/purchases')
        self.assertEqual(status,500)
        self.assertNotIn('sensitive',json.dumps(body))
