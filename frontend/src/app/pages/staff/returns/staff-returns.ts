import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Subscription, finalize, switchMap, tap, timeout } from 'rxjs';
import {
  DeliveryModality,
  ReturnDetail,
  ReturnKind,
  ReturnProgressStep,
  ReturnState,
  ReturnsService,
  returnDate,
  returnLabel,
  returnReference,
  returnStateLabel,
  returnTone,
} from '../../../core/services/returns.service';
import { SessionService } from '../../../core/services/session.service';
import { formatBs } from '../../../core/utils/money';
import { ReturnModal } from '../../../shared/components/return-modal/return-modal';

type Action =
  | 'ACEPTAR_INICIAL'
  | 'RECHAZAR_INICIAL'
  | 'CONFIRMAR_RECEPCION'
  | 'INSPECCIONAR'
  | 'APROBADA'
  | 'RECHAZADA'
  | 'PROCESAR'
  | 'CONFIRMAR_DIFERENCIA'
  | 'COBRO_TIENDA'
  | 'VERIFICAR_STRIPE'
  | 'PROCESAR_CAMBIO';

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
  readonly tipo = signal<ReturnKind | ''>('');
  readonly modalidad = signal<DeliveryModality | ''>('');
  readonly branchId = signal<number | null>(null);
  readonly offset = signal(0);
  readonly hasNext = signal(false);
  readonly action = signal<Action | null>(null);

  // CU16 Campos interactivos de revisión e inspección
  readonly motivoRechazo = signal('');
  readonly observacionesRecepcion = signal('');
  readonly estadoFisico = signal('OPTIMO');
  readonly etiquetasIntactas = signal(true);
  readonly correspondenciaCompra = signal(true);
  readonly observacionesInspeccion = signal('');
  readonly resultadoInspeccion = signal<'APROBADA' | 'RECHAZADA'>('APROBADA');

  // CU17 Campos para procesar cambio de prenda
  readonly medioPagoCambio = signal<'EFECTIVO' | 'QR' | 'TARJETA'>('EFECTIVO');
  readonly referenciaPagoCambio = signal('');
  readonly reintegrarStockOriginal = signal(true);

  // Soporte para edición / procesamiento legacy
  readonly drafts = signal<Record<number, Draft>>({});
  readonly receipt = signal('');
  readonly canProcessReturn = computed(() =>
    ['ADMINISTRADOR', 'ENCARGADO_SUCURSAL', 'ENCARGADO'].includes(
      (this.session.getUser()?.rol || '').toUpperCase(),
    ),
  );
  readonly method = computed(() => {
    const p = this.detail()?.pago;
    if (p?.medio === 'TARJETA' && p.proveedor === 'STRIPE' && p.entorno === 'TEST') return 'STRIPE';
    if (
      (p?.medio === 'EFECTIVO' || p?.medio === 'QR' || p?.medio === 'TARJETA') &&
      p.proveedor === 'MANUAL' &&
      p.entorno === 'LOCAL'
    )
      return 'MANUAL';
    return '';
  });
  readonly failedRefund = computed(
    () => this.detail()?.reembolsos.some((x) => x.estado === 'RECHAZADO') ?? false,
  );
  readonly needsRefund = computed(() => {
    const row = this.detail();
    if (!row) return false;
    if (row.reembolsos.some((x) => x.estado === 'PENDIENTE')) return true;
    if (row.tipo === 'DEVOLUCION' && row.estado === 'APROBADA') {
      const amount = Number(row.monto_reembolsar ?? row.saldo_a_favor_estimado ?? 0);
      return amount > 0 && !row.reembolsos.some((x) => x.estado === 'APROBADO');
    }
    return false;
  });

  readonly refreshRequired = signal(false);
  readonly modalError = signal('');
  readonly reference = returnReference;
  readonly label = returnLabel;
  readonly stateLabel = returnStateLabel;
  readonly tone = returnTone;
  readonly date = returnDate;
  readonly money = formatBs;
  readonly Number = Number;
  readonly Math = Math;
  readonly basePath = this.router.url.startsWith('/admin')
    ? '/admin/devoluciones'
    : '/staff/devoluciones';
  readonly ownRequest = computed(
    () => this.detail()?.id_usuario_solicitante === this.session.getUser()?.id_usuario,
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
          timeout(35000),
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
        .list(this.state(), this.offset(), this.tipo(), this.modalidad(), this.branchId() ?? undefined)
        .pipe(
          timeout(35000),
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

  filter(value: string, tipo = '', modalidad = ''): void {
    if (this.busy()) return;
    this.state.set((value as ReturnState) || '');
    this.tipo.set((tipo as ReturnKind) || '');
    this.modalidad.set((modalidad as DeliveryModality) || '');
    this.offset.set(0);
    this.load();
  }

  stepTone(step: ReturnProgressStep): string {
    switch (step.estado) {
      case 'COMPLETADO':
        return 'good';
      case 'ACTUAL':
        return 'pending';
      case 'RECHAZADO':
        return 'bad';
      default:
        return 'muted';
    }
  }

  stepIcon(step: ReturnProgressStep): string {
    switch (step.estado) {
      case 'COMPLETADO':
        return '✓';
      case 'ACTUAL':
        return '●';
      case 'RECHAZADO':
        return '✕';
      default:
        return String(step.paso);
    }
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
    if (!row || this.busy() || this.loading() || this.refreshRequired() || this.ownRequest())
      return;

    if (action === 'ACEPTAR_INICIAL' || action === 'RECHAZAR_INICIAL') {
      if (row.estado !== 'SOLICITADA') return;
    } else if (action === 'CONFIRMAR_RECEPCION') {
      if (row.estado !== 'PENDIENTE_ENTREGA') return;
    } else if (action === 'INSPECCIONAR') {
      if (row.estado !== 'RECIBIDA') return;
    } else if (action === 'PROCESAR') {
      if (row.estado !== 'APROBADA' || this.failedRefund()) return;
      if (row.tipo === 'DEVOLUCION' && !this.canProcessReturn()) return;
    } else if (
      action === 'PROCESAR_CAMBIO' ||
      action === 'CONFIRMAR_DIFERENCIA' ||
      action === 'COBRO_TIENDA' ||
      action === 'VERIFICAR_STRIPE'
    ) {
      if (row.estado !== 'APROBADA' || row.tipo !== 'CAMBIO') return;
    } else if (action === 'APROBADA' || action === 'RECHAZADA') {
      if (row.estado !== 'SOLICITADA') return;
    }

    this.action.set(action);
    this.modalError.set('');
    this.receipt.set('');
    this.motivoRechazo.set('');
    this.observacionesRecepcion.set('');
    this.estadoFisico.set('OPTIMO');
    this.etiquetasIntactas.set(true);
    this.correspondenciaCompra.set(true);
    this.observacionesInspeccion.set('');
    this.resultadoInspeccion.set('APROBADA');
    this.medioPagoCambio.set('EFECTIVO');
    this.referenciaPagoCambio.set('');
    this.reintegrarStockOriginal.set(
      row.apta_reintegro_stock !== undefined
        ? row.apta_reintegro_stock
        : (row.estado_fisico === 'OPTIMO' || row.estado_fisico === 'BUENO') && row.etiquetas_intactas !== false,
    );
  }

  close(): void {
    if (!this.busy()) this.action.set(null);
  }

  confirm(): void {
    const row = this.detail(),
      action = this.action();
    if (!row || !action || this.busy() || this.ownRequest()) return;

    if (action === 'RECHAZAR_INICIAL' && !this.motivoRechazo().trim()) {
      this.modalError.set('El motivo de rechazo es obligatorio para rechazar la solicitud.');
      return;
    }
    if (
      action === 'INSPECCIONAR' &&
      this.resultadoInspeccion() === 'RECHAZADA' &&
      !this.motivoRechazo().trim()
    ) {
      this.modalError.set(
        'El motivo de rechazo es obligatorio al rechazar la prenda en la inspección física.',
      );
      return;
    }

    let request$;
    if (action === 'ACEPTAR_INICIAL') {
      request$ = this.api.initialReview(row.id_devolucion, { resultado: 'ACEPTADA' });
    } else if (action === 'RECHAZAR_INICIAL') {
      request$ = this.api.initialReview(row.id_devolucion, {
        resultado: 'RECHAZADA',
        motivo_rechazo: this.motivoRechazo().trim(),
      });
    } else if (action === 'CONFIRMAR_RECEPCION') {
      request$ = this.api.receiveItem(row.id_devolucion, {
        observaciones: this.observacionesRecepcion().trim() || undefined,
      });
    } else if (action === 'INSPECCIONAR') {
      request$ = this.api.inspectItem(row.id_devolucion, {
        resultado: this.resultadoInspeccion(),
        estado_fisico: this.estadoFisico().trim() || 'OPTIMO',
        etiquetas_intactas: this.etiquetasIntactas(),
        correspondencia_compra: this.correspondenciaCompra(),
        observaciones: this.observacionesInspeccion().trim() || undefined,
        motivo_rechazo:
          this.resultadoInspeccion() === 'RECHAZADA' ? this.motivoRechazo().trim() : undefined,
      });
    } else if (action === 'PROCESAR') {
      if (
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
      request$ = this.api.process(
        row.id_devolucion,
        this.needsRefund() && this.method() === 'MANUAL' ? this.receipt().trim() : undefined,
        row.tipo === 'DEVOLUCION'
          ? row.apta_reintegro_stock !== false && this.reintegrarStockOriginal()
          : undefined,
      );
    } else if (action === 'CONFIRMAR_DIFERENCIA') {
      request$ = this.api.confirmExchangeDifference(row.id_devolucion);
    } else if (action === 'COBRO_TIENDA') {
      if (!this.medioPagoCambio()) {
        this.modalError.set('Selecciona un método de cobro en tienda.');
        return;
      }
      if (
        (this.medioPagoCambio() === 'QR' || this.medioPagoCambio() === 'TARJETA') &&
        !this.referenciaPagoCambio().trim()
      ) {
        this.modalError.set(
          `Ingresa el número de comprobante o referencia de la transacción confirmada con ${this.medioPagoCambio()}.`,
        );
        return;
      }
      request$ = this.api.confirmExchangeStorePayment(row.id_devolucion, {
        medio_pago: this.medioPagoCambio(),
        referencia_manual: this.referenciaPagoCambio().trim() || undefined,
      });
    } else if (action === 'VERIFICAR_STRIPE') {
      request$ = this.api.confirmExchangeStripeStaff(row.id_devolucion);
    } else if (action === 'PROCESAR_CAMBIO') {
      request$ = this.api.processExchange(row.id_devolucion, {
        reintegrar_stock_original: this.reintegrarStockOriginal(),
      });
    } else if (action === 'APROBADA' || action === 'RECHAZADA') {
      let body: any = { resultado: action === 'RECHAZADA' ? 'RECHAZADA' : 'APROBADA' };
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
      request$ = this.api.review(row.id_devolucion, body);
    }

    if (!request$) {
      this.busy.set(false);
      return;
    }

    this.busy.set(true);
    this.modalError.set('');
    this.error.set('');

    const isLegacyApproval = action === 'APROBADA';
    request$
      .pipe(
        tap(() => {
          if (isLegacyApproval) {
            this.refreshRequired.set(true);
            this.action.set(null);
          }
        }),
        switchMap((response) =>
          isLegacyApproval ? this.api.detail(row.id_devolucion) : [response],
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
          let msg = '';
          if (action === 'ACEPTAR_INICIAL') {
            msg =
              'Solicitud aceptada inicialmente. El cliente ahora puede seleccionar la modalidad de entrega.';
          } else if (action === 'RECHAZAR_INICIAL' || action === 'RECHAZADA') {
            msg = 'Solicitud rechazada con éxito.';
          } else if (action === 'CONFIRMAR_RECEPCION') {
            msg = 'Prenda recibida en tienda física. Ya puedes realizar la inspección.';
          } else if (action === 'INSPECCIONAR') {
            msg =
              response.data.estado === 'APROBADA'
                ? 'Inspección completada con éxito. Solicitud aprobada definitivamente (lista para CU17/CU18).'
                : 'Inspección completada. Solicitud rechazada.';
          } else if (action === 'PROCESAR') {
            msg =
              response.data.estado === 'PROCESADA'
                ? `${row.tipo === 'CANCELACION' ? 'CANCELACIÓN' : 'DEVOLUCIÓN'} PROCESADA`
                : response.data.reembolsos.some((x) => x.estado === 'RECHAZADO')
                  ? 'El reembolso no se completó. Requiere revisión del personal.'
                  : 'Reembolso pendiente de confirmación. Reconsulta sobre esta misma solicitud.';
          } else if (action === 'CONFIRMAR_DIFERENCIA') {
            msg = 'Importe definitivo confirmado con éxito. El cambio quedó registrado como pendiente de pago.';
          } else if (action === 'COBRO_TIENDA') {
            msg = 'Cobro presencial en tienda registrado y confirmado con éxito.';
          } else if (action === 'VERIFICAR_STRIPE') {
            msg = 'Pago online con Stripe verificado y confirmado con éxito en el servidor.';
          } else if (action === 'PROCESAR_CAMBIO') {
            msg = 'Cambio de prenda procesado y prenda de reemplazo entregada con éxito. Inventario actualizado.';
          } else if (action === 'APROBADA') {
            msg = 'Solicitud aprobada. Ya puedes procesarla.';
          }
          this.success.set(msg);
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
