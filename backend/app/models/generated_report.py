"""Modelo SQLAlchemy para reportes generados con IA (CU21)."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.tenant import TenantMixin


class GeneratedReport(TenantMixin, Base):
    """Almacena el resultado y metadatos de los reportes empresariales generados."""

    __tablename__ = "t_reporte_generado"

    id_reporte: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    empresa_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("t_empresa.id_empresa"), nullable=False, index=True
    )
    id_usuario: Mapped[int] = mapped_column(
        Integer, ForeignKey("t_usuario.id_usuario"), nullable=False, index=True
    )
    tipo: Mapped[str] = mapped_column(
        String(30), nullable=False, index=True
    )
    titulo: Mapped[str] = mapped_column(
        String(150), nullable=False
    )
    consulta: Mapped[str] = mapped_column(
        String(500), nullable=False
    )
    filtros_aplicados: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict
    )
    resultado: Mapped[dict] = mapped_column(
        JSON, nullable=False
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), index=True
    )

    usuario = relationship("User", foreign_keys=[id_usuario])

