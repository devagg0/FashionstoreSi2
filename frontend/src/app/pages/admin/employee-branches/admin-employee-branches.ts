import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, HostListener, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { EMPTY, expand, finalize, forkJoin, reduce } from 'rxjs';
import { AdminApiErrorService } from '../../../core/services/admin-api-error.service';
import { AdminBranchesService, AdminBranch } from '../../../core/services/admin-branches.service';
import { AdminEmployeeBranchesService, Assignment, AssignmentPagination, EmployeeOption } from '../../../core/services/admin-employee-branches.service';
import { Icon } from '../../../shared/components/icon/icon';

@Component({
  selector: 'app-admin-employee-branches',
  imports: [ReactiveFormsModule, DatePipe, Icon],
  templateUrl: './admin-employee-branches.html',
  styleUrl: './admin-employee-branches.scss',
})
export class AdminEmployeeBranches implements OnInit {
  private readonly api = inject(AdminEmployeeBranchesService);
  private readonly branchesApi = inject(AdminBranchesService);
  private readonly errors = inject(AdminApiErrorService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly fb = inject(FormBuilder);
  protected readonly assignments = signal<Assignment[]>([]);
  protected readonly employees = signal<EmployeeOption[]>([]);
  private readonly historicalEmployees = signal<{ id_empleado: number; label: string }[]>([]);
  protected readonly filterEmployees = computed(() => [...new Map([
    ...this.historicalEmployees(),
    ...this.employees().map(e => ({ id_empleado: e.id_empleado, label: `${e.nombre} ${e.apellido} — ${e.rol}` })),
  ].map(e => [e.id_empleado, e])).values()]);
  protected readonly branches = signal<AdminBranch[]>([]);
  protected readonly activeBranches = computed(() => this.branches().filter(branch => branch.estado));
  protected readonly pagination = signal<AssignmentPagination>({ page: 1, page_size: 10, total: 0, total_pages: 0 });
  protected readonly loading = signal(false);
  protected readonly optionsLoading = signal(false);
  protected readonly optionsError = signal<string | null>(null);
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly successMessage = signal<string | null>(null);
  protected readonly modalError = signal<string | null>(null);
  protected readonly saving = signal(false);
  protected readonly formOpen = signal(false);
  protected readonly detailOpen = signal(false);
  protected readonly detailLoading = signal(false);
  protected readonly detail = signal<Assignment | null>(null);
  protected readonly statusAssignment = signal<Assignment | null>(null);
  protected readonly filters = this.fb.nonNullable.group({ id_empleado: 0, id_sucursal: 0, estado: '' });
  protected readonly form = this.fb.nonNullable.group({
    id_empleado: [0, [Validators.required, Validators.min(1)]],
    id_sucursal: [0, [Validators.required, Validators.min(1)]],
  });

  ngOnInit() { this.loadOptions(); this.loadAssignments(); }

  protected loadOptions() {
    if (this.optionsLoading()) return;
    this.optionsLoading.set(true);
    this.optionsError.set(null);
    forkJoin({
      employees: this.api.listEmployees().pipe(
        expand(r => r.pagination.page < r.pagination.total_pages ? this.api.listEmployees(r.pagination.page + 1, r.pagination.page_size) : EMPTY),
        reduce((all, r) => [...all, ...r.data], [] as EmployeeOption[]),
      ),
      branches: this.branchesApi.listBranches({ page: 1, pageSize: 100 }).pipe(
        expand(r => r.pagination.page < r.pagination.total_pages ? this.branchesApi.listBranches({ page: r.pagination.page + 1, pageSize: r.pagination.page_size }) : EMPTY),
        reduce((all, r) => [...all, ...r.data], [] as AdminBranch[]),
      ),
    }).pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.optionsLoading.set(false))).subscribe({
      next: ({ employees, branches }) => { this.employees.set(employees); this.branches.set(branches); },
      error: (e: HttpErrorResponse) => this.optionsError.set(this.resolve(e)),
    });
  }

  protected loadAssignments(page = 1) {
    if (this.loading()) return;
    const values = this.filters.getRawValue();
    this.loading.set(true);
    this.errorMessage.set(null);
    this.api.listAssignments({
      id_empleado: values.id_empleado || undefined, id_sucursal: values.id_sucursal || undefined,
      estado: values.estado === '' ? undefined : values.estado === 'true', page, pageSize: 10,
    }).pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.loading.set(false))).subscribe({
      next: r => {
        this.assignments.set(r.data); this.pagination.set(r.pagination);
        this.historicalEmployees.update(all => [...new Map([
          ...all, ...r.data.map(a => ({ id_empleado: a.id_empleado, label: `${a.nombre_empleado} — ${a.rol}` })),
        ].map(e => [e.id_empleado, e])).values()]);
        if (page > 1 && page > r.pagination.total_pages) {
          this.loading.set(false);
          this.loadAssignments(Math.max(1, r.pagination.total_pages));
        }
      },
      error: (e: HttpErrorResponse) => this.errorMessage.set(this.resolve(e)),
    });
  }
  protected clearFilters() { this.filters.reset(); this.loadAssignments(); }
  protected changePage(delta: number) {
    const page = this.pagination().page + delta;
    if (page >= 1 && page <= this.pagination().total_pages) this.loadAssignments(page);
  }
  protected openForm() {
    this.successMessage.set(null); this.modalError.set(null);
    this.form.reset(); this.formOpen.set(true); this.loadOptions();
  }
  protected submit() {
    if (this.saving() || this.optionsLoading() || this.optionsError()) return;
    if (this.form.invalid) { this.form.markAllAsTouched(); this.modalError.set('Selecciona un empleado y una sucursal.'); return; }
    this.saving.set(true); this.modalError.set(null);
    this.api.createAssignment(this.form.getRawValue()).pipe(
      takeUntilDestroyed(this.destroyRef), finalize(() => this.saving.set(false)),
    ).subscribe({
      next: r => {
        this.formOpen.set(false);
        this.successMessage.set(r.status === 201 ? 'Asignación creada correctamente.' : 'Asignación reactivada correctamente.');
        this.loadAssignments();
      },
      error: (e: HttpErrorResponse) => this.modalError.set(this.resolve(e)),
    });
  }
  protected viewDetail(id: number) {
    this.detail.set(null); this.detailOpen.set(true); this.detailLoading.set(true);
    this.api.getAssignment(id).pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.detailLoading.set(false))).subscribe({
      next: r => this.detail.set(r.data),
      error: (e: HttpErrorResponse) => { this.detailOpen.set(false); this.errorMessage.set(this.resolve(e)); },
    });
  }
  protected requestStatus(assignment: Assignment) { this.modalError.set(null); this.statusAssignment.set(assignment); }
  protected confirmStatus() {
    const assignment = this.statusAssignment();
    if (!assignment || this.saving()) return;
    this.saving.set(true); this.modalError.set(null);
    this.api.updateStatus(assignment.id_empleado_sucursal, !assignment.estado).pipe(
      takeUntilDestroyed(this.destroyRef), finalize(() => this.saving.set(false)),
    ).subscribe({
      next: r => {
        this.statusAssignment.set(null);
        this.successMessage.set(r.data.estado ? 'Asignación reactivada correctamente.' : 'Asignación desactivada correctamente.');
        this.loadAssignments(this.pagination().page);
      },
      error: (e: HttpErrorResponse) => this.modalError.set(this.resolve(e)),
    });
  }
  @HostListener('document:keydown.escape')
  protected closeModals() {
    if (this.saving() || this.detailLoading()) return;
    this.formOpen.set(false); this.detailOpen.set(false); this.statusAssignment.set(null); this.modalError.set(null);
  }
  private resolve(e: HttpErrorResponse) {
    return this.errors.resolve(e, {
      notFound: 'El empleado, la sucursal o la asignación ya no existe.',
      conflict: 'Esta asignación ya se encuentra activa o existe un conflicto con los datos actuales.',
      fallback: 'No pudimos completar la solicitud. Inténtalo nuevamente.',
    });
  }
}
