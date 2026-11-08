import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Subscription, finalize, of, switchMap, tap, timeout } from 'rxjs';
import {
  ClientPurchasesService,
  PurchaseChannel,
  PurchaseDetail,
  PurchaseState,
  PurchaseSummary,
} from '../../core/services/client-purchases.service';
import { CheckoutNavigationService } from '../../core/services/checkout-navigation.service';
import { Payment, PaymentsService } from '../../core/services/payments.service';
import { OfflineService } from '../../core/services/offline.service';
import { OfflinePurchaseReceiptData } from '../../core/models/offline.model';
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
  private readonly offlineService = inject(OfflineService);
  private readonly navigation = inject(CheckoutNavigationService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroy = inject(DestroyRef);
  private request?: Subscription;
  private readonly reconciling = new Set<number>();
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
  readonly pendingLocal = signal<OfflinePurchaseReceiptData[]>([]);
  readonly isOffline = computed(() => {
    return !this.offlineService.isOnline() || (typeof navigator !== 'undefined' && !navigator.onLine);
  });
  readonly isOfflineDetail = computed(() => {
    const d = this.detail();
    if (!d) return false;
    return this.pendingLocal().some(
      (p) => p.id_venta_local === d.id_venta || p.numero_venta_local === d.numero_venta,
    );
  });
  readonly hasLocalPurchases = computed(() => this.pendingLocal().length > 0);
  readonly filteredPendingLocal = computed(() => {
    const estadoFilter = this.estado();
    const canalFilter = this.canal();
    const serverSaleNumbers = new Set(this.items().map((i) => i.numero_venta));
    return this.pendingLocal().filter((item) => {
      if (serverSaleNumbers.has(item.numero_venta_local)) return false;
      if (canalFilter && item.canal !== canalFilter) return false;
      if (estadoFilter) {
        if (estadoFilter === 'PENDIENTE') {
          return item.estado_venta === 'PENDIENTE' || item.estado_pago === 'PENDIENTE_VALIDACION';
        }
        return item.estado_venta === estadoFilter;
      }
      return true;
    });
  });
  readonly totalCount = computed(() => this.total() + this.filteredPendingLocal().length);
  readonly filtered = computed(() => !!this.estado() || !!this.canal());
  readonly more = computed(() => this.items().length < this.total());
  readonly money = formatBs;
  readonly saleReference = formatSaleReference;
  private failedAppend = false;
  constructor() {
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroy)).subscribe((params) => {
      const raw = params.get('id');
      if (raw === null) {
        const idVentaQuery = this.route.snapshot.queryParamMap.get('id_venta');
        if (idVentaQuery && /^[1-9]\d*$/.test(idVentaQuery)) {
          void this.router.navigate(['/mis-compras', idVentaQuery], {
            queryParams: this.route.snapshot.queryParams,
          });
          return;
        }
      }
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
      !['', 'PENDIENTE', 'COMPLETADA', 'ANULADA', 'RECHAZADA'].includes(estado) ||
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
    void this.loadPendingLocal();
    const id = this.id();
    if (id !== null && (!Number.isSafeInteger(id) || id <= 0 || id > 2147483647)) {
      this.missing.set(true);
      this.error.set('Compra no encontrada.');
      return;
    }
    this.loading.set(true);
    if (id !== null) {
      if (this.isOffline()) {
        void this.loadOfflineDetail(id);
        return;
      }
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
            this.reconcileStripePayment(response.data);
          },
          error: async (error: HttpErrorResponse | Error) => {
            const status = error instanceof HttpErrorResponse ? error.status : 0;
            if (status === 0 || status === 404 || this.isOffline()) {
              const loaded = await this.loadOfflineDetail(id);
              if (loaded) return;
            }
            this.fail(error);
          },
        });
    } else {
      if (this.isOffline()) {
        this.loading.set(false);
        this.items.set([]);
        this.total.set(0);
        this.error.set('');
        return;
      }
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
            for (const purchase of this.items()) this.reconcileStripePayment(purchase);
          },
          error: async (error: HttpErrorResponse | Error) => {
            const status = error instanceof HttpErrorResponse ? error.status : 0;
            if ((status === 0 || this.isOffline()) && this.id() === null) {
              await this.loadPendingLocal();
              if (this.pendingLocal().length > 0 || this.isOffline()) {
                this.items.set([]);
                this.total.set(0);
                this.error.set('');
                return;
              }
            }
            this.fail(error);
          },
        });
    }
  }
  private async loadPendingLocal(): Promise<void> {
    try {
      const rows = await this.offlineService.getPendingClientPurchases();
      this.pendingLocal.set(rows);
      if (rows.length > 0 && this.id() === null) {
        if (this.error().includes('conectar') || this.isOffline()) {
          this.error.set('');
        }
      }
    } catch {
      this.pendingLocal.set([]);
    }
  }
  private async loadOfflineDetail(id: number): Promise<boolean> {
    try {
      const receipt = await this.offlineService.getOfflinePurchaseReceipt(id);
      if (receipt) {
        const detail: PurchaseDetail = {
          id_venta: receipt.id_venta_local,
          numero_venta: receipt.numero_venta_local,
          fecha: receipt.fecha_registro,
          fecha_completada: null,
          canal: receipt.canal ?? 'DIGITAL',
          estado: 'PENDIENTE',
          subtotal: receipt.subtotal.toFixed(2),
          descuento_total: receipt.descuento_total.toFixed(2),
          total: receipt.total.toFixed(2),
          moneda: receipt.moneda,
          sucursal: {
            id_sucursal: receipt.sucursal.id_sucursal,
            nombre: receipt.sucursal.nombre,
          },
          pago: {
            id_pago: receipt.id_venta_local,
            medio: receipt.medio_pago,
            estado: 'PENDIENTE',
            monto: receipt.total.toFixed(2),
            moneda: receipt.moneda,
            fecha_aprobacion: null,
          },
          productos: receipt.detalles.map((d, idx) => ({
            id_detalle_venta: d.id_detalle_local ?? idx + 1,
            id_variante_producto: d.id_variante_producto,
            nombre: d.producto_nombre,
            talla: d.talla,
            color: d.color,
            cantidad: d.cantidad,
            precio_unitario: d.precio_unitario.toFixed(2),
            descuento_unitario: d.descuento_unitario.toFixed(2),
            subtotal_linea: d.subtotal_linea.toFixed(2),
            imagen: null,
          })),
          pagos: [
            {
              id_pago: receipt.id_venta_local,
              medio: receipt.medio_pago,
              estado: 'PENDIENTE',
              monto: receipt.total.toFixed(2),
              moneda: receipt.moneda,
              fecha_aprobacion: null,
            },
          ],
          devoluciones: [],
          reembolsos: [],
        };
        this.detail.set(detail);
        this.error.set('');
        this.loading.set(false);
        return true;
      }
    } catch {
      // ignore
    }
    this.loading.set(false);
    this.missing.set(true);
    this.error.set('Compra no encontrada.');
    return false;
  }
  private reconcileStripePayment(purchase: PurchaseSummary): void {
    const payment = purchase.pago;
    if (
      purchase.canal !== 'DIGITAL' ||
      purchase.estado !== 'PENDIENTE' ||
      payment?.medio !== 'TARJETA' ||
      payment.estado !== 'PENDIENTE' ||
      this.reconciling.has(payment.id_pago)
    )
      return;
    this.reconciling.add(payment.id_pago);
    this.payments
      .sync(payment.id_pago)
      .pipe(
        timeout(25000),
        takeUntilDestroyed(this.destroy),
        finalize(() => this.reconciling.delete(payment.id_pago)),
      )
      .subscribe({
        next: (response) => this.applyPaymentState(response.data),
        error: () => undefined,
      });
  }
  private applyPaymentState(payment: Payment): void {
    this.items.update((items) =>
      items.map((purchase) =>
        purchase.id_venta === payment.id_venta && purchase.pago?.id_pago === payment.id_pago
          ? {
              ...purchase,
              estado: payment.estado_venta,
              pago: {
                ...purchase.pago,
                estado: payment.estado,
                fecha_aprobacion: payment.fecha_aprobacion,
              },
            }
          : purchase,
      ),
    );
    this.detail.update((purchase) => {
      if (!purchase || purchase.id_venta !== payment.id_venta) return purchase;
      const updatedPayment = purchase.pago?.id_pago === payment.id_pago
        ? { ...purchase.pago, estado: payment.estado, fecha_aprobacion: payment.fecha_aprobacion }
        : purchase.pago;
      return {
        ...purchase,
        estado: payment.estado_venta,
        pago: updatedPayment,
        pagos: purchase.pagos.map((item) =>
          item.id_pago === payment.id_pago
            ? { ...item, estado: payment.estado, fecha_aprobacion: payment.fecha_aprobacion }
            : item,
        ),
      };
    });
  }
  private fail(error: HttpErrorResponse | Error): void {
    const status = error instanceof HttpErrorResponse ? error.status : 0;
    if ((status === 0 || this.isOffline()) && (this.pendingLocal().length > 0 || this.isOffline()) && this.id() === null) {
      this.error.set('');
      return;
    }
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
    try {
      this.navigation.prepare?.();
    } catch {
      this.error.set(
        'El navegador bloqueó la ventana de Stripe Checkout. Habilita las ventanas emergentes para continuar.',
      );
      return;
    }
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
          this.navigation.close?.();
          this.error.set('La sesión de pago no corresponde a esta compra.');
          return;
        }
        try {
          this.navigation.go(response.data.url);
          void this.router
            .navigate(['/compra', purchase.id_venta, 'pago'])
            .then((navigated) => {
              if (!navigated) {
                this.navigation.close?.();
                this.error.set('No pudimos volver a la pantalla de pago.');
              }
            })
            .catch(() => {
              this.navigation.close?.();
              this.error.set('No pudimos volver a la pantalla de pago.');
            });
        } catch {
          this.navigation.close();
          this.error.set('No pudimos abrir el checkout de Stripe.');
        }
      },
      error: (error) => {
        this.navigation.close();
        this.fail(error);
      },
    });
  }
}
