"""ampliar t_devolucion y t_detalle_devolucion para CU15 cambio y devolucion de prenda

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-11-07
"""

from alembic import op
import sqlalchemy as sa


revision = "d6e7f8a9b0c1"
down_revision = "c5d6e7f8a9b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "t_devolucion",
        sa.Column(
            "modalidad_entrega",
            sa.String(length=30),
            nullable=True,
        ),
    )
    op.drop_constraint("ck_devolucion_tipo", "t_devolucion", type_="check")
    op.create_check_constraint(
        "ck_devolucion_tipo",
        "t_devolucion",
        "tipo IN ('DEVOLUCION','CANCELACION','CAMBIO')",
    )
    op.create_check_constraint(
        "ck_devolucion_modalidad_entrega",
        "t_devolucion",
        "modalidad_entrega IS NULL OR modalidad_entrega IN ('ENTREGA_EN_TIENDA','DELIVERY_SIMULADO')",
    )

    op.add_column(
        "t_detalle_devolucion",
        sa.Column("id_variante_reemplazo", sa.Integer(), nullable=True),
    )
    op.add_column(
        "t_detalle_devolucion",
        sa.Column(
            "cantidad_reemplazo",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "t_detalle_devolucion",
        sa.Column(
            "precio_original_reconocido",
            sa.Numeric(precision=12, scale=2),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "t_detalle_devolucion",
        sa.Column(
            "precio_reemplazo_estimado",
            sa.Numeric(precision=12, scale=2),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "t_detalle_devolucion",
        sa.Column(
            "diferencia_precio_estimada",
            sa.Numeric(precision=12, scale=2),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.create_foreign_key(
        "fk_detalle_devolucion_variante_reemplazo",
        "t_detalle_devolucion",
        "t_variante_producto",
        ["id_variante_reemplazo"],
        ["id_variante_producto"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_detalle_devolucion_cantidad_reemplazo",
        "t_detalle_devolucion",
        "cantidad_reemplazo >= 0",
    )
    op.create_check_constraint(
        "ck_detalle_devolucion_reemplazo_consistente",
        "t_detalle_devolucion",
        "(id_variante_reemplazo IS NULL AND cantidad_reemplazo = 0) OR (id_variante_reemplazo IS NOT NULL AND cantidad_reemplazo = cantidad)",
    )
    op.create_check_constraint(
        "ck_detalle_devolucion_precios_estimados",
        "t_detalle_devolucion",
        "precio_original_reconocido >= 0 AND precio_reemplazo_estimado >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_detalle_devolucion_precios_estimados",
        "t_detalle_devolucion",
        type_="check",
    )
    op.drop_constraint(
        "ck_detalle_devolucion_reemplazo_consistente",
        "t_detalle_devolucion",
        type_="check",
    )
    op.drop_constraint(
        "ck_detalle_devolucion_cantidad_reemplazo",
        "t_detalle_devolucion",
        type_="check",
    )
    op.drop_constraint(
        "fk_detalle_devolucion_variante_reemplazo",
        "t_detalle_devolucion",
        type_="foreignkey",
    )
    op.drop_column("t_detalle_devolucion", "diferencia_precio_estimada")
    op.drop_column("t_detalle_devolucion", "precio_reemplazo_estimado")
    op.drop_column("t_detalle_devolucion", "precio_original_reconocido")
    op.drop_column("t_detalle_devolucion", "cantidad_reemplazo")
    op.drop_column("t_detalle_devolucion", "id_variante_reemplazo")

    op.drop_constraint(
        "ck_devolucion_modalidad_entrega", "t_devolucion", type_="check"
    )
    op.drop_constraint("ck_devolucion_tipo", "t_devolucion", type_="check")
    op.create_check_constraint(
        "ck_devolucion_tipo",
        "t_devolucion",
        "tipo IN ('DEVOLUCION','CANCELACION')",
    )
    op.drop_column("t_devolucion", "modalidad_entrega")

