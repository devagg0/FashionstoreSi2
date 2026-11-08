"""CU16: Evaluar solicitud, modalidad entrega, recepcion e inspeccion fisica

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-11-07
"""
from alembic import op
import sqlalchemy as sa

revision = "e7f8a9b0c1d2"
down_revision = "d6e7f8a9b0c1"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("t_devolucion", sa.Column("motivo_rechazo", sa.String(500), nullable=True))
    op.add_column("t_devolucion", sa.Column("fecha_evaluacion_inicial", sa.DateTime(), nullable=True))
    op.add_column("t_devolucion", sa.Column("id_usuario_evaluador", sa.Integer(), nullable=True))
    op.add_column("t_devolucion", sa.Column("fecha_seleccion_modalidad", sa.DateTime(), nullable=True))
    op.add_column("t_devolucion", sa.Column("fecha_recepcion", sa.DateTime(), nullable=True))
    op.add_column("t_devolucion", sa.Column("id_usuario_receptor", sa.Integer(), nullable=True))
    op.add_column("t_devolucion", sa.Column("estado_fisico", sa.String(50), nullable=True))
    op.add_column("t_devolucion", sa.Column("etiquetas_intactas", sa.Boolean(), nullable=True))
    op.add_column("t_devolucion", sa.Column("correspondencia_compra", sa.Boolean(), nullable=True))
    op.add_column("t_devolucion", sa.Column("observaciones_inspeccion", sa.String(500), nullable=True))
    op.add_column("t_devolucion", sa.Column("fecha_inspeccion", sa.DateTime(), nullable=True))
    op.add_column("t_devolucion", sa.Column("id_usuario_inspector", sa.Integer(), nullable=True))

    op.create_foreign_key("fk_devolucion_evaluador", "t_devolucion", "t_usuario", ["id_usuario_evaluador"], ["id_usuario"], ondelete="RESTRICT")
    op.create_foreign_key("fk_devolucion_receptor", "t_devolucion", "t_usuario", ["id_usuario_receptor"], ["id_usuario"], ondelete="RESTRICT")
    op.create_foreign_key("fk_devolucion_inspector", "t_devolucion", "t_usuario", ["id_usuario_inspector"], ["id_usuario"], ondelete="RESTRICT")

    op.alter_column(
        "t_devolucion",
        "estado",
        existing_type=sa.String(20),
        type_=sa.String(30),
        existing_nullable=False,
    )

    op.drop_constraint("ck_devolucion_estado", "t_devolucion", type_="check")
    op.create_check_constraint(
        "ck_devolucion_estado",
        "t_devolucion",
        "estado IN ('SOLICITADA','ACEPTADA_INICIALMENTE','PENDIENTE_ENTREGA','RECIBIDA','APROBADA','RECHAZADA','PROCESADA')",
    )

    op.drop_constraint("ck_devolucion_resolucion", "t_devolucion", type_="check")
    op.create_check_constraint(
        "ck_devolucion_resolucion",
        "t_devolucion",
        "estado NOT IN ('APROBADA','RECHAZADA','PROCESADA') OR (id_usuario_resolutor IS NOT NULL AND fecha_resolucion IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_devolucion_resolucion", "t_devolucion", type_="check")
    op.create_check_constraint(
        "ck_devolucion_resolucion",
        "t_devolucion",
        "estado = 'SOLICITADA' OR (id_usuario_resolutor IS NOT NULL AND fecha_resolucion IS NOT NULL)",
    )
    op.drop_constraint("ck_devolucion_estado", "t_devolucion", type_="check")
    op.create_check_constraint(
        "ck_devolucion_estado",
        "t_devolucion",
        "estado IN ('SOLICITADA','APROBADA','RECHAZADA','PROCESADA')",
    )
    op.alter_column(
        "t_devolucion",
        "estado",
        existing_type=sa.String(30),
        type_=sa.String(20),
        existing_nullable=False,
    )
    op.drop_constraint("fk_devolucion_inspector", "t_devolucion", type_="foreignkey")
    op.drop_constraint("fk_devolucion_receptor", "t_devolucion", type_="foreignkey")
    op.drop_constraint("fk_devolucion_evaluador", "t_devolucion", type_="foreignkey")
    op.drop_column("t_devolucion", "id_usuario_inspector")
    op.drop_column("t_devolucion", "fecha_inspeccion")
    op.drop_column("t_devolucion", "observaciones_inspeccion")
    op.drop_column("t_devolucion", "correspondencia_compra")
    op.drop_column("t_devolucion", "etiquetas_intactas")
    op.drop_column("t_devolucion", "estado_fisico")
    op.drop_column("t_devolucion", "id_usuario_receptor")
    op.drop_column("t_devolucion", "fecha_recepcion")
    op.drop_column("t_devolucion", "fecha_seleccion_modalidad")
    op.drop_column("t_devolucion", "id_usuario_evaluador")
    op.drop_column("t_devolucion", "fecha_evaluacion_inicial")
    op.drop_column("t_devolucion", "motivo_rechazo")

