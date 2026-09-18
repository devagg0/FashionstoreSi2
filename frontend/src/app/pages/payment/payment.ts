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
import { Observable, finalize, map, of, switchMap, tap, timeout } from 'rxjs';
import {
  Payment,
  PaymentAction,
  PaymentAttempt,
  PaymentMethod,
  PaymentResponse,
  PaymentsService,
} from '../../core/services/payments.service';
import { CheckoutNavigationService } from '../../core/services/checkout-navigation.service';
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
  readonly id = Number(this.route.snapshot.paramMap.get('id'));
  readonly sale = signal(this.api.sale(this.id));
  readonly attempt = signal(this.api.attempt(this.id));
  readonly payment = signal<Payment | null>(null);
  readonly method = signal<PaymentMethod>(this.attempt()?.medio ?? 'TARJETA');
  readonly busy = signal(false);
  readonly loading = signal(false);
  readonly error = signal('');
  readonly returnMessage = signal('');
  readonly redirecting = signal(false);
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
  readonly methods = computed<PaymentMethod[]>(() =>
    this.sale()?.canal === 'PRESENCIAL'
      ? this.session.getUser()?.rol.toUpperCase() === 'CAJERO'
        ? ['EFECTIVO', 'QR', 'TARJETA']
        : []
      : this.session.getUser()?.rol.toUpperCase() === 'CLIENTE'
        ? ['QR', 'TARJETA']
        : [],
  );
  readonly terminal = computed(() => !!this.payment() && this.payment()!.estado !== 'PENDIENTE');
  readonly canPay = computed(
    () =>
      !!this.sale() &&
      !this.busy() &&
      !this.loading() &&
      !this.expired() &&
      !this.uncertain() &&
      this.status() === 'PENDIENTE' &&
      !this.terminal() &&
      this.methods().includes(this.method()),
  );
  readonly back = computed(() =>
    this.sale()?.canal === 'PRESENCIAL'
      ? '/staff/ventas/nueva'
      : this.completed()
        ? '/catalogo'
        : '/compra/' + this.id,
  );

  constructor() {
    if (!Number.isInteger(this.id) || this.id <= 0 || this.id > 2147483647) {
      this.error.set('La venta solicitada no es válida.');
      return;
    } else if (!this.sale())
      this.error.set(
        'No encontramos el resumen de esta venta. Abre el pago desde tu compra o desde la venta en caja.',
      );
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
    } else if (this.attempt()?.idPago) this.refresh();
    else if (this.attempt()) this.uncertain.set(true);
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
    if (!this.persist(attempt)) return;
    this.execute(this.process(attempt));
  }
  prepareQr(): void {
    if (!this.canPay() || this.method() !== 'QR') return;
    const attempt = this.attempt() ?? { key: crypto.randomUUID(), medio: 'QR' as const };
    if (!this.persist(attempt)) return;
    this.execute(this.process(attempt, true));
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
          map((checkout) => {
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
            } catch (error) {
              this.redirecting.set(false);
              throw error;
            }
            return { success: true as const, data: checkout.data.payment };
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
      // Sin referencia, sync no puede encontrar la sesión. Repetir su creación
      // con el mismo pago conserva la idempotencia que administra el backend.
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
  private accept(payment: Payment): void {
    if (payment.id_venta !== this.id) throw new Error('El pago no corresponde a esta venta.');
    this.payment.set(payment);
    if (payment.estado_venta === 'COMPLETADA') this.returnMessage.set('');
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
    // Si falla storage despues de una respuesta, conservar el id en memoria y bloquear nuevos intentos.
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
