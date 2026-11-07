"""Lógica de negocio y orquestación para PK08 - CU08 y CU09: Preparar y consultar catálogo y disponibilidad offline en FashionStore (Web Angular PWA)."""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
from typing import Any

from sqlalchemy.orm import Session

from app.PK07.CU07_ConsultarPlanLimites.service import (
    FeatureNotEnabledError,
    NoActiveSubscriptionError,
    SaasPlanLimitsService,
)
from app.PK08.CU08_PrepararInformacionOffline.repository import OfflineRepository
from app.PK08.CU08_PrepararInformacionOffline.schemas import (
    OfflineBranchData,
    OfflineCategoryData,
    OfflineClientData,
    OfflineCollectionData,
    OfflineColorData,
    OfflinePackageMetadata,
    OfflinePackageResponse,
    OfflineProductColorFacet,
    OfflineProductData,
    OfflineProductImageData,
    OfflineProductSizeFacet,
    OfflineSizeData,
    OfflineStatusResponse,
    OfflineStockData,
    OfflineVariantData,
)
from app.schemas.auth import AuthenticatedUserData

ALLOWED_OFFLINE_ROLES: set[str] = {
    "SUPERADMIN",
    "ADMINISTRADOR",
    "ADMIN",
    "CAJERO",
    "ENCARGADO_SUCURSAL",
    "CLIENTE",
}
ADMINISTRATIVE_ROLES: set[str] = {"SUPERADMIN", "ADMINISTRADOR", "ADMIN"}
EMPLOYEE_OFFLINE_ROLES: set[str] = {"CAJERO", "ENCARGADO_SUCURSAL"}
CLIENT_OFFLINE_ROLES: set[str] = {"CLIENTE"}
DEFAULT_OFFLINE_TTL_SECONDS: int = 86400  # 24 horas por defecto
SHORT_DESCRIPTION_LENGTH: int = 180


class OfflineServiceError(Exception):
    """Excepción base para errores de preparación y consulta offline."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class UnauthorizedOfflineRoleError(OfflineServiceError):
    def __init__(self, role: str) -> None:
        super().__init__(
            status_code=403,
            message=f"El rol '{role}' no cuenta con permisos para operar o descargar datos offline en FashionStore.",
        )


class CompanyNotActiveError(OfflineServiceError):
    def __init__(self, message: str = "La empresa no se encuentra en estado ACTIVA.") -> None:
        super().__init__(status_code=403, message=message)


class CompanyNotFoundError(OfflineServiceError):
    def __init__(self, message: str = "Empresa no encontrada.") -> None:
        super().__init__(status_code=404, message=message)


class EmployeeProfileNotFoundError(OfflineServiceError):
    def __init__(
        self,
        message: str = "El usuario no cuenta con un perfil de empleado activo en esta empresa.",
    ) -> None:
        super().__init__(status_code=403, message=message)


class NoAuthorizedBranchesError(OfflineServiceError):
    def __init__(
        self,
        message: str = "El usuario no tiene sucursales activas autorizadas para operar offline.",
    ) -> None:
        super().__init__(status_code=403, message=message)


class BranchNotAuthorizedError(OfflineServiceError):
    def __init__(self, branch_id: int) -> None:
        super().__init__(
            status_code=403,
            message=f"La sucursal con ID {branch_id} no está autorizada para este usuario o se encuentra inactiva.",
        )


class BranchNotFoundError(OfflineServiceError):
    def __init__(self, branch_id: int) -> None:
        super().__init__(
            status_code=404,
            message=f"La sucursal con ID {branch_id} no fue encontrada en la empresa especificada.",
        )


class OfflineService:
    """Orquesta la preparación, versionado, vigencia y estructura del catálogo offline."""

    def __init__(
        self,
        db: Session,
        repository: OfflineRepository | None = None,
        saas_service: SaasPlanLimitsService | None = None,
    ) -> None:
        self.db = db
        self.repository = repository or OfflineRepository(db)
        self.saas_service = saas_service or SaasPlanLimitsService(db)

    @staticmethod
    def _short_description(description: str | None) -> str | None:
        """Genera la descripción corta compatible con CatalogService._short_description."""
        if description is None or len(description) <= SHORT_DESCRIPTION_LENGTH:
            return description
        shortened = description[: SHORT_DESCRIPTION_LENGTH - 3].rstrip()
        return f"{shortened}..."

    def _validate_role_and_permissions(self, user: AuthenticatedUserData) -> str:
        """Verifica que el usuario tenga un rol autorizado para el modo offline."""
        role = user.rol.upper()
        if role not in ALLOWED_OFFLINE_ROLES:
            raise UnauthorizedOfflineRoleError(user.rol)
        return role

    def _validate_saas_offline_feature(
        self,
        company_id: int,
        *,
        now: datetime | None = None,
    ) -> Any:
        """Reutiliza CU07 para exigir suscripción activa y funcionalidad OFFLINE habilitada."""
        try:
            return self.saas_service.validate_feature_enabled(
                company_id, "OFFLINE", now=now
            )
        except (NoActiveSubscriptionError, FeatureNotEnabledError) as err:
            raise OfflineServiceError(status_code=403, message=str(err)) from err

    def _resolve_company(
        self,
        user: AuthenticatedUserData,
        requested_company_id: int | None,
    ) -> Any:
        """Resuelve y valida la empresa multitenant asegurando aislamiento estricto."""
        role = user.rol.upper()
        if role == "SUPERADMIN":
            target_company_id = requested_company_id or user.id_empresa
            if not target_company_id:
                raise OfflineServiceError(
                    status_code=400,
                    message="Debe especificar el parámetro 'empresa_id' para la operación como SUPERADMIN.",
                )
        else:
            user_company_id = user.id_empresa
            if (
                not user_company_id
                and role in CLIENT_OFFLINE_ROLES
                and hasattr(self.repository, "get_client_for_user")
            ):
                client_profile = self.repository.get_client_for_user(user.id_usuario)
                candidate_company_id = getattr(client_profile, "empresa_id", None)
                if isinstance(candidate_company_id, int):
                    user_company_id = candidate_company_id

            if not user_company_id:
                raise OfflineServiceError(
                    status_code=403,
                    message="El usuario no tiene una empresa asociada en su token.",
                )
            if (
                requested_company_id is not None
                and requested_company_id != user_company_id
            ):
                raise OfflineServiceError(
                    status_code=403,
                    message="Acceso denegado: no puede solicitar datos de otra empresa.",
                )
            target_company_id = user_company_id

        company = self.repository.get_company_by_id(target_company_id)
        if company is None:
            raise CompanyNotFoundError(f"Empresa con ID {target_company_id} no encontrada.")
        if company.estado != "ACTIVA":
            raise CompanyNotActiveError(
                f"La empresa '{company.nombre}' no se encuentra activa (estado: {company.estado})."
            )
        return company

    def _resolve_authorized_branches(
        self,
        user: AuthenticatedUserData,
        company_id: int,
        requested_branch_id: int | None = None,
    ) -> list[tuple[Any, str | None]]:
        """Determina las sucursales autorizadas para el usuario según su rol y asignaciones."""
        role = user.rol.upper()

        if role in ADMINISTRATIVE_ROLES or role in CLIENT_OFFLINE_ROLES:
            all_branches = self.repository.get_all_active_branches(company_id)
            if requested_branch_id is not None:
                match = [
                    (b, city) for (b, city) in all_branches if b.id_sucursal == requested_branch_id
                ]
                if not match:
                    found = self.repository.get_branch_by_id(requested_branch_id, company_id)
                    if found is None:
                        raise BranchNotFoundError(requested_branch_id)
                    if not found[0].estado:
                        raise BranchNotAuthorizedError(requested_branch_id)
                    match = [found]
                return match
            return all_branches

        # Roles operativos: CAJERO / ENCARGADO_SUCURSAL
        employee = self.repository.get_employee_for_user(user.id_usuario, company_id)
        if employee is None:
            raise EmployeeProfileNotFoundError()

        authorized = self.repository.get_authorized_branches_for_employee(
            employee.id_empleado, company_id
        )
        if not authorized:
            raise NoAuthorizedBranchesError()

        if requested_branch_id is not None:
            match = [
                (b, city) for (b, city) in authorized if b.id_sucursal == requested_branch_id
            ]
            if not match:
                raise BranchNotAuthorizedError(requested_branch_id)
            return match

        return authorized

    def _resolve_authorized_clients(
        self,
        user: AuthenticatedUserData,
        company_id: int,
    ) -> list[tuple[Any, Any]]:
        """Obtiene los registros de clientes autorizados según el rol del usuario.

        Para CLIENTE: retorna exclusivamente su propio registro de cliente, nunca datos de terceros.
        Para roles administrativos y empleados: retorna los clientes mínimos de la empresa.
        """
        client_rows = self.repository.get_minimal_clients(company_id)
        if user.rol.upper() in CLIENT_OFFLINE_ROLES:
            return [
                (cli, u)
                for (cli, u) in client_rows
                if getattr(u, "id_usuario", None) == user.id_usuario
            ]
        return client_rows

    def _compute_package_metadata(
        self,
        company: Any,
        user: AuthenticatedUserData,
        selected_branch_ids: list[int],
        subscription: Any,
        product_count: int,
        variant_count: int,
        stock_count: int,
        client_count: int,
        category_count: int,
        max_updated: datetime | None,
        now: datetime | None = None,
    ) -> OfflinePackageMetadata:
        """Calcula metadatos, identificador de versión e intervalo de vigencia de forma determinista."""
        gen_time = now or datetime.now(timezone.utc).replace(tzinfo=None)
        ttl_time = gen_time + timedelta(seconds=DEFAULT_OFFLINE_TTL_SECONDS)

        # Si la suscripción vence antes del TTL estándar de 24h, la vigencia se recorta
        sub_end = getattr(subscription, "fecha_fin_periodo", None)
        if sub_end is not None and sub_end < ttl_time:
            valido_hasta = sub_end
        else:
            valido_hasta = ttl_time

        vigencia_segundos = max(0, int((valido_hasta - gen_time).total_seconds()))

        # Generar hash determinista de versión basado EXCLUSIVAMENTE en datos y contexto autorizado,
        # sin depender del reloj del servidor cuando los datos no han cambiado.
        branch_key = "_".join(map(str, sorted(selected_branch_ids)))
        ts_str = max_updated.isoformat() if max_updated else "STATIC_SNAPSHOT"
        role_scope = f"-CL{user.id_usuario}" if user.rol.upper() in CLIENT_OFFLINE_ROLES else ""
        raw_seed = (
            f"E{company.id_empresa}-B{branch_key}-P{product_count}-V{variant_count}-"
            f"S{stock_count}-C{client_count}-CAT{category_count}-{ts_str}{role_scope}"
        )
        version_hash = hashlib.sha256(raw_seed.encode("utf-8")).hexdigest()[:12]
        version = f"FS-OFFLINE-E{company.id_empresa}-{version_hash}"

        return OfflinePackageMetadata(
            version=version,
            fecha_generacion=gen_time,
            valido_hasta=valido_hasta,
            vigencia_segundos=vigencia_segundos,
            id_empresa=company.id_empresa,
            empresa_codigo=company.codigo,
            empresa_nombre=company.nombre,
            id_usuario=user.id_usuario,
            usuario_rol=user.rol,
            sucursales_autorizadas_ids=selected_branch_ids,
            suscripcion_activa=True,
            funcionalidad_offline=True,
            total_sucursales=len(selected_branch_ids),
            total_categorias=category_count,
            total_productos=product_count,
            total_variantes=variant_count,
            total_existencias=stock_count,
            total_clientes=client_count,
        )

    def check_offline_status(
        self,
        user: AuthenticatedUserData,
        *,
        requested_company_id: int | None = None,
        requested_branch_id: int | None = None,
        client_version: str | None = None,
        now: datetime | None = None,
    ) -> OfflineStatusResponse:
        """Verifica vigencia, suscripción y requerimiento de actualización sin descargar todo el paquete."""
        self._validate_role_and_permissions(user)
        company = self._resolve_company(user, requested_company_id)
        subscription = self._validate_saas_offline_feature(company.id_empresa, now=now)
        branches = self._resolve_authorized_branches(
            user, company.id_empresa, requested_branch_id
        )
        branch_ids = [b[0].id_sucursal for b in branches]
        branch_id_set = set(branch_ids)

        max_updated = self.repository.get_max_updated_at(company.id_empresa, branch_ids)
        raw_products = self.repository.get_products(company.id_empresa)
        products = [p for p in raw_products if getattr(p, "estado", True)]
        active_product_ids = {p.id_producto for p in products}

        raw_variants = self.repository.get_variants(company.id_empresa)
        variants = [
            v
            for v in raw_variants
            if getattr(v, "estado", True) and v.id_producto in active_product_ids
        ]
        active_variant_ids = {v.id_variante_producto for v in variants}

        raw_inventory = self.repository.get_inventory(company.id_empresa, branch_ids)
        inventory = [
            inv
            for inv in raw_inventory
            if inv.id_variante_producto in active_variant_ids
            and inv.id_sucursal in branch_id_set
        ]
        clients = self._resolve_authorized_clients(user, company.id_empresa)
        raw_categories = self.repository.get_categories(company.id_empresa)
        categories = [c for c in raw_categories if getattr(c, "estado", True)]

        metadata = self._compute_package_metadata(
            company=company,
            user=user,
            selected_branch_ids=branch_ids,
            subscription=subscription,
            product_count=len(products),
            variant_count=len(variants),
            stock_count=len(inventory),
            client_count=len(clients),
            category_count=len(categories),
            max_updated=max_updated,
            now=now,
        )

        current_time = now or datetime.now(timezone.utc).replace(tzinfo=None)
        is_fresh = current_time < metadata.valido_hasta
        clean_client_version = client_version.strip('"').strip() if client_version else None
        is_same_version = bool(clean_client_version and clean_client_version == metadata.version)

        vigente = is_fresh and is_same_version
        requiere_actualizacion = not vigente

        if vigente:
            message = "Datos actualizados. El paquete offline local coincide con el servidor y no requiere descarga."
        elif not is_fresh and clean_client_version:
            message = "Actualización disponible. El paquete offline local ha caducado."
        elif clean_client_version and not is_same_version:
            message = "Actualización disponible. Existen cambios en catálogo o existencias en el servidor."
        else:
            message = "Actualización disponible. No se detectó versión previa en el cliente."

        return OfflineStatusResponse(
            success=True,
            id_empresa=company.id_empresa,
            version_actual=metadata.version,
            version_solicitada=clean_client_version,
            vigente=vigente,
            requiere_actualizacion=requiere_actualizacion,
            fecha_generacion=metadata.fecha_generacion,
            valido_hasta=metadata.valido_hasta,
            sucursales_autorizadas_ids=branch_ids,
            suscripcion_activa=True,
            funcionalidad_offline=True,
            message=message,
        )

    def prepare_offline_package(
        self,
        user: AuthenticatedUserData,
        *,
        requested_company_id: int | None = None,
        requested_branch_id: int | None = None,
        now: datetime | None = None,
    ) -> OfflinePackageResponse:
        """Prepara el paquete completo de catálogo y disponibilidad offline respetando multitenancy y privacidad."""
        self._validate_role_and_permissions(user)
        company = self._resolve_company(user, requested_company_id)
        subscription = self._validate_saas_offline_feature(company.id_empresa, now=now)

        branches_with_cities = self._resolve_authorized_branches(
            user, company.id_empresa, requested_branch_id
        )
        branch_ids = [b[0].id_sucursal for b in branches_with_cities]
        branch_map: dict[int, tuple[Any, str | None]] = {
            b.id_sucursal: (b, city_name) for (b, city_name) in branches_with_cities
        }

        # 1. Sucursales autorizadas
        branch_list: list[OfflineBranchData] = [
            OfflineBranchData(
                id_sucursal=b.id_sucursal,
                id_ciudad=b.id_ciudad,
                ciudad=city_name,
                nombre=b.nombre,
                direccion=b.direccion,
                telefono=b.telefono,
                hora_apertura=b.hora_apertura,
                hora_cierre=b.hora_cierre,
                estado=b.estado,
            )
            for (b, city_name) in branches_with_cities
        ]

        # 2. Categorías activas
        raw_categories = self.repository.get_categories(company.id_empresa)
        categories = [c for c in raw_categories if getattr(c, "estado", True)]
        category_map = {c.id_categoria: c.nombre for c in categories}
        category_list: list[OfflineCategoryData] = [
            OfflineCategoryData(
                id_categoria=c.id_categoria,
                nombre=c.nombre,
                descripcion=c.descripcion,
                estado=c.estado,
            )
            for c in categories
        ]

        # 2b. Temporadas y colecciones activas (opcionales si están configuradas)
        season_map: dict[int, str] = {}
        if hasattr(self.repository, "get_seasons"):
            raw_seasons = self.repository.get_seasons(company.id_empresa)
            if isinstance(raw_seasons, (list, tuple)):
                season_map = {
                    s.id_temporada: s.nombre
                    for s in raw_seasons
                    if getattr(s, "estado", True)
                }

        collections_by_product: dict[int, list[OfflineCollectionData]] = defaultdict(list)
        if hasattr(self.repository, "get_product_collections"):
            raw_collections = self.repository.get_product_collections(company.id_empresa)
            if isinstance(raw_collections, (list, tuple)):
                for prod_id, col in raw_collections:
                    if getattr(col, "estado", True):
                        collections_by_product[prod_id].append(
                            OfflineCollectionData(
                                id_coleccion=col.id_coleccion,
                                nombre=col.nombre,
                            )
                        )

        # 3. Tallas activas
        raw_sizes = self.repository.get_sizes(company.id_empresa)
        sizes = [s for s in raw_sizes if getattr(s, "estado", True)]
        size_map = {s.id_talla: s.nombre for s in sizes}
        size_list: list[OfflineSizeData] = [
            OfflineSizeData(
                id_talla=s.id_talla,
                nombre=s.nombre,
                descripcion=s.descripcion,
                estado=s.estado,
            )
            for s in sizes
        ]

        # 4. Colores activos
        raw_colors = self.repository.get_colors(company.id_empresa)
        colors = [c for c in raw_colors if getattr(c, "estado", True)]
        color_map = {c.id_color: c.nombre for c in colors}
        color_hex_map = {c.id_color: c.codigo_hex for c in colors}
        color_list: list[OfflineColorData] = [
            OfflineColorData(
                id_color=c.id_color,
                nombre=c.nombre,
                codigo_hex=c.codigo_hex,
                estado=c.estado,
            )
            for c in colors
        ]

        # 5. Productos activos
        raw_products = self.repository.get_products(company.id_empresa)
        products = [p for p in raw_products if getattr(p, "estado", True)]
        active_product_ids = {p.id_producto for p in products}
        product_price_map = {p.id_producto: p.precio for p in products}

        # 6. Variantes activas pertenecientes a productos activos
        raw_variants = self.repository.get_variants(company.id_empresa)
        variants = [
            v
            for v in raw_variants
            if getattr(v, "estado", True) and v.id_producto in active_product_ids
        ]
        variant_by_id = {v.id_variante_producto: v for v in variants}
        variant_to_product = {v.id_variante_producto: v.id_producto for v in variants}

        # 7. Existencias conocidas de sucursales autorizadas (sin alterar inventario)
        raw_inventory = self.repository.get_inventory(company.id_empresa, branch_ids)
        stock_by_variant: dict[int, int] = defaultdict(int)
        stock_by_product: dict[int, int] = defaultdict(int)
        stock_list: list[OfflineStockData] = []

        for inv in raw_inventory:
            var_obj = variant_by_id.get(inv.id_variante_producto)
            branch_tuple = branch_map.get(inv.id_sucursal)
            if var_obj is None or branch_tuple is None:
                continue

            branch_obj, city_name = branch_tuple
            available_qty = max(0, int(inv.stock_actual) - int(inv.stock_reservado))
            stock_by_variant[var_obj.id_variante_producto] += available_qty
            stock_by_product[var_obj.id_producto] += available_qty

            stock_list.append(
                OfflineStockData(
                    id_inventario_sucursal=inv.id_inventario_sucursal,
                    id_sucursal=inv.id_sucursal,
                    id_variante_producto=inv.id_variante_producto,
                    id_producto=var_obj.id_producto,
                    sku=var_obj.sku,
                    id_talla=var_obj.id_talla,
                    talla=size_map.get(var_obj.id_talla),
                    id_color=var_obj.id_color,
                    color=color_map.get(var_obj.id_color),
                    color_hex=color_hex_map.get(var_obj.id_color),
                    nombre_sucursal=branch_obj.nombre,
                    id_ciudad=branch_obj.id_ciudad,
                    nombre_ciudad=city_name,
                    stock_actual=inv.stock_actual,
                    stock_reservado=inv.stock_reservado,
                    stock_disponible=available_qty,
                    stock_minimo=inv.stock_minimo,
                    estado_disponibilidad="DISPONIBLE" if available_qty > 0 else "AGOTADO",
                    updated_at=inv.updated_at,
                )
            )

        # Construir lista final de variantes y facetas de talla/color por producto
        variant_list: list[OfflineVariantData] = []
        product_sizes: dict[int, dict[int, OfflineProductSizeFacet]] = defaultdict(dict)
        product_colors: dict[int, dict[int, OfflineProductColorFacet]] = defaultdict(dict)

        for v in variants:
            v_stock = stock_by_variant.get(v.id_variante_producto, 0)
            talla_nombre = size_map.get(v.id_talla)
            color_nombre = color_map.get(v.id_color)
            color_hex = color_hex_map.get(v.id_color)

            if talla_nombre:
                product_sizes[v.id_producto].setdefault(
                    v.id_talla,
                    OfflineProductSizeFacet(id_talla=v.id_talla, nombre=talla_nombre),
                )
            if color_nombre:
                product_colors[v.id_producto].setdefault(
                    v.id_color,
                    OfflineProductColorFacet(
                        id_color=v.id_color,
                        nombre=color_nombre,
                        codigo_hex=color_hex,
                    ),
                )

            variant_list.append(
                OfflineVariantData(
                    id_variante_producto=v.id_variante_producto,
                    id_producto=v.id_producto,
                    id_talla=v.id_talla,
                    talla=talla_nombre,
                    id_color=v.id_color,
                    color=color_nombre,
                    color_hex=color_hex,
                    sku=v.sku,
                    precio=product_price_map.get(v.id_producto),
                    stock_total_disponible=v_stock,
                    disponible_red=v_stock > 0,
                    estado=v.estado,
                )
            )

        # Referencias de imágenes de productos activos
        images = []
        if hasattr(self.repository, "get_product_images"):
            raw_images = self.repository.get_product_images(company.id_empresa)
            if isinstance(raw_images, (list, tuple)):
                images = [
                    img
                    for img in raw_images
                    if getattr(img, "id_producto", None) in active_product_ids
                ]

        images_by_product: dict[int, list[str]] = defaultdict(list)
        gallery_by_product: dict[int, list[OfflineProductImageData]] = defaultdict(list)
        principal_image_by_product: dict[int, str] = {}
        for idx, img in enumerate(images, start=1):
            images_by_product[img.id_producto].append(img.url_imagen)
            is_main = bool(getattr(img, "es_principal", False))
            if is_main and img.id_producto not in principal_image_by_product:
                principal_image_by_product[img.id_producto] = img.url_imagen
            gallery_by_product[img.id_producto].append(
                OfflineProductImageData(
                    id_imagen_producto=getattr(img, "id_imagen_producto", idx),
                    url_imagen=img.url_imagen,
                    es_principal=is_main,
                )
            )

        product_list: list[OfflineProductData] = []
        for p in products:
            p_images = images_by_product.get(p.id_producto, [])
            p_principal = principal_image_by_product.get(p.id_producto) or (
                p_images[0] if p_images else None
            )
            p_stock = stock_by_product.get(p.id_producto, 0)
            p_temporada_id = getattr(p, "id_temporada", None)
            p_temporada_nombre = (
                season_map.get(p_temporada_id) if p_temporada_id is not None else None
            )

            product_list.append(
                OfflineProductData(
                    id_producto=p.id_producto,
                    id_categoria=p.id_categoria,
                    categoria=category_map.get(p.id_categoria),
                    id_temporada=p_temporada_id,
                    temporada=p_temporada_nombre,
                    nombre=p.nombre,
                    seccion=p.seccion,
                    descripcion=p.descripcion,
                    descripcion_corta=self._short_description(getattr(p, "descripcion", None)),
                    precio=p.precio,
                    precio_base=p.precio,
                    precio_final=p.precio,
                    tiene_promocion=False,
                    imagen_principal=p_principal,
                    imagenes=p_images,
                    galeria=gallery_by_product.get(p.id_producto, []),
                    tallas_disponibles=list(product_sizes.get(p.id_producto, {}).values()),
                    colores_disponibles=list(product_colors.get(p.id_producto, {}).values()),
                    colecciones=collections_by_product.get(p.id_producto, []),
                    stock_total_disponible=p_stock,
                    disponible_red=p_stock > 0,
                    created_at=getattr(p, "created_at", None),
                    updated_at=getattr(p, "updated_at", None),
                    estado=p.estado,
                )
            )

        # 8. Clientes mínimos autorizados (sanitizados, sin contraseñas ni datos de terceros para CLIENTE)
        client_rows = self._resolve_authorized_clients(user, company.id_empresa)
        client_list: list[OfflineClientData] = [
            OfflineClientData(
                id_cliente=cli.id_cliente,
                id_usuario=u.id_usuario,
                nombre=u.nombre,
                apellido=u.apellido,
                correo=u.correo,
                telefono=u.telefono,
            )
            for (cli, u) in client_rows
        ]

        max_updated = self.repository.get_max_updated_at(company.id_empresa, branch_ids)
        metadata = self._compute_package_metadata(
            company=company,
            user=user,
            selected_branch_ids=branch_ids,
            subscription=subscription,
            product_count=len(product_list),
            variant_count=len(variant_list),
            stock_count=len(stock_list),
            client_count=len(client_list),
            category_count=len(category_list),
            max_updated=max_updated,
            now=now,
        )

        return OfflinePackageResponse(
            success=True,
            message="Paquete offline preparado exitosamente",
            metadata=metadata,
            sucursales=branch_list,
            categorias=category_list,
            tallas=size_list,
            colores=color_list,
            productos=product_list,
            variantes=variant_list,
            existencias=stock_list,
            clientes=client_list,
        )
