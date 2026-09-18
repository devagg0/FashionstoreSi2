import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { Subscription, finalize, timeout } from 'rxjs';
import { ReceiptsService, SaleReceipt } from '../../core/services/receipts.service';
import { formatBs } from '../../core/utils/money';

@Component({
  selector: 'app-sale-receipt',
  imports: [RouterLink],
  templateUrl: './receipt.html',
  styleUrl: './receipt.scss',
})
export class ReceiptPage {
  private readonly api = inject(ReceiptsService);
  private readonly route = inject(ActivatedRoute);
  private readonly destroy = inject(DestroyRef);
  private request?: Subscription;
  private id = 0;
  readonly staff = this.route.snapshot.data['audience'] === 'staff';
  readonly receipt = signal<SaleReceipt | null>(null);
  readonly loading = signal(false);
  readonly error = signal('');
  readonly expired = signal(false);
  readonly retryable = signal(false);
  readonly back = signal('/mis-compras');
  readonly money = formatBs;
  constructor() {
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroy)).subscribe(params => {
      this.request?.unsubscribe();
      const raw = params.get('id') ?? '';
      this.id = /^[1-9]\d*$/.test(raw) ? Number(raw) : 0;
      this.back.set(this.staff ? '/staff/ventas/nueva' : this.id ? `/mis-compras/${this.id}` : '/mis-compras');
      this.load();
    });
    this.destroy.onDestroy(() => this.request?.unsubscribe());
  }
  load(): void {
    if (this.loading()) return;
    this.receipt.set(null);
    this.error.set('');
    this.expired.set(false);
    this.retryable.set(false);
    if (!Number.isSafeInteger(this.id) || this.id <= 0 || this.id > 2147483647) {
      this.error.set('Comprobante no encontrado.');
      return;
    }
    this.loading.set(true);
    this.request = this.api.get(this.id, this.staff ? 'staff' : 'client')
      .pipe(timeout(25000), finalize(() => this.loading.set(false)))
      .subscribe({
        next: response => this.receipt.set(response.data),
        error: (error: HttpErrorResponse | Error) => {
          const status = error instanceof HttpErrorResponse ? error.status : 0;
          this.expired.set(status === 401);
          this.retryable.set(status === 0 || status >= 500);
          this.error.set(({
            0: 'No pudimos conectar. Revisa tu conexión y vuelve a intentarlo.',
            401: 'Tu sesión expiró. Inicia sesión para consultar el comprobante.',
            403: 'No tienes permiso para consultar este comprobante.',
            404: 'Comprobante no encontrado o no disponible para tu cuenta o sucursal.',
            409: 'Comprobante no disponible. La venta debe estar COMPLETADA y tener un pago aprobado válido. Las ventas PENDIENTES o ANULADAS no tienen comprobante.',
          } as Record<number, string>)[status] ?? 'No pudimos consultar el comprobante. Inténtalo nuevamente.');
        },
      });
  }
  print(): void {
    if (this.receipt() && !this.loading() && !this.error()) window.print();
  }
  date(value: string): string {
    const date = new Date(/(Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`);
    return Number.isNaN(date.getTime()) ? 'Fecha no disponible' : new Intl.DateTimeFormat('es-BO', {
      dateStyle: 'long', timeStyle: 'short', timeZone: 'America/La_Paz',
    }).format(date);
  }
  method(value: string): string {
    return ({ TARJETA: 'Tarjeta', EFECTIVO: 'Efectivo', QR: 'QR' } as Record<string, string>)[value] ?? 'No disponible';
  }
}
