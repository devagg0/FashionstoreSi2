import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, computed, effect, inject, input, output, signal, untracked } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { finalize, forkJoin, of, timeout } from 'rxjs';
import { PurchaseDetail, PurchaseItem } from '../../../core/services/client-purchases.service';
import {
  DeliveryModality,
  ExchangeOptionLine,
  ExchangeOptionsData,
  ReplacementVariant,
  ReturnDetail,
  ReturnKind,
  ReturnRequest,
  ReturnsService,
  returnDate,
  returnLabel,
  returnReference,
  returnStateLabel,
  returnTone,
} from '../../../core/services/returns.service';
import { OfflineService } from '../../../core/services/offline.service';
import { ReturnModal } from '../../../shared/components/return-modal/return-modal';
import { formatBs } from '../../../core/utils/money';

@Component({
  selector: 'app-purchase-return-request',
  imports: [FormsModule, ReturnModal, RouterLink],
  templateUrl: './return-request.html',
  styleUrl: './return-request.scss',
})
export class PurchaseReturnRequest {
  readonly purchase = input.required<PurchaseDetail>();
  readonly changed = output<void>();
  private readonly api = inject(ReturnsService);
  private readonly offlineService = inject(OfflineService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroy = inject(DestroyRef);
  private stripeVerificationAttempted = false;

  readonly kind = signal<ReturnKind | null>(null);
  readonly busy = signal(false);
  readonly checking = signal(false);
  readonly verified = signal(false);
  readonly error = signal('');
  readonly success = signal('');
  readonly selected = signal<ReturnDetail | null>(null);
  readonly history = signal<ReturnDetail[]>([]);
  readonly frozen = signal(false);
  readonly quantities = signal<Record<number, number>>({});
  readonly replacements = signal<Record<number, number>>({});
  readonly modalidadEntrega = signal<DeliveryModality | null>(null);
  readonly reason = signal('');

  // Opciones de cambio y validación de 72 horas
  readonly optionsData = signal<ExchangeOptionsData | null>(null);
  readonly loadingOptions = signal(false);
  readonly optionsError = signal('');

  // CU16 Modalidad de entrega seleccionada por el cliente tras aceptación inicial
  readonly clientSelectedModality = signal<DeliveryModality | null>(null);
  readonly savingModality = signal(false);

  // CU17 Pago de diferencia con Stripe
  readonly payingStripe = signal(false);
  readonly verifyingStripe = signal(false);
  readonly stripePendingReconciliation = signal(false);
  readonly paymentSuccess = signal('');
  readonly paymentError = signal('');

  private attempt?: { fingerprint: string; key: string; body: ReturnRequest };
  readonly reference = returnReference;
  readonly label = returnLabel;
  readonly stateLabel = returnStateLabel;
  readonly tone = returnTone;
  readonly date = returnDate;
  readonly money = formatBs;

  readonly isOnline = computed(() => {
    return this.offlineService.isOnline() && (typeof navigator === 'undefined' || navigator.onLine);
  });

  readonly canCancel = computed(
    () =>
      this.purchase().estado === 'PENDIENTE' &&
      !this.purchase().devoluciones.some(
        (x) => x.tipo === 'CANCELACION' && x.estado !== 'RECHAZADA',
      ) &&
      !this.history().some((x) => x.tipo === 'CANCELACION' && x.estado !== 'RECHAZADA'),
  );

  readonly isWithin72hLocal = computed(() => {
    const p = this.purchase();
    if (p.estado !== 'COMPLETADA') return false;
    const completedAt = p.fecha_completada || p.fecha;
    if (!completedAt) return false;
    const date = new Date(/(Z|[+-]\d{2}:\d{2})$/.test(completedAt) ? completedAt : `${completedAt}Z`);
    if (Number.isNaN(date.getTime())) return false;
    const elapsedHours = (Date.now() - date.getTime()) / (1000 * 60 * 60);
    return elapsedHours <= 72 && elapsedHours >= 0;
  });

  readonly dentroPlazo72h = computed(() => {
    const opts = this.optionsData();
    if (opts) return opts.dentro_plazo_72h;
    return this.isWithin72hLocal();
  });

  readonly plazoExpiradoMensaje = computed(() => {
    if (this.purchase().estado !== 'COMPLETADA') return '';
    if (this.optionsData() && !this.optionsData()?.dentro_plazo_72h) {
      return (
        this.optionsData()?.motivo_no_elegible ||
        'El plazo máximo de 72 horas posteriores a la finalización de la compra ha expirado para solicitar cambios o devoluciones.'
      );
    }
    if (!this.dentroPlazo72h()) {
      return 'El plazo máximo de 72 horas posteriores a la finalización de la compra ha expirado para solicitar cambios o devoluciones.';
    }
    return '';
  });

  readonly horasRestantes = computed(() => {
    return this.optionsData()?.horas_restantes ?? null;
  });

  readonly variantesDisponibles = computed(() => {
    return this.optionsData()?.variantes_reemplazo_disponibles ?? [];
  });

  readonly lineasCompra = computed(() => {
    return this.optionsData()?.lineas_compra ?? [];
  });

  readonly units = computed(() => {
    const items = this.purchase()?.productos || [];
    const quantities = this.quantities();
    return items.reduce((sum, item) => {
      const maxAvail = this.available(item);
      const raw = quantities[item.id_detalle_venta] || 0;
      return sum + Math.max(0, Math.min(raw, maxAvail));
    }, 0);
  });

  readonly economicSummary = computed(() => {
    const kind = this.kind();
    if (!kind || kind === 'CANCELACION') return null;
    const quantities = this.quantities();
    const replacements = this.replacements();
    const lineas = this.lineasCompra();
    const variantes = this.variantesDisponibles();
    const items = this.purchase().productos;
    const saleTotal = Number(this.purchase().total) || 0;

    let totalOriginal = 0;
    let totalReemplazo = 0;

    for (const item of items) {
      const maxAvail = this.available(item);
      const rawQty = quantities[item.id_detalle_venta] || 0;
      const qty = Math.max(0, Math.min(rawQty, maxAvail));
      if (qty <= 0) continue;
      const optLine = lineas.find((l) => l.id_detalle_venta === item.id_detalle_venta);
      const unitVal = optLine != null && optLine.valor_unitario_reconocido != null
        ? Number(optLine.valor_unitario_reconocido)
        : Math.max(0, Number(item.precio_unitario) - Number(item.descuento_unitario));
      totalOriginal += unitVal * qty;

      if (kind === 'CAMBIO') {
        const replId = replacements[item.id_detalle_venta];
        const replVar = variantes.find((v) => v.id_variante_producto === replId);
        const replPrice = replVar ? Number(replVar.precio_unitario) : 0;
        totalReemplazo += replPrice * qty;
      }
    }

    // No superar lo efectivamente pagado por la compra original
    totalOriginal = Math.min(totalOriginal, saleTotal);

    if (kind === 'DEVOLUCION') {
      return {
        moneda: this.purchase().moneda || 'BOB',
        totalOriginal,
        totalReemplazo: 0,
        diferencia: 0,
        saldoAFavor: totalOriginal,
        importeAdicional: 0,
        resultado: 'SALDO_A_FAVOR' as const,
      };
    }

    const diferencia = totalReemplazo - totalOriginal;
    const importeAdicional = diferencia > 0 ? diferencia : 0;
    const saldoAFavor = diferencia < 0 ? Math.min(Math.abs(diferencia), saleTotal) : 0;
    const resultado =
      importeAdicional > 0
        ? ('IMPORTE_ADICIONAL' as const)
        : saldoAFavor > 0
          ? ('SALDO_A_FAVOR' as const)
          : ('SIN_DIFERENCIA' as const);

    return {
      moneda: this.purchase().moneda || 'BOB',
      totalOriginal,
      totalReemplazo,
      diferencia,
      importeAdicional,
      saldoAFavor,
      resultado,
    };
  });

  constructor() {
    effect(() => {
      const p = this.purchase();
      if (p && p.estado === 'COMPLETADA' && p.fecha_completada && this.isOnline()) {
        untracked(() => {
          if (!this.optionsData() || this.optionsData()?.id_venta !== p.id_venta) {
            this.loadExchangeOptions(p.id_venta);
          }
        });
      }
      if (p && p.devoluciones && p.devoluciones.length > 0 && this.isOnline()) {
        untracked(() => {
          const current = this.selected();
          const returnIdParam = this.route.snapshot.queryParamMap.get('return_id');
          const targetId = returnIdParam ? Number(returnIdParam) : NaN;
          const targetFromQuery = !Number.isNaN(targetId)
            ? p.devoluciones.find((d) => d.id_devolucion === targetId)
            : null;

          if (targetFromQuery && (!current || current.id_devolucion !== targetFromQuery.id_devolucion)) {
            if (!this.checking()) {
              this.view(targetFromQuery.id_devolucion);
            }
          } else if (!current || !p.devoluciones.some((d) => d.id_devolucion === current.id_devolucion)) {
            if (!this.checking()) {
              const target = p.devoluciones.find((d) => d.estado !== 'RECHAZADA') || p.devoluciones[0];
              this.view(target.id_devolucion);
            }
          }
        });
      }
    });
  }

  loadExchangeOptions(saleId: number): void {
    if (this.loadingOptions() || !this.isOnline()) return;
    if (this.optionsData() && this.optionsData()?.id_venta === saleId) return;
    this.loadingOptions.set(true);
    this.optionsError.set('');
    this.api
      .exchangeOptions(saleId)
      .pipe(
        timeout(25000),
        takeUntilDestroyed(this.destroy),
        finalize(() => this.loadingOptions.set(false)),
      )
      .subscribe({
        next: (response) => {
          this.optionsData.set(response.data);
        },
        error: (err) => {
          if (err instanceof HttpErrorResponse && err.status === 409) {
            this.optionsError.set(err.error?.message || 'Plazo de 72 horas expirado');
          }
        },
      });
  }

  availableReplacementsFor(item: PurchaseItem): ReplacementVariant[] {
    return this.variantesDisponibles().filter(
      (v) => v.id_variante_producto !== item.id_variante_producto && v.stock_disponible > 0,
    );
  }

  selectedReplacementVariant(detailId: number): ReplacementVariant | null {
    const replId = this.replacements()[detailId];
    if (!replId) return null;
    return this.variantesDisponibles().find((v) => v.id_variante_producto === replId) || null;
  }

  setReplacement(detailId: number, variantId: number | null): void {
    if (!this.busy() && !this.frozen()) {
      this.replacements.update((x) => {
        const next = { ...x };
        if (variantId) {
          next[detailId] = Number(variantId);
        } else {
          delete next[detailId];
        }
        return next;
      });
    }
  }

  unitRecognizedValue(item: PurchaseItem): number {
    const optLine = this.lineasCompra().find((l) => l.id_detalle_venta === item.id_detalle_venta);
    if (optLine && optLine.valor_unitario_reconocido != null) {
      return Number(optLine.valor_unitario_reconocido);
    }
    return Math.max(0, Number(item.precio_unitario) - Number(item.descuento_unitario));
  }

  allReplacementsSelected(): boolean {
    if (this.units() === 0) return false;
    const quantities = this.quantities();
    const replacements = this.replacements();
    for (const item of this.purchase().productos) {
      const qty = quantities[item.id_detalle_venta] || 0;
      if (qty > 0 && !replacements[item.id_detalle_venta]) {
        return false;
      }
    }
    return true;
  }

  open(kind: ReturnKind): void {
    if (this.busy() || this.checking()) return;
    if (kind === 'CANCELACION' && !this.canCancel()) return;
    if (kind === 'DEVOLUCION' || kind === 'CAMBIO') {
      if (!this.isOnline()) {
        this.error.set('Se requiere conexión a internet para solicitar cambio o devolución.');
        return;
      }
      if (this.purchase().estado !== 'COMPLETADA') return;
      if (this.optionsData() && !this.dentroPlazo72h()) {
        this.error.set('El plazo de 72 horas posteriores a la compra ha expirado.');
        return;
      }
      if (this.purchase().fecha_completada && !this.isWithin72hLocal()) {
        this.error.set('El plazo de 72 horas posteriores a la compra ha expirado.');
        return;
      }
    }
    this.kind.set(kind);
    this.error.set('');
    if (!this.frozen()) {
      this.reason.set('');
      this.quantities.set({});
      this.replacements.set({});
      this.modalidadEntrega.set(null);
    }
    if (kind === 'CAMBIO') {
      this.checkHistory();
      if (!this.optionsData() && this.isOnline()) {
        this.loadExchangeOptions(this.purchase().id_venta);
      }
    } else if (kind === 'DEVOLUCION') {
      this.checkHistory();
      if (this.purchase().fecha_completada && !this.isWithin72hLocal()) {
        this.error.set('El plazo de 72 horas posteriores a la compra ha expirado.');
        return;
      }
    }
  }

  private checkHistory(): void {
    this.checking.set(true);
    this.verified.set(false);
    const ids = this.purchase()
      .devoluciones.filter((x) => x.estado !== 'RECHAZADA')
      .map((x) => x.id_devolucion);
    (ids.length ? forkJoin(ids.map((id) => this.api.own(id))) : of([]))
      .pipe(
        timeout(25000),
        takeUntilDestroyed(this.destroy),
        finalize(() => this.checking.set(false)),
      )
      .subscribe({
        next: (rows) => {
          this.history.set(rows.map((x) => x.data));
          this.verified.set(true);
        },
        error: (error) => this.error.set(this.api.error(error)),
      });
  }

  available(item: PurchaseItem): number {
    const optLine = this.lineasCompra().find((l) => l.id_detalle_venta === item.id_detalle_venta);
    if (optLine && typeof optLine.cantidad_disponible === 'number') {
      return Math.max(0, optLine.cantidad_disponible);
    }
    const used = this.history()
      .filter((x) => x.estado !== 'RECHAZADA')
      .flatMap((x) => x.lineas)
      .filter((x) => x.id_variante_producto === item.id_variante_producto)
      .reduce((a, b) => a + b.cantidad, 0);
    return Math.max(0, item.cantidad - used);
  }

  quantity(item: PurchaseItem, value: unknown): void {
    if (!this.busy() && !this.frozen()) {
      const maxAvail = this.available(item);
      const parsed = typeof value === 'number' ? value : parseInt(String(value ?? 0), 10);
      const clamped = Number.isNaN(parsed) || parsed < 0 ? 0 : Math.min(parsed, maxAvail);
      this.quantities.update((x) => ({ ...x, [item.id_detalle_venta]: clamped }));
      if (clamped <= 0) {
        this.replacements.update((x) => {
          const next = { ...x };
          delete next[item.id_detalle_venta];
          return next;
        });
      }
    }
  }

  onQuantityInput(item: PurchaseItem, event: Event): void {
    const inputEl = event.target as HTMLInputElement;
    if (!inputEl) return;
    const maxAvail = this.available(item);
    let val = parseInt(inputEl.value, 10);
    if (Number.isNaN(val) || val < 0) {
      val = 0;
    } else if (val > maxAvail) {
      val = maxAvail;
    }
    inputEl.value = String(val);
    this.quantity(item, val);
  }

  onQuantityPaste(item: PurchaseItem, event: ClipboardEvent): void {
    const inputEl = event.target as HTMLInputElement;
    if (!inputEl) return;
    setTimeout(() => {
      const maxAvail = this.available(item);
      let val = parseInt(inputEl.value, 10);
      if (Number.isNaN(val) || val < 0) {
        val = 0;
      } else if (val > maxAvail) {
        val = maxAvail;
      }
      inputEl.value = String(val);
      this.quantity(item, val);
    }, 0);
  }

  close(): void {
    if (!this.busy() && !this.checking()) this.kind.set(null);
  }

  submit(): void {
    const kind = this.kind();
    if (!kind || this.busy() || this.checking()) return;
    if (kind === 'DEVOLUCION' && !this.verified()) return;
    if (kind === 'CAMBIO' && !this.allReplacementsSelected()) {
      this.error.set('Selecciona una prenda de reemplazo para cada línea a cambiar.');
      return;
    }
    const motivo = this.reason().trim();
    if (!motivo || motivo.length > 500) {
      this.error.set('Escribe un motivo de entre 1 y 500 caracteres.');
      return;
    }
    const lines = this.purchase().productos.map((x) => {
      const maxAvail = this.available(x);
      const rawQty = this.quantities()[x.id_detalle_venta] ?? 0;
      const parsedQty = Math.max(0, Math.min(rawQty, maxAvail));
      return {
        item: x,
        cantidad: parsedQty,
        rawCantidad: rawQty,
        maxAvail,
      };
    });
    if (
      (kind === 'DEVOLUCION' || kind === 'CAMBIO') &&
      !this.frozen()
    ) {
      if (lines.some((x) => x.rawCantidad > x.maxAvail)) {
        this.error.set('La cantidad solicitada supera las unidades disponibles para cambio o devolución.');
        return;
      }
      if (lines.some((x) => !Number.isInteger(x.rawCantidad) || x.rawCantidad < 0)) {
        this.error.set('La cantidad debe ser un número entero mayor o igual a 0.');
        return;
      }
      if (!lines.some((x) => x.cantidad > 0)) {
        this.error.set('Selecciona al menos una unidad para procesar la solicitud.');
        return;
      }
    }
    const body: ReturnRequest =
      kind === 'CANCELACION'
        ? { motivo }
        : kind === 'CAMBIO'
          ? {
              tipo: 'CAMBIO',
              motivo,
              lineas: lines
                .filter((x) => x.cantidad > 0)
                .map((x) => ({
                  id_detalle_venta: x.item.id_detalle_venta,
                  cantidad: x.cantidad,
                  id_variante_reemplazo: this.replacements()[x.item.id_detalle_venta],
                  cantidad_reemplazo: x.cantidad,
                })),
            }
          : {
              motivo,
              lineas: lines
                .filter((x) => x.cantidad > 0)
                .map((x) => ({ id_detalle_venta: x.item.id_detalle_venta, cantidad: x.cantidad })),
            };
    const fingerprint = JSON.stringify([this.purchase().id_venta, kind, body]);
    if (!this.attempt || this.attempt.fingerprint !== fingerprint) {
      this.attempt = { fingerprint, key: this.api.attemptKey(fingerprint), body };
    }
    this.error.set('');
    this.busy.set(true);
    this.api
      .request(this.purchase().id_venta, kind, this.attempt.body, this.attempt.key)
      .pipe(
        timeout(25000),
        takeUntilDestroyed(this.destroy),
        finalize(() => this.busy.set(false)),
      )
      .subscribe({
        next: (response) => {
          this.selected.set(response.data);
          this.history.update((rows) => [
            ...rows.filter((x) => x.id_devolucion !== response.data.id_devolucion),
            response.data,
          ]);
          const ref = this.reference(response.data.id_devolucion);
          const estadoTexto =
            response.data.estado === 'SOLICITADA'
              ? 'Pendiente de revisión del cajero'
              : response.data.estado;
          this.success.set(`Solicitud ${ref} registrada con éxito. Estado: ${estadoTexto}.`);
          this.kind.set(null);
          this.frozen.set(false);
          this.api.clearAttempt(fingerprint);
          this.attempt = undefined;
          this.changed.emit();
        },
        error: (error) => {
          this.error.set(this.api.error(error));
          this.frozen.set(
            !(error instanceof HttpErrorResponse) || [0, 500, 503].includes(error.status),
          );
          if (error instanceof HttpErrorResponse && [409, 422].includes(error.status))
            this.changed.emit();
        },
      });
  }

  view(id: number): void {
    if (this.busy() || this.checking()) return;
    this.checking.set(true);
    this.error.set('');
    this.api
      .own(id)
      .pipe(
        timeout(25000),
        takeUntilDestroyed(this.destroy),
        finalize(() => this.checking.set(false)),
      )
      .subscribe({
        next: (response) => {
          this.selected.set(response.data);
          this.handleStripeReturnParams(response.data);
        },
        error: (error) => this.error.set(this.api.error(error)),
      });
  }

  private handleStripeReturnParams(row: ReturnDetail): void {
    const qp = this.route.snapshot.queryParamMap;
    const checkout = qp.get('checkout');
    const sessionId = qp.get('session_id') || undefined;

    if (row.estado_pago_adicional === 'CONFIRMADO') {
      this.stripePendingReconciliation.set(false);
    }

    if (checkout === 'cancel') {
      this.stripePendingReconciliation.set(false);
      this.paymentError.set(
        'El pago con Stripe fue cancelado o no completado. Puedes volver a intentarlo cuando gustes.',
      );
      this.paymentSuccess.set('');
      void this.router.navigate([], {
        relativeTo: this.route,
        queryParams: { return_id: row.id_devolucion },
        replaceUrl: true,
      });
      return;
    }

    if (checkout === 'success') {
      if (row.estado_pago_adicional === 'CONFIRMADO') {
        this.paymentSuccess.set('✓ Pago con Stripe verificado y confirmado con éxito.');
        this.paymentError.set('');
        void this.router.navigate([], {
          relativeTo: this.route,
          queryParams: { return_id: row.id_devolucion },
          replaceUrl: true,
        });
        return;
      }

      if (
        (row.estado_pago_adicional === 'PENDIENTE' || !row.estado_pago_adicional) &&
        !this.stripeVerificationAttempted
      ) {
        this.stripeVerificationAttempted = true;
        this.stripePendingReconciliation.set(true);
        this.verifyStripePayment(row.id_devolucion, sessionId);
      }
      return;
    }

    if (
      row.tipo === 'CAMBIO' &&
      row.estado === 'APROBADA' &&
      row.estado_pago_adicional === 'PENDIENTE' &&
      row.stripe_session_id &&
      !this.stripeVerificationAttempted
    ) {
      this.stripeVerificationAttempted = true;
      this.verifyStripePayment(row.id_devolucion, row.stripe_session_id, true);
    }
  }

  confirmDeliveryModality(returnId: number): void {
    const mod = this.clientSelectedModality();
    if (!mod || this.savingModality() || !this.isOnline()) return;
    this.savingModality.set(true);
    this.error.set('');
    this.api
      .selectDeliveryModality(returnId, { modalidad_entrega: mod })
      .pipe(
        timeout(25000),
        takeUntilDestroyed(this.destroy),
        finalize(() => this.savingModality.set(false)),
      )
      .subscribe({
        next: (response) => {
          this.selected.set(response.data);
          this.history.update((rows) => [
            ...rows.filter((x) => x.id_devolucion !== response.data.id_devolucion),
            response.data,
          ]);
          this.success.set(
            `Modalidad de entrega registrada con éxito (${mod === 'DELIVERY_SIMULADO' ? 'Delivery simulado' : 'Entrega en tienda'}). Estado actual: Pendiente de entrega.`,
          );
          this.clientSelectedModality.set(null);
          this.changed.emit();
        },
        error: (error) => this.error.set(this.api.error(error)),
      });
  }

  payWithStripe(returnId: number): void {
    if (
      this.payingStripe() ||
      this.verifyingStripe() ||
      this.stripePendingReconciliation() ||
      !this.isOnline()
    )
      return;
    this.payingStripe.set(true);
    this.paymentError.set('');
    this.paymentSuccess.set('');
    this.api
      .createExchangeStripeCheckout(returnId)
      .pipe(
        timeout(25000),
        takeUntilDestroyed(this.destroy),
        finalize(() => this.payingStripe.set(false)),
      )
      .subscribe({
        next: (response) => {
          if (response.data?.url) {
            window.location.href = response.data.url;
          } else {
            this.paymentError.set('No se recibió la URL de Stripe Checkout');
          }
        },
        error: (err) => {
          const msg = this.api.error(err);
          this.paymentError.set(msg);
          if (
            err instanceof HttpErrorResponse &&
            err.status === 409 &&
            msg.toLowerCase().includes('completado')
          ) {
            this.stripePendingReconciliation.set(true);
            this.verifyStripePayment(returnId);
          } else if (
            err instanceof HttpErrorResponse &&
            [0, 500, 503].includes(err.status) &&
            this.selected()?.stripe_session_id
          ) {
            this.stripePendingReconciliation.set(true);
          }
        },
      });
  }

  verifyStripePayment(returnId: number, sessionId?: string, silentIfUnpaid = false): void {
    if (this.verifyingStripe() || !this.isOnline()) return;
    this.verifyingStripe.set(true);
    if (!silentIfUnpaid) {
      this.paymentError.set('');
      this.paymentSuccess.set('');
    }
    this.api
      .confirmExchangeStripeClient(returnId, sessionId)
      .pipe(
        timeout(25000),
        takeUntilDestroyed(this.destroy),
        finalize(() => this.verifyingStripe.set(false)),
      )
      .subscribe({
        next: (response) => {
          this.stripePendingReconciliation.set(false);
          this.selected.set(response.data);
          this.history.update((rows) => [
            ...rows.filter((x) => x.id_devolucion !== response.data.id_devolucion),
            response.data,
          ]);
          this.paymentSuccess.set('✓ Pago con Stripe verificado y confirmado con éxito en el servidor.');
          this.changed.emit();
          void this.router.navigate([], {
            relativeTo: this.route,
            queryParams: { return_id: response.data.id_devolucion },
            replaceUrl: true,
          });
        },
        error: (err) => {
          const status = err instanceof HttpErrorResponse ? err.status : 0;
          const msg = this.api.error(err);
          const isUnpaid =
            status === 409 &&
            (msg.includes('unpaid') || msg.includes('aún no está confirmado'));
          if (isUnpaid) {
            this.stripePendingReconciliation.set(false);
            if (!silentIfUnpaid) {
              this.paymentError.set(msg);
            }
          } else if ([0, 500, 503].includes(status)) {
            this.stripePendingReconciliation.set(true);
            this.paymentError.set(
              `${msg} Si ya completaste el pago en Stripe, usa «Verificar pago online» sin iniciar un nuevo cobro.`,
            );
          } else {
            this.paymentError.set(msg);
          }
          void this.router.navigate([], {
            relativeTo: this.route,
            queryParams: { return_id: returnId },
            replaceUrl: true,
          });
        },
      });
  }
}
