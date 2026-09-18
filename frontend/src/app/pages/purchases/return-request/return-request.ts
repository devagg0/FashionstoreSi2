import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, computed, inject, input, output, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { finalize, forkJoin, of, timeout } from 'rxjs';
import { PurchaseDetail, PurchaseItem } from '../../../core/services/client-purchases.service';
import {
  ReturnDetail,
  ReturnKind,
  ReturnRequest,
  ReturnsService,
  returnDate,
  returnLabel,
  returnReference,
  returnTone,
} from '../../../core/services/returns.service';
import { ReturnModal } from '../../../shared/components/return-modal/return-modal';
import { formatBs } from '../../../core/utils/money';

@Component({
  selector: 'app-purchase-return-request',
  imports: [FormsModule, ReturnModal],
  templateUrl: './return-request.html',
  styleUrl: './return-request.scss',
})
export class PurchaseReturnRequest {
  readonly purchase = input.required<PurchaseDetail>();
  readonly changed = output<void>();
  private readonly api = inject(ReturnsService);
  private readonly destroy = inject(DestroyRef);
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
  readonly reason = signal('');
  private attempt?: { fingerprint: string; key: string; body: ReturnRequest };
  readonly reference = returnReference;
  readonly label = returnLabel;
  readonly tone = returnTone;
  readonly date = returnDate;
  readonly money = formatBs;
  readonly canCancel = computed(
    () =>
      this.purchase().estado === 'PENDIENTE' &&
      !this.purchase().devoluciones.some(
        (x) => x.tipo === 'CANCELACION' && x.estado !== 'RECHAZADA',
      ) &&
      !this.history().some((x) => x.tipo === 'CANCELACION' && x.estado !== 'RECHAZADA'),
  );
  readonly units = computed(() => Object.values(this.quantities()).reduce((a, b) => a + b, 0));

  open(kind: ReturnKind): void {
    if (
      this.busy() ||
      this.checking() ||
      (kind === 'CANCELACION' && !this.canCancel()) ||
      (kind === 'DEVOLUCION' && this.purchase().estado !== 'COMPLETADA')
    )
      return;
    this.kind.set(kind);
    this.error.set('');
    if (!this.frozen()) {
      this.reason.set('');
      this.quantities.set({});
    }
    if (kind === 'DEVOLUCION') this.checkHistory();
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
    const used = this.history()
      .filter((x) => x.estado !== 'RECHAZADA')
      .flatMap((x) => x.lineas)
      .filter((x) => x.id_variante_producto === item.id_variante_producto)
      .reduce((a, b) => a + b.cantidad, 0);
    return Math.max(0, item.cantidad - used);
  }
  quantity(item: PurchaseItem, value: number): void {
    if (!this.busy() && !this.frozen())
      this.quantities.update((x) => ({ ...x, [item.id_detalle_venta]: Number(value) }));
  }
  close(): void {
    if (!this.busy() && !this.checking()) this.kind.set(null);
  }
  submit(): void {
    const kind = this.kind();
    if (!kind || this.busy() || this.checking() || (kind === 'DEVOLUCION' && !this.verified()))
      return;
    const motivo = this.reason().trim();
    if (!motivo || motivo.length > 500) {
      this.error.set('Escribe un motivo de entre 1 y 500 caracteres.');
      return;
    }
    const lines = this.purchase().productos.map((x) => ({
      item: x,
      cantidad: this.quantities()[x.id_detalle_venta] ?? 0,
    }));
    if (
      kind === 'DEVOLUCION' &&
      !this.frozen() &&
      (lines.some(
        (x) =>
          !Number.isInteger(x.cantidad) || x.cantidad < 0 || x.cantidad > this.available(x.item),
      ) ||
        !lines.some((x) => x.cantidad > 0))
    ) {
      this.error.set('Selecciona al menos una unidad y respeta las cantidades disponibles.');
      return;
    }
    const body: ReturnRequest =
      kind === 'CANCELACION'
        ? { motivo }
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
          this.success.set('Solicitud registrada. El personal de FashionStore revisará tu caso.');
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
          this.changed.emit();
        },
        error: (error) => this.error.set(this.api.error(error)),
      });
  }
}
