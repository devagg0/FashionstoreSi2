"""CU15 con unittest y mocks: no abre conexiones ni ejecuta DDL."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError

from app.repositories.inventory_movements import InventoryMovementRepository
from app.routers import admin_inventory_movements as routes
from app.routers.admin_users import require_administrator
from app.schemas.admin_inventory_movements import MovementCreateRequest, MovementDetailCreate
from app.services.admin_inventory_movements import (
    AdminInventoryMovementService, MovementConflictError, MovementNotFoundError,
    MovementPersistenceError, MovementValidationError,
)


def payload(kind="ENTRADA", **overrides):
    data = dict(tipo_movimiento=kind, id_empleado_sucursal=9,
                id_sucursal_origen=1 if kind in {"SALIDA", "AJUSTE_NEGATIVO", "TRANSFERENCIA"} else None,
                id_sucursal_destino=2 if kind in {"ENTRADA", "AJUSTE_POSITIVO", "TRANSFERENCIA"} else None,
                detalles=[dict(id_variante_producto=3, cantidad=4)])
    return MovementCreateRequest(**(data | overrides))


def header(kind="ENTRADA"):
    return dict(
        id_movimiento_inventario=10, **payload(kind).model_dump(exclude={"detalles"}),
        estado="PENDIENTE", fecha_movimiento=datetime(2026, 1, 1),
        created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1),
        sucursal_origen="Centro" if kind in {"SALIDA", "AJUSTE_NEGATIVO", "TRANSFERENCIA"} else None,
        sucursal_destino="Norte" if kind in {"ENTRADA", "AJUSTE_POSITIVO", "TRANSFERENCIA"} else None,
        id_empleado=5, nombre_empleado="Ana Pérez", rol="CAJERO",
    )


def detail():
    return dict(id_variante_producto=3, sku="SKU-3", producto="Camisa", talla="M",
                color="Azul", cantidad=4, costo_unitario=None)


class MovementSchemaTests(TestCase):
    def test_zero_quantity(self):
        with self.assertRaises(ValidationError):
            MovementDetailCreate(id_variante_producto=3, cantidad=0)

    def test_negative_quantity(self):
        with self.assertRaises(ValidationError):
            MovementDetailCreate(id_variante_producto=3, cantidad=-1)

    def test_empty_details(self):
        with self.assertRaises(ValidationError):
            payload(detalles=[])

    def test_sale_and_client_state_forbidden(self):
        for values in ({"tipo_movimiento": "VENTA"}, {"estado": "CONFIRMADO"}, {"id_venta": 1}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                payload(**values)

    def test_invalid_cost_and_non_integer_quantity(self):
        for values in ({"costo_unitario": -1}, {"costo_unitario": "1.001"},
                       {"costo_unitario": "100000000"}, {"cantidad": 1.5}, {"cantidad": True}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                MovementDetailCreate(**(dict(id_variante_producto=3, cantidad=4) | values))


class MovementServiceTests(TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.service = AdminInventoryMovementService(self.db)
        self.repo = self.service.repository = MagicMock()
        self.configure()

    def configure(self, kind="ENTRADA"):
        self.movement = SimpleNamespace(**header(kind))
        self.details = [SimpleNamespace(**detail())]
        self.assignment = SimpleNamespace(estado=True, id_sucursal=self.movement.id_sucursal_origen or 2)
        self.employee = SimpleNamespace(id_empleado=5, id_usuario=6)
        self.user = SimpleNamespace(estado=True)
        self.role = SimpleNamespace(nombre="CAJERO", estado=True)
        self.repo.get_responsible.return_value = (self.assignment, self.employee, self.user, self.role)
        self.repo.get_branch.return_value = SimpleNamespace(estado=True)
        self.repo.get_variant.return_value = (SimpleNamespace(estado=True), SimpleNamespace(estado=True))
        self.repo.get_movement.return_value = self.movement
        self.repo.get_details.return_value = self.details
        self.repo.create.return_value = self.movement
        self.repo.get_detail.side_effect = lambda _: dict(vars(self.movement), detalles=[detail()])
        self.origin = SimpleNamespace(stock_actual=10, stock_reservado=4, stock_minimo=2, updated_at=None)
        self.destination = SimpleNamespace(stock_actual=2, stock_reservado=1, stock_minimo=0, updated_at=None)
        self.repo.lock_inventory.side_effect = lambda branch, variant: self.origin if branch == 1 else self.destination

    def assert_create_error(self, error):
        with self.assertRaises(error):
            self.service.create_movement(payload())
        self.db.rollback.assert_called_once()
        self.db.commit.assert_not_called()
        self.repo.create.assert_not_called()

    def test_duplicate_variant(self):
        repeated = dict(id_variante_producto=3, cantidad=4)
        with self.assertRaises(MovementValidationError):
            self.service.create_movement(payload(detalles=[repeated, repeated]))
        self.repo.create.assert_not_called()

    def test_service_empty_details(self):
        request = payload().model_copy(update={"detalles": []})
        with self.assertRaises(MovementValidationError):
            self.service.create_movement(request)

    def test_missing_branch(self):
        self.repo.get_branch.return_value = None
        self.assert_create_error(MovementNotFoundError)

    def test_inactive_branch(self):
        self.repo.get_branch.return_value.estado = False
        self.assert_create_error(MovementValidationError)

    def test_missing_variant(self):
        self.repo.get_variant.return_value = None
        self.assert_create_error(MovementNotFoundError)

    def test_inactive_variant(self):
        self.repo.get_variant.return_value[0].estado = False
        self.assert_create_error(MovementValidationError)

    def test_inactive_product(self):
        self.repo.get_variant.return_value[1].estado = False
        self.assert_create_error(MovementValidationError)

    def test_missing_product(self):
        self.repo.get_variant.return_value = (SimpleNamespace(estado=True), None)
        self.assert_create_error(MovementNotFoundError)

    def test_missing_assignment(self):
        self.repo.get_responsible.return_value = None
        self.assert_create_error(MovementNotFoundError)

    def test_missing_employee(self):
        self.repo.get_responsible.return_value = (self.assignment, None, self.user, self.role)
        self.assert_create_error(MovementNotFoundError)

    def test_inactive_assignment(self):
        self.assignment.estado = False
        self.assert_create_error(MovementValidationError)

    def test_inactive_employee_user(self):
        self.user.estado = False
        self.assert_create_error(MovementValidationError)

    def test_non_operational_roles(self):
        for name in ("ADMINISTRADOR", "CLIENTE", "PROVEEDOR"):
            self.role.nombre = name
            with self.subTest(role=name), self.assertRaises(MovementValidationError):
                self.service.create_movement(payload())

    def test_inactive_role(self):
        self.role.estado = False
        self.assert_create_error(MovementValidationError)

    def test_incompatible_assignment(self):
        self.assignment.id_sucursal = 99
        self.assert_create_error(MovementValidationError)

    def test_transfer_responsible_must_belong_to_origin(self):
        self.configure("TRANSFERENCIA")
        self.assignment.id_sucursal = 2
        with self.assertRaises(MovementValidationError):
            self.service.create_movement(payload("TRANSFERENCIA"))

    def test_create_all_types_pending_without_stock_changes(self):
        for kind in ("ENTRADA", "SALIDA", "AJUSTE_POSITIVO", "AJUSTE_NEGATIVO", "TRANSFERENCIA"):
            self.configure(kind)
            self.role.nombre = "ENCARGADO_SUCURSAL"
            with self.subTest(kind=kind):
                self.assertEqual(self.service.create_movement(payload(kind)).estado, "PENDIENTE")
        self.assertEqual(self.db.commit.call_count, 5)
        self.repo.lock_inventory.assert_not_called()
        self.repo.create_inventory.assert_not_called()

    def test_equal_transfer_branches(self):
        with self.assertRaises(MovementValidationError):
            self.service.create_movement(payload("TRANSFERENCIA", id_sucursal_destino=1))

    def test_invalid_branch_combinations(self):
        for kind, values in (("ENTRADA", {"id_sucursal_origen": 1}),
                             ("AJUSTE_POSITIVO", {"id_sucursal_destino": None}),
                             ("SALIDA", {"id_sucursal_destino": 2}),
                             ("AJUSTE_NEGATIVO", {"id_sucursal_origen": None}),
                             ("TRANSFERENCIA", {"id_sucursal_destino": None})):
            with self.subTest(kind=kind), self.assertRaises(MovementValidationError):
                self.service.create_movement(payload(kind, **values))

    def check_confirm(self, kind, origin_stock, destination_stock):
        self.configure(kind)
        result = self.service.confirm_movement(10)
        self.assertEqual(result.estado, "CONFIRMADO")
        self.assertEqual(self.origin.stock_actual, origin_stock)
        self.assertEqual(self.destination.stock_actual, destination_stock)
        self.assertEqual(self.origin.stock_reservado, 4)
        self.assertEqual(self.destination.stock_reservado, 1)
        self.repo.get_movement.assert_called_once_with(10, for_update=True)
        self.db.commit.assert_called_once()
        self.assertGreater(result.updated_at, datetime(2026, 1, 1))

    def test_confirm_entry(self):
        self.check_confirm("ENTRADA", 10, 6)

    def test_confirm_exit(self):
        self.check_confirm("SALIDA", 6, 2)

    def test_confirm_positive_adjustment(self):
        self.check_confirm("AJUSTE_POSITIVO", 10, 6)

    def test_confirm_negative_adjustment(self):
        self.check_confirm("AJUSTE_NEGATIVO", 6, 2)

    def test_confirm_transfer_updates_both(self):
        self.check_confirm("TRANSFERENCIA", 6, 6)
        self.assertEqual(self.origin.updated_at, self.destination.updated_at)
        self.assertEqual(self.origin.updated_at, self.movement.updated_at)

    def test_insufficient_stock(self):
        self.configure("SALIDA")
        self.origin.stock_actual, self.origin.stock_reservado = 3, 0
        with self.assertRaises(MovementConflictError):
            self.service.confirm_movement(10)
        self.db.rollback.assert_called_once()
        self.assertEqual(self.origin.stock_actual, 3)
        self.assertEqual(self.movement.estado, "PENDIENTE")

    def test_reserved_stock_protected(self):
        self.configure("SALIDA")
        self.details[0].cantidad = 7
        with self.assertRaises(MovementConflictError):
            self.service.confirm_movement(10)
        self.assertEqual(self.origin.stock_actual, 10)
        self.db.commit.assert_not_called()

    def test_exact_available_stock_allowed(self):
        self.configure("SALIDA")
        self.details[0].cantidad = 6
        self.service.confirm_movement(10)
        self.assertEqual(self.origin.stock_actual, self.origin.stock_reservado)

    def test_second_confirmation_rejected(self):
        self.service.confirm_movement(10)
        with self.assertRaises(MovementConflictError):
            self.service.confirm_movement(10)
        self.db.commit.assert_called_once()
        self.assertEqual(self.destination.stock_actual, 6)

    def test_cancelled_cannot_confirm(self):
        self.movement.estado = "ANULADO"
        with self.assertRaises(MovementConflictError):
            self.service.confirm_movement(10)
        self.repo.lock_inventory.assert_not_called()

    def test_cancel_pending_without_stock(self):
        self.assertEqual(self.service.cancel_movement(10).estado, "ANULADO")
        self.repo.lock_inventory.assert_not_called()
        self.repo.create_inventory.assert_not_called()
        self.db.commit.assert_called_once()
        self.assertGreater(self.movement.updated_at, datetime(2026, 1, 1))

    def test_cancel_confirmed_rejected(self):
        self.movement.estado = "CONFIRMADO"
        with self.assertRaises(MovementConflictError):
            self.service.cancel_movement(10)
        self.db.commit.assert_not_called()

    def test_second_cancel_rejected(self):
        self.service.cancel_movement(10)
        with self.assertRaises(MovementConflictError):
            self.service.cancel_movement(10)

    def test_revalidate_on_confirmation(self):
        self.user.estado = False
        with self.assertRaises(MovementValidationError):
            self.service.confirm_movement(10)
        self.repo.lock_inventory.assert_not_called()

    def test_create_destination_when_absent(self):
        for kind in ("ENTRADA", "AJUSTE_POSITIVO", "TRANSFERENCIA"):
            self.configure(kind)
            self.repo.lock_inventory.side_effect = lambda branch, variant: self.origin if branch == 1 else None
            created = SimpleNamespace(stock_actual=0, stock_reservado=0, stock_minimo=0)
            self.repo.create_inventory.return_value = created
            with self.subTest(kind=kind):
                self.service.confirm_movement(10)
                self.assertEqual(created.stock_actual, 4)
                self.repo.create_inventory.assert_called_with(2, 3)

    def test_missing_origin_never_created(self):
        for kind in ("SALIDA", "AJUSTE_NEGATIVO", "TRANSFERENCIA"):
            self.configure(kind)
            self.repo.lock_inventory.side_effect = None
            self.repo.lock_inventory.return_value = None
            with self.subTest(kind=kind), self.assertRaises(MovementConflictError):
                self.service.confirm_movement(10)
        self.repo.create_inventory.assert_not_called()

    def test_lock_order_with_multiple_details_and_reverse_transfer(self):
        self.configure("TRANSFERENCIA")
        self.movement.id_sucursal_origen, self.movement.id_sucursal_destino = 2, 1
        self.assignment.id_sucursal = 2
        self.details.append(SimpleNamespace(**(detail() | {"id_variante_producto": 1})))
        self.repo.lock_inventory.side_effect = lambda *args: SimpleNamespace(stock_actual=10, stock_reservado=0)
        self.service.confirm_movement(10)
        self.assertEqual([call.args for call in self.repo.lock_inventory.call_args_list],
                         [(1, 1), (1, 3), (2, 1), (2, 3)])

    def test_all_details_checked_before_mutating_stock(self):
        self.configure("TRANSFERENCIA")
        self.details.append(SimpleNamespace(**(detail() | {"id_variante_producto": 4})))
        self.repo.lock_inventory.side_effect = [self.origin, None]
        with self.assertRaises(MovementConflictError):
            self.service.confirm_movement(10)
        self.assertEqual(self.origin.stock_actual, 10)
        self.assertEqual(self.destination.stock_actual, 2)
        self.db.rollback.assert_called_once()

    def test_rollback_create_persistence_error(self):
        self.repo.create.side_effect = SQLAlchemyError("private database information")
        with self.assertRaises(MovementPersistenceError):
            self.service.create_movement(payload())
        self.db.rollback.assert_called_once()
        self.db.commit.assert_not_called()

    def test_rollback_confirm_flush_failure(self):
        self.db.flush.side_effect = SQLAlchemyError("failed")
        with self.assertRaises(MovementPersistenceError):
            self.service.confirm_movement(10)
        self.db.rollback.assert_called_once()
        self.db.commit.assert_not_called()

    def test_rollback_commit_failure(self):
        self.db.commit.side_effect = SQLAlchemyError("failed")
        with self.assertRaises(MovementPersistenceError):
            self.service.cancel_movement(10)
        self.db.rollback.assert_called_once()

    def test_concurrent_destination_insert_rolls_back(self):
        self.repo.lock_inventory.side_effect = None
        self.repo.lock_inventory.return_value = None
        self.repo.create_inventory.side_effect = IntegrityError("insert", {}, Exception("unique"))
        with self.assertRaises(MovementConflictError):
            self.service.confirm_movement(10)
        self.assertEqual(self.movement.estado, "PENDIENTE")
        self.db.rollback.assert_called_once()
        self.db.commit.assert_not_called()

    def test_deadlock_is_conflict(self):
        self.repo.lock_inventory.side_effect = DBAPIError("select", {}, SimpleNamespace(pgcode="40P01"))
        with self.assertRaises(MovementConflictError):
            self.service.confirm_movement(10)
        self.db.rollback.assert_called_once()

    def test_missing_movement_on_mutations(self):
        self.repo.get_movement.return_value = None
        for operation in (self.service.confirm_movement, self.service.cancel_movement):
            with self.assertRaises(MovementNotFoundError):
                operation(99)

    def test_detail_and_missing_detail(self):
        result = self.service.get_movement(10)
        self.assertEqual(result.detalles[0].sku, "SKU-3")
        self.assertEqual(result.nombre_empleado, "Ana Pérez")
        self.repo.get_detail.side_effect = None
        self.repo.get_detail.return_value = None
        with self.assertRaises(MovementNotFoundError):
            self.service.get_movement(99)

    def test_list_filters_and_pagination(self):
        filters = dict(search="ajuste", tipo_movimiento="ENTRADA", estado="PENDIENTE",
                       id_sucursal=2, id_variante_producto=3, fecha_desde=datetime(2026, 1, 1),
                       fecha_hasta=datetime(2026, 2, 1), page=2, page_size=2)
        self.repo.list_movements.return_value = ([header()], 3)
        data, pagination = self.service.list_movements(**filters)
        self.assertEqual(len(data), 1)
        self.assertEqual(pagination.total_pages, 2)
        self.repo.list_movements.assert_called_once_with(**filters)

    def test_empty_list(self):
        self.repo.list_movements.return_value = ([], 0)
        data, pagination = self.service.list_movements(page=1, page_size=20)
        self.assertEqual((data, pagination.total_pages), ([], 0))

    def test_invalid_date_range(self):
        with self.assertRaises(MovementValidationError):
            self.service.list_movements(fecha_desde=datetime(2026, 2, 1), fecha_hasta=datetime(2026, 1, 1))

    def test_aware_dates_normalized(self):
        self.repo.list_movements.return_value = ([], 0)
        self.service.list_movements(fecha_desde=datetime(2026, 1, 1, tzinfo=timezone.utc))
        self.assertIsNone(self.repo.list_movements.call_args.kwargs["fecha_desde"].tzinfo)


def sql(statement):
    return str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


class MovementRepositoryTests(TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.repo = InventoryMovementRepository(self.db)

    def test_movement_lock_excludes_sale(self):
        self.repo.get_movement(10, for_update=True)
        statement = sql(self.db.scalar.call_args.args[0])
        self.assertIn("FOR UPDATE", statement)
        self.assertNotIn("'VENTA'", statement)
        self.assertIn("id_movimiento_inventario = 10", statement)

    def test_inventory_lock_uses_both_keys(self):
        self.repo.lock_inventory(2, 3)
        statement = sql(self.db.scalar.call_args.args[0])
        for fragment in ("FOR UPDATE", "id_sucursal = 2", "id_variante_producto = 3"):
            self.assertIn(fragment, statement)

    def test_create_inventory_zero_defaults_no_commit(self):
        inventory = self.repo.create_inventory(2, 3)
        self.assertEqual((inventory.stock_actual, inventory.stock_reservado, inventory.stock_minimo), (0, 0, 0))
        self.db.add.assert_called_once_with(inventory)
        self.db.flush.assert_called_once()
        self.db.commit.assert_not_called()

    def test_create_header_details_without_inventory(self):
        self.db.flush.side_effect = lambda: setattr(self.db.add.call_args.args[0], "id_movimiento_inventario", 10)
        movement = self.repo.create(payload())
        self.assertEqual(movement.estado, "PENDIENTE")
        rows = self.db.add_all.call_args.args[0]
        self.assertEqual((rows[0].id_movimiento_inventario, rows[0].cantidad), (10, 4))
        self.db.add.assert_called_once_with(movement)
        self.db.commit.assert_not_called()

    def test_list_sql_filters_count_and_order(self):
        self.db.scalar.return_value = 3
        self.db.execute.return_value.mappings.return_value.all.return_value = [header()]
        rows, total = self.repo.list_movements(
            search="ajuste", tipo_movimiento="ENTRADA", estado="PENDIENTE",
            id_sucursal=2, id_variante_producto=3, fecha_desde=datetime(2026, 1, 1),
            fecha_hasta=datetime(2026, 2, 1), page=2, page_size=2,
        )
        statement = sql(self.db.execute.call_args.args[0])
        for fragment in ("ILIKE", "id_sucursal_origen = 2 OR", "id_sucursal_destino = 2",
                         "JOIN t_detalle_movimiento_inventario", "id_variante_producto = 3",
                         "estado = 'PENDIENTE'", "tipo_movimiento = 'ENTRADA'",
                         "fecha_movimiento >=", "fecha_movimiento <=", "LIMIT 2 OFFSET 2",
                         "fecha_movimiento DESC", "id_movimiento_inventario DESC"):
            self.assertIn(fragment, statement)
        count = sql(self.db.scalar.call_args.args[0])
        self.assertIn("count(*)", count)
        self.assertIn("id_variante_producto = 3", count)
        self.assertNotIn("LIMIT", count)
        self.assertEqual((len(rows), total), (1, 3))

    def test_detail_joins(self):
        first, second = MagicMock(), MagicMock()
        first.mappings.return_value.one_or_none.return_value = header()
        second.mappings.return_value.all.return_value = [detail()]
        self.db.execute.side_effect = [first, second]
        self.assertEqual(self.repo.get_detail(10)["detalles"][0]["sku"], "SKU-3")
        statement = sql(self.db.execute.call_args.args[0])
        for table in ("t_variante_producto", "t_producto", "t_talla", "t_color"):
            self.assertIn("JOIN " + table, statement)

    def test_responsible_join_checks_all_existing_entities(self):
        self.repo.get_responsible(9)
        statement = sql(self.db.execute.call_args.args[0])
        for table in ("t_empleado", "t_usuario", "t_rol"):
            self.assertIn("LEFT OUTER JOIN " + table, statement)


class MovementRouteTests(TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.patcher = patch.object(routes, "AdminInventoryMovementService")
        self.service = self.patcher.start().return_value
        self.addCleanup(self.patcher.stop)
        self.data = header() | {"detalles": [detail()]}

    def operations(self, administrator):
        return (
            lambda: routes.list_movements(administrator=administrator, db=self.db),
            lambda: routes.get_movement(10, administrator=administrator, db=self.db),
            lambda: routes.create_movement(payload(), administrator=administrator, db=self.db),
            lambda: routes.confirm_movement(10, administrator=administrator, db=self.db),
            lambda: routes.cancel_movement(10, administrator=administrator, db=self.db),
        )

    def test_all_endpoints_success(self):
        self.service.get_movement.return_value = self.data
        self.service.create_movement.return_value = self.data
        self.service.confirm_movement.return_value = self.data | {"estado": "CONFIRMADO"}
        self.service.cancel_movement.return_value = self.data | {"estado": "ANULADO"}
        self.service.list_movements.return_value = ([header()], dict(page=1, page_size=20, total=1, total_pages=1))
        for operation in self.operations(SimpleNamespace(id_usuario=1)):
            self.assertTrue(operation().success)

    def test_all_endpoints_preserve_authentication_and_authorization_errors(self):
        for code in (401, 403):
            denied = JSONResponse(status_code=code, content={"success": False, "message": "Acceso denegado"})
            for operation in self.operations(denied):
                self.assertIs(operation(), denied)
        self.assertEqual(self.service.mock_calls, [])

    def test_error_mapping_and_safe_persistence_message(self):
        for error, code in ((MovementValidationError("invalid"), 400), (MovementNotFoundError("missing"), 404),
                            (MovementConflictError("conflict"), 409), (MovementPersistenceError("secret"), 500),
                            (SQLAlchemyError("secret"), 500)):
            for name in ("list_movements", "get_movement", "create_movement", "confirm_movement", "cancel_movement"):
                getattr(self.service, name).side_effect = error
            for operation in self.operations(SimpleNamespace(id_usuario=1)):
                response = operation()
                self.assertEqual(response.status_code, code)
                self.assertNotIn(b"secret", response.body)

    def test_openapi_security_registration_and_validation_limits(self):
        from app.main import app

        base = "/api/admin/inventory-movements"
        paths = app.openapi()["paths"]
        for path, method in ((base, "get"), (base, "post"),
                             (base + "/{id_movimiento_inventario}", "get"),
                             (base + "/{id_movimiento_inventario}/confirm", "patch"),
                             (base + "/{id_movimiento_inventario}/cancel", "patch")):
            operation = paths[path][method]
            self.assertTrue(operation["security"])
            for code in (400, 401, 403, 404, 409, 422, 500):
                self.assertIn(str(code), operation["responses"])
        self.assertIn("201", paths[base]["post"]["responses"])
        parameters = {item["name"]: item["schema"] for item in paths[base]["get"]["parameters"]}
        self.assertEqual(parameters["page"]["minimum"], 1)
        self.assertEqual(parameters["page_size"]["maximum"], 100)
        self.assertNotIn("VENTA", str(parameters["tipo_movimiento"]))
        for route in routes.router.routes:
            self.assertIn(require_administrator, [dependency.call for dependency in route.dependant.dependencies])
