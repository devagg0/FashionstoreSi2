"""Persistencia de CU02 sobre ``t_empresa``."""

from datetime import datetime, timezone

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models.company import Company
from app.PK07.CU01_RegistrarEmpresa.repository import CompanyRegistrationRepository


class CompanyManagementRepository(CompanyRegistrationRepository):
    """Consultas y cambios permitidos para empresas contratantes."""

    def __init__(self, db: Session) -> None:
        super().__init__(db)

    @staticmethod
    def _apply_filters(
        statement: Select,
        *,
        search: str | None,
        state: str | None,
    ) -> Select:
        if search and search.strip():
            escaped = (
                search.strip()
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            pattern = f"%{escaped}%"
            statement = statement.where(
                or_(
                    Company.nombre.ilike(pattern, escape="\\"),
                    Company.codigo.ilike(pattern, escape="\\"),
                    Company.nit.ilike(pattern, escape="\\"),
                )
            )
        if state is not None:
            statement = statement.where(Company.estado == state)
        return statement

    def list_companies(
        self,
        *,
        search: str | None,
        state: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Company], int]:
        filters = {"search": search, "state": state}
        statement = self._apply_filters(select(Company), **filters)
        count_statement = self._apply_filters(
            select(func.count(Company.id_empresa)),
            **filters,
        )
        companies = list(
            self.db.scalars(
                statement.order_by(Company.nombre, Company.id_empresa)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return companies, self.db.scalar(count_statement) or 0

    def get_by_id(
        self,
        company_id: int,
        *,
        for_update: bool = False,
    ) -> Company | None:
        statement = select(Company).where(Company.id_empresa == company_id)
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def update(self, company: Company, **values: object) -> None:
        for field, value in values.items():
            setattr(company, field, value)
        company.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        self.db.flush()

    def update_state(self, company: Company, *, state: str) -> None:
        company.estado = state
        company.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        self.db.flush()
