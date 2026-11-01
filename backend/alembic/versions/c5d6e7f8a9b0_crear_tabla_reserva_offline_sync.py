"""crear tabla reserva offline sync para idempotencia en PK08 CU10

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-11-01
"""

from alembic import op
import sqlalchemy as sa


revision = "c5d6e7f8a9b0"
down_revision = "b4c5d6e7f8a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "t_reserva_offline_sync",
        sa.Column("id_sync", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("empresa_id", sa.Integer(), nullable=False),
        sa.Column("uuid_reserva_offline", sa.String(length=64), nullable=False),
        sa.Column("id_reserva", sa.Integer(), nullable=True),
        sa.Column("codigo_reserva", sa.String(length=50), nullable=True),
        sa.Column("id_sucursal", sa.Integer(), nullable=False),
        sa.Column("id_cliente", sa.Integer(), nullable=False),
        sa.Column("id_usuario", sa.Integer(), nullable=False),
        sa.Column("estado_sincronizacion", sa.String(length=20), nullable=False),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("detalles_json", sa.Text(), nullable=True),
        sa.Column("fecha_reserva_offline", sa.DateTime(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["t_empresa.id_empresa"],
            name="fk_reserva_offline_sync_empresa",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["id_reserva"],
            ["t_reserva.id_reserva"],
            name="fk_reserva_offline_sync_reserva",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["id_sucursal"],
            ["t_sucursal.id_sucursal"],
            name="fk_reserva_offline_sync_sucursal",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["id_cliente"],
            ["t_cliente.id_cliente"],
            name="fk_reserva_offline_sync_cliente",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["id_usuario"],
            ["t_usuario.id_usuario"],
            name="fk_reserva_offline_sync_usuario",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id_sync", name="pk_t_reserva_offline_sync"),
        sa.UniqueConstraint(
            "empresa_id",
            "uuid_reserva_offline",
            name="uq_reserva_offline_empresa_uuid",
        ),
        sa.CheckConstraint(
            "estado_sincronizacion IN ('SINCRONIZADA', 'RECHAZADA', 'CONFLICTO')",
            name="ck_reserva_offline_estado",
        ),
    )
    op.create_index(
        "ix_reserva_offline_sync_uuid",
        "t_reserva_offline_sync",
        ["uuid_reserva_offline"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_reserva_offline_sync_uuid", table_name="t_reserva_offline_sync")
    op.drop_table("t_reserva_offline_sync")

