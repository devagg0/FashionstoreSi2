"""Persistencia para la gestión administrativa de proveedores."""

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models.supplier import Supplier


class AdminSupplierRepository:
    """Centraliza las consultas y mutaciones sobre ``t_proveedor``."""

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
                or_(*(field.ilike(f"%{escaped_search}%", escape="\\")
                      for field in (Supplier.nombre, Supplier.nit, Supplier.correo)))
            )
        if state is not None:
            statement = statement.where(Supplier.estado.is_(state))
        return statement

    def list_suppliers(
        self,
        *,
        search: str | None,
        state: bool | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Supplier], int]:
        """Lista proveedores filtrados y devuelve el total antes de paginar."""
        filters = {"search": search, "state": state}
        statement = self._apply_filters(select(Supplier), **filters)
        count_statement = self._apply_filters(
            select(func.count(Supplier.id_proveedor)),
            **filters,
        )

        suppliers = list(
            self.db.scalars(
                statement.order_by(Supplier.nombre, Supplier.id_proveedor)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        total = self.db.scalar(count_statement) or 0
        return suppliers, total

    def get_by_id(
        self,
        supplier_id: int,
        *,
        for_update: bool = False,
    ) -> Supplier | None:
        """Obtiene un proveedor y permite bloquearlo para una modificación."""
        statement = select(Supplier).where(Supplier.id_proveedor == supplier_id)
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def create(
        self, *, nombre: str, nit: str | None = None,
        telefono: str | None = None, correo: str | None = None,
        direccion: str | None = None,
    ) -> Supplier:
        record = Supplier(
            nombre=nombre, nit=nit, telefono=telefono, correo=correo,
            direccion=direccion, id_usuario=None, estado=True,
        )
        self.db.add(record)
        self.db.flush()
        return record

    def update(self, record: Supplier, **values: object) -> None:
        """Aplica solamente los campos validados por el schema."""
        for field, value in values.items():
            setattr(record, field, value)
        self.db.flush()

    def update_status(self, supplier: Supplier, *, state: bool) -> None:
        """Activa o desactiva sin eliminar el registro."""
        supplier.estado = state
        self.db.flush()
