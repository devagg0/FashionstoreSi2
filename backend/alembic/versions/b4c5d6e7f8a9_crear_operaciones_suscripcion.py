"""crear operaciones suscripcion saas

Revision ID: b4c5d6e7f8a9
Revises: 9c3d4e5f6a7b
Create Date: 2026-10-31

"""

from alembic import op
import sqlalchemy as sa


revision = "b4c5d6e7f8a9"
down_revision = "9c3d4e5f6a7b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "t_operacion_suscripcion",
        sa.Column("id_operacion", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id_empresa", sa.Integer(), nullable=False),
        sa.Column("id_plan_saas", sa.Integer(), nullable=False),
        sa.Column("id_suscripcion", sa.Integer(), nullable=True),
        sa.Column("tipo_operacion", sa.String(length=30), nullable=False),
        sa.Column("estado", sa.String(length=20), server_default=sa.text("'PENDIENTE'"), nullable=False),
        sa.Column("metodo_pago", sa.String(length=20), server_default=sa.text("'TARJETA'"), nullable=False),
        sa.Column("monto", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("moneda", sa.String(length=3), server_default=sa.text("'BOB'"), nullable=False),
        sa.Column("proveedor", sa.String(length=20), server_default=sa.text("'STRIPE'"), nullable=False),
        sa.Column("id_sesion_checkout", sa.String(length=255), nullable=True),
        sa.Column("id_pago_externo", sa.String(length=255), nullable=True),
        sa.Column("fecha_ejecucion_programada", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id_operacion", name="pk_operacion_suscripcion"),
        sa.ForeignKeyConstraint(
            ["id_empresa"],
            ["t_empresa.id_empresa"],
            name="fk_operacion_suscripcion_empresa",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["id_plan_saas"],
            ["t_plan_saas.id_plan_saas"],
            name="fk_operacion_suscripcion_plan",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["id_suscripcion"],
            ["t_suscripcion.id_suscripcion"],
            name="fk_operacion_suscripcion_sub",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "tipo_operacion IN ('CONTRATACION','RENOVACION','CAMBIO_PLAN')",
            name="ck_operacion_suscripcion_tipo",
        ),
        sa.CheckConstraint(
            "estado IN ('PENDIENTE','COMPLETADA','FALLIDA','CANCELADA','PROGRAMADA')",
            name="ck_operacion_suscripcion_estado",
        ),
        sa.CheckConstraint(
            "metodo_pago IN ('TARJETA','QR')",
            name="ck_operacion_suscripcion_metodo",
        ),
        sa.UniqueConstraint("id_sesion_checkout", name="uq_operacion_suscripcion_sesion"),
    )
    op.create_index(
        "ix_operacion_suscripcion_empresa",
        "t_operacion_suscripcion",
        ["id_empresa", "created_at"],
    )
    op.create_index(
        "ix_operacion_suscripcion_sesion",
        "t_operacion_suscripcion",
        ["id_sesion_checkout"],
    )


def downgrade() -> None:
    op.drop_index("ix_operacion_suscripcion_sesion", table_name="t_operacion_suscripcion")
    op.drop_index("ix_operacion_suscripcion_empresa", table_name="t_operacion_suscripcion")
    op.drop_table("t_operacion_suscripcion")

