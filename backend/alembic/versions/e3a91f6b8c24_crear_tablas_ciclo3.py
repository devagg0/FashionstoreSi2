"""crear_tablas_ciclo3

Revision ID: e3a91f6b8c24
Revises: 9d4a7c6e2b11
Create Date: 2026-09-17 16:49:39.727373

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e3a91f6b8c24'
down_revision = '9d4a7c6e2b11'
branch_labels = None
depends_on = None


# Stock: false sin retencion; true solo si una venta DIGITAL PENDIENTE
# compromete unidades en stock_reservado. Volver a false al completar,
# cancelar, expirar o liberar, dentro de la misma transaccion de inventario.
# Desde reserva: transferir el compromiso, NO incrementar stock_reservado
# otra vez. Esta migracion no crea reservas ni modifica stocks.
# CHECK no controla sumas entre filas: limites acumulados, moneda del pago,
# transiciones, reintegro y conciliacion requieren bloqueos en el futuro.
# UTC sin zona, actualizado explicitamente, como las tablas comerciales.


def col(name, kind, nullable=False, default=None):
    return sa.Column(name, kind, nullable=nullable,
                     server_default=sa.text(default) if default is not None else None)


def pk(name):
    return sa.Column(name, sa.Integer(), primary_key=True, autoincrement=True)


def timestamps():
    return [col(n, sa.DateTime(), default="now()") for n in ("created_at", "updated_at")]


def fk(columns, targets, name):
    return sa.ForeignKeyConstraint(columns, targets, name=name, ondelete="RESTRICT")


def check(name, expression):
    return sa.CheckConstraint(expression, name=name)


def index(name, table, columns, where=None, unique=False):
    options = {"postgresql_where": sa.text(where)} if where else {}
    op.create_index(name, table, columns, unique=unique, **options)


VENTA_CHECKS = {
    "ck_venta_canal": "canal IN ('PRESENCIAL','DIGITAL')",
    "ck_venta_moneda": "moneda = 'BOB'",
    "ck_venta_empleado_canal": "canal = 'DIGITAL' OR id_empleado IS NOT NULL",
    "ck_venta_cliente_digital": "canal <> 'DIGITAL' OR id_cliente IS NOT NULL",
    "ck_venta_carrito_canal": "id_carrito IS NULL OR canal = 'DIGITAL'",
    "ck_venta_fecha_completada": (
        "(estado <> 'PENDIENTE' OR fecha_completada IS NULL) AND "
        "(estado <> 'COMPLETADA' OR fecha_completada IS NOT NULL) AND "
        "(fecha_completada IS NULL OR fecha_completada >= fecha_venta)"
    ),
    "ck_venta_expiracion_pago": "fecha_expiracion_pago IS NULL OR fecha_expiracion_pago > created_at",
    "ck_venta_stock_comprometido": "NOT stock_comprometido OR (canal = 'DIGITAL' AND estado = 'PENDIENTE')",
}


def upgrade() -> None:
    """Crear Ciclo 3 con moneda oficial BOB, sin conversion de importes."""
    op.add_column("t_venta", col("canal", sa.String(20), default="'PRESENCIAL'"))
    op.add_column("t_venta", col("moneda", sa.String(3), nullable=True))
    op.execute("UPDATE t_venta SET moneda = 'BOB' WHERE moneda IS NULL")
    # SET NOT NULL verifica que el backfill no dejo ningun NULL.
    op.alter_column("t_venta", "moneda", existing_type=sa.String(3), nullable=False)
    op.add_column("t_venta", col("id_carrito", sa.Integer(), nullable=True))
    op.add_column("t_venta", col("fecha_completada", sa.DateTime(), nullable=True))
    # No habia fecha efectiva: aproximacion documentada para ventas historicas.
    op.execute("UPDATE t_venta SET fecha_completada = fecha_venta WHERE estado = 'COMPLETADA'")
    op.add_column("t_venta", col("fecha_expiracion_pago", sa.DateTime(), nullable=True))
    op.add_column("t_venta", col("stock_comprometido", sa.Boolean(), default="false"))
    op.alter_column("t_venta", "id_empleado", existing_type=sa.Integer(), nullable=True)
    op.create_foreign_key("fk_venta_carrito", "t_venta", "t_carrito", ["id_carrito"], ["id_carrito"], ondelete="RESTRICT")
    op.create_unique_constraint("uq_venta_carrito", "t_venta", ["id_carrito"])
    for name, expression in VENTA_CHECKS.items():
        op.create_check_constraint(name, "t_venta", expression)
    index("ix_venta_expiracion_comprometida", "t_venta", ["fecha_expiracion_pago"], "estado = 'PENDIENTE' AND stock_comprometido")
    index("ix_venta_fecha_completada", "t_venta", ["fecha_completada"], "fecha_completada IS NOT NULL")

    op.alter_column("t_movimiento_inventario", "id_empleado_sucursal", existing_type=sa.Integer(), nullable=True)
    op.create_check_constraint("ck_movimiento_responsable_automatico", "t_movimiento_inventario",
                               "id_empleado_sucursal IS NOT NULL OR (tipo_movimiento = 'VENTA' AND id_venta IS NOT NULL)")
    # Validacion relacional, en ambos sentidos. Bloquear venta serializa cambios
    # de canal con inserciones/actualizaciones de movimientos automaticos.
    op.execute("""CREATE FUNCTION fn_ciclo3_movimiento_digital() RETURNS trigger
        LANGUAGE plpgsql AS $$ DECLARE venta_canal varchar(20); BEGIN
            IF NEW.id_empleado_sucursal IS NULL THEN
                SELECT canal INTO venta_canal FROM t_venta
                    WHERE id_venta = NEW.id_venta FOR UPDATE;
                IF NEW.tipo_movimiento <> 'VENTA' OR venta_canal IS DISTINCT FROM 'DIGITAL' THEN
                    RAISE EXCEPTION 'Movimiento sin empleado requiere venta DIGITAL' USING ERRCODE = '23514';
                END IF;
            END IF;
            RETURN NEW;
        END $$""")
    op.execute("""CREATE TRIGGER tr_ciclo3_movimiento_digital BEFORE INSERT OR UPDATE ON t_movimiento_inventario
        FOR EACH ROW EXECUTE FUNCTION fn_ciclo3_movimiento_digital()""")
    op.execute("""CREATE FUNCTION fn_ciclo3_venta_canal() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
            IF NEW.canal <> 'DIGITAL' AND EXISTS (SELECT 1 FROM t_movimiento_inventario
                WHERE id_venta = NEW.id_venta AND id_empleado_sucursal IS NULL) THEN
                RAISE EXCEPTION 'Venta con movimiento automatico debe permanecer DIGITAL' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END $$""")
    op.execute("""CREATE TRIGGER tr_ciclo3_venta_canal BEFORE UPDATE OF canal ON t_venta
        FOR EACH ROW EXECUTE FUNCTION fn_ciclo3_venta_canal()""")

    op.create_table("t_pago",
        pk("id_pago"), col("id_venta", sa.Integer()),
        col("medio", sa.String(20)), col("proveedor", sa.String(20)), col("entorno", sa.String(20)),
        col("estado", sa.String(20), default="'PENDIENTE'"), col("monto", sa.Numeric(12, 2)),
        col("moneda", sa.String(3)), col("referencia_externa", sa.String(255), nullable=True),
        col("clave_idempotencia", postgresql.UUID(as_uuid=True)),
        col("fecha_aprobacion", sa.DateTime(), nullable=True), *timestamps(),
        fk(["id_venta"], ["t_venta.id_venta"], "fk_pago_venta"),
        sa.UniqueConstraint("clave_idempotencia", name="uq_pago_idempotencia"),
        sa.UniqueConstraint("proveedor", "entorno", "referencia_externa", name="uq_pago_referencia"),
        sa.UniqueConstraint("id_pago", "id_venta", name="uq_pago_venta_pertenencia"),
        check("ck_pago_estado", "estado IN ('PENDIENTE','APROBADO','RECHAZADO','CANCELADO','EXPIRADO','REEMBOLSADO')"),
        check("ck_pago_medio", "medio IN ('EFECTIVO','QR','TARJETA')"),
        check("ck_pago_proveedor", "proveedor IN ('MANUAL','STRIPE')"),
        check("ck_pago_entorno", "entorno IN ('LOCAL','TEST')"),
        check("ck_pago_combinacion", "(proveedor = 'MANUAL' AND entorno = 'LOCAL' AND medio IN ('EFECTIVO','QR')) OR (proveedor = 'STRIPE' AND entorno = 'TEST' AND medio = 'TARJETA')"),
        check("ck_pago_monto", "monto > 0"), check("ck_pago_moneda", "moneda = 'BOB'"),
        check("ck_pago_referencia", "referencia_externa IS NULL OR length(trim(referencia_externa)) > 0"),
        check("ck_pago_aprobacion", "estado NOT IN ('APROBADO','REEMBOLSADO') OR fecha_aprobacion IS NOT NULL"),
        check("ck_pago_stripe_referencia", "proveedor <> 'STRIPE' OR estado NOT IN ('APROBADO','REEMBOLSADO') OR referencia_externa IS NOT NULL"),
    )
    index("ix_pago_venta_created_at", "t_pago", ["id_venta", "created_at"])
    index("uq_pago_venta_cobrado", "t_pago", ["id_venta"], "estado IN ('APROBADO','REEMBOLSADO')", True)
    index("uq_pago_venta_pendiente", "t_pago", ["id_venta"], "estado = 'PENDIENTE'", True)

    op.create_table("t_devolucion",
        pk("id_devolucion"), col("id_venta", sa.Integer()), col("tipo", sa.String(20)),
        col("estado", sa.String(20), default="'SOLICITADA'"), col("motivo", sa.String(500)),
        col("id_usuario_solicitante", sa.Integer()), col("id_usuario_resolutor", sa.Integer(), nullable=True),
        col("id_movimiento_inventario", sa.Integer(), nullable=True),
        col("clave_idempotencia", postgresql.UUID(as_uuid=True)),
        col("fecha_resolucion", sa.DateTime(), nullable=True),
        col("fecha_procesamiento", sa.DateTime(), nullable=True), *timestamps(),
        fk(["id_venta"], ["t_venta.id_venta"], "fk_devolucion_venta"),
        fk(["id_usuario_solicitante"], ["t_usuario.id_usuario"], "fk_devolucion_solicitante"),
        fk(["id_usuario_resolutor"], ["t_usuario.id_usuario"], "fk_devolucion_resolutor"),
        fk(["id_movimiento_inventario"], ["t_movimiento_inventario.id_movimiento_inventario"], "fk_devolucion_movimiento"),
        sa.UniqueConstraint("id_devolucion", "id_venta", name="uq_devolucion_venta_pertenencia"),
        sa.UniqueConstraint("id_movimiento_inventario", name="uq_devolucion_movimiento"),
        sa.UniqueConstraint("clave_idempotencia", name="uq_devolucion_idempotencia"),
        check("ck_devolucion_tipo", "tipo IN ('DEVOLUCION','CANCELACION')"),
        check("ck_devolucion_estado", "estado IN ('SOLICITADA','APROBADA','RECHAZADA','PROCESADA')"),
        check("ck_devolucion_motivo", "length(trim(motivo)) > 0"),
        check("ck_devolucion_cancelacion", "tipo <> 'CANCELACION' OR id_movimiento_inventario IS NULL"),
        check("ck_devolucion_resolucion", "estado = 'SOLICITADA' OR (id_usuario_resolutor IS NOT NULL AND fecha_resolucion IS NOT NULL)"),
        check("ck_devolucion_procesamiento", "estado <> 'PROCESADA' OR fecha_procesamiento IS NOT NULL"),
        check("ck_devolucion_fecha_resolucion", "fecha_resolucion IS NULL OR fecha_resolucion >= created_at"),
        check("ck_devolucion_fecha_procesamiento", "fecha_procesamiento IS NULL OR (fecha_resolucion IS NOT NULL AND fecha_procesamiento >= fecha_resolucion)"),
    )
    index("ix_devolucion_venta_created_at", "t_devolucion", ["id_venta", "created_at"])
    index("ix_devolucion_estado_created_at", "t_devolucion", ["estado", "created_at"])
    index("uq_devolucion_cancelacion_activa", "t_devolucion", ["id_venta"], "tipo = 'CANCELACION' AND estado IN ('SOLICITADA','APROBADA','PROCESADA')", True)

    op.create_table("t_detalle_devolucion",
        pk("id_detalle_devolucion"), col("id_devolucion", sa.Integer()), col("id_venta", sa.Integer()),
        # UNIQUE existente (venta,variante) identifica una linea exacta;
        # no se modifica t_detalle_venta ni se duplica id_detalle_venta.
        col("id_variante_producto", sa.Integer()), col("cantidad", sa.Integer()),
        col("cantidad_reintegrar", sa.Integer(), default="0"),
        col("importe_restitucion", sa.Numeric(12, 2)), *timestamps(),
        fk(["id_devolucion", "id_venta"], ["t_devolucion.id_devolucion", "t_devolucion.id_venta"], "fk_detalle_devolucion_cabecera"),
        fk(["id_venta", "id_variante_producto"], ["t_detalle_venta.id_venta", "t_detalle_venta.id_variante_producto"], "fk_detalle_devolucion_linea_venta"),
        sa.UniqueConstraint("id_devolucion", "id_variante_producto", name="uq_detalle_devolucion_variante"),
        check("ck_detalle_devolucion_cantidad", "cantidad > 0"),
        check("ck_detalle_devolucion_reintegro", "cantidad_reintegrar >= 0 AND cantidad_reintegrar <= cantidad"),
        check("ck_detalle_devolucion_importe", "importe_restitucion >= 0"),
    )
    index("ix_detalle_devolucion_linea_venta", "t_detalle_devolucion", ["id_venta", "id_variante_producto"])

    op.create_table("t_reembolso",
        pk("id_reembolso"), col("id_venta", sa.Integer()), col("id_pago", sa.Integer()),
        col("id_devolucion", sa.Integer()), col("estado", sa.String(20), default="'PENDIENTE'"),
        col("monto", sa.Numeric(12, 2)), col("referencia_externa", sa.String(255), nullable=True),
        col("clave_idempotencia", postgresql.UUID(as_uuid=True)),
        col("id_usuario_responsable", sa.Integer(), nullable=True),
        col("fecha_aprobacion", sa.DateTime(), nullable=True), *timestamps(),
        fk(["id_pago", "id_venta"], ["t_pago.id_pago", "t_pago.id_venta"], "fk_reembolso_pago_venta"),
        fk(["id_devolucion", "id_venta"], ["t_devolucion.id_devolucion", "t_devolucion.id_venta"], "fk_reembolso_devolucion_venta"),
        fk(["id_usuario_responsable"], ["t_usuario.id_usuario"], "fk_reembolso_responsable"),
        sa.UniqueConstraint("clave_idempotencia", name="uq_reembolso_idempotencia"),
        sa.UniqueConstraint("id_pago", "referencia_externa", name="uq_reembolso_referencia"),
        check("ck_reembolso_estado", "estado IN ('PENDIENTE','APROBADO','RECHAZADO')"),
        check("ck_reembolso_monto", "monto > 0"),
        check("ck_reembolso_referencia", "referencia_externa IS NULL OR length(trim(referencia_externa)) > 0"),
        check("ck_reembolso_aprobacion", "estado <> 'APROBADO' OR fecha_aprobacion IS NOT NULL"),
    )
    index("ix_reembolso_pago_estado", "t_reembolso", ["id_pago", "estado"])
    index("ix_reembolso_devolucion_created_at", "t_reembolso", ["id_devolucion", "created_at"])
    index("uq_reembolso_devolucion_pendiente", "t_reembolso", ["id_devolucion"], "estado = 'PENDIENTE'", True)


def downgrade() -> None:
    """Revertir solo si no se pierde informacion comercial del Ciclo 3."""
    # Evitar una insercion/cambio entre la comprobacion y los DROP. Alembic
    # ejecuta el DDL PostgreSQL en una transaccion; conservar estos bloqueos
    # hasta su fin. No se elimina ninguna tabla anterior al Ciclo 3.
    op.execute("""LOCK TABLE t_venta, t_movimiento_inventario, t_pago,
        t_devolucion, t_detalle_devolucion, t_reembolso IN ACCESS EXCLUSIVE MODE""")
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM t_pago)
           OR EXISTS (SELECT 1 FROM t_devolucion)
           OR EXISTS (SELECT 1 FROM t_detalle_devolucion)
           OR EXISTS (SELECT 1 FROM t_reembolso) THEN
            RAISE EXCEPTION 'Downgrade bloqueado: existen pagos, devoluciones o reembolsos del Ciclo 3';
        END IF;
        IF EXISTS (SELECT 1 FROM t_venta WHERE id_empleado IS NULL)
           OR EXISTS (SELECT 1 FROM t_movimiento_inventario WHERE id_empleado_sucursal IS NULL) THEN
            RAISE EXCEPTION 'Downgrade bloqueado: existen responsables NULL incompatibles con Ciclo 2';
        END IF;
        IF EXISTS (SELECT 1 FROM t_venta WHERE
            canal IS DISTINCT FROM 'PRESENCIAL'
            OR moneda IS DISTINCT FROM 'BOB'
            OR id_carrito IS NOT NULL
            OR fecha_expiracion_pago IS NOT NULL
            OR stock_comprometido IS DISTINCT FROM false
            OR (fecha_completada IS NOT NULL AND
                (estado <> 'COMPLETADA' OR fecha_completada IS DISTINCT FROM fecha_venta))) THEN
            RAISE EXCEPTION 'Downgrade bloqueado: columnas de venta contienen informacion del Ciclo 3 no reconstruible';
        END IF;
    END $$""")
    # Solo se descartan valores compatibles/reconstruibles: PRESENCIAL, BOB,
    # false, NULL y fecha_completada = fecha_venta en COMPLETADA (backfill).
    for table in ("t_reembolso", "t_detalle_devolucion", "t_devolucion", "t_pago"):
        op.drop_table(table)
    op.execute("DROP TRIGGER tr_ciclo3_venta_canal ON t_venta")
    op.execute("DROP TRIGGER tr_ciclo3_movimiento_digital ON t_movimiento_inventario")
    op.execute("DROP FUNCTION fn_ciclo3_venta_canal()")
    op.execute("DROP FUNCTION fn_ciclo3_movimiento_digital()")
    op.drop_constraint("ck_movimiento_responsable_automatico", "t_movimiento_inventario", type_="check")
    op.alter_column("t_movimiento_inventario", "id_empleado_sucursal", existing_type=sa.Integer(), nullable=False)
    op.drop_index("ix_venta_expiracion_comprometida", table_name="t_venta")
    op.drop_index("ix_venta_fecha_completada", table_name="t_venta")
    for name in VENTA_CHECKS:
        op.drop_constraint(name, "t_venta", type_="check")
    op.drop_constraint("fk_venta_carrito", "t_venta", type_="foreignkey")
    op.drop_constraint("uq_venta_carrito", "t_venta", type_="unique")
    for name in ("stock_comprometido", "fecha_expiracion_pago", "fecha_completada", "id_carrito", "moneda", "canal"):
        op.drop_column("t_venta", name)
    op.alter_column("t_venta", "id_empleado", existing_type=sa.Integer(), nullable=False)
