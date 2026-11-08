from sqlalchemy import select, func
from sqlalchemy.exc import OperationalError
from app.models.returns import Return, ReturnDetail, Refund
from app.models.branch import Branch
from app.models.branch_inventory import BranchInventory
from app.models.color import Color
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.sale import Sale
from app.models.size import Size

class ReturnsRepository:
    def __init__(self, db):
        self.db = db

    def lock(self, return_id):
        return self.db.scalar(select(Return).where(Return.id_devolucion == return_id)
            .with_for_update().execution_options(populate_existing=True))

    def details(self, return_id):
        return self.db.scalars(select(ReturnDetail).where(ReturnDetail.id_devolucion == return_id)
            .order_by(ReturnDetail.id_variante_producto)).all()

    def refunds(self, return_id):
        return self.db.scalars(select(Refund).where(Refund.id_devolucion == return_id)
            .with_for_update().execution_options(populate_existing=True)).all()

    def used(self, sale_id, variant_id):
        return self.db.scalar(select(func.coalesce(func.sum(ReturnDetail.cantidad), 0))
            .join(Return, Return.id_devolucion == ReturnDetail.id_devolucion)
            .where(Return.id_venta == sale_id, ReturnDetail.id_variante_producto == variant_id,
                   Return.estado != "RECHAZADA"))

    def reserved_money(self, payment_id, exclude=None):
        stmt = select(func.coalesce(func.sum(Refund.monto), 0)).where(
            Refund.id_pago == payment_id, Refund.estado.in_(("PENDIENTE", "APROBADO")))
        if exclude is not None:
            stmt = stmt.where(Refund.id_reembolso != exclude)
        return self.db.scalar(stmt)

    def add(self, model, **values):
        row = model(**values)
        self.db.add(row)
        self.db.flush()
        return row

    def replacement_variant(self, variant_id: int, branch_id: int):
        row = self.db.execute(
            select(ProductVariant, Product, Size, Color)
            .join(Product, Product.id_producto == ProductVariant.id_producto)
            .join(Size, Size.id_talla == ProductVariant.id_talla)
            .join(Color, Color.id_color == ProductVariant.id_color)
            .where(ProductVariant.id_variante_producto == variant_id)
        ).one_or_none()
        if row is None:
            return None
        variant, product, size, color = row
        inventory = self.db.scalar(
            select(BranchInventory).where(
                BranchInventory.id_sucursal == branch_id,
                BranchInventory.id_variante_producto == variant_id,
            )
        )
        return {
            "variant": variant,
            "product": product,
            "size": size,
            "color": color,
            "inventory": inventory,
        }

    def available_exchange_variants(self, branch_id: int, empresa_id: int | None = None):
        stmt = (
            select(ProductVariant, Product, Size, Color, BranchInventory)
            .join(Product, Product.id_producto == ProductVariant.id_producto)
            .join(Size, Size.id_talla == ProductVariant.id_talla)
            .join(Color, Color.id_color == ProductVariant.id_color)
            .join(
                BranchInventory,
                (BranchInventory.id_variante_producto == ProductVariant.id_variante_producto)
                & (BranchInventory.id_sucursal == branch_id),
            )
            .where(
                ProductVariant.estado.is_(True),
                Product.estado.is_(True),
                Size.estado.is_(True),
                Color.estado.is_(True),
                BranchInventory.stock_actual > BranchInventory.stock_reservado,
            )
            .order_by(Product.nombre.asc(), Size.id_talla.asc(), Color.nombre.asc())
        )
        if empresa_id is not None:
            stmt = stmt.where(
                ProductVariant.empresa_id == empresa_id,
                Product.empresa_id == empresa_id,
            )
        return self.db.execute(stmt).all()

    def catalog_metadata(self, variant_ids: list[int], branch_id: int | None = None) -> dict[int, dict]:
        if not variant_ids:
            return {}
        try:
            with self.db.begin_nested():
                rows = self.db.execute(
                    select(ProductVariant, Product, Size, Color)
                    .outerjoin(Product, Product.id_producto == ProductVariant.id_producto)
                    .outerjoin(Size, Size.id_talla == ProductVariant.id_talla)
                    .outerjoin(Color, Color.id_color == ProductVariant.id_color)
                    .where(ProductVariant.id_variante_producto.in_(variant_ids))
                ).all()
                inv_by_variant = {}
                if branch_id is not None:
                    inv_rows = self.db.scalars(
                        select(BranchInventory).where(
                            BranchInventory.id_sucursal == branch_id,
                            BranchInventory.id_variante_producto.in_(variant_ids),
                        )
                    ).all()
                    inv_by_variant = {i.id_variante_producto: i for i in inv_rows}
                result = {}
                for variant, product, size, color in rows:
                    inv = inv_by_variant.get(variant.id_variante_producto)
                    avail = max(0, (inv.stock_actual - inv.stock_reservado)) if inv is not None else 0
                    result[variant.id_variante_producto] = {
                        "id_variante_producto": variant.id_variante_producto,
                        "id_producto": variant.id_producto,
                        "nombre_producto": product.nombre if product else None,
                        "sku": variant.sku,
                        "id_talla": variant.id_talla,
                        "talla": size.nombre if size else None,
                        "id_color": variant.id_color,
                        "color": color.nombre if color else None,
                        "codigo_hex": color.codigo_hex if color else None,
                        "precio_unitario_actual": product.precio if product else None,
                        "stock_disponible_sucursal": avail,
                    }
                return result
        except OperationalError:
            return {}

    def branch_info(self, branch_id: int | None) -> dict | None:
        if branch_id is None:
            return None
        try:
            with self.db.begin_nested():
                branch = self.db.get(Branch, branch_id)
                if branch is None:
                    return None
                return {
                    "id_sucursal": branch.id_sucursal,
                    "nombre": branch.nombre,
                    "direccion": branch.direccion,
                    "telefono": branch.telefono,
                }
        except OperationalError:
            return None

    def client_returns(
        self,
        client_id: int,
        empresa_id: int | None = None,
        tipo: str | None = None,
        estado: str | None = None,
        sale_id: int | None = None,
        modalidad_entrega: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ):
        stmt = (
            select(Return)
            .join(Sale, Sale.id_venta == Return.id_venta)
            .where(Sale.id_cliente == client_id)
        )
        if empresa_id is not None:
            stmt = stmt.where(Sale.empresa_id == empresa_id)
        if tipo is not None:
            stmt = stmt.where(Return.tipo == tipo)
        if estado is not None:
            stmt = stmt.where(Return.estado == estado)
        if sale_id is not None:
            stmt = stmt.where(Return.id_venta == sale_id)
        if modalidad_entrega is not None:
            stmt = stmt.where(Return.modalidad_entrega == modalidad_entrega)
        return self.db.scalars(
            stmt.order_by(Return.created_at.desc(), Return.id_devolucion.desc())
            .limit(limit)
            .offset(offset)
        ).all()
