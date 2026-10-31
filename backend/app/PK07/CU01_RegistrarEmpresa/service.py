"""Reglas transaccionales de CU01: registrar empresa contratante."""

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.company import Company
from app.PK07.CU01_RegistrarEmpresa.repository import CompanyRegistrationRepository
from app.PK07.CU01_RegistrarEmpresa.schemas import CompanyCreateRequest, CompanyData


class CompanyCodeAlreadyExistsError(Exception):
    """El cÃ³digo solicitado ya identifica a otra empresa."""


class CompanyNitAlreadyExistsError(Exception):
    """El NIT solicitado ya identifica a otra empresa."""


class CompanyRegistrationPersistenceError(Exception):
    """La empresa no pudo persistirse de forma segura."""


def company_to_data(company: Company) -> CompanyData:
    """ProyecciÃ³n pÃºblica compartida por los CU de empresas SaaS."""
    return CompanyData(
        id_empresa=company.id_empresa,
        codigo=company.codigo,
        nombre=company.nombre,
        nit=company.nit,
        zona_horaria=company.zona_horaria,
        estado=company.estado,
        created_at=company.created_at,
        updated_at=company.updated_at,
    )


class CompanyRegistrationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = CompanyRegistrationRepository(db)

    def register(self, payload: CompanyCreateRequest) -> CompanyData:
        try:
            if self.repository.get_by_code(payload.codigo) is not None:
                raise CompanyCodeAlreadyExistsError
            if payload.nit is not None and self.repository.get_by_nit(payload.nit) is not None:
                raise CompanyNitAlreadyExistsError

            company = self.repository.create(
                code=payload.codigo,
                name=payload.nombre,
                nit=payload.nit,
                timezone=payload.zona_horaria,
            )
            result = company_to_data(company)
            self.db.commit()
            return result
        except (CompanyCodeAlreadyExistsError, CompanyNitAlreadyExistsError):
            self.db.rollback()
            raise
        except IntegrityError as error:
            self.db.rollback()
            constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
            if constraint == "uq_empresa_codigo":
                raise CompanyCodeAlreadyExistsError from error
            if constraint == "uq_empresa_nit":
                raise CompanyNitAlreadyExistsError from error
            raise CompanyRegistrationPersistenceError from error
        except SQLAlchemyError as error:
            self.db.rollback()
            raise CompanyRegistrationPersistenceError from error
        except Exception as error:
            self.db.rollback()
            raise CompanyRegistrationPersistenceError from error

    @staticmethod
    def _to_data(company: Company) -> CompanyData:
        return company_to_data(company)
