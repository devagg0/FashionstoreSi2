"""CU30: Servicio unificado de consulta de operaciones (compras, reservas y pagos) del cliente."""

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from math import ceil
from typing import List, Optional

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.models.client import Client
from app.models.color import Color
from app.models.offline_reservation_sync import (
    OfflineReservationSync,
    ensure_offline_reservation_sync_table,
)
from app.models.payment import Payment
from app.models.product import Product
from app.models.product_image import ProductImage
from app.models.product_variant import ProductVariant
from app.models.reservation import Reservation
from app.models.reservation_detail import ReservationDetail
from app.models.sale import Sale
from app.models.sale_detail import SaleDetail
from app.models.size import Size
from app.schemas.client_operations import (
    ClientOperationDetailResponse,
    ClientOperationItem,
    ClientOperationsListResponse,
    ClientOperationsSummaryResponse,
    OperationItemDetail,
    OperationPaymentSummary,
)

logger = logging.getLogger(__name__)


class ClientOperationAccessError(Exception):
    """Acceso denegado o perfil no asociado."""
    pass


class ClientOperationNotFoundError(Exception):
    """Operación no encontrada o no pertenece al cliente."""
    pass


class ClientOperationsService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _naive_utc(value: Optional[datetime]) -> Optional[datetime]:
        if value is None:
            return None
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def get_client(self, user_id: int, empresa_id: int) -> Client:
        client = self.db.scalar(
            select(Client).where(
                Client.id_usuario == user_id,
                Client.empresa_id == empresa_id,
            )
        )
        if client is None:
            raise ClientOperationAccessError(
                "La cuenta no tiene un perfil de CLIENTE asociado en esta empresa"
            )
        return client

    def _get_main_image_subquery(self, empresa_id: int):
        return (
            select(ProductImage.url_imagen)
            .where(
                ProductImage.id_producto == Product.id_producto,
                ProductImage.empresa_id == empresa_id,
            )
            .order_by(ProductImage.es_principal.desc(), ProductImage.id_imagen_producto)
            .limit(1)
            .scalar_subquery()
        )

    def _map_payment_summary(self, payment: Payment) -> OperationPaymentSummary:
        return OperationPaymentSummary(
            id_pago=payment.id_pago,
            id_venta=payment.id_venta,
            medio=payment.medio,
            proveedor=payment.proveedor,
            entorno=payment.entorno,
            estado=payment.estado,
            confirmado=(payment.estado == "APROBADO"),
            monto=payment.monto,
            moneda=payment.moneda,
            referencia_externa=payment.referencia_externa,
            fecha_aprobacion=self._naive_utc(payment.fecha_aprobacion),
            created_at=self._naive_utc(payment.created_at),
        )

    def _fetch_sale_items(self, sale_id: int, empresa_id: int) -> List[OperationItemDetail]:
        img_sub = self._get_main_image_subquery(empresa_id)
        stmt = (
            select(
                SaleDetail.cantidad,
                SaleDetail.precio_unitario,
                SaleDetail.subtotal_linea,
                Product.id_producto,
                Product.nombre.label("producto"),
                ProductVariant.sku,
                Size.nombre.label("talla"),
                Color.nombre.label("color"),
                Color.codigo_hex.label("codigo_hex"),
                img_sub.label("imagen_principal"),
            )
            .outerjoin(
                ProductVariant,
                ProductVariant.id_variante_producto == SaleDetail.id_variante_producto,
            )
            .outerjoin(Product, Product.id_producto == ProductVariant.id_producto)
            .outerjoin(Size, Size.id_talla == ProductVariant.id_talla)
            .outerjoin(Color, Color.id_color == ProductVariant.id_color)
            .where(
                SaleDetail.id_venta == sale_id,
                SaleDetail.empresa_id == empresa_id,
            )
            .order_by(SaleDetail.id_detalle_venta)
        )
        rows = self.db.execute(stmt).all()
        return [
            OperationItemDetail(
                id_producto=row.id_producto,
                producto=row.producto or "Prenda",
                sku=row.sku,
                talla=row.talla,
                color=row.color,
                codigo_hex=row.codigo_hex,
                cantidad=row.cantidad,
                precio_unitario=row.precio_unitario,
                subtotal=row.subtotal_linea,
                imagen_principal=row.imagen_principal,
            )
            for row in rows
        ]

    def _fetch_reservation_items(self, reservation_id: int, empresa_id: int) -> List[OperationItemDetail]:
        img_sub = self._get_main_image_subquery(empresa_id)
        stmt = (
            select(
                ReservationDetail.cantidad,
                ReservationDetail.precio_unitario,
                Product.id_producto,
                Product.nombre.label("producto"),
                ProductVariant.sku,
                Size.nombre.label("talla"),
                Color.nombre.label("color"),
                Color.codigo_hex.label("codigo_hex"),
                img_sub.label("imagen_principal"),
            )
            .outerjoin(
                ProductVariant,
                ProductVariant.id_variante_producto == ReservationDetail.id_variante_producto,
            )
            .outerjoin(Product, Product.id_producto == ProductVariant.id_producto)
            .outerjoin(Size, Size.id_talla == ProductVariant.id_talla)
            .outerjoin(Color, Color.id_color == ProductVariant.id_color)
            .where(
                ReservationDetail.id_reserva == reservation_id,
                ReservationDetail.empresa_id == empresa_id,
            )
            .order_by(ReservationDetail.id_detalle_reserva)
        )
        rows = self.db.execute(stmt).all()
        return [
            OperationItemDetail(
                id_producto=row.id_producto,
                producto=row.producto or "Prenda",
                sku=row.sku,
                talla=row.talla,
                color=row.color,
                codigo_hex=row.codigo_hex,
                cantidad=row.cantidad,
                precio_unitario=row.precio_unitario,
                subtotal=Decimal(row.cantidad) * Decimal(row.precio_unitario),
                imagen_principal=row.imagen_principal,
            )
            for row in rows
        ]

    def list_operations(
        self,
        user_id: int,
        empresa_id: int,
        tipo: Optional[str] = None,
        estado: Optional[str] = None,
        desde: Optional[datetime] = None,
        hasta: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> ClientOperationsListResponse:
        client = self.get_client(user_id, empresa_id)
        client_id = client.id_cliente
        ensure_offline_reservation_sync_table(self.db)

        operations: List[ClientOperationItem] = []

        # 1. Compras (t_venta)
        sales_stmt = (
            select(Sale, Branch)
            .outerjoin(
                Branch,
                (Branch.id_sucursal == Sale.id_sucursal)
                & (Branch.empresa_id == Sale.empresa_id),
            )
            .where(Sale.id_cliente == client_id, Sale.empresa_id == empresa_id)
            .order_by(desc(Sale.fecha_venta), desc(Sale.id_venta))
        )
        sales_rows = self.db.execute(sales_stmt).all()
        sale_ids = [s.id_venta for s, _ in sales_rows]

        # Pagos asociados a compras
        payments_by_sale = {}
        if sale_ids:
            p_stmt = (
                select(Payment)
                .where(Payment.id_venta.in_(sale_ids), Payment.empresa_id == empresa_id)
                .order_by(desc(Payment.created_at), desc(Payment.id_pago))
            )
            payments = self.db.scalars(p_stmt).all()
            for p in payments:
                payments_by_sale.setdefault(p.id_venta, []).append(p)

        # Cantidad de prendas por compra
        items_count_by_sale = {}
        if sale_ids:
            cnt_stmt = (
                select(SaleDetail.id_venta, func.sum(SaleDetail.cantidad))
                .where(
                    SaleDetail.id_venta.in_(sale_ids),
                    SaleDetail.empresa_id == empresa_id,
                )
                .group_by(SaleDetail.id_venta)
            )
            for vid, cnt in self.db.execute(cnt_stmt).all():
                items_count_by_sale[vid] = int(cnt or 0)

        for sale, branch in sales_rows:
            sale_payments = payments_by_sale.get(sale.id_venta, [])
            latest_payment = (
                self._map_payment_summary(sale_payments[0])
                if sale_payments
                else None
            )
            is_confirmed = sale.estado == "COMPLETADA"
            label = "CONFIRMADA" if is_confirmed else sale.estado

            operations.append(
                ClientOperationItem(
                    id_operacion=f"COMPRA:{sale.id_venta}",
                    tipo="COMPRA",
                    id_referencia=sale.id_venta,
                    codigo=sale.numero_venta,
                    codigo_referencia=None,
                    fecha=self._naive_utc(sale.fecha_venta) or datetime.now(timezone.utc).replace(tzinfo=None),
                    importe=sale.total,
                    moneda=sale.moneda or "BOB",
                    estado=sale.estado,
                    estado_etiqueta=label,
                    confirmada=is_confirmed,
                    origen="ONLINE",
                    sucursal=branch.nombre if branch else None,
                    id_sucursal=sale.id_sucursal,
                    cantidad_prendas=items_count_by_sale.get(sale.id_venta, 0),
                    pago=latest_payment,
                )
            )

        # 2. Reservas (t_reserva)
        res_stmt = (
            select(Reservation, Branch)
            .outerjoin(
                Branch,
                (Branch.id_sucursal == Reservation.id_sucursal)
                & (Branch.empresa_id == Reservation.empresa_id),
            )
            .where(Reservation.id_cliente == client_id, Reservation.empresa_id == empresa_id)
            .order_by(desc(Reservation.created_at), desc(Reservation.id_reserva))
        )
        res_rows = self.db.execute(res_stmt).all()
        res_ids = [r.id_reserva for r, _ in res_rows]
        existing_res_codes = {r.codigo for r, _ in res_rows if r.codigo}

        # Consultar registros de sincronización offline asociados a reservas
        sync_by_res_id = {}
        if res_ids:
            try:
                with self.db.begin_nested():
                    sync_stmt = select(OfflineReservationSync).where(
                        OfflineReservationSync.id_reserva.in_(res_ids),
                        OfflineReservationSync.empresa_id == empresa_id,
                    )
                    for sync in self.db.scalars(sync_stmt).all():
                        if sync.id_reserva:
                            sync_by_res_id[sync.id_reserva] = sync
            except Exception as exc:
                logger.warning("No se pudo consultar sync de reservas en list_operations: %s", exc)

        # Cantidad de prendas y monto estimado por reserva
        res_totals = {}
        if res_ids:
            res_cnt_stmt = (
                select(
                    ReservationDetail.id_reserva,
                    func.sum(ReservationDetail.cantidad),
                    func.sum(ReservationDetail.cantidad * ReservationDetail.precio_unitario),
                )
                .where(
                    ReservationDetail.id_reserva.in_(res_ids),
                    ReservationDetail.empresa_id == empresa_id,
                )
                .group_by(ReservationDetail.id_reserva)
            )
            for rid, cnt, monto in self.db.execute(res_cnt_stmt).all():
                res_totals[rid] = (int(cnt or 0), Decimal(str(monto or 0)))

        for res, branch in res_rows:
            sync_rec = sync_by_res_id.get(res.id_reserva)
            is_offline = sync_rec is not None
            is_confirmed = res.estado in ("CONFIRMADA", "ATENDIDA")
            prendas, total_monto = res_totals.get(res.id_reserva, (0, Decimal("0.00")))

            operations.append(
                ClientOperationItem(
                    id_operacion=f"RESERVA:{res.id_reserva}",
                    tipo="RESERVA",
                    id_referencia=res.id_reserva,
                    codigo=res.codigo,
                    codigo_referencia=None,
                    fecha=self._naive_utc(res.created_at) or datetime.now(timezone.utc).replace(tzinfo=None),
                    importe=total_monto,
                    moneda="BOB",
                    estado=res.estado,
                    estado_etiqueta=res.estado,
                    confirmada=is_confirmed,
                    origen="OFFLINE_SYNC" if is_offline else "ONLINE",
                    sucursal=branch.nombre if branch else None,
                    id_sucursal=res.id_sucursal,
                    cantidad_prendas=prendas,
                    pago=None,
                    uuid_offline=sync_rec.uuid_reserva_offline if sync_rec else None,
                    fecha_atencion_programada=self._naive_utc(res.fecha_atencion_programada),
                    fecha_expiracion=self._naive_utc(res.fecha_expiracion),
                )
            )

        # 3. Intentos de sincronización offline fallidos o en conflicto (no en t_reserva)
        try:
            with self.db.begin_nested():
                unsynced_offline_stmt = (
                    select(OfflineReservationSync, Branch)
                    .outerjoin(
                        Branch,
                        (Branch.id_sucursal == OfflineReservationSync.id_sucursal)
                        & (Branch.empresa_id == OfflineReservationSync.empresa_id),
                    )
                    .where(
                        OfflineReservationSync.id_cliente == client_id,
                        OfflineReservationSync.empresa_id == empresa_id,
                        OfflineReservationSync.id_reserva.is_(None),
                    )
                    .order_by(desc(OfflineReservationSync.created_at))
                )
                seen_uuids = set()
                for sync_item, branch in self.db.execute(unsynced_offline_stmt).all():
                    if sync_item.uuid_reserva_offline in seen_uuids:
                        continue
                    if sync_item.codigo_reserva and sync_item.codigo_reserva in existing_res_codes:
                        continue
                    seen_uuids.add(sync_item.uuid_reserva_offline)
                    label = (
                        "CONFLICTO"
                        if sync_item.estado_sincronizacion == "CONFLICTO"
                        else "RECHAZADA (OFFLINE)"
                    )
                    operations.append(
                        ClientOperationItem(
                            id_operacion=f"RESERVA_OFFLINE:{sync_item.id_sync}",
                            tipo="RESERVA",
                            id_referencia=sync_item.id_sync,
                            codigo=sync_item.codigo_reserva or f"OFF-{sync_item.uuid_reserva_offline[:8]}",
                            codigo_referencia=None,
                            fecha=self._naive_utc(sync_item.fecha_reserva_offline or sync_item.created_at)
                            or datetime.now(timezone.utc).replace(tzinfo=None),
                            importe=Decimal("0.00"),
                            moneda="BOB",
                            estado=sync_item.estado_sincronizacion,
                            estado_etiqueta=label,
                            confirmada=False,
                            origen="OFFLINE_SYNC",
                            sucursal=branch.nombre if branch else None,
                            id_sucursal=sync_item.id_sucursal,
                            cantidad_prendas=0,
                            pago=None,
                            motivo=sync_item.motivo,
                            uuid_offline=sync_item.uuid_reserva_offline,
                        )
                    )
        except Exception as exc:
            logger.warning("No se pudo consultar registros offline sin reserva: %s", exc)

        # 4. Pagos individuales (t_pago asociados a compras del cliente)
        pay_stmt = (
            select(Payment, Sale, Branch)
            .join(
                Sale,
                (Sale.id_venta == Payment.id_venta)
                & (Sale.empresa_id == Payment.empresa_id),
            )
            .outerjoin(
                Branch,
                (Branch.id_sucursal == Sale.id_sucursal)
                & (Branch.empresa_id == Sale.empresa_id),
            )
            .where(Sale.id_cliente == client_id, Payment.empresa_id == empresa_id)
            .order_by(desc(Payment.created_at), desc(Payment.id_pago))
        )
        for pay, sale, branch in self.db.execute(pay_stmt).all():
            is_confirmed = pay.estado == "APROBADO"
            label = "CONFIRMADO" if is_confirmed else pay.estado

            operations.append(
                ClientOperationItem(
                    id_operacion=f"PAGO:{pay.id_pago}",
                    tipo="PAGO",
                    id_referencia=pay.id_pago,
                    codigo=f"PAG-{pay.id_pago:06d}",
                    codigo_referencia=sale.numero_venta,
                    fecha=self._naive_utc(pay.created_at or sale.fecha_venta)
                    or datetime.now(timezone.utc).replace(tzinfo=None),
                    importe=pay.monto,
                    moneda=pay.moneda,
                    estado=pay.estado,
                    estado_etiqueta=label,
                    confirmada=is_confirmed,
                    origen="ONLINE",
                    sucursal=branch.nombre if branch else None,
                    id_sucursal=sale.id_sucursal,
                    cantidad_prendas=0,
                    pago=self._map_payment_summary(pay),
                )
            )

        # Totales globales por tipo y estado
        totales_por_tipo = {"COMPRA": 0, "RESERVA": 0, "PAGO": 0}
        totales_por_estado = {
            "CONFIRMADA": 0,
            "PENDIENTE": 0,
            "RECHAZADA": 0,
            "CANCELADA": 0,
            "EXPIRADA": 0,
            "CONFLICTO": 0,
            "REEMBOLSADO": 0,
        }

        for op in operations:
            totales_por_tipo[op.tipo] = totales_por_tipo.get(op.tipo, 0) + 1
            if op.confirmada:
                totales_por_estado["CONFIRMADA"] += 1
            elif op.estado == "PENDIENTE":
                totales_por_estado["PENDIENTE"] += 1
            elif op.estado in ("RECHAZADA", "RECHAZADO", "ANULADA"):
                totales_por_estado["RECHAZADA"] += 1
            elif op.estado in ("CANCELADA", "CANCELADO"):
                totales_por_estado["CANCELADA"] += 1
            elif op.estado in ("EXPIRADA", "EXPIRADO"):
                totales_por_estado["EXPIRADA"] += 1
            elif op.estado == "CONFLICTO":
                totales_por_estado["CONFLICTO"] += 1
            elif op.estado == "REEMBOLSADO":
                totales_por_estado["REEMBOLSADO"] += 1

        # Filtros
        filtered = operations
        if tipo:
            t_upper = tipo.strip().upper()
            filtered = [op for op in filtered if op.tipo == t_upper]

        if estado:
            e_upper = estado.strip().upper()
            if e_upper in ("CONFIRMADA", "CONFIRMADO", "APROBADO", "COMPLETADA"):
                filtered = [op for op in filtered if op.confirmada]
            elif e_upper == "PENDIENTE":
                filtered = [op for op in filtered if op.estado == "PENDIENTE"]
            elif e_upper in ("RECHAZADA", "RECHAZADO", "ANULADA"):
                filtered = [
                    op
                    for op in filtered
                    if op.estado in ("RECHAZADA", "RECHAZADO", "ANULADA")
                ]
            elif e_upper in ("CANCELADA", "CANCELADO"):
                filtered = [
                    op for op in filtered if op.estado in ("CANCELADA", "CANCELADO")
                ]
            elif e_upper in ("EXPIRADA", "EXPIRADO"):
                filtered = [
                    op for op in filtered if op.estado in ("EXPIRADA", "EXPIRADO")
                ]
            else:
                filtered = [op for op in filtered if op.estado == e_upper]

        desde_naive = self._naive_utc(desde)
        if desde_naive:
            filtered = [op for op in filtered if op.fecha >= desde_naive]

        hasta_naive = self._naive_utc(hasta)
        if hasta_naive:
            filtered = [op for op in filtered if op.fecha <= hasta_naive]

        # Ordenar cronológicamente descendente
        filtered.sort(key=lambda x: x.fecha, reverse=True)

        total_items = len(filtered)
        total_pages = ceil(total_items / page_size) if total_items > 0 else 1
        page = max(1, page)
        offset = (page - 1) * page_size
        paged_items = filtered[offset : offset + page_size]

        return ClientOperationsListResponse(
            success=True,
            items=paged_items,
            total=total_items,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            totales_por_tipo=totales_por_tipo,
            totales_por_estado=totales_por_estado,
        )

    def get_operation_detail(
        self, user_id: int, empresa_id: int, tipo: str, id_referencia: int
    ) -> ClientOperationDetailResponse:
        client = self.get_client(user_id, empresa_id)
        client_id = client.id_cliente
        ensure_offline_reservation_sync_table(self.db)
        tipo_upper = tipo.strip().upper()

        if tipo_upper == "COMPRA":
            sale_stmt = (
                select(Sale, Branch)
                .outerjoin(
                    Branch,
                    (Branch.id_sucursal == Sale.id_sucursal)
                    & (Branch.empresa_id == Sale.empresa_id),
                )
                .where(
                    Sale.id_venta == id_referencia,
                    Sale.id_cliente == client_id,
                    Sale.empresa_id == empresa_id,
                )
            )
            row = self.db.execute(sale_stmt).one_or_none()
            if row is None:
                raise ClientOperationNotFoundError(
                    "La compra solicitada no existe o no pertenece al cliente"
                )
            sale, branch = row

            payments_stmt = (
                select(Payment)
                .where(Payment.id_venta == sale.id_venta, Payment.empresa_id == empresa_id)
                .order_by(desc(Payment.created_at), desc(Payment.id_pago))
            )
            payments = self.db.scalars(payments_stmt).all()
            latest_payment = (
                self._map_payment_summary(payments[0]) if payments else None
            )

            items = self._fetch_sale_items(sale.id_venta, empresa_id)
            is_confirmed = sale.estado == "COMPLETADA"

            operation_item = ClientOperationItem(
                id_operacion=f"COMPRA:{sale.id_venta}",
                tipo="COMPRA",
                id_referencia=sale.id_venta,
                codigo=sale.numero_venta,
                codigo_referencia=None,
                fecha=self._naive_utc(sale.fecha_venta) or datetime.now(timezone.utc).replace(tzinfo=None),
                importe=sale.total,
                moneda=sale.moneda or "BOB",
                estado=sale.estado,
                estado_etiqueta="CONFIRMADA" if is_confirmed else sale.estado,
                confirmada=is_confirmed,
                origen="ONLINE",
                sucursal=branch.nombre if branch else None,
                id_sucursal=sale.id_sucursal,
                cantidad_prendas=sum(item.cantidad for item in items),
                pago=latest_payment,
                detalles=items,
            )
            return ClientOperationDetailResponse(success=True, data=operation_item)

        elif tipo_upper == "RESERVA":
            res_stmt = (
                select(Reservation, Branch)
                .outerjoin(
                    Branch,
                    (Branch.id_sucursal == Reservation.id_sucursal)
                    & (Branch.empresa_id == Reservation.empresa_id),
                )
                .where(
                    Reservation.id_reserva == id_referencia,
                    Reservation.id_cliente == client_id,
                    Reservation.empresa_id == empresa_id,
                )
            )
            row = self.db.execute(res_stmt).one_or_none()
            if row is not None:
                res, branch = row
                sync_rec = None
                try:
                    with self.db.begin_nested():
                        sync_rec = self.db.scalar(
                            select(OfflineReservationSync).where(
                                OfflineReservationSync.id_reserva == res.id_reserva,
                                OfflineReservationSync.empresa_id == empresa_id,
                            )
                        )
                except Exception as exc:
                    logger.warning("No se pudo consultar sync en detalle reserva: %s", exc)

                items = self._fetch_reservation_items(res.id_reserva, empresa_id)
                is_confirmed = res.estado in ("CONFIRMADA", "ATENDIDA")
                total_importe = sum((item.subtotal for item in items), Decimal("0.00"))

                operation_item = ClientOperationItem(
                    id_operacion=f"RESERVA:{res.id_reserva}",
                    tipo="RESERVA",
                    id_referencia=res.id_reserva,
                    codigo=res.codigo,
                    codigo_referencia=None,
                    fecha=self._naive_utc(res.created_at) or datetime.now(timezone.utc).replace(tzinfo=None),
                    importe=total_importe,
                    moneda="BOB",
                    estado=res.estado,
                    estado_etiqueta=res.estado,
                    confirmada=is_confirmed,
                    origen="OFFLINE_SYNC" if sync_rec else "ONLINE",
                    sucursal=branch.nombre if branch else None,
                    id_sucursal=res.id_sucursal,
                    cantidad_prendas=sum(item.cantidad for item in items),
                    pago=None,
                    detalles=items,
                    uuid_offline=sync_rec.uuid_reserva_offline if sync_rec else None,
                    fecha_atencion_programada=self._naive_utc(res.fecha_atencion_programada),
                    fecha_expiracion=self._naive_utc(res.fecha_expiracion),
                )
                return ClientOperationDetailResponse(success=True, data=operation_item)

            sync_row = None
            try:
                with self.db.begin_nested():
                    sync_stmt = (
                        select(OfflineReservationSync, Branch)
                        .outerjoin(
                            Branch,
                            (Branch.id_sucursal == OfflineReservationSync.id_sucursal)
                            & (Branch.empresa_id == OfflineReservationSync.empresa_id),
                        )
                        .where(
                            OfflineReservationSync.id_sync == id_referencia,
                            OfflineReservationSync.id_cliente == client_id,
                            OfflineReservationSync.empresa_id == empresa_id,
                        )
                    )
                    sync_row = self.db.execute(sync_stmt).one_or_none()
            except Exception as exc:
                logger.warning("Error consultando detalle de reserva offline: %s", exc)

            if sync_row is None:
                raise ClientOperationNotFoundError(
                    "La reserva solicitada no existe o no pertenece al cliente"
                )

            sync_item, branch = sync_row
            detalles_parsed: List[OperationItemDetail] = []
            if sync_item.detalles_json:
                try:
                    payload = json.loads(sync_item.detalles_json)
                    items_raw = payload.get("detalles", payload.get("items", []))
                    for it in items_raw:
                        detalles_parsed.append(
                            OperationItemDetail(
                                id_producto=it.get("id_producto"),
                                producto=it.get("nombre", it.get("producto", "Prenda")),
                                sku=it.get("sku"),
                                talla=it.get("talla"),
                                color=it.get("color"),
                                cantidad=int(it.get("cantidad", 1)),
                                precio_unitario=Decimal(str(it.get("precio_unitario", 0))),
                                subtotal=Decimal(str(it.get("precio_unitario", 0)))
                                * int(it.get("cantidad", 1)),
                            )
                        )
                except Exception as exc:
                    logger.warning("Error parseando detalles_json de sync %s: %s", sync_item.id_sync, exc)

            label = (
                "CONFLICTO"
                if sync_item.estado_sincronizacion == "CONFLICTO"
                else "RECHAZADA (OFFLINE)"
            )
            operation_item = ClientOperationItem(
                id_operacion=f"RESERVA_OFFLINE:{sync_item.id_sync}",
                tipo="RESERVA",
                id_referencia=sync_item.id_sync,
                codigo=sync_item.codigo_reserva or f"OFF-{sync_item.uuid_reserva_offline[:8]}",
                fecha=self._naive_utc(sync_item.fecha_reserva_offline or sync_item.created_at)
                or datetime.now(timezone.utc).replace(tzinfo=None),
                importe=sum((it.subtotal for it in detalles_parsed), Decimal("0.00")),
                moneda="BOB",
                estado=sync_item.estado_sincronizacion,
                estado_etiqueta=label,
                confirmada=False,
                origen="OFFLINE_SYNC",
                sucursal=branch.nombre if branch else None,
                id_sucursal=sync_item.id_sucursal,
                cantidad_prendas=sum(it.cantidad for it in detalles_parsed),
                pago=None,
                detalles=detalles_parsed if detalles_parsed else None,
                motivo=sync_item.motivo,
                uuid_offline=sync_item.uuid_reserva_offline,
            )
            return ClientOperationDetailResponse(success=True, data=operation_item)

        elif tipo_upper == "PAGO":
            pay_stmt = (
                select(Payment, Sale, Branch)
                .join(
                    Sale,
                    (Sale.id_venta == Payment.id_venta)
                    & (Sale.empresa_id == Payment.empresa_id),
                )
                .outerjoin(
                    Branch,
                    (Branch.id_sucursal == Sale.id_sucursal)
                    & (Branch.empresa_id == Sale.empresa_id),
                )
                .where(
                    Payment.id_pago == id_referencia,
                    Sale.id_cliente == client_id,
                    Payment.empresa_id == empresa_id,
                )
            )
            row = self.db.execute(pay_stmt).one_or_none()
            if row is None:
                raise ClientOperationNotFoundError(
                    "El pago solicitado no existe o no pertenece al cliente"
                )
            pay, sale, branch = row

            is_confirmed = pay.estado == "APROBADO"
            items = self._fetch_sale_items(sale.id_venta, empresa_id)

            operation_item = ClientOperationItem(
                id_operacion=f"PAGO:{pay.id_pago}",
                tipo="PAGO",
                id_referencia=pay.id_pago,
                codigo=f"PAG-{pay.id_pago:06d}",
                codigo_referencia=sale.numero_venta,
                fecha=self._naive_utc(pay.created_at or sale.fecha_venta)
                or datetime.now(timezone.utc).replace(tzinfo=None),
                importe=pay.monto,
                moneda=pay.moneda,
                estado=pay.estado,
                estado_etiqueta="CONFIRMADO" if is_confirmed else pay.estado,
                confirmada=is_confirmed,
                origen="ONLINE",
                sucursal=branch.nombre if branch else None,
                id_sucursal=sale.id_sucursal,
                cantidad_prendas=sum(it.cantidad for it in items),
                pago=self._map_payment_summary(pay),
                detalles=items,
            )
            return ClientOperationDetailResponse(success=True, data=operation_item)

        else:
            raise ClientOperationNotFoundError(f"Tipo de operación '{tipo}' no soportado")

    def get_summary(self, user_id: int, empresa_id: int) -> ClientOperationsSummaryResponse:
        client = self.get_client(user_id, empresa_id)
        client_id = client.id_cliente
        ensure_offline_reservation_sync_table(self.db)

        total_compras = int(
            self.db.scalar(
                select(func.count(Sale.id_venta)).where(
                    Sale.id_cliente == client_id, Sale.empresa_id == empresa_id
                )
            )
            or 0
        )

        total_reservas = int(
            self.db.scalar(
                select(func.count(Reservation.id_reserva)).where(
                    Reservation.id_cliente == client_id, Reservation.empresa_id == empresa_id
                )
            )
            or 0
        )

        total_offline = 0
        try:
            with self.db.begin_nested():
                total_offline = int(
                    self.db.scalar(
                        select(func.count(OfflineReservationSync.id_sync)).where(
                            OfflineReservationSync.id_cliente == client_id,
                            OfflineReservationSync.empresa_id == empresa_id,
                            OfflineReservationSync.id_reserva.is_(None),
                        )
                    )
                    or 0
                )
        except Exception as exc:
            logger.warning("No se pudo contar registros offline en summary: %s", exc)

        total_reservas += total_offline

        total_pagos = int(
            self.db.scalar(
                select(func.count(Payment.id_pago))
                .join(
                    Sale,
                    (Sale.id_venta == Payment.id_venta)
                    & (Sale.empresa_id == Payment.empresa_id),
                )
                .where(Sale.id_cliente == client_id, Payment.empresa_id == empresa_id)
            )
            or 0
        )

        total_gastado = self.db.scalar(
            select(func.sum(Sale.total)).where(
                Sale.id_cliente == client_id,
                Sale.empresa_id == empresa_id,
                Sale.estado == "COMPLETADA",
            )
        ) or Decimal("0.00")

        pendientes = 0
        confirmadas = 0
        rechazadas = total_offline

        ventas_stats = self.db.execute(
            select(Sale.estado, func.count(Sale.id_venta))
            .where(Sale.id_cliente == client_id, Sale.empresa_id == empresa_id)
            .group_by(Sale.estado)
        ).all()
        for est, cnt in ventas_stats:
            c_int = int(cnt or 0)
            if est == "COMPLETADA":
                confirmadas += c_int
            elif est == "PENDIENTE":
                pendientes += c_int
            else:
                rechazadas += c_int

        res_stats = self.db.execute(
            select(Reservation.estado, func.count(Reservation.id_reserva))
            .where(Reservation.id_cliente == client_id, Reservation.empresa_id == empresa_id)
            .group_by(Reservation.estado)
        ).all()
        for est, cnt in res_stats:
            c_int = int(cnt or 0)
            if est in ("CONFIRMADA", "ATENDIDA"):
                confirmadas += c_int
            elif est == "PENDIENTE":
                pendientes += c_int
            else:
                rechazadas += c_int

        pay_stats = self.db.execute(
            select(Payment.estado, func.count(Payment.id_pago))
            .join(
                Sale,
                (Sale.id_venta == Payment.id_venta)
                & (Sale.empresa_id == Payment.empresa_id),
            )
            .where(Sale.id_cliente == client_id, Payment.empresa_id == empresa_id)
            .group_by(Payment.estado)
        ).all()
        for est, cnt in pay_stats:
            c_int = int(cnt or 0)
            if est == "APROBADO":
                confirmadas += c_int
            elif est == "PENDIENTE":
                pendientes += c_int
            else:
                rechazadas += c_int

        total_operaciones = total_compras + total_reservas + total_pagos

        return ClientOperationsSummaryResponse(
            success=True,
            total_operaciones=total_operaciones,
            total_compras=total_compras,
            total_reservas=total_reservas,
            total_pagos=total_pagos,
            pendientes=pendientes,
            confirmadas=confirmadas,
            rechazadas=rechazadas,
            importe_total_compras=Decimal(str(total_gastado)),
        )
