"""Persistencia para la gestión administrativa de ciudades."""

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.city import City


class AdminCityRepository:
    """Centraliza las consultas y mutaciones sobre ``t_ciudad``."""

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
                City.nombre.ilike(f"%{escaped_search}%", escape="\\")
            )
        if state is not None:
            statement = statement.where(City.estado.is_(state))
        return statement

    def list_cities(
        self,
        *,
        search: str | None,
        state: bool | None,
        page: int,
        page_size: int,
    ) -> tuple[list[City], int]:
        """Lista ciudades filtradas y devuelve el total antes de paginar."""
        filters = {"search": search, "state": state}
        statement = self._apply_filters(select(City), **filters)
        count_statement = self._apply_filters(
            select(func.count(City.id_ciudad)),
            **filters,
        )

        cities = list(
            self.db.scalars(
                statement.order_by(City.nombre, City.id_ciudad)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        total = self.db.scalar(count_statement) or 0
        return cities, total

    def get_by_id(
        self,
        city_id: int,
        *,
        for_update: bool = False,
    ) -> City | None:
        """Obtiene una ciudad y permite bloquearla para una modificación."""
        statement = select(City).where(City.id_ciudad == city_id)
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def get_by_name(
        self,
        name: str,
        *,
        exclude_city_id: int | None = None,
    ) -> City | None:
        """Busca duplicados sin distinguir mayúsculas de minúsculas."""
        statement = select(City).where(
            func.lower(City.nombre) == name.lower()
        )
        if exclude_city_id is not None:
            statement = statement.where(City.id_ciudad != exclude_city_id)
        return self.db.scalar(statement)

    def create(self, *, name: str) -> City:
        """Prepara una ciudad activa sin confirmar la transacción."""
        city = City(nombre=name, estado=True)
        self.db.add(city)
        self.db.flush()
        return city

    def update_name(self, city: City, *, name: str) -> None:
        """Modifica el nombre dentro de la transacción actual."""
        city.nombre = name
        self.db.flush()

    def update_status(self, city: City, *, state: bool) -> None:
        """Activa o desactiva sin eliminar el registro."""
        city.estado = state
        self.db.flush()
