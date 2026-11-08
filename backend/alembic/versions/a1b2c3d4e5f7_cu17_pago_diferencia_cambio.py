"""CU17: Pago de diferencia de cambio de prenda (online Stripe y presencial)

Revision ID: a1b2c3d4e5f7
Revises: f8a9b0c1d2e3
Create Date: 2026-11-07
"""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f7"
down_revision = "f8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("t_devolucion", sa.Column("estado_pago_adicional", sa.String(20), nullable=True))
    op.add_column("t_devolucion", sa.Column("stripe_session_id", sa.String(255), nullable=True))
    op.create_check_constraint(
        "ck_devolucion_estado_pago_adicional",
        "t_devolucion",
        "estado_pago_adicional IS NULL OR estado_pago_adicional IN ('PENDIENTE', 'CONFIRMADO', 'NO_APLICA')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_devolucion_estado_pago_adicional", "t_devolucion", type_="check")
    op.drop_column("t_devolucion", "stripe_session_id")
    op.drop_column("t_devolucion", "estado_pago_adicional")

