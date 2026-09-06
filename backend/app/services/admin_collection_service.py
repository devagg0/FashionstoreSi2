"""Reglas de negocio de la gestión administrativa de colecciones."""

from math import ceil

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.collection import Collection
from app.repositories.admin_collection_repository import AdminCollectionRepository
from app.schemas.admin_collection import (
    AdminCollectionData,
    CollectionCreateRequest,
    CollectionPaginationData,
    CollectionStatusUpdateRequest,
    CollectionUpdateRequest,
)


class CollectionNotFoundError(Exception):
    """La coleccion solicitada no existe."""


class AdminCollectionPersistenceError(Exception):
    """Una operación administrativa de coleccion no pudo persistirse."""


class AdminCollectionService:
    """Orquesta consultas y cambios de colecciones para CU08."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = AdminCollectionRepository(db)

    def list_collections(
        self,
        *,
        search: str | None,
        state: bool | None,
        page: int,
        page_size: int,
    ) -> tuple[list[AdminCollectionData], CollectionPaginationData]:
        """Obtiene una página de colecciones con filtros opcionales."""
        collections, total = self.repository.list_collections(
            search=search,
            state=state,
            page=page,
            page_size=page_size,
        )
        pagination = CollectionPaginationData(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=ceil(total / page_size) if total else 0,
        )
        return [self._to_collection_data(collection) for collection in collections], pagination

    def get_collection(self, collection_id: int) -> AdminCollectionData:
        """Obtiene el detalle de una coleccion existente."""
        collection = self.repository.get_by_id(collection_id)
        if collection is None:
            raise CollectionNotFoundError
        return self._to_collection_data(collection)

    def create_collection(self, payload: CollectionCreateRequest) -> AdminCollectionData:
        """Crea una coleccion activa; los nombres repetidos estan permitidos."""
        try:
            collection = self.repository.create(**payload.model_dump())
            result = self._to_collection_data(collection)
            self.db.commit()
            return result
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminCollectionPersistenceError from error

    def update_collection(
        self,
        *,
        collection_id: int,
        payload: CollectionUpdateRequest,
    ) -> AdminCollectionData:
        """Modifica parcialmente los campos sin imponer unicidad de nombres."""
        try:
            collection = self.repository.get_by_id(collection_id, for_update=True)
            if collection is None:
                raise CollectionNotFoundError
            self.repository.update(collection, **payload.model_dump(exclude_unset=True))
            result = self._to_collection_data(collection)
            self.db.commit()
            return result
        except CollectionNotFoundError:
            self.db.rollback()
            raise
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminCollectionPersistenceError from error

    def update_status(
        self,
        *,
        collection_id: int,
        payload: CollectionStatusUpdateRequest,
    ) -> AdminCollectionData:
        """Activa o desactiva una coleccion sin borrarla físicamente."""
        try:
            collection = self.repository.get_by_id(collection_id, for_update=True)
            if collection is None:
                raise CollectionNotFoundError

            self.repository.update_status(collection, state=payload.estado)
            result = self._to_collection_data(collection)
            self.db.commit()
            return result
        except CollectionNotFoundError:
            self.db.rollback()
            raise
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminCollectionPersistenceError from error

    @staticmethod
    def _to_collection_data(collection: Collection) -> AdminCollectionData:
        """Convierte el modelo ORM a su representación pública."""
        return AdminCollectionData(
            id_coleccion=collection.id_coleccion,
            nombre=collection.nombre,
            estado=collection.estado,
            descripcion=collection.descripcion,
            created_at=collection.created_at,
            updated_at=collection.updated_at,
        )
