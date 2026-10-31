"""Infraestructura ORM compartida por las entidades pertenecientes a empresa."""

from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column


class TenantMixin:
    """Añade la empresa obligatoria sin cambiar las PK históricas."""

    empresa_id: Mapped[int] = mapped_column(Integer, nullable=False)
