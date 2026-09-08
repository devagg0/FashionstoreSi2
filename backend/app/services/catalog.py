"""Reglas de presentacion y negocio del catalogo publico de CU12."""

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from math import ceil
from typing import Mapping

from sqlalchemy.orm import Session

from app.repositories.catalog import CatalogRepository
from app.schemas.catalog import (
    CatalogCollectionData,
    CatalogColorData,
    CatalogImageData,
    CatalogPaginationData,
    CatalogProductAvailabilityData,
    CatalogProductData,
    CatalogProductDetailData,
    CatalogPromotionData,
    CatalogSizeData,
    CatalogSort,
    CatalogVariantAvailabilityData,
    CatalogVariantData,
)


MONEY = Decimal("0.01")


class CatalogProductNotFoundError(Exception):
    """El producto no existe o no esta publicado en el catalogo."""


class CatalogReferenceNotFoundError(Exception):
    """La sucursal o ciudad indicada no existe."""


class CatalogReferenceInactiveError(Exception):
    """La sucursal o ciudad indicada no esta disponible para el catalogo."""


class CatalogFilterError(Exception):
    """La combinacion de filtros no es valida."""


class CatalogService:
    """Construye respuestas publicas sin exponer datos administrativos."""

    SHORT_DESCRIPTION_LENGTH = 180

    def __init__(self, db: Session) -> None:
        self.repository = CatalogRepository(db)

    def list_products(
        self,
        *,
        search: str | None,
        section: str | None,
        category_id: int | None,
        size_id: int | None,
        color_id: int | None,
        min_price: Decimal | None,
        max_price: Decimal | None,
        on_promotion: bool | None,
        branch_id: int | None,
        city_id: int | None,
        sort: CatalogSort,
        page: int,
        page_size: int,
    ) -> tuple[list[CatalogProductData], CatalogPaginationData]:
        branch_name = self._validate_location(branch_id=branch_id, city_id=city_id)
        rows, total = self.repository.list_products(
            search=search,
            section=section,
            category_id=category_id,
            size_id=size_id,
            color_id=color_id,
            min_price=min_price,
            max_price=max_price,
            on_promotion=on_promotion,
            branch_id=branch_id,
            city_id=city_id,
            sort=sort,
            page=page,
            page_size=page_size,
        )
        product_ids = [row["id_producto"] for row in rows]
        variant_rows = self.repository.list_active_variants(
            product_ids, branch_id=branch_id
        )
        variants_by_product = self._group_by_product(variant_rows)
        data = [
            self._to_list_product(
                row,
                variants=variants_by_product[row["id_producto"]],
                branch_id=branch_id,
                branch_name=branch_name,
            )
            for row in rows
        ]
        return data, CatalogPaginationData(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=ceil(total / page_size) if total else 0,
        )

    def get_product(
        self, product_id: int, *, branch_id: int | None
    ) -> CatalogProductDetailData:
        self._validate_location(branch_id=branch_id, city_id=None)
        row = self.repository.get_active_product(product_id)
        if row is None:
            raise CatalogProductNotFoundError("Producto no encontrado")

        variant_rows = self.repository.list_active_variants(
            [product_id], branch_id=branch_id
        )
        promotions = [
            self._to_promotion(item, Decimal(row["precio_base"]))
            for item in self.repository.list_current_promotions(product_id)
        ]
        highlighted = promotions[0] if promotions else None
        images = [
            CatalogImageData.model_validate(item)
            for item in self.repository.list_images(product_id)
        ]
        variants = [
            self._to_variant(item, branch_id=branch_id) for item in variant_rows
        ]
        sizes, colors = self._variant_facets(variant_rows)

        return CatalogProductDetailData(
            id_producto=row["id_producto"],
            nombre=row["nombre"],
            descripcion=row["descripcion"],
            seccion=row["seccion"],
            id_categoria=row["id_categoria"],
            categoria=row["categoria"],
            id_temporada=row["id_temporada"],
            temporada=row["temporada"],
            precio_base=self._money(row["precio_base"]),
            precio_final=(
                highlighted.precio_resultante
                if highlighted is not None
                else self._money(row["precio_base"])
            ),
            tiene_promocion=highlighted is not None,
            promociones_vigentes=promotions,
            promocion_destacada=highlighted,
            porcentaje_descuento=(
                highlighted.porcentaje_descuento if highlighted else None
            ),
            monto_descuento=(highlighted.monto_descuento if highlighted else None),
            imagen_principal=row["imagen_principal"],
            galeria=images,
            variantes=variants,
            tallas=sizes,
            colores=colors,
            colecciones=[
                CatalogCollectionData.model_validate(item)
                for item in self.repository.list_active_collections(product_id)
            ],
        )

    def _validate_location(
        self, *, branch_id: int | None, city_id: int | None
    ) -> str | None:
        city = None
        if city_id is not None:
            city = self.repository.get_city(city_id)
            if city is None:
                raise CatalogReferenceNotFoundError("Ciudad no encontrada")
            if not city.estado:
                raise CatalogReferenceInactiveError("La ciudad no esta activa")

        if branch_id is None:
            return None
        branch = self.repository.get_branch(branch_id)
        if branch is None:
            raise CatalogReferenceNotFoundError("Sucursal no encontrada")
        if not branch.estado:
            raise CatalogReferenceInactiveError("La sucursal no esta activa")
        if city is not None and branch.id_ciudad != city.id_ciudad:
            raise CatalogFilterError("La sucursal no pertenece a la ciudad indicada")
        return branch.nombre

    def _to_list_product(
        self,
        row: Mapping,
        *,
        variants: list[Mapping],
        branch_id: int | None,
        branch_name: str | None,
    ) -> CatalogProductData:
        base_price = self._money(row["precio_base"])
        promotion = (
            self._to_promotion(row, base_price)
            if row["id_promocion"] is not None
            else None
        )
        sizes, colors = self._variant_facets(variants)
        availability = None
        if branch_id is not None:
            quantity = sum(self._available_quantity(item) for item in variants)
            availability = CatalogProductAvailabilityData(
                id_sucursal=branch_id,
                sucursal=branch_name or "",
                estado="DISPONIBLE" if quantity > 0 else "AGOTADO",
                cantidad_disponible=quantity,
            )
        return CatalogProductData(
            id_producto=row["id_producto"],
            nombre=row["nombre"],
            descripcion_corta=self._short_description(row["descripcion"]),
            seccion=row["seccion"],
            id_categoria=row["id_categoria"],
            categoria=row["categoria"],
            precio_base=base_price,
            precio_final=(promotion.precio_resultante if promotion else base_price),
            tiene_promocion=promotion is not None,
            promocion_destacada=promotion,
            porcentaje_descuento=(
                promotion.porcentaje_descuento if promotion else None
            ),
            monto_descuento=(promotion.monto_descuento if promotion else None),
            imagen_principal=row["imagen_principal"],
            colores_disponibles=colors,
            tallas_disponibles=sizes,
            disponibilidad_sucursal=availability,
        )

    @classmethod
    def _to_promotion(
        cls, row: Mapping, base_price: Decimal
    ) -> CatalogPromotionData:
        value = cls._money(row["valor_descuento"])
        result_price = cls._money(row["precio_resultante"])
        amount = cls._money(max(base_price - result_price, Decimal("0")))
        return CatalogPromotionData(
            id_promocion=row["id_promocion"],
            nombre=row["promocion_nombre"],
            codigo=row["promocion_codigo"],
            descripcion=row["promocion_descripcion"],
            tipo_descuento=row["tipo_descuento"],
            valor=value,
            porcentaje_descuento=(
                value if row["tipo_descuento"] == "PORCENTAJE" else None
            ),
            monto_descuento=amount,
            precio_resultante=result_price,
            fecha_inicio=row["fecha_inicio"],
            fecha_fin=row["fecha_fin"],
            acumulable=row["acumulable"],
        )

    @staticmethod
    def _to_variant(row: Mapping, *, branch_id: int | None) -> CatalogVariantData:
        availability = None
        if branch_id is not None:
            quantity = CatalogService._available_quantity(row)
            availability = CatalogVariantAvailabilityData(
                id_sucursal=branch_id,
                estado="DISPONIBLE" if quantity > 0 else "AGOTADO",
                cantidad_disponible=quantity,
            )
        return CatalogVariantData(
            id_variante_producto=row["id_variante_producto"],
            sku=row["sku"],
            talla=CatalogSizeData(
                id_talla=row["id_talla"], nombre=row["talla"]
            ),
            color=CatalogColorData(
                id_color=row["id_color"],
                nombre=row["color"],
                codigo_hex=row["codigo_hex"],
            ),
            disponibilidad_sucursal=availability,
        )

    @staticmethod
    def _variant_facets(
        variants: list[Mapping],
    ) -> tuple[list[CatalogSizeData], list[CatalogColorData]]:
        sizes: dict[int, CatalogSizeData] = {}
        colors: dict[int, CatalogColorData] = {}
        for item in variants:
            sizes.setdefault(
                item["id_talla"],
                CatalogSizeData(id_talla=item["id_talla"], nombre=item["talla"]),
            )
            colors.setdefault(
                item["id_color"],
                CatalogColorData(
                    id_color=item["id_color"],
                    nombre=item["color"],
                    codigo_hex=item["codigo_hex"],
                ),
            )
        return list(sizes.values()), list(colors.values())

    @staticmethod
    def _group_by_product(rows) -> dict[int, list[Mapping]]:
        grouped: dict[int, list[Mapping]] = defaultdict(list)
        for row in rows:
            grouped[row["id_producto"]].append(row)
        return grouped

    @staticmethod
    def _available_quantity(row: Mapping) -> int:
        return max(
            int(row.get("stock_actual", 0)) - int(row.get("stock_reservado", 0)),
            0,
        )

    @classmethod
    def _short_description(cls, description: str | None) -> str | None:
        if description is None or len(description) <= cls.SHORT_DESCRIPTION_LENGTH:
            return description
        shortened = description[: cls.SHORT_DESCRIPTION_LENGTH - 3].rstrip()
        return f"{shortened}..."

    @staticmethod
    def _money(value: Decimal) -> Decimal:
        return Decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)
