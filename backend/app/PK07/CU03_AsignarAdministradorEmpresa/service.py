"""Reglas transaccionales de CU03: asignar administrador de empresa."""

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.PK07.CU03_AsignarAdministradorEmpresa.repository import CompanyAdminRepository
from app.PK07.CU03_AsignarAdministradorEmpresa.schemas import (
    AssignCompanyAdminRequest,
    AvailableUserData,
    AvailableUsersPaginationData,
    CompanyAdminData,
    CreateAndAssignCompanyAdminRequest,
)


class CompanyNotFoundError(Exception):
    """La empresa indicada no existe en el sistema."""


class CompanyNotActiveError(Exception):
    """La empresa no se encuentra en estado ACTIVA."""


class UserNotFoundError(Exception):
    """El usuario indicado no existe en el sistema."""


class UserInactiveError(Exception):
    """El usuario seleccionado está inactivo."""


class CannotAssignSuperadminError(Exception):
    """No se permite asignar a un usuario SUPERADMIN como administrador de empresa."""


class UserNotEligibleRoleError(Exception):
    """El usuario no posee el rol ADMINISTRADOR requerido."""


class EmailAlreadyExistsError(Exception):
    """El correo electrónico ya se encuentra registrado para otro usuario."""


class UserAlreadyAssignedError(Exception):
    """El usuario ya se encuentra asignado como administrador principal de esta empresa."""


class UserAlreadyAssignedToOtherCompanyError(Exception):
    """El usuario ya es administrador principal de otra empresa."""


class AdminRoleNotConfiguredError(Exception):
    """El rol ADMINISTRADOR no existe o está deshabilitado en t_rol."""


class AdminAssignmentNotFoundError(Exception):
    """La empresa no tiene un administrador asignado actualmente."""


class CompanyAdminPersistenceError(Exception):
    """Ocurrió un error inesperado al persistir la asignación del administrador."""


class CompanyAdminService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = CompanyAdminRepository(db)

    def get_assigned_admin(self, company_id: int) -> CompanyAdminData:
        """Consulta el administrador asignado a una empresa."""
        company = self.repository.get_company(company_id)
        if company is None:
            raise CompanyNotFoundError

        result = self.repository.get_assigned_admin(company_id)
        if result is None:
            raise AdminAssignmentNotFoundError

        membership, user, role = result
        return CompanyAdminData(
            id_empresa=company_id,
            id_usuario=user.id_usuario,
            nombre=user.nombre,
            apellido=user.apellido,
            correo=user.correo,
            telefono=user.telefono,
            rol=role.nombre,
            estado=membership.estado,
            es_propietario=membership.es_propietario,
            created_at=membership.created_at,
            updated_at=membership.updated_at,
        )

    def search_available_users(
        self,
        *,
        search: str | None = None,
        company_id: int | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[AvailableUserData], AvailableUsersPaginationData]:
        """Busca usuarios activos ADMINISTRADOR no asignados como titulares a otra empresa."""
        rows, total = self.repository.search_available_users(
            search=search,
            company_id=company_id,
            page=page,
            page_size=page_size,
        )
        data = [
            AvailableUserData(
                id_usuario=user.id_usuario,
                nombre=user.nombre,
                apellido=user.apellido,
                correo=user.correo,
                telefono=user.telefono,
                rol_global=role.nombre,
                estado=user.estado,
                created_at=user.created_at,
            )
            for user, role in rows
        ]
        pagination = AvailableUsersPaginationData.create(
            page=page,
            page_size=page_size,
            total=total,
        )
        return data, pagination

    def assign_admin(
        self,
        company_id: int,
        payload: AssignCompanyAdminRequest,
    ) -> CompanyAdminData:
        """Asigna o reasigna un usuario ADMINISTRADOR existente a una empresa."""
        try:
            # 1. Validar empresa activa
            company = self.repository.get_company(company_id)
            if company is None:
                raise CompanyNotFoundError
            if company.estado != "ACTIVA":
                raise CompanyNotActiveError

            # 2. Validar usuario activo y rol global ADMINISTRADOR con bloqueo para evitar condiciones de carrera
            user_tuple = self.repository.get_user_with_role(payload.id_usuario, for_update=True)
            if user_tuple is None:
                raise UserNotFoundError
            user, global_role = user_tuple
            if not user.estado:
                raise UserInactiveError
            if global_role.nombre.upper() == "SUPERADMIN":
                raise CannotAssignSuperadminError
            if global_role.nombre.upper() != "ADMINISTRADOR":
                raise UserNotEligibleRoleError

            # 3. Validar restricción: un administrador solo puede ser titular de una empresa
            other_ownership = self.repository.get_other_company_ownership(
                payload.id_usuario,
                exclude_company_id=company_id,
            )
            if other_ownership is not None:
                raise UserAlreadyAssignedToOtherCompanyError

            # 4. Validar existencia del rol ADMINISTRADOR
            admin_role = self.repository.get_role_by_name("ADMINISTRADOR")
            if admin_role is None or not admin_role.estado:
                raise AdminRoleNotConfiguredError

            # 5. Validar duplicados exactos en esta misma empresa
            current_admin = self.repository.get_assigned_admin(company_id)
            if current_admin is not None:
                curr_membership, curr_user, _ = current_admin
                if (
                    curr_user.id_usuario == payload.id_usuario
                    and curr_membership.es_propietario
                    and curr_membership.estado == payload.estado
                ):
                    raise UserAlreadyAssignedError

            # 6. Gestionar la asignación sin violar uq_usuario_empresa_propietario
            self.repository.clear_existing_owner(company_id, exclude_user_id=payload.id_usuario)
            membership = self.repository.save_admin_membership(
                company_id=company_id,
                user_id=payload.id_usuario,
                role_id=admin_role.id_rol,
                state=payload.estado,
            )

            result = CompanyAdminData(
                id_empresa=company_id,
                id_usuario=user.id_usuario,
                nombre=user.nombre,
                apellido=user.apellido,
                correo=user.correo,
                telefono=user.telefono,
                rol=admin_role.nombre,
                estado=membership.estado,
                es_propietario=membership.es_propietario,
                created_at=membership.created_at,
                updated_at=membership.updated_at,
            )
            self.db.commit()
            return result
        except (
            CompanyNotFoundError,
            CompanyNotActiveError,
            UserNotFoundError,
            UserInactiveError,
            CannotAssignSuperadminError,
            UserNotEligibleRoleError,
            UserAlreadyAssignedToOtherCompanyError,
            UserAlreadyAssignedError,
            AdminRoleNotConfiguredError,
            AdminAssignmentNotFoundError,
        ):
            self.db.rollback()
            raise
        except IntegrityError as error:
            self.db.rollback()
            constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
            if constraint == "uq_usuario_empresa_propietario":
                raise UserAlreadyAssignedError from error
            raise CompanyAdminPersistenceError from error
        except (SQLAlchemyError, Exception) as error:
            self.db.rollback()
            raise CompanyAdminPersistenceError from error

    def create_and_assign_admin(
        self,
        company_id: int,
        payload: CreateAndAssignCompanyAdminRequest,
    ) -> CompanyAdminData:
        """Crea un usuario nuevo con rol ADMINISTRADOR y lo asocia directamente a la empresa."""
        try:
            # 1. Validar empresa activa
            company = self.repository.get_company(company_id)
            if company is None:
                raise CompanyNotFoundError
            if company.estado != "ACTIVA":
                raise CompanyNotActiveError

            # 2. Validar rol ADMINISTRADOR configurado
            admin_role = self.repository.get_role_by_name("ADMINISTRADOR")
            if admin_role is None or not admin_role.estado:
                raise AdminRoleNotConfiguredError

            # 3. Validar correo duplicado
            email = str(payload.correo).strip().lower()
            if self.repository.get_user_by_email(email) is not None:
                raise EmailAlreadyExistsError

            # 4. Hashear contraseña con Argon2
            hashed_password = hash_password(payload.password.get_secret_value())

            # 5. Crear usuario en t_usuario
            user = self.repository.create_admin_user(
                first_name=payload.nombre.strip(),
                last_name=payload.apellido.strip(),
                email=email,
                password_hash=hashed_password,
                role_id=admin_role.id_rol,
                phone=payload.telefono.strip() if payload.telefono else None,
            )

            # 6. Desmarcar propietario previo si existe
            self.repository.clear_existing_owner(company_id, exclude_user_id=user.id_usuario)

            # 7. Asignar membresía como administrador y propietario
            membership = self.repository.save_admin_membership(
                company_id=company_id,
                user_id=user.id_usuario,
                role_id=admin_role.id_rol,
                state=payload.estado,
            )

            result = CompanyAdminData(
                id_empresa=company_id,
                id_usuario=user.id_usuario,
                nombre=user.nombre,
                apellido=user.apellido,
                correo=user.correo,
                telefono=user.telefono,
                rol=admin_role.nombre,
                estado=membership.estado,
                es_propietario=membership.es_propietario,
                created_at=membership.created_at,
                updated_at=membership.updated_at,
            )
            self.db.commit()
            return result
        except (
            CompanyNotFoundError,
            CompanyNotActiveError,
            EmailAlreadyExistsError,
            AdminRoleNotConfiguredError,
        ):
            self.db.rollback()
            raise
        except IntegrityError as error:
            self.db.rollback()
            constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
            if constraint in ("uq_usuario_correo", "ix_usuario_correo"):
                raise EmailAlreadyExistsError from error
            if constraint == "uq_usuario_empresa_propietario":
                raise UserAlreadyAssignedError from error
            raise CompanyAdminPersistenceError from error
        except (SQLAlchemyError, Exception) as error:
            self.db.rollback()
            raise CompanyAdminPersistenceError from error
