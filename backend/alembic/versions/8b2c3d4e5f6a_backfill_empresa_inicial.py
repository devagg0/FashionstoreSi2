"""backfill de empresa inicial y membresias

Revision ID: 8b2c3d4e5f6a
Revises: 7a1b2c3d4e5f
Create Date: 2026-10-29

"""

from alembic import op
import sqlalchemy as sa


revision = "8b2c3d4e5f6a"
down_revision = "7a1b2c3d4e5f"
branch_labels = None
depends_on = None


INITIAL_COMPANY_CODE = "fashionstore-inicial"
INITIAL_PLAN_CODE = "LEGACY_FULL"
INITIAL_FEATURE_CODE = "LEGACY_FULL_ACCESS"


# Padres antes que hijos. El valor es el mismo para toda la base heredada,
# pero conservar el orden hace explicita la dependencia del backfill.
BACKFILL_ORDER = (
    "t_cliente",
    "t_empleado",
    "t_proveedor",
    "t_sucursal",
    "t_categoria",
    "t_talla",
    "t_color",
    "t_temporada",
    "t_coleccion",
    "t_empleado_sucursal",
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


def _scalar(bind, statement: str, **params):
    return bind.execute(sa.text(statement), params).scalar_one()


def upgrade() -> None:
    """Asigna todos los datos heredados a un tenant inicial sin borrar filas."""
    bind = op.get_bind()

    counts_before = {
        table: _scalar(bind, f'SELECT count(*) FROM "{table}"')
        for table in BACKFILL_ORDER
    }
    for table in BACKFILL_ORDER:
        already_assigned = _scalar(
            bind,
            f'SELECT count(*) FROM "{table}" WHERE empresa_id IS NOT NULL',
        )
        if already_assigned:
            raise RuntimeError(
                f"Backfill inicial rechazado: {table} ya contiene "
                f"{already_assigned} filas asignadas a una empresa"
            )

    company_id = _scalar(
        bind,
        """
        INSERT INTO t_empresa (codigo, nombre, estado)
        VALUES (:codigo, 'FashionStore Inicial', 'ACTIVA')
        RETURNING id_empresa
        """,
        codigo=INITIAL_COMPANY_CODE,
    )
    plan_id = _scalar(
        bind,
        """
        INSERT INTO t_plan_saas
            (codigo, nombre, descripcion, precio, moneda, periodo_meses, estado)
        VALUES
            (:codigo, 'Plan heredado completo',
             'Compatibilidad con CU01-CU30 durante la migracion multitenant',
             0, 'BOB', 1200, true)
        RETURNING id_plan_saas
        """,
        codigo=INITIAL_PLAN_CODE,
    )
    feature_id = _scalar(
        bind,
        """
        INSERT INTO t_funcionalidad_saas
            (codigo, nombre, descripcion, estado)
        VALUES
            (:codigo, 'Acceso heredado completo',
             'Habilita el comportamiento existente de CU01-CU30', true)
        RETURNING id_funcionalidad_saas
        """,
        codigo=INITIAL_FEATURE_CODE,
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO t_plan_funcionalidad
                (id_plan_saas, id_funcionalidad_saas, habilitada, limite)
            VALUES (:plan_id, :feature_id, true, NULL)
            """
        ),
        {"plan_id": plan_id, "feature_id": feature_id},
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO t_suscripcion
                (id_empresa, id_plan_saas, estado, fecha_inicio,
                 fecha_fin_periodo, renovacion_automatica, proveedor)
            VALUES
                (:company_id, :plan_id, 'ACTIVA', now(),
                 now() + interval '100 years', false, 'MANUAL')
            """
        ),
        {"company_id": company_id, "plan_id": plan_id},
    )

    # Rol global reservado; ningun usuario existente se eleva automaticamente.
    bind.execute(
        sa.text(
            """
            INSERT INTO t_rol (nombre, descripcion, estado)
            VALUES ('SUPERADMIN', 'Administrador global de la plataforma SaaS', true)
            ON CONFLICT (nombre) DO NOTHING
            """
        )
    )

    # Se conserva el rol actual en la membresia. El primer ADMINISTRADOR queda
    # como propietario; si no existe, no se inventan privilegios.
    bind.execute(
        sa.text(
            """
            WITH propietario AS (
                SELECT min(u.id_usuario) AS id_usuario
                FROM t_usuario u
                JOIN t_rol r ON r.id_rol = u.id_rol
                WHERE upper(r.nombre) = 'ADMINISTRADOR'
            )
            INSERT INTO t_usuario_empresa
                (id_empresa, id_usuario, id_rol, estado, es_propietario)
            SELECT
                :company_id,
                u.id_usuario,
                u.id_rol,
                'ACTIVO',
                u.id_usuario = (SELECT id_usuario FROM propietario)
            FROM t_usuario u
            JOIN t_rol r ON r.id_rol = u.id_rol
            WHERE upper(r.nombre) <> 'SUPERADMIN'
            """
        ),
        {"company_id": company_id},
    )

    for table in BACKFILL_ORDER:
        bind.execute(
            sa.text(f'UPDATE "{table}" SET empresa_id = :company_id'),
            {"company_id": company_id},
        )

    for table, count_before in counts_before.items():
        count_after = _scalar(bind, f'SELECT count(*) FROM "{table}"')
        missing = _scalar(
            bind,
            f'SELECT count(*) FROM "{table}" '
            "WHERE empresa_id IS NULL OR empresa_id <> :company_id",
            company_id=company_id,
        )
        if count_after != count_before or missing != 0:
            raise RuntimeError(
                f"Backfill multitenant inconsistente en {table}: "
                f"antes={count_before}, despues={count_after}, sin_empresa={missing}"
            )

    expected_memberships = _scalar(
        bind,
        """
        SELECT count(*)
        FROM t_usuario u
        JOIN t_rol r ON r.id_rol = u.id_rol
        WHERE upper(r.nombre) <> 'SUPERADMIN'
        """,
    )
    actual_memberships = _scalar(
        bind,
        """
        SELECT count(*) FROM t_usuario_empresa WHERE id_empresa = :company_id
        """,
        company_id=company_id,
    )
    if actual_memberships != expected_memberships:
        raise RuntimeError(
            "Backfill de membresias incompleto: "
            f"esperadas={expected_memberships}, creadas={actual_memberships}"
        )


def downgrade() -> None:
    bind = op.get_bind()
    company_id = bind.execute(
        sa.text("SELECT id_empresa FROM t_empresa WHERE codigo = :codigo"),
        {"codigo": INITIAL_COMPANY_CODE},
    ).scalar_one_or_none()

    if company_id is not None:
        for table in reversed(BACKFILL_ORDER):
            bind.execute(
                sa.text(
                    f'UPDATE "{table}" SET empresa_id = NULL '
                    "WHERE empresa_id = :company_id"
                ),
                {"company_id": company_id},
            )
        bind.execute(
            sa.text("DELETE FROM t_usuario_empresa WHERE id_empresa = :company_id"),
            {"company_id": company_id},
        )
        bind.execute(
            sa.text("DELETE FROM t_suscripcion WHERE id_empresa = :company_id"),
            {"company_id": company_id},
        )
        bind.execute(
            sa.text("DELETE FROM t_empresa WHERE id_empresa = :company_id"),
            {"company_id": company_id},
        )

    bind.execute(
        sa.text(
            """
            DELETE FROM t_plan_funcionalidad
            WHERE id_plan_saas IN (
                SELECT id_plan_saas FROM t_plan_saas WHERE codigo = :plan_code
            )
              AND id_funcionalidad_saas IN (
                SELECT id_funcionalidad_saas
                FROM t_funcionalidad_saas WHERE codigo = :feature_code
            )
            """
        ),
        {"plan_code": INITIAL_PLAN_CODE, "feature_code": INITIAL_FEATURE_CODE},
    )
    bind.execute(
        sa.text("DELETE FROM t_funcionalidad_saas WHERE codigo = :codigo"),
        {"codigo": INITIAL_FEATURE_CODE},
    )
    bind.execute(
        sa.text("DELETE FROM t_plan_saas WHERE codigo = :codigo"),
        {"codigo": INITIAL_PLAN_CODE},
    )
    bind.execute(
        sa.text(
            """
            DELETE FROM t_rol r
            WHERE r.nombre = 'SUPERADMIN'
              AND NOT EXISTS (
                  SELECT 1 FROM t_usuario u WHERE u.id_rol = r.id_rol
              )
            """
        )
    )
