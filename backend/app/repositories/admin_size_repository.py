"""Persistencia para la gestión administrativa de tallas."""

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.size import Size


class AdminSizeRepository:
    """Centraliza las consultas y mutaciones sobre ``t_talla``."""

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
                Size.nombre.ilike(f"%{escaped_search}%", escape="\\")
            )
        if state is not None:
            statement = statement.where(Size.estado.is_(state))
        return statement

    def list_sizes(
        self,
        *,
        search: str | None,
        state: bool | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Size], int]:
        """Lista tallas filtradas y devuelve el total antes de paginar."""
        filters = {"search": search, "state": state}
        statement = self._apply_filters(select(Size), **filters)
        count_statement = self._apply_filters(
            select(func.count(Size.id_talla)),
            **filters,
        )

        sizes = list(
            self.db.scalars(
                statement.order_by(Size.nombre, Size.id_talla)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        total = self.db.scalar(count_statement) or 0
        return sizes, total

    def get_by_id(
        self,
        size_id: int,
        *,
        for_update: bool = False,
    ) -> Size | None:
        """Obtiene una talla y permite bloquearla para una modificación."""
        statement = select(Size).where(Size.id_talla == size_id)
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def get_by_name(
        self,
        name: str,
        *,
        exclude_size_id: int | None = None,
    ) -> Size | None:
        """Busca duplicados sin distinguir mayúsculas de minúsculas."""
        statement = select(Size).where(
            func.lower(Size.nombre) == name.lower()
        )
        if exclude_size_id is not None:
            statement = statement.where(Size.id_talla != exclude_size_id)
        return self.db.scalar(statement)

    def create(self, *, nombre: str, descripcion: str | None = None) -> Size:
        record = Size(nombre=nombre, descripcion=descripcion, estado=True)
        self.db.add(record)
        self.db.flush()
        return record

    def update(self, record: Size, **values: object) -> None:
        """Aplica solamente los campos validados por el schema."""
        for field, value in values.items():
            setattr(record, field, value)
        self.db.flush()

    def update_status(self, size: Size, *, state: bool) -> None:
        """Activa o desactiva sin eliminar el registro."""
        size.estado = state
        self.db.flush()
