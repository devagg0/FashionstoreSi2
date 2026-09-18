"""CU25: consultas HTTP y SQL reales, exclusivamente SQLite en memoria."""
import json
from unittest import TestCase
from unittest.mock import patch

from fastapi import FastAPI
from sqlalchemy import event

from tests import test_client_purchases as fixtures
from app.core.database import get_db
from app.models.employee import Employee
from app.models.employee_branch import EmployeeBranch
from app.models.payment import Payment
from app.models.sale import Sale
from app.models.user import User
from app.routers import receipts as routes
from app.routers.client_reservations import require_client
from app.routers.staff_reservations import require_reservation_staff


class ReceiptTests(TestCase):
    def setUp(self):
        self.fixture = fixtures.ClientPurchaseTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.db = self.fixture.db
        for model in (User, Employee, EmployeeBranch):
            model.__table__.create(self.fixture.engine)
        self.db.add_all([
            User(id_usuario=12, id_rol=1, nombre='Ana', apellido='Perez',
                 correo='ana@example.test', password_hash='PRIVATE'),
            Employee(id_empleado=5, id_usuario=20),
            EmployeeBranch(id_empleado=5, id_sucursal=2),
        ])
        self.db.commit()
        self.app = FastAPI()
        self.app.include_router(routes.router)
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.app.dependency_overrides[require_client] = lambda: fixtures.NS(id_usuario=12, rol='CLIENTE')
        self.app.dependency_overrides[require_reservation_staff] = lambda: fixtures.NS(id_usuario=20, rol='CAJERO')

    def get(self, sale_id=1, staff=False):
        prefix = '/api/staff/sales' if staff else '/api/client/purchases'
        return fixtures.request(self.app, f'{prefix}/{sale_id}/receipt')

    def complete_presencial(self, medio='EFECTIVO', anonymous=True):
        sale = self.db.get(Sale, 2)
        sale.estado = 'COMPLETADA'
        sale.fecha_completada = sale.fecha_venta
        if anonymous:
            sale.id_cliente = None
        payment = self.db.get(Payment, 2)
        payment.estado = 'APROBADO'
        payment.medio = medio
        payment.fecha_aprobacion = sale.fecha_completada
        self.db.commit()

    def test_digital_own_receipt_historical_amounts_and_public_fields(self):
        status, body = self.get()
        self.assertEqual(status, 200)
        data = body['data']
        self.assertEqual(data['numero_venta'], 'VTA-1')
        self.assertEqual(data['canal'], 'DIGITAL')
        self.assertEqual(data['moneda'], 'BOB')
        self.assertEqual(data['fecha_completada'], '2026-09-17T12:00:00')
        self.assertEqual(data['cliente'], {'nombre': 'Ana', 'apellido': 'Perez'})
        self.assertEqual(data['sucursal'], {'nombre': 'Centro', 'direccion': 'Calle A'})
        self.assertEqual((data['subtotal'], data['descuento_total'], data['total']), ('24.00', '4.00', '20.00'))
        self.assertEqual(data['productos'], [{'nombre': 'Camisa', 'talla': 'M', 'color': 'Blanco',
            'cantidad': 2, 'precio_unitario': '12.00', 'descuento_unitario': '2.00', 'subtotal_linea': '20.00'}])
        self.assertEqual(data['pago'], {'medio': 'TARJETA', 'estado': 'APROBADO', 'monto': '20.00'})
        text = json.dumps(body)
        for secret in ('cs_test_private', 'clave_idempotencia', 'referencia_externa', 'password',
                       'id_pago', 'id_cliente', 'id_variante_producto', 'correo', 'proveedor'):
            self.assertNotIn(secret, text)

    def test_foreign_and_missing_are_same_404(self):
        self.assertEqual(self.get(3), self.get(999))
        self.assertEqual(self.get(3)[0], 404)

    def test_pending_and_annulled_rejected(self):
        self.assertEqual(self.get(2)[0], 409)
        self.db.get(Sale, 2).estado = 'ANULADA'
        self.db.commit()
        self.assertEqual(self.get(2)[0], 409)

    def test_presencial_without_registered_client_cash(self):
        self.complete_presencial()
        status, body = self.get(2, staff=True)
        self.assertEqual(status, 200)
        self.assertIsNone(body['data']['cliente'])
        self.assertEqual(body['data']['canal'], 'PRESENCIAL')
        self.assertEqual(body['data']['pago']['medio'], 'EFECTIVO')
        self.assertEqual(self.get(2)[0], 404)

    def test_presencial_qr_and_registered_client(self):
        self.complete_presencial('QR', anonymous=False)
        status, body = self.get(2)
        self.assertEqual(status, 200)
        self.assertEqual(body['data']['pago']['medio'], 'QR')
        self.assertEqual(body['data']['cliente']['nombre'], 'Ana')

    def test_staff_can_read_digital_sale_without_sale_employee(self):
        self.assertEqual(self.get(staff=True)[0], 200)

    def test_staff_foreign_branch_and_inactive_assignment(self):
        self.app.dependency_overrides[require_reservation_staff] = lambda: fixtures.NS(id_usuario=21, rol='CAJERO')
        self.assertEqual(self.get(staff=True)[0], 404)
        self.app.dependency_overrides[require_reservation_staff] = lambda: fixtures.NS(id_usuario=20, rol='CAJERO')
        self.db.get(EmployeeBranch, 1).estado = False
        self.db.commit()
        self.assertEqual(self.get(staff=True)[0], 404)

    def test_missing_approved_payment_rejected(self):
        self.db.get(Payment, 1).estado = 'PENDIENTE'
        self.db.commit()
        status, body = self.get()
        self.assertEqual(status, 409)
        self.assertIn('pago aprobado', body['message'])

    def test_inconsistent_payment_rejected(self):
        self.db.get(Payment, 1).monto = 19
        self.db.commit()
        self.assertEqual(self.get()[0], 409)

    def test_refunded_payment_preserves_historical_receipt(self):
        self.db.get(Payment, 1).estado = 'REEMBOLSADO'
        self.db.commit()
        status, body = self.get()
        self.assertEqual(status, 200)
        self.assertEqual(body['data']['pago']['estado'], 'REEMBOLSADO')
        self.assertEqual(body['data']['total'], '20.00')

    def test_repeated_receipt_only_reads_no_commit_or_flush(self):
        statements = []
        def capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement.lstrip().split()[0].upper())
        event.listen(self.fixture.engine, 'before_cursor_execute', capture)
        self.db.autoflush = False
        with patch.object(self.db, 'commit') as commit, patch.object(self.db, 'flush') as flush:
            first = self.get()
            self.assertEqual(first, self.get())
            self.assertEqual(first[0], 200)
            self.assertEqual(self.get(staff=True)[0], 200)
            commit.assert_not_called()
            flush.assert_not_called()
        self.assertTrue(statements)
        self.assertEqual(set(statements), {'SELECT'})

    def test_missing_client_profile(self):
        self.app.dependency_overrides[require_client] = lambda: fixtures.NS(id_usuario=999, rol='CLIENTE')
        self.assertEqual(self.get()[0], 403)

    def test_session_required_and_staff_client_role_rejected(self):
        self.app.dependency_overrides.pop(require_client)
        self.assertEqual(self.get()[0], 401)
        self.app.dependency_overrides.pop(require_reservation_staff)
        self.assertEqual(self.get(staff=True)[0], 401)
        with patch('app.routers.staff_reservations.AuthService') as auth:
            auth.return_value.get_current_user.return_value = fixtures.NS(id_usuario=12, rol='CLIENTE')
            self.assertEqual(fixtures.request(self.app, '/api/staff/sales/1/receipt', token=True)[0], 403)

    def test_invalid_sale_id(self):
        self.assertEqual(self.get(0)[0], 422)

    def test_registered_in_main(self):
        from app.main import app
        paths = app.openapi()['paths']
        self.assertIn('/api/client/purchases/{id_venta}/receipt', paths)
        self.assertIn('/api/staff/sales/{id_venta}/receipt', paths)
