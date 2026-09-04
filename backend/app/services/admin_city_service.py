"""Reglas de negocio de la gestión administrativa de ciudades."""

from math import ceil

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.city import City
from app.repositories.admin_city_repository import AdminCityRepository
from app.schemas.admin_city import (
    AdminCityData,
    CityCreateRequest,
    CityPaginationData,
    CityStatusUpdateRequest,
    CityUpdateRequest,
)


class CityNotFoundError(Exception):
    """La ciudad solicitada no existe."""


class CityNameDuplicateError(Exception):
    """Ya existe una ciudad con el mismo nombre normalizado."""


class AdminCityPersistenceError(Exception):
    """Una operación administrativa de ciudad no pudo persistirse."""


class AdminCityService:
    """Orquesta consultas y cambios de ciudades para CU04."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = AdminCityRepository(db)

    def list_cities(
        self,
        *,
        search: str | None,
        state: bool | None,
        page: int,
        page_size: int,
    ) -> tuple[list[AdminCityData], CityPaginationData]:
        """Obtiene una página de ciudades con filtros opcionales."""
        cities, total = self.repository.list_cities(
            search=search,
            state=state,
            page=page,
            page_size=page_size,
        )
        pagination = CityPaginationData(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=ceil(total / page_size) if total else 0,
        )
        return [self._to_city_data(city) for city in cities], pagination

    def get_city(self, city_id: int) -> AdminCityData:
        """Obtiene el detalle de una ciudad existente."""
        city = self.repository.get_by_id(city_id)
        if city is None:
            raise CityNotFoundError
        return self._to_city_data(city)

    def create_city(self, payload: CityCreateRequest) -> AdminCityData:
        """Crea una ciudad activa tras comprobar su nombre normalizado."""
        try:
            if self.repository.get_by_name(payload.nombre) is not None:
                raise CityNameDuplicateError

            city = self.repository.create(name=payload.nombre)
            result = self._to_city_data(city)
            self.db.commit()
            return result
        except CityNameDuplicateError:
            self.db.rollback()
            raise
        except IntegrityError as error:
            self._handle_integrity_error(error, payload.nombre)
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminCityPersistenceError from error

    def update_city(
        self,
        *,
        city_id: int,
        payload: CityUpdateRequest,
    ) -> AdminCityData:
        """Modifica el nombre sin permitir duplicados case-insensitive."""
        try:
            city = self.repository.get_by_id(city_id, for_update=True)
            if city is None:
                raise CityNotFoundError
            if self.repository.get_by_name(
                payload.nombre,
                exclude_city_id=city_id,
            ) is not None:
                raise CityNameDuplicateError

            self.repository.update_name(city, name=payload.nombre)
            result = self._to_city_data(city)
            self.db.commit()
            return result
        except (CityNotFoundError, CityNameDuplicateError):
            self.db.rollback()
            raise
        except IntegrityError as error:
            self._handle_integrity_error(error, payload.nombre, city_id)
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminCityPersistenceError from error

    def update_status(
        self,
        *,
        city_id: int,
        payload: CityStatusUpdateRequest,
    ) -> AdminCityData:
        """Activa o desactiva una ciudad sin borrarla físicamente."""
        try:
            city = self.repository.get_by_id(city_id, for_update=True)
            if city is None:
                raise CityNotFoundError

            self.repository.update_status(city, state=payload.estado)
            result = self._to_city_data(city)
            self.db.commit()
            return result
        except CityNotFoundError:
            self.db.rollback()
            raise
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminCityPersistenceError from error

    def _handle_integrity_error(
        self,
        error: IntegrityError,
        name: str,
        exclude_city_id: int | None = None,
    ) -> None:
        """Traduce una carrera de unicidad a un conflicto de dominio."""
        self.db.rollback()
        try:
            duplicate = self.repository.get_by_name(
                name,
                exclude_city_id=exclude_city_id,
            )
        except SQLAlchemyError as lookup_error:
            self.db.rollback()
            raise AdminCityPersistenceError from lookup_error

        if duplicate is not None:
            raise CityNameDuplicateError from error
        raise AdminCityPersistenceError from error

    @staticmethod
    def _to_city_data(city: City) -> AdminCityData:
        """Convierte el modelo ORM a su representación pública."""
        return AdminCityData(
            id_ciudad=city.id_ciudad,
            nombre=city.nombre,
            estado=city.estado,
        )
