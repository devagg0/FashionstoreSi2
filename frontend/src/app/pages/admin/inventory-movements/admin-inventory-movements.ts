import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, HostListener, inject, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, ValidatorFn, Validators } from '@angular/forms';
import { EMPTY, Observable, Subscription, expand, finalize, forkJoin, reduce } from 'rxjs';
import { AdminApiErrorService } from '../../../core/services/admin-api-error.service';
import { AdminBranch, AdminBranchesService } from '../../../core/services/admin-branches.service';
import {
  AdminEmployeeBranchesService,
  Assignment,
} from '../../../core/services/admin-employee-branches.service';
import {
  AdminProduct,
  AdminProductsService,
  AdminProductVariant,
} from '../../../core/services/admin-products.service';
import { AdminUsersService } from '../../../core/services/admin-users.service';
import {
  AdminInventoryMovementsService,
  Movement,
  MovementFilters,
  MovementFullData,
  MovementPagination,
  MovementState,
  MovementType,
} from '../../../core/services/admin-inventory-movements.service';
import { Icon } from '../../../shared/components/icon/icon';

export const movementRules: ValidatorFn = (control) => {
  const {
    tipo_movimiento: type,
    id_sucursal_origen: origin,
    id_sucursal_destino: destination,
    detalles = [],
  } = control.getRawValue();
  const errors: Record<string, boolean> = {};
  if (['SALIDA', 'AJUSTE_NEGATIVO', 'TRANSFERENCIA'].includes(type) && !origin)
    errors['origin'] = true;
  if (['ENTRADA', 'AJUSTE_POSITIVO', 'TRANSFERENCIA'].includes(type) && !destination)
    errors['destination'] = true;
  if (type === 'TRANSFERENCIA' && origin && origin === destination) errors['sameBranch'] = true;
  if (!detalles.length) errors['noDetails'] = true;
  const ids = detalles
    .map((row: { id_variante_producto: number | null }) => row.id_variante_producto)
    .filter(Boolean);
  if (new Set(ids).size !== ids.length) errors['duplicateVariant'] = true;
  return Object.keys(errors).length ? errors : null;
};

// Follow the existing paginated option endpoints through their final page.
function allPages<T>(
  fetch: (page: number) => Observable<{ data: T[]; pagination: MovementPagination }>,
): Observable<T[]> {
  return fetch(1).pipe(
    expand((response) =>
      response.pagination.page < response.pagination.total_pages
        ? fetch(response.pagination.page + 1)
        : EMPTY,
    ),
    reduce((rows, response) => [...rows, ...response.data], [] as T[]),
  );
}

@Component({
  selector: 'app-admin-inventory-movements',
  imports: [ReactiveFormsModule, Icon],
  templateUrl: './admin-inventory-movements.html',
  styleUrl: './admin-inventory-movements.scss',
})
export class AdminInventoryMovements implements OnInit {
  private readonly destroyRef = inject(DestroyRef);
  private readonly fb = inject(FormBuilder);
  private readonly service = inject(AdminInventoryMovementsService);
  private readonly branchesService = inject(AdminBranchesService);
  private readonly productsService = inject(AdminProductsService);
  private readonly assignmentsService = inject(AdminEmployeeBranchesService);
  private readonly usersService = inject(AdminUsersService);
  private readonly errors = inject(AdminApiErrorService);
  protected readonly types: MovementType[] = [
    'ENTRADA',
    'SALIDA',
    'TRANSFERENCIA',
    'AJUSTE_POSITIVO',
    'AJUSTE_NEGATIVO',
  ];
  protected readonly states: MovementState[] = ['PENDIENTE', 'CONFIRMADO', 'ANULADO'];
  protected readonly movements = signal<Movement[]>([]);
  protected readonly pagination = signal<MovementPagination>({
    page: 1,
    page_size: 10,
    total: 0,
    total_pages: 0,
  });
  protected readonly loading = signal(false);
  protected readonly saving = signal(false);
  protected readonly optionsLoading = signal(false);
  protected readonly responsibleLoading = signal(false);
  protected readonly detailLoading = signal(false);
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly successMessage = signal<string | null>(null);
  protected readonly modalError = signal<string | null>(null);
  protected readonly optionsError = signal<string | null>(null);
  protected readonly actionError = signal<string | null>(null);
  protected readonly createOpen = signal(false);
  protected readonly detailOpen = signal(false);
  protected readonly detail = signal<MovementFullData | null>(null);
  protected readonly action = signal<{ movement: Movement; kind: 'confirm' | 'cancel' } | null>(
    null,
  );
  protected readonly branches = signal<AdminBranch[]>([]);
  protected readonly products = signal<AdminProduct[]>([]);
  protected readonly variants = signal<Record<number, AdminProductVariant[]>>({});
  protected readonly variantLoading = signal<Record<number, boolean>>({});
  protected readonly responsibleOptions = signal<Assignment[]>([]);
  protected readonly filterProduct = this.fb.control<number | null>(null);
  protected readonly filters = this.fb.nonNullable.group({
    search: ['', Validators.maxLength(200)],
    tipo_movimiento: '',
    estado: '',
    id_sucursal: this.fb.control<number | null>(null),
    id_variante_producto: this.fb.control<number | null>(null),
    fecha_desde: '',
    fecha_hasta: '',
  });
  protected readonly form = this.fb.nonNullable.group(
    {
      tipo_movimiento: ['ENTRADA' as MovementType, Validators.required],
      id_sucursal_origen: this.fb.control<number | null>(null),
      id_sucursal_destino: this.fb.control<number | null>(null),
      id_empleado_sucursal: this.fb.control<number | null>(null, Validators.required),
      motivo: ['', Validators.maxLength(200)],
      detalles: this.fb.array([this.newDetail()]),
    },
    { validators: movementRules },
  );
  protected get details() {
    return this.form.controls.detalles;
  }
  private listRequest?: Subscription;
  private responsibleRequest?: Subscription;
  private detailRequest?: Subscription;
  private appliedFilters: MovementFilters = {};

  ngOnInit(): void {
    this.loadMovements();
    this.loadOptions();
    this.form.controls.tipo_movimiento.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.changeType());
    for (const field of ['id_sucursal_origen', 'id_sucursal_destino'] as const) {
      this.form.controls[field].valueChanges
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe(() => this.loadResponsible());
    }
    this.filterProduct.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((id) => {
      this.filters.controls.id_variante_producto.reset();
      if (id) this.loadVariants(id);
    });
  }

  protected loadOptions(): void {
    this.optionsLoading.set(true);
    this.optionsError.set(null);
    forkJoin({
      branches: allPages((page) => this.branchesService.listBranches({ page, pageSize: 100 })),
      products: allPages((page) => this.productsService.listProducts({ page, pageSize: 100 })),
    })
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.optionsLoading.set(false)),
      )
      .subscribe({
        next: ({ branches, products }) => {
          this.branches.set(branches);
          this.products.set(products);
        },
        error: (error: HttpErrorResponse) => this.optionsError.set(this.resolveError(error)),
      });
  }

  protected applyFilters(): void {
    const raw = this.filters.getRawValue();
    if (
      this.filters.invalid ||
      (raw.fecha_desde && raw.fecha_hasta && raw.fecha_desde > raw.fecha_hasta)
    ) {
      this.errorMessage.set(
        'Revisa la búsqueda y el rango de fechas: desde no puede ser posterior a hasta.',
      );
      return;
    }
    this.appliedFilters = {
      search: raw.search,
      tipo_movimiento: (raw.tipo_movimiento as MovementType) || undefined,
      estado: (raw.estado as MovementState) || undefined,
      id_sucursal: raw.id_sucursal ?? undefined,
      id_variante_producto: raw.id_variante_producto ?? undefined,
      fecha_desde: raw.fecha_desde ? new Date(raw.fecha_desde).toISOString() : undefined,
      fecha_hasta: raw.fecha_hasta ? new Date(raw.fecha_hasta).toISOString() : undefined,
    };
    this.loadMovements();
  }
  protected clearFilters(): void {
    this.filters.reset();
    this.filterProduct.reset();
    this.appliedFilters = {};
    this.loadMovements();
  }
  protected loadMovements(page = 1): void {
    this.listRequest?.unsubscribe();
    this.loading.set(true);
    this.errorMessage.set(null);
    this.listRequest = this.service
      .listMovements({ ...this.appliedFilters, page, pageSize: 10 })
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.loading.set(false)),
      )
      .subscribe({
        next: (response) => {
          this.movements.set(response.data);
          this.pagination.set(response.pagination);
        },
        error: (error: HttpErrorResponse) => this.errorMessage.set(this.resolveError(error)),
      });
  }
  protected openCreate(): void {
    this.form.reset({ tipo_movimiento: 'ENTRADA', motivo: '' }, { emitEvent: false });
    this.details.clear();
    this.addDetail();
    this.changeType();
    this.modalError.set(null);
    this.successMessage.set(null);
    this.createOpen.set(true);
  }
  protected hasOrigin(): boolean {
    return ['SALIDA', 'AJUSTE_NEGATIVO', 'TRANSFERENCIA'].includes(
      this.form.controls.tipo_movimiento.value,
    );
  }
  protected hasDestination(): boolean {
    return ['ENTRADA', 'AJUSTE_POSITIVO', 'TRANSFERENCIA'].includes(
      this.form.controls.tipo_movimiento.value,
    );
  }
  protected changeType(): void {
    for (const [field, visible] of [
      ['id_sucursal_origen', this.hasOrigin()],
      ['id_sucursal_destino', this.hasDestination()],
    ] as const) {
      const control = this.form.controls[field];
      if (visible) control.enable({ emitEvent: false });
      else {
        control.reset(null, { emitEvent: false });
        control.disable({ emitEvent: false });
      }
    }
    this.form.updateValueAndValidity({ emitEvent: false });
    this.loadResponsible();
  }
  protected loadResponsible(): void {
    this.responsibleRequest?.unsubscribe();
    this.form.controls.id_empleado_sucursal.reset();
    this.responsibleOptions.set([]);
    const branch = this.hasOrigin()
      ? this.form.controls.id_sucursal_origen.value
      : this.form.controls.id_sucursal_destino.value;
    if (!branch) return;
    this.responsibleLoading.set(true);
    this.modalError.set(null);
    this.responsibleRequest = forkJoin({
      assignments: allPages((page) =>
        this.assignmentsService.listAssignments({
          id_sucursal: branch,
          estado: true,
          page,
          pageSize: 100,
        }),
      ),
      employees: allPages((page) => this.assignmentsService.listEmployees(page, 100)),
      roles: this.usersService.listRoles(),
    })
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.responsibleLoading.set(false)),
      )
      .subscribe({
        next: ({ assignments, employees, roles }) => {
          const activeRoles = new Set(
            roles.data
              .filter(
                (role) =>
                  role.estado &&
                  ['CAJERO', 'ENCARGADO_SUCURSAL'].includes(role.nombre.toUpperCase()),
              )
              .map((role) => role.nombre.toUpperCase()),
          );
          const activeEmployees = new Set(
            employees
              .filter((employee) => employee.estado && activeRoles.has(employee.rol.toUpperCase()))
              .map((employee) => employee.id_empleado),
          );
          this.responsibleOptions.set(
            assignments.filter(
              (assignment) =>
                assignment.estado &&
                assignment.id_sucursal === branch &&
                activeEmployees.has(assignment.id_empleado),
            ),
          );
        },
        error: (error: HttpErrorResponse) => this.modalError.set(this.resolveError(error)),
      });
  }
  private newDetail() {
    return this.fb.group({
      id_producto: this.fb.control<number | null>(null, Validators.required),
      id_variante_producto: this.fb.control<number | null>(null, Validators.required),
      cantidad: [1, [Validators.required, Validators.min(1), Validators.pattern(/^\d+$/)]],
      costo_unitario: this.fb.control<number | null>(null, [
        Validators.min(0),
        Validators.pattern(/^\d{1,8}(?:\.\d{1,2})?$/),
      ]),
    });
  }
  protected addDetail(): void {
    this.details.push(this.newDetail());
  }
  protected removeDetail(index: number): void {
    this.details.removeAt(index);
  }
  protected selectProduct(index: number): void {
    const row = this.details.at(index);
    row.controls.id_variante_producto.reset();
    const id = row.controls.id_producto.value;
    if (id) this.loadVariants(id);
  }
  protected loadVariants(id: number): void {
    if (this.variants()[id] || this.variantLoading()[id]) return;
    this.variantLoading.update((value) => ({ ...value, [id]: true }));
    this.productsService
      .getProduct(id)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.variantLoading.update((value) => ({ ...value, [id]: false }))),
      )
      .subscribe({
        next: ({ data }) => this.variants.update((value) => ({ ...value, [id]: data.variantes })),
        error: (error: HttpErrorResponse) => {
          const message = this.resolveError(error);
          this.modalError.set(message);
          this.errorMessage.set(message);
        },
      });
  }
  protected variantOptions(id: number | null, activeOnly = false): AdminProductVariant[] {
    return (id ? (this.variants()[id] ?? []) : []).filter(
      (variant) => !activeOnly || variant.estado,
    );
  }
  protected submitMovement(): void {
    if (this.saving()) return;
    this.form.markAllAsTouched();
    if (this.form.invalid) {
      this.modalError.set(
        'Revisa los campos: sucursales válidas, responsable, variantes únicas, cantidades enteras mayores que cero y costos de hasta 8 enteros y 2 decimales. Se requiere al menos un detalle.',
      );
      return;
    }
    const raw = this.form.getRawValue();
    if (
      !this.responsibleOptions().some(
        (item) => item.id_empleado_sucursal === raw.id_empleado_sucursal,
      )
    ) {
      this.modalError.set('Selecciona un responsable compatible con la sucursal.');
      return;
    }
    this.saving.set(true);
    this.modalError.set(null);
    this.service
      .createMovement({
        tipo_movimiento: raw.tipo_movimiento,
        id_sucursal_origen: raw.id_sucursal_origen,
        id_sucursal_destino: raw.id_sucursal_destino,
        id_empleado_sucursal: raw.id_empleado_sucursal!,
        motivo: raw.motivo.trim() || null,
        detalles: raw.detalles.map((row) => ({
          id_variante_producto: row.id_variante_producto!,
          cantidad: row.cantidad!,
          costo_unitario: row.costo_unitario,
        })),
      })
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.saving.set(false)),
      )
      .subscribe({
        next: () => {
          this.createOpen.set(false);
          this.successMessage.set('Movimiento registrado correctamente.');
          this.loadMovements();
        },
        error: (error: HttpErrorResponse) => this.modalError.set(this.resolveError(error)),
      });
  }
  protected viewDetail(id: number): void {
    this.detailRequest?.unsubscribe();
    this.detail.set(null);
    this.detailOpen.set(true);
    this.detailLoading.set(true);
    this.modalError.set(null);
    this.detailRequest = this.service
      .getMovement(id)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.detailLoading.set(false)),
      )
      .subscribe({
        next: ({ data }) => this.detail.set(data),
        error: (error: HttpErrorResponse) => this.modalError.set(this.resolveError(error)),
      });
  }
  protected openAction(movement: Movement, kind: 'confirm' | 'cancel'): void {
    if (movement.estado !== 'PENDIENTE') return;
    this.actionError.set(null);
    this.successMessage.set(null);
    this.action.set({ movement, kind });
  }
  protected executeAction(): void {
    const action = this.action();
    if (!action || this.saving()) return;
    this.saving.set(true);
    this.actionError.set(null);
    const id = action.movement.id_movimiento_inventario;
    const request =
      action.kind === 'confirm'
        ? this.service.confirmMovement(id)
        : this.service.cancelMovement(id);
    request
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.saving.set(false)),
      )
      .subscribe({
        next: ({ data }) => {
          this.action.set(null);
          this.successMessage.set(
            action.kind === 'confirm'
              ? 'Movimiento confirmado correctamente.'
              : 'Movimiento anulado correctamente.',
          );
          if (this.detail()?.id_movimiento_inventario === id) this.detail.set(data);
          this.loadMovements(this.pagination().page);
        },
        error: (error: HttpErrorResponse) => this.actionError.set(this.resolveError(error)),
      });
  }
  protected closeCreate(): void {
    if (!this.saving()) this.createOpen.set(false);
  }
  protected closeDetail(): void {
    if (!this.saving()) {
      this.detailRequest?.unsubscribe();
      this.detailOpen.set(false);
    }
  }
  protected closeAction(): void {
    if (!this.saving()) this.action.set(null);
  }
  @HostListener('document:keydown.escape') protected closeModal(): void {
    if (this.action()) this.closeAction();
    else if (this.createOpen()) this.closeCreate();
    else this.closeDetail();
  }
  protected label(value: string): string {
    return value.replaceAll('_', ' ');
  }
  protected formatDate(value: string): string {
    return new Intl.DateTimeFormat('es-BO', { dateStyle: 'medium', timeStyle: 'short' }).format(
      new Date(/(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`),
    );
  }
  protected resolveError(error: HttpErrorResponse): string {
    const message =
      [400, 404, 409].includes(error.status) && typeof error.error?.message === 'string'
        ? error.error.message
        : undefined;
    return this.errors.resolve(error, {
      notFound: message,
      conflict: message,
      fallback:
        message ??
        (error.status === 400
          ? 'Datos inválidos.'
          : 'No pudimos procesar el movimiento de inventario. Inténtalo nuevamente.'),
    });
  }
}
