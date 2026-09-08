"""Contratos de entrada y salida para CU10: gestion de productos."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _ProductFields(_StrictModel):
    @field_validator("nombre", "descripcion", mode="before", check_fields=False)
    @classmethod
    def normalize_text(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class ProductCreateRequest(_ProductFields):
    id_categoria: int = Field(gt=0)
    id_temporada: int | None = Field(default=None, gt=0)
    nombre: str = Field(min_length=1, max_length=150)
    seccion: Literal["HOMBRE", "MUJER", "UNISEX"]
    descripcion: str | None = None
    precio: Decimal = Field(ge=0, max_digits=10, decimal_places=2)


class ProductUpdateRequest(_ProductFields):
    id_categoria: int | None = Field(default=None, gt=0)
    id_temporada: int | None = Field(default=None, gt=0)
    nombre: str | None = Field(default=None, min_length=1, max_length=150)
    seccion: Literal["HOMBRE", "MUJER", "UNISEX"] | None = None
    descripcion: str | None = None
    precio: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)

    @model_validator(mode="after")
    def require_changes(self) -> "ProductUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("Debe enviar al menos un campo para actualizar")
        non_nullable = {"id_categoria", "nombre", "seccion", "precio"}
        if any(getattr(self, field) is None for field in self.model_fields_set & non_nullable):
            raise ValueError("Los campos obligatorios no aceptan null")
        return self


class ProductStatusUpdateRequest(_StrictModel):
    estado: bool


class ProductVariantCreateRequest(_StrictModel):
    id_talla: int = Field(gt=0)
    id_color: int = Field(gt=0)
    sku: str = Field(min_length=1, max_length=100)

    @field_validator("sku", mode="before")
    @classmethod
    def normalize_sku(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class ProductVariantUpdateRequest(_StrictModel):
    id_talla: int | None = Field(default=None, gt=0)
    id_color: int | None = Field(default=None, gt=0)
    sku: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("sku", mode="before")
    @classmethod
    def normalize_sku(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def require_changes(self) -> "ProductVariantUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("Debe enviar al menos un campo para actualizar")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Los campos de variante no aceptan null")
        return self


class ProductVariantStatusUpdateRequest(_StrictModel):
    estado: bool


class ProductCollectionsRequest(_StrictModel):
    id_colecciones: list[int] = Field(min_length=1, max_length=100)

    @field_validator("id_colecciones")
    @classmethod
    def validate_collection_ids(cls, value: list[int]) -> list[int]:
        if any(item <= 0 for item in value):
            raise ValueError("Los identificadores deben ser positivos")
        if len(set(value)) != len(value):
            raise ValueError("No se permiten colecciones repetidas")
        return value


class ProductSupplierItemRequest(_StrictModel):
    id_proveedor: int = Field(gt=0)
    costo_referencia: Decimal | None = Field(
        default=None, ge=0, max_digits=10, decimal_places=2
    )


class ProductSuppliersRequest(_StrictModel):
    proveedores: list[ProductSupplierItemRequest] = Field(min_length=1, max_length=100)

    @field_validator("proveedores")
    @classmethod
    def validate_supplier_ids(
        cls, value: list[ProductSupplierItemRequest]
    ) -> list[ProductSupplierItemRequest]:
        ids = [item.id_proveedor for item in value]
        if len(set(ids)) != len(ids):
            raise ValueError("No se permiten proveedores repetidos")
        return value


class ProductSupplierUpdateRequest(_StrictModel):
    costo_referencia: Decimal | None = None

    @model_validator(mode="after")
    def require_changes(self) -> "ProductSupplierUpdateRequest":
        if "costo_referencia" not in self.model_fields_set:
            raise ValueError("Debe enviar el costo de referencia")
        return self


class ProductSupplierStatusUpdateRequest(_StrictModel):
    estado: bool


class ProductImageCreateRequest(_StrictModel):
    url_imagen: str = Field(min_length=1, max_length=2048)
    es_principal: bool = False

    @field_validator("url_imagen", mode="before")
    @classmethod
    def normalize_url(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("url_imagen")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            parsed = urlsplit(value)
        except ValueError as error:
            raise ValueError("La imagen debe usar una URL HTTP o HTTPS") from error
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            raise ValueError("La imagen debe usar una URL HTTP o HTTPS")
        return value


class ProductImageUpdateRequest(ProductImageCreateRequest):
    url_imagen: str | None = Field(default=None, min_length=1, max_length=2048)
    es_principal: bool | None = None

    @model_validator(mode="after")
    def require_changes(self) -> "ProductImageUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("Debe enviar al menos un campo para actualizar")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Los campos de imagen no aceptan null")
        return self


class ProductVariantData(BaseModel):
    id_variante_producto: int
    id_talla: int
    talla: str
    id_color: int
    color: str
    sku: str
    estado: bool
    created_at: datetime
    updated_at: datetime


class ProductCollectionData(BaseModel):
    id_producto_coleccion: int
    id_coleccion: int
    coleccion: str
    estado_coleccion: bool


class ProductSupplierData(BaseModel):
    id_producto_proveedor: int
    id_proveedor: int
    proveedor: str
    costo_referencia: Decimal | None
    estado: bool
    estado_proveedor: bool


class ProductImageData(BaseModel):
    id_imagen_producto: int
    url_imagen: str
    es_principal: bool
    created_at: datetime


class AdminProductData(BaseModel):
    id_producto: int
    id_categoria: int
    categoria: str
    id_temporada: int | None
    temporada: str | None
    nombre: str
    seccion: str
    descripcion: str | None
    precio: Decimal
    estado: bool
    imagen_principal: str | None = None
    total_variantes: int = 0
    created_at: datetime
    updated_at: datetime


class AdminProductDetailData(AdminProductData):
    variantes: list[ProductVariantData]
    colecciones: list[ProductCollectionData]
    proveedores: list[ProductSupplierData]
    imagenes: list[ProductImageData]


class ProductPaginationData(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class AdminProductListResponse(BaseModel):
    success: Literal[True] = True
    data: list[AdminProductData]
    pagination: ProductPaginationData


class AdminProductResponse(BaseModel):
    success: Literal[True] = True
    data: AdminProductDetailData


class AdminProductCreateResponse(AdminProductResponse):
    message: str = "Producto creado correctamente"


class AdminProductUpdateResponse(AdminProductResponse):
    message: str


class ProductVariantResponse(BaseModel):
    success: Literal[True] = True
    message: str
    data: ProductVariantData


class ProductCollectionsResponse(BaseModel):
    success: Literal[True] = True
    message: str
    data: list[ProductCollectionData]


class ProductSuppliersResponse(BaseModel):
    success: Literal[True] = True
    message: str
    data: list[ProductSupplierData]


class ProductSupplierResponse(BaseModel):
    success: Literal[True] = True
    message: str
    data: ProductSupplierData


class ProductImageResponse(BaseModel):
    success: Literal[True] = True
    message: str
    data: ProductImageData
