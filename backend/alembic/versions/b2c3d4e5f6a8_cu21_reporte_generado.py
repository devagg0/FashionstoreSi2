"""CU21: Crear tabla de reportes generados con IA

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f7
Create Date: 2026-11-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b2c3d4e5f6a8"
down_revision = "a1b2c3d4e5f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "t_reporte_generado",
        sa.Column("id_reporte", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("empresa_id", sa.Integer(), nullable=False),
        sa.Column("id_usuario", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(length=30), nullable=False),
        sa.Column("titulo", sa.String(length=150), nullable=False),
        sa.Column("consulta", sa.String(length=500), nullable=False),
        sa.Column("filtros_aplicados", sa.JSON(), nullable=False),
        sa.Column("resultado", sa.JSON(), nullable=False),
        sa.Column("creado_en", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["empresa_id"], ["t_empresa.id_empresa"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["id_usuario"], ["t_usuario.id_usuario"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id_reporte"),
    )
    op.create_index("ix_t_reporte_generado_empresa_id", "t_reporte_generado", ["empresa_id"])
    op.create_index("ix_t_reporte_generado_id_usuario", "t_reporte_generado", ["id_usuario"])
    op.create_index("ix_t_reporte_generado_tipo", "t_reporte_generado", ["tipo"])
    op.create_index("ix_t_reporte_generado_creado_en", "t_reporte_generado", ["creado_en"])


def downgrade() -> None:
    op.drop_index("ix_t_reporte_generado_creado_en", table_name="t_reporte_generado")
    op.drop_index("ix_t_reporte_generado_tipo", table_name="t_reporte_generado")
    op.drop_index("ix_t_reporte_generado_id_usuario", table_name="t_reporte_generado")
    op.drop_index("ix_t_reporte_generado_empresa_id", table_name="t_reporte_generado")
    op.drop_table("t_reporte_generado")

