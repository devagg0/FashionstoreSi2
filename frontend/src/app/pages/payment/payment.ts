import { HttpErrorResponse } from '@angular/common/http';
import {
  Component,
  DestroyRef,
  ElementRef,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { Observable, finalize, of, switchMap, tap, timeout } from 'rxjs';
import { OfflinePurchaseReceiptData } from '../../core/models/offline.model';
import { CheckoutNavigationService } from '../../core/services/checkout-navigation.service';
import { ClientCheckoutService } from '../../core/services/client-checkout.service';
import { OfflineService } from '../../core/services/offline.service';
import {
  Payment,
  PaymentAction,
  PaymentAttempt,
  PaymentMethod,
  PaymentResponse,
  PaymentSale,
  PaymentsService,
} from '../../core/services/payments.service';
import { SessionService } from '../../core/services/session.service';
import { formatBs } from '../../core/utils/money';

@Component({
  selector: 'app-payment',
  imports: [RouterLink],
  templateUrl: './payment.html',
  styleUrl: './payment.scss',
})
export class PaymentPage {
  private readonly api = inject(PaymentsService);
  private readonly navigation = inject(CheckoutNavigationService);
  private readonly session = inject(SessionService);
  private readonly destroy = inject(DestroyRef);
  private readonly route = inject(ActivatedRoute);
  private readonly offlineService = inject(OfflineService);
  private readonly checkoutService = inject(ClientCheckoutService);

  readonly id = Number(this.route.snapshot.paramMap.get('id'));
  readonly sale = signal(this.resolveSale());
  readonly attempt = signal(this.api.attempt(this.id));
  readonly payment = signal<Payment | null>(null);
  readonly method = signal<PaymentMethod>(this.attempt()?.medio ?? 'TARJETA');
  readonly busy = signal(false);
  readonly loading = signal(false);
  readonly error = signal('');
  readonly returnMessage = signal('');
  readonly redirecting = signal(false);
  readonly offlineReceipt = signal<OfflinePurchaseReceiptData | null>(null);

  readonly isOfflineMode = computed(
    () =>
      !this.offlineService.isOnline() ||
      (typeof navigator !== 'undefined' && !navigator.onLine),
  );

  readonly qrCells = computed(() => {
    const p = this.payment();
    if (!p || p.medio !== 'QR') return [];
    const reference = `FashionStore|pago:${p.id_pago}|monto:${p.monto}|operacion:${p.clave_idempotencia}`;
    let hash = 2166136261;
    for (const char of reference) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619);
    const cells: { x: number; y: number }[] = [];
    for (let y = 0; y < 25; y++)
      for (let x = 0; x < 25; x++) {
        const corner = [
          [0, 0],
          [18, 0],
          [0, 18],
        ].find(([cx, cy]) => x >= cx && x < cx + 8 && y >= cy && y < cy + 8);
        let filled: boolean;
        if (corner) {
          const dx = x - corner[0],
            dy = y - corner[1];
          filled =
            dx < 7 &&
            dy < 7 &&
            (dx === 0 ||
              dy === 0 ||
              dx === 6 ||
              dy === 6 ||
              (dx >= 2 && dx <= 4 && dy >= 2 && dy <= 4));
        } else {
          hash ^= hash << 13;
          hash ^= hash >>> 17;
          hash ^= hash << 5;
          filled = (hash & 1) === 1;
        }
        if (filled) cells.push({ x: x + 2, y: y + 2 });
      }
    return cells;
  });

  readonly expired = signal(false);
  readonly uncertain = signal(false);
  readonly action = signal<PaymentAction>('APROBADO');
  readonly dialog = viewChild<ElementRef<HTMLDialogElement>>('confirmation');
  private returnFocus: HTMLElement | null = null;
  readonly money = formatBs;
  readonly status = computed(
    () => this.payment()?.estado_venta ?? this.sale()?.estado ?? 'PENDIENTE',
  );
  readonly completed = computed(() => this.status() === 'COMPLETADA');
  readonly rejected = computed(() => this.status() === 'RECHAZADA');
  readonly methods = computed<PaymentMethod[]>(() =>
    this.sale()?.canal === 'PRESENCIAL'
      ? this.session.getUser()?.rol.toUpperCase() === 'CAJERO'
        ? ['EFECTIVO', 'QR', 'TARJETA']
        : []
      : this.session.getUser()?.rol.toUpperCase() === 'CLIENTE'
        ? ['QR', 'TARJETA']
        : [],
  );
  readonly terminal = computed(() => !this.offlineReceipt() && !!this.payment() && this.payment()!.estado !== 'PENDIENTE');
  readonly canPay = computed(
    () =>
      !!this.sale() &&
      !this.busy() &&
      !this.loading() &&
      !this.expired() &&
      !this.uncertain() &&
      this.status() === 'PENDIENTE' &&
      !this.terminal() &&
      !this.offlineReceipt() &&
      this.methods().includes(this.method()),
  );
  readonly back = computed(() =>
    this.sale()?.canal === 'PRESENCIAL'
      ? '/staff/ventas/nueva'
      : this.completed() || !!this.offlineReceipt()
        ? '/catalogo'
        : '/compra/' + this.id,
  );

  constructor() {
    if (!Number.isInteger(this.id) || this.id <= 0 || this.id > 2147483647) {
      this.error.set('La venta solicitada no es válida.');
      return;
    } else if (!this.sale()) {
      this.error.set(
        'No encontramos el resumen de esta venta. Abre el pago desde tu compra o desde la venta en caja.',
      );
    }

    // Comprobar si ya existe un comprobante offline para esta venta
    void this.offlineService.getOfflinePurchaseReceipt(this.id).then((storedReceipt) => {
      if (storedReceipt) {
        this.offlineReceipt.set(storedReceipt);
        const restoredPayment: Payment = {
          id_pago: storedReceipt.id_venta_local,
          id_venta: this.id,
          medio: storedReceipt.medio_pago,
          proveedor: storedReceipt.medio_pago === 'TARJETA' ? 'STRIPE' : 'MANUAL',
          entorno: 'LOCAL',
          estado: storedReceipt.medio_pago === 'EFECTIVO' ? 'APROBADO' : 'PENDIENTE',
          estado_venta: 'PENDIENTE',
          monto: String(storedReceipt.total),
          moneda: 'BOB',
          referencia_externa: storedReceipt.referencia_pago,
          clave_idempotencia: storedReceipt.uuid_venta_offline,
          fecha_aprobacion: storedReceipt.medio_pago === 'EFECTIVO' ? storedReceipt.fecha_registro : null,
          created_at: storedReceipt.fecha_registro,
          updated_at: storedReceipt.fecha_registro,
        };
        this.payment.set(restoredPayment);
        this.sale.update((curSale) => {
          if (!curSale) return curSale;
          const updated = {
            ...curSale,
            id: storedReceipt.id_venta_local,
            numero: storedReceipt.numero_venta_local,
            estado: 'PENDIENTE' as const,
          };
          this.api.saveSale(updated);
          return updated;
        });
      }
    });

    const returnKind = this.route.snapshot.queryParamMap?.get('checkout');
    if (returnKind === 'success' || returnKind === 'cancel') {
      const raw = this.route.snapshot.queryParamMap.get('payment_id');
      const paymentId = raw && /^[1-9]\d*$/.test(raw) ? Number(raw) : 0;
      if (
        !Number.isSafeInteger(paymentId) ||
        paymentId <= 0 ||
        paymentId > 2147483647 ||
        (this.attempt()?.idPago && this.attempt()!.idPago !== paymentId)
      ) {
        this.error.set(
          'El retorno de Stripe no corresponde al intento guardado. Consulta tu pago.',
        );
        return;
      }
      this.returnMessage.set(
        returnKind === 'cancel'
          ? 'Pago cancelado. Tu compra continúa pendiente.'
          : 'Verificando el resultado del pago con Stripe…',
      );
      this.loading.set(true);
      this.execute(
        this.api.get(paymentId).pipe(
          tap((response) => {
            if (response.data.medio !== 'TARJETA' || response.data.id_pago !== paymentId)
              throw new Error('Retorno inválido');
            this.accept(response.data);
          }),
          switchMap(() => this.api.sync(paymentId)),
        ),
      );
    } else if (this.attempt()?.idPago) {
      if (
        this.attempt()!.medio === 'TARJETA' &&
        (this.navigation.isActive?.() ?? false)
      ) {
        this.redirecting.set(true);
        this.returnMessage.set('Verificando el resultado del pago con Stripe…');
        this.execute(this.monitorCheckout(this.attempt()!.idPago!));
      } else this.refresh();
    } else if (this.attempt()) {
      if (!this.isOfflineMode()) {
        this.uncertain.set(true);
      }
    }
  }

  private resolveSale(): PaymentSale | null {
    const sale = this.api.sale(this.id);
    if (sale) return sale;
    const offlineSale = this.checkoutService.offlineSale(this.id);
    if (offlineSale) {
      const pres = this.checkoutService.presentation(this.id);
      const paymentSale: PaymentSale = {
        id: offlineSale.id_venta,
        numero: offlineSale.numero_venta,
        sucursal: pres?.sucursal ?? `Sucursal #${offlineSale.id_sucursal}`,
        canal: 'DIGITAL',
        estado: offlineSale.estado,
        fecha: null,
        subtotal: offlineSale.subtotal,
        descuento: offlineSale.descuento_total,
        total: offlineSale.total,
        items: offlineSale.items.map((it) => {
          const p = pres?.items.find((row) => row.id_variante_producto === it.id_variante_producto);
          return {
            id: it.id_variante_producto,
            nombre: p?.nombre ?? `Variante #${it.id_variante_producto}`,
            talla: p?.talla,
            color: p?.color,
            imagen: p?.imagen,
            cantidad: it.cantidad,
            precio: it.precio_unitario,
            subtotal: it.subtotal_linea,
          };
        }),
      };
      this.api.saveSale(paymentSale);
      return paymentSale;
    }
    return null;
  }

  choose(method: PaymentMethod): void {
    if (this.busy() || this.attempt() || !this.canPay() || !this.methods().includes(method)) return;
    this.method.set(method);
  }

  open(action: PaymentAction): void {
    if (!this.canPay()) return;
    this.action.set(action);
    this.returnFocus =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const dialog = this.dialog()?.nativeElement;
    if (dialog?.showModal) dialog.showModal();
    else dialog?.setAttribute('open', '');
  }

  close(): void {
    const dialog = this.dialog()?.nativeElement;
    if (dialog?.close) dialog.close();
    else dialog?.removeAttribute('open');
    this.returnFocus?.focus();
  }

  confirm(): void {
    if (!this.canPay()) return;
    this.close();

    const attempt = this.attempt() ?? {
      key: crypto.randomUUID(),
      medio: this.method(),
      ...(this.method() === 'EFECTIVO' ? { action: this.action() } : {}),
    };
    if (!this.persist(attempt)) {
      if (this.method() === 'TARJETA') this.navigation.close?.();
      return;
    }

    if (this.isOfflineMode()) {
      if (this.sale()?.canal === 'PRESENCIAL') {
        this.confirmOfflineCashierSale(attempt);
      } else {
        this.confirmOfflinePurchase(attempt);
      }
      return;
    }

    if (this.method() === 'TARJETA') {
      try {
        this.navigation.prepare?.();
      } catch (error) {
        this.fail(error instanceof Error ? error : new Error('No pudimos abrir Stripe Checkout.'));
        return;
      }
    }

    this.execute(this.process(attempt));
  }

  prepareQr(): void {
    if (!this.canPay() || this.method() !== 'QR') return;
    const attempt = this.attempt() ?? { key: crypto.randomUUID(), medio: 'QR' as const };
    if (!this.persist(attempt)) return;

    if (this.isOfflineMode()) {
      const sale = this.sale();
      const offlinePayment: Payment = {
        id_pago: this.id,
        id_venta: this.id,
        medio: 'QR',
        proveedor: 'MANUAL',
        entorno: 'LOCAL',
        estado: 'PENDIENTE',
        estado_venta: 'PENDIENTE',
        monto: sale?.total ?? '0.00',
        moneda: 'BOB',
        referencia_externa: null,
        clave_idempotencia: attempt.key,
        fecha_aprobacion: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      this.accept(offlinePayment);
      return;
    }

    this.execute(this.process(attempt, true));
  }

  private confirmOfflinePurchase(attempt: PaymentAttempt): void {
    const currentSale = this.sale();
    if (!currentSale) {
      this.error.set('No se encontró el resumen de esta venta.');
      return;
    }

    this.busy.set(true);
    this.error.set('');

    const presentation = this.checkoutService.presentation(this.id);
    const offlineSale = this.checkoutService.offlineSale(this.id);
    const branchId = presentation?.id_sucursal ?? offlineSale?.id_sucursal ?? 1;

    this.offlineService
      .registerClientOfflinePurchase({
        uuid: attempt.key,
        idSucursal: branchId,
        medioPago: attempt.medio === 'QR' ? 'QR' : 'TARJETA',
        items: currentSale.items.map((it) => ({
          id_variante_producto: it.id,
          cantidad: it.cantidad,
          precio_unitario: Number(it.precio),
        })),
      })
      .then((result) => {
        this.busy.set(false);
        if (!result.success || !result.receipt) {
          this.error.set(
            result.message || 'No fue posible registrar la compra digital en modo offline.',
          );
          return;
        }

        this.offlineReceipt.set(result.receipt);

        this.sale.update((prev) => {
          if (!prev) return prev;
          const updated = {
            ...prev,
            id: result.id_venta_local,
            numero: result.numero_venta_local,
            estado: 'PENDIENTE' as const,
          };
          this.api.saveSale(updated);
          return updated;
        });

        const simulatedPayment: Payment = {
          id_pago: result.id_venta_local,
          id_venta: this.id,
          medio: attempt.medio,
          proveedor: attempt.medio === 'TARJETA' ? 'STRIPE' : 'MANUAL',
          entorno: 'LOCAL',
          estado: 'PENDIENTE',
          estado_venta: 'PENDIENTE',
          monto: currentSale.total,
          moneda: 'BOB',
          referencia_externa: result.receipt.referencia_pago,
          clave_idempotencia: attempt.key,
          fecha_aprobacion: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };

        this.accept(simulatedPayment);
      })
      .catch((err: unknown) => {
        this.busy.set(false);
        this.error.set(
          err instanceof Error
            ? err.message
            : 'Ocurrió un error al registrar la compra digital offline.',
        );
      });
  }

  private confirmOfflineCashierSale(attempt: PaymentAttempt): void {
    const currentSale = this.sale();
    if (!currentSale) {
      this.error.set('No se encontró el resumen de esta venta.');
      return;
    }

    this.busy.set(true);
    this.error.set('');

    const branchId = currentSale.id_sucursal ?? 1;

    this.offlineService
      .registerCashierOfflineSale({
        uuid: attempt.key,
        idSucursal: branchId,
        idReserva: currentSale.id_reserva ?? null,
        medioPago: attempt.medio,
        items: currentSale.items.map((it) => ({
          id_variante_producto: it.id,
          cantidad: it.cantidad,
          precio_unitario: Number(it.precio),
        })),
      })
      .then((result) => {
        this.busy.set(false);
        if (!result.success || !result.receipt) {
          this.error.set(
            result.message || 'No fue posible registrar la venta presencial en modo offline.',
          );
          return;
        }

        this.offlineReceipt.set(result.receipt);

        this.sale.update((prev) => {
          if (!prev) return prev;
          const updated = {
            ...prev,
            id: result.id_venta_local,
            numero: result.numero_venta_local,
            estado: 'PENDIENTE' as const,
          };
          this.api.saveSale(updated);
          return updated;
        });

        const cashierPayment: Payment = {
          id_pago: result.id_venta_local,
          id_venta: this.id,
          medio: attempt.medio,
          proveedor: attempt.medio === 'TARJETA' ? 'STRIPE' : 'MANUAL',
          entorno: 'LOCAL',
          estado: attempt.medio === 'EFECTIVO' ? 'APROBADO' : 'PENDIENTE',
          estado_venta: 'PENDIENTE',
          monto: currentSale.total,
          moneda: 'BOB',
          referencia_externa: result.receipt.referencia_pago,
          clave_idempotencia: attempt.key,
          fecha_aprobacion: attempt.medio === 'EFECTIVO' ? new Date().toISOString() : null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };

        this.accept(cashierPayment);
      })
      .catch((err: unknown) => {
        this.busy.set(false);
        this.error.set(
          err instanceof Error
            ? err.message
            : 'Ocurrió un error al registrar la venta presencial offline.',
        );
      });
  }

  private process(attempt: PaymentAttempt, prepareOnly = false): Observable<PaymentResponse> {
    const start = attempt.idPago
      ? this.api.get(attempt.idPago)
      : this.api.start(this.id, attempt.medio, attempt.key);
    return start.pipe(
      tap((response) => this.accept(response.data)),
      switchMap((response) => {
        if (
          response.data.estado !== 'PENDIENTE' ||
          response.data.estado_venta !== 'PENDIENTE' ||
          prepareOnly
        )
          return of(response);
        if (attempt.medio === 'QR') return this.api.qr(response.data.id_pago);
        if (attempt.medio === 'EFECTIVO')
          return this.api.manual(response.data.id_pago, attempt.action ?? 'APROBADO');
        return this.api.checkout(response.data.id_pago).pipe(
          switchMap((checkout) => {
            if (
              checkout.data.payment.id_pago !== response.data.id_pago ||
              checkout.data.payment.medio !== 'TARJETA' ||
              checkout.data.payment.proveedor !== 'STRIPE' ||
              checkout.data.payment.entorno !== 'TEST' ||
              checkout.data.payment.estado !== 'PENDIENTE' ||
              !checkout.data.session_id.startsWith('cs_test_') ||
              checkout.data.payment.referencia_externa !== checkout.data.session_id
            ) {
              throw new Error('Checkout no corresponde a este pago TEST.');
            }
            this.accept(checkout.data.payment);
            if (!this.persist(this.attempt()!)) throw new Error('No se pudo guardar el pago');
            this.redirecting.set(true);
            try {
              this.navigation.go(checkout.data.url);
              this.returnMessage.set('Verificando el resultado del pago con Stripe…');
            } catch (error) {
              this.redirecting.set(false);
              this.navigation.close();
              throw error;
            }
            return this.monitorCheckout(checkout.data.payment.id_pago);
          }),
        );
      }),
    );
  }

  retry(): void {
    if (this.busy() || this.loading() || this.expired() || this.completed() || !this.attempt())
      return;
    const attempt = this.attempt()!;
    if (!this.persist(attempt)) return;
    if (attempt.idPago) {
      if (attempt.medio === 'TARJETA' && this.payment()?.referencia_externa === null) {
        this.execute(this.process(attempt));
        return;
      }
      this.refresh(attempt.medio === 'TARJETA');
      return;
    }
    this.execute(this.process(attempt, attempt.medio === 'QR'));
  }

  refresh(sync = false): void {
    const id = this.attempt()?.idPago ?? this.payment()?.id_pago;
    if (!id || this.busy() || this.loading() || this.expired()) return;
    this.loading.set(true);
    this.execute(sync && this.method() === 'TARJETA' ? this.api.sync(id) : this.api.get(id));
  }

  recover(value: string): void {
    const id = Number(value);
    if (!Number.isInteger(id) || id <= 0 || this.busy() || this.loading() || this.expired()) return;
    this.execute(this.api.get(id));
  }

  newAttempt(): void {
    if (this.busy() || this.loading() || !this.terminal() || this.status() !== 'PENDIENTE') return;
    try {
      this.api.clearAttempt(this.id);
    } catch {
      this.error.set('Habilita el almacenamiento antes de iniciar otro intento.');
      return;
    }
    this.attempt.set(null);
    this.payment.set(null);
    this.uncertain.set(false);
    this.error.set('');
    this.returnMessage.set('');
    this.offlineReceipt.set(null);
  }

  private execute(request: Observable<PaymentResponse>): void {
    this.busy.set(true);
    this.error.set('');
    request
      .pipe(
        timeout(25000),
        tap((response) => this.accept(response.data)),
        takeUntilDestroyed(this.destroy),
        finalize(() => {
          this.busy.set(this.redirecting());
          this.loading.set(false);
        }),
      )
      .subscribe({ next: () => this.uncertain.set(false), error: (error) => this.fail(error) });
  }

  private monitorCheckout(paymentId: number): Observable<PaymentResponse> {
    return this.api.monitorStripe(paymentId, () => this.navigation.isActive?.() ?? false).pipe(
      tap((response) => {
        const terminal =
          response.data.estado !== 'PENDIENTE' ||
          response.data.estado_venta !== 'PENDIENTE';
        if (terminal || !(this.navigation.isActive?.() ?? false)) {
          this.redirecting.set(false);
          const rejected =
            response.data.estado === 'RECHAZADO' ||
            response.data.estado_venta === 'RECHAZADA';
          if (rejected) this.navigation.close?.();
        }
      }),
    );
  }

  private accept(payment: Payment): void {
    if (payment.id_venta !== this.id) throw new Error('El pago no corresponde a esta venta.');
    this.payment.set(payment);
    const currentSale = this.sale();
    if (currentSale && currentSale.estado !== payment.estado_venta) {
      const updatedSale = { ...currentSale, estado: payment.estado_venta };
      this.sale.set(updatedSale);
      this.api.saveSale(updatedSale);
    }
    if (payment.estado_venta === 'COMPLETADA') this.returnMessage.set('');
    else if (payment.estado === 'RECHAZADO' || payment.estado_venta === 'RECHAZADA')
      this.returnMessage.set(
        'Stripe rechazó el pago. La venta fue rechazada y el stock comprometido quedó liberado.',
      );
    else if (this.returnMessage().startsWith('Verificando'))
      this.returnMessage.set(
        'Tu pago continúa pendiente. Consulta su estado antes de volver a intentar.',
      );
    this.method.set(payment.medio);
    const attempt = {
      key: payment.clave_idempotencia,
      medio: payment.medio,
      idPago: payment.id_pago,
      ...(payment.medio === 'EFECTIVO' ? { action: this.attempt()?.action } : {}),
    };
    if (!this.persist(attempt)) throw new Error('No se pudo conservar el intento de pago.');
  }

  private persist(attempt: PaymentAttempt): boolean {
    this.attempt.set(attempt);
    try {
      this.api.saveAttempt(this.id, attempt);
      return true;
    } catch {
      this.error.set(
        'No se pudo guardar el intento. Habilita el almacenamiento de esta pestaña para continuar.',
      );
      this.uncertain.set(true);
      return false;
    }
  }

  private fail(error: HttpErrorResponse | Error): void {
    if (this.redirecting()) this.redirecting.set(false);
    this.navigation.close?.();
    const status = error instanceof HttpErrorResponse ? error.status : 0;
    this.expired.set(status === 401);
    this.uncertain.set(!!this.attempt() && (status === 0 || status >= 500 || status === 409));
    this.error.set(
      (
        {
          0: 'La conexión se interrumpió o agotó el tiempo de espera. Conservamos tu intento; verifica su estado antes de continuar.',
          401: 'Tu sesión expiró. Inicia sesión para recuperar tu pago.',
          403: 'No tienes permiso para pagar esta venta.',
          404: 'No se encontró la venta o el pago solicitado.',
          409: 'La venta ya fue completada, tiene un pago activo o el intento presenta un conflicto. Consulta el estado del pago.',
          422: 'Este método no está disponible o los datos del intento no son válidos.',
          503: 'El resultado de Stripe es incierto. Sincroniza el mismo pago antes de iniciar otro intento.',
        } as Record<number, string>
      )[status] ??
        'No pudimos verificar el pago. Conservamos el intento para reintentar con seguridad.',
    );
  }

  date(value: string | null): string {
    if (!value) return 'No disponible';
    const date = new Date(/(Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`);
    return Number.isNaN(date.getTime())
      ? 'No disponible'
      : new Intl.DateTimeFormat('es-BO', {
          dateStyle: 'medium',
          timeStyle: 'short',
          timeZone: 'America/La_Paz',
        }).format(date);
  }
}
