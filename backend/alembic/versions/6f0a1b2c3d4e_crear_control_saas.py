"""crear plano de control SaaS

Revision ID: 6f0a1b2c3d4e
Revises: 4a8d2f6c1b90
Create Date: 2026-10-29

"""

from alembic import op
import sqlalchemy as sa


revision = "6f0a1b2c3d4e"
down_revision = "4a8d2f6c1b90"
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    """Crea exclusivamente el plano de control SaaS, sin datos ni RLS."""
    op.create_table(
        "t_empresa",
        sa.Column("id_empresa", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("codigo", sa.String(length=63), nullable=False),
        sa.Column("nombre", sa.String(length=150), nullable=False),
        sa.Column("nit", sa.String(length=30), nullable=True),
        sa.Column(
            "zona_horaria",
            sa.String(length=50),
            server_default=sa.text("'America/La_Paz'"),
            nullable=False,
        ),
        sa.Column(
            "estado",
            sa.String(length=20),
            server_default=sa.text("'ACTIVA'"),
            nullable=False,
        ),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id_empresa", name="pk_empresa"),
        sa.UniqueConstraint("codigo", name="uq_empresa_codigo"),
        sa.CheckConstraint(
            "codigo = lower(codigo) AND "
            "codigo ~ '^[a-z0-9]+(-[a-z0-9]+)*$'",
            name="ck_empresa_codigo",
        ),
        sa.CheckConstraint(
            "length(trim(nombre)) > 0",
            name="ck_empresa_nombre",
        ),
        sa.CheckConstraint(
            "estado IN ('ACTIVA','SUSPENDIDA','CANCELADA')",
            name="ck_empresa_estado",
        ),
    )
    op.create_index("ix_empresa_estado", "t_empresa", ["estado"])
    op.create_index(
        "uq_empresa_nit",
        "t_empresa",
        ["nit"],
        unique=True,
        postgresql_where=sa.text("nit IS NOT NULL"),
    )

    op.create_table(
        "t_plan_saas",
        sa.Column("id_plan_saas", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("codigo", sa.String(length=50), nullable=False),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("descripcion", sa.String(length=300), nullable=True),
        sa.Column("precio", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "moneda",
            sa.String(length=3),
            server_default=sa.text("'BOB'"),
            nullable=False,
        ),
        sa.Column(
            "periodo_meses",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "estado",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id_plan_saas", name="pk_plan_saas"),
        sa.UniqueConstraint("codigo", name="uq_plan_saas_codigo"),
        sa.CheckConstraint("length(trim(codigo)) > 0", name="ck_plan_saas_codigo"),
        sa.CheckConstraint("length(trim(nombre)) > 0", name="ck_plan_saas_nombre"),
        sa.CheckConstraint("precio >= 0", name="ck_plan_saas_precio"),
        sa.CheckConstraint("moneda = 'BOB'", name="ck_plan_saas_moneda"),
        sa.CheckConstraint("periodo_meses > 0", name="ck_plan_saas_periodo"),
    )
    op.create_index("ix_plan_saas_estado_precio", "t_plan_saas", ["estado", "precio"])

    op.create_table(
        "t_funcionalidad_saas",
        sa.Column(
            "id_funcionalidad_saas", sa.Integer(), autoincrement=True, nullable=False
        ),
        sa.Column("codigo", sa.String(length=80), nullable=False),
        sa.Column("nombre", sa.String(length=120), nullable=False),
        sa.Column("descripcion", sa.String(length=300), nullable=True),
        sa.Column(
            "estado",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        *_timestamps(),
        sa.PrimaryKeyConstraint(
            "id_funcionalidad_saas", name="pk_funcionalidad_saas"
        ),
        sa.UniqueConstraint("codigo", name="uq_funcionalidad_saas_codigo"),
        sa.CheckConstraint(
            "length(trim(codigo)) > 0", name="ck_funcionalidad_saas_codigo"
        ),
        sa.CheckConstraint(
            "length(trim(nombre)) > 0", name="ck_funcionalidad_saas_nombre"
        ),
    )

    op.create_table(
        "t_usuario_empresa",
        sa.Column("id_empresa", sa.Integer(), nullable=False),
        sa.Column("id_usuario", sa.Integer(), nullable=False),
        sa.Column("id_rol", sa.Integer(), nullable=False),
        sa.Column(
            "estado",
            sa.String(length=20),
            server_default=sa.text("'ACTIVO'"),
            nullable=False,
        ),
        sa.Column(
            "es_propietario",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["id_empresa"],
            ["t_empresa.id_empresa"],
            name="fk_usuario_empresa_empresa",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["id_usuario"],
            ["t_usuario.id_usuario"],
            name="fk_usuario_empresa_usuario",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["id_rol"],
            ["t_rol.id_rol"],
            name="fk_usuario_empresa_rol",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "id_empresa", "id_usuario", name="pk_usuario_empresa"
        ),
        sa.CheckConstraint(
            "estado IN ('INVITADO','ACTIVO','SUSPENDIDO','RETIRADO')",
            name="ck_usuario_empresa_estado",
        ),
    )
    op.create_index(
        "ix_usuario_empresa_usuario_estado",
        "t_usuario_empresa",
        ["id_usuario", "estado"],
    )
    op.create_index(
        "ix_usuario_empresa_empresa_rol_estado",
        "t_usuario_empresa",
        ["id_empresa", "id_rol", "estado"],
    )
    op.create_index(
        "uq_usuario_empresa_propietario",
        "t_usuario_empresa",
        ["id_empresa"],
        unique=True,
        postgresql_where=sa.text("es_propietario"),
    )

    op.create_table(
        "t_plan_funcionalidad",
        sa.Column("id_plan_saas", sa.Integer(), nullable=False),
        sa.Column("id_funcionalidad_saas", sa.Integer(), nullable=False),
        sa.Column(
            "habilitada",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("limite", sa.Integer(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["id_plan_saas"],
            ["t_plan_saas.id_plan_saas"],
            name="fk_plan_funcionalidad_plan",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["id_funcionalidad_saas"],
            ["t_funcionalidad_saas.id_funcionalidad_saas"],
            name="fk_plan_funcionalidad_funcionalidad",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "id_plan_saas",
            "id_funcionalidad_saas",
            name="pk_plan_funcionalidad",
        ),
        sa.CheckConstraint(
            "limite IS NULL OR limite >= 0",
            name="ck_plan_funcionalidad_limite",
        ),
    )

    op.create_table(
        "t_suscripcion",
        sa.Column("id_suscripcion", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id_empresa", sa.Integer(), nullable=False),
        sa.Column("id_plan_saas", sa.Integer(), nullable=False),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("fecha_inicio", sa.DateTime(), nullable=False),
        sa.Column("fecha_fin_periodo", sa.DateTime(), nullable=False),
        sa.Column("fecha_fin_prueba", sa.DateTime(), nullable=True),
        sa.Column("fecha_cancelacion", sa.DateTime(), nullable=True),
        sa.Column(
            "renovacion_automatica",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("proveedor", sa.String(length=20), nullable=True),
        sa.Column("referencia_externa", sa.String(length=255), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["id_empresa"],
            ["t_empresa.id_empresa"],
            name="fk_suscripcion_empresa",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["id_plan_saas"],
            ["t_plan_saas.id_plan_saas"],
            name="fk_suscripcion_plan",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id_suscripcion", name="pk_suscripcion"),
        sa.CheckConstraint(
            "estado IN ('PRUEBA','ACTIVA','SUSPENDIDA','CANCELADA','EXPIRADA')",
            name="ck_suscripcion_estado",
        ),
        sa.CheckConstraint(
            "fecha_fin_periodo > fecha_inicio",
            name="ck_suscripcion_periodo",
        ),
        sa.CheckConstraint(
            "fecha_fin_prueba IS NULL OR fecha_fin_prueba >= fecha_inicio",
            name="ck_suscripcion_prueba",
        ),
        sa.CheckConstraint(
            "estado <> 'CANCELADA' OR fecha_cancelacion IS NOT NULL",
            name="ck_suscripcion_cancelacion",
        ),
        sa.CheckConstraint(
            "proveedor IS NULL OR proveedor IN ('MANUAL','STRIPE')",
            name="ck_suscripcion_proveedor",
        ),
        sa.CheckConstraint(
            "referencia_externa IS NULL OR proveedor IS NOT NULL",
            name="ck_suscripcion_referencia",
        ),
    )
    op.create_index(
        "ix_suscripcion_empresa_created_at",
        "t_suscripcion",
        ["id_empresa", "created_at"],
    )
    op.create_index(
        "ix_suscripcion_estado_fin_periodo",
        "t_suscripcion",
        ["estado", "fecha_fin_periodo"],
    )
    op.create_index(
        "uq_suscripcion_referencia_externa",
        "t_suscripcion",
        ["proveedor", "referencia_externa"],
        unique=True,
        postgresql_where=sa.text("referencia_externa IS NOT NULL"),
    )
    op.create_index(
        "uq_suscripcion_empresa_vigente",
        "t_suscripcion",
        ["id_empresa"],
        unique=True,
        postgresql_where=sa.text("estado IN ('PRUEBA','ACTIVA','SUSPENDIDA')"),
    )


def downgrade() -> None:
    op.drop_table("t_suscripcion")
    op.drop_table("t_plan_funcionalidad")
    op.drop_table("t_usuario_empresa")
    op.drop_table("t_funcionalidad_saas")
    op.drop_table("t_plan_saas")
    op.drop_table("t_empresa")
