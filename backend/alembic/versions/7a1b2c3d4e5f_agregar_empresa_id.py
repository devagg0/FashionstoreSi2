"""agregar empresa_id nullable a tablas empresariales

Revision ID: 7a1b2c3d4e5f
Revises: 6f0a1b2c3d4e
Create Date: 2026-10-29

"""

from alembic import op
import sqlalchemy as sa


revision = "7a1b2c3d4e5f"
down_revision = "6f0a1b2c3d4e"
branch_labels = None
depends_on = None


TENANT_TABLES = (
    "t_cliente",
    "t_empleado",
    "t_proveedor",
    "t_sucursal",
    "t_empleado_sucursal",
    "t_categoria",
    "t_talla",
    "t_color",
    "t_temporada",
    "t_coleccion",
    "t_producto",
    "t_variante_producto",
    "t_producto_proveedor",
    "t_producto_coleccion",
    "t_imagen_producto",
    "t_promocion",
    "t_promocion_producto",
    "t_inventario_sucursal",
    "t_reserva",
    "t_detalle_reserva",
    "t_carrito",
    "t_detalle_carrito",
    "t_venta",
    "t_detalle_venta",
    "t_movimiento_inventario",
    "t_detalle_movimiento_inventario",
    "t_pago",
    "t_devolucion",
    "t_detalle_devolucion",
    "t_reembolso",
)


def _stem(table: str) -> str:
    return table.removeprefix("t_")


def upgrade() -> None:
    """Fase expand: nullable para mantener operativo el backend anterior."""
    for table in TENANT_TABLES:
        stem = _stem(table)
        op.add_column(table, sa.Column("empresa_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            f"fk_{stem}_empresa",
            table,
            "t_empresa",
            ["empresa_id"],
            ["id_empresa"],
            ondelete="RESTRICT",
        )
        op.create_index(f"ix_{stem}_empresa_id", table, ["empresa_id"])


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        stem = _stem(table)
        op.drop_index(f"ix_{stem}_empresa_id", table_name=table)
        op.drop_constraint(f"fk_{stem}_empresa", table, type_="foreignkey")
        op.drop_column(table, "empresa_id")
