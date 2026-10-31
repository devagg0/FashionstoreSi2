"""Reglas de negocio y orquestación para PK07 / CU04: Asociar usuarios y sucursales a empresa."""

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.tenant_context import SUPERADMIN_ROLE, set_tenant_context
from app.PK07.CU04_AsociarUsuariosYSucursalesEmpresa.repository import CompanyResourcesRepository
from app.PK07.CU04_AsociarUsuariosYSucursalesEmpresa.schemas import (
    AssociateExistingBranchRequest,
    AssociateUserRequest,
    CompanyBranchData,
    CompanyResourcesData,
    CompanyUserData,
    CreateCompanyBranchRequest,
)


class CompanyNotFoundError(Exception):
    """La empresa indicada no existe en el sistema."""


class CompanyNotActiveError(Exception):
    """La empresa indicada no se encuentra en estado ACTIVA."""


class UserNotFoundError(Exception):
    """El usuario indicado no existe en el sistema."""


class UserInactiveError(Exception):
    """El usuario seleccionado está inactivo."""


class CannotAssignSuperadminError(Exception):
    """No se permite asociar a un usuario con rol SUPERADMIN o asignar dicho rol a nivel de empresa."""


class AdministratorRoleNotAllowedInCU04Error(Exception):
    """La asignación del rol ADMINISTRADOR corresponde exclusivamente a CU03."""


class OwnershipAssignmentNotAllowedInCU04Error(Exception):
    """La condición de Titular / Propietario no puede asignarse mediante CU04."""


class RoleNotConfiguredError(Exception):
    """El rol empresarial solicitado no existe o no se encuentra activo."""


class UserAlreadyAssociatedError(Exception):
    """El usuario ya se encuentra activamente asociado a esta empresa con el mismo rol."""


class UserAlreadyOwnerOfOtherCompanyError(Exception):
    """El usuario ya se encuentra registrado como propietario principal de otra empresa."""


class BranchNotFoundError(Exception):
    """La sucursal solicitada no existe."""


class BranchCityNotFoundError(Exception):
    """La ciudad especificada para la sucursal no existe."""


class BranchCityInactiveError(Exception):
    """La ciudad especificada para la sucursal se encuentra inactiva."""


class BranchAlreadyAssociatedError(Exception):
    """La sucursal ya pertenece activamente a esta empresa."""


class BranchBelongsToAnotherCompanyError(Exception):
    """La sucursal pertenece a otra empresa y la propiedad exclusiva prohíbe transferencias entre empresas."""


class CompanyResourcesPersistenceError(Exception):
    """Ocurrió un error inesperado al persistir la asociación o recurso empresarial."""


EMPLOYEE_ROLE_NAMES = {"CAJERO", "ENCARGADO_SUCURSAL"}
ALLOWED_CU04_ROLES = {"CAJERO", "ENCARGADO_SUCURSAL", "CLIENTE", "PROVEEDOR"}


class CompanyResourcesService:
    """Gestiona la consulta y asociación de usuarios y sucursales a una empresa SaaS."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = CompanyResourcesRepository(db)

    def _require_active_company(self, company_id: int):
        company = self.repository.get_company(company_id)
        if company is None:
            raise CompanyNotFoundError
        if company.estado != "ACTIVA":
            raise CompanyNotActiveError
        return company

    def list_company_users(
        self,
        company_id: int,
        *,
        role_name: str | None = None,
        state: str | None = None,
        search: str | None = None,
    ) -> list[CompanyUserData]:
        """Consulta los usuarios asociados a una empresa específica."""
        company = self.repository.get_company(company_id)
        if company is None:
            raise CompanyNotFoundError

        rows = self.repository.list_company_users(
            company_id,
            role_name=role_name,
            state=state,
            search=search,
        )
        return [
            CompanyUserData(
                id_empresa=membership.id_empresa,
                id_usuario=user.id_usuario,
                nombre=user.nombre,
                apellido=user.apellido,
                correo=user.correo,
                telefono=user.telefono,
                id_rol=role.id_rol,
                rol=role.nombre,
                estado=membership.estado,
                es_propietario=membership.es_propietario,
                created_at=membership.created_at,
                updated_at=membership.updated_at,
            )
            for membership, user, role in rows
        ]

    def list_company_branches(
        self,
        company_id: int,
        *,
        state: bool | None = None,
        search: str | None = None,
    ) -> list[CompanyBranchData]:
        """Consulta las sucursales asociadas a una empresa específica."""
        company = self.repository.get_company(company_id)
        if company is None:
            raise CompanyNotFoundError

        rows = self.repository.list_company_branches(
            company_id,
            state=state,
            search=search,
        )
        return [
            CompanyBranchData(
                id_sucursal=branch.id_sucursal,
                empresa_id=branch.empresa_id,
                id_ciudad=branch.id_ciudad,
                ciudad_nombre=city.nombre if city else None,
                nombre=branch.nombre,
                direccion=branch.direccion,
                telefono=branch.telefono,
                hora_apertura=branch.hora_apertura,
                hora_cierre=branch.hora_cierre,
                estado=branch.estado,
                created_at=branch.created_at,
                updated_at=branch.updated_at,
            )
            for branch, city in rows
        ]

    def get_company_resources(self, company_id: int) -> CompanyResourcesData:
        """Obtiene la vista consolidada de usuarios y sucursales de una empresa."""
        company = self.repository.get_company(company_id)
        if company is None:
            raise CompanyNotFoundError

        users = self.list_company_users(company_id)
        branches = self.list_company_branches(company_id)
        return CompanyResourcesData(
            id_empresa=company.id_empresa,
            empresa_nombre=company.nombre,
            empresa_codigo=company.codigo,
            usuarios=users,
            sucursales=branches,
        )

    def associate_user(
        self,
        company_id: int,
        payload: AssociateUserRequest,
    ) -> CompanyUserData:
        """Asocia un usuario existente con un rol empresarial válido a la empresa."""
        try:
            # 1. Validar empresa activa
            self._require_active_company(company_id)

            # 2. Validar usuario existente y activo
            user_data = self.repository.get_user_with_role(payload.id_usuario)
            if user_data is None:
                raise UserNotFoundError
            user, global_role = user_data
            if not user.estado:
                raise UserInactiveError

            # 3. Impedir asociar SUPERADMIN o ADMINISTRADOR mediante CU04
            if global_role.nombre.upper() == SUPERADMIN_ROLE or payload.rol.upper() == SUPERADMIN_ROLE:
                raise CannotAssignSuperadminError
            if payload.rol.upper() == "ADMINISTRADOR":
                raise AdministratorRoleNotAllowedInCU04Error
            if payload.rol.upper() not in ALLOWED_CU04_ROLES:
                raise RoleNotConfiguredError
            if payload.es_propietario:
                raise OwnershipAssignmentNotAllowedInCU04Error

            # 4. Validar rol empresarial elegible en t_rol
            role = self.repository.get_role_by_name(payload.rol)
            if role is None or not role.estado:
                raise RoleNotConfiguredError

            # 5. Validar conflicto de membresía previa
            existing_membership = self.repository.get_user_membership(company_id, payload.id_usuario)
            if (
                existing_membership is not None
                and existing_membership.estado == "ACTIVO"
                and existing_membership.id_rol == role.id_rol
                and existing_membership.es_propietario == payload.es_propietario
            ):
                raise UserAlreadyAssociatedError

            # 6. Validar restricción de un solo propietario por usuario
            if payload.es_propietario:
                other_ownership = self.repository.get_other_company_ownership(
                    payload.id_usuario,
                    exclude_company_id=company_id,
                )
                if other_ownership is not None:
                    raise UserAlreadyOwnerOfOtherCompanyError
                self.repository.clear_existing_owner(company_id, exclude_user_id=payload.id_usuario)

            # 7. Guardar membresía en t_usuario_empresa
            membership = self.repository.save_user_membership(
                company_id=company_id,
                user_id=user.id_usuario,
                role_id=role.id_rol,
                state=payload.estado,
                es_propietario=payload.es_propietario,
            )

            # 8. Sincronizar perfiles funcionales según rol (empleado / cliente)
            set_tenant_context(self.db, company_id, is_superadmin=True)
            if role.nombre.upper() in EMPLOYEE_ROLE_NAMES:
                if self.repository.get_employee(user.id_usuario, company_id) is None:
                    self.repository.create_employee(
                        user_id=user.id_usuario,
                        company_id=company_id,
                        cargo=role.nombre,
                    )
            elif role.nombre.upper() == "CLIENTE":
                if self.repository.get_client(user.id_usuario, company_id) is None:
                    self.repository.create_client(
                        user_id=user.id_usuario,
                        company_id=company_id,
                    )

            result = CompanyUserData(
                id_empresa=company_id,
                id_usuario=user.id_usuario,
                nombre=user.nombre,
                apellido=user.apellido,
                correo=user.correo,
                telefono=user.telefono,
                id_rol=role.id_rol,
                rol=role.nombre,
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
            AdministratorRoleNotAllowedInCU04Error,
            OwnershipAssignmentNotAllowedInCU04Error,
            RoleNotConfiguredError,
            UserAlreadyAssociatedError,
            UserAlreadyOwnerOfOtherCompanyError,
        ):
            self.db.rollback()
            raise
        except IntegrityError as error:
            self.db.rollback()
            constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
            if constraint == "uq_usuario_empresa_propietario":
                raise UserAlreadyOwnerOfOtherCompanyError from error
            raise CompanyResourcesPersistenceError from error
        except (SQLAlchemyError, Exception) as error:
            self.db.rollback()
            raise CompanyResourcesPersistenceError from error

    def create_company_branch(
        self,
        company_id: int,
        payload: CreateCompanyBranchRequest,
    ) -> CompanyBranchData:
        """Crea una sucursal directamente dentro de la empresa garantizando propiedad exclusiva."""
        try:
            # 1. Validar empresa activa
            self._require_active_company(company_id)

            # Validar límite de sucursales según plan SaaS
            from app.PK07.CU07_ConsultarPlanLimites.service import SaasPlanLimitsService
            SaasPlanLimitsService(self.db).validate_branch_creation_limit(company_id, is_reactivation=False)

            # 2. Validar ciudad activa
            city = self.repository.get_city(payload.id_ciudad, for_update=True)
            if city is None:
                raise BranchCityNotFoundError
            if not city.estado:
                raise BranchCityInactiveError

            # 3. Establecer contexto multitenant para inserciones seguras
            set_tenant_context(self.db, company_id, is_superadmin=True)

            # 4. Crear sucursal con propiedad exclusiva
            branch = self.repository.create_branch(
                company_id=company_id,
                id_ciudad=payload.id_ciudad,
                nombre=payload.nombre,
                direccion=payload.direccion,
                telefono=payload.telefono,
                hora_apertura=payload.hora_apertura,
                hora_cierre=payload.hora_cierre,
            )

            result = CompanyBranchData(
                id_sucursal=branch.id_sucursal,
                empresa_id=branch.empresa_id,
                id_ciudad=branch.id_ciudad,
                ciudad_nombre=city.nombre,
                nombre=branch.nombre,
                direccion=branch.direccion,
                telefono=branch.telefono,
                hora_apertura=branch.hora_apertura,
                hora_cierre=branch.hora_cierre,
                estado=branch.estado,
                created_at=branch.created_at,
                updated_at=branch.updated_at,
            )
            self.db.commit()
            return result
        except (
            CompanyNotFoundError,
            CompanyNotActiveError,
            BranchCityNotFoundError,
            BranchCityInactiveError,
        ):
            self.db.rollback()
            raise
        except (SQLAlchemyError, Exception) as error:
            self.db.rollback()
            raise CompanyResourcesPersistenceError from error

    def associate_existing_branch(
        self,
        company_id: int,
        payload: AssociateExistingBranchRequest,
    ) -> CompanyBranchData:
        """Asocia o reactiva una sucursal respetando la propiedad exclusiva e impidiendo cruces entre empresas."""
        try:
            # 1. Validar empresa activa
            self._require_active_company(company_id)

            # 2. Buscar sucursal existente
            branch_data = self.repository.get_branch(payload.id_sucursal)
            if branch_data is None:
                raise BranchNotFoundError
            branch, city = branch_data

            # 3. Validar propiedad exclusiva y aislamiento multitenant
            if branch.empresa_id == company_id:
                if branch.estado:
                    raise BranchAlreadyAssociatedError
                # Si estaba inactiva dentro de esta misma empresa, se reactiva validando el límite
                from app.PK07.CU07_ConsultarPlanLimites.service import SaasPlanLimitsService
                SaasPlanLimitsService(self.db).validate_branch_creation_limit(company_id, is_reactivation=True)
                branch.estado = True
                self.db.flush()
            else:
                # La sucursal pertenece a otra empresa: propiedad exclusiva prohíbe cruces
                raise BranchBelongsToAnotherCompanyError

            result = CompanyBranchData(
                id_sucursal=branch.id_sucursal,
                empresa_id=branch.empresa_id,
                id_ciudad=branch.id_ciudad,
                ciudad_nombre=city.nombre if city else None,
                nombre=branch.nombre,
                direccion=branch.direccion,
                telefono=branch.telefono,
                hora_apertura=branch.hora_apertura,
                hora_cierre=branch.hora_cierre,
                estado=branch.estado,
                created_at=branch.created_at,
                updated_at=branch.updated_at,
            )
            self.db.commit()
            return result
        except (
            CompanyNotFoundError,
            CompanyNotActiveError,
            BranchNotFoundError,
            BranchAlreadyAssociatedError,
            BranchBelongsToAnotherCompanyError,
        ):
            self.db.rollback()
            raise
        except (SQLAlchemyError, Exception) as error:
            self.db.rollback()
            raise CompanyResourcesPersistenceError from error

