"""Pruebas unitarias con mocks para PK08 - CU08: Preparar información para operación offline en FashionStore (Web Angular PWA).

Pruebas estrictamente locales sin conexión a Supabase ni mutaciones en base de datos.
"""

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock

from app.PK07.CU07_ConsultarPlanLimites.service import (
    FeatureNotEnabledError,
    NoActiveSubscriptionError,
)
from app.PK08.CU08_PrepararInformacionOffline.service import (
    BranchNotAuthorizedError,
    OfflineService,
    OfflineServiceError,
    UnauthorizedOfflineRoleError,
)
from app.schemas.auth import AuthenticatedUserData

NOW = datetime(2026, 10, 31, 19, 0, 0)


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
    nombre: str = "Camisa Lino Premium",
    precio: Decimal = Decimal("249.50"),
    empresa_id: int = 1,
    id_categoria: int = 1,
    estado: bool = True,
):
    return SimpleNamespace(
        id_producto=id_producto,
        id_categoria=id_categoria,
        id_temporada=None,
        nombre=nombre,
        seccion="HOMBRE",
        descripcion="Camisa 100% lino",
        precio=precio,
        estado=estado,
        empresa_id=empresa_id,
        updated_at=NOW,
    )


def dummy_variant(
    id_variante_producto: int = 500,
    id_producto: int = 100,
    id_talla: int = 2,
    id_color: int = 3,
    sku: str = "CAM-LINO-BLA-M",
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
    )


def dummy_stock(
    id_inventario_sucursal: int = 1,
    id_sucursal: int = 10,
    id_variante_producto: int = 500,
    stock_actual: int = 25,
    stock_reservado: int = 5,
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


def dummy_client_and_user(
    id_cliente: int = 1,
    id_usuario: int = 42,
    nombre: str = "Carlos",
    apellido: str = "Mendoza",
    correo: str = "carlos.mendoza@email.com",
    telefono: str = "70011223",
    empresa_id: int = 1,
):
    client = SimpleNamespace(
        id_cliente=id_cliente,
        id_usuario=id_usuario,
        fecha_nacimiento=None,
        genero="M",
        empresa_id=empresa_id,
    )
    user = SimpleNamespace(
        id_usuario=id_usuario,
        nombre=nombre,
        apellido=apellido,
        correo=correo,
        password_hash="argon2id$sensitive_hash_that_must_never_leak",
        telefono=telefono,
        estado=True,
    )
    return client, user


class TestCU08PrepareOfflineData(TestCase):
    """Suite de 8 pruebas unitarias con mocks para PK08 - CU08."""

    def setUp(self):
        self.mock_db = MagicMock()
        self.mock_repo = MagicMock()
        self.mock_saas = MagicMock()
        self.service = OfflineService(
            self.mock_db,
            repository=self.mock_repo,
            saas_service=self.mock_saas,
        )

        # Configuración base válida
        self.company = dummy_company(id_empresa=1)
        self.sub = dummy_subscription(id_empresa=1)
        self.mock_repo.get_company_by_id.return_value = self.company
        self.mock_saas.validate_feature_enabled.return_value = self.sub

    def test_1_package_structure_and_completeness(self):
        """Verifica la estructura completa del paquete offline, cálculo de stock disponible y vigencia."""
        admin_user = AuthenticatedUserData(
            id_usuario=10,
            nombre="Admin",
            apellido="Principal",
            correo="admin@modaoriente.com",
            rol="ADMINISTRADOR",
            id_empresa=1,
        )

        b1, city1 = dummy_branch(id_sucursal=10, nombre="Sucursal Central", ciudad="Santa Cruz")
        self.mock_repo.get_all_active_branches.return_value = [(b1, city1)]
        self.mock_repo.get_categories.return_value = [
            SimpleNamespace(id_categoria=1, nombre="Camisas", descripcion="Camisas casuales", estado=True)
        ]
        self.mock_repo.get_sizes.return_value = [
            SimpleNamespace(id_talla=2, nombre="M", descripcion="Talla Mediana", estado=True)
        ]
        self.mock_repo.get_colors.return_value = [
            SimpleNamespace(id_color=3, nombre="Blanco", codigo_hex="#FFFFFF", estado=True)
        ]
        self.mock_repo.get_products.return_value = [dummy_product()]
        self.mock_repo.get_variants.return_value = [dummy_variant()]
        self.mock_repo.get_inventory.return_value = [dummy_stock(stock_actual=30, stock_reservado=8)]
        self.mock_repo.get_minimal_clients.return_value = [dummy_client_and_user()]
        self.mock_repo.get_max_updated_at.return_value = NOW

        resp = self.service.prepare_offline_package(admin_user, now=NOW)

        self.assertTrue(resp.success)
        self.assertIn("FS-OFFLINE-E1-", resp.metadata.version)
        self.assertEqual(resp.metadata.id_empresa, 1)
        self.assertEqual(resp.metadata.vigencia_segundos, 86400)
        self.assertEqual(resp.metadata.valido_hasta, NOW + timedelta(seconds=86400))
        self.assertEqual(resp.metadata.total_sucursales, 1)
        self.assertEqual(resp.metadata.total_productos, 1)
        self.assertEqual(resp.metadata.total_existencias, 1)
        self.assertEqual(resp.metadata.total_clientes, 1)

        # Validar cálculo de stock disponible (30 - 8 = 22)
        stock_item = resp.existencias[0]
        self.assertEqual(stock_item.stock_actual, 30)
        self.assertEqual(stock_item.stock_reservado, 8)
        self.assertEqual(stock_item.stock_disponible, 22)

        # Validar precio de producto
        prod_item = resp.productos[0]
        self.assertEqual(prod_item.precio, Decimal("249.50"))

    def test_2_unauthorized_role_rejected(self):
        """Verifica que roles no autorizados (CLIENTE, PROVEEDOR) sean rechazados con HTTP 403."""
        client_user = AuthenticatedUserData(
            id_usuario=99,
            nombre="Cliente",
            apellido="Final",
            correo="cliente@gmail.com",
            rol="CLIENTE",
            id_empresa=1,
        )

        with self.assertRaises(UnauthorizedOfflineRoleError) as ctx:
            self.service.prepare_offline_package(client_user)

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("no cuenta con permisos", ctx.exception.message)

        with self.assertRaises(UnauthorizedOfflineRoleError):
            self.service.check_offline_status(client_user)

    def test_3_strict_multitenant_isolation(self):
        """Verifica que un usuario de la empresa 1 no pueda solicitar datos de la empresa 2."""
        cashier_user = AuthenticatedUserData(
            id_usuario=20,
            nombre="Pedro",
            apellido="Cajero",
            correo="pedro@empresa1.com",
            rol="CAJERO",
            id_empresa=1,
        )

        # Intento de cruce tenant explícito
        with self.assertRaises(OfflineServiceError) as ctx:
            self.service.prepare_offline_package(
                cashier_user,
                requested_company_id=2,
            )

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("Acceso denegado: no puede solicitar datos de otra empresa", ctx.exception.message)

        # Validar que nunca se consultó el repositorio con empresa_id != 1
        for call_args in self.mock_repo.get_products.call_args_list:
            self.assertEqual(call_args[0][0], 1)

    def test_4_cashier_branch_authorization_and_inventory_filtering(self):
        """Verifica que un cajero solo reciba existencias y sucursales donde tiene asignación activa."""
        cashier_user = AuthenticatedUserData(
            id_usuario=33,
            nombre="Ana",
            apellido="Gómez",
            correo="ana@cajeros.com",
            rol="CAJERO",
            id_empresa=1,
        )

        # Ana es empleada id=5 y solo está asignada a Sucursal 10 (no a la 20)
        self.mock_repo.get_employee_for_user.return_value = SimpleNamespace(id_empleado=5, empresa_id=1)
        b10, city10 = dummy_branch(id_sucursal=10, nombre="Sucursal 10")
        self.mock_repo.get_authorized_branches_for_employee.return_value = [(b10, city10)]
        self.mock_repo.get_categories.return_value = []
        self.mock_repo.get_sizes.return_value = []
        self.mock_repo.get_colors.return_value = []
        self.mock_repo.get_products.return_value = [dummy_product()]
        self.mock_repo.get_variants.return_value = [dummy_variant()]
        self.mock_repo.get_inventory.return_value = [dummy_stock(id_sucursal=10)]
        self.mock_repo.get_minimal_clients.return_value = []
        self.mock_repo.get_max_updated_at.return_value = NOW

        # 1. Ana descarga sin especificar sucursal: recibe solo sucursal 10
        resp = self.service.prepare_offline_package(cashier_user, now=NOW)
        self.assertEqual(resp.metadata.sucursales_autorizadas_ids, [10])
        self.mock_repo.get_inventory.assert_called_with(1, [10])

        # 2. Ana intenta descargar para la sucursal 20 (no autorizada para ella)
        with self.assertRaises(BranchNotAuthorizedError) as ctx:
            self.service.prepare_offline_package(
                cashier_user,
                requested_branch_id=20,
                now=NOW,
            )
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("ID 20 no está autorizada", ctx.exception.message)

    def test_5_saas_subscription_required_reusing_cu07(self):
        """Verifica que sin suscripción activa se bloquee la operación reutilizando CU07."""
        admin_user = AuthenticatedUserData(
            id_usuario=1,
            nombre="Admin",
            apellido="General",
            correo="admin@empresa.com",
            rol="ADMINISTRADOR",
            id_empresa=1,
        )

        self.mock_saas.validate_feature_enabled.side_effect = NoActiveSubscriptionError(
            "La empresa no cuenta con una suscripción SaaS activa vigente."
        )

        with self.assertRaises(OfflineServiceError) as ctx:
            self.service.prepare_offline_package(admin_user)

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("suscripción SaaS activa vigente", ctx.exception.message)

    def test_6_offline_feature_disabled_reusing_cu07(self):
        """Verifica que si la funcionalidad OFFLINE no está contratada se bloquee vía CU07."""
        admin_user = AuthenticatedUserData(
            id_usuario=1,
            nombre="Admin",
            apellido="General",
            correo="admin@empresa.com",
            rol="ADMINISTRADOR",
            id_empresa=1,
        )

        self.mock_saas.validate_feature_enabled.side_effect = FeatureNotEnabledError(
            "El plan SaaS contratado no incluye la funcionalidad 'OFFLINE'."
        )

        with self.assertRaises(OfflineServiceError) as ctx:
            self.service.prepare_offline_package(admin_user)

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("funcionalidad 'OFFLINE'", ctx.exception.message)

    def test_7_privacy_sanitization_excludes_passwords_and_sensitive_fields(self):
        """Verifica que los clientes offline no contengan contraseñas, hashes ni campos sensibles."""
        admin_user = AuthenticatedUserData(
            id_usuario=1,
            nombre="Admin",
            apellido="General",
            correo="admin@empresa.com",
            rol="ADMINISTRADOR",
            id_empresa=1,
        )

        b, city = dummy_branch()
        self.mock_repo.get_all_active_branches.return_value = [(b, city)]
        self.mock_repo.get_categories.return_value = []
        self.mock_repo.get_sizes.return_value = []
        self.mock_repo.get_colors.return_value = []
        self.mock_repo.get_products.return_value = []
        self.mock_repo.get_variants.return_value = []
        self.mock_repo.get_inventory.return_value = []
        self.mock_repo.get_minimal_clients.return_value = [dummy_client_and_user()]
        self.mock_repo.get_max_updated_at.return_value = NOW

        resp = self.service.prepare_offline_package(admin_user, now=NOW)

        client_dict = resp.clientes[0].model_dump()
        self.assertEqual(
            set(client_dict.keys()),
            {"id_cliente", "id_usuario", "nombre", "apellido", "correo", "telefono"},
        )
        self.assertNotIn("password", client_dict)
        self.assertNotIn("password_hash", client_dict)
        self.assertNotIn("fecha_nacimiento", client_dict)
        self.assertNotIn("genero", client_dict)

    def test_8_read_only_and_subsequent_status_check(self):
        """Verifica que no se ejecute commit ni alteración de inventario y que la consulta posterior de vigencia sea coherente."""
        admin_user = AuthenticatedUserData(
            id_usuario=1,
            nombre="Admin",
            apellido="General",
            correo="admin@empresa.com",
            rol="ADMINISTRADOR",
            id_empresa=1,
        )

        b, city = dummy_branch()
        self.mock_repo.get_all_active_branches.return_value = [(b, city)]
        self.mock_repo.get_categories.return_value = []
        self.mock_repo.get_sizes.return_value = []
        self.mock_repo.get_colors.return_value = []
        self.mock_repo.get_products.return_value = [dummy_product()]
        self.mock_repo.get_variants.return_value = [dummy_variant()]
        stock_orig = dummy_stock(stock_actual=50, stock_reservado=10)
        self.mock_repo.get_inventory.return_value = [stock_orig]
        self.mock_repo.get_minimal_clients.return_value = []
        self.mock_repo.get_max_updated_at.return_value = NOW

        # 1. Preparación de paquete
        resp = self.service.prepare_offline_package(admin_user, now=NOW)

        # Garantía estricta de sólo lectura
        self.mock_db.commit.assert_not_called()
        self.mock_db.add.assert_not_called()
        self.mock_db.delete.assert_not_called()
        self.assertEqual(stock_orig.stock_actual, 50)
        self.assertEqual(stock_orig.stock_reservado, 10)

        # 2. Descarga / consulta posterior con la misma versión dentro de la vigencia (determinismo temporal)
        status_same = self.service.check_offline_status(
            admin_user,
            client_version=resp.metadata.version,
            now=NOW + timedelta(hours=2),
        )
        self.assertTrue(status_same.vigente)
        self.assertFalse(status_same.requiere_actualizacion)
        self.assertEqual(status_same.version_actual, resp.metadata.version)
        self.assertIn("Datos actualizados", status_same.message)

        # 2b. Consulta con ETag entrecomillado '"versión"'
        status_quoted = self.service.check_offline_status(
            admin_user,
            client_version=f'"{resp.metadata.version}"',
            now=NOW + timedelta(hours=3),
        )
        self.assertTrue(status_quoted.vigente)
        self.assertEqual(status_quoted.version_solicitada, resp.metadata.version)

        # 3. Consulta con versión antigua o caducada
        status_old = self.service.check_offline_status(
            admin_user,
            client_version="FS-OFFLINE-E1-versionantigua",
            now=NOW + timedelta(hours=2),
        )
        self.assertFalse(status_old.vigente)
        self.assertTrue(status_old.requiere_actualizacion)
        self.assertIn("Actualización disponible", status_old.message)

