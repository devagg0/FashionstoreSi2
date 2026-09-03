from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EmployeeBranch(Base):
    __tablename__ = "t_empleado_sucursal"
    __table_args__ = (UniqueConstraint("id_empleado", "id_sucursal"),)

    id_empleado_sucursal: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    id_empleado: Mapped[int] = mapped_column(
        Integer, ForeignKey("t_empleado.id_empleado"), nullable=False
    )
    id_sucursal: Mapped[int] = mapped_column(
        Integer, ForeignKey("t_sucursal.id_sucursal"), nullable=False
    )
    fecha_asignacion: Mapped[date] = mapped_column(
        Date, nullable=False, server_default=func.current_date()
    )
    estado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
