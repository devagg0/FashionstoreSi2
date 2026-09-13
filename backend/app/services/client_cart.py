"""CU19: intención de compra sin reserva, venta ni modificación de inventario."""

from datetime import datetime, timezone

from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.repositories.catalog import CatalogRepository
from app.repositories.client_cart import ClientCartRepository
from app.schemas.client_cart import CartData, CartItemData
from app.services.catalog import CatalogService


class CartAccessError(Exception):
    pass


class CartNotFoundError(Exception):
    pass


class CartValidationError(Exception):
    pass


class CartConflictError(Exception):
    pass


class CartPersistenceError(Exception):
    pass


class ClientCartService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = ClientCartRepository(db)
        self.catalog_repository = CatalogRepository(db)

    def _operation(self, operation, *, write=False):
        try:
            result = operation()
            if write:
                self.db.commit()
            return result
        except (CartAccessError, CartNotFoundError, CartValidationError, CartConflictError):
            self.db.rollback()
            raise
        except IntegrityError as error:
            self.db.rollback()
            raise CartConflictError("Conflicto concurrente en el carrito; reintente la operación.") from error
        except DBAPIError as error:
            self.db.rollback()
            code = getattr(error.orig, "sqlstate", None) or getattr(error.orig, "pgcode", None)
            if code in {"40001", "40P01", "55P03"}:
                raise CartConflictError("Conflicto concurrente; reintente la operación.") from error
            raise CartPersistenceError from error
        except Exception as error:
            self.db.rollback()
            raise CartPersistenceError from error

    def _cart(self, user_id: int, *, write=False):
        # Serializa escrituras del mismo cliente incluso cuando aún no hay carrito.
        # El bloqueo termina con commit/rollback; no se bloquea inventario.
        client = self.repository.get_client(user_id, for_update=write)
        if client is None:
            raise CartAccessError("Se requiere un perfil de cliente válido.")
        cart = self.repository.get_active_cart(client.id_cliente, for_update=write)
        if cart is not None and (cart.estado != "ACTIVO" or cart.id_cliente != client.id_cliente):
            raise CartConflictError("El carrito no está disponible para esta operación.")
        return client, cart

    def _available(self, product_id: int, variant_id: int) -> int:
        return max((
            CatalogService._available_quantity(row)
            for row in self.repository.availability(product_id, variant_id)
        ), default=0)

    def _validate(self, variant_id: int, quantity: int):
        if type(quantity) is not int or not 1 <= quantity <= 2147483647:
            raise CartValidationError("La cantidad debe ser un entero positivo válido.")
        row = self.repository.get_variant(variant_id)
        if row is None or row[1] is None:
            raise CartNotFoundError("Variante o producto no encontrado.")
        variant, product = row
        if not variant.estado or not product.estado:
            raise CartValidationError("El producto o la variante están inactivos.")
        if quantity > self._available(product.id_producto, variant_id):
            raise CartConflictError("Stock disponible insuficiente para la cantidad solicitada.")

    def _data(self, cart):
        if cart is None:
            return CartData()
        items = []
        prices = {}
        for row in self.repository.list_items(cart.id_carrito):
            product_id = row["id_producto"]
            if product_id not in prices:
                base = CatalogService._money(row["precio"])
                # Misma consulta, orden y presentación CU12, incluso para productos
                # luego desactivados. No se inventa una política de descuentos.
                promotions = self.catalog_repository.list_current_promotions(product_id)
                promotion = CatalogService._to_promotion(promotions[0], base) if promotions else None
                final = promotion.precio_resultante if promotion else base
                prices[product_id] = base, final, promotion
            base, final, promotion = prices[product_id]
            active = row["estado_producto"] and row["estado_variante"]
            items.append(CartItemData(
                **{key: row[key] for key in (
                    "id_detalle_carrito", "id_variante_producto", "id_producto",
                    "nombre_producto", "sku", "imagen_principal", "cantidad",
                    "estado_producto", "estado_variante",
                )},
                talla=dict(id_talla=row["id_talla"], nombre=row["talla"]),
                color=dict(id_color=row["id_color"], nombre=row["color"], codigo_hex=row["codigo_hex"]),
                precio_base=base, precio_final=final, promocion=promotion,
                subtotal_linea=CatalogService._money(row["cantidad"] * final),
                disponibilidad_actual=self._available(product_id, row["id_variante_producto"]) if active else 0,
            ))
        zero = CatalogService._money(0)
        return CartData(
            id_carrito=cart.id_carrito, estado="ACTIVO", items=items,
            cantidad_items=len(items), cantidad_unidades=sum(item.cantidad for item in items),
            subtotal=CatalogService._money(sum((item.cantidad * item.precio_base for item in items), zero)),
            descuento_total=CatalogService._money(sum((item.cantidad * (item.precio_base - item.precio_final) for item in items), zero)),
            total=CatalogService._money(sum((item.subtotal_linea for item in items), zero)),
        )

    def get_cart(self, user_id: int):
        return self._operation(lambda: self._data(self._cart(user_id)[1]))

    def _finish(self, cart):
        cart.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        self.db.flush()
        return self._data(cart)

    def add_item(self, user_id: int, payload):
        def operation():
            client, cart = self._cart(user_id, write=True)
            item = self.repository.get_item(cart.id_carrito, payload.id_variante_producto) if cart else None
            quantity = payload.cantidad + (item.cantidad if item else 0)
            self._validate(payload.id_variante_producto, quantity)
            if cart is None:
                cart = self.repository.create_cart(client.id_cliente)
            if item is None:
                self.repository.create_item(cart.id_carrito, payload.id_variante_producto, quantity)
            else:
                self.repository.update_quantity(item, quantity)
            return self._finish(cart)
        return self._operation(operation, write=True)

    def _existing_item(self, cart, variant_id):
        item = self.repository.get_item(cart.id_carrito, variant_id) if cart else None
        if item is None:
            raise CartNotFoundError("El artículo no existe en tu carrito activo.")
        return item

    def update_item(self, user_id: int, variant_id: int, payload):
        def operation():
            _, cart = self._cart(user_id, write=True)
            item = self._existing_item(cart, variant_id)
            self._validate(variant_id, payload.cantidad)
            self.repository.update_quantity(item, payload.cantidad)
            return self._finish(cart)
        return self._operation(operation, write=True)

    def delete_item(self, user_id: int, variant_id: int):
        def operation():
            _, cart = self._cart(user_id, write=True)
            item = self._existing_item(cart, variant_id)
            self.repository.delete_item(item)
            return self._finish(cart)
        return self._operation(operation, write=True)

    def clear_cart(self, user_id: int):
        def operation():
            _, cart = self._cart(user_id, write=True)
            if cart is None:
                return CartData()
            self.repository.clear_items(cart.id_carrito)
            return self._finish(cart)
        return self._operation(operation, write=True)
