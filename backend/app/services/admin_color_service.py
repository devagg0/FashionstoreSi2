"""Reglas de negocio de la gestión administrativa de colores."""

from math import ceil

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.color import Color
from app.repositories.admin_color_repository import AdminColorRepository
from app.schemas.admin_color import (
    AdminColorData,
    ColorCreateRequest,
    ColorPaginationData,
    ColorStatusUpdateRequest,
    ColorUpdateRequest,
)


class ColorNotFoundError(Exception):
    """El color solicitado no existe."""


class ColorNameDuplicateError(Exception):
    """Ya existe un color con el mismo nombre normalizado."""


class AdminColorPersistenceError(Exception):
    """Una operación administrativa de color no pudo persistirse."""


class AdminColorService:
    """Orquesta consultas y cambios de colores para CU07."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = AdminColorRepository(db)

    def list_colors(
        self,
        *,
        search: str | None,
        state: bool | None,
        page: int,
        page_size: int,
    ) -> tuple[list[AdminColorData], ColorPaginationData]:
        """Obtiene una página de colores con filtros opcionales."""
        colors, total = self.repository.list_colors(
            search=search,
            state=state,
            page=page,
            page_size=page_size,
        )
        pagination = ColorPaginationData(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=ceil(total / page_size) if total else 0,
        )
        return [self._to_color_data(color) for color in colors], pagination

    def get_color(self, color_id: int) -> AdminColorData:
        """Obtiene el detalle de un color existente."""
        color = self.repository.get_by_id(color_id)
        if color is None:
            raise ColorNotFoundError
        return self._to_color_data(color)

    def create_color(self, payload: ColorCreateRequest) -> AdminColorData:
        """Crea un color activo tras comprobar su nombre normalizado."""
        try:
            if self.repository.get_by_name(payload.nombre) is not None:
                raise ColorNameDuplicateError

            color = self.repository.create(**payload.model_dump())
            result = self._to_color_data(color)
            self.db.commit()
            return result
        except ColorNameDuplicateError:
            self.db.rollback()
            raise
        except IntegrityError as error:
            self._handle_integrity_error(error, payload.nombre)
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminColorPersistenceError from error

    def update_color(
        self,
        *,
        color_id: int,
        payload: ColorUpdateRequest,
    ) -> AdminColorData:
        """Modifica parcialmente los campos sin permitir nombres duplicados."""
        try:
            color = self.repository.get_by_id(color_id, for_update=True)
            if color is None:
                raise ColorNotFoundError
            if "nombre" in payload.model_fields_set and self.repository.get_by_name(
                payload.nombre,
                exclude_color_id=color_id,
            ) is not None:
                raise ColorNameDuplicateError

            self.repository.update(color, **payload.model_dump(exclude_unset=True))
            result = self._to_color_data(color)
            self.db.commit()
            return result
        except (ColorNotFoundError, ColorNameDuplicateError):
            self.db.rollback()
            raise
        except IntegrityError as error:
            self._handle_integrity_error(error, payload.nombre, color_id)
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminColorPersistenceError from error

    def update_status(
        self,
        *,
        color_id: int,
        payload: ColorStatusUpdateRequest,
    ) -> AdminColorData:
        """Activa o desactiva un color sin borrarla físicamente."""
        try:
            color = self.repository.get_by_id(color_id, for_update=True)
            if color is None:
                raise ColorNotFoundError

            self.repository.update_status(color, state=payload.estado)
            result = self._to_color_data(color)
            self.db.commit()
            return result
        except ColorNotFoundError:
            self.db.rollback()
            raise
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminColorPersistenceError from error

    def _handle_integrity_error(
        self,
        error: IntegrityError,
        name: str | None,
        exclude_color_id: int | None = None,
    ) -> None:
        """Traduce una carrera de unicidad a un conflicto de dominio."""
        self.db.rollback()
        try:
            duplicate = None if name is None else self.repository.get_by_name(
                name,
                exclude_color_id=exclude_color_id,
            )
        except SQLAlchemyError as lookup_error:
            self.db.rollback()
            raise AdminColorPersistenceError from lookup_error

        if duplicate is not None:
            raise ColorNameDuplicateError from error
        raise AdminColorPersistenceError from error

    @staticmethod
    def _to_color_data(color: Color) -> AdminColorData:
        """Convierte el modelo ORM a su representación pública."""
        return AdminColorData(
            id_color=color.id_color,
            nombre=color.nombre,
            estado=color.estado,
            codigo_hex=color.codigo_hex,
            created_at=color.created_at,
            updated_at=color.updated_at,
        )
