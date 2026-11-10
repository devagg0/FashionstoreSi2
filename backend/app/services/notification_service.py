"""Servicio de gestión de notificaciones de reservas y compras (CU29)."""

import logging
from datetime import datetime, timezone
from math import ceil
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.tenant_context import set_tenant_context
from app.integrations.brevo import BrevoEmailClient
from app.models.client import Client
from app.models.notification import Notification
from app.models.payment import Payment
from app.models.reservation import Reservation
from app.models.sale import Sale
from app.models.user import User
from app.schemas.notification import (
    MarkReadResponse,
    NotificationListResponse,
    NotificationResponse,
    UnreadCountResponse,
)

logger = logging.getLogger(__name__)


class NotificationService:
    """Gestiona la creación idempotente, consulta y lectura de notificaciones para clientes."""

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @classmethod
    def create_notification(
        cls,
        db: Session,
        *,
        empresa_id: int,
        usuario_id: int,
        tipo: str,
        titulo: str,
        mensaje: str,
        referencia_origen: Optional[str] = None,
        referencia_id: Optional[int] = None,
        codigo_referencia: Optional[str] = None,
        clave_idempotencia: Optional[str] = None,
        send_email: bool = True,
    ) -> Notification:
        """Crea una notificación para el cliente de forma idempotente y opcionalmente envía Brevo."""
        resolved_empresa_id = empresa_id or db.info.get("empresa_id") or 1
        set_tenant_context(db, resolved_empresa_id)

        # Generar clave de idempotencia determinista si no se especifica
        key = clave_idempotencia or f"{tipo}:{referencia_origen or 'SYS'}:{referencia_id or 0}"

        # 1. Comprobar existencia previa por idempotencia dentro de la empresa
        existing = db.execute(
            select(Notification).where(
                Notification.empresa_id == resolved_empresa_id,
                Notification.clave_idempotencia == key,
            )
        ).scalar_one_or_none()

        if existing is not None:
            return existing

        now = cls._now()
        notification = Notification(
            empresa_id=resolved_empresa_id,
            id_usuario=usuario_id,
            tipo=tipo,
            titulo=titulo,
            mensaje=mensaje,
            referencia_origen=referencia_origen,
            referencia_id=referencia_id,
            codigo_referencia=codigo_referencia,
            clave_idempotencia=key,
            leido=False,
            fecha_lectura=None,
            created_at=now,
            updated_at=now,
        )
        db.add(notification)
        db.flush()

        # 2. Reutilización no bloqueante de Brevo para envío de correo transaccional
        if send_email:
            try:
                user = db.execute(
                    select(User).where(User.id_usuario == usuario_id)
                ).scalar_one_or_none()

                if user and user.correo:
                    full_name = f"{user.nombre} {user.apellido}".strip()
                    BrevoEmailClient().send_notification_email(
                        recipient_email=user.correo,
                        recipient_name=full_name,
                        subject=f"FashionStore · {titulo}",
                        title=titulo,
                        message=mensaje,
                    )
            except Exception as exc:
                # El fallo en el envío de correo jamás bloquea o revierte la transacción comercial
                logger.warning(
                    "No se pudo despachar el correo transaccional por Brevo para usuario %s: %s",
                    usuario_id,
                    exc,
                )

        return notification

    @classmethod
    def list_notifications(
        cls,
        db: Session,
        *,
        empresa_id: int,
        usuario_id: int,
        page: int = 1,
        page_size: int = 20,
        unread_only: bool = False,
    ) -> NotificationListResponse:
        """Devuelve el listado paginado de notificaciones del cliente autenticado."""
        set_tenant_context(db, empresa_id)

        query = select(Notification).where(
            Notification.empresa_id == empresa_id,
            Notification.id_usuario == usuario_id,
        )

        if unread_only:
            query = query.where(Notification.leido == False)  # noqa: E712

        # Conteo total
        count_stmt = select(func.count(Notification.id_notificacion)).where(
            Notification.empresa_id == empresa_id,
            Notification.id_usuario == usuario_id,
        )
        total = int(db.execute(count_stmt).scalar() or 0)

        # Conteo no leídas
        unread_stmt = select(func.count(Notification.id_notificacion)).where(
            Notification.empresa_id == empresa_id,
            Notification.id_usuario == usuario_id,
            Notification.leido == False,  # noqa: E712
        )
        no_leidas = int(db.execute(unread_stmt).scalar() or 0)

        # Paginación ordenada cronológicamente
        offset = max(0, (page - 1) * page_size)
        items = db.execute(
            query.order_by(Notification.created_at.desc()).offset(offset).limit(page_size)
        ).scalars().all()

        response_items = [
            NotificationResponse(
                id_notificacion=n.id_notificacion,
                usuario_id=n.id_usuario,
                empresa_id=n.empresa_id,
                tipo=n.tipo,
                titulo=n.titulo,
                mensaje=n.mensaje,
                referencia_origen=n.referencia_origen,
                referencia_id=n.referencia_id,
                codigo_referencia=n.codigo_referencia,
                leido=n.leido,
                fecha_lectura=n.fecha_lectura,
                created_at=n.created_at,
            )
            for n in items
        ]

        total_pages = ceil(total / page_size) if total > 0 else 1

        return NotificationListResponse(
            items=response_items,
            total=total,
            no_leidas=no_leidas,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    @classmethod
    def get_unread_count(
        cls,
        db: Session,
        *,
        empresa_id: int,
        usuario_id: int,
    ) -> UnreadCountResponse:
        """Devuelve el total de notificaciones no leídas para insignias en la barra de navegación."""
        set_tenant_context(db, empresa_id)

        unread_stmt = select(func.count(Notification.id_notificacion)).where(
            Notification.empresa_id == empresa_id,
            Notification.id_usuario == usuario_id,
            Notification.leido == False,  # noqa: E712
        )
        no_leidas = int(db.execute(unread_stmt).scalar() or 0)
        return UnreadCountResponse(no_leidas=no_leidas)

    @classmethod
    def mark_as_read(
        cls,
        db: Session,
        *,
        empresa_id: int,
        usuario_id: int,
        notification_id: int,
    ) -> NotificationResponse:
        """Marca una notificación específica como leída validando que pertenezca al usuario y empresa."""
        set_tenant_context(db, empresa_id)

        notification = db.execute(
            select(Notification).where(
                Notification.id_notificacion == notification_id,
                Notification.empresa_id == empresa_id,
                Notification.id_usuario == usuario_id,
            )
        ).scalar_one_or_none()

        if notification is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notificación no encontrada o no pertenece al usuario.",
            )

        if not notification.leido:
            now = cls._now()
            notification.leido = True
            notification.fecha_lectura = now
            notification.updated_at = now
            db.commit()
            db.refresh(notification)

        return NotificationResponse(
            id_notificacion=notification.id_notificacion,
            usuario_id=notification.id_usuario,
            empresa_id=notification.empresa_id,
            tipo=notification.tipo,
            titulo=notification.titulo,
            mensaje=notification.mensaje,
            referencia_origen=notification.referencia_origen,
            referencia_id=notification.referencia_id,
            codigo_referencia=notification.codigo_referencia,
            leido=notification.leido,
            fecha_lectura=notification.fecha_lectura,
            created_at=notification.created_at,
        )

    @classmethod
    def mark_all_as_read(
        cls,
        db: Session,
        *,
        empresa_id: int,
        usuario_id: int,
    ) -> MarkReadResponse:
        """Marca todas las notificaciones pendientes del cliente como leídas."""
        set_tenant_context(db, empresa_id)

        unread_notifications = db.execute(
            select(Notification).where(
                Notification.empresa_id == empresa_id,
                Notification.id_usuario == usuario_id,
                Notification.leido == False,  # noqa: E712
            )
        ).scalars().all()

        now = cls._now()
        for n in unread_notifications:
            n.leido = True
            n.fecha_lectura = now
            n.updated_at = now

        db.commit()
        return MarkReadResponse(success=True, marcadas=len(unread_notifications))

    # ==========================================
    # DISPARADORES AUTOMÁTICOS ANTE EVENTOS REALES
    # ==========================================

    @classmethod
    def notify_reservation_created(
        cls,
        db: Session,
        reservation: Reservation,
    ) -> Optional[Notification]:
        """Dispara notificación al cliente cuando se crea una reserva."""
        empresa_id = getattr(reservation, "empresa_id", None) or db.info.get("empresa_id")
        client = db.execute(
            select(Client).where(Client.id_cliente == reservation.id_cliente)
        ).scalar_one_or_none()
        if not client:
            return None
        if not empresa_id:
            empresa_id = getattr(client, "empresa_id", None) or 1

        return cls.create_notification(
            db,
            empresa_id=empresa_id,
            usuario_id=client.id_usuario,
            tipo="RESERVA_CREADA",
            titulo="Reserva registrada con éxito",
            mensaje=f"Tu reserva #{reservation.codigo} ha sido creada. Recuerda acudir antes de su vencimiento.",
            referencia_origen="RESERVA",
            referencia_id=reservation.id_reserva,
            codigo_referencia=reservation.codigo,
            clave_idempotencia=f"RESERVA_CREADA:{reservation.id_reserva}",
        )

    @classmethod
    def notify_reservation_confirmed(
        cls,
        db: Session,
        reservation: Reservation,
    ) -> Optional[Notification]:
        """Dispara notificación al cliente cuando la tienda confirma su reserva."""
        empresa_id = getattr(reservation, "empresa_id", None) or db.info.get("empresa_id")
        client = db.execute(
            select(Client).where(Client.id_cliente == reservation.id_cliente)
        ).scalar_one_or_none()
        if not client:
            return None
        if not empresa_id:
            empresa_id = getattr(client, "empresa_id", None) or 1

        return cls.create_notification(
            db,
            empresa_id=empresa_id,
            usuario_id=client.id_usuario,
            tipo="RESERVA_CONFIRMADA",
            titulo="Reserva confirmada",
            mensaje=f"Tu reserva #{reservation.codigo} ha sido confirmada por la sucursal. Tus prendas están reservadas.",
            referencia_origen="RESERVA",
            referencia_id=reservation.id_reserva,
            codigo_referencia=reservation.codigo,
            clave_idempotencia=f"RESERVA_CONFIRMADA:{reservation.id_reserva}",
        )

    @classmethod
    def notify_reservation_cancelled(
        cls,
        db: Session,
        reservation: Reservation,
    ) -> Optional[Notification]:
        """Dispara notificación al cliente cuando se cancela una reserva."""
        empresa_id = getattr(reservation, "empresa_id", None) or db.info.get("empresa_id")
        client = db.execute(
            select(Client).where(Client.id_cliente == reservation.id_cliente)
        ).scalar_one_or_none()
        if not client:
            return None
        if not empresa_id:
            empresa_id = getattr(client, "empresa_id", None) or 1

        return cls.create_notification(
            db,
            empresa_id=empresa_id,
            usuario_id=client.id_usuario,
            tipo="RESERVA_CANCELADA",
            titulo="Reserva cancelada",
            mensaje=f"La reserva #{reservation.codigo} ha sido cancelada y el stock fue liberado.",
            referencia_origen="RESERVA",
            referencia_id=reservation.id_reserva,
            codigo_referencia=reservation.codigo,
            clave_idempotencia=f"RESERVA_CANCELADA:{reservation.id_reserva}",
        )

    @classmethod
    def notify_reservation_expired(
        cls,
        db: Session,
        reservation: Reservation,
    ) -> Optional[Notification]:
        """Dispara notificación al cliente cuando una reserva expira sin atención."""
        empresa_id = getattr(reservation, "empresa_id", None) or db.info.get("empresa_id")
        client = db.execute(
            select(Client).where(Client.id_cliente == reservation.id_cliente)
        ).scalar_one_or_none()
        if not client:
            return None
        if not empresa_id:
            empresa_id = getattr(client, "empresa_id", None) or 1

        return cls.create_notification(
            db,
            empresa_id=empresa_id,
            usuario_id=client.id_usuario,
            tipo="RESERVA_EXPIRADA",
            titulo="Reserva expirada",
            mensaje=f"El plazo de atención de tu reserva #{reservation.codigo} ha vencido y quedó expirada.",
            referencia_origen="RESERVA",
            referencia_id=reservation.id_reserva,
            codigo_referencia=reservation.codigo,
            clave_idempotencia=f"RESERVA_EXPIRADA:{reservation.id_reserva}",
        )

    @classmethod
    def notify_payment_confirmed(
        cls,
        db: Session,
        sale: Sale,
        payment: Payment,
    ) -> Optional[Notification]:
        """Dispara notificación al cliente cuando su pago es aprobado."""
        if not sale.id_cliente:
            return None

        empresa_id = getattr(sale, "empresa_id", None) or getattr(payment, "empresa_id", None) or db.info.get("empresa_id")
        client = db.execute(
            select(Client).where(Client.id_cliente == sale.id_cliente)
        ).scalar_one_or_none()
        if not client:
            return None
        if not empresa_id:
            empresa_id = getattr(client, "empresa_id", None) or 1

        return cls.create_notification(
            db,
            empresa_id=empresa_id,
            usuario_id=client.id_usuario,
            tipo="PAGO_CONFIRMADO",
            titulo="Pago aprobado",
            mensaje=f"Tu pago por Bs. {float(payment.monto):.2f} (Venta #{sale.numero_venta}) ha sido aprobado.",
            referencia_origen="PAGO",
            referencia_id=payment.id_pago,
            codigo_referencia=sale.numero_venta,
            clave_idempotencia=f"PAGO_CONFIRMADO:{payment.id_pago}",
        )

    @classmethod
    def notify_purchase_confirmed(
        cls,
        db: Session,
        sale: Sale,
    ) -> Optional[Notification]:
        """Dispara notificación al cliente cuando su compra se completa satisfactoriamente."""
        if not sale.id_cliente:
            return None

        empresa_id = getattr(sale, "empresa_id", None) or db.info.get("empresa_id")
        client = db.execute(
            select(Client).where(Client.id_cliente == sale.id_cliente)
        ).scalar_one_or_none()
        if not client:
            return None
        if not empresa_id:
            empresa_id = getattr(client, "empresa_id", None) or 1

        return cls.create_notification(
            db,
            empresa_id=empresa_id,
            usuario_id=client.id_usuario,
            tipo="COMPRA_CONFIRMADA",
            titulo="Compra confirmada",
            mensaje=f"¡Gracias por tu compra! Tu orden #{sale.numero_venta} por Bs. {float(sale.total):.2f} ha sido confirmada.",
            referencia_origen="VENTA",
            referencia_id=sale.id_venta,
            codigo_referencia=sale.numero_venta,
            clave_idempotencia=f"COMPRA_CONFIRMADA:{sale.id_venta}",
        )

    @classmethod
    def notify_payment_rejected(
        cls,
        db: Session,
        sale: Sale,
        payment: Payment,
    ) -> Optional[Notification]:
        """Dispara notificación al cliente cuando su pago resulta rechazado."""
        if not sale.id_cliente:
            return None

        empresa_id = getattr(sale, "empresa_id", None) or getattr(payment, "empresa_id", None) or db.info.get("empresa_id")
        client = db.execute(
            select(Client).where(Client.id_cliente == sale.id_cliente)
        ).scalar_one_or_none()
        if not client:
            return None
        if not empresa_id:
            empresa_id = getattr(client, "empresa_id", None) or 1

        return cls.create_notification(
            db,
            empresa_id=empresa_id,
            usuario_id=client.id_usuario,
            tipo="PAGO_RECHAZADO",
            titulo="Pago rechazado",
            mensaje=f"El pago para la orden #{sale.numero_venta} no pudo completarse y ha sido rechazado.",
            referencia_origen="PAGO",
            referencia_id=payment.id_pago,
            codigo_referencia=sale.numero_venta,
            clave_idempotencia=f"PAGO_RECHAZADO:{payment.id_pago}",
        )

