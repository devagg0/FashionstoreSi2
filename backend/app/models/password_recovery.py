"""Persistencia segura de solicitudes de recuperación de contraseña."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PasswordRecovery(Base):
    """Código temporal asociado a un usuario de FashionStore."""

    __tablename__ = "t_recuperacion_contrasena"

    id_recuperacion: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    id_usuario: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("t_usuario.id_usuario", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    codigo_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    intentos: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    usado: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    expira_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
