"""Reglas de negocio de la gestión administrativa de proveedores."""

from math import ceil

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.supplier import Supplier
from app.repositories.admin_supplier_repository import AdminSupplierRepository
from app.schemas.admin_supplier import (
    AdminSupplierData,
    SupplierCreateRequest,
    SupplierPaginationData,
    SupplierStatusUpdateRequest,
    SupplierUpdateRequest,
)


class SupplierNotFoundError(Exception):
    """El proveedor solicitado no existe."""


class AdminSupplierPersistenceError(Exception):
    """Una operación administrativa de proveedor no pudo persistirse."""


class AdminSupplierService:
    """Orquesta consultas y cambios de proveedores para CU09."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = AdminSupplierRepository(db)

    def list_suppliers(
        self,
        *,
        search: str | None,
        state: bool | None,
        page: int,
        page_size: int,
    ) -> tuple[list[AdminSupplierData], SupplierPaginationData]:
        """Obtiene una página de proveedores con filtros opcionales."""
        suppliers, total = self.repository.list_suppliers(
            search=search,
            state=state,
            page=page,
            page_size=page_size,
        )
        pagination = SupplierPaginationData(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=ceil(total / page_size) if total else 0,
        )
        return [self._to_supplier_data(supplier) for supplier in suppliers], pagination

    def get_supplier(self, supplier_id: int) -> AdminSupplierData:
        """Obtiene el detalle de un proveedor existente."""
        supplier = self.repository.get_by_id(supplier_id)
        if supplier is None:
            raise SupplierNotFoundError
        return self._to_supplier_data(supplier)

    def create_supplier(self, payload: SupplierCreateRequest) -> AdminSupplierData:
        """Crea un proveedor activo; los nombres repetidos estan permitidos."""
        try:
            supplier = self.repository.create(**payload.model_dump(exclude={"id_usuario"}))
            result = self._to_supplier_data(supplier)
            self.db.commit()
            return result
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminSupplierPersistenceError from error

    def update_supplier(
        self,
        *,
        supplier_id: int,
        payload: SupplierUpdateRequest,
    ) -> AdminSupplierData:
        """Modifica parcialmente los campos sin imponer unicidad de nombres."""
        try:
            supplier = self.repository.get_by_id(supplier_id, for_update=True)
            if supplier is None:
                raise SupplierNotFoundError
            self.repository.update(supplier, **payload.model_dump(exclude_unset=True))
            result = self._to_supplier_data(supplier)
            self.db.commit()
            return result
        except SupplierNotFoundError:
            self.db.rollback()
            raise
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminSupplierPersistenceError from error

    def update_status(
        self,
        *,
        supplier_id: int,
        payload: SupplierStatusUpdateRequest,
    ) -> AdminSupplierData:
        """Activa o desactiva un proveedor sin borrarlo físicamente."""
        try:
            supplier = self.repository.get_by_id(supplier_id, for_update=True)
            if supplier is None:
                raise SupplierNotFoundError

            self.repository.update_status(supplier, state=payload.estado)
            result = self._to_supplier_data(supplier)
            self.db.commit()
            return result
        except SupplierNotFoundError:
            self.db.rollback()
            raise
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminSupplierPersistenceError from error

    @staticmethod
    def _to_supplier_data(supplier: Supplier) -> AdminSupplierData:
        """Convierte el modelo ORM a su representación pública."""
        return AdminSupplierData(
            id_proveedor=supplier.id_proveedor,
            nombre=supplier.nombre,
            estado=supplier.estado,
            id_usuario=supplier.id_usuario,
            nit=supplier.nit,
            telefono=supplier.telefono,
            correo=supplier.correo,
            direccion=supplier.direccion,
            created_at=supplier.created_at,
            updated_at=supplier.updated_at,
        )
