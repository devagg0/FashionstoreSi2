import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Subscription, finalize, timeout } from 'rxjs';
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
} from '../../core/services/returns.service';
import { OfflineService } from '../../core/services/offline.service';
import { formatBs } from '../../core/utils/money';
import { formatSaleReference } from '../../core/utils/sale-reference';

@Component({
  selector: 'app-client-returns',
  imports: [RouterLink],
  templateUrl: './client-returns.html',
  styleUrl: './client-returns.scss',
})
export class ClientReturnsPage {
  private readonly api = inject(ReturnsService);
  private readonly offlineService = inject(OfflineService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroy = inject(DestroyRef);
  private request?: Subscription;

  readonly id = signal<number | null>(null);
  readonly items = signal<ReturnDetail[]>([]);
  readonly detail = signal<ReturnDetail | null>(null);
  readonly loading = signal(false);
  readonly error = signal('');

  // Filtros
  readonly tipo = signal<ReturnKind | ''>('');
  readonly state = signal<ReturnState | ''>('');
  readonly modalidad = signal<DeliveryModality | ''>('');
  readonly offset = signal(0);
  readonly hasNext = signal(false);

  readonly isOnline = computed(() => {
    return this.offlineService.isOnline() && (typeof navigator === 'undefined' || navigator.onLine);
  });

  readonly reference = returnReference;
  readonly label = returnLabel;
  readonly stateLabel = returnStateLabel;
  readonly tone = returnTone;
  readonly date = returnDate;
  readonly money = formatBs;
  readonly saleReference = formatSaleReference;

  readonly filtered = computed(() => !!this.tipo() || !!this.state() || !!this.modalidad());

  constructor() {
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroy)).subscribe((params) => {
      const raw = params.get('id');
      this.id.set(raw === null ? null : /^[1-9]\d*$/.test(raw) ? Number(raw) : NaN);
      this.detail.set(null);
      this.offset.set(0);
      this.load();
    });
    this.destroy.onDestroy(() => this.request?.unsubscribe());
  }

  filter(tipo: string, state: string, modalidad: string): void {
    if (this.loading()) return;
    this.tipo.set((tipo as ReturnKind) || '');
    this.state.set((state as ReturnState) || '');
    this.modalidad.set((modalidad as DeliveryModality) || '');
    this.offset.set(0);
    this.load();
  }

  page(direction: number): void {
    if (this.loading()) return;
    this.offset.set(Math.max(0, this.offset() + direction * 20));
    this.load();
  }

  load(): void {
    this.request?.unsubscribe();
    this.error.set('');

    if (!this.isOnline()) {
      this.loading.set(false);
      this.error.set(
        'Se requiere conexión a internet para consultar el estado actualizado de tus solicitudes.',
      );
      return;
    }

    const currentId = this.id();
    if (currentId !== null && (!Number.isSafeInteger(currentId) || currentId < 1 || currentId > 2147483647)) {
      this.error.set('Solicitud no encontrada.');
      return;
    }

    this.loading.set(true);

    if (currentId !== null) {
      this.request = this.api
        .own(currentId)
        .pipe(
          timeout(30000),
          finalize(() => this.loading.set(false)),
        )
        .subscribe({
          next: (response) => {
            this.detail.set(response.data);
          },
          error: (err) => {
            this.detail.set(null);
            this.error.set(this.api.error(err));
          },
        });
    } else {
      this.request = this.api
        .listOwn(this.state(), this.offset(), this.tipo(), undefined, this.modalidad())
        .pipe(
          timeout(30000),
          finalize(() => this.loading.set(false)),
        )
        .subscribe({
          next: (response) => {
            this.items.set(response.data);
            this.hasNext.set(response.data.length === 20);
          },
          error: (err) => {
            this.items.set([]);
            this.error.set(this.api.error(err));
          },
        });
    }
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
}

