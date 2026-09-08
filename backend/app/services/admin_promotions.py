"""Reglas de negocio de CU11: gestion administrativa de promociones."""

from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal
from math import ceil

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.repositories.admin_promotions import AdminPromotionRepository
from app.schemas.admin_promotions import (
    AdminPromotionData,
    AdminPromotionDetailData,
    DiscountType,
    PromotionCreateRequest,
    PromotionPaginationData,
    PromotionProductData,
    PromotionProductsRequest,
    PromotionStatusUpdateRequest,
    PromotionUpdateRequest,
    Validity,
)


class PromotionNotFoundError(Exception):
    """La promocion solicitada no existe."""


class PromotionProductNotFoundError(Exception):
    """Un producto seleccionado no existe."""


class PromotionProductInactiveError(Exception):
    """Un producto seleccionado esta inactivo."""


class PromotionConflictError(Exception):
    """El codigo o una asociacion de producto ya existe."""


class PromotionBusinessRuleError(Exception):
    """Los cambios no forman una promocion valida."""


class AdminPromotionPersistenceError(Exception):
    """La operacion de promocion no pudo persistirse."""


DOMAIN_ERRORS = (
    PromotionNotFoundError,
    PromotionProductNotFoundError,
    PromotionProductInactiveError,
    PromotionConflictError,
    PromotionBusinessRuleError,
)


class AdminPromotionService:
    """Orquesta promociones globales y asociaciones a productos."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = AdminPromotionRepository(db)

    def list_promotions(
        self,
        *,
        search: str | None,
        state: bool | None,
        validity: Validity | None,
        page: int,
        page_size: int,
    ) -> tuple[list[AdminPromotionData], PromotionPaginationData]:
        rows, total = self.repository.list_promotions(
            search=search,
            state=state,
            validity=validity,
            page=page,
            page_size=page_size,
        )
        return (
            [self._to_promotion_data(row) for row in rows],
            PromotionPaginationData(
                page=page,
                page_size=page_size,
                total=total,
                total_pages=ceil(total / page_size) if total else 0,
            ),
        )

    def get_promotion(self, promotion_id: int) -> AdminPromotionDetailData:
        return self._get_detail(promotion_id)

    def list_products(self, promotion_id: int) -> list[PromotionProductData]:
        if self.repository.get_by_id(promotion_id) is None:
            raise PromotionNotFoundError("Promocion no encontrada")
        return self._get_products(promotion_id)

    def create_promotion(
        self, payload: PromotionCreateRequest
    ) -> AdminPromotionDetailData:
        try:
            if payload.codigo is not None:
                self._ensure_unique_code(payload.codigo)
            promotion = self.repository.create_promotion(**payload.model_dump())
            result = self._get_detail(promotion.id_promocion)
            self.db.commit()
            return result
        except DOMAIN_ERRORS:
            self.db.rollback()
            raise
        except IntegrityError as error:
            self.db.rollback()
            raise PromotionConflictError(
                "El codigo de promocion ya esta registrado"
            ) from error
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminPromotionPersistenceError from error

    def update_promotion(
        self, *, promotion_id: int, payload: PromotionUpdateRequest
    ) -> AdminPromotionDetailData:
        try:
            promotion = self._get_for_update(promotion_id)
            values = payload.model_dump(exclude_unset=True)
            discount_type = values.get("tipo_descuento", promotion.tipo_descuento)
            discount_value = values.get("valor", promotion.valor)
            start = values.get("fecha_inicio", promotion.fecha_inicio)
            end = values.get("fecha_fin", promotion.fecha_fin)
            self._validate_rules(discount_type, discount_value, start, end)
            if "codigo" in values and values["codigo"] is not None:
                self._ensure_unique_code(
                    values["codigo"], exclude_promotion_id=promotion_id
                )
            self.repository.update_promotion(promotion, **values)
            result = self._get_detail(promotion_id)
            self.db.commit()
            return result
        except DOMAIN_ERRORS:
            self.db.rollback()
            raise
        except IntegrityError as error:
            self.db.rollback()
            raise PromotionConflictError(
                "El codigo de promocion ya esta registrado"
            ) from error
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminPromotionPersistenceError from error

    def update_status(
        self, *, promotion_id: int, payload: PromotionStatusUpdateRequest
    ) -> AdminPromotionDetailData:
        try:
            promotion = self._get_for_update(promotion_id)
            self.repository.update_status(promotion, state=payload.estado)
            result = self._get_detail(promotion_id)
            self.db.commit()
            return result
        except DOMAIN_ERRORS:
            self.db.rollback()
            raise
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminPromotionPersistenceError from error

    def add_products(
        self, *, promotion_id: int, payload: PromotionProductsRequest
    ) -> list[PromotionProductData]:
        try:
            promotion = self._get_for_update(promotion_id)
            for product_id in payload.id_productos:
                product = self.repository.get_product(product_id, for_update=True)
                if product is None:
                    raise PromotionProductNotFoundError(
                        f"Producto {product_id} no encontrado"
                    )
                if not product.estado:
                    raise PromotionProductInactiveError(
                        f"El producto {product_id} esta inactivo"
                    )
                if self.repository.get_association(
                    promotion_id, product_id, for_update=True
                ) is not None:
                    raise PromotionConflictError(
                        f"El producto {product_id} ya esta asociado a la promocion"
                    )
            for product_id in payload.id_productos:
                self.repository.add_product(promotion_id, product_id)
            self.repository.touch_promotion(promotion)
            result = self._get_products(promotion_id)
            self.db.commit()
            return result
        except DOMAIN_ERRORS:
            self.db.rollback()
            raise
        except IntegrityError as error:
            self.db.rollback()
            raise PromotionConflictError(
                "Uno o mas productos ya estan asociados a la promocion"
            ) from error
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminPromotionPersistenceError from error

    def _get_for_update(self, promotion_id: int):
        promotion = self.repository.get_by_id(promotion_id, for_update=True)
        if promotion is None:
            raise PromotionNotFoundError("Promocion no encontrada")
        return promotion

    def _ensure_unique_code(
        self, code: str, *, exclude_promotion_id: int | None = None
    ) -> None:
        if self.repository.get_by_code(
            code,
            exclude_promotion_id=exclude_promotion_id,
            for_update=True,
        ) is not None:
            raise PromotionConflictError(
                "El codigo de promocion ya esta registrado"
            )

    def _get_detail(self, promotion_id: int) -> AdminPromotionDetailData:
        row = self.repository.get_summary(promotion_id)
        if row is None:
            raise PromotionNotFoundError("Promocion no encontrada")
        data = self._to_promotion_data(row)
        return AdminPromotionDetailData(
            **data.model_dump(), productos=self._get_products(promotion_id)
        )

    def _get_products(self, promotion_id: int) -> list[PromotionProductData]:
        return [
            PromotionProductData.model_validate(row)
            for row in self.repository.list_products(promotion_id)
        ]

    @staticmethod
    def _validate_rules(
        discount_type: DiscountType,
        value: Decimal,
        start: datetime,
        end: datetime,
    ) -> None:
        if end < start:
            raise PromotionBusinessRuleError(
                "La fecha fin debe ser igual o posterior a la fecha inicio"
            )
        if value <= 0:
            raise PromotionBusinessRuleError(
                "El valor del descuento debe ser mayor a cero"
            )
        if discount_type == "PORCENTAJE" and value > Decimal("100"):
            raise PromotionBusinessRuleError(
                "El porcentaje no puede ser mayor a 100"
            )

    @classmethod
    def _to_promotion_data(cls, row) -> AdminPromotionData:
        if isinstance(row, Mapping):
            values = dict(row)
        else:
            values = {
                field: getattr(row, field)
                for field in AdminPromotionData.model_fields
                if field != "vigencia"
            }
        start = values["fecha_inicio"]
        end = values["fecha_fin"]
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        validity: Validity
        if now < start:
            validity = "PROGRAMADA"
        elif now > end:
            validity = "EXPIRADA"
        else:
            validity = "VIGENTE"
        values["vigencia"] = validity
        return AdminPromotionData.model_validate(values)
