"""CU13: valida visibilidad y presenta disponibilidad, sin transacciones de escritura."""

from sqlalchemy.orm import Session

from app.repositories.catalog_availability import CatalogAvailabilityRepository
from app.schemas.catalog_availability import (
    AvailabilityProductData, AvailabilityVariantData, BranchAvailabilityData,
    CatalogAvailabilityData,
)
from app.schemas.catalog import CatalogColorData, CatalogSizeData
from app.services.catalog import CatalogService


class AvailabilityNotFoundError(Exception):
    pass


class AvailabilityValidationError(Exception):
    pass


class CatalogAvailabilityService:
    def __init__(self, db: Session):
        self.repository = CatalogAvailabilityRepository(db)

    def get_availability(self, product_id, *, id_variante_producto=None,
                         id_sucursal=None, id_ciudad=None, id_talla=None,
                         id_color=None):
        product = self.repository.get_product(product_id)
        if product is None or not product.estado:
            raise AvailabilityNotFoundError("Producto no encontrado")
        if id_variante_producto is not None:
            variant = self.repository.get_variant(id_variante_producto)
            if variant is None or not variant.estado:
                raise AvailabilityNotFoundError("Variante no encontrada")
            if variant.id_producto != product_id:
                raise AvailabilityValidationError("La variante no pertenece al producto")
        rows = self.repository.list_availability(
            product_id, id_variante_producto=id_variante_producto,
            id_sucursal=id_sucursal, id_ciudad=id_ciudad,
            id_talla=id_talla, id_color=id_color,
        )
        return CatalogAvailabilityData(
            producto=AvailabilityProductData(
                id_producto=product.id_producto, nombre=product.nombre, estado=product.estado,
            ),
            disponibilidad=[self._data(row) for row in rows],
        )

    @staticmethod
    def _data(row):
        return BranchAvailabilityData(
            variante=AvailabilityVariantData(
                id_variante_producto=row["id_variante_producto"], sku=row["sku"],
                talla=CatalogSizeData(id_talla=row["id_talla"], nombre=row["talla"]),
                color=CatalogColorData(id_color=row["id_color"], nombre=row["color"],
                                       codigo_hex=row["codigo_hex"]),
                estado=row["variante_estado"],
            ),
            id_sucursal=row["id_sucursal"], nombre_sucursal=row["nombre_sucursal"],
            id_ciudad=row["id_ciudad"], nombre_ciudad=row["nombre_ciudad"],
            stock_actual=row["stock_actual"], stock_reservado=row["stock_reservado"],
            # Reutilizacion exacta de CU12 sin modificar sus archivos.
            stock_disponible=CatalogService._available_quantity(row),
        )
