"""agregar fecha de atencion programada a reserva

Revision ID: 9d4a7c6e2b11
Revises: c2b73a1d9e84
Create Date: 2026-09-12 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9d4a7c6e2b11"
down_revision: Union[str, Sequence[str], None] = "c2b73a1d9e84"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Agrega la cita elegida por el cliente sin reutilizar fecha_atencion."""
    op.add_column(
        "t_reserva",
        sa.Column(
            "fecha_atencion_programada",
            sa.DateTime(),
            nullable=True,
            comment="Fecha y hora elegida por el cliente para acudir a la sucursal",
        ),
    )
    # Los registros previos no guardaban la cita. Se conserva su vencimiento
    # historico y se deriva una cita tecnica usando la tolerancia inicial de 60 min.
    op.execute(
        "UPDATE t_reserva "
        "SET fecha_atencion_programada = fecha_expiracion - INTERVAL '60 minutes' "
        "WHERE fecha_atencion_programada IS NULL"
    )
    op.alter_column(
        "t_reserva",
        "fecha_atencion_programada",
        existing_type=sa.DateTime(),
        nullable=False,
    )
    op.create_check_constraint(
        "ck_reserva_expiracion_programada",
        "t_reserva",
        "fecha_expiracion > fecha_atencion_programada",
    )


def downgrade() -> None:
    """Retira solamente la fecha programada y su restriccion."""
    op.drop_constraint(
        "ck_reserva_expiracion_programada", "t_reserva", type_="check"
    )
    op.drop_column("t_reserva", "fecha_atencion_programada")
