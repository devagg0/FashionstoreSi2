"""Persistencia para la gestión administrativa de categorías."""

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.category import Category


class AdminCategoryRepository:
    """Centraliza las consultas y mutaciones sobre ``t_categoria``."""

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
                Category.nombre.ilike(f"%{escaped_search}%", escape="\\")
            )
        if state is not None:
            statement = statement.where(Category.estado.is_(state))
        return statement

    def list_categories(
        self,
        *,
        search: str | None,
        state: bool | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Category], int]:
        """Lista categorías filtradas y devuelve el total antes de paginar."""
        filters = {"search": search, "state": state}
        statement = self._apply_filters(select(Category), **filters)
        count_statement = self._apply_filters(
            select(func.count(Category.id_categoria)),
            **filters,
        )

        categories = list(
            self.db.scalars(
                statement.order_by(Category.nombre, Category.id_categoria)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        total = self.db.scalar(count_statement) or 0
        return categories, total

    def get_by_id(
        self,
        category_id: int,
        *,
        for_update: bool = False,
    ) -> Category | None:
        """Obtiene una categoría y permite bloquearla para una modificación."""
        statement = select(Category).where(Category.id_categoria == category_id)
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def get_by_name(
        self,
        name: str,
        *,
        exclude_category_id: int | None = None,
    ) -> Category | None:
        """Busca duplicados sin distinguir mayúsculas de minúsculas."""
        statement = select(Category).where(
            func.lower(Category.nombre) == name.lower()
        )
        if exclude_category_id is not None:
            statement = statement.where(Category.id_categoria != exclude_category_id)
        return self.db.scalar(statement)

    def create(self, *, nombre: str, descripcion: str | None = None) -> Category:
        record = Category(nombre=nombre, descripcion=descripcion, estado=True)
        self.db.add(record)
        self.db.flush()
        return record

    def update(self, record: Category, **values: object) -> None:
        """Aplica solamente los campos validados por el schema."""
        for field, value in values.items():
            setattr(record, field, value)
        self.db.flush()

    def update_status(self, category: Category, *, state: bool) -> None:
        """Activa o desactiva sin eliminar el registro."""
        category.estado = state
        self.db.flush()
