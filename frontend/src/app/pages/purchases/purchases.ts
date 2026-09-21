import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { Subscription, finalize, of, switchMap, tap, timeout } from 'rxjs';
import {
  ClientPurchasesService,
  PurchaseChannel,
  PurchaseDetail,
  PurchaseState,
  PurchaseSummary,
} from '../../core/services/client-purchases.service';
import { CheckoutNavigationService } from '../../core/services/checkout-navigation.service';
import { PaymentsService } from '../../core/services/payments.service';
import { PurchaseReturnRequest } from './return-request/return-request';
import { formatBs } from '../../core/utils/money';
import { formatSaleReference } from '../../core/utils/sale-reference';

@Component({
  selector: 'app-purchases',
  imports: [RouterLink, PurchaseReturnRequest],
  templateUrl: './purchases.html',
  styleUrl: './purchases.scss',
})
export class PurchasesPage {
  private readonly api = inject(ClientPurchasesService);
  private readonly payments = inject(PaymentsService);
  private readonly navigation = inject(CheckoutNavigationService);
  private readonly route = inject(ActivatedRoute);
  private readonly destroy = inject(DestroyRef);
  private request?: Subscription;
  readonly id = signal<number | null>(null);
  readonly items = signal<PurchaseSummary[]>([]);
  readonly detail = signal<PurchaseDetail | null>(null);
  readonly total = signal(0);
  readonly estado = signal<PurchaseState | ''>('');
  readonly canal = signal<PurchaseChannel | ''>('');
  readonly loading = signal(false);
  readonly error = signal('');
  readonly expired = signal(false);
  readonly missing = signal(false);
  readonly continuing = signal<number | null>(null);
  readonly filtered = computed(() => !!this.estado() || !!this.canal());
  readonly more = computed(() => this.items().length < this.total());
  readonly money = formatBs;
  readonly saleReference = formatSaleReference;
  private failedAppend = false;
  constructor() {
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroy)).subscribe((params) => {
      const raw = params.get('id');
      this.id.set(raw === null ? null : /^[1-9]\d*$/.test(raw) ? Number(raw) : NaN);
      this.items.set([]);
      this.detail.set(null);
      this.total.set(0);
      this.load();
    });
    this.destroy.onDestroy(() => this.request?.unsubscribe());
  }
  filter(estado: string, canal: string): void {
    if (this.expired()) return;
    if (
      !['', 'PENDIENTE', 'COMPLETADA', 'ANULADA'].includes(estado) ||
      !['', 'DIGITAL', 'PRESENCIAL'].includes(canal)
    )
      return;
    this.estado.set(estado as PurchaseState | '');
    this.canal.set(canal as PurchaseChannel | '');
    this.items.set([]);
    this.total.set(0);
    this.load();
  }
  retry(): void {
    if (!this.loading() && !this.expired()) this.load(this.failedAppend);
  }
  loadMore(): void {
    if (!this.loading() && !this.expired() && this.more()) this.load(true);
  }
  private load(append = false): void {
    this.request?.unsubscribe();
    this.error.set('');
    this.expired.set(false);
    this.missing.set(false);
    this.failedAppend = append;
    const id = this.id();
    if (id !== null && (!Number.isSafeInteger(id) || id <= 0 || id > 2147483647)) {
      this.missing.set(true);
      this.error.set('Compra no encontrada.');
      return;
    }
    this.loading.set(true);
    if (id !== null) {
      this.request = this.api
        .detail(id)
        .pipe(
          timeout(25000),
          finalize(() => this.loading.set(false)),
        )
        .subscribe({
          next: (response) => {
            if (response.data.id_venta !== id) {
              this.error.set('No pudimos verificar esta compra.');
              return;
            }
            this.detail.set(response.data);
          },
          error: (error) => this.fail(error),
        });
    } else {
      this.request = this.api
        .list(this.estado(), this.canal(), append ? this.items().length : 0)
        .pipe(
          timeout(25000),
          finalize(() => this.loading.set(false)),
        )
        .subscribe({
          next: (response) => {
            // El backend pagina en orden descendente por fecha/id; conservar ese orden.
            const all = append ? [...this.items(), ...response.data.items] : response.data.items;
            this.items.set(
              all.filter(
                (item, index) =>
                  all.findIndex((other) => other.id_venta === item.id_venta) === index,
              ),
            );
            this.total.set(response.data.total);
          },
          error: (error) => this.fail(error),
        });
    }
  }
  private fail(error: HttpErrorResponse | Error): void {
    const status = error instanceof HttpErrorResponse ? error.status : 0;
    this.expired.set(status === 401);
    this.missing.set(status === 404);
    this.error.set(
      (
        {
          0: 'No pudimos conectar. Revisa tu conexión e inténtalo nuevamente.',
          401: 'Tu sesión expiró. Inicia sesión para consultar tus compras.',
          403: 'No tienes permiso para consultar estas compras.',
          404: 'Compra no encontrada.',
          500: 'No pudimos consultar tus compras. Inténtalo nuevamente.',
          503: 'El servicio no está disponible temporalmente.',
        } as Record<number, string>
      )[status] ?? 'No pudimos consultar tus compras. Inténtalo nuevamente.',
    );
  }
  date(value: string | null): string {
    if (!value) return 'Fecha no disponible';
    const date = new Date(/(Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`);
    return Number.isNaN(date.getTime())
      ? 'Fecha no disponible'
      : new Intl.DateTimeFormat('es-BO', {
          dateStyle: 'medium',
          timeStyle: 'short',
          timeZone: 'America/La_Paz',
        }).format(date);
  }
  tone(state: string): string {
    return ['COMPLETADA', 'APROBADO', 'APROBADA', 'PROCESADA'].includes(state)
      ? 'good'
      : ['RECHAZADO', 'RECHAZADA', 'ANULADA', 'CANCELADO', 'EXPIRADO'].includes(state)
        ? 'bad'
        : state === 'REEMBOLSADO'
          ? 'refund'
          : 'pending';
  }

  canContinue(purchase: PurchaseSummary): boolean {
    return purchase.canal === 'DIGITAL' && purchase.estado === 'PENDIENTE';
  }

  continuePurchase(purchase: PurchaseSummary): void {
    if (!this.canContinue(purchase) || this.continuing() !== null) return;
    this.continuing.set(purchase.id_venta);
    const key = crypto.randomUUID();
    this.api.detail(purchase.id_venta).pipe(
      timeout(25000),
      switchMap((response) => {
        const detail = response.data;
        if (detail.id_venta !== purchase.id_venta || detail.canal !== 'DIGITAL' || detail.estado !== 'PENDIENTE') {
          throw new Error('La compra ya no está pendiente.');
        }
        this.payments.saveSale({
          id: detail.id_venta,
          numero: detail.numero_venta,
          sucursal: detail.sucursal.nombre,
          canal: 'DIGITAL',
          estado: detail.estado,
          fecha: detail.fecha,
          subtotal: detail.subtotal,
          descuento: detail.descuento_total,
          total: detail.total,
          items: detail.productos.map((item) => ({
            id: item.id_variante_producto,
            nombre: item.nombre ?? `Variante #${item.id_variante_producto}`,
            talla: item.talla ?? '',
            color: item.color ?? '',
            cantidad: item.cantidad,
            precio: item.precio_unitario,
            subtotal: item.subtotal_linea,
          })),
        });
        const payment = detail.pago
          ? of({ success: true as const, data: detail.pago })
          : this.payments.start(detail.id_venta, 'TARJETA', key);
        return payment;
      }),
      tap((response) => {
        this.payments.saveAttempt(purchase.id_venta, {
          key,
          medio: 'TARJETA',
          idPago: response.data.id_pago,
        });
      }),
      switchMap((response) => this.payments.checkout(response.data.id_pago)),
      timeout(25000),
      finalize(() => this.continuing.set(null)),
    ).subscribe({
      next: (response) => {
        const payment = response.data.payment;
        if (payment.id_venta !== purchase.id_venta ||
            payment.medio !== 'TARJETA' ||
            payment.proveedor !== 'STRIPE' ||
            payment.entorno !== 'TEST' ||
            payment.estado !== 'PENDIENTE' ||
            !response.data.session_id.startsWith('cs_test_') ||
            payment.referencia_externa !== response.data.session_id) {
          this.error.set('La sesión de pago no corresponde a esta compra.');
          return;
        }
        try {
          this.navigation.go(response.data.url);
        } catch {
          this.error.set('No pudimos abrir el checkout de Stripe.');
        }
      },
      error: (error) => this.fail(error),
    });
  }
}
