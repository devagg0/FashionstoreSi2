"""Reglas de negocio de la gestión administrativa de tallas."""

from math import ceil

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.size import Size
from app.repositories.admin_size_repository import AdminSizeRepository
from app.schemas.admin_size import (
    AdminSizeData,
    SizeCreateRequest,
    SizePaginationData,
    SizeStatusUpdateRequest,
    SizeUpdateRequest,
)


class SizeNotFoundError(Exception):
    """La talla solicitada no existe."""


class SizeNameDuplicateError(Exception):
    """Ya existe una talla con el mismo nombre normalizado."""


class AdminSizePersistenceError(Exception):
    """Una operación administrativa de talla no pudo persistirse."""


class AdminSizeService:
    """Orquesta consultas y cambios de tallas para CU07."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = AdminSizeRepository(db)

    def list_sizes(
        self,
        *,
        search: str | None,
        state: bool | None,
        page: int,
        page_size: int,
    ) -> tuple[list[AdminSizeData], SizePaginationData]:
        """Obtiene una página de tallas con filtros opcionales."""
        sizes, total = self.repository.list_sizes(
            search=search,
            state=state,
            page=page,
            page_size=page_size,
        )
        pagination = SizePaginationData(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=ceil(total / page_size) if total else 0,
        )
        return [self._to_size_data(size) for size in sizes], pagination

    def get_size(self, size_id: int) -> AdminSizeData:
        """Obtiene el detalle de una talla existente."""
        size = self.repository.get_by_id(size_id)
        if size is None:
            raise SizeNotFoundError
        return self._to_size_data(size)

    def create_size(self, payload: SizeCreateRequest) -> AdminSizeData:
        """Crea una talla activa tras comprobar su nombre normalizado."""
        try:
            if self.repository.get_by_name(payload.nombre) is not None:
                raise SizeNameDuplicateError

            size = self.repository.create(**payload.model_dump())
            result = self._to_size_data(size)
            self.db.commit()
            return result
        except SizeNameDuplicateError:
            self.db.rollback()
            raise
        except IntegrityError as error:
            self._handle_integrity_error(error, payload.nombre)
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminSizePersistenceError from error

    def update_size(
        self,
        *,
        size_id: int,
        payload: SizeUpdateRequest,
    ) -> AdminSizeData:
        """Modifica parcialmente los campos sin permitir nombres duplicados."""
        try:
            size = self.repository.get_by_id(size_id, for_update=True)
            if size is None:
                raise SizeNotFoundError
            if "nombre" in payload.model_fields_set and self.repository.get_by_name(
                payload.nombre,
                exclude_size_id=size_id,
            ) is not None:
                raise SizeNameDuplicateError

            self.repository.update(size, **payload.model_dump(exclude_unset=True))
            result = self._to_size_data(size)
            self.db.commit()
            return result
        except (SizeNotFoundError, SizeNameDuplicateError):
            self.db.rollback()
            raise
        except IntegrityError as error:
            self._handle_integrity_error(error, payload.nombre, size_id)
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminSizePersistenceError from error

    def update_status(
        self,
        *,
        size_id: int,
        payload: SizeStatusUpdateRequest,
    ) -> AdminSizeData:
        """Activa o desactiva una talla sin borrarla físicamente."""
        try:
            size = self.repository.get_by_id(size_id, for_update=True)
            if size is None:
                raise SizeNotFoundError

            self.repository.update_status(size, state=payload.estado)
            result = self._to_size_data(size)
            self.db.commit()
            return result
        except SizeNotFoundError:
            self.db.rollback()
            raise
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminSizePersistenceError from error

    def _handle_integrity_error(
        self,
        error: IntegrityError,
        name: str | None,
        exclude_size_id: int | None = None,
    ) -> None:
        """Traduce una carrera de unicidad a un conflicto de dominio."""
        self.db.rollback()
        try:
            duplicate = None if name is None else self.repository.get_by_name(
                name,
                exclude_size_id=exclude_size_id,
            )
        except SQLAlchemyError as lookup_error:
            self.db.rollback()
            raise AdminSizePersistenceError from lookup_error

        if duplicate is not None:
            raise SizeNameDuplicateError from error
        raise AdminSizePersistenceError from error

    @staticmethod
    def _to_size_data(size: Size) -> AdminSizeData:
        """Convierte el modelo ORM a su representación pública."""
        return AdminSizeData(
            id_talla=size.id_talla,
            nombre=size.nombre,
            estado=size.estado,
            descripcion=size.descripcion,
            created_at=size.created_at,
            updated_at=size.updated_at,
        )
