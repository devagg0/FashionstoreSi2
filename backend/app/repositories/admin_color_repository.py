"""Persistencia para la gestión administrativa de colores."""

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.color import Color


class AdminColorRepository:
    """Centraliza las consultas y mutaciones sobre ``t_color``."""

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
                Color.nombre.ilike(f"%{escaped_search}%", escape="\\")
            )
        if state is not None:
            statement = statement.where(Color.estado.is_(state))
        return statement

    def list_colors(
        self,
        *,
        search: str | None,
        state: bool | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Color], int]:
        """Lista colores filtradas y devuelve el total antes de paginar."""
        filters = {"search": search, "state": state}
        statement = self._apply_filters(select(Color), **filters)
        count_statement = self._apply_filters(
            select(func.count(Color.id_color)),
            **filters,
        )

        colors = list(
            self.db.scalars(
                statement.order_by(Color.nombre, Color.id_color)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        total = self.db.scalar(count_statement) or 0
        return colors, total

    def get_by_id(
        self,
        color_id: int,
        *,
        for_update: bool = False,
    ) -> Color | None:
        """Obtiene un color y permite bloquearla para una modificación."""
        statement = select(Color).where(Color.id_color == color_id)
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def get_by_name(
        self,
        name: str,
        *,
        exclude_color_id: int | None = None,
    ) -> Color | None:
        """Busca duplicados sin distinguir mayúsculas de minúsculas."""
        statement = select(Color).where(
            func.lower(Color.nombre) == name.lower()
        )
        if exclude_color_id is not None:
            statement = statement.where(Color.id_color != exclude_color_id)
        return self.db.scalar(statement)

    def create(self, *, nombre: str, codigo_hex: str | None = None) -> Color:
        record = Color(nombre=nombre, codigo_hex=codigo_hex, estado=True)
        self.db.add(record)
        self.db.flush()
        return record

    def update(self, record: Color, **values: object) -> None:
        """Aplica solamente los campos validados por el schema."""
        for field, value in values.items():
            setattr(record, field, value)
        self.db.flush()

    def update_status(self, color: Color, *, state: bool) -> None:
        """Activa o desactiva sin eliminar el registro."""
        color.estado = state
        self.db.flush()
