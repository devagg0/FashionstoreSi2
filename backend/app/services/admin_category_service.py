"""Reglas de negocio de la gestión administrativa de categorías."""

from math import ceil

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.category import Category
from app.repositories.admin_category_repository import AdminCategoryRepository
from app.schemas.admin_category import (
    AdminCategoryData,
    CategoryCreateRequest,
    CategoryPaginationData,
    CategoryStatusUpdateRequest,
    CategoryUpdateRequest,
)


class CategoryNotFoundError(Exception):
    """La categoría solicitada no existe."""


class CategoryNameDuplicateError(Exception):
    """Ya existe una categoría con el mismo nombre normalizado."""


class AdminCategoryPersistenceError(Exception):
    """Una operación administrativa de categoría no pudo persistirse."""


class AdminCategoryService:
    """Orquesta consultas y cambios de categorías para CU07."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = AdminCategoryRepository(db)

    def list_categories(
        self,
        *,
        search: str | None,
        state: bool | None,
        page: int,
        page_size: int,
    ) -> tuple[list[AdminCategoryData], CategoryPaginationData]:
        """Obtiene una página de categorías con filtros opcionales."""
        categories, total = self.repository.list_categories(
            search=search,
            state=state,
            page=page,
            page_size=page_size,
        )
        pagination = CategoryPaginationData(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=ceil(total / page_size) if total else 0,
        )
        return [self._to_category_data(category) for category in categories], pagination

    def get_category(self, category_id: int) -> AdminCategoryData:
        """Obtiene el detalle de una categoría existente."""
        category = self.repository.get_by_id(category_id)
        if category is None:
            raise CategoryNotFoundError
        return self._to_category_data(category)

    def create_category(self, payload: CategoryCreateRequest) -> AdminCategoryData:
        """Crea una categoría activa tras comprobar su nombre normalizado."""
        try:
            if self.repository.get_by_name(payload.nombre) is not None:
                raise CategoryNameDuplicateError

            category = self.repository.create(**payload.model_dump())
            result = self._to_category_data(category)
            self.db.commit()
            return result
        except CategoryNameDuplicateError:
            self.db.rollback()
            raise
        except IntegrityError as error:
            self._handle_integrity_error(error, payload.nombre)
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminCategoryPersistenceError from error

    def update_category(
        self,
        *,
        category_id: int,
        payload: CategoryUpdateRequest,
    ) -> AdminCategoryData:
        """Modifica parcialmente los campos sin permitir nombres duplicados."""
        try:
            category = self.repository.get_by_id(category_id, for_update=True)
            if category is None:
                raise CategoryNotFoundError
            if "nombre" in payload.model_fields_set and self.repository.get_by_name(
                payload.nombre,
                exclude_category_id=category_id,
            ) is not None:
                raise CategoryNameDuplicateError

            self.repository.update(category, **payload.model_dump(exclude_unset=True))
            result = self._to_category_data(category)
            self.db.commit()
            return result
        except (CategoryNotFoundError, CategoryNameDuplicateError):
            self.db.rollback()
            raise
        except IntegrityError as error:
            self._handle_integrity_error(error, payload.nombre, category_id)
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminCategoryPersistenceError from error

    def update_status(
        self,
        *,
        category_id: int,
        payload: CategoryStatusUpdateRequest,
    ) -> AdminCategoryData:
        """Activa o desactiva una categoría sin borrarla físicamente."""
        try:
            category = self.repository.get_by_id(category_id, for_update=True)
            if category is None:
                raise CategoryNotFoundError

            self.repository.update_status(category, state=payload.estado)
            result = self._to_category_data(category)
            self.db.commit()
            return result
        except CategoryNotFoundError:
            self.db.rollback()
            raise
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminCategoryPersistenceError from error

    def _handle_integrity_error(
        self,
        error: IntegrityError,
        name: str | None,
        exclude_category_id: int | None = None,
    ) -> None:
        """Traduce una carrera de unicidad a un conflicto de dominio."""
        self.db.rollback()
        try:
            duplicate = None if name is None else self.repository.get_by_name(
                name,
                exclude_category_id=exclude_category_id,
            )
        except SQLAlchemyError as lookup_error:
            self.db.rollback()
            raise AdminCategoryPersistenceError from lookup_error

        if duplicate is not None:
            raise CategoryNameDuplicateError from error
        raise AdminCategoryPersistenceError from error

    @staticmethod
    def _to_category_data(category: Category) -> AdminCategoryData:
        """Convierte el modelo ORM a su representación pública."""
        return AdminCategoryData(
            id_categoria=category.id_categoria,
            nombre=category.nombre,
            estado=category.estado,
            descripcion=category.descripcion,
            created_at=category.created_at,
            updated_at=category.updated_at,
        )
