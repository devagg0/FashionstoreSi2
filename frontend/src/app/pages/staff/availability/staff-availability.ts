import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, inject, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { catchError, finalize, forkJoin, map, of, switchMap } from 'rxjs';
import { CatalogService } from '../../../core/services/catalog.service';
import { StaffApiErrorService } from '../../../core/services/staff-api-error.service';
import { StaffReservationsService } from '../../../core/services/staff-reservations.service';
import { Icon } from '../../../shared/components/icon/icon';

interface StaffAvailabilityRow {
  id: number;
  producto: string;
  talla: string;
  color: string;
  codigoHex: string | null;
  sku: string;
  stockDisponible: number;
}

@Component({
  selector: 'app-staff-availability',
  imports: [Icon, ReactiveFormsModule],
  templateUrl: './staff-availability.html',
})
export class StaffAvailability implements OnInit {
  private readonly reservations = inject(StaffReservationsService);
  private readonly catalog = inject(CatalogService);
  private readonly errors = inject(StaffApiErrorService);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly search = new FormControl('', { nonNullable: true });
  protected readonly rows = signal<StaffAvailabilityRow[]>([]);
  protected readonly loading = signal(true);
  protected readonly errorMessage = signal('');
  protected readonly branch = this.reservations.branch;
  protected readonly page = signal(1);
  protected readonly totalPages = signal(0);

  ngOnInit(): void {
    this.load();
  }

  protected load(page = 1): void {
    this.loading.set(true);
    this.errorMessage.set('');
    this.reservations
      .loadBranchContext()
      .pipe(
        switchMap((branch) => {
          if (!branch) {
            throw new Error('BRANCH_CONTEXT_UNAVAILABLE');
          }
          return this.catalog.listProducts({
            search: this.search.value.trim() || undefined,
            idSucursal: branch.id_sucursal,
            page,
            pageSize: 8,
          }).pipe(map((response) => ({ branch, response })));
        }),
        switchMap(({ branch, response }) => {
          this.page.set(response.pagination.page);
          this.totalPages.set(response.pagination.total_pages);
          if (!response.data.length) return of([] as StaffAvailabilityRow[]);
          return forkJoin(
            response.data.map((product) =>
              this.catalog.getProduct(product.id_producto, branch.id_sucursal).pipe(
                map((detail) =>
                  detail.data.variantes.map((variant) => ({
                    id: variant.id_variante_producto,
                    producto: detail.data.nombre,
                    talla: variant.talla.nombre,
                    color: variant.color.nombre,
                    codigoHex: variant.color.codigo_hex,
                    sku: variant.sku,
                    stockDisponible:
                      variant.disponibilidad_sucursal?.id_sucursal === branch.id_sucursal
                        ? variant.disponibilidad_sucursal.cantidad_disponible
                        : 0,
                  })),
                ),
                catchError(() => of([] as StaffAvailabilityRow[])),
              ),
            ),
          ).pipe(map((groups) => groups.flat()));
        }),
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.loading.set(false)),
      )
      .subscribe({
        next: (rows) => this.rows.set(rows),
        error: (error: HttpErrorResponse | Error) => {
          this.rows.set([]);
          this.errorMessage.set(
            error.message === 'BRANCH_CONTEXT_UNAVAILABLE'
              ? 'El backend todavía no ofrece el contexto de sucursal cuando no existen reservas.'
              : this.errors.resolve(
                  error as HttpErrorResponse,
                  'No pudimos consultar la disponibilidad.',
                ),
          );
        },
      });
  }
}
