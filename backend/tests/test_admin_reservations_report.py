"""CU30: ASGI, agregaciones reales SQLite y SQL PostgreSQL."""
import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from fastapi import FastAPI
from sqlalchemy import create_engine, event, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import get_db
from app.models.branch import Branch
from app.models.category import Category
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.reservation import Reservation
from app.models.reservation_detail import ReservationDetail
from app.routers.admin_reservations_report import router
from app.schemas.admin_reservations_report import STATES, ReservationsReportFilters
from app.services.admin_reservations_report import AdminReservationsReportService
from app.services.auth_service import InactiveAccountError, InvalidAccessTokenError

ROUTE = "/api/admin/reservations-report"


def request(app, query="", token=True):
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "GET", "scheme": "http", "path": ROUTE,
        "raw_path": ROUTE.encode(), "query_string": query.encode(),
        "root_path": "", "server": ("test", 80), "client": ("test", 1),
        "headers": [(b"authorization", b"Bearer fake")] if token else [],
    }
    asyncio.run(app(scope, receive, send))
    status = next(m["status"] for m in messages if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return status, json.loads(body)


class AdminReservationsReportTests(TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', poolclass=StaticPool,
                                    connect_args={'check_same_thread': False})
        for model in (Branch, Category, Product, ProductVariant, Reservation, ReservationDetail):
            model.__table__.create(self.engine)
        self.db = Session(self.engine, autoflush=False)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        for i in (1, 2, 3):
            self.db.add(Branch(id_sucursal=i, id_ciudad=1, nombre=f'Sucursal {i}', direccion='Av', estado=False))
            self.db.add(Category(id_categoria=i, nombre=f'Categoria {i}', estado=False))
            self.db.add(Product(id_producto=i, id_categoria=i, nombre=f'Producto {i}',
                                seccion='UNISEX', precio=100, estado=False))
            self.db.add(ProductVariant(id_variante_producto=i, id_producto=i, id_talla=1,
                                       id_color=1, sku=f'SKU{i}', estado=False))
        self.db.add(ProductVariant(id_variante_producto=4, id_producto=1, id_talla=2,
                                   id_color=1, sku='SKU4', estado=False))
        self.db.flush()
        self.add_reservation(1, STATES[0], '2026-09-18T03:59:59.999999', [(1, 2), (4, 1), (2, 3)])
        self.add_reservation(2, STATES[1], '2026-09-18T04:00:00', [(2, 2)], branch=2)
        self.add_reservation(3, STATES[2], '2026-09-19T03:59:59.999999', [(1, 1)], client=2,
                             attended='2026-09-21T04:00:00')
        self.add_reservation(4, STATES[3], '2026-09-19T04:00:00', [(2, 1)], client=2)
        self.add_reservation(5, STATES[4], '2026-10-01T04:00:00', [(1, 1)], client=3)
        self.db.commit()
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.auth = self.enterContext(patch('app.services.admin_user_service.AuthService.get_current_user'))
        self.auth.return_value = SimpleNamespace(id_usuario=1, rol='ADMINISTRADOR')
        clock = self.enterContext(patch('app.services.admin_reservations_report.datetime', wraps=datetime))
        clock.now.return_value = datetime(2026, 9, 22, tzinfo=timezone.utc)

    def add_reservation(self, rid, state, created, lines, branch=1, client=1, attended=None):
        self.db.add(Reservation(id_reserva=rid, id_cliente=client, id_sucursal=branch,
                                codigo=f'R{rid}', estado=state, created_at=datetime.fromisoformat(created),
                                fecha_atencion_programada=datetime(2026, 10, 2, 4),
                                fecha_expiracion=datetime(2026, 10, 2, 5),
                                fecha_atencion=datetime.fromisoformat(attended) if attended else None))
        self.db.flush()
        for variant, qty in lines:
            self.db.add(ReservationDetail(id_reserva=rid, id_variante_producto=variant,
                                          cantidad=qty, precio_unitario=10))
        self.db.flush()

    def report(self, query=''):
        status, body = request(self.app, query)
        self.assertEqual(status, 200, body)
        return body['data']

    def test_unfiltered_distinct_clients_states_and_rankings(self):
        data = self.report()
        self.assertEqual(data['kpis'], dict(total_reservas=5, unidades_reservadas=11,
            clientes_con_reservas=3, reservas_pendientes=1, reservas_confirmadas=1,
            reservas_atendidas=1, reservas_canceladas=1, reservas_expiradas=1))
        self.assertEqual([r['estado'] for r in data['por_estado']], list(STATES))
        self.assertEqual([(r['id_producto'], r['total_reservas'], r['unidades_reservadas'])
                         for r in data['productos_mas_reservados']], [(2, 3, 6), (1, 3, 5)])
        self.assertEqual(sum(r['clientes_con_reservas'] for r in data['por_sucursal']), 4)

    def test_creation_local_boundaries_and_open_ranges(self):
        data = self.report('tipo_fecha=CREACION&fecha_desde=2026-09-18&fecha_hasta=2026-09-18')
        self.assertEqual(data['kpis']['total_reservas'], 2)
        self.assertEqual(data['kpis']['unidades_reservadas'], 3)
        self.assertEqual(data['serie_periodica'][0]['inicio_periodo'], '2026-09-18')
        self.assertEqual(self.report('fecha_desde=2026-09-18')['kpis']['total_reservas'], 4)
        self.assertEqual(self.report('fecha_hasta=2026-09-18')['kpis']['total_reservas'], 3)

    def test_programmed_and_attended_dates_exclude_nulls(self):
        self.assertEqual(self.report('tipo_fecha=PROGRAMADA&fecha_desde=2026-10-02&fecha_hasta=2026-10-02')['kpis']['total_reservas'], 5)
        self.assertEqual(self.report('tipo_fecha=PROGRAMADA&fecha_hasta=2026-09-30')['kpis']['total_reservas'], 0)
        data = self.report('tipo_fecha=ATENCION')
        self.assertEqual(data['kpis']['total_reservas'], 1)
        self.assertEqual(data['serie_periodica'][0]['inicio_periodo'], '2026-09-21')
        self.assertEqual(self.report('tipo_fecha=ATENCION&fecha_hasta=2026-09-20')['kpis']['total_reservas'], 0)

    def test_periods(self):
        expected = {'DIA': [('2026-09-17', 1), ('2026-09-18', 2), ('2026-09-19', 1), ('2026-10-01', 1)],
                    'SEMANA': [('2026-09-14', 4), ('2026-09-28', 1)],
                    'MES': [('2026-09-01', 4), ('2026-10-01', 1)]}
        for period, rows in expected.items():
            with self.subTest(period=period):
                self.assertEqual([(r['inicio_periodo'], r['total_reservas']) for r in
                                  self.report(f'periodo={period}')['serie_periodica']], rows)
        self.add_reservation(6, 'ATENDIDA', '2026-09-20T04:00:00', [(1, 1)], attended='2026-09-21T03:59:59')
        self.db.commit()
        self.assertEqual([(r['inicio_periodo'], r['total_reservas']) for r in
            self.report('tipo_fecha=ATENCION&periodo=SEMANA')['serie_periodica']], [('2026-09-14', 1), ('2026-09-21', 1)])

    def test_filters_mixed_categories_multiple_variants(self):
        for query in ('id_categoria=1', 'id_producto=1', 'id_producto=1&id_categoria=1'):
            with self.subTest(query=query):
                data = self.report(query)
                self.assertEqual(data['kpis']['total_reservas'], 3)
                self.assertEqual(data['kpis']['unidades_reservadas'], 5)
                self.assertEqual(len(data['categorias_mas_reservadas']), 1)
        self.assertEqual(self.report('id_sucursal=2')['kpis']['total_reservas'], 1)
        for state in STATES:
            data = self.report(f'estado={state}')
            self.assertEqual(data['kpis']['total_reservas'], 1)
            self.assertEqual(len(data['por_estado']), 5)
            self.assertEqual(sum(r['total_reservas'] for r in data['por_estado']), 1)
        data = self.report('id_sucursal=1&estado=PENDIENTE&id_categoria=1&id_producto=1&fecha_hasta=2026-09-17')
        self.assertEqual(data['kpis']['unidades_reservadas'], 3)
        self.assertEqual(data['kpis']['total_reservas'], 1)

    def test_empty_and_mismatched_product_category(self):
        for query in ('id_producto=1&id_categoria=2', 'id_producto=3', 'id_sucursal=3', 'fecha_desde=2027-01-01'):
            data = self.report(query)
            self.assertTrue(all(value == 0 for value in data['kpis'].values()))
            self.assertEqual(len(data['por_estado']), 5)
            self.assertTrue(all(r['total_reservas'] == r['unidades_reservadas'] == 0 for r in data['por_estado']))
            for key in ('por_sucursal', 'serie_periodica', 'productos_mas_reservados', 'categorias_mas_reservadas'):
                self.assertEqual(data[key], [])

    def test_warning_scope_before_state_and_at_expiration(self):
        for rid in (1, 2):
            row = self.db.get(Reservation, rid)
            row.fecha_atencion_programada = datetime(2026, 9, 21, 23)
            row.fecha_expiracion = datetime(2026, 9, 22)
        self.db.commit()
        for query, expected in (('', 2), ('estado=EXPIRADA', 2), ('estado=ATENDIDA&id_producto=1', 1),
                                ('id_sucursal=2', 1), ('fecha_desde=2026-09-18', 1),
                                ('tipo_fecha=ATENCION', 0), ('id_categoria=3', 0)):
            self.assertEqual(self.report(query)['advertencias']['reservas_vencidas_sin_actualizar'], expected)
        self.assertEqual(self.db.get(Reservation, 1).estado, 'PENDIENTE')

    def test_tie_order_and_header_without_details(self):
        self.add_reservation(6, 'PENDIENTE', '2026-09-18T12:00:00', [(1, 1)])
        self.add_reservation(7, 'PENDIENTE', '2026-09-18T12:00:00', [])
        self.db.commit()
        data = self.report()
        self.assertEqual(data['kpis']['total_reservas'], 7)
        self.assertEqual([r['id_producto'] for r in data['productos_mas_reservados']], [1, 2])
        self.assertEqual([r['id_categoria'] for r in data['categorias_mas_reservadas']], [1, 2])
        self.assertEqual(self.report('id_categoria=1')['kpis']['total_reservas'], 4)

    def test_invalid_filters(self):
        queries = ['fecha_desde=2026-09-19&fecha_hasta=2026-09-18', 'fecha_desde=2026-02-30',
                   'fecha_desde=2026-9-1', 'fecha_desde=0', 'fecha_hasta=9999-12-31',
                   'fecha_hasta=2026-09-18T00:00:00', 'tipo_fecha=OTRA', 'periodo=ANIO', 'estado=OTRO']
        queries += [f'{key}={value}' for key in ('id_sucursal', 'id_categoria', 'id_producto')
                    for value in ('0', '-1', '999', 'abc', '1.5')]
        for query in queries:
            with self.subTest(query=query):
                self.assertEqual(request(self.app, query)[0], 422)

    def test_security(self):
        with patch('app.routers.admin_reservations_report.AdminReservationsReportService') as service:
            self.assertEqual(request(self.app, token=False)[0], 401)
            for error, status in ((InvalidAccessTokenError, 401), (InactiveAccountError, 403)):
                self.auth.side_effect = error
                self.assertEqual(request(self.app)[0], status)
            self.auth.side_effect = None
            for role in ('CLIENTE', 'CAJERO', 'ENCARGADO_SUCURSAL', 'PROVEEDOR'):
                self.auth.return_value = SimpleNamespace(id_usuario=1, rol=role)
                self.assertEqual(request(self.app)[0], 403)
            service.assert_not_called()

    def test_read_only_and_bounded_queries(self):
        statements = []
        def capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)
        event.listen(self.engine, 'before_cursor_execute', capture)
        self.addCleanup(event.remove, self.engine, 'before_cursor_execute', capture)
        self.report()
        self.assertEqual(len(statements), 7)
        for rid in range(10, 60):
            self.add_reservation(rid, 'PENDIENTE', '2026-09-18T12:00:00', [(1, 2), (2, 1)])
        self.db.commit()
        before = list(self.db.execute(select(Reservation.__table__)))
        details_before = list(self.db.execute(select(ReservationDetail.__table__)))
        statements.clear()
        with patch.object(self.db, 'commit', side_effect=AssertionError('commit forbidden')), \
             patch.object(self.db, 'flush', side_effect=AssertionError('flush forbidden')), \
             patch('app.services.client_reservations.ClientReservationService._expire_locked', side_effect=AssertionError('expire forbidden')):
            self.assertEqual(self.report()['kpis']['total_reservas'], 55)
            self.assertEqual(len(statements), 7)
            statements.clear()
            self.report('id_sucursal=1&id_categoria=1&id_producto=1')
            self.assertEqual(len(statements), 10)
        self.assertTrue(all(s.lstrip().upper().startswith(('WITH', 'SELECT')) for s in statements))
        self.assertFalse(any(name in s for s in statements for name in ('t_inventario', 't_pago', 't_imagen')))
        self.assertEqual(list(self.db.execute(select(Reservation.__table__))), before)
        self.assertEqual(list(self.db.execute(select(ReservationDetail.__table__))), details_before)

    def test_service_suppresses_autoflush(self):
        self.db.autoflush = True
        row = self.db.get(Product, 1)
        row.nombre = 'Pending unrelated change'
        with patch.object(self.db, 'flush', side_effect=AssertionError('flush forbidden')):
            AdminReservationsReportService(self.db).report(ReservationsReportFilters(id_producto=1))
        self.db.rollback()

    def test_postgresql_compilation(self):
        statements = []
        def capture(statement):
            statements.append(statement)
            return SimpleNamespace(mappings=lambda: SimpleNamespace(one=lambda: {}, all=lambda: []))
        service = AdminReservationsReportService(self.db)
        with patch.object(self.db, 'get_bind', return_value=SimpleNamespace(dialect=postgresql.dialect())), \
             patch.object(self.db, 'scalar', return_value=0), patch.object(self.db, 'execute', side_effect=capture):
            for period in ('DIA', 'SEMANA', 'MES'):
                service.repository.report(ReservationsReportFilters(periodo=period, id_categoria=1),
                                          None, None, datetime(2026, 9, 22))
        sql = '\n'.join(str(s.compile(dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True})) for s in statements)
        self.assertIn("timezone('America/La_Paz', timezone('UTC'", sql)
        for unit in ('day', 'week', 'month'):
            self.assertIn(f"date_trunc('{unit}'", sql)
        self.assertIn('count(distinct(', sql.lower())
        self.assertNotIn('t_inventario', sql)

    def test_errors_and_registration(self):
        with patch('app.routers.admin_reservations_report.AdminReservationsReportService.report', side_effect=SQLAlchemyError('private')):
            status, body = request(self.app)
            self.assertEqual(status, 500)
            self.assertNotIn('private', json.dumps(body))
        from app.main import app
        self.assertIn(ROUTE, app.openapi()['paths'])
