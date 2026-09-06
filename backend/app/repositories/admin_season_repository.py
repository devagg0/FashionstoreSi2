"""Persistencia para la gestión administrativa de temporadas."""

from datetime import date

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.season import Season


class AdminSeasonRepository:
    """Centraliza las consultas y mutaciones sobre ``t_temporada``."""

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _apply_filters(
        statement: Select,
        *,
        search: str | None,
        state: bool | None,
    ) -> Select:
        """Aplica los mismos filtros al listado y a su conteo."""
        if search and search.strip():
            escaped_search = (
                search.strip()
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            statement = statement.where(
                Season.nombre.ilike(f"%{escaped_search}%", escape="\\")
            )
        if state is not None:
            statement = statement.where(Season.estado.is_(state))
        return statement

    def list_seasons(
        self,
        *,
        search: str | None,
        state: bool | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Season], int]:
        """Lista temporadas filtradas y devuelve el total antes de paginar."""
        filters = {"search": search, "state": state}
        statement = self._apply_filters(select(Season), **filters)
        count_statement = self._apply_filters(
            select(func.count(Season.id_temporada)),
            **filters,
        )

        seasons = list(
            self.db.scalars(
                statement.order_by(Season.nombre, Season.id_temporada)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        total = self.db.scalar(count_statement) or 0
        return seasons, total

    def get_by_id(
        self,
        season_id: int,
        *,
        for_update: bool = False,
    ) -> Season | None:
        """Obtiene una temporada y permite bloquearla para una modificación."""
        statement = select(Season).where(Season.id_temporada == season_id)
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def create(
        self, *, nombre: str, descripcion: str | None = None,
        fecha_inicio: date | None = None, fecha_fin: date | None = None,
    ) -> Season:
        record = Season(
            nombre=nombre, descripcion=descripcion, estado=True,
            fecha_inicio=fecha_inicio, fecha_fin=fecha_fin,
        )
        self.db.add(record)
        self.db.flush()
        return record

    def update(self, record: Season, **values: object) -> None:
        """Aplica solamente los campos validados por el schema."""
        for field, value in values.items():
            setattr(record, field, value)
        self.db.flush()

    def update_status(self, season: Season, *, state: bool) -> None:
        """Activa o desactiva sin eliminar el registro."""
        season.estado = state
        self.db.flush()
