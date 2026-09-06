"""Pruebas CU09 sin conectar ni modificar la base de datos."""
from datetime import datetime
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from app.repositories.admin_supplier_repository import AdminSupplierRepository
from app.services.admin_supplier_service import AdminSupplierService, SupplierNotFoundError, AdminSupplierPersistenceError
from app.schemas.admin_supplier import SupplierCreateRequest, SupplierUpdateRequest, SupplierStatusUpdateRequest
from app.routers import admin_suppliers as routes


def record():
    return SimpleNamespace(id_proveedor=7, nombre="Base", nit=None, telefono=None, correo=None, direccion=None, id_usuario=None, estado=True,
                           created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1))


class SchemaTests(TestCase):
    def test_normalization_and_lengths(self):
        self.assertEqual(SupplierCreateRequest(nombre=" Base ", direccion=" abc ").model_dump(),
                         {"nombre": "Base", "direccion": "abc", "nit": None, "telefono": None, "correo": None, "id_usuario": None})
        for values in ({}, {"nombre": " "}, {"nombre": None}, {"nombre": "x" * (150+1)},
                       {"nombre": "Base", "direccion": "x" * (200+1)}, {"nombre": "Base", "estado": False},
                       {"nombre": "Base", "id_sucursal": 1}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                SupplierCreateRequest(**values)
        self.assertEqual(len(SupplierCreateRequest(nombre="x" * 150, direccion="x" * 200).nombre), 150)

    def test_patch(self):
        self.assertEqual(SupplierUpdateRequest(direccion=None).model_dump(exclude_unset=True), {"direccion": None})
        for values in ({}, {"nombre": None}, {"estado": False}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                SupplierUpdateRequest(**values)


class ServiceTests(TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.service = AdminSupplierService(self.db)
        self.repo = self.service.repository = MagicMock()
        self.item = record()
        self.repo.get_by_id.return_value = self.item
        self.repo.get_by_name.return_value = None
        self.repo.create.return_value = self.item
        self.repo.update.side_effect = lambda item, **values: item.__dict__.update(values)
        self.repo.update_status.side_effect = lambda item, state: setattr(item, "estado", state)

    def test_create(self):
        result = self.service.create_supplier(SupplierCreateRequest(nombre=" Base "))
        self.repo.create.assert_called_once_with(nombre="Base", nit=None, telefono=None, correo=None, direccion=None)
        self.assertTrue(result.estado)
        self.db.commit.assert_called_once()

    def test_same_name_allowed_on_create_and_update(self):
        self.repo.get_by_name.return_value = self.item
        for _ in range(2):
            self.service.create_supplier(SupplierCreateRequest(nombre="Base"))
        self.service.update_supplier(supplier_id=7, payload=SupplierUpdateRequest(nombre="Base"))
        self.repo.get_by_name.assert_not_called()
        self.assertEqual(self.repo.create.call_count, 2)
        self.assertEqual(self.db.commit.call_count, 3)

    def test_list_search_state_pagination(self):
        self.repo.list_suppliers.return_value = ([self.item], 3)
        data, pagination = self.service.list_suppliers(search="ba", state=False, page=2, page_size=2)
        self.repo.list_suppliers.assert_called_once_with(search="ba", state=False, page=2, page_size=2)
        self.assertEqual(data[0].id_proveedor, 7)
        self.assertEqual(pagination.model_dump(), {"page": 2, "page_size": 2, "total": 3, "total_pages": 2})

    def test_detail_and_partial_update(self):
        self.assertEqual(self.service.get_supplier(7).nombre, "Base")
        result = self.service.update_supplier(supplier_id=7, payload=SupplierUpdateRequest(direccion=" abc "))
        self.assertEqual(result.direccion, "abc")
        self.assertEqual(result.nombre, "Base")
        self.repo.get_by_name.assert_not_called()
        result = self.service.update_supplier(supplier_id=7, payload=SupplierUpdateRequest(direccion=None))
        self.assertIsNone(result.direccion)
        self.service.update_supplier(supplier_id=7, payload=SupplierUpdateRequest(nombre="BASE"))
        self.repo.get_by_name.assert_not_called()

    def test_deactivate_and_reactivate(self):
        for state in (False, True):
            result = self.service.update_status(supplier_id=7, payload=SupplierStatusUpdateRequest(estado=state))
            self.assertEqual(result.estado, state)
        self.db.delete.assert_not_called()
        self.assertEqual(result.created_at, datetime(2026, 1, 1))
        self.assertEqual(result.updated_at, datetime(2026, 1, 1))

    def test_missing(self):
        self.repo.get_by_id.return_value = None
        for operation in (lambda: self.service.get_supplier(999),
                          lambda: self.service.update_supplier(supplier_id=999, payload=SupplierUpdateRequest(nombre="Other")),
                          lambda: self.service.update_status(supplier_id=999, payload=SupplierStatusUpdateRequest(estado=False))):
            with self.assertRaises(SupplierNotFoundError):
                operation()

    def test_persistence_rollback(self):
        self.db.commit.side_effect = SQLAlchemyError("failure")
        with self.assertRaises(AdminSupplierPersistenceError):
            self.service.create_supplier(SupplierCreateRequest(nombre="Base"))
        self.db.rollback.assert_called_once()

    def test_integrity_error_is_not_a_name_conflict(self):
        self.repo.create.side_effect = IntegrityError("insert", {}, Exception())
        with self.assertRaises(AdminSupplierPersistenceError):
            self.service.create_supplier(SupplierCreateRequest(nombre="Base"))
        self.db.rollback.assert_called_once()
        self.repo.get_by_name.assert_not_called()


class RepositoryTests(TestCase):
    def test_filters_escaped_search_and_order(self):
        db = MagicMock()
        db.scalars.return_value.all.return_value = []
        db.scalar.return_value = 0
        repository = AdminSupplierRepository(db)
        self.assertEqual(repository.list_suppliers(search=" %_\\ ", state=False, page=2, page_size=3), ([], 0))
        statement = db.scalars.call_args.args[0].compile(dialect=postgresql.dialect())
        sql = str(statement)
        self.assertIn("ILIKE", sql)
        self.assertIn("estado IS false", sql)
        self.assertIn("ORDER BY t_proveedor.nombre, t_proveedor.id_proveedor", sql)
        self.assertIn("%\\%\\_\\\\%", statement.params.values())
        self.assertIn(3, statement.params.values())
        count = db.scalar.call_args.args[0].compile(dialect=postgresql.dialect())
        self.assertEqual(count.params['nombre_1'], statement.params['nombre_1'])

    def test_create_active_without_name_lookup(self):
        db = MagicMock()
        repository = AdminSupplierRepository(db)
        first = repository.create(nombre="Base")
        second = repository.create(nombre="Base")
        self.assertEqual(first.nombre, second.nombre)
        self.assertTrue(first.estado)
        self.assertIsNone(first.direccion)
        self.assertEqual(db.add.call_count, 2)
        db.scalar.assert_not_called()

    def test_status_only_changes_record(self):
        db = MagicMock()
        item = record()
        original = vars(item).copy()
        AdminSupplierRepository(db).update_status(item, state=False)
        self.assertEqual(vars(item), {**original, "estado": False})
        db.flush.assert_called_once()
        db.delete.assert_not_called()

    def test_update_locks_record(self):
        db = MagicMock()
        AdminSupplierRepository(db).get_by_id(7, for_update=True)
        query = db.scalar.call_args.args[0].compile(dialect=postgresql.dialect())
        self.assertIn("FOR UPDATE", str(query))


class RouteTests(TestCase):
    def test_routes_and_pagination_limit(self):
        registered = {(method, route.path) for route in routes.router.routes for method in route.methods}
        self.assertEqual(registered, {("GET", "/api/admin/suppliers"), ("POST", "/api/admin/suppliers"),
            ("GET", "/api/admin/suppliers/{id_proveedor}"), ("PATCH", "/api/admin/suppliers/{id_proveedor}"),
            ("PATCH", "/api/admin/suppliers/{id_proveedor}/status")})
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(routes.router)
        params = app.openapi()["paths"]["/api/admin/suppliers"]["get"]["parameters"]
        self.assertEqual(next(p for p in params if p['name'] == 'page_size')['schema']['maximum'], 100)

    def test_denied_access_never_calls_service(self):
        for code in (401, 403):
            denied = JSONResponse(status_code=code, content={"success": False})
            with patch.object(routes, "AdminSupplierService") as service:
                calls = [routes.list_suppliers(administrator=denied, db=MagicMock()),
                    routes.get_supplier(7, administrator=denied, db=MagicMock()),
                    routes.create_supplier(SupplierCreateRequest(nombre="Base"), administrator=denied, db=MagicMock()),
                    routes.update_supplier(7, SupplierUpdateRequest(nombre="Other"), administrator=denied, db=MagicMock()),
                    routes.update_supplier_status(7, SupplierStatusUpdateRequest(estado=False), administrator=denied, db=MagicMock())]
                self.assertTrue(all(result is denied for result in calls))
                service.assert_not_called()


class ResponseTests(TestCase):
    def test_main_registration_and_success_status(self):
        from app.main import app
        operation = app.openapi()["paths"]["/api/admin/suppliers"]
        self.assertIn("201", operation["post"]["responses"])
        self.assertIn("200", operation["get"]["responses"])
        self.assertTrue(operation["post"]["security"])
        with patch.object(routes, "AdminSupplierService") as service:
            service.return_value.create_supplier.return_value = vars(record())
            result = routes.create_supplier(SupplierCreateRequest(nombre="Base"), administrator=object(), db=MagicMock())
            self.assertTrue(result.success)
            self.assertEqual(result.data.nombre, "Base")

    def test_missing_and_persistence_errors(self):
        with patch.object(routes, "AdminSupplierService") as service:
            instance = service.return_value
            instance.get_supplier.side_effect = SupplierNotFoundError
            instance.update_supplier.side_effect = SupplierNotFoundError
            instance.update_status.side_effect = SupplierNotFoundError
            results = [
                routes.get_supplier(999, administrator=object(), db=MagicMock()),
                routes.update_supplier(999, SupplierUpdateRequest(nombre="Base"), administrator=object(), db=MagicMock()),
                routes.update_supplier_status(999, SupplierStatusUpdateRequest(estado=False), administrator=object(), db=MagicMock()),
            ]
            self.assertTrue(all(result.status_code == 404 for result in results))
            instance.create_supplier.side_effect = AdminSupplierPersistenceError
            result = routes.create_supplier(SupplierCreateRequest(nombre="Base"), administrator=object(), db=MagicMock())
            self.assertEqual(result.status_code, 500)
            instance.list_suppliers.side_effect = SQLAlchemyError("failure")
            db = MagicMock()
            result = routes.list_suppliers(administrator=object(), db=db)
            self.assertEqual(result.status_code, 500)
            db.rollback.assert_called_once()

class SupplierScopeTests(TestCase):
    def test_optional_fields_and_email_validation(self):
        payload = SupplierCreateRequest(nombre=' Base ', nit=None, telefono=None, correo=None, direccion=None, id_usuario=None)
        self.assertTrue(all(value is None for key, value in payload.model_dump().items() if key != 'nombre'))
        self.assertEqual(SupplierCreateRequest(nombre='Base', correo=' user@example.com ').correo, 'user@example.com')
        for field, limit in [('nit', 30), ('telefono', 30), ('direccion', 200)]:
            self.assertEqual(len(getattr(SupplierCreateRequest(nombre='Base', **{field: 'x' * limit}), field)), limit)
            with self.assertRaises(ValidationError):
                SupplierCreateRequest(nombre='Base', **{field: 'x' * (limit + 1)})
        for email in ('invalid', 'a' * 64 + '@' + 'b' * 63 + '.example.com.more.example'):
            with self.assertRaises(ValidationError):
                SupplierCreateRequest(nombre='Base', correo=email)

    def test_user_association_is_not_writable(self):
        with self.assertRaises(ValidationError):
            SupplierCreateRequest(nombre='Base', id_usuario=12)
        for value in (None, 12):
            with self.assertRaises(ValidationError):
                SupplierUpdateRequest(id_usuario=value)
        db = MagicMock()
        service = AdminSupplierService(db)
        item = record()
        item.id_usuario = 12
        service.repository.get_by_id = MagicMock(return_value=item)
        self.assertEqual(service.update_supplier(supplier_id=7, payload=SupplierUpdateRequest(nombre='Other')).id_usuario, 12)
        self.assertEqual(service.update_status(supplier_id=7, payload=SupplierStatusUpdateRequest(estado=False)).id_usuario, 12)
        self.assertEqual(item.id_usuario, 12)
        db.delete.assert_not_called()

    def test_all_write_failures_rollback(self):
        for operation in ('create', 'update', 'status'):
            for stage in ('flush', 'commit'):
                with self.subTest(operation=operation, stage=stage):
                    db = MagicMock()
                    service = AdminSupplierService(db)
                    service.repository.get_by_id = MagicMock(return_value=record())
                    service._to_supplier_data = MagicMock(return_value=record())
                    getattr(db, stage).side_effect = SQLAlchemyError('private database details')
                    with self.assertRaises(AdminSupplierPersistenceError):
                        if operation == 'create':
                            service.create_supplier(SupplierCreateRequest(nombre='Base'))
                        elif operation == 'update':
                            service.update_supplier(supplier_id=7, payload=SupplierUpdateRequest(nit=None))
                        else:
                            service.update_status(supplier_id=7, payload=SupplierStatusUpdateRequest(estado=False))
                    db.rollback.assert_called_once()
                    if stage == 'flush':
                        db.commit.assert_not_called()

    def test_search_columns_count_and_optional_state(self):
        for state in (None, True, False):
            db = MagicMock()
            db.scalars.return_value.all.return_value = []
            db.scalar.return_value = 0
            AdminSupplierRepository(db).list_suppliers(search='needle', state=state, page=3, page_size=2)
            query = db.scalars.call_args.args[0].compile(dialect=postgresql.dialect())
            count = db.scalar.call_args.args[0].compile(dialect=postgresql.dialect())
            for column in ('nombre', 'nit', 'correo'):
                self.assertIn(f't_proveedor.{column} ILIKE', str(query))
                self.assertEqual(query.params[f'{column}_1'], count.params[f'{column}_1'])
            self.assertIn(4, query.params.values())
            if state is None:
                self.assertNotIn('estado IS', str(query))
            else:
                self.assertIn(f'estado IS {str(state).lower()}', str(query))

    def test_duplicate_commercial_fields_do_not_trigger_lookups(self):
        db = MagicMock()
        repository = AdminSupplierRepository(db)
        values = dict(nombre='Same', nit='123', telefono='456', correo='same@example.com', direccion='Same')
        for _ in range(2):
            item = repository.create(**values)
            self.assertIsNone(item.id_usuario)
        db.scalar.assert_not_called()
        self.assertEqual(db.add.call_count, 2)
