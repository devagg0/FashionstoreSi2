import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Subscription, finalize, switchMap, tap, timeout } from 'rxjs';
import {
  ReturnDetail,
  ReturnState,
  ReturnsService,
  ReviewRequest,
  returnDate,
  returnLabel,
  returnReference,
  returnTone,
} from '../../../core/services/returns.service';
import { SessionService } from '../../../core/services/session.service';
import { formatBs } from '../../../core/utils/money';
import { ReturnModal } from '../../../shared/components/return-modal/return-modal';

type Action = 'APROBADA' | 'RECHAZADA' | 'PROCESAR';
interface Draft {
  cantidad_reintegrar: number;
  importe_restitucion: string;
}
@Component({
  selector: 'app-staff-returns',
  imports: [RouterLink, FormsModule, ReturnModal],
  templateUrl: './staff-returns.html',
  styleUrl: './staff-returns.scss',
})
export class StaffReturnsPage {
  private readonly api = inject(ReturnsService);
  private readonly session = inject(SessionService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroy = inject(DestroyRef);
  private request?: Subscription;
  readonly id = signal<number | null>(null);
  readonly items = signal<ReturnDetail[]>([]);
  readonly detail = signal<ReturnDetail | null>(null);
  readonly loading = signal(false);
  readonly busy = signal(false);
  readonly error = signal('');
  readonly success = signal('');
  readonly state = signal<ReturnState | ''>('');
  readonly offset = signal(0);
  readonly hasNext = signal(false);
  readonly action = signal<Action | null>(null);
  readonly drafts = signal<Record<number, Draft>>({});
  readonly method = computed(() => {
    const p = this.detail()?.pago;
    if (p?.medio === 'TARJETA' && p.proveedor === 'STRIPE' && p.entorno === 'TEST') return 'STRIPE';
    if (
      (p?.medio === 'EFECTIVO' || p?.medio === 'QR') &&
      p.proveedor === 'MANUAL' &&
      p.entorno === 'LOCAL'
    )
      return 'MANUAL';
    return '';
  });
  readonly refreshRequired = signal(false);
  readonly receipt = signal('');
  readonly modalError = signal('');
  readonly reference = returnReference;
  readonly label = returnLabel;
  readonly tone = returnTone;
  readonly date = returnDate;
  readonly money = formatBs;
  readonly basePath = this.router.url.startsWith('/admin')
    ? '/admin/devoluciones'
    : '/staff/devoluciones';
  readonly ownRequest = computed(
    () => this.detail()?.id_usuario_solicitante === this.session.getUser()?.id_usuario,
  );
  readonly failedRefund = computed(
    () => this.detail()?.reembolsos.some((x) => x.estado === 'RECHAZADO') ?? false,
  );
  readonly needsRefund = computed(
    () => this.detail()?.reembolsos.some((x) => x.estado === 'PENDIENTE') ?? false,
  );
  constructor() {
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroy)).subscribe((params) => {
      const raw = params.get('id');
      this.id.set(raw === null ? null : /^[1-9]\d*$/.test(raw) ? Number(raw) : NaN);
      this.detail.set(null);
      this.action.set(null);
      this.success.set('');
      this.offset.set(0);
      this.load();
    });
    this.destroy.onDestroy(() => this.request?.unsubscribe());
  }
  load(): void {
    if (this.busy()) return;
    this.request?.unsubscribe();
    this.error.set('');
    const id = this.id();
    if (id !== null && (!Number.isSafeInteger(id) || id < 1 || id > 2147483647)) {
      this.error.set('Solicitud no encontrada.');
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
            this.setDetail(response.data);
            this.refreshRequired.set(false);
          },
          error: (error) => this.error.set(this.api.error(error)),
        });
    } else {
      this.request = this.api
        .list(this.state(), this.offset())
        .pipe(
          timeout(25000),
          finalize(() => this.loading.set(false)),
        )
        .subscribe({
          next: (response) => {
            this.items.set(response.data);
            this.hasNext.set(response.data.length === 20);
          },
          error: (error) => {
            this.items.set([]);
            this.error.set(this.api.error(error));
          },
        });
    }
  }
  private setDetail(row: ReturnDetail): void {
    if (row.id_devolucion !== this.id()) {
      this.error.set('No pudimos verificar esta solicitud.');
      return;
    }
    this.detail.set(row);
    this.drafts.set(
      Object.fromEntries(
        row.lineas.map((x) => [
          x.id_variante_producto,
          {
            cantidad_reintegrar: x.cantidad_reintegrar,
            importe_restitucion: String(x.importe_restitucion),
          },
        ]),
      ),
    );
  }

  filter(value: string): void {
    if (!['', 'SOLICITADA', 'APROBADA', 'RECHAZADA', 'PROCESADA'].includes(value) || this.busy())
      return;
    this.state.set(value as ReturnState | '');
    this.offset.set(0);
    this.load();
  }
  page(direction: number): void {
    if (this.loading() || this.busy()) return;
    this.offset.set(Math.max(0, this.offset() + direction * 20));
    this.load();
  }
  edit(variant: number, field: keyof Draft, value: string | number): void {
    if (this.busy()) return;
    this.drafts.update((rows) => ({
      ...rows,
      [variant]: {
        ...rows[variant],
        [field]: field === 'cantidad_reintegrar' ? Number(value) : String(value),
      },
    }));
  }
  open(action: Action): void {
    const row = this.detail();
    if (
      !row ||
      this.busy() ||
      this.loading() ||
      this.refreshRequired() ||
      this.ownRequest() ||
      (action === 'PROCESAR'
        ? row.estado !== 'APROBADA' || this.failedRefund()
        : row.estado !== 'SOLICITADA')
    )
      return;
    this.action.set(action);
    this.modalError.set('');
    this.receipt.set('');
  }
  close(): void {
    if (!this.busy()) this.action.set(null);
  }
  confirm(): void {
    const row = this.detail(),
      action = this.action();
    if (!row || !action || this.busy() || this.ownRequest()) return;
    let body: ReviewRequest = { resultado: action === 'RECHAZADA' ? 'RECHAZADA' : 'APROBADA' };
    if (action === 'APROBADA' && row.tipo === 'DEVOLUCION') {
      const lines = row.lineas.map((line) => ({
        id_variante_producto: line.id_variante_producto,
        ...this.drafts()[line.id_variante_producto],
      }));
      if (
        lines.some(
          (x, i) =>
            !Number.isInteger(x.cantidad_reintegrar) ||
            x.cantidad_reintegrar < 0 ||
            x.cantidad_reintegrar > row.lineas[i].cantidad ||
            !/^\d+(?:\.\d{1,2})?$/.test(x.importe_restitucion) ||
            Number(x.importe_restitucion) > Number(row.lineas[i].importe_restitucion),
        )
      ) {
        this.modalError.set(
          'Revisa el reintegro y los importes: no pueden superar lo solicitado ni el máximo de restitución.',
        );
        return;
      }
      body = { resultado: 'APROBADA', lineas: lines };
    }
    if (
      action === 'PROCESAR' &&
      this.needsRefund() &&
      (!this.method() || (this.method() === 'MANUAL' && !this.receipt().trim()))
    ) {
      this.modalError.set(
        this.method() === 'MANUAL'
          ? 'Ingresa el comprobante del reembolso manual.'
          : 'No existe un pago original aprobado válido para reembolsar. Actualiza el detalle.',
      );
      return;
    }
    this.busy.set(true);
    this.modalError.set('');
    this.error.set('');
    const request =
      action === 'PROCESAR'
        ? this.api.process(
            row.id_devolucion,
            this.needsRefund() && this.method() === 'MANUAL' ? this.receipt().trim() : undefined,
          )
        : this.api.review(row.id_devolucion, body);
    request
      .pipe(
        tap(() => {
          if (action === 'APROBADA') {
            this.refreshRequired.set(true);
            this.action.set(null);
          }
        }),
        switchMap((response) =>
          action === 'APROBADA' ? this.api.detail(row.id_devolucion) : [response],
        ),
        timeout(25000),
        takeUntilDestroyed(this.destroy),
        finalize(() => this.busy.set(false)),
      )
      .subscribe({
        next: (response) => {
          this.setDetail(response.data);
          this.refreshRequired.set(false);
          this.action.set(null);
          this.success.set(
            response.data.estado === 'PROCESADA'
              ? `${row.tipo === 'CANCELACION' ? 'CANCELACIÓN' : 'DEVOLUCIÓN'} PROCESADA`
              : response.data.reembolsos.some((x) => x.estado === 'RECHAZADO')
                ? 'El reembolso no se completó. Requiere revisión del personal.'
                : action === 'PROCESAR'
                  ? 'Reembolso pendiente de confirmación. Reconsulta sobre esta misma solicitud.'
                  : action === 'RECHAZADA'
                    ? 'Solicitud rechazada.'
                    : 'Solicitud aprobada. Ya puedes procesarla.',
          );
        },
        error: (error) => {
          const message = this.api.error(error);
          if (this.refreshRequired()) this.error.set(message);
          else this.modalError.set(message);
          this.success.set('');
        },
      });
  }
}
