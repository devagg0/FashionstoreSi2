"""crear recuperacion contrasena

Revision ID: 7b3c2d1e9f40
Revises: 0c173d413ca6
Create Date: 2026-09-04 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7b3c2d1e9f40"
down_revision: Union[str, Sequence[str], None] = "0c173d413ca6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Crea la tabla de códigos temporales de recuperación."""
    op.create_table(
        "t_recuperacion_contrasena",
        sa.Column("id_recuperacion", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id_usuario", sa.Integer(), nullable=False),
        sa.Column("codigo_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "intentos",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "usado",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("expira_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["id_usuario"],
            ["t_usuario.id_usuario"],
            name="fk_recuperacion_contrasena_usuario",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "id_recuperacion",
            name="pk_recuperacion_contrasena",
        ),
    )
    op.create_index(
        "ix_t_recuperacion_contrasena_id_usuario",
        "t_recuperacion_contrasena",
        ["id_usuario"],
        unique=False,
    )


def downgrade() -> None:
    """Elimina la tabla de recuperación de contraseña."""
    op.drop_index(
        "ix_t_recuperacion_contrasena_id_usuario",
        table_name="t_recuperacion_contrasena",
    )
    op.drop_table("t_recuperacion_contrasena")
