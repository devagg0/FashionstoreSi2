"""Contratos de CU06 sobre la asociación empleado-sucursal existente."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EmployeeBranchCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id_empleado: int = Field(gt=0)
    id_sucursal: int = Field(gt=0)


class EmployeeBranchStatusUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estado: bool


class AdminEmployeeBranchData(BaseModel):
    id_empleado_sucursal: int
    id_empleado: int
    nombre_empleado: str
    correo: str
    rol: str
    id_sucursal: int
    nombre_sucursal: str
    fecha_asignacion: date
    estado: bool


class EmployeeBranchPaginationData(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class AdminEmployeeBranchResponse(BaseModel):
    success: Literal[True] = True
    data: AdminEmployeeBranchData


class AdminEmployeeBranchUpdateResponse(AdminEmployeeBranchResponse):
    message: str


class AdminEmployeeBranchListResponse(BaseModel):
    success: Literal[True] = True
    data: list[AdminEmployeeBranchData]
    pagination: EmployeeBranchPaginationData


class AssignableEmployeeData(BaseModel):
    id_empleado: int
    id_usuario: int
    nombre: str
    apellido: str
    correo: str
    rol: str
    estado: bool


class AssignableEmployeeListResponse(BaseModel):
    success: Literal[True] = True
    data: list[AssignableEmployeeData]
    pagination: EmployeeBranchPaginationData
