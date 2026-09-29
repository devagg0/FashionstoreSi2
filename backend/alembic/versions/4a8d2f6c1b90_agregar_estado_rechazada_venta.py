"""agregar estado rechazada a venta

Revision ID: 4a8d2f6c1b90
Revises: e3a91f6b8c24
Create Date: 2026-09-27
"""

from alembic import op


revision = "4a8d2f6c1b90"
down_revision = "e3a91f6b8c24"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_venta_estado", "t_venta", type_="check")
    op.create_check_constraint(
        "ck_venta_estado",
        "t_venta",
        "estado IN ('PENDIENTE', 'COMPLETADA', 'ANULADA', 'RECHAZADA')",
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM t_venta WHERE estado = 'RECHAZADA') THEN
                RAISE EXCEPTION
                    'No se puede revertir: existen ventas con estado RECHAZADA';
            END IF;
        END
        $$;
        """
    )
    op.drop_constraint("ck_venta_estado", "t_venta", type_="check")
    op.create_check_constraint(
        "ck_venta_estado",
        "t_venta",
        "estado IN ('PENDIENTE', 'COMPLETADA', 'ANULADA')",
    )
