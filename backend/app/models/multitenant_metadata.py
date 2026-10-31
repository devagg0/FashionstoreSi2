"""Restricciones compuestas que reflejan el contrato Alembic multitenant."""

from sqlalchemy import ForeignKeyConstraint, UniqueConstraint

from app.core.database import Base


TENANT_PRIMARY_KEYS = {
    "t_cliente": "id_cliente", "t_empleado": "id_empleado",
    "t_proveedor": "id_proveedor", "t_sucursal": "id_sucursal",
    "t_empleado_sucursal": "id_empleado_sucursal", "t_categoria": "id_categoria",
    "t_talla": "id_talla", "t_color": "id_color", "t_temporada": "id_temporada",
    "t_coleccion": "id_coleccion", "t_producto": "id_producto",
    "t_variante_producto": "id_variante_producto",
    "t_producto_proveedor": "id_producto_proveedor",
    "t_producto_coleccion": "id_producto_coleccion",
    "t_imagen_producto": "id_imagen_producto", "t_promocion": "id_promocion",
    "t_promocion_producto": "id_promocion_producto",
    "t_inventario_sucursal": "id_inventario_sucursal", "t_reserva": "id_reserva",
    "t_detalle_reserva": "id_detalle_reserva", "t_carrito": "id_carrito",
    "t_detalle_carrito": "id_detalle_carrito", "t_venta": "id_venta",
    "t_detalle_venta": "id_detalle_venta",
    "t_movimiento_inventario": "id_movimiento_inventario",
    "t_detalle_movimiento_inventario": "id_detalle_movimiento_inventario",
    "t_pago": "id_pago", "t_devolucion": "id_devolucion",
    "t_detalle_devolucion": "id_detalle_devolucion", "t_reembolso": "id_reembolso",
}

SCOPED_UNIQUES = (
    ("t_cliente", "uq_cliente_empresa_usuario", ("empresa_id", "id_usuario")),
    ("t_empleado", "uq_empleado_empresa_usuario", ("empresa_id", "id_usuario")),
    ("t_proveedor", "uq_proveedor_empresa_usuario", ("empresa_id", "id_usuario")),
    ("t_categoria", "uq_categoria_empresa_nombre", ("empresa_id", "nombre")),
    ("t_talla", "uq_talla_empresa_nombre", ("empresa_id", "nombre")),
    ("t_color", "uq_color_empresa_nombre", ("empresa_id", "nombre")),
    ("t_variante_producto", "uq_variante_empresa_sku", ("empresa_id", "sku")),
    ("t_promocion", "uq_promocion_empresa_codigo", ("empresa_id", "codigo")),
    ("t_reserva", "uq_reserva_empresa_codigo", ("empresa_id", "codigo")),
    ("t_venta", "uq_venta_empresa_numero", ("empresa_id", "numero_venta")),
)

SPECIAL_UNIQUES = (
    ("t_empleado_sucursal", "uq_mt_empleado_sucursal_triple", ("empresa_id", "id_empleado", "id_sucursal")),
    ("t_detalle_venta", "uq_mt_detalle_venta_linea", ("empresa_id", "id_venta", "id_variante_producto")),
    ("t_pago", "uq_mt_pago_venta", ("empresa_id", "id_pago", "id_venta")),
    ("t_devolucion", "uq_mt_devolucion_venta", ("empresa_id", "id_devolucion", "id_venta")),
)

# tabla, locales, destino, remotas, nombre, ondelete
COMPOSITE_FOREIGN_KEYS = (
    ("t_cliente", ("empresa_id", "id_usuario"), "t_usuario_empresa", ("id_empresa", "id_usuario"), "fk_mt_cliente_membresia", "RESTRICT"),
    ("t_empleado", ("empresa_id", "id_usuario"), "t_usuario_empresa", ("id_empresa", "id_usuario"), "fk_mt_empleado_membresia", "RESTRICT"),
    ("t_proveedor", ("empresa_id", "id_usuario"), "t_usuario_empresa", ("id_empresa", "id_usuario"), "fk_mt_proveedor_membresia", "RESTRICT"),
    ("t_empleado_sucursal", ("empresa_id", "id_empleado"), "t_empleado", ("empresa_id", "id_empleado"), "fk_mt_asignacion_empleado", "RESTRICT"),
    ("t_empleado_sucursal", ("empresa_id", "id_sucursal"), "t_sucursal", ("empresa_id", "id_sucursal"), "fk_mt_asignacion_sucursal", "RESTRICT"),
    ("t_producto", ("empresa_id", "id_categoria"), "t_categoria", ("empresa_id", "id_categoria"), "fk_mt_producto_categoria", "RESTRICT"),
    ("t_producto", ("empresa_id", "id_temporada"), "t_temporada", ("empresa_id", "id_temporada"), "fk_mt_producto_temporada", "RESTRICT"),
    ("t_variante_producto", ("empresa_id", "id_producto"), "t_producto", ("empresa_id", "id_producto"), "fk_mt_variante_producto", "RESTRICT"),
    ("t_variante_producto", ("empresa_id", "id_talla"), "t_talla", ("empresa_id", "id_talla"), "fk_mt_variante_talla", "RESTRICT"),
    ("t_variante_producto", ("empresa_id", "id_color"), "t_color", ("empresa_id", "id_color"), "fk_mt_variante_color", "RESTRICT"),
    ("t_producto_proveedor", ("empresa_id", "id_producto"), "t_producto", ("empresa_id", "id_producto"), "fk_mt_producto_proveedor_producto", "RESTRICT"),
    ("t_producto_proveedor", ("empresa_id", "id_proveedor"), "t_proveedor", ("empresa_id", "id_proveedor"), "fk_mt_producto_proveedor_proveedor", "RESTRICT"),
    ("t_producto_coleccion", ("empresa_id", "id_producto"), "t_producto", ("empresa_id", "id_producto"), "fk_mt_producto_coleccion_producto", "RESTRICT"),
    ("t_producto_coleccion", ("empresa_id", "id_coleccion"), "t_coleccion", ("empresa_id", "id_coleccion"), "fk_mt_producto_coleccion_coleccion", "RESTRICT"),
    ("t_imagen_producto", ("empresa_id", "id_producto"), "t_producto", ("empresa_id", "id_producto"), "fk_mt_imagen_producto", "CASCADE"),
    ("t_promocion_producto", ("empresa_id", "id_promocion"), "t_promocion", ("empresa_id", "id_promocion"), "fk_mt_promocion_producto_promocion", "CASCADE"),
    ("t_promocion_producto", ("empresa_id", "id_producto"), "t_producto", ("empresa_id", "id_producto"), "fk_mt_promocion_producto_producto", "CASCADE"),
    ("t_inventario_sucursal", ("empresa_id", "id_sucursal"), "t_sucursal", ("empresa_id", "id_sucursal"), "fk_mt_inventario_sucursal", "RESTRICT"),
    ("t_inventario_sucursal", ("empresa_id", "id_variante_producto"), "t_variante_producto", ("empresa_id", "id_variante_producto"), "fk_mt_inventario_variante", "RESTRICT"),
    ("t_reserva", ("empresa_id", "id_cliente"), "t_cliente", ("empresa_id", "id_cliente"), "fk_mt_reserva_cliente", "RESTRICT"),
    ("t_reserva", ("empresa_id", "id_sucursal"), "t_sucursal", ("empresa_id", "id_sucursal"), "fk_mt_reserva_sucursal", "RESTRICT"),
    ("t_reserva", ("empresa_id", "id_empleado_atencion", "id_sucursal"), "t_empleado_sucursal", ("empresa_id", "id_empleado", "id_sucursal"), "fk_mt_reserva_empleado_sucursal", "RESTRICT"),
    ("t_detalle_reserva", ("empresa_id", "id_reserva"), "t_reserva", ("empresa_id", "id_reserva"), "fk_mt_detalle_reserva_cabecera", "CASCADE"),
    ("t_detalle_reserva", ("empresa_id", "id_variante_producto"), "t_variante_producto", ("empresa_id", "id_variante_producto"), "fk_mt_detalle_reserva_variante", "RESTRICT"),
    ("t_carrito", ("empresa_id", "id_cliente"), "t_cliente", ("empresa_id", "id_cliente"), "fk_mt_carrito_cliente", "RESTRICT"),
    ("t_detalle_carrito", ("empresa_id", "id_carrito"), "t_carrito", ("empresa_id", "id_carrito"), "fk_mt_detalle_carrito_cabecera", "CASCADE"),
    ("t_detalle_carrito", ("empresa_id", "id_variante_producto"), "t_variante_producto", ("empresa_id", "id_variante_producto"), "fk_mt_detalle_carrito_variante", "RESTRICT"),
    ("t_venta", ("empresa_id", "id_sucursal"), "t_sucursal", ("empresa_id", "id_sucursal"), "fk_mt_venta_sucursal", "RESTRICT"),
    ("t_venta", ("empresa_id", "id_empleado", "id_sucursal"), "t_empleado_sucursal", ("empresa_id", "id_empleado", "id_sucursal"), "fk_mt_venta_empleado_sucursal", "RESTRICT"),
    ("t_venta", ("empresa_id", "id_cliente"), "t_cliente", ("empresa_id", "id_cliente"), "fk_mt_venta_cliente", "RESTRICT"),
    ("t_venta", ("empresa_id", "id_reserva"), "t_reserva", ("empresa_id", "id_reserva"), "fk_mt_venta_reserva", "RESTRICT"),
    ("t_venta", ("empresa_id", "id_carrito"), "t_carrito", ("empresa_id", "id_carrito"), "fk_mt_venta_carrito", "RESTRICT"),
    ("t_detalle_venta", ("empresa_id", "id_venta"), "t_venta", ("empresa_id", "id_venta"), "fk_mt_detalle_venta_cabecera", "CASCADE"),
    ("t_detalle_venta", ("empresa_id", "id_variante_producto"), "t_variante_producto", ("empresa_id", "id_variante_producto"), "fk_mt_detalle_venta_variante", "RESTRICT"),
    ("t_detalle_venta", ("empresa_id", "id_promocion"), "t_promocion", ("empresa_id", "id_promocion"), "fk_mt_detalle_venta_promocion", "RESTRICT"),
    ("t_movimiento_inventario", ("empresa_id", "id_sucursal_origen"), "t_sucursal", ("empresa_id", "id_sucursal"), "fk_mt_movimiento_origen", "RESTRICT"),
    ("t_movimiento_inventario", ("empresa_id", "id_sucursal_destino"), "t_sucursal", ("empresa_id", "id_sucursal"), "fk_mt_movimiento_destino", "RESTRICT"),
    ("t_movimiento_inventario", ("empresa_id", "id_empleado_sucursal"), "t_empleado_sucursal", ("empresa_id", "id_empleado_sucursal"), "fk_mt_movimiento_responsable", "RESTRICT"),
    ("t_movimiento_inventario", ("empresa_id", "id_venta"), "t_venta", ("empresa_id", "id_venta"), "fk_mt_movimiento_venta", "RESTRICT"),
    ("t_detalle_movimiento_inventario", ("empresa_id", "id_movimiento_inventario"), "t_movimiento_inventario", ("empresa_id", "id_movimiento_inventario"), "fk_mt_detalle_movimiento_cabecera", "CASCADE"),
    ("t_detalle_movimiento_inventario", ("empresa_id", "id_variante_producto"), "t_variante_producto", ("empresa_id", "id_variante_producto"), "fk_mt_detalle_movimiento_variante", "RESTRICT"),
    ("t_pago", ("empresa_id", "id_venta"), "t_venta", ("empresa_id", "id_venta"), "fk_mt_pago_venta", "RESTRICT"),
    ("t_devolucion", ("empresa_id", "id_venta"), "t_venta", ("empresa_id", "id_venta"), "fk_mt_devolucion_venta", "RESTRICT"),
    ("t_devolucion", ("empresa_id", "id_movimiento_inventario"), "t_movimiento_inventario", ("empresa_id", "id_movimiento_inventario"), "fk_mt_devolucion_movimiento", "RESTRICT"),
    ("t_detalle_devolucion", ("empresa_id", "id_devolucion", "id_venta"), "t_devolucion", ("empresa_id", "id_devolucion", "id_venta"), "fk_mt_detalle_devolucion_cabecera", "RESTRICT"),
    ("t_detalle_devolucion", ("empresa_id", "id_venta", "id_variante_producto"), "t_detalle_venta", ("empresa_id", "id_venta", "id_variante_producto"), "fk_mt_detalle_devolucion_linea", "RESTRICT"),
    ("t_reembolso", ("empresa_id", "id_pago", "id_venta"), "t_pago", ("empresa_id", "id_pago", "id_venta"), "fk_mt_reembolso_pago", "RESTRICT"),
    ("t_reembolso", ("empresa_id", "id_devolucion", "id_venta"), "t_devolucion", ("empresa_id", "id_devolucion", "id_venta"), "fk_mt_reembolso_devolucion", "RESTRICT"),
)


def _has_constraint(table, name: str) -> bool:
    return any(constraint.name == name for constraint in table.constraints)


def configure_multitenant_metadata() -> None:
    """Completa metadata una sola vez después de importar todos los modelos."""
    for table_name, primary_key in TENANT_PRIMARY_KEYS.items():
        table = Base.metadata.tables[table_name]
        company_fk_name = f"fk_{table_name.removeprefix('t_')}_empresa"
        if not _has_constraint(table, company_fk_name):
            table.append_constraint(
                ForeignKeyConstraint(
                    ("empresa_id",),
                    ("t_empresa.id_empresa",),
                    name=company_fk_name,
                    ondelete="RESTRICT",
                )
            )
        name = f"uq_{table_name.removeprefix('t_')}_empresa_pk"
        if not _has_constraint(table, name):
            table.append_constraint(UniqueConstraint("empresa_id", primary_key, name=name))

    for table_name, name, columns in (*SCOPED_UNIQUES, *SPECIAL_UNIQUES):
        table = Base.metadata.tables[table_name]
        if not _has_constraint(table, name):
            table.append_constraint(UniqueConstraint(*columns, name=name))

    for table_name, local, target, remote, name, ondelete in COMPOSITE_FOREIGN_KEYS:
        table = Base.metadata.tables[table_name]
        if not _has_constraint(table, name):
            table.append_constraint(
                ForeignKeyConstraint(
                    local,
                    [f"{target}.{column}" for column in remote],
                    name=name,
                    ondelete=ondelete,
                )
            )
