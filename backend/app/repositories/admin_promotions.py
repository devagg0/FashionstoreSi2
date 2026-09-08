"""Persistencia de CU11 sobre promociones y sus productos."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.promotion import Promotion
from app.models.promotion_product import PromotionProduct
from app.schemas.admin_promotions import Validity


class AdminPromotionRepository:
    """Centraliza consultas y mutaciones de ``t_promocion``."""

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _apply_filters(
        statement: Select,
        *,
        search: str | None,
        state: bool | None,
        validity: Validity | None,
    ) -> Select:
        if search and search.strip():
            escaped = (
                search.strip()
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            pattern = f"%{escaped}%"
            statement = statement.where(
                or_(
                    Promotion.nombre.ilike(pattern, escape="\\"),
                    Promotion.codigo.ilike(pattern, escape="\\"),
                    Promotion.descripcion.ilike(pattern, escape="\\"),
                )
            )
        if state is not None:
            statement = statement.where(Promotion.estado.is_(state))
        if validity == "PROGRAMADA":
            statement = statement.where(Promotion.fecha_inicio > func.now())
        elif validity == "VIGENTE":
            statement = statement.where(
                Promotion.fecha_inicio <= func.now(),
                Promotion.fecha_fin >= func.now(),
            )
        elif validity == "EXPIRADA":
            statement = statement.where(Promotion.fecha_fin < func.now())
        return statement

    @staticmethod
    def _summary_columns():
        product_count = (
            select(func.count(PromotionProduct.id_promocion_producto))
            .where(PromotionProduct.id_promocion == Promotion.id_promocion)
            .correlate(Promotion)
            .scalar_subquery()
        )
        return (
            Promotion.id_promocion,
            Promotion.nombre,
            Promotion.codigo,
            Promotion.descripcion,
            Promotion.tipo_descuento,
            Promotion.valor,
            Promotion.fecha_inicio,
            Promotion.fecha_fin,
            Promotion.acumulable,
            Promotion.estado,
            product_count.label("total_productos"),
            Promotion.created_at,
            Promotion.updated_at,
        )

    def list_promotions(
        self,
        *,
        search: str | None,
        state: bool | None,
        validity: Validity | None,
        page: int,
        page_size: int,
    ):
        filters = {"search": search, "state": state, "validity": validity}
        statement = self._apply_filters(
            select(*self._summary_columns()), **filters
        )
        count_statement = self._apply_filters(
            select(func.count(Promotion.id_promocion)), **filters
        )
        rows = self.db.execute(
            statement.order_by(Promotion.nombre, Promotion.id_promocion)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).mappings().all()
        total = self.db.scalar(count_statement) or 0
        return rows, total

    def get_by_id(
        self, promotion_id: int, *, for_update: bool = False
    ) -> Promotion | None:
        statement = select(Promotion).where(Promotion.id_promocion == promotion_id)
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def get_summary(self, promotion_id: int):
        return self.db.execute(
            select(*self._summary_columns()).where(
                Promotion.id_promocion == promotion_id
            )
        ).mappings().one_or_none()

    def get_by_code(
        self,
        code: str,
        *,
        exclude_promotion_id: int | None = None,
        for_update: bool = False,
    ) -> Promotion | None:
        statement = select(Promotion).where(
            func.lower(Promotion.codigo) == code.lower()
        )
        if exclude_promotion_id is not None:
            statement = statement.where(
                Promotion.id_promocion != exclude_promotion_id
            )
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def create_promotion(
        self,
        *,
        nombre: str,
        codigo: str | None,
        descripcion: str | None,
        tipo_descuento: str,
        valor: Decimal,
        fecha_inicio: datetime,
        fecha_fin: datetime,
        acumulable: bool,
    ) -> Promotion:
        promotion = Promotion(
            nombre=nombre,
            codigo=codigo,
            descripcion=descripcion,
            tipo_descuento=tipo_descuento,
            valor=valor,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            acumulable=acumulable,
            estado=True,
        )
        self.db.add(promotion)
        self.db.flush()
        return promotion

    def update_promotion(self, promotion: Promotion, **values: object) -> None:
        for field, value in values.items():
            setattr(promotion, field, value)
        promotion.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        self.db.flush()

    def update_status(self, promotion: Promotion, *, state: bool) -> None:
        promotion.estado = state
        promotion.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        self.db.flush()

    def touch_promotion(self, promotion: Promotion) -> None:
        """Registra que sus asociaciones fueron modificadas."""
        promotion.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        self.db.flush()

    def list_products(self, promotion_id: int):
        return self.db.execute(
            select(
                PromotionProduct.id_promocion_producto,
                Product.id_producto,
                Product.nombre,
                Product.seccion,
                Product.precio,
                Product.estado,
            )
            .join(
                Product,
                Product.id_producto == PromotionProduct.id_producto,
            )
            .where(PromotionProduct.id_promocion == promotion_id)
            .order_by(Product.nombre, Product.id_producto)
        ).mappings().all()

    def get_product(
        self, product_id: int, *, for_update: bool = False
    ) -> Product | None:
        statement = select(Product).where(Product.id_producto == product_id)
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def get_association(
        self,
        promotion_id: int,
        product_id: int,
        *,
        for_update: bool = False,
    ) -> PromotionProduct | None:
        statement = select(PromotionProduct).where(
            PromotionProduct.id_promocion == promotion_id,
            PromotionProduct.id_producto == product_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def add_product(self, promotion_id: int, product_id: int) -> PromotionProduct:
        association = PromotionProduct(
            id_promocion=promotion_id,
            id_producto=product_id,
        )
        self.db.add(association)
        self.db.flush()
        return association
