"""CU20: intencion de venta, sin cobros ni descuento fisico de inventario."""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy.exc import DBAPIError, IntegrityError

from app.repositories.staff_sales import StaffSalesRepository
from app.schemas.staff_sales import (
    SaleBranchData, SaleData, SaleQuoteData, SaleQuoteLineData, SaleReleaseData,
)
from app.services.catalog import CatalogProductNotFoundError, CatalogService


class SaleError(Exception):
    def __init__(self, status_code, message):
        super().__init__(message)
        self.status_code = status_code


class StaffSalesService:
    def __init__(self, db):
        self.db = db
        self.repository = StaffSalesRepository(db)
        self.catalog = CatalogService(db)

    def _run(self, operation, *, write=False):
        try:
            result = operation()
            if write:
                self.db.commit()
            return result
        except SaleError:
            self.db.rollback()
            raise
        except IntegrityError as error:
            self.db.rollback()
            raise SaleError(409, "Venta, reserva o movimiento duplicado; verifique la operacion") from error
        except DBAPIError as error:
            self.db.rollback()
            code = getattr(error.orig, "sqlstate", None) or getattr(error.orig, "pgcode", None)
            if code in {"40001", "40P01", "55P03"}:
                raise SaleError(409, "Conflicto concurrente; reintente la operacion") from error
            raise SaleError(500, "No fue posible procesar la venta") from error
        except Exception as error:
            self.db.rollback()
            raise SaleError(500, "No fue posible procesar la venta") from error

    def _context(self, user_id, branch_id=None, *, for_update=False):
        employee = self.repository.get_employee(user_id)
        if employee is None:
            raise SaleError(403, "Perfil de empleado no encontrado")
        branches = [SaleBranchData.model_validate(row) for row in
                    self.repository.branches(employee.id_empleado, for_update=for_update)]
        if branch_id is not None and self.repository.get_branch(branch_id) is None:
            raise SaleError(404, "Sucursal no encontrada")
        if not branches:
            raise SaleError(403, "El cajero no tiene asignaciones activas en sucursales activas")
        return employee, branches

    def list_branches(self, user_id):
        return self._run(lambda: self._context(user_id)[1])

    @staticmethod
    def _choose_branch(branches, branch_id):
        if branch_id is None:
            if len(branches) != 1:
                raise SaleError(422, "Seleccione una de sus sucursales activas")
            return branches[0]
        branch = next((row for row in branches if row.id_sucursal == branch_id), None)
        if branch is None:
            raise SaleError(403, "Sucursal no autorizada o inactiva")
        return branch

    def _prepare(self, user_id, payload, *, for_update=False):
        employee, branches = self._context(user_id, payload.id_sucursal, for_update=for_update)
        branch = self._choose_branch(branches, payload.id_sucursal)
        quantities = {item.id_variante_producto: item.cantidad for item in payload.items}
        reservation = None
        reserved = {}
        if payload.id_reserva is not None:
            reservation = self.repository.get_reservation(payload.id_reserva, for_update=for_update)
            if reservation is None:
                raise SaleError(404, "Reserva no encontrada")
            if reservation.id_sucursal != branch.id_sucursal:
                raise SaleError(403, "La reserva no pertenece a la sucursal de la venta")
            if reservation.estado != "ATENDIDA":
                raise SaleError(409, "La reserva debe estar ATENDIDA")
            if self.repository.sale_for_reservation(reservation.id_reserva) is not None:
                raise SaleError(409, "La reserva ya tiene una venta asociada")
            reserved = {row.id_variante_producto: row for row in
                        self.repository.reservation_details(reservation.id_reserva)}
            for variant_id, quantity in quantities.items():
                if variant_id not in reserved:
                    raise SaleError(422, "La variante no pertenece a la reserva")
                if quantity > reserved[variant_id].cantidad:
                    raise SaleError(422, "La cantidad de compra supera la reservada")

        variant_ids = sorted(reserved if reservation is not None else quantities)
        inventories = {row.id_variante_producto: row for row in self.repository.inventories(
            branch.id_sucursal, variant_ids, for_update=for_update,
        )}
        if set(inventories) != set(variant_ids):
            raise SaleError(409 if reservation else 404, "No existe inventario de la variante en la sucursal")
        releases = []
        for variant_id in variant_ids:
            inventory = inventories[variant_id]
            if reservation is not None:
                original = reserved[variant_id].cantidad
                if inventory.stock_reservado < original or inventory.stock_actual < inventory.stock_reservado:
                    raise SaleError(409, "El stock reservado es inconsistente")
                quantity = quantities.get(variant_id, 0)
                releases.append(SaleReleaseData(
                    id_variante_producto=variant_id, cantidad_reservada=original,
                    cantidad_compra=quantity, cantidad_liberar=original - quantity,
                ))
            elif quantities[variant_id] > inventory.stock_actual - inventory.stock_reservado:
                raise SaleError(409, "Stock disponible insuficiente en la sucursal")

        lines = []
        prices = {}
        for variant_id in sorted(quantities):
            row = self.repository.variant(variant_id)
            if row is None:
                raise SaleError(404, "Variante no encontrada")
            variant, product, size, color = row
            if product is None:
                raise SaleError(404, "Producto no encontrado")
            if reservation is None and (not product.estado or not variant.estado):
                raise SaleError(422, "El producto o la variante estan inactivos")
            promotion_id = None
            discount = Decimal("0.00")
            if reservation is not None:
                price = CatalogService._money(reserved[variant_id].precio_unitario)
            else:
                if product.id_producto not in prices:
                    try:
                        prices[product.id_producto] = self.catalog.get_product(product.id_producto, branch_id=None)
                    except CatalogProductNotFoundError as error:
                        raise SaleError(422, "El producto ya no esta activo") from error
                priced = prices[product.id_producto]
                price = CatalogService._money(priced.precio_base)
                discount = price - CatalogService._money(priced.precio_final)
                if priced.promocion_destacada is not None:
                    promotion_id = priced.promocion_destacada.id_promocion
            quantity = quantities[variant_id]
            inventory = inventories[variant_id]
            lines.append(SaleQuoteLineData(
                id_variante_producto=variant_id, sku=variant.sku, producto=product.nombre,
                talla=size, color=color, cantidad=quantity, precio_unitario=price,
                descuento_unitario=discount, id_promocion=promotion_id,
                subtotal_linea=quantity * (price - discount),
                cantidad_disponible=(reserved[variant_id].cantidad if reservation else
                                     inventory.stock_actual - inventory.stock_reservado),
            ))
        subtotal = sum((line.cantidad * line.precio_unitario for line in lines), Decimal("0.00"))
        discount = sum((line.cantidad * line.descuento_unitario for line in lines), Decimal("0.00"))
        if subtotal > Decimal("9999999999.99"):
            raise SaleError(422, "El importe supera el limite admitido por la venta")
        quote = SaleQuoteData(
            sucursal=branch, id_empleado=employee.id_empleado,
            id_cliente=reservation.id_cliente if reservation else None,
            id_reserva=payload.id_reserva, detalles=lines, liberaciones=releases,
            subtotal=subtotal, descuento_total=discount, total=subtotal-discount,
        )
        return quote, inventories

    def quote(self, user_id, payload):
        return self._run(lambda: self._prepare(user_id, payload)[0])

    @staticmethod
    def sale_number(user_id, key: UUID):
        # La clave es estable entre reintentos; UNIQUE resuelve carreras entre procesos.
        return f"VTA-{user_id}-{key.hex.upper()}"

    def create(self, user_id, payload, key: UUID):
        def operation():
            quote, inventories = self._prepare(user_id, payload, for_update=True)
            number = self.sale_number(user_id, key)
            if self.repository.sale_for_number(number) is not None:
                raise SaleError(409, "Esta solicitud de venta ya fue registrada")
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            for release in quote.liberaciones:
                if release.cantidad_liberar:
                    inventory = inventories[release.id_variante_producto]
                    inventory.stock_reservado -= release.cantidad_liberar
                    inventory.updated_at = now
            sale = self.repository.create_sale(
                id_sucursal=quote.sucursal.id_sucursal, id_empleado=quote.id_empleado,
                id_cliente=quote.id_cliente, id_reserva=quote.id_reserva,
                numero_venta=number, estado="PENDIENTE", subtotal=quote.subtotal,
                descuento_total=quote.descuento_total, total=quote.total, fecha_venta=now,
            )
            items = [line.model_dump(include={
                "id_variante_producto", "cantidad", "precio_unitario",
                "descuento_unitario", "id_promocion", "subtotal_linea",
            }) for line in quote.detalles]
            self.repository.create_details(sale.id_venta, items)
            self.repository.create_movement(sale, quote.sucursal.id_empleado_sucursal, items)
            # Materializar y validar la respuesta antes del unico commit.
            return SaleData.model_validate(self.repository.detail(sale))
        return self._run(operation, write=True)

    def get_sale(self, user_id, sale_id):
        def operation():
            _, branches = self._context(user_id)
            sale = self.repository.get_sale(sale_id)
            if sale is None:
                raise SaleError(404, "Venta no encontrada")
            self._choose_branch(branches, sale.id_sucursal)
            return SaleData.model_validate(self.repository.detail(sale))
        return self._run(operation)
