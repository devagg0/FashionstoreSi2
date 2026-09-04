"""Reglas de negocio de la gestión administrativa de usuarios y roles."""

from math import ceil

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.repositories.admin_user_repository import AdminUserRepository
from app.repositories.auth_repository import AuthRepository
from app.schemas.admin_user import (
    AdminRoleData,
    AdminUserCreateRequest,
    AdminUserData,
    PaginationData,
    UserRoleUpdateRequest,
    UserStatusUpdateRequest,
)
from app.schemas.auth import AuthenticatedUserData
from app.core.security import hash_password
from app.services.auth_service import (
    AuthService,
    EmailAlreadyRegisteredError,
)


ADMIN_ROLE_NAME = "ADMINISTRADOR"
CLIENT_ROLE_NAME = "CLIENTE"
EMPLOYEE_ROLE_NAMES = {"CAJERO", "ENCARGADO_SUCURSAL"}
SUPPLIER_ROLE_NAME = "PROVEEDOR"


class AdministratorRequiredError(Exception):
    """El usuario autenticado no posee el rol administrativo en la BD."""


class UserNotFoundError(Exception):
    """El usuario solicitado no existe."""


class RoleNotFoundError(Exception):
    """El nombre de rol solicitado no existe en t_rol."""


class SelfDeactivationError(Exception):
    """Un administrador intentó desactivar su propia cuenta."""


class SelfRoleChangeError(Exception):
    """Un administrador intentó cambiar su propio rol."""


class RoleProfileConflictError(Exception):
    """El usuario no tiene el perfil requerido para el rol solicitado."""


class AdminUserPersistenceError(Exception):
    """Una modificación administrativa no pudo persistirse."""


class InternalRoleNotConfiguredError(Exception):
    """Un rol interno permitido no está configurado en t_rol."""


class InternalRoleNotAllowedError(Exception):
    """El rol no puede utilizarse para crear una cuenta interna."""


class AdministratorRoleAssignmentError(Exception):
    """El rol del administrador principal no puede asignarse a otro usuario."""


class AdminUserService:
    """Orquesta autorización, consultas y cambios de usuarios de CU03."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = AdminUserRepository(db)
        self.auth_repository = AuthRepository(db)
        self.auth_service = AuthService(db)

    def authenticate_administrator(self, token: str) -> AuthenticatedUserData:
        """Reutiliza JWT y exige el rol ADMINISTRADOR leído desde la BD."""
        current_user = self.auth_service.get_current_user(token)
        if current_user.rol.upper() != ADMIN_ROLE_NAME:
            raise AdministratorRequiredError
        return current_user

    def list_users(
        self,
        *,
        search: str | None,
        role: str | None,
        state: bool | None,
        page: int,
        page_size: int,
    ) -> tuple[list[AdminUserData], PaginationData]:
        """Obtiene una página segura de usuarios con filtros opcionales."""
        rows, total = self.repository.list_users(
            search=search,
            role=role,
            state=state,
            page=page,
            page_size=page_size,
        )
        users = [self._to_user_data(user, role_name) for user, role_name in rows]
        pagination = PaginationData(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=ceil(total / page_size) if total else 0,
        )
        return users, pagination

    def create_user(self, payload: AdminUserCreateRequest) -> AdminUserData:
        """Crea un usuario interno y su perfil laboral cuando corresponde."""
        try:
            if payload.rol not in EMPLOYEE_ROLE_NAMES:
                raise InternalRoleNotAllowedError

            email = str(payload.correo)
            if self.auth_repository.get_user_by_email(email) is not None:
                raise EmailAlreadyRegisteredError

            role = self.repository.get_role_by_name(payload.rol)
            if role is None:
                raise InternalRoleNotConfiguredError

            user = self.auth_repository.create_user(
                role_id=role.id_rol,
                first_name=payload.nombre,
                last_name=payload.apellido,
                email=email,
                phone=payload.telefono,
                password_hash=hash_password(payload.password.get_secret_value()),
            )
            self.repository.create_employee(user_id=user.id_usuario)

            created_user = self._to_user_data(user, role.nombre)
            self.db.commit()
            return created_user
        except (
            EmailAlreadyRegisteredError,
            InternalRoleNotAllowedError,
            InternalRoleNotConfiguredError,
        ):
            self.db.rollback()
            raise
        except IntegrityError as error:
            self.db.rollback()

            try:
                email_exists = (
                    self.auth_repository.get_user_by_email(str(payload.correo))
                    is not None
                )
            except Exception as lookup_error:
                self.db.rollback()
                raise AdminUserPersistenceError from lookup_error

            self.db.rollback()
            if email_exists:
                raise EmailAlreadyRegisteredError from error
            raise AdminUserPersistenceError from error
        except Exception as error:
            self.db.rollback()
            raise AdminUserPersistenceError from error

    def get_user(self, user_id: int) -> AdminUserData:
        """Obtiene el detalle seguro de un usuario."""
        result = self.repository.get_user_with_role(user_id)
        if result is None:
            raise UserNotFoundError
        return self._to_user_data(*result)

    def update_status(
        self,
        *,
        current_admin_id: int,
        user_id: int,
        payload: UserStatusUpdateRequest,
    ) -> AdminUserData:
        """Activa o desactiva una cuenta protegiendo al administrador actual."""
        if current_admin_id == user_id and not payload.estado:
            raise SelfDeactivationError

        try:
            result = self.repository.get_user_with_role(user_id, for_update=True)
            if result is None:
                raise UserNotFoundError

            user, role_name = result
            self.repository.update_status(user, payload.estado)
            self.db.commit()
            return self._to_user_data(user, role_name)
        except (UserNotFoundError, SelfDeactivationError):
            self.db.rollback()
            raise
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminUserPersistenceError from error

    def update_role(
        self,
        *,
        current_admin_id: int,
        user_id: int,
        payload: UserRoleUpdateRequest,
    ) -> AdminUserData:
        """Cambia un rol por nombre después de validar el perfil asociado."""
        if current_admin_id == user_id:
            raise SelfRoleChangeError

        try:
            result = self.repository.get_user_with_role(user_id, for_update=True)
            if result is None:
                raise UserNotFoundError

            user, _current_role_name = result
            role = self.repository.get_role_by_name(payload.rol)
            if role is None:
                raise RoleNotFoundError
            if role.nombre.upper() == ADMIN_ROLE_NAME:
                raise AdministratorRoleAssignmentError

            self._validate_role_profile(user.id_usuario, role.nombre)
            self.repository.update_role(user, role)
            self.db.commit()
            return self._to_user_data(user, role.nombre)
        except (
            UserNotFoundError,
            AdministratorRoleAssignmentError,
            RoleNotFoundError,
            SelfRoleChangeError,
            RoleProfileConflictError,
        ):
            self.db.rollback()
            raise
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminUserPersistenceError from error

    def list_roles(self) -> list[AdminRoleData]:
        """Expone roles de t_rol sin crear, modificar ni eliminar registros."""
        return [
            AdminRoleData(
                id_rol=role.id_rol,
                nombre=role.nombre,
                descripcion=role.descripcion,
                estado=role.estado,
            )
            for role in self.repository.list_roles()
        ]

    def _validate_role_profile(self, user_id: int, role_name: str) -> None:
        """Aplica las asociaciones requeridas por cada rol de negocio."""
        normalized_role = role_name.upper()
        if normalized_role == CLIENT_ROLE_NAME:
            if not self.repository.has_client_profile(user_id):
                raise RoleProfileConflictError(
                    "El usuario requiere un registro asociado en t_cliente "
                    "para asumir el rol CLIENTE"
                )
        elif normalized_role in EMPLOYEE_ROLE_NAMES:
            if not self.repository.has_employee_profile(user_id):
                raise RoleProfileConflictError(
                    "El usuario requiere un perfil en t_empleado para asumir "
                    f"el rol {role_name}"
                )
        elif normalized_role == SUPPLIER_ROLE_NAME:
            if not self.repository.has_supplier_profile(user_id):
                raise RoleProfileConflictError(
                    "El usuario requiere una asociación en t_proveedor para "
                    "asumir el rol PROVEEDOR"
                )

    @staticmethod
    def _to_user_data(user: object, role_name: str) -> AdminUserData:
        """Construye la proyección permitida sin leer password_hash."""
        return AdminUserData(
            id_usuario=user.id_usuario,
            nombre=user.nombre,
            apellido=user.apellido,
            correo=user.correo,
            estado=user.estado,
            rol=role_name,
        )
