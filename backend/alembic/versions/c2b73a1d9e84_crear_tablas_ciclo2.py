"""crear tablas ciclo2

Revision ID: c2b73a1d9e84
Revises: 7b3c2d1e9f40
Create Date: 2026-09-07 18:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c2b73a1d9e84"
down_revision: Union[str, Sequence[str], None] = "7b3c2d1e9f40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Crea exclusivamente las tablas y los índices del Ciclo 2."""
    op.create_table(
        "t_promocion",
        sa.Column("id_promocion", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("nombre", sa.String(length=150), nullable=False),
        sa.Column("codigo", sa.String(length=50), nullable=True),
        sa.Column("descripcion", sa.String(length=200), nullable=True),
        sa.Column("tipo_descuento", sa.String(length=20), nullable=False),
        sa.Column("valor", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("fecha_inicio", sa.DateTime(), nullable=False),
        sa.Column("fecha_fin", sa.DateTime(), nullable=False),
        sa.Column(
            "acumulable",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "estado",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "tipo_descuento IN ('PORCENTAJE', 'MONTO_FIJO')",
            name="ck_promocion_tipo_descuento",
        ),
        sa.CheckConstraint(
            "valor > 0",
            name="ck_promocion_valor_positivo",
        ),
        sa.CheckConstraint(
            "tipo_descuento <> 'PORCENTAJE' OR valor <= 100",
            name="ck_promocion_porcentaje_valido",
        ),
        sa.CheckConstraint(
            "fecha_fin >= fecha_inicio",
            name="ck_promocion_rango_fechas",
        ),
        sa.PrimaryKeyConstraint("id_promocion"),
        sa.UniqueConstraint("codigo"),
    )
    op.create_index(
        "ix_promocion_vigencia",
        "t_promocion",
        ["estado", "fecha_inicio", "fecha_fin"],
        unique=False,
    )

    op.create_table(
        "t_promocion_producto",
        sa.Column(
            "id_promocion_producto",
            sa.Integer(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("id_promocion", sa.Integer(), nullable=False),
        sa.Column("id_producto", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["id_producto"],
            ["t_producto.id_producto"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["id_promocion"],
            ["t_promocion.id_promocion"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id_promocion_producto"),
        sa.UniqueConstraint(
            "id_promocion",
            "id_producto",
            name="uq_promocion_producto",
        ),
    )
    op.create_index(
        "ix_promocion_producto_id_producto",
        "t_promocion_producto",
        ["id_producto"],
        unique=False,
    )

    op.create_table(
        "t_inventario_sucursal",
        sa.Column(
            "id_inventario_sucursal",
            sa.Integer(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("id_sucursal", sa.Integer(), nullable=False),
        sa.Column("id_variante_producto", sa.Integer(), nullable=False),
        sa.Column(
            "stock_actual",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "stock_reservado",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "stock_minimo",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "stock_actual >= 0",
            name="ck_inventario_stock_actual",
        ),
        sa.CheckConstraint(
            "stock_reservado >= 0",
            name="ck_inventario_stock_reservado",
        ),
        sa.CheckConstraint(
            "stock_minimo >= 0",
            name="ck_inventario_stock_minimo",
        ),
        sa.CheckConstraint(
            "stock_reservado <= stock_actual",
            name="ck_inventario_reservado_disponible",
        ),
        sa.ForeignKeyConstraint(
            ["id_sucursal"],
            ["t_sucursal.id_sucursal"],
        ),
        sa.ForeignKeyConstraint(
            ["id_variante_producto"],
            ["t_variante_producto.id_variante_producto"],
        ),
        sa.PrimaryKeyConstraint("id_inventario_sucursal"),
        sa.UniqueConstraint(
            "id_sucursal",
            "id_variante_producto",
            name="uq_inventario_sucursal_variante",
        ),
    )
    op.create_index(
        "ix_inventario_sucursal_id_variante_producto",
        "t_inventario_sucursal",
        ["id_variante_producto"],
        unique=False,
    )

    op.create_table(
        "t_reserva",
        sa.Column("id_reserva", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id_cliente", sa.Integer(), nullable=False),
        sa.Column("id_sucursal", sa.Integer(), nullable=False),
        sa.Column("id_empleado_atencion", sa.Integer(), nullable=True),
        sa.Column("codigo", sa.String(length=50), nullable=False),
        sa.Column(
            "estado",
            sa.String(length=20),
            server_default=sa.text("'PENDIENTE'"),
            nullable=False,
        ),
        sa.Column("fecha_expiracion", sa.DateTime(), nullable=False),
        sa.Column("fecha_atencion", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "estado IN ("
            "'PENDIENTE', 'CONFIRMADA', 'ATENDIDA', "
            "'CANCELADA', 'EXPIRADA'"
            ")",
            name="ck_reserva_estado",
        ),
        sa.CheckConstraint(
            "fecha_expiracion > created_at",
            name="ck_reserva_fecha_expiracion",
        ),
        sa.ForeignKeyConstraint(
            ["id_cliente"],
            ["t_cliente.id_cliente"],
        ),
        sa.ForeignKeyConstraint(
            ["id_empleado_atencion", "id_sucursal"],
            [
                "t_empleado_sucursal.id_empleado",
                "t_empleado_sucursal.id_sucursal",
            ],
            name="fk_reserva_empleado_sucursal",
        ),
        sa.ForeignKeyConstraint(
            ["id_sucursal"],
            ["t_sucursal.id_sucursal"],
        ),
        sa.PrimaryKeyConstraint("id_reserva"),
        sa.UniqueConstraint("codigo"),
    )
    op.create_index(
        "ix_reserva_cliente_created_at",
        "t_reserva",
        ["id_cliente", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_reserva_sucursal_estado",
        "t_reserva",
        ["id_sucursal", "estado"],
        unique=False,
    )

    op.create_table(
        "t_detalle_reserva",
        sa.Column(
            "id_detalle_reserva",
            sa.Integer(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("id_reserva", sa.Integer(), nullable=False),
        sa.Column("id_variante_producto", sa.Integer(), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.Column(
            "precio_unitario",
            sa.Numeric(precision=10, scale=2),
            nullable=False,
        ),
        sa.CheckConstraint(
            "cantidad > 0",
            name="ck_detalle_reserva_cantidad",
        ),
        sa.CheckConstraint(
            "precio_unitario >= 0",
            name="ck_detalle_reserva_precio",
        ),
        sa.ForeignKeyConstraint(
            ["id_reserva"],
            ["t_reserva.id_reserva"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["id_variante_producto"],
            ["t_variante_producto.id_variante_producto"],
        ),
        sa.PrimaryKeyConstraint("id_detalle_reserva"),
        sa.UniqueConstraint(
            "id_reserva",
            "id_variante_producto",
            name="uq_detalle_reserva_variante",
        ),
    )
    op.create_index(
        "ix_detalle_reserva_id_variante_producto",
        "t_detalle_reserva",
        ["id_variante_producto"],
        unique=False,
    )

    op.create_table(
        "t_carrito",
        sa.Column("id_carrito", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id_cliente", sa.Integer(), nullable=False),
        sa.Column(
            "estado",
            sa.String(length=20),
            server_default=sa.text("'ACTIVO'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "estado IN ('ACTIVO', 'CONVERTIDO', 'ABANDONADO')",
            name="ck_carrito_estado",
        ),
        sa.ForeignKeyConstraint(
            ["id_cliente"],
            ["t_cliente.id_cliente"],
        ),
        sa.PrimaryKeyConstraint("id_carrito"),
    )
    op.create_index(
        "uq_carrito_cliente_activo",
        "t_carrito",
        ["id_cliente"],
        unique=True,
        postgresql_where=sa.text("estado = 'ACTIVO'"),
    )

    op.create_table(
        "t_detalle_carrito",
        sa.Column(
            "id_detalle_carrito",
            sa.Integer(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("id_carrito", sa.Integer(), nullable=False),
        sa.Column("id_variante_producto", sa.Integer(), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "cantidad > 0",
            name="ck_detalle_carrito_cantidad",
        ),
        sa.ForeignKeyConstraint(
            ["id_carrito"],
            ["t_carrito.id_carrito"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["id_variante_producto"],
            ["t_variante_producto.id_variante_producto"],
        ),
        sa.PrimaryKeyConstraint("id_detalle_carrito"),
        sa.UniqueConstraint(
            "id_carrito",
            "id_variante_producto",
            name="uq_detalle_carrito_variante",
        ),
    )

    op.create_table(
        "t_venta",
        sa.Column("id_venta", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id_sucursal", sa.Integer(), nullable=False),
        sa.Column("id_empleado", sa.Integer(), nullable=False),
        sa.Column("id_cliente", sa.Integer(), nullable=True),
        sa.Column("id_reserva", sa.Integer(), nullable=True),
        sa.Column("numero_venta", sa.String(length=50), nullable=False),
        sa.Column(
            "estado",
            sa.String(length=20),
            server_default=sa.text("'PENDIENTE'"),
            nullable=False,
        ),
        sa.Column(
            "subtotal",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
        ),
        sa.Column(
            "descuento_total",
            sa.Numeric(precision=12, scale=2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "total",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
        ),
        sa.Column(
            "fecha_venta",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "estado IN ('PENDIENTE', 'COMPLETADA', 'ANULADA')",
            name="ck_venta_estado",
        ),
        sa.CheckConstraint(
            "subtotal >= 0",
            name="ck_venta_subtotal",
        ),
        sa.CheckConstraint(
            "descuento_total >= 0 AND descuento_total <= subtotal",
            name="ck_venta_descuento_total",
        ),
        sa.CheckConstraint(
            "total >= 0",
            name="ck_venta_total",
        ),
        sa.CheckConstraint(
            "total = subtotal - descuento_total",
            name="ck_venta_calculo_total",
        ),
        sa.ForeignKeyConstraint(
            ["id_cliente"],
            ["t_cliente.id_cliente"],
        ),
        sa.ForeignKeyConstraint(
            ["id_empleado", "id_sucursal"],
            [
                "t_empleado_sucursal.id_empleado",
                "t_empleado_sucursal.id_sucursal",
            ],
            name="fk_venta_empleado_sucursal",
        ),
        sa.ForeignKeyConstraint(
            ["id_reserva"],
            ["t_reserva.id_reserva"],
        ),
        sa.ForeignKeyConstraint(
            ["id_sucursal"],
            ["t_sucursal.id_sucursal"],
        ),
        sa.PrimaryKeyConstraint("id_venta"),
        sa.UniqueConstraint("id_reserva", name="uq_venta_reserva"),
        sa.UniqueConstraint("numero_venta"),
    )
    op.create_index(
        "ix_venta_cliente_fecha",
        "t_venta",
        ["id_cliente", "fecha_venta"],
        unique=False,
    )
    op.create_index(
        "ix_venta_sucursal_fecha",
        "t_venta",
        ["id_sucursal", "fecha_venta"],
        unique=False,
    )

    op.create_table(
        "t_detalle_venta",
        sa.Column(
            "id_detalle_venta",
            sa.Integer(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("id_venta", sa.Integer(), nullable=False),
        sa.Column("id_variante_producto", sa.Integer(), nullable=False),
        sa.Column("id_promocion", sa.Integer(), nullable=True),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.Column(
            "precio_unitario",
            sa.Numeric(precision=10, scale=2),
            nullable=False,
        ),
        sa.Column(
            "descuento_unitario",
            sa.Numeric(precision=10, scale=2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "subtotal_linea",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
        ),
        sa.CheckConstraint(
            "cantidad > 0",
            name="ck_detalle_venta_cantidad",
        ),
        sa.CheckConstraint(
            "precio_unitario >= 0",
            name="ck_detalle_venta_precio",
        ),
        sa.CheckConstraint(
            "descuento_unitario >= 0 "
            "AND descuento_unitario <= precio_unitario",
            name="ck_detalle_venta_descuento",
        ),
        sa.CheckConstraint(
            "subtotal_linea >= 0",
            name="ck_detalle_venta_subtotal",
        ),
        sa.CheckConstraint(
            "subtotal_linea = cantidad * "
            "(precio_unitario - descuento_unitario)",
            name="ck_detalle_venta_calculo_subtotal",
        ),
        sa.ForeignKeyConstraint(
            ["id_promocion"],
            ["t_promocion.id_promocion"],
        ),
        sa.ForeignKeyConstraint(
            ["id_variante_producto"],
            ["t_variante_producto.id_variante_producto"],
        ),
        sa.ForeignKeyConstraint(
            ["id_venta"],
            ["t_venta.id_venta"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id_detalle_venta"),
        sa.UniqueConstraint(
            "id_venta",
            "id_variante_producto",
            name="uq_detalle_venta_variante",
        ),
    )
    op.create_index(
        "ix_detalle_venta_id_variante_producto",
        "t_detalle_venta",
        ["id_variante_producto"],
        unique=False,
    )

    op.create_table(
        "t_movimiento_inventario",
        sa.Column(
            "id_movimiento_inventario",
            sa.Integer(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("id_sucursal_origen", sa.Integer(), nullable=True),
        sa.Column("id_sucursal_destino", sa.Integer(), nullable=True),
        sa.Column("id_empleado_sucursal", sa.Integer(), nullable=False),
        sa.Column("id_venta", sa.Integer(), nullable=True),
        sa.Column("tipo_movimiento", sa.String(length=30), nullable=False),
        sa.Column(
            "estado",
            sa.String(length=20),
            server_default=sa.text("'PENDIENTE'"),
            nullable=False,
        ),
        sa.Column("motivo", sa.String(length=200), nullable=True),
        sa.Column(
            "fecha_movimiento",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "tipo_movimiento IN ("
            "'ENTRADA', 'SALIDA', 'TRANSFERENCIA', "
            "'AJUSTE_POSITIVO', 'AJUSTE_NEGATIVO', 'VENTA'"
            ")",
            name="ck_movimiento_inventario_tipo",
        ),
        sa.CheckConstraint(
            "estado IN ('PENDIENTE', 'CONFIRMADO', 'ANULADO')",
            name="ck_movimiento_inventario_estado",
        ),
        sa.CheckConstraint(
            "(tipo_movimiento = 'TRANSFERENCIA' "
            "AND id_sucursal_origen IS NOT NULL "
            "AND id_sucursal_destino IS NOT NULL "
            "AND id_sucursal_origen <> id_sucursal_destino) "
            "OR (tipo_movimiento IN ('ENTRADA', 'AJUSTE_POSITIVO') "
            "AND id_sucursal_origen IS NULL "
            "AND id_sucursal_destino IS NOT NULL) "
            "OR (tipo_movimiento IN ("
            "'SALIDA', 'AJUSTE_NEGATIVO', 'VENTA'"
            ") AND id_sucursal_origen IS NOT NULL "
            "AND id_sucursal_destino IS NULL)",
            name="ck_movimiento_inventario_sucursales",
        ),
        sa.CheckConstraint(
            "(tipo_movimiento = 'VENTA' AND id_venta IS NOT NULL) "
            "OR (tipo_movimiento <> 'VENTA' AND id_venta IS NULL)",
            name="ck_movimiento_inventario_venta",
        ),
        sa.ForeignKeyConstraint(
            ["id_empleado_sucursal"],
            ["t_empleado_sucursal.id_empleado_sucursal"],
        ),
        sa.ForeignKeyConstraint(
            ["id_sucursal_destino"],
            ["t_sucursal.id_sucursal"],
        ),
        sa.ForeignKeyConstraint(
            ["id_sucursal_origen"],
            ["t_sucursal.id_sucursal"],
        ),
        sa.ForeignKeyConstraint(
            ["id_venta"],
            ["t_venta.id_venta"],
        ),
        sa.PrimaryKeyConstraint("id_movimiento_inventario"),
        sa.UniqueConstraint(
            "id_venta",
            name="uq_movimiento_inventario_venta",
        ),
    )
    op.create_index(
        "ix_movimiento_inventario_destino_fecha",
        "t_movimiento_inventario",
        ["id_sucursal_destino", "fecha_movimiento"],
        unique=False,
    )
    op.create_index(
        "ix_movimiento_inventario_origen_fecha",
        "t_movimiento_inventario",
        ["id_sucursal_origen", "fecha_movimiento"],
        unique=False,
    )

    op.create_table(
        "t_detalle_movimiento_inventario",
        sa.Column(
            "id_detalle_movimiento_inventario",
            sa.Integer(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("id_movimiento_inventario", sa.Integer(), nullable=False),
        sa.Column("id_variante_producto", sa.Integer(), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.Column(
            "costo_unitario",
            sa.Numeric(precision=10, scale=2),
            nullable=True,
        ),
        sa.CheckConstraint(
            "cantidad > 0",
            name="ck_detalle_movimiento_cantidad",
        ),
        sa.CheckConstraint(
            "costo_unitario IS NULL OR costo_unitario >= 0",
            name="ck_detalle_movimiento_costo",
        ),
        sa.ForeignKeyConstraint(
            ["id_movimiento_inventario"],
            ["t_movimiento_inventario.id_movimiento_inventario"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["id_variante_producto"],
            ["t_variante_producto.id_variante_producto"],
        ),
        sa.PrimaryKeyConstraint("id_detalle_movimiento_inventario"),
        sa.UniqueConstraint(
            "id_movimiento_inventario",
            "id_variante_producto",
            name="uq_detalle_movimiento_variante",
        ),
    )
    op.create_index(
        "ix_detalle_movimiento_id_variante_producto",
        "t_detalle_movimiento_inventario",
        ["id_variante_producto"],
        unique=False,
    )


def downgrade() -> None:
    """Elimina exclusivamente las tablas y los índices del Ciclo 2."""
    op.drop_index(
        "ix_detalle_movimiento_id_variante_producto",
        table_name="t_detalle_movimiento_inventario",
    )
    op.drop_table("t_detalle_movimiento_inventario")

    op.drop_index(
        "ix_movimiento_inventario_origen_fecha",
        table_name="t_movimiento_inventario",
    )
    op.drop_index(
        "ix_movimiento_inventario_destino_fecha",
        table_name="t_movimiento_inventario",
    )
    op.drop_table("t_movimiento_inventario")

    op.drop_index(
        "ix_detalle_venta_id_variante_producto",
        table_name="t_detalle_venta",
    )
    op.drop_table("t_detalle_venta")
    op.drop_index("ix_venta_sucursal_fecha", table_name="t_venta")
    op.drop_index("ix_venta_cliente_fecha", table_name="t_venta")
    op.drop_table("t_venta")

    op.drop_table("t_detalle_carrito")
    op.drop_index("uq_carrito_cliente_activo", table_name="t_carrito")
    op.drop_table("t_carrito")

    op.drop_index(
        "ix_detalle_reserva_id_variante_producto",
        table_name="t_detalle_reserva",
    )
    op.drop_table("t_detalle_reserva")
    op.drop_index("ix_reserva_sucursal_estado", table_name="t_reserva")
    op.drop_index("ix_reserva_cliente_created_at", table_name="t_reserva")
    op.drop_table("t_reserva")

    op.drop_index(
        "ix_inventario_sucursal_id_variante_producto",
        table_name="t_inventario_sucursal",
    )
    op.drop_table("t_inventario_sucursal")

    op.drop_index(
        "ix_promocion_producto_id_producto",
        table_name="t_promocion_producto",
    )
    op.drop_table("t_promocion_producto")
    op.drop_index("ix_promocion_vigencia", table_name="t_promocion")
    op.drop_table("t_promocion")
