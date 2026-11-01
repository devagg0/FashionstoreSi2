"""Repositorio de persistencia para PK08 - CU08: Preparar información para operación offline.

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
from app.models.color import Color
from app.models.company import Company
from app.models.employee import Employee
from app.models.employee_branch import EmployeeBranch
from app.models.product import Product
from app.models.product_image import ProductImage
from app.models.product_variant import ProductVariant
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
        """Retorna todas las sucursales activas de la empresa (para administradores)."""
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
        """Obtiene los productos activos con sus precios oficiales."""
        statement = (
            select(Product)
            .where(Product.empresa_id == company_id, Product.estado.is_(True))
            .order_by(Product.id_producto)
        )
        return list(self.db.scalars(statement).all())

    def get_product_images(self, company_id: int) -> list[ProductImage]:
        """Obtiene las referencias de imágenes de productos de la empresa."""
        statement = (
            select(ProductImage)
            .where(ProductImage.empresa_id == company_id)
            .order_by(
                ProductImage.id_producto,
                ProductImage.es_principal.desc(),
                ProductImage.id_imagen_producto,
            )
        )
        return list(self.db.scalars(statement).all())

    def get_variants(self, company_id: int) -> list[ProductVariant]:
        """Obtiene las variantes activas de productos de la empresa."""
        statement = (
            select(ProductVariant)
            .where(
                ProductVariant.empresa_id == company_id,
                ProductVariant.estado.is_(True),
            )
            .order_by(ProductVariant.id_variante_producto)
        )
        return list(self.db.scalars(statement).all())

    def get_inventory(
        self, company_id: int, branch_ids: list[int]
    ) -> list[BranchInventory]:
        """Obtiene existencias físicas únicamente para las sucursales autorizadas de la empresa."""
        if not branch_ids:
            return []
        statement = (
            select(BranchInventory)
            .where(
                BranchInventory.empresa_id == company_id,
                BranchInventory.id_sucursal.in_(branch_ids),
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
