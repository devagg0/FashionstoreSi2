import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, HostListener, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import {
  CompanyPagination,
  CompanyState,
  CompanyUpdateRequest,
  SaasCompaniesService,
  SaasCompany,
} from '../../../core/services/saas-companies.service';
import { SessionService } from '../../../core/services/session.service';
import {
  CompanyBranchConsumptionResponse,
  CompanyPlanLimitsResponse,
  SaasPlanLimitsService,
} from '../../../core/services/saas-plan-limits.service';
import { Icon } from '../../../shared/components/icon/icon';
import { trimmedLengthValidator } from '../../../shared/validators/auth.validators';

type CompanyModal = 'detail' | 'edit' | 'state' | null;

interface ApiErrorBody {
  message?: string;
}

const EMPTY_PAGINATION: CompanyPagination = {
  page: 1,
  page_size: 10,
  total: 0,
  total_pages: 0,
};

@Component({
  selector: 'app-manage-companies',
  imports: [DatePipe, Icon, ReactiveFormsModule, RouterLink],
  templateUrl: './manage-companies.html',
  styleUrl: './manage-companies.scss',
})
export class ManageCompanies implements OnInit {
  private readonly companiesService = inject(SaasCompaniesService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly formBuilder = inject(FormBuilder);
  private readonly router = inject(Router);
  private readonly sessionService = inject(SessionService);
  private readonly planLimitsService = inject(SaasPlanLimitsService);

  protected readonly companyPlan = signal<CompanyPlanLimitsResponse | null>(null);
  protected readonly companyConsumption = signal<CompanyBranchConsumptionResponse | null>(null);
  protected readonly planLoading = signal(false);
  private listRequestId = 0;

  protected readonly companies = signal<SaasCompany[]>([]);
  protected readonly pagination = signal<CompanyPagination>(EMPTY_PAGINATION);
  protected readonly loading = signal(false);
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly successMessage = signal<string | null>(null);
  protected readonly activeSearch = signal('');
  protected readonly activeState = signal<CompanyState | ''>('');

  protected readonly modal = signal<CompanyModal>(null);
  protected readonly selectedCompany = signal<SaasCompany | null>(null);
  protected readonly detailLoading = signal(false);
  protected readonly saving = signal(false);
  protected readonly modalErrorMessage = signal<string | null>(null);
  protected readonly stateTarget = signal<CompanyState | null>(null);

  protected readonly timezones = [
    { value: 'America/La_Paz', label: 'Bolivia · La Paz (GMT-4)' },
    { value: 'America/Lima', label: 'Perú · Lima (GMT-5)' },
    { value: 'America/Santiago', label: 'Chile · Santiago' },
    { value: 'America/Argentina/Buenos_Aires', label: 'Argentina · Buenos Aires (GMT-3)' },
    { value: 'America/Sao_Paulo', label: 'Brasil · São Paulo' },
  ] as const;

  protected readonly filtersForm = this.formBuilder.nonNullable.group({
    search: ['', [Validators.maxLength(150)]],
    estado: this.formBuilder.nonNullable.control<CompanyState | ''>(''),
  });

  protected readonly editForm = this.formBuilder.nonNullable.group({
    codigo: [
      '',
      [
        Validators.required,
        Validators.maxLength(63),
        Validators.pattern(/^[a-z0-9]+(?:-[a-z0-9]+)*$/),
      ],
    ],
    nombre: ['', [Validators.required, trimmedLengthValidator(1, 150)]],
    nit: ['', [Validators.maxLength(30), Validators.pattern(/^\d{5,30}$/)]],
    zona_horaria: ['America/La_Paz', [Validators.required, Validators.maxLength(50)]],
  });

  ngOnInit(): void {
    this.loadCompanies();
  }

  protected loadCompanies(page = 1): void {
    const requestId = ++this.listRequestId;
    this.loading.set(true);
    this.errorMessage.set(null);
    this.companiesService
      .listCompanies({
        search: this.activeSearch() || undefined,
        estado: this.activeState() || undefined,
        page,
        pageSize: this.pagination().page_size || 10,
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (response) => {
          if (requestId !== this.listRequestId) return;
          if (
            page > 1 &&
            response.data.length === 0 &&
            response.pagination.total_pages < page
          ) {
            this.loadCompanies(Math.max(1, response.pagination.total_pages));
            return;
          }
          this.companies.set(response.data);
          this.pagination.set(response.pagination);
          this.loading.set(false);
        },
        error: (error: HttpErrorResponse) => {
          if (requestId !== this.listRequestId) return;
          this.loading.set(false);
          this.handlePageError(error);
        },
      });
  }

  protected applyFilters(): void {
    if (this.filtersForm.invalid) {
      this.filtersForm.markAllAsTouched();
      return;
    }
    const values = this.filtersForm.getRawValue();
    this.activeSearch.set(values.search.trim());
    this.activeState.set(values.estado);
    this.successMessage.set(null);
    this.loadCompanies(1);
  }

  protected resetFilters(): void {
    this.filtersForm.reset({ search: '', estado: '' });
    this.activeSearch.set('');
    this.activeState.set('');
    this.successMessage.set(null);
    this.loadCompanies(1);
  }

  protected previousPage(): void {
    if (!this.loading() && this.pagination().page > 1) {
      this.loadCompanies(this.pagination().page - 1);
    }
  }

  protected nextPage(): void {
    const pagination = this.pagination();
    if (!this.loading() && pagination.page < pagination.total_pages) {
      this.loadCompanies(pagination.page + 1);
    }
  }

  protected openDetails(company: SaasCompany): void {
    this.modal.set('detail');
    this.selectedCompany.set(company);
    this.modalErrorMessage.set(null);
    this.detailLoading.set(true);
    this.planLoading.set(true);
    this.companyPlan.set(null);
    this.companyConsumption.set(null);

    this.companiesService
      .getCompany(company.id_empresa)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.detailLoading.set(false)),
      )
      .subscribe({
        next: (response) => this.selectedCompany.set(response.data),
        error: (error: HttpErrorResponse) => this.handleModalError(error),
      });

    this.planLimitsService
      .getCompanyPlanLimitsById(company.id_empresa)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.planLoading.set(false)),
      )
      .subscribe({
        next: (resp) => this.companyPlan.set(resp),
        error: () => {},
      });

    this.planLimitsService
      .getCompanyBranchConsumptionById(company.id_empresa)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (resp) => this.companyConsumption.set(resp),
        error: () => {},
      });
  }

  protected openEdit(company: SaasCompany): void {
    this.selectedCompany.set(company);
    this.modalErrorMessage.set(null);
    this.editForm.reset({
      codigo: company.codigo,
      nombre: company.nombre,
      nit: company.nit ?? '',
      zona_horaria: company.zona_horaria,
    });
    this.modal.set('edit');
  }

  protected saveEdit(): void {
    const company = this.selectedCompany();
    if (!company || this.saving()) return;
    this.normalizeEditFields();
    this.modalErrorMessage.set(null);
    if (this.editForm.invalid) {
      this.editForm.markAllAsTouched();
      this.modalErrorMessage.set('Revisa los campos marcados antes de guardar.');
      return;
    }
    const values = this.editForm.getRawValue();
    const payload: CompanyUpdateRequest = {
      codigo: values.codigo,
      nombre: values.nombre,
      nit: values.nit || null,
      zona_horaria: values.zona_horaria,
    };
    this.saving.set(true);
    this.companiesService
      .updateCompany(company.id_empresa, payload)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.saving.set(false)),
      )
      .subscribe({
        next: (response) => {
          this.selectedCompany.set(response.data);
          this.modal.set(null);
          this.successMessage.set('Empresa actualizada correctamente.');
          this.loadCompanies(this.pagination().page);
        },
        error: (error: HttpErrorResponse) => this.handleModalError(error),
      });
  }

  protected openStateDialog(company: SaasCompany, target: CompanyState): void {
    this.selectedCompany.set(company);
    this.stateTarget.set(target);
    this.modalErrorMessage.set(null);
    this.modal.set('state');
  }

  protected confirmStateChange(): void {
    const company = this.selectedCompany();
    const target = this.stateTarget();
    if (!company || !target || this.saving()) return;
    this.saving.set(true);
    this.modalErrorMessage.set(null);
    this.companiesService
      .updateCompanyState(company.id_empresa, target)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.saving.set(false)),
      )
      .subscribe({
        next: (response) => {
          this.selectedCompany.set(response.data);
          this.modal.set(null);
          this.successMessage.set(`Empresa ${target.toLowerCase()} correctamente.`);
          this.loadCompanies(this.pagination().page);
        },
        error: (error: HttpErrorResponse) => this.handleModalError(error),
      });
  }

  protected closeModal(): void {
    if (this.saving()) return;
    this.modal.set(null);
    this.selectedCompany.set(null);
    this.stateTarget.set(null);
    this.modalErrorMessage.set(null);
  }

  protected isEditInvalid(field: keyof typeof this.editForm.controls): boolean {
    const control = this.editForm.controls[field];
    return control.invalid && (control.touched || control.dirty);
  }

  protected stateVerb(state: CompanyState | null): string {
    return state === 'ACTIVA' ? 'activar' : state === 'SUSPENDIDA' ? 'suspender' : 'cancelar';
  }

  @HostListener('document:keydown.escape')
  protected closeWithEscape(): void {
    this.closeModal();
  }

  private normalizeEditFields(): void {
    const controls = this.editForm.controls;
    controls.codigo.setValue(controls.codigo.value.trim().toLowerCase(), { emitEvent: false });
    controls.nombre.setValue(controls.nombre.value.trim(), { emitEvent: false });
    controls.nit.setValue(controls.nit.value.trim(), { emitEvent: false });
    this.editForm.updateValueAndValidity({ emitEvent: false });
  }

  private handlePageError(error: HttpErrorResponse): void {
    if (error.status === 401) {
      this.expireSession();
      return;
    }
    if (error.status === 403) {
      this.errorMessage.set('Tu cuenta no tiene permisos para gestionar empresas.');
      return;
    }
    this.errorMessage.set('No pudimos cargar las empresas. Inténtalo nuevamente.');
  }

  private handleModalError(error: HttpErrorResponse): void {
    const backendMessage = (error.error as ApiErrorBody | null)?.message;
    if (error.status === 401) {
      this.expireSession();
      return;
    }
    if (error.status === 403) {
      this.modalErrorMessage.set('Tu cuenta no tiene permisos para realizar esta acción.');
    } else if (error.status === 404) {
      this.modalErrorMessage.set('La empresa ya no existe o no está disponible.');
    } else if (error.status === 409) {
      this.modalErrorMessage.set(backendMessage ?? 'La operación entra en conflicto con el estado actual.');
    } else if (error.status === 422) {
      this.modalErrorMessage.set('El servidor rechazó los datos. Revisa el formulario.');
    } else {
      this.modalErrorMessage.set('No pudimos completar la operación. Inténtalo nuevamente.');
    }
  }

  private expireSession(): void {
    this.sessionService.logout();
    void this.router.navigateByUrl('/login', {
      state: { successMessage: 'Tu sesión expiró. Inicia sesión nuevamente.' },
    });
  }
}
