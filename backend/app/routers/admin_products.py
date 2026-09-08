"""Endpoints protegidos de CU10 para gestionar productos."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.routers.admin_users import AdminDependency, COMMON_ERROR_RESPONSES
from app.schemas.admin_products import (
    AdminProductCreateResponse,
    AdminProductListResponse,
    AdminProductResponse,
    AdminProductUpdateResponse,
    ProductCollectionsRequest,
    ProductCollectionsResponse,
    ProductCreateRequest,
    ProductImageCreateRequest,
    ProductImageResponse,
    ProductImageUpdateRequest,
    ProductStatusUpdateRequest,
    ProductSupplierResponse,
    ProductSuppliersRequest,
    ProductSuppliersResponse,
    ProductSupplierStatusUpdateRequest,
    ProductSupplierUpdateRequest,
    ProductUpdateRequest,
    ProductVariantCreateRequest,
    ProductVariantResponse,
    ProductVariantStatusUpdateRequest,
    ProductVariantUpdateRequest,
)
from app.schemas.auth import ErrorResponse
from app.services.admin_products import (
    AdminProductPersistenceError,
    AdminProductService,
    ProductChildNotFoundError,
    ProductConflictError,
    ProductImageStorageConfigurationError,
    ProductImageStorageError,
    ProductImageValidationError,
    ProductNotFoundError,
    ProductReferenceInactiveError,
    ProductReferenceNotFoundError,
)


router = APIRouter(
    prefix="/api/admin/products",
    tags=["Administracion de productos"],
)

PRODUCT_ERROR_RESPONSES = {
    **COMMON_ERROR_RESPONSES,
    status.HTTP_404_NOT_FOUND: {
        "model": ErrorResponse,
        "description": "Producto o referencia no encontrada",
    },
    status.HTTP_409_CONFLICT: {
        "model": ErrorResponse,
        "description": "SKU o asociacion duplicada",
    },
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": ErrorResponse,
        "description": "Referencia inactiva o datos invalidos",
    },
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "model": ErrorResponse,
        "description": "No fue posible procesar el producto",
    },
    status.HTTP_502_BAD_GATEWAY: {
        "model": ErrorResponse,
        "description": "Supabase Storage no pudo guardar la imagen",
    },
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        "model": ErrorResponse,
        "description": "Supabase Storage no esta configurado",
    },
}

OPERATION_ERRORS = (
    ProductNotFoundError,
    ProductChildNotFoundError,
    ProductReferenceNotFoundError,
    ProductReferenceInactiveError,
    ProductConflictError,
    ProductImageValidationError,
    ProductImageStorageConfigurationError,
    ProductImageStorageError,
    AdminProductPersistenceError,
    SQLAlchemyError,
)


def _error_response(error: Exception) -> JSONResponse:
    if isinstance(
        error,
        (ProductNotFoundError, ProductChildNotFoundError, ProductReferenceNotFoundError),
    ):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(error, ProductConflictError):
        code = status.HTTP_409_CONFLICT
    elif isinstance(error, ProductReferenceInactiveError):
        code = status.HTTP_422_UNPROCESSABLE_CONTENT
    elif isinstance(error, ProductImageValidationError):
        code = status.HTTP_422_UNPROCESSABLE_CONTENT
    elif isinstance(error, ProductImageStorageConfigurationError):
        code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif isinstance(error, ProductImageStorageError):
        code = status.HTTP_502_BAD_GATEWAY
    else:
        code = status.HTTP_500_INTERNAL_SERVER_ERROR
    message = str(error) if code != 500 else "No fue posible procesar el producto"
    return JSONResponse(
        status_code=code,
        content={"success": False, "message": message},
    )


@router.get(
    "",
    response_model=AdminProductListResponse,
    summary="Listar productos",
    responses=PRODUCT_ERROR_RESPONSES,
)
def list_products(
    administrator: AdminDependency,
    search: Annotated[str | None, Query(max_length=150)] = None,
    estado: bool | None = None,
    id_categoria: Annotated[int | None, Query(gt=0)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
) -> AdminProductListResponse | JSONResponse:
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        data, pagination = AdminProductService(db).list_products(
            search=search,
            state=estado,
            category_id=id_categoria,
            page=page,
            page_size=page_size,
        )
        return AdminProductListResponse(data=data, pagination=pagination)
    except OPERATION_ERRORS as error:
        db.rollback()
        return _error_response(error)


@router.get(
    "/{id_producto}",
    response_model=AdminProductResponse,
    summary="Obtener detalle de producto",
    responses=PRODUCT_ERROR_RESPONSES,
)
def get_product(
    id_producto: int,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminProductResponse | JSONResponse:
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        return AdminProductResponse(
            data=AdminProductService(db).get_product(id_producto)
        )
    except OPERATION_ERRORS as error:
        db.rollback()
        return _error_response(error)


@router.post(
    "",
    response_model=AdminProductCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar producto",
    responses=PRODUCT_ERROR_RESPONSES,
)
def create_product(
    payload: ProductCreateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminProductCreateResponse | JSONResponse:
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        return AdminProductCreateResponse(
            data=AdminProductService(db).create_product(payload)
        )
    except OPERATION_ERRORS as error:
        return _error_response(error)


@router.patch(
    "/{id_producto}",
    response_model=AdminProductUpdateResponse,
    summary="Actualizar producto",
    responses=PRODUCT_ERROR_RESPONSES,
)
def update_product(
    id_producto: int,
    payload: ProductUpdateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminProductUpdateResponse | JSONResponse:
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        return AdminProductUpdateResponse(
            message="Producto actualizado correctamente",
            data=AdminProductService(db).update_product(
                product_id=id_producto, payload=payload
            ),
        )
    except OPERATION_ERRORS as error:
        return _error_response(error)


@router.patch(
    "/{id_producto}/status",
    response_model=AdminProductUpdateResponse,
    summary="Activar o desactivar producto",
    responses=PRODUCT_ERROR_RESPONSES,
)
def update_product_status(
    id_producto: int,
    payload: ProductStatusUpdateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminProductUpdateResponse | JSONResponse:
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        return AdminProductUpdateResponse(
            message="Estado del producto actualizado correctamente",
            data=AdminProductService(db).update_product_status(
                product_id=id_producto, payload=payload
            ),
        )
    except OPERATION_ERRORS as error:
        return _error_response(error)


@router.post(
    "/{id_producto}/variants",
    response_model=ProductVariantResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar variante de producto",
    responses=PRODUCT_ERROR_RESPONSES,
)
def create_variant(
    id_producto: int,
    payload: ProductVariantCreateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> ProductVariantResponse | JSONResponse:
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        return ProductVariantResponse(
            message="Variante creada correctamente",
            data=AdminProductService(db).create_variant(
                product_id=id_producto, payload=payload
            ),
        )
    except OPERATION_ERRORS as error:
        return _error_response(error)


@router.patch(
    "/{id_producto}/variants/{id_variante_producto}",
    response_model=ProductVariantResponse,
    summary="Actualizar variante de producto",
    responses=PRODUCT_ERROR_RESPONSES,
)
def update_variant(
    id_producto: int,
    id_variante_producto: int,
    payload: ProductVariantUpdateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> ProductVariantResponse | JSONResponse:
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        return ProductVariantResponse(
            message="Variante actualizada correctamente",
            data=AdminProductService(db).update_variant(
                product_id=id_producto,
                variant_id=id_variante_producto,
                payload=payload,
            ),
        )
    except OPERATION_ERRORS as error:
        return _error_response(error)


@router.patch(
    "/{id_producto}/variants/{id_variante_producto}/status",
    response_model=ProductVariantResponse,
    summary="Activar o desactivar variante",
    responses=PRODUCT_ERROR_RESPONSES,
)
def update_variant_status(
    id_producto: int,
    id_variante_producto: int,
    payload: ProductVariantStatusUpdateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> ProductVariantResponse | JSONResponse:
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        return ProductVariantResponse(
            message="Estado de la variante actualizado correctamente",
            data=AdminProductService(db).update_variant_status(
                product_id=id_producto,
                variant_id=id_variante_producto,
                payload=payload,
            ),
        )
    except OPERATION_ERRORS as error:
        return _error_response(error)


@router.post(
    "/{id_producto}/collections",
    response_model=ProductCollectionsResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Asociar colecciones al producto",
    responses=PRODUCT_ERROR_RESPONSES,
)
def add_collections(
    id_producto: int,
    payload: ProductCollectionsRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> ProductCollectionsResponse | JSONResponse:
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        return ProductCollectionsResponse(
            message="Colecciones asociadas correctamente",
            data=AdminProductService(db).add_collections(
                product_id=id_producto, payload=payload
            ),
        )
    except OPERATION_ERRORS as error:
        return _error_response(error)


@router.post(
    "/{id_producto}/suppliers",
    response_model=ProductSuppliersResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Asociar proveedores al producto",
    responses=PRODUCT_ERROR_RESPONSES,
)
def add_suppliers(
    id_producto: int,
    payload: ProductSuppliersRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> ProductSuppliersResponse | JSONResponse:
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        return ProductSuppliersResponse(
            message="Proveedores asociados correctamente",
            data=AdminProductService(db).add_suppliers(
                product_id=id_producto, payload=payload
            ),
        )
    except OPERATION_ERRORS as error:
        return _error_response(error)


@router.patch(
    "/{id_producto}/suppliers/{id_producto_proveedor}",
    response_model=ProductSupplierResponse,
    summary="Actualizar costo de proveedor del producto",
    responses=PRODUCT_ERROR_RESPONSES,
)
def update_supplier(
    id_producto: int,
    id_producto_proveedor: int,
    payload: ProductSupplierUpdateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> ProductSupplierResponse | JSONResponse:
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        return ProductSupplierResponse(
            message="Proveedor del producto actualizado correctamente",
            data=AdminProductService(db).update_supplier(
                product_id=id_producto,
                association_id=id_producto_proveedor,
                payload=payload,
            ),
        )
    except OPERATION_ERRORS as error:
        return _error_response(error)


@router.patch(
    "/{id_producto}/suppliers/{id_producto_proveedor}/status",
    response_model=ProductSupplierResponse,
    summary="Activar o desactivar proveedor del producto",
    responses=PRODUCT_ERROR_RESPONSES,
)
def update_supplier_status(
    id_producto: int,
    id_producto_proveedor: int,
    payload: ProductSupplierStatusUpdateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> ProductSupplierResponse | JSONResponse:
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        return ProductSupplierResponse(
            message="Estado del proveedor del producto actualizado correctamente",
            data=AdminProductService(db).update_supplier_status(
                product_id=id_producto,
                association_id=id_producto_proveedor,
                payload=payload,
            ),
        )
    except OPERATION_ERRORS as error:
        return _error_response(error)


@router.post(
    "/{id_producto}/images",
    response_model=ProductImageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar imagen del producto",
    responses=PRODUCT_ERROR_RESPONSES,
)
def create_image(
    id_producto: int,
    payload: ProductImageCreateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> ProductImageResponse | JSONResponse:
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        return ProductImageResponse(
            message="Imagen creada correctamente",
            data=AdminProductService(db).create_image(
                product_id=id_producto, payload=payload
            ),
        )
    except OPERATION_ERRORS as error:
        return _error_response(error)


@router.post(
    "/{id_producto}/images/upload",
    response_model=ProductImageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Subir imagen del producto",
    responses=PRODUCT_ERROR_RESPONSES,
)
def upload_image(
    id_producto: int,
    administrator: AdminDependency,
    archivo: Annotated[UploadFile, File(description="Imagen JPG, PNG o WEBP")],
    es_principal: Annotated[bool, Form()] = False,
    db: Session = Depends(get_db),
) -> ProductImageResponse | JSONResponse:
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        content = archivo.file.read(AdminProductService.MAX_IMAGE_SIZE_BYTES + 1)
        return ProductImageResponse(
            message="Imagen subida correctamente",
            data=AdminProductService(db).upload_image(
                product_id=id_producto,
                filename=archivo.filename or "",
                content_type=archivo.content_type or "",
                content=content,
                is_primary=es_principal,
            ),
        )
    except OPERATION_ERRORS as error:
        return _error_response(error)
    finally:
        archivo.file.close()


@router.patch(
    "/{id_producto}/images/{id_imagen_producto}",
    response_model=ProductImageResponse,
    summary="Actualizar imagen del producto",
    responses=PRODUCT_ERROR_RESPONSES,
)
def update_image(
    id_producto: int,
    id_imagen_producto: int,
    payload: ProductImageUpdateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> ProductImageResponse | JSONResponse:
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        return ProductImageResponse(
            message="Imagen actualizada correctamente",
            data=AdminProductService(db).update_image(
                product_id=id_producto,
                image_id=id_imagen_producto,
                payload=payload,
            ),
        )
    except OPERATION_ERRORS as error:
        return _error_response(error)
