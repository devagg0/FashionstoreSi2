import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import {
  AuthService,
  RegisterClientRequest,
} from '../../core/services/auth.service';
import { AuthLayout } from '../../layout/auth-layout/auth-layout';
import { Icon } from '../../shared/components/icon/icon';
import {
  matchingFieldsValidator,
  optionalPhoneValidator,
  PASSWORD_REQUIREMENTS,
  PasswordRequirement,
  passwordStrengthValidator,
  trimmedLengthValidator,
} from '../../shared/validators/auth.validators';

type RegisterControlName =
  | 'nombre'
  | 'apellido'
  | 'correo'
  | 'telefono'
  | 'password'
  | 'confirmPassword';

@Component({
  selector: 'app-register',
  imports: [AuthLayout, Icon, ReactiveFormsModule, RouterLink],
  templateUrl: './register.html',
  styleUrl: './register.scss',
})
export class Register {
  private readonly authService = inject(AuthService);
  private readonly formBuilder = inject(FormBuilder);

  protected readonly isSubmitting = signal(false);
  protected readonly registrationSuccess = signal(false);
  protected readonly serverMessage = signal<string | null>(null);
  protected readonly showPassword = signal(false);
  protected readonly showConfirmation = signal(false);
  protected readonly passwordRequirements = PASSWORD_REQUIREMENTS;

  protected readonly registerForm = this.formBuilder.nonNullable.group(
    {
      nombre: ['', [Validators.required, trimmedLengthValidator(2, 100)]],
      apellido: ['', [Validators.required, trimmedLengthValidator(2, 100)]],
      correo: ['', [Validators.required, Validators.email]],
      telefono: ['', optionalPhoneValidator()],
      password: [
        '',
        [Validators.required, Validators.minLength(8), passwordStrengthValidator()],
      ],
      confirmPassword: ['', Validators.required],
    },
    { validators: matchingFieldsValidator('password', 'confirmPassword') },
  );

  protected isInvalid(controlName: RegisterControlName): boolean {
    const control = this.registerForm.controls[controlName];
    return control.invalid && (control.touched || control.dirty);
  }

  protected hasError(controlName: RegisterControlName, errorName: string): boolean {
    return this.registerForm.controls[controlName].hasError(errorName);
  }

  protected confirmationMismatch(): boolean {
    const confirmation = this.registerForm.controls.confirmPassword;
    return (
      this.registerForm.hasError('passwordMismatch') &&
      (confirmation.touched || confirmation.dirty)
    );
  }

  protected passwordMeets(requirement: PasswordRequirement): boolean {
    return requirement.test(this.registerForm.controls.password.value);
  }

  protected submitRegistration(): void {
    if (this.isSubmitting()) {
      return;
    }

    this.serverMessage.set(null);

    if (this.registerForm.invalid) {
      this.registerForm.markAllAsTouched();
      this.serverMessage.set('Revisa los datos ingresados.');
      return;
    }

    const value = this.registerForm.getRawValue();
    const phone = value.telefono.trim();
    const payload: RegisterClientRequest = {
      nombre: value.nombre.trim(),
      apellido: value.apellido.trim(),
      correo: value.correo.trim().toLowerCase(),
      telefono: phone || null,
      password: value.password,
      confirm_password: value.confirmPassword,
    };

    this.isSubmitting.set(true);
    this.authService
      .registerClient(payload)
      .pipe(finalize(() => this.isSubmitting.set(false)))
      .subscribe({
        next: () => {
          this.registrationSuccess.set(true);
          this.registerForm.reset();
        },
        error: (error: HttpErrorResponse) => this.handleRegistrationError(error),
      });
  }

  private handleRegistrationError(error: HttpErrorResponse): void {
    if (error.status === 409) {
      const emailControl = this.registerForm.controls.correo;
      emailControl.setErrors({ ...emailControl.errors, emailTaken: true });
      emailControl.markAsTouched();
      return;
    }

    if (error.status === 422) {
      this.serverMessage.set('Revisa los datos ingresados.');
      return;
    }

    this.serverMessage.set(
      'No pudimos crear tu cuenta en este momento. Inténtalo nuevamente.',
    );
  }
}
