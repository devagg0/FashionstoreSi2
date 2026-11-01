"""Pruebas unitarias con mocks para PK08 - CU09: Consultar catálogo y disponibilidad offline de FashionStore (Web Angular PWA).

Pruebas estrictamente locales sin conexión a Supabase ni mutaciones en base de datos.
Verifica estructura del catálogo, relaciones producto-variante-existencias, variantes con precios y tallas/colores,
imágenes, stock disponible por sucursal autorizada, permisos y aislamiento multitenant.
"""

from datetime import datetime, time, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock

from app.PK07.CU07_ConsultarPlanLimites.service import (
    FeatureNotEnabledError,
    NoActiveSubscriptionError,
)
from app.PK08.CU08_PrepararInformacionOffline.service import (
    OfflineService,
    OfflineServiceError,
    UnauthorizedOfflineRoleError,
)
from app.schemas.auth import AuthenticatedUserData

NOW = datetime(2026, 10, 31, 20, 0, 0)


def dummy_company(
    id_empresa: int = 1,
    codigo: str = "moda-oriente",
    nombre: str = "Moda Oriente",
    estado: str = "ACTIVA",
):
    return SimpleNamespace(
        id_empresa=id_empresa,
        codigo=codigo,
        nombre=nombre,
        estado=estado,
    )


def dummy_subscription(
    id_suscripcion: int = 1,
    id_empresa: int = 1,
    id_plan_saas: int = 2,
    estado: str = "ACTIVA",
    fecha_fin_periodo: datetime | None = None,
):
    return SimpleNamespace(
        id_suscripcion=id_suscripcion,
        id_empresa=id_empresa,
        id_plan_saas=id_plan_saas,
        estado=estado,
        fecha_inicio=datetime(2026, 10, 1, 0, 0, 0),
        fecha_fin_periodo=fecha_fin_periodo or datetime(2027, 1, 1, 0, 0, 0),
    )


def dummy_branch(
    id_sucursal: int = 10,
    nombre: str = "Sucursal Central",
    direccion: str = "Av. San Martín 123",
    ciudad: str = "Santa Cruz",
    id_ciudad: int = 1,
    empresa_id: int = 1,
    estado: bool = True,
):
    branch = SimpleNamespace(
        id_sucursal=id_sucursal,
        nombre=nombre,
        direccion=direccion,
        id_ciudad=id_ciudad,
        telefono="33445566",
        hora_apertura=time(8, 30),
        hora_cierre=time(20, 0),
        estado=estado,
        empresa_id=empresa_id,
    )
    return branch, ciudad


def dummy_product(
    id_producto: int = 100,
    nombre: str = "Vestido Seda Estampado",
    precio: Decimal = Decimal("350.00"),
    id_categoria: int = 1,
    descripcion: str = "Vestido largo de seda 100% natural",
    empresa_id: int = 1,
    estado: bool = True,
):
    return SimpleNamespace(
        id_producto=id_producto,
        id_categoria=id_categoria,
        id_temporada=None,
        nombre=nombre,
        seccion="MUJER",
        descripcion=descripcion,
        precio=precio,
        estado=estado,
        empresa_id=empresa_id,
        updated_at=NOW,
    )


def dummy_variant(
    id_variante_producto: int = 200,
    id_producto: int = 100,
    id_talla: int = 1,
    id_color: int = 1,
    sku: str = "VES-SED-M-ROJ",
    empresa_id: int = 1,
    estado: bool = True,
):
    return SimpleNamespace(
        id_variante_producto=id_variante_producto,
        id_producto=id_producto,
        id_talla=id_talla,
        id_color=id_color,
        sku=sku,
        estado=estado,
        empresa_id=empresa_id,
        updated_at=NOW,
    )


def dummy_stock(
    id_inventario_sucursal: int = 500,
    id_sucursal: int = 10,
    id_variante_producto: int = 200,
    stock_actual: int = 15,
    stock_reservado: int = 3,
    stock_minimo: int = 2,
    empresa_id: int = 1,
):
    return SimpleNamespace(
        id_inventario_sucursal=id_inventario_sucursal,
        id_sucursal=id_sucursal,
        id_variante_producto=id_variante_producto,
        stock_actual=stock_actual,
        stock_reservado=stock_reservado,
        stock_minimo=stock_minimo,
        empresa_id=empresa_id,
        updated_at=NOW,
    )


class TestCU09QueryCatalogOffline(TestCase):
    """Suite de 7 pruebas unitarias con mocks para PK08 - CU09."""

    def setUp(self):
        self.mock_db = MagicMock()
        self.mock_repo = MagicMock()
        self.mock_saas = MagicMock()
        self.service = OfflineService(
            self.mock_db,
            repository=self.mock_repo,
            saas_service=self.mock_saas,
        )

        self.company = dummy_company(id_empresa=1)
        self.sub = dummy_subscription(id_empresa=1)
        self.mock_repo.get_company_by_id.return_value = self.company
        self.mock_saas.validate_feature_enabled.return_value = self.sub

    def test_1_catalog_products_with_category_and_images(self):
        """Verifica que los productos incluyan nombre, descripción, categoría, precio e imágenes."""
        user = AuthenticatedUserData(
            id_usuario=1,
            nombre="Encargada",
            apellido="Ventas",
            correo="ventas@modaoriente.com",
            rol="ENCARGADO_SUCURSAL",
            id_empresa=1,
        )

        b, city = dummy_branch(id_sucursal=10)
        emp = SimpleNamespace(id_empleado=5)
        self.mock_repo.get_employee_for_user.return_value = emp
        self.mock_repo.get_authorized_branches_for_employee.return_value = [(b, city)]

        self.mock_repo.get_categories.return_value = [
            SimpleNamespace(id_categoria=1, nombre="Vestidos", descripcion="Vestidos de gala", estado=True)
        ]
        self.mock_repo.get_sizes.return_value = []
        self.mock_repo.get_colors.return_value = []
        self.mock_repo.get_products.return_value = [
            dummy_product(
                id_producto=100,
                nombre="Vestido Seda",
                descripcion="Elegante vestido de seda",
                precio=Decimal("350.00"),
                id_categoria=1,
            )
        ]
        self.mock_repo.get_product_images.return_value = [
            SimpleNamespace(id_imagen_producto=1, id_producto=100, url_imagen="https://cdn.fashionstore.com/v1.jpg", es_principal=True),
            SimpleNamespace(id_imagen_producto=2, id_producto=100, url_imagen="https://cdn.fashionstore.com/v2.jpg", es_principal=False),
        ]
        self.mock_repo.get_variants.return_value = []
        self.mock_repo.get_inventory.return_value = []
        self.mock_repo.get_minimal_clients.return_value = []
        self.mock_repo.get_max_updated_at.return_value = NOW

        package = self.service.prepare_offline_package(user, now=NOW)

        self.assertEqual(len(package.productos), 1)
        p = package.productos[0]
        self.assertEqual(p.id_producto, 100)
        self.assertEqual(p.nombre, "Vestido Seda")
        self.assertEqual(p.descripcion, "Elegante vestido de seda")
        self.assertEqual(p.categoria, "Vestidos")
        self.assertEqual(p.precio, Decimal("350.00"))
        self.assertEqual(p.imagen_principal, "https://cdn.fashionstore.com/v1.jpg")
        self.assertEqual(p.imagenes, ["https://cdn.fashionstore.com/v1.jpg", "https://cdn.fashionstore.com/v2.jpg"])

    def test_2_variants_with_sku_size_color_and_corresponding_price(self):
        """Verifica que las variantes incluyan SKU, talla, color y el precio correspondiente del producto."""
        user = AuthenticatedUserData(
            id_usuario=2,
            nombre="Cajero",
            apellido="Norte",
            correo="cajero@modaoriente.com",
            rol="CAJERO",
            id_empresa=1,
        )

        b, city = dummy_branch(id_sucursal=10)
        emp = SimpleNamespace(id_empleado=6)
        self.mock_repo.get_employee_for_user.return_value = emp
        self.mock_repo.get_authorized_branches_for_employee.return_value = [(b, city)]

        self.mock_repo.get_categories.return_value = []
        self.mock_repo.get_sizes.return_value = [
            SimpleNamespace(id_talla=1, nombre="M", descripcion="Mediana", estado=True),
            SimpleNamespace(id_talla=2, nombre="L", descripcion="Grande", estado=True),
        ]
        self.mock_repo.get_colors.return_value = [
            SimpleNamespace(id_color=1, nombre="Rojo Carmesí", codigo_hex="#DC143C", estado=True),
            SimpleNamespace(id_color=2, nombre="Azul Marino", codigo_hex="#000080", estado=True),
        ]
        self.mock_repo.get_products.return_value = [
            dummy_product(id_producto=100, precio=Decimal("280.00"))
        ]
        self.mock_repo.get_product_images.return_value = []
        self.mock_repo.get_variants.return_value = [
            dummy_variant(id_variante_producto=201, id_producto=100, id_talla=1, id_color=1, sku="VES-M-ROJ"),
            dummy_variant(id_variante_producto=202, id_producto=100, id_talla=2, id_color=2, sku="VES-L-AZU"),
        ]
        self.mock_repo.get_inventory.return_value = []
        self.mock_repo.get_minimal_clients.return_value = []
        self.mock_repo.get_max_updated_at.return_value = NOW

        package = self.service.prepare_offline_package(user, now=NOW)

        self.assertEqual(len(package.variantes), 2)
        v1 = package.variantes[0]
        self.assertEqual(v1.sku, "VES-M-ROJ")
        self.assertEqual(v1.talla, "M")
        self.assertEqual(v1.color, "Rojo Carmesí")
        self.assertEqual(v1.color_hex, "#DC143C")
        self.assertEqual(v1.precio, Decimal("280.00"))

        v2 = package.variantes[1]
        self.assertEqual(v2.sku, "VES-L-AZU")
        self.assertEqual(v2.talla, "L")
        self.assertEqual(v2.color, "Azul Marino")
        self.assertEqual(v2.color_hex, "#000080")
        self.assertEqual(v2.precio, Decimal("280.00"))

    def test_3_stock_and_availability_calculation_by_authorized_branch(self):
        """Verifica el cálculo de existencias: stock actual, reservado y stock disponible."""
        user = AuthenticatedUserData(
            id_usuario=1,
            nombre="Admin",
            apellido="General",
            correo="admin@modaoriente.com",
            rol="ADMINISTRADOR",
            id_empresa=1,
        )

        b, city = dummy_branch(id_sucursal=10)
        self.mock_repo.get_all_active_branches.return_value = [(b, city)]
        self.mock_repo.get_categories.return_value = []
        self.mock_repo.get_sizes.return_value = []
        self.mock_repo.get_colors.return_value = []
        self.mock_repo.get_products.return_value = [dummy_product(id_producto=100)]
        self.mock_repo.get_product_images.return_value = []
        self.mock_repo.get_variants.return_value = [dummy_variant(id_variante_producto=201, id_producto=100)]
        self.mock_repo.get_inventory.return_value = [
            dummy_stock(
                id_inventario_sucursal=501,
                id_sucursal=10,
                id_variante_producto=201,
                stock_actual=20,
                stock_reservado=6,
                stock_minimo=3,
            )
        ]
        self.mock_repo.get_minimal_clients.return_value = []
        self.mock_repo.get_max_updated_at.return_value = NOW

        package = self.service.prepare_offline_package(user, now=NOW)

        self.assertEqual(len(package.existencias), 1)
        st = package.existencias[0]
        self.assertEqual(st.id_sucursal, 10)
        self.assertEqual(st.id_variante_producto, 201)
        self.assertEqual(st.id_producto, 100)
        self.assertEqual(st.stock_actual, 20)
        self.assertEqual(st.stock_reservado, 6)
        self.assertEqual(st.stock_disponible, 14)  # 20 - 6 = 14
        self.assertEqual(st.stock_minimo, 3)

    def test_4_relational_consistency_for_offline_filtering_and_details(self):
        """Verifica la coherencia relacional entre productos, variantes y existencias para consultas IndexedDB."""
        user = AuthenticatedUserData(
            id_usuario=1,
            nombre="Admin",
            apellido="General",
            correo="admin@modaoriente.com",
            rol="ADMINISTRADOR",
            id_empresa=1,
        )

        b1, c1 = dummy_branch(id_sucursal=10, nombre="Sucursal 1")
        b2, c2 = dummy_branch(id_sucursal=20, nombre="Sucursal 2")
        self.mock_repo.get_all_active_branches.return_value = [(b1, c1), (b2, c2)]
        self.mock_repo.get_categories.return_value = [
            SimpleNamespace(id_categoria=1, nombre="Pantalones", descripcion="", estado=True)
        ]
        self.mock_repo.get_sizes.return_value = [
            SimpleNamespace(id_talla=1, nombre="32", descripcion="", estado=True)
        ]
        self.mock_repo.get_colors.return_value = [
            SimpleNamespace(id_color=1, nombre="Negro", codigo_hex="#000", estado=True)
        ]
        self.mock_repo.get_products.return_value = [
            dummy_product(id_producto=101, nombre="Jean Slim", id_categoria=1, precio=Decimal("199.00"))
        ]
        self.mock_repo.get_product_images.return_value = []
        self.mock_repo.get_variants.return_value = [
            dummy_variant(id_variante_producto=301, id_producto=101, id_talla=1, id_color=1, sku="JEA-32-NEG")
        ]
        self.mock_repo.get_inventory.return_value = [
            dummy_stock(id_inventario_sucursal=601, id_sucursal=10, id_variante_producto=301, stock_actual=10, stock_reservado=2),
            dummy_stock(id_inventario_sucursal=602, id_sucursal=20, id_variante_producto=301, stock_actual=5, stock_reservado=0),
        ]
        self.mock_repo.get_minimal_clients.return_value = []
        self.mock_repo.get_max_updated_at.return_value = NOW

        package = self.service.prepare_offline_package(user, now=NOW)

        # Simulación de consulta offline en IndexedDB:
        # 1. Búsqueda de producto por categoría
        found_products = [p for p in package.productos if p.categoria == "Pantalones"]
        self.assertEqual(len(found_products), 1)
        prod = found_products[0]

        # 2. Búsqueda de variantes de ese producto
        found_variants = [v for v in package.variantes if v.id_producto == prod.id_producto]
        self.assertEqual(len(found_variants), 1)
        var = found_variants[0]
        self.assertEqual(var.sku, "JEA-32-NEG")

        # 3. Consulta de disponibilidad en Sucursal 10 vs 20
        stock_suc10 = next(s for s in package.existencias if s.id_variante_producto == var.id_variante_producto and s.id_sucursal == 10)
        stock_suc20 = next(s for s in package.existencias if s.id_variante_producto == var.id_variante_producto and s.id_sucursal == 20)
        self.assertEqual(stock_suc10.stock_disponible, 8)
        self.assertEqual(stock_suc20.stock_disponible, 5)

    def test_5_branch_permissions_and_inventory_isolation_cashier(self):
        """Verifica que un cajero solo reciba existencias de las sucursales donde tiene asignación activa."""
        cashier = AuthenticatedUserData(
            id_usuario=5,
            nombre="Pedro",
            apellido="Cajero",
            correo="pedro@modaoriente.com",
            rol="CAJERO",
            id_empresa=1,
        )

        b10, c10 = dummy_branch(id_sucursal=10, nombre="Sucursal Asignada")
        emp = SimpleNamespace(id_empleado=8)
        self.mock_repo.get_employee_for_user.return_value = emp
        # El cajero SOLO está asignado a la sucursal 10
        self.mock_repo.get_authorized_branches_for_employee.return_value = [(b10, c10)]

        self.mock_repo.get_categories.return_value = []
        self.mock_repo.get_sizes.return_value = []
        self.mock_repo.get_colors.return_value = []
        self.mock_repo.get_products.return_value = [dummy_product()]
        self.mock_repo.get_product_images.return_value = []
        self.mock_repo.get_variants.return_value = [dummy_variant(id_variante_producto=201)]

        # get_inventory es llamado con [10] únicamente
        self.mock_repo.get_inventory.return_value = [
            dummy_stock(id_inventario_sucursal=1, id_sucursal=10, id_variante_producto=201, stock_actual=12, stock_reservado=2)
        ]
        self.mock_repo.get_minimal_clients.return_value = []
        self.mock_repo.get_max_updated_at.return_value = NOW

        package = self.service.prepare_offline_package(cashier, now=NOW)

        self.mock_repo.get_inventory.assert_called_once_with(1, [10])
        self.assertEqual(len(package.sucursales), 1)
        self.assertEqual(package.sucursales[0].id_sucursal, 10)
        self.assertEqual(len(package.existencias), 1)
        self.assertEqual(package.existencias[0].id_sucursal, 10)

    def test_6_strict_multitenant_isolation(self):
        """Verifica que un usuario de la empresa 1 no pueda solicitar datos de la empresa 2."""
        user_emp1 = AuthenticatedUserData(
            id_usuario=1,
            nombre="Usuario",
            apellido="Empresa 1",
            correo="user@emp1.com",
            rol="ADMINISTRADOR",
            id_empresa=1,
        )

        with self.assertRaises(OfflineServiceError) as ctx:
            self.service.prepare_offline_package(user_emp1, requested_company_id=2)

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("no puede solicitar datos de otra empresa", ctx.exception.message)

    def test_7_saas_cu07_validation_and_read_only_guarantee(self):
        """Verifica que la consulta exija suscripción SaaS activa y no altere la base de datos."""
        user = AuthenticatedUserData(
            id_usuario=1,
            nombre="Admin",
            apellido="General",
            correo="admin@empresa.com",
            rol="ADMINISTRADOR",
            id_empresa=1,
        )

        # 1. Sin suscripción activa falla con 403
        self.mock_saas.validate_feature_enabled.side_effect = NoActiveSubscriptionError("Suscripción vencida")
        with self.assertRaises(OfflineServiceError) as ctx:
            self.service.prepare_offline_package(user)
        self.assertEqual(ctx.exception.status_code, 403)

        # 2. Restaurar suscripción activa y comprobar garantía de sólo lectura
        self.mock_saas.validate_feature_enabled.side_effect = None
        self.mock_saas.validate_feature_enabled.return_value = self.sub

        b, city = dummy_branch()
        self.mock_repo.get_all_active_branches.return_value = [(b, city)]
        self.mock_repo.get_categories.return_value = []
        self.mock_repo.get_sizes.return_value = []
        self.mock_repo.get_colors.return_value = []
        self.mock_repo.get_products.return_value = [dummy_product()]
        self.mock_repo.get_product_images.return_value = []
        self.mock_repo.get_variants.return_value = [dummy_variant()]
        stock_entity = dummy_stock(stock_actual=30, stock_reservado=5)
        self.mock_repo.get_inventory.return_value = [stock_entity]
        self.mock_repo.get_minimal_clients.return_value = []
        self.mock_repo.get_max_updated_at.return_value = NOW

        package = self.service.prepare_offline_package(user, now=NOW)

        # Garantía de sólo lectura estricta: ninguna mutación a la BD
        self.mock_db.commit.assert_not_called()
        self.mock_db.add.assert_not_called()
        self.mock_db.delete.assert_not_called()
        self.assertEqual(stock_entity.stock_actual, 30)
        self.assertEqual(stock_entity.stock_reservado, 5)
        self.assertEqual(package.existencias[0].stock_disponible, 25)
