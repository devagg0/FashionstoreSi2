"""Persistencia de CU01 sobre ``t_empresa``."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.company import Company


class CompanyRegistrationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_code(
        self,
        code: str,
        *,
        exclude_company_id: int | None = None,
    ) -> Company | None:
        statement = select(Company).where(Company.codigo == code)
        if exclude_company_id is not None:
            statement = statement.where(Company.id_empresa != exclude_company_id)
        return self.db.scalar(statement)

    def get_by_nit(
        self,
        nit: str,
        *,
        exclude_company_id: int | None = None,
    ) -> Company | None:
        statement = select(Company).where(Company.nit == nit)
        if exclude_company_id is not None:
            statement = statement.where(Company.id_empresa != exclude_company_id)
        return self.db.scalar(statement)

    def create(
        self,
        *,
        code: str,
        name: str,
        nit: str | None,
        timezone: str,
    ) -> Company:
        company = Company(
            codigo=code,
            nombre=name,
            nit=nit,
            zona_horaria=timezone,
            estado="ACTIVA",
        )
        self.db.add(company)
        self.db.flush()
        return company
