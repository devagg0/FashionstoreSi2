"""Reglas de negocio de la gestión administrativa de temporadas."""

from math import ceil

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.season import Season
from app.repositories.admin_season_repository import AdminSeasonRepository
from app.schemas.admin_season import (
    AdminSeasonData,
    SeasonCreateRequest,
    SeasonPaginationData,
    SeasonStatusUpdateRequest,
    SeasonUpdateRequest,
)


class SeasonNotFoundError(Exception):
    """La temporada solicitada no existe."""


class AdminSeasonPersistenceError(Exception):
    """Una operación administrativa de temporada no pudo persistirse."""


class AdminSeasonService:
    """Orquesta consultas y cambios de temporadas para CU08."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = AdminSeasonRepository(db)

    def list_seasons(
        self,
        *,
        search: str | None,
        state: bool | None,
        page: int,
        page_size: int,
    ) -> tuple[list[AdminSeasonData], SeasonPaginationData]:
        """Obtiene una página de temporadas con filtros opcionales."""
        seasons, total = self.repository.list_seasons(
            search=search,
            state=state,
            page=page,
            page_size=page_size,
        )
        pagination = SeasonPaginationData(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=ceil(total / page_size) if total else 0,
        )
        return [self._to_season_data(season) for season in seasons], pagination

    def get_season(self, season_id: int) -> AdminSeasonData:
        """Obtiene el detalle de una temporada existente."""
        season = self.repository.get_by_id(season_id)
        if season is None:
            raise SeasonNotFoundError
        return self._to_season_data(season)

    def create_season(self, payload: SeasonCreateRequest) -> AdminSeasonData:
        """Crea una temporada activa; los nombres repetidos estan permitidos."""
        try:
            season = self.repository.create(**payload.model_dump())
            result = self._to_season_data(season)
            self.db.commit()
            return result
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminSeasonPersistenceError from error

    def update_season(
        self,
        *,
        season_id: int,
        payload: SeasonUpdateRequest,
    ) -> AdminSeasonData:
        """Modifica parcialmente los campos sin imponer unicidad de nombres."""
        try:
            season = self.repository.get_by_id(season_id, for_update=True)
            if season is None:
                raise SeasonNotFoundError
            self.repository.update(season, **payload.model_dump(exclude_unset=True))
            result = self._to_season_data(season)
            self.db.commit()
            return result
        except SeasonNotFoundError:
            self.db.rollback()
            raise
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminSeasonPersistenceError from error

    def update_status(
        self,
        *,
        season_id: int,
        payload: SeasonStatusUpdateRequest,
    ) -> AdminSeasonData:
        """Activa o desactiva una temporada sin borrarla físicamente."""
        try:
            season = self.repository.get_by_id(season_id, for_update=True)
            if season is None:
                raise SeasonNotFoundError

            self.repository.update_status(season, state=payload.estado)
            result = self._to_season_data(season)
            self.db.commit()
            return result
        except SeasonNotFoundError:
            self.db.rollback()
            raise
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminSeasonPersistenceError from error

    @staticmethod
    def _to_season_data(season: Season) -> AdminSeasonData:
        """Convierte el modelo ORM a su representación pública."""
        return AdminSeasonData(
            id_temporada=season.id_temporada,
            nombre=season.nombre,
            estado=season.estado,
            descripcion=season.descripcion,
            fecha_inicio=season.fecha_inicio,
            fecha_fin=season.fecha_fin,
            created_at=season.created_at,
            updated_at=season.updated_at,
        )
