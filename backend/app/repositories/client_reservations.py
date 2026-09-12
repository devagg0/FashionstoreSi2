"""Persistencia de CU17; el servicio controla cada transaccion."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.models.branch_inventory import BranchInventory
from app.models.city import City
from app.models.client import Client
from app.models.color import Color
from app.models.product import Product
from app.models.product_image import ProductImage
from app.models.product_variant import ProductVariant
from app.models.reservation import Reservation
from app.models.reservation_detail import ReservationDetail
from app.models.size import Size


HOLDING_STATES = ("PENDIENTE", "CONFIRMADA")


class ClientReservationRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_client_by_user(self, user_id: int):
        return self.db.scalar(select(Client).where(Client.id_usuario == user_id))

    def get_branch(self, branch_id: int):
        return self.db.get(Branch, branch_id)

    def get_variant(self, variant_id: int):
        return self.db.execute(
            select(ProductVariant, Product)
            .join(Product, Product.id_producto == ProductVariant.id_producto)
            .where(ProductVariant.id_variante_producto == variant_id)
        ).one_or_none()

    def lock_inventories(self, branch_id: int, variant_ids: list[int]):
        if not variant_ids:
            return []
        return self.db.scalars(
            select(BranchInventory)
            .where(
                BranchInventory.id_sucursal == branch_id,
                BranchInventory.id_variante_producto.in_(sorted(variant_ids)),
            )
            .order_by(BranchInventory.id_variante_producto)
            .with_for_update()
        ).all()

    def code_exists(self, code: str) -> bool:
        return self.db.scalar(
            select(Reservation.id_reserva).where(Reservation.codigo == code)
        ) is not None

    def create_reservation(
        self,
        *,
        client_id: int,
        branch_id: int,
        code: str,
        scheduled_at: datetime,
        expires_at: datetime,
    ):
        reservation = Reservation(
            id_cliente=client_id,
            id_sucursal=branch_id,
            id_empleado_atencion=None,
            codigo=code,
            estado="PENDIENTE",
            fecha_atencion_programada=scheduled_at,
            fecha_expiracion=expires_at,
            fecha_atencion=None,
        )
        self.db.add(reservation)
        self.db.flush()
        return reservation

    def create_details(self, reservation_id: int, items: list[dict]):
        self.db.add_all(
            [
                ReservationDetail(id_reserva=reservation_id, **item)
                for item in items
            ]
        )
        self.db.flush()

    def get_owned_reservation(
        self, reservation_id: int, client_id: int, *, for_update: bool = False
    ):
        statement = select(Reservation).where(
            Reservation.id_reserva == reservation_id,
            Reservation.id_cliente == client_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def get_details(self, reservation_id: int):
        return self.db.scalars(
            select(ReservationDetail)
            .where(ReservationDetail.id_reserva == reservation_id)
            .order_by(ReservationDetail.id_variante_producto)
        ).all()

    def list_due_ids(self, client_id: int, now: datetime):
        return list(
            self.db.scalars(
                select(Reservation.id_reserva)
                .where(
                    Reservation.id_cliente == client_id,
                    Reservation.estado.in_(HOLDING_STATES),
                    Reservation.fecha_expiracion <= now,
                )
                .order_by(Reservation.id_reserva)
            ).all()
        )

    @staticmethod
    def _principal_image():
        return (
            select(ProductImage.url_imagen)
            .where(ProductImage.id_producto == Product.id_producto)
            .order_by(
                ProductImage.es_principal.desc(),
                ProductImage.id_imagen_producto,
            )
            .limit(1)
            .correlate(Product)
            .scalar_subquery()
        )

    @classmethod
    def _summary_statement(cls):
        quantity = func.coalesce(func.sum(ReservationDetail.cantidad), 0)
        total = func.coalesce(
            func.sum(ReservationDetail.cantidad * ReservationDetail.precio_unitario), 0
        )
        return (
            select(
                Reservation.id_reserva,
                Reservation.codigo,
                Reservation.estado,
                Reservation.created_at,
                Reservation.fecha_atencion_programada,
                Reservation.fecha_expiracion,
                Branch.id_sucursal,
                Branch.nombre.label("sucursal"),
                Branch.direccion,
                City.id_ciudad,
                City.nombre.label("ciudad"),
                quantity.label("cantidad_prendas"),
                total.label("total"),
            )
            .select_from(Reservation)
            .join(Branch, Branch.id_sucursal == Reservation.id_sucursal)
            .join(City, City.id_ciudad == Branch.id_ciudad)
            .outerjoin(
                ReservationDetail,
                ReservationDetail.id_reserva == Reservation.id_reserva,
            )
            .group_by(
                Reservation.id_reserva,
                Branch.id_sucursal,
                Branch.nombre,
                Branch.direccion,
                City.id_ciudad,
                City.nombre,
            )
        )

    def list_reservations(
        self, client_id: int, *, state=None, page=1, page_size=20
    ):
        statement = self._summary_statement().where(
            Reservation.id_cliente == client_id
        )
        if state is not None:
            statement = statement.where(Reservation.estado == state)
        total = self.db.scalar(
            select(func.count()).select_from(statement.subquery())
        ) or 0
        rows = self.db.execute(
            statement.order_by(
                Reservation.created_at.desc(), Reservation.id_reserva.desc()
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).mappings().all()
        return rows, total

    def get_detail(self, reservation_id: int, client_id: int):
        header = self.db.execute(
            self._summary_statement().where(
                Reservation.id_reserva == reservation_id,
                Reservation.id_cliente == client_id,
            )
        ).mappings().one_or_none()
        if header is None:
            return None
        items = self.db.execute(
            select(
                ReservationDetail.id_variante_producto,
                ProductVariant.sku,
                Product.id_producto,
                Product.nombre.label("producto"),
                self._principal_image().label("imagen_principal"),
                Size.id_talla,
                Size.nombre.label("talla"),
                Color.id_color,
                Color.nombre.label("color"),
                Color.codigo_hex,
                ReservationDetail.cantidad,
                ReservationDetail.precio_unitario,
            )
            .select_from(ReservationDetail)
            .join(
                ProductVariant,
                ProductVariant.id_variante_producto
                == ReservationDetail.id_variante_producto,
            )
            .join(Product, Product.id_producto == ProductVariant.id_producto)
            .join(Size, Size.id_talla == ProductVariant.id_talla)
            .join(Color, Color.id_color == ProductVariant.id_color)
            .where(ReservationDetail.id_reserva == reservation_id)
            .order_by(ReservationDetail.id_variante_producto)
        ).mappings().all()
        return {**header, "items": items}
