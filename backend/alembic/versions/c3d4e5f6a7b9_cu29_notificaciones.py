"""CU29: Crear tabla de notificaciones para reservas y compras

Revision ID: c3d4e5f6a7b9
Revises: b2c3d4e5f6a8
Create Date: 2026-11-09
"""
from alembic import op
import sqlalchemy as sa

revision = "c3d4e5f6a7b9"
down_revision = "b2c3d4e5f6a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "t_notificacion",
        sa.Column("id_notificacion", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("empresa_id", sa.Integer(), nullable=False),
        sa.Column("id_usuario", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(length=50), nullable=False),
        sa.Column("titulo", sa.String(length=150), nullable=False),
        sa.Column("mensaje", sa.String(length=500), nullable=False),
        sa.Column("referencia_origen", sa.String(length=50), nullable=True),
        sa.Column("referencia_id", sa.Integer(), nullable=True),
        sa.Column("codigo_referencia", sa.String(length=100), nullable=True),
        sa.Column("clave_idempotencia", sa.String(length=150), nullable=False),
        sa.Column("leido", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("fecha_lectura", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["empresa_id"], ["t_empresa.id_empresa"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["id_usuario"], ["t_usuario.id_usuario"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id_notificacion"),
        sa.UniqueConstraint("empresa_id", "clave_idempotencia", name="uq_notificacion_empresa_idempotencia"),
    )
    op.create_index("ix_t_notificacion_empresa_id", "t_notificacion", ["empresa_id"])
    op.create_index("ix_t_notificacion_id_usuario", "t_notificacion", ["id_usuario"])
    op.create_index("ix_t_notificacion_tipo", "t_notificacion", ["tipo"])
    op.create_index("ix_t_notificacion_clave_idempotencia", "t_notificacion", ["clave_idempotencia"])
    op.create_index("ix_t_notificacion_leido", "t_notificacion", ["leido"])
    op.create_index("ix_t_notificacion_created_at", "t_notificacion", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_t_notificacion_created_at", table_name="t_notificacion")
    op.drop_index("ix_t_notificacion_leido", table_name="t_notificacion")
    op.drop_index("ix_t_notificacion_clave_idempotencia", table_name="t_notificacion")
    op.drop_index("ix_t_notificacion_tipo", table_name="t_notificacion")
    op.drop_index("ix_t_notificacion_id_usuario", table_name="t_notificacion")
    op.drop_index("ix_t_notificacion_empresa_id", table_name="t_notificacion")
    op.drop_table("t_notificacion")

