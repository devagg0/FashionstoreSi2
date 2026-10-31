"""Reglas transaccionales de CU02: gestionar empresas contratantes."""

from math import ceil

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.PK07.CU01_RegistrarEmpresa.service import (
    CompanyCodeAlreadyExistsError,
    CompanyNitAlreadyExistsError,
    company_to_data,
)
from app.PK07.CU02_GestionarEmpresas.repository import CompanyManagementRepository
from app.PK07.CU02_GestionarEmpresas.schemas import (
    CompanyPaginationData,
    CompanyStateUpdateRequest,
    CompanyUpdateRequest,
)


class CompanyNotFoundError(Exception):
    """La empresa solicitada no existe."""


class CompanyStateTransitionError(Exception):
    """Una empresa cancelada no puede volver a operar."""


class CompanyManagementPersistenceError(Exception):
    """La operaciÃ³n no pudo completarse de forma segura."""


class CompanyManagementService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = CompanyManagementRepository(db)

    def list_companies(self, *, search, state, page, page_size):
        try:
            companies, total = self.repository.list_companies(
                search=search,
                state=state,
                page=page,
                page_size=page_size,
            )
            pagination = CompanyPaginationData(
                page=page,
                page_size=page_size,
                total=total,
                total_pages=ceil(total / page_size) if total else 0,
            )
            return [company_to_data(company) for company in companies], pagination
        except SQLAlchemyError as error:
            self.db.rollback()
            raise CompanyManagementPersistenceError from error

    def get_company(self, company_id: int):
        try:
            company = self.repository.get_by_id(company_id)
            if company is None:
                raise CompanyNotFoundError
            return company_to_data(company)
        except CompanyNotFoundError:
            raise
        except SQLAlchemyError as error:
            self.db.rollback()
            raise CompanyManagementPersistenceError from error

    def update_company(self, *, company_id: int, payload: CompanyUpdateRequest):
        try:
            company = self.repository.get_by_id(company_id, for_update=True)
            if company is None:
                raise CompanyNotFoundError
            values = payload.model_dump(exclude_unset=True)
            if "codigo" in values and values["codigo"] != company.codigo:
                if self.repository.get_by_code(
                    values["codigo"], exclude_company_id=company_id
                ) is not None:
                    raise CompanyCodeAlreadyExistsError
            if "nit" in values and values["nit"] != company.nit and values["nit"] is not None:
                if self.repository.get_by_nit(
                    values["nit"], exclude_company_id=company_id
                ) is not None:
                    raise CompanyNitAlreadyExistsError
            self.repository.update(company, **values)
            result = company_to_data(company)
            self.db.commit()
            return result
        except (
            CompanyNotFoundError,
            CompanyCodeAlreadyExistsError,
            CompanyNitAlreadyExistsError,
        ):
            self.db.rollback()
            raise
        except IntegrityError as error:
            self.db.rollback()
            self._raise_integrity_error(error)
        except Exception as error:
            self.db.rollback()
            if isinstance(error, CompanyManagementPersistenceError):
                raise
            raise CompanyManagementPersistenceError from error

    def update_state(self, *, company_id: int, payload: CompanyStateUpdateRequest):
        try:
            company = self.repository.get_by_id(company_id, for_update=True)
            if company is None:
                raise CompanyNotFoundError
            if company.estado == "CANCELADA" and payload.estado != "CANCELADA":
                raise CompanyStateTransitionError
            self.repository.update_state(company, state=payload.estado)
            result = company_to_data(company)
            self.db.commit()
            return result
        except (CompanyNotFoundError, CompanyStateTransitionError):
            self.db.rollback()
            raise
        except SQLAlchemyError as error:
            self.db.rollback()
            raise CompanyManagementPersistenceError from error
        except Exception as error:
            self.db.rollback()
            raise CompanyManagementPersistenceError from error

    @staticmethod
    def _raise_integrity_error(error: IntegrityError) -> None:
        constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
        if constraint == "uq_empresa_codigo":
            raise CompanyCodeAlreadyExistsError from error
        if constraint == "uq_empresa_nit":
            raise CompanyNitAlreadyExistsError from error
        raise CompanyManagementPersistenceError from error
