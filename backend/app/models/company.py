from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Company(Base):
    __tablename__ = "t_empresa"
    __table_args__ = (
        CheckConstraint(
            "codigo = lower(codigo) AND codigo ~ '^[a-z0-9]+(-[a-z0-9]+)*$'",
            name="ck_empresa_codigo",
        ),
        CheckConstraint("length(trim(nombre)) > 0", name="ck_empresa_nombre"),
        CheckConstraint(
            "estado IN ('ACTIVA','SUSPENDIDA','CANCELADA')",
            name="ck_empresa_estado",
        ),
        Index("ix_empresa_estado", "estado"),
        Index(
            "uq_empresa_nit",
            "nit",
            unique=True,
            postgresql_where=text("nit IS NOT NULL"),
        ),
    )

    id_empresa: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(63), nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    nit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    zona_horaria: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default=text("'America/La_Paz'")
    )
    estado: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'ACTIVA'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
