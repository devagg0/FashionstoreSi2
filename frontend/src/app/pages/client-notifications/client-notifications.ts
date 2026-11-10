import { CommonModule, DatePipe } from '@angular/common';
import { Component, DestroyRef, inject, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Router, RouterLink } from '@angular/router';
import {
  ClientNotificationsService,
  NotificationItem,
  NotificationListResponse,
} from '../../core/services/client-notifications.service';
import { Icon, IconName } from '../../shared/components/icon/icon';

@Component({
  selector: 'app-client-notifications',
  standalone: true,
  imports: [CommonModule, RouterLink, DatePipe, Icon],
  templateUrl: './client-notifications.html',
  styleUrl: './client-notifications.scss',
})
export class ClientNotificationsPage implements OnInit {
  private readonly notificationsService = inject(ClientNotificationsService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  readonly loading = signal(false);
  readonly markingAll = signal(false);
  readonly error = signal<string>('');

  readonly notifications = signal<NotificationItem[]>([]);
  readonly total = signal<number>(0);
  readonly unreadCount = signal<number>(0);
  readonly filterUnread = signal<boolean>(false);
  readonly currentPage = signal<number>(1);
  readonly totalPages = signal<number>(1);

  ngOnInit(): void {
    this.loadNotifications(1);
  }

  loadNotifications(page: number = 1): void {
    this.loading.set(true);
    this.error.set('');

    this.notificationsService
      .getNotifications(page, 15, this.filterUnread())
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res: NotificationListResponse) => {
          this.notifications.set(res.items);
          this.total.set(res.total);
          this.unreadCount.set(res.no_leidas);
          this.currentPage.set(res.page);
          this.totalPages.set(res.total_pages);
          this.loading.set(false);
        },
        error: (err) => {
          this.loading.set(false);
          const detail =
            err?.error?.message ||
            err?.error?.detail ||
            'No fue posible cargar tus notificaciones. Intenta nuevamente.';
          this.error.set(detail);
        },
      });
  }

  setFilter(unreadOnly: boolean): void {
    if (this.filterUnread() === unreadOnly) return;
    this.filterUnread.set(unreadOnly);
    this.loadNotifications(1);
  }

  markAsRead(item: NotificationItem, event?: Event): void {
    if (event) {
      event.stopPropagation();
    }
    if (item.leido) return;

    this.notificationsService
      .markAsRead(item.id_notificacion)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (updated) => {
          this.notifications.update((list) =>
            list.map((n) =>
              n.id_notificacion === updated.id_notificacion ? { ...n, leido: true } : n,
            ),
          );
          this.unreadCount.update((count) => Math.max(0, count - 1));
        },
        error: () => {},
      });
  }

  markAllAsRead(): void {
    if (this.unreadCount() === 0 || this.markingAll()) return;

    this.markingAll.set(true);
    this.notificationsService
      .markAllAsRead()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.markingAll.set(false);
          this.notifications.update((list) => list.map((n) => ({ ...n, leido: true })));
          this.unreadCount.set(0);
        },
        error: () => {
          this.markingAll.set(false);
        },
      });
  }

  navigateToTarget(item: NotificationItem): void {
    this.markAsRead(item);

    const url = this.getActionUrl(item);
    if (url) {
      this.router.navigateByUrl(url);
    }
  }

  getActionUrl(item: NotificationItem): string | null {
    if (item.referencia_origen === 'RESERVA') {
      return '/mis-reservas';
    }
    if (item.referencia_origen === 'VENTA' || item.referencia_origen === 'PAGO') {
      if (item.referencia_id) {
        return `/mis-compras/${item.referencia_id}`;
      }
      return '/mis-compras';
    }
    return null;
  }

  getActionLabel(item: NotificationItem): string {
    if (item.referencia_origen === 'RESERVA') {
      return 'Ver reserva';
    }
    if (item.referencia_origen === 'VENTA' || item.referencia_origen === 'PAGO') {
      return 'Ver compra';
    }
    return 'Ver detalle';
  }

  getIconName(tipo: string): IconName {
    switch (tipo) {
      case 'RESERVA_CREADA':
        return 'store';
      case 'RESERVA_CONFIRMADA':
      case 'PAGO_CONFIRMADO':
      case 'COMPRA_CONFIRMADA':
        return 'circle-check';
      case 'RESERVA_CANCELADA':
        return 'close';
      case 'RESERVA_EXPIRADA':
      case 'PAGO_RECHAZADO':
        return 'alert-circle';
      default:
        return 'inbox';
    }
  }

  getIconClass(tipo: string): string {
    switch (tipo) {
      case 'RESERVA_CONFIRMADA':
      case 'PAGO_CONFIRMADO':
      case 'COMPRA_CONFIRMADA':
        return 'icon-success';
      case 'RESERVA_CANCELADA':
      case 'RESERVA_EXPIRADA':
      case 'PAGO_RECHAZADO':
        return 'icon-danger';
      case 'RESERVA_CREADA':
        return 'icon-info';
      default:
        return 'icon-default';
    }
  }
}

