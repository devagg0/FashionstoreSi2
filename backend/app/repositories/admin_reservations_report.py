"""CU30: siete SELECT agregados, sin ejecutar el ciclo de reservas."""

from sqlalchemy import Date, Integer, case, cast, func, select
from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.models.category import Category
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.reservation import Reservation
from app.models.reservation_detail import ReservationDetail
from app.schemas.admin_reservations_report import STATES


class AdminReservationsReportRepository:
    def __init__(self, db: Session):
        self.db = db

    def exists(self, column, value):
        return self.db.scalar(select(column).where(column == value)) is not None

    def _period(self, column, period):
        if self.db.get_bind().dialect.name == "sqlite":
            local = func.datetime(column, "-4 hours")
            if period == "MES":
                return func.date(local, "start of month")
            if period == "SEMANA":
                # SQLite domingo=0; desplazar al lunes de la misma semana.
                offset = (cast(func.strftime("%w", local), Integer) + 6) % 7
                return func.date(local, func.printf("-%d days", offset))
            return func.date(local)
        local = func.timezone("America/La_Paz", func.timezone("UTC", column))
        unit = {"DIA": "day", "SEMANA": "week", "MES": "month"}[period]
        return cast(func.date_trunc(unit, local), Date)

    def report(self, filters, start_utc, end_utc, now_utc):
        date_column = {
            "CREACION": Reservation.created_at,
            "PROGRAMADA": Reservation.fecha_atencion_programada,
            "ATENCION": Reservation.fecha_atencion,
        }[filters.tipo_fecha]
        headers = select(
            Reservation.id_reserva, Reservation.id_cliente, Reservation.id_sucursal,
            Reservation.estado, Reservation.fecha_expiracion, date_column.label("fecha"),
        ).where(date_column.is_not(None))
        if start_utc is not None:
            headers = headers.where(date_column >= start_utc)
        if end_utc is not None:
            headers = headers.where(date_column < end_utc)
        if filters.id_sucursal is not None:
            headers = headers.where(Reservation.id_sucursal == filters.id_sucursal)
        headers = headers.cte("cabeceras_alcance")

        lines = select(
            ReservationDetail.id_reserva, ReservationDetail.cantidad,
            Product.id_producto, Product.nombre.label("nombre_producto"),
            Category.id_categoria, Category.nombre.label("nombre_categoria"),
        ).join(headers, headers.c.id_reserva == ReservationDetail.id_reserva).join(
            ProductVariant, ProductVariant.id_variante_producto == ReservationDetail.id_variante_producto,
        ).join(Product, Product.id_producto == ProductVariant.id_producto).join(
            Category, Category.id_categoria == Product.id_categoria,
        )
        for column, value in ((Product.id_producto, filters.id_producto),
                              (Category.id_categoria, filters.id_categoria)):
            if value is not None:
                lines = lines.where(column == value)
        lines = lines.cte("lineas_alcance")
        details = select(
            lines.c.id_reserva, func.sum(lines.c.cantidad).label("unidades"),
        ).group_by(lines.c.id_reserva).cte("detalles_por_reserva")
        filtered_lines = filters.id_producto is not None or filters.id_categoria is not None
        scope = select(
            headers, func.coalesce(details.c.unidades, 0).label("unidades"),
        ).join(details, details.c.id_reserva == headers.c.id_reserva,
               isouter=not filtered_lines).cte("reservas_alcance")
        warning = self.db.scalar(select(func.count()).select_from(scope).where(
            scope.c.estado.in_(("PENDIENTE", "CONFIRMADA")),
            scope.c.fecha_expiracion <= now_utc,
        ))
        statement = select(scope)
        if filters.estado is not None:
            statement = statement.where(scope.c.estado == filters.estado)
        base = statement.cte("reservas_filtradas")
        totals = (
            func.count().label("total_reservas"),
            func.coalesce(func.sum(base.c.unidades), 0).label("unidades_reservadas"),
        )
        clients = func.count(func.distinct(base.c.id_cliente)).label("clientes_con_reservas")
        state_keys = ("pendientes", "confirmadas", "atendidas", "canceladas", "expiradas")
        state_counts = [func.coalesce(func.sum(case((base.c.estado == state, 1), else_=0)), 0)
                        .label(f"reservas_{key}") for state, key in zip(STATES, state_keys)]
        kpis = self.db.execute(select(*totals, clients, *state_counts).select_from(base)).mappings().one()
        states = self.db.execute(select(base.c.estado, *totals).group_by(base.c.estado)).mappings().all()
        branches = self.db.execute(select(
            base.c.id_sucursal, Branch.nombre.label("nombre_sucursal"), *totals, clients,
        ).join(Branch, Branch.id_sucursal == base.c.id_sucursal)
            .group_by(base.c.id_sucursal, Branch.nombre).order_by(base.c.id_sucursal)).mappings().all()
        period = self._period(base.c.fecha, filters.periodo)
        series = self.db.execute(select(period.label("inicio_periodo"), *totals)
                                 .group_by(period).order_by(period)).mappings().all()
        rankings = []
        for id_column, name_column in ((lines.c.id_producto, lines.c.nombre_producto),
                                       (lines.c.id_categoria, lines.c.nombre_categoria)):
            units = func.sum(lines.c.cantidad)
            rankings.append(self.db.execute(select(
                id_column, name_column,
                func.count(func.distinct(lines.c.id_reserva)).label("total_reservas"),
                units.label("unidades_reservadas"),
            ).join(base, base.c.id_reserva == lines.c.id_reserva)
                .group_by(id_column, name_column).order_by(units.desc(), id_column)).mappings().all())
        return dict(kpis=kpis, por_estado=states, por_sucursal=branches,
                    serie_periodica=series, productos_mas_reservados=rankings[0],
                    categorias_mas_reservadas=rankings[1],
                    advertencias={"reservas_vencidas_sin_actualizar": warning})
