"""Persistencia para la gestión administrativa de sucursales."""

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.branch import Branch


class AdminBranchRepository:
    """Centraliza las consultas y mutaciones sobre ``t_sucursal``."""

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
                Branch.nombre.ilike(f"%{escaped_search}%", escape="\\")
            )
        if state is not None:
            statement = statement.where(Branch.estado.is_(state))
        return statement

    def list_branches(
        self,
        *,
        search: str | None,
        state: bool | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Branch], int]:
        """Lista sucursales filtradas y devuelve el total antes de paginar."""
        filters = {"search": search, "state": state}
        statement = self._apply_filters(select(Branch), **filters)
        count_statement = self._apply_filters(
            select(func.count(Branch.id_sucursal)),
            **filters,
        )

        branches = list(
            self.db.scalars(
                statement.order_by(Branch.nombre, Branch.id_sucursal)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        total = self.db.scalar(count_statement) or 0
        return branches, total

    def get_by_id(
        self,
        branch_id: int,
        *,
        for_update: bool = False,
    ) -> Branch | None:
        """Obtiene una sucursal y permite bloquearla para una modificación."""
        statement = select(Branch).where(Branch.id_sucursal == branch_id)
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def create(self, **values: object) -> Branch:
        """Prepara una sucursal activa sin confirmar la transacción."""
        branch = Branch(**values, estado=True)
        self.db.add(branch)
        self.db.flush()
        return branch

    def update(self, branch: Branch, **values: object) -> None:
        """Modifica los datos suministrados en la transacción actual."""
        for field, value in values.items():
            setattr(branch, field, value)
        self.db.flush()

    def update_status(self, branch: Branch, *, state: bool) -> None:
        """Activa o desactiva sin eliminar el registro."""
        branch.estado = state
        self.db.flush()
