"""Reglas seguras para promover una cuenta existente a SUPERADMIN global."""

from dataclasses import dataclass
from typing import Literal

from email_validator import EmailNotValidError, validate_email
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.PK07.superadmin_bootstrap.repository import SuperadminBootstrapRepository


ADMIN_ROLE = "ADMINISTRADOR"
SUPERADMIN_ROLE = "SUPERADMIN"


class InvalidBootstrapEmailError(Exception):
    pass


class BootstrapUserNotFoundError(Exception):
    pass


class BootstrapUserInactiveError(Exception):
    pass


class BootstrapRoleNotConfiguredError(Exception):
    pass


class BootstrapUserNotEligibleError(Exception):
    pass


class SuperadminBootstrapPersistenceError(Exception):
    pass


@dataclass(frozen=True)
class SuperadminBootstrapResult:
    user_id: int
    email: str
    status: Literal["ELIGIBLE", "ASSIGNED", "ALREADY_ASSIGNED"]


class SuperadminBootstrapService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = SuperadminBootstrapRepository(db)

    @staticmethod
    def normalize_email(email: str) -> str:
        try:
            return validate_email(
                email.strip(),
                check_deliverability=False,
            ).normalized.lower()
        except (AttributeError, EmailNotValidError) as error:
            raise InvalidBootstrapEmailError from error

    def check(self, email: str) -> SuperadminBootstrapResult:
        normalized = self.normalize_email(email)
        try:
            user, current_role, _superadmin_role = self._validate(
                normalized,
                for_update=False,
            )
            status = (
                "ALREADY_ASSIGNED"
                if current_role.nombre.upper() == SUPERADMIN_ROLE
                else "ELIGIBLE"
            )
            return SuperadminBootstrapResult(user.id_usuario, user.correo, status)
        except (
            BootstrapUserNotFoundError,
            BootstrapUserInactiveError,
            BootstrapRoleNotConfiguredError,
            BootstrapUserNotEligibleError,
        ):
            self.db.rollback()
            raise
        except SQLAlchemyError as error:
            self.db.rollback()
            raise SuperadminBootstrapPersistenceError from error

    def assign(self, email: str) -> SuperadminBootstrapResult:
        normalized = self.normalize_email(email)
        try:
            user, current_role, superadmin_role = self._validate(
                normalized,
                for_update=True,
            )
            if current_role.nombre.upper() == SUPERADMIN_ROLE:
                self.db.commit()
                return SuperadminBootstrapResult(
                    user.id_usuario,
                    user.correo,
                    "ALREADY_ASSIGNED",
                )
            self.repository.assign_global_role(user, superadmin_role)
            self.db.commit()
            return SuperadminBootstrapResult(user.id_usuario, user.correo, "ASSIGNED")
        except (
            BootstrapUserNotFoundError,
            BootstrapUserInactiveError,
            BootstrapRoleNotConfiguredError,
            BootstrapUserNotEligibleError,
        ):
            self.db.rollback()
            raise
        except Exception as error:
            self.db.rollback()
            raise SuperadminBootstrapPersistenceError from error

    def _validate(self, email: str, *, for_update: bool):
        row = self.repository.get_user_with_global_role(
            email,
            for_update=for_update,
        )
        if row is None:
            raise BootstrapUserNotFoundError
        user, current_role = row
        if not user.estado:
            raise BootstrapUserInactiveError

        superadmin_role = self.repository.get_active_role(SUPERADMIN_ROLE)
        if superadmin_role is None:
            raise BootstrapRoleNotConfiguredError
        if current_role.nombre.upper() == SUPERADMIN_ROLE:
            return user, current_role, superadmin_role
        if current_role.nombre.upper() != ADMIN_ROLE:
            raise BootstrapUserNotEligibleError
        if not self.repository.has_active_admin_membership(user.id_usuario):
            raise BootstrapUserNotEligibleError
        return user, current_role, superadmin_role
