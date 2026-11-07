"""Repositorio de persistencia para PK08 - CU08 y CU09: Preparar y consultar catálogo y disponibilidad offline.

Consultas de sólo lectura estrictamente filtradas por tenant (empresa_id) y sucursales autorizadas.
Nunca modifica inventario, no inserta ventas ni ejecuta transacciones de escritura.
"""

from datetime import datetime
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.models.branch_inventory import BranchInventory
from app.models.category import Category
from app.models.city import City
from app.models.client import Client
from app.models.collection import Collection
from app.models.color import Color
from app.models.company import Company
from app.models.employee import Employee
from app.models.employee_branch import EmployeeBranch
from app.models.product import Product
from app.models.product_collection import ProductCollection
from app.models.product_image import ProductImage
from app.models.product_variant import ProductVariant
from app.models.season import Season
from app.models.size import Size
from app.models.user import User


class OfflineRepository:
    """Acceso a datos de catálogo, existencias y recursos para operación offline en FashionStore."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_company_by_id(self, company_id: int) -> Company | None:
        """Obtiene la entidad de empresa por id."""
        return self.db.get(Company, company_id)

    def get_employee_for_user(self, user_id: int, company_id: int) -> Employee | None:
        """Obtiene el empleado asociado a un usuario dentro de la empresa especificada."""
        statement = select(Employee).where(
            Employee.id_usuario == user_id,
            Employee.empresa_id == company_id,
        )
        return self.db.scalar(statement)

    def get_client_for_user(
        self, user_id: int, company_id: int | None = None
    ) -> Client | None:
        """Obtiene el perfil de cliente asociado al usuario autenticado."""
        statement = select(Client).where(Client.id_usuario == user_id)
        if company_id is not None:
            statement = statement.where(Client.empresa_id == company_id)
        return self.db.scalar(statement)

    def get_authorized_branches_for_employee(
        self, employee_id: int, company_id: int
    ) -> list[tuple[Branch, str | None]]:
        """Retorna las sucursales activas en las que el empleado tiene asignación activa."""
        statement = (
            select(Branch, City.nombre.label("ciudad"))
            .select_from(EmployeeBranch)
            .join(Branch, Branch.id_sucursal == EmployeeBranch.id_sucursal)
            .outerjoin(City, City.id_ciudad == Branch.id_ciudad)
            .where(
                EmployeeBranch.id_empleado == employee_id,
                EmployeeBranch.estado.is_(True),
                Branch.estado.is_(True),
                Branch.empresa_id == company_id,
            )
            .order_by(Branch.id_sucursal)
        )
        return [(row[0], row[1]) for row in self.db.execute(statement).all()]

    def get_all_active_branches(
        self, company_id: int
    ) -> list[tuple[Branch, str | None]]:
        """Retorna todas las sucursales activas de la empresa (para administradores y clientes)."""
        statement = (
            select(Branch, City.nombre.label("ciudad"))
            .outerjoin(City, City.id_ciudad == Branch.id_ciudad)
            .where(
                Branch.empresa_id == company_id,
                Branch.estado.is_(True),
            )
            .order_by(Branch.id_sucursal)
        )
        return [(row[0], row[1]) for row in self.db.execute(statement).all()]

    def get_branch_by_id(
        self, branch_id: int, company_id: int
    ) -> tuple[Branch, str | None] | None:
        """Busca una sucursal específica dentro del tenant."""
        statement = (
            select(Branch, City.nombre.label("ciudad"))
            .outerjoin(City, City.id_ciudad == Branch.id_ciudad)
            .where(
                Branch.id_sucursal == branch_id,
                Branch.empresa_id == company_id,
            )
        )
        row = self.db.execute(statement).first()
        if row is None:
            return None
        return (row[0], row[1])

    def get_categories(self, company_id: int) -> list[Category]:
        """Obtiene las categorías activas de la empresa."""
        statement = (
            select(Category)
            .where(Category.empresa_id == company_id, Category.estado.is_(True))
            .order_by(Category.id_categoria)
        )
        return list(self.db.scalars(statement).all())

    def get_seasons(self, company_id: int) -> list[Season]:
        """Obtiene las temporadas activas de la empresa."""
        statement = (
            select(Season)
            .where(Season.empresa_id == company_id, Season.estado.is_(True))
            .order_by(Season.id_temporada)
        )
        return list(self.db.scalars(statement).all())

    def get_product_collections(
        self, company_id: int
    ) -> list[tuple[int, Collection]]:
        """Obtiene las colecciones activas asociadas a productos de la empresa."""
        statement = (
            select(ProductCollection.id_producto, Collection)
            .join(
                Collection,
                Collection.id_coleccion == ProductCollection.id_coleccion,
            )
            .where(
                ProductCollection.empresa_id == company_id,
                Collection.empresa_id == company_id,
                Collection.estado.is_(True),
            )
            .order_by(ProductCollection.id_producto, Collection.nombre, Collection.id_coleccion)
        )
        return [(row[0], row[1]) for row in self.db.execute(statement).all()]

    def get_sizes(self, company_id: int) -> list[Size]:
        """Obtiene las tallas activas de la empresa."""
        statement = (
            select(Size)
            .where(Size.empresa_id == company_id, Size.estado.is_(True))
            .order_by(Size.id_talla)
        )
        return list(self.db.scalars(statement).all())

    def get_colors(self, company_id: int) -> list[Color]:
        """Obtiene los colores activos de la empresa."""
        statement = (
            select(Color)
            .where(Color.empresa_id == company_id, Color.estado.is_(True))
            .order_by(Color.id_color)
        )
        return list(self.db.scalars(statement).all())

    def get_products(self, company_id: int) -> list[Product]:
        """Obtiene los productos activos pertenecientes a categorías activas de la empresa."""
        statement = (
            select(Product)
            .join(Category, Category.id_categoria == Product.id_categoria)
            .where(
                Product.empresa_id == company_id,
                Product.estado.is_(True),
                Category.empresa_id == company_id,
                Category.estado.is_(True),
            )
            .order_by(Product.id_producto)
        )
        return list(self.db.scalars(statement).all())

    def get_product_images(self, company_id: int) -> list[ProductImage]:
        """Obtiene las referencias de imágenes de productos activos de la empresa."""
        statement = (
            select(ProductImage)
            .join(Product, Product.id_producto == ProductImage.id_producto)
            .where(
                ProductImage.empresa_id == company_id,
                Product.empresa_id == company_id,
                Product.estado.is_(True),
            )
            .order_by(
                ProductImage.id_producto,
                ProductImage.es_principal.desc(),
                ProductImage.id_imagen_producto,
            )
        )
        return list(self.db.scalars(statement).all())

    def get_variants(self, company_id: int) -> list[ProductVariant]:
        """Obtiene las variantes activas de productos activos con talla y color activos."""
        statement = (
            select(ProductVariant)
            .join(Product, Product.id_producto == ProductVariant.id_producto)
            .join(Size, Size.id_talla == ProductVariant.id_talla)
            .join(Color, Color.id_color == ProductVariant.id_color)
            .where(
                ProductVariant.empresa_id == company_id,
                ProductVariant.estado.is_(True),
                Product.empresa_id == company_id,
                Product.estado.is_(True),
                Size.empresa_id == company_id,
                Size.estado.is_(True),
                Color.empresa_id == company_id,
                Color.estado.is_(True),
            )
            .order_by(ProductVariant.id_variante_producto)
        )
        return list(self.db.scalars(statement).all())

    def get_inventory(
        self, company_id: int, branch_ids: list[int]
    ) -> list[BranchInventory]:
        """Obtiene existencias físicas únicamente para variantes y sucursales activas autorizadas."""
        if not branch_ids:
            return []
        statement = (
            select(BranchInventory)
            .join(
                ProductVariant,
                ProductVariant.id_variante_producto
                == BranchInventory.id_variante_producto,
            )
            .join(Product, Product.id_producto == ProductVariant.id_producto)
            .join(Branch, Branch.id_sucursal == BranchInventory.id_sucursal)
            .where(
                BranchInventory.empresa_id == company_id,
                BranchInventory.id_sucursal.in_(branch_ids),
                ProductVariant.empresa_id == company_id,
                ProductVariant.estado.is_(True),
                Product.empresa_id == company_id,
                Product.estado.is_(True),
                Branch.empresa_id == company_id,
                Branch.estado.is_(True),
            )
            .order_by(BranchInventory.id_inventario_sucursal)
        )
        return list(self.db.scalars(statement).all())

    def get_minimal_clients(
        self, company_id: int
    ) -> list[tuple[Client, User]]:
        """Obtiene clientes de la empresa con sus datos básicos minimizados (sin credenciales ni contraseñas)."""
        statement = (
            select(Client, User)
            .join(User, User.id_usuario == Client.id_usuario)
            .where(
                Client.empresa_id == company_id,
                User.estado.is_(True),
            )
            .order_by(Client.id_cliente)
        )
        return [(row[0], row[1]) for row in self.db.execute(statement).all()]

    def get_max_updated_at(
        self, company_id: int, branch_ids: list[int]
    ) -> datetime | None:
        """Obtiene la fecha máxima de modificación para generar el hash de versión del paquete."""
        max_p = self.db.scalar(
            select(func.max(Product.updated_at)).where(
                Product.empresa_id == company_id,
                Product.estado.is_(True),
            )
        )
        max_pv = self.db.scalar(
            select(func.max(ProductVariant.updated_at)).where(
                ProductVariant.empresa_id == company_id,
                ProductVariant.estado.is_(True),
            )
        )
        max_inv = None
        if branch_ids:
            max_inv = self.db.scalar(
                select(func.max(BranchInventory.updated_at)).where(
                    BranchInventory.empresa_id == company_id,
                    BranchInventory.id_sucursal.in_(branch_ids),
                )
            )
        max_b = None
        if branch_ids:
            max_b = self.db.scalar(
                select(func.max(Branch.updated_at)).where(
                    Branch.empresa_id == company_id,
                    Branch.id_sucursal.in_(branch_ids),
                    Branch.estado.is_(True),
                )
            )
        timestamps = [t for t in (max_p, max_pv, max_inv, max_b) if t is not None]
        return max(timestamps) if timestamps else None
