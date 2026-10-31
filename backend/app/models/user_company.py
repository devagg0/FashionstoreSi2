from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UserCompany(Base):
    __tablename__ = "t_usuario_empresa"
    __table_args__ = (
        CheckConstraint(
            "estado IN ('INVITADO','ACTIVO','SUSPENDIDO','RETIRADO')",
            name="ck_usuario_empresa_estado",
        ),
        Index("ix_usuario_empresa_usuario_estado", "id_usuario", "estado"),
        Index("ix_usuario_empresa_empresa_rol_estado", "id_empresa", "id_rol", "estado"),
        Index(
            "uq_usuario_empresa_propietario",
            "id_empresa",
            unique=True,
            postgresql_where=text("es_propietario"),
        ),
    )

    id_empresa: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("t_empresa.id_empresa", name="fk_usuario_empresa_empresa", ondelete="CASCADE"),
        primary_key=True,
    )
    id_usuario: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("t_usuario.id_usuario", name="fk_usuario_empresa_usuario", ondelete="RESTRICT"),
        primary_key=True,
    )
    id_rol: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("t_rol.id_rol", name="fk_usuario_empresa_rol", ondelete="RESTRICT"),
        nullable=False,
    )
    estado: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'ACTIVO'"))
    es_propietario: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
