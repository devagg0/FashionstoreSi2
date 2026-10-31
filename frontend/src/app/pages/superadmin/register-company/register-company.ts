import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { finalize } from 'rxjs';
import {
  CompanyCreateRequest,
  SaasCompaniesService,
  SaasCompany,
} from '../../../core/services/saas-companies.service';
import { SessionService } from '../../../core/services/session.service';
import { Icon } from '../../../shared/components/icon/icon';
import { trimmedLengthValidator } from '../../../shared/validators/auth.validators';

interface ApiErrorBody {
  message?: string;
}

@Component({
  selector: 'app-register-company',
  imports: [DatePipe, Icon, ReactiveFormsModule],
  templateUrl: './register-company.html',
  styleUrl: './register-company.scss',
})
export class RegisterCompany {
  private readonly companiesService = inject(SaasCompaniesService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly formBuilder = inject(FormBuilder);
  private readonly router = inject(Router);
  private readonly sessionService = inject(SessionService);

  protected readonly submitting = signal(false);
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly createdCompany = signal<SaasCompany | null>(null);
  protected readonly timezones = [
    { value: 'America/La_Paz', label: 'Bolivia · La Paz (GMT-4)' },
    { value: 'America/Lima', label: 'Perú · Lima (GMT-5)' },
    { value: 'America/Santiago', label: 'Chile · Santiago' },
    { value: 'America/Argentina/Buenos_Aires', label: 'Argentina · Buenos Aires (GMT-3)' },
    { value: 'America/Sao_Paulo', label: 'Brasil · São Paulo' },
  ] as const;

  protected readonly companyForm = this.formBuilder.nonNullable.group({
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

  protected submit(): void {
    if (this.submitting()) return;

    this.normalizeFields();
    this.errorMessage.set(null);
    if (this.companyForm.invalid) {
      this.companyForm.markAllAsTouched();
      this.errorMessage.set('Revisa los campos marcados antes de continuar.');
      return;
    }

    const values = this.companyForm.getRawValue();
    const request: CompanyCreateRequest = {
      codigo: values.codigo,
      nombre: values.nombre,
      nit: values.nit || null,
      zona_horaria: values.zona_horaria,
    };

    this.submitting.set(true);
    this.companiesService
      .createCompany(request)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.submitting.set(false)),
      )
      .subscribe({
        next: (response) => {
          this.createdCompany.set(response.data);
          this.companyForm.disable({ emitEvent: false });
        },
        error: (error: HttpErrorResponse) => this.handleError(error),
      });
  }

  protected registerAnother(): void {
    this.createdCompany.set(null);
    this.errorMessage.set(null);
    this.companyForm.enable({ emitEvent: false });
    this.companyForm.reset({
      codigo: '',
      nombre: '',
      nit: '',
      zona_horaria: 'America/La_Paz',
    });
  }

  protected normalizeCode(): void {
    const control = this.companyForm.controls.codigo;
    control.setValue(control.value.trim().toLowerCase(), { emitEvent: false });
  }

  protected isInvalid(field: keyof typeof this.companyForm.controls): boolean {
    const control = this.companyForm.controls[field];
    return control.invalid && (control.touched || control.dirty);
  }

  private normalizeFields(): void {
    this.normalizeCode();
    const name = this.companyForm.controls.nombre;
    const nit = this.companyForm.controls.nit;
    name.setValue(name.value.trim(), { emitEvent: false });
    nit.setValue(nit.value.trim(), { emitEvent: false });
    this.companyForm.updateValueAndValidity({ emitEvent: false });
  }

  private handleError(error: HttpErrorResponse): void {
    const backendMessage = (error.error as ApiErrorBody | null)?.message;
    if (error.status === 401) {
      this.sessionService.logout();
      this.errorMessage.set('Tu sesión expiró. Inicia sesión nuevamente.');
      void this.router.navigateByUrl('/login', {
        state: { successMessage: 'Tu sesión expiró. Inicia sesión nuevamente.' },
      });
      return;
    }
    if (error.status === 403) {
      this.errorMessage.set('Tu cuenta no tiene permisos de SUPERADMIN para registrar empresas.');
      return;
    }
    if (error.status === 409) {
      this.errorMessage.set(backendMessage ?? 'El código o NIT ya pertenece a otra empresa.');
      return;
    }
    if (error.status === 422) {
      this.errorMessage.set('El servidor rechazó los datos. Revisa el formato de cada campo.');
      return;
    }
    this.errorMessage.set('No pudimos registrar la empresa. Inténtalo nuevamente.');
  }
}
