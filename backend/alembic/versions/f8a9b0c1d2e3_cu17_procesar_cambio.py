"""CU17: Procesar cambio de talla o producto

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-11-07
"""
from alembic import op
import sqlalchemy as sa

revision = "f8a9b0c1d2e3"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("t_devolucion", sa.Column("diferencia_definitiva", sa.Numeric(12, 2), nullable=True))
    op.add_column("t_devolucion", sa.Column("monto_adicional_cobrado", sa.Numeric(12, 2), nullable=True))
    op.add_column("t_devolucion", sa.Column("medio_pago_adicional", sa.String(20), nullable=True))
    op.add_column("t_devolucion", sa.Column("referencia_pago_adicional", sa.String(255), nullable=True))
    op.add_column("t_devolucion", sa.Column("fecha_entrega_reemplazo", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("t_devolucion", "fecha_entrega_reemplazo")
    op.drop_column("t_devolucion", "referencia_pago_adicional")
    op.drop_column("t_devolucion", "medio_pago_adicional")
    op.drop_column("t_devolucion", "monto_adicional_cobrado")
    op.drop_column("t_devolucion", "diferencia_definitiva")

