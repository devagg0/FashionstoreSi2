"""Contratos Pydantic para PK08 - CU08: Preparar información para operación offline en FashionStore (Web Angular PWA)."""

from datetime import datetime, time
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class OfflineBranchData(BaseModel):
    """Sucursal autorizada para operar en la PWA."""

    model_config = ConfigDict(from_attributes=True)

    id_sucursal: int
    id_ciudad: int
    ciudad: str | None = None
    nombre: str
    direccion: str
    telefono: str | None = None
    hora_apertura: time | None = None
    hora_cierre: time | None = None
    estado: bool = True


class OfflineCategoryData(BaseModel):
    """Categoría para navegación y filtros del catálogo offline."""

    model_config = ConfigDict(from_attributes=True)

    id_categoria: int
    nombre: str
    descripcion: str | None = None
    estado: bool = True


class OfflineSizeData(BaseModel):
    """Talla normalizada de producto."""

    model_config = ConfigDict(from_attributes=True)

    id_talla: int
    nombre: str
    descripcion: str | None = None
    estado: bool = True


class OfflineColorData(BaseModel):
    """Color normalizado de producto."""

    model_config = ConfigDict(from_attributes=True)

    id_color: int
    nombre: str
    codigo_hex: str | None = None
    estado: bool = True


class OfflineProductData(BaseModel):
    """Producto base con precio de lista para venta presencial y catálogo offline."""

    model_config = ConfigDict(from_attributes=True)

    id_producto: int
    id_categoria: int
    categoria: str | None = None
    id_temporada: int | None = None
    nombre: str
    seccion: str
    descripcion: str | None = None
    precio: Decimal
    imagen_principal: str | None = None
    imagenes: list[str] = Field(default_factory=list)
    estado: bool = True


class OfflineVariantData(BaseModel):
    """Variante física comercializable (talla + color + SKU + precio correspondiente)."""

    model_config = ConfigDict(from_attributes=True)

    id_variante_producto: int
    id_producto: int
    id_talla: int
    talla: str | None = None
    id_color: int
    color: str | None = None
    color_hex: str | None = None
    sku: str
    precio: Decimal | None = None
    estado: bool = True


class OfflineStockData(BaseModel):
    """Existencia física en sucursal autorizada (sin modificar inventario)."""

    model_config = ConfigDict(from_attributes=True)

    id_inventario_sucursal: int
    id_sucursal: int
    id_variante_producto: int
    id_producto: int | None = None
    stock_actual: int
    stock_reservado: int
    stock_disponible: int
    stock_minimo: int
    updated_at: datetime


class OfflineClientData(BaseModel):
    """Cliente mínimo indispensable para venta offline sin datos sensibles ni contraseñas."""

    model_config = ConfigDict(from_attributes=True)

    id_cliente: int
    id_usuario: int
    nombre: str
    apellido: str
    correo: str | None = None
    telefono: str | None = None


class OfflinePackageMetadata(BaseModel):
    """Metadatos de versión, vigencia e integridad del paquete offline."""

    version: str
    fecha_generacion: datetime
    valido_hasta: datetime
    vigencia_segundos: int
    id_empresa: int
    empresa_codigo: str
    empresa_nombre: str
    id_usuario: int
    usuario_rol: str
    sucursales_autorizadas_ids: list[int]
    suscripcion_activa: bool = True
    funcionalidad_offline: bool = True
    total_sucursales: int
    total_categorias: int
    total_productos: int
    total_variantes: int
    total_existencias: int
    total_clientes: int


class OfflinePackageResponse(BaseModel):
    """Respuesta completa del paquete de datos para persistir en IndexedDB."""

    success: Literal[True] = True
    message: str = "Paquete offline preparado exitosamente"
    metadata: OfflinePackageMetadata
    sucursales: list[OfflineBranchData]
    categorias: list[OfflineCategoryData]
    tallas: list[OfflineSizeData]
    colores: list[OfflineColorData]
    productos: list[OfflineProductData]
    variantes: list[OfflineVariantData]
    existencias: list[OfflineStockData]
    clientes: list[OfflineClientData]


class OfflineStatusResponse(BaseModel):
    """Respuesta liviana de validación de vigencia y cambios del paquete offline."""

    success: Literal[True] = True
    id_empresa: int
    version_actual: str
    version_solicitada: str | None = None
    vigente: bool
    requiere_actualizacion: bool
    fecha_generacion: datetime
    valido_hasta: datetime
    sucursales_autorizadas_ids: list[int]
    suscripcion_activa: bool = True
    funcionalidad_offline: bool = True
    message: str

