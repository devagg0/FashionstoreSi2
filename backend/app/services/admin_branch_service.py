"""Reglas de negocio de la gestión administrativa de sucursales."""

from math import ceil

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.repositories.admin_city_repository import AdminCityRepository
from app.repositories.admin_branch_repository import AdminBranchRepository
from app.schemas.admin_branch import (
    AdminBranchData,
    BranchCreateRequest,
    BranchPaginationData,
    BranchStatusUpdateRequest,
    BranchUpdateRequest,
)


class BranchNotFoundError(Exception):
    """La sucursal solicitada no existe."""


class BranchCityNotFoundError(Exception):
    """La ciudad seleccionada no existe."""


class BranchCityInactiveError(Exception):
    """Una nueva asociación requiere una ciudad activa."""


class AdminBranchPersistenceError(Exception):
    """Una operación administrativa de sucursal no pudo persistirse."""


class AdminBranchService:
    """Orquesta consultas y cambios de sucursales para CU05."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = AdminBranchRepository(db)
        self.city_repository = AdminCityRepository(db)

    def list_branches(
        self,
        *,
        search: str | None,
        state: bool | None,
        page: int,
        page_size: int,
    ) -> tuple[list[AdminBranchData], BranchPaginationData]:
        """Obtiene una página de sucursales con filtros opcionales."""
        branches, total = self.repository.list_branches(
            search=search,
            state=state,
            page=page,
            page_size=page_size,
        )
        pagination = BranchPaginationData(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=ceil(total / page_size) if total else 0,
        )
        return [self._to_branch_data(branch) for branch in branches], pagination

    def get_branch(self, branch_id: int) -> AdminBranchData:
        """Obtiene el detalle de una sucursal existente."""
        branch = self.repository.get_by_id(branch_id)
        if branch is None:
            raise BranchNotFoundError
        return self._to_branch_data(branch)

    def _validate_city(self, city_id: int) -> None:
        city = self.city_repository.get_by_id(city_id, for_update=True)
        if city is None:
            raise BranchCityNotFoundError
        if not city.estado:
            raise BranchCityInactiveError

    def create_branch(self, payload: BranchCreateRequest) -> AdminBranchData:
        """Crea una sucursal activa asociada a una ciudad activa."""
        try:
            self._validate_city(payload.id_ciudad)
            branch = self.repository.create(**payload.model_dump())
            result = self._to_branch_data(branch)
            self.db.commit()
            return result
        except (BranchCityNotFoundError, BranchCityInactiveError):
            self.db.rollback()
            raise
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminBranchPersistenceError from error

    def update_branch(
        self, *, branch_id: int, payload: BranchUpdateRequest,
    ) -> AdminBranchData:
        """Valida la ciudad únicamente cuando cambia la asociación."""
        try:
            branch = self.repository.get_by_id(branch_id, for_update=True)
            if branch is None:
                raise BranchNotFoundError
            values = payload.model_dump(exclude_unset=True)
            if "id_ciudad" in values and values["id_ciudad"] != branch.id_ciudad:
                self._validate_city(values["id_ciudad"])
            self.repository.update(branch, **values)
            result = self._to_branch_data(branch)
            self.db.commit()
            return result
        except (BranchNotFoundError, BranchCityNotFoundError, BranchCityInactiveError):
            self.db.rollback()
            raise
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminBranchPersistenceError from error

    def update_status(
        self,
        *,
        branch_id: int,
        payload: BranchStatusUpdateRequest,
    ) -> AdminBranchData:
        """Activa o desactiva una sucursal sin borrarla físicamente."""
        try:
            branch = self.repository.get_by_id(branch_id, for_update=True)
            if branch is None:
                raise BranchNotFoundError

            self.repository.update_status(branch, state=payload.estado)
            result = self._to_branch_data(branch)
            self.db.commit()
            return result
        except BranchNotFoundError:
            self.db.rollback()
            raise
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminBranchPersistenceError from error

    @staticmethod
    def _to_branch_data(branch: Branch) -> AdminBranchData:
        """Convierte el modelo ORM a su representación pública."""
        return AdminBranchData(
            id_sucursal=branch.id_sucursal,
            id_ciudad=branch.id_ciudad,
            nombre=branch.nombre,
            direccion=branch.direccion,
            telefono=branch.telefono,
            hora_apertura=branch.hora_apertura,
            hora_cierre=branch.hora_cierre,
            created_at=branch.created_at,
            updated_at=branch.updated_at,
            estado=branch.estado,
        )
