"""Persistencia para la gestión administrativa de colecciones."""

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.collection import Collection


class AdminCollectionRepository:
    """Centraliza las consultas y mutaciones sobre ``t_coleccion``."""

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
                Collection.nombre.ilike(f"%{escaped_search}%", escape="\\")
            )
        if state is not None:
            statement = statement.where(Collection.estado.is_(state))
        return statement

    def list_collections(
        self,
        *,
        search: str | None,
        state: bool | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Collection], int]:
        """Lista colecciones filtradas y devuelve el total antes de paginar."""
        filters = {"search": search, "state": state}
        statement = self._apply_filters(select(Collection), **filters)
        count_statement = self._apply_filters(
            select(func.count(Collection.id_coleccion)),
            **filters,
        )

        collections = list(
            self.db.scalars(
                statement.order_by(Collection.nombre, Collection.id_coleccion)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        total = self.db.scalar(count_statement) or 0
        return collections, total

    def get_by_id(
        self,
        collection_id: int,
        *,
        for_update: bool = False,
    ) -> Collection | None:
        """Obtiene una coleccion y permite bloquearla para una modificación."""
        statement = select(Collection).where(Collection.id_coleccion == collection_id)
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def create(self, *, nombre: str, descripcion: str | None = None) -> Collection:
        record = Collection(nombre=nombre, descripcion=descripcion, estado=True)
        self.db.add(record)
        self.db.flush()
        return record

    def update(self, record: Collection, **values: object) -> None:
        """Aplica solamente los campos validados por el schema."""
        for field, value in values.items():
            setattr(record, field, value)
        self.db.flush()

    def update_status(self, collection: Collection, *, state: bool) -> None:
        """Activa o desactiva sin eliminar el registro."""
        collection.estado = state
        self.db.flush()
