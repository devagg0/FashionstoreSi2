"""Repositorio de persistencia transaccional para PK08 - CU11: Registrar venta de contado y compra digital offline."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.models.branch_inventory import BranchInventory
from app.models.cart import Cart
from app.models.client import Client
from app.models.employee import Employee
from app.models.employee_branch import EmployeeBranch
from app.models.inventory_movement import InventoryMovement
from app.models.inventory_movement_detail import InventoryMovementDetail
from app.models.offline_reservation_sync import (
    OfflineReservationSync,
    ensure_offline_reservation_sync_table,
)
from app.models.payment import Payment
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.promotion import Promotion
from app.models.promotion_product import PromotionProduct
from app.models.reservation import Reservation
from app.models.reservation_detail import ReservationDetail
from app.models.sale import Sale
from app.models.sale_detail import SaleDetail


class OfflineSaleRepository:
    """Acceso y persistencia atómica de ventas presenciales, compras digitales, pagos y reservas en PostgreSQL."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_sale_by_number(self, company_id: int, sale_number: str) -> Sale | None:
        """Busca una venta por número único dentro de la empresa (control de idempotencia)."""
        statement = select(Sale).where(
            Sale.empresa_id == company_id,
            Sale.numero_venta == sale_number,
        )
        return self.db.scalar(statement)

    def get_sale_by_id(self, company_id: int, sale_id: int) -> Sale | None:
        """Obtiene una venta por su identificador dentro de la empresa."""
        statement = select(Sale).where(
            Sale.empresa_id == company_id,
            Sale.id_venta == sale_id,
        )
        return self.db.scalar(statement)

    def get_payment_by_key(
        self, company_id: int, idempotency_key: UUID
    ) -> Payment | None:
        """Busca un pago por su clave UUID de idempotencia dentro de la empresa."""
        statement = select(Payment).where(
            Payment.empresa_id == company_id,
            Payment.clave_idempotencia == idempotency_key,
        )
        return self.db.scalar(statement)

    def get_payment_for_sale(self, company_id: int, sale_id: int) -> Payment | None:
        """Obtiene el pago asociado a una venta dentro de la empresa."""
        statement = (
            select(Payment)
            .where(
                Payment.empresa_id == company_id,
                Payment.id_venta == sale_id,
            )
            .order_by(Payment.id_pago.desc())
        )
        return self.db.scalar(statement)

    def get_branch(self, company_id: int, branch_id: int) -> Branch | None:
        """Obtiene una sucursal validando pertenencia a la empresa."""
        statement = select(Branch).where(
            Branch.empresa_id == company_id,
            Branch.id_sucursal == branch_id,
        )
        return self.db.scalar(statement)

    def get_client_by_user(self, company_id: int, user_id: int) -> Client | None:
        """Obtiene el perfil de cliente vinculado al usuario autenticado dentro de la empresa."""
        statement = select(Client).where(
            Client.empresa_id == company_id,
            Client.id_usuario == user_id,
        )
        return self.db.scalar(statement)

    def get_client_by_id(self, company_id: int, client_id: int) -> Client | None:
        """Obtiene un cliente por su ID dentro de la empresa."""
        statement = select(Client).where(
            Client.empresa_id == company_id,
            Client.id_cliente == client_id,
        )
        return self.db.scalar(statement)

    def get_employee_by_user(self, company_id: int, user_id: int) -> Employee | None:
        """Obtiene el perfil de empleado vinculado al usuario autenticado dentro de la empresa."""
        statement = select(Employee).where(
            Employee.empresa_id == company_id,
            Employee.id_usuario == user_id,
        )
        return self.db.scalar(statement)

    def get_employee_branch_assignment(
        self, company_id: int, employee_id: int, branch_id: int
    ) -> EmployeeBranch | None:
        """Obtiene la asignación activa del empleado a la sucursal especificada."""
        statement = select(EmployeeBranch).where(
            EmployeeBranch.empresa_id == company_id,
            EmployeeBranch.id_empleado == employee_id,
            EmployeeBranch.id_sucursal == branch_id,
            EmployeeBranch.estado.is_(True),
        )
        return self.db.scalar(statement)

    def get_employee_active_branch_ids(
        self, company_id: int, employee_id: int
    ) -> list[int]:
        """Lista los IDs de sucursales activas donde el empleado tiene asignación activa."""
        statement = (
            select(EmployeeBranch.id_sucursal)
            .join(Branch, Branch.id_sucursal == EmployeeBranch.id_sucursal)
            .where(
                EmployeeBranch.empresa_id == company_id,
                EmployeeBranch.id_empleado == employee_id,
                EmployeeBranch.estado.is_(True),
                Branch.empresa_id == company_id,
                Branch.estado.is_(True),
            )
            .order_by(EmployeeBranch.id_sucursal)
        )
        return list(self.db.scalars(statement).all())

    def get_cart(
        self,
        company_id: int,
        cart_id: int,
        client_id: int,
        *,
        for_update: bool = False,
    ) -> Cart | None:
        """Obtiene el carrito del cliente dentro de la empresa."""
        statement = select(Cart).where(
            Cart.empresa_id == company_id,
            Cart.id_carrito == cart_id,
            Cart.id_cliente == client_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def get_sale_for_cart(self, company_id: int, cart_id: int) -> Sale | None:
        """Verifica si un carrito ya fue convertido en una venta previa."""
        statement = select(Sale).where(
            Sale.empresa_id == company_id,
            Sale.id_carrito == cart_id,
        )
        return self.db.scalar(statement)

    def get_reservation(
        self,
        company_id: int,
        *,
        reservation_id: int | None = None,
        code: str | None = None,
        uuid_offline: str | None = None,
        for_update: bool = False,
    ) -> Reservation | None:
        """Resuelve una reserva por ID, código o UUID offline (CU10) dentro de la empresa."""
        def _query_by_id(res_id: int) -> Reservation | None:
            stmt = select(Reservation).where(
                Reservation.empresa_id == company_id,
                Reservation.id_reserva == res_id,
            )
            if for_update:
                stmt = stmt.with_for_update()
            return self.db.scalar(stmt)

        def _query_by_code(res_code: str) -> Reservation | None:
            stmt = select(Reservation).where(
                Reservation.empresa_id == company_id,
                Reservation.codigo == res_code.strip().upper(),
            )
            if for_update:
                stmt = stmt.with_for_update()
            return self.db.scalar(stmt)

        if reservation_id is not None and reservation_id < 70000000:
            found = _query_by_id(reservation_id)
            if found is not None:
                return found

        if uuid_offline:
            ensure_offline_reservation_sync_table(self.db)
            sync_row = self.db.scalar(
                select(OfflineReservationSync).where(
                    OfflineReservationSync.empresa_id == company_id,
                    OfflineReservationSync.uuid_reserva_offline == uuid_offline.strip(),
                )
            )
            if sync_row and sync_row.id_reserva is not None:
                found = _query_by_id(sync_row.id_reserva)
                if found is not None:
                    return found

        if code:
            found = _query_by_code(code)
            if found is not None:
                return found
            ensure_offline_reservation_sync_table(self.db)
            sync_by_code = self.db.scalar(
                select(OfflineReservationSync).where(
                    OfflineReservationSync.empresa_id == company_id,
                    OfflineReservationSync.uuid_reserva_offline == code.strip(),
                )
            )
            if sync_by_code and sync_by_code.id_reserva is not None:
                found = _query_by_id(sync_by_code.id_reserva)
                if found is not None:
                    return found

        if reservation_id is not None and reservation_id >= 70000000:
            return _query_by_id(reservation_id)

        return None

    def get_reservation_details(
        self, company_id: int, reservation_id: int
    ) -> list[ReservationDetail]:
        """Obtiene los detalles de prendas reservadas para una reserva."""
        statement = (
            select(ReservationDetail)
            .where(
                ReservationDetail.empresa_id == company_id,
                ReservationDetail.id_reserva == reservation_id,
            )
            .order_by(ReservationDetail.id_variante_producto)
        )
        return list(self.db.scalars(statement).all())

    def get_sale_for_reservation(
        self, company_id: int, reservation_id: int
    ) -> Sale | None:
        """Verifica si la reserva ya cuenta con una venta asociada en t_venta."""
        statement = select(Sale).where(
            Sale.empresa_id == company_id,
            Sale.id_reserva == reservation_id,
        )
        return self.db.scalar(statement)

    def get_variants_with_products(
        self, company_id: int, variant_ids: list[int]
    ) -> dict[int, tuple[ProductVariant, Product]]:
        """Obtiene las variantes y sus productos padre validando pertenencia al tenant."""
        if not variant_ids:
            return {}
        statement = (
            select(ProductVariant, Product)
            .join(Product, Product.id_producto == ProductVariant.id_producto)
            .where(
                ProductVariant.empresa_id == company_id,
                Product.empresa_id == company_id,
                ProductVariant.id_variante_producto.in_(sorted(variant_ids)),
            )
        )
        rows = self.db.execute(statement).all()
        return {row[0].id_variante_producto: (row[0], row[1]) for row in rows}

    def get_active_promotions_for_products(
        self, company_id: int, product_ids: list[int], now: datetime
    ) -> dict[int, tuple[int, Decimal]]:
        """Obtiene la mejor promoción activa (id_promocion, descuento_unitario) por producto."""
        if not product_ids:
            return {}
        statement = (
            select(PromotionProduct.id_producto, Promotion, Product.precio)
            .join(Promotion, Promotion.id_promocion == PromotionProduct.id_promocion)
            .join(Product, Product.id_producto == PromotionProduct.id_producto)
            .where(
                PromotionProduct.empresa_id == company_id,
                Promotion.empresa_id == company_id,
                Product.empresa_id == company_id,
                Promotion.estado.is_(True),
                Promotion.fecha_inicio <= now,
                Promotion.fecha_fin >= now,
                PromotionProduct.id_producto.in_(sorted(product_ids)),
            )
            .order_by(Promotion.id_promocion)
        )
        rows = self.db.execute(statement).all()
        best: dict[int, tuple[int, Decimal]] = {}
        for prod_id, promo, base_price in rows:
            base = Decimal(str(base_price)).quantize(Decimal("0.01"))
            val = Decimal(str(promo.valor))
            if getattr(promo, "tipo_descuento", "") == "PORCENTAJE":
                disc = (base * val / Decimal("100")).quantize(Decimal("0.01"))
            else:
                disc = val.quantize(Decimal("0.01"))
            disc = min(base, max(Decimal("0.00"), disc))
            if prod_id not in best or disc > best[prod_id][1]:
                best[prod_id] = (promo.id_promocion, disc)
        return best

    def lock_inventories(
        self, company_id: int, branch_id: int, variant_ids: list[int]
    ) -> dict[int, BranchInventory]:
        """Bloquea las filas de inventario de la sucursal para las variantes indicadas."""
        if not variant_ids:
            return {}
        statement = (
            select(BranchInventory)
            .where(
                BranchInventory.empresa_id == company_id,
                BranchInventory.id_sucursal == branch_id,
                BranchInventory.id_variante_producto.in_(sorted(variant_ids)),
            )
            .order_by(BranchInventory.id_variante_producto)
            .with_for_update()
        )
        rows = self.db.scalars(statement).all()
        return {inv.id_variante_producto: inv for inv in rows}

    def create_sale(
        self,
        *,
        company_id: int,
        branch_id: int,
        employee_id: int | None,
        client_id: int | None,
        reservation_id: int | None,
        cart_id: int | None,
        canal: str,
        sale_number: str,
        estado: str,
        stock_comprometido: bool,
        subtotal: Decimal,
        descuento_total: Decimal,
        total: Decimal,
        fecha_venta: datetime,
        fecha_completada: datetime | None,
        fecha_expiracion_pago: datetime | None,
        now: datetime,
    ) -> Sale:
        """Persiste el encabezado de venta en t_venta."""
        sale = Sale(
            empresa_id=company_id,
            id_sucursal=branch_id,
            id_empleado=employee_id,
            id_cliente=client_id,
            id_reserva=reservation_id,
            id_carrito=cart_id,
            canal=canal,
            moneda="BOB",
            numero_venta=sale_number,
            estado=estado,
            stock_comprometido=stock_comprometido,
            subtotal=subtotal,
            descuento_total=descuento_total,
            total=total,
            fecha_venta=fecha_venta,
            fecha_completada=fecha_completada,
            fecha_expiracion_pago=fecha_expiracion_pago,
            created_at=now,
            updated_at=now,
        )
        self.db.add(sale)
        self.db.flush()
        return sale

    def create_sale_details(
        self, company_id: int, sale_id: int, lines: list[dict[str, Any]]
    ) -> list[SaleDetail]:
        """Persiste los detalles de línea de venta en t_detalle_venta."""
        details = [
            SaleDetail(
                empresa_id=company_id,
                id_venta=sale_id,
                id_variante_producto=line["id_variante_producto"],
                cantidad=line["cantidad"],
                precio_unitario=line["precio_unitario"],
                descuento_unitario=line["descuento_unitario"],
                id_promocion=line.get("id_promocion"),
                subtotal_linea=line["subtotal_linea"],
            )
            for line in lines
        ]
        self.db.add_all(details)
        self.db.flush()
        return details

    def create_inventory_movement(
        self,
        *,
        company_id: int,
        sale_id: int,
        branch_id: int,
        employee_branch_id: int | None,
        estado: str,
        motivo: str,
        lines: list[dict[str, Any]],
        now: datetime,
    ) -> InventoryMovement:
        """Crea el movimiento de inventario asociado a la venta y sus detalles."""
        movement = InventoryMovement(
            empresa_id=company_id,
            id_sucursal_origen=branch_id,
            id_sucursal_destino=None,
            id_empleado_sucursal=employee_branch_id,
            id_venta=sale_id,
            tipo_movimiento="VENTA",
            estado=estado,
            motivo=motivo,
            fecha_movimiento=now,
            created_at=now,
            updated_at=now,
        )
        self.db.add(movement)
        self.db.flush()
        movement_details = [
            InventoryMovementDetail(
                empresa_id=company_id,
                id_movimiento_inventario=movement.id_movimiento_inventario,
                id_variante_producto=line["id_variante_producto"],
                cantidad=line["cantidad"],
                costo_unitario=None,
            )
            for line in lines
        ]
        self.db.add_all(movement_details)
        self.db.flush()
        return movement

    def create_payment(
        self,
        *,
        company_id: int,
        sale_id: int,
        medio: str,
        proveedor: str,
        entorno: str,
        estado: str,
        monto: Decimal,
        idempotency_key: UUID,
        fecha_aprobacion: datetime | None,
        referencia_externa: str | None = None,
        now: datetime,
    ) -> Payment:
        """Crea el registro de pago en t_pago."""
        payment = Payment(
            empresa_id=company_id,
            id_venta=sale_id,
            medio=medio,
            proveedor=proveedor,
            entorno=entorno,
            estado=estado,
            monto=monto,
            moneda="BOB",
            referencia_externa=referencia_externa,
            clave_idempotencia=idempotency_key,
            fecha_aprobacion=fecha_aprobacion,
            created_at=now,
            updated_at=now,
        )
        self.db.add(payment)
        self.db.flush()
        return payment

