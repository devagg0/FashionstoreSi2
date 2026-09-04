import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, HostListener, inject, output, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { finalize } from 'rxjs';
import { AuthService } from '../../../core/services/auth.service';
import { Icon } from '../../../shared/components/icon/icon';
import {
  matchingFieldsValidator,
  PASSWORD_REQUIREMENTS,
  PasswordRequirement,
  passwordStrengthValidator,
} from '../../../shared/validators/auth.validators';

type RecoveryStep = 'email' | 'code' | 'password' | 'success';
type PasswordControlName = 'newPassword' | 'confirmPassword';

@Component({
  selector: 'app-password-recovery-modal',
  imports: [Icon, ReactiveFormsModule],
  templateUrl: './password-recovery-modal.html',
  styleUrl: './password-recovery-modal.scss',
})
export class PasswordRecoveryModal {
  private readonly authService = inject(AuthService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly formBuilder = inject(FormBuilder);
  private readonly emailAddress = signal('');
  private readonly resetToken = signal<string | null>(null);

  readonly closed = output<void>();

  protected readonly step = signal<RecoveryStep>('email');
  protected readonly isSubmitting = signal(false);
  protected readonly serverMessage = signal<string | null>(null);
  protected readonly showNewPassword = signal(false);
  protected readonly showConfirmation = signal(false);
  protected readonly passwordRequirements = PASSWORD_REQUIREMENTS;

  protected readonly emailForm = this.formBuilder.nonNullable.group({
    correo: ['', [Validators.required, Validators.email]],
  });
  protected readonly codeForm = this.formBuilder.nonNullable.group({
    codigo: ['', [Validators.required, Validators.pattern(/^\d{6}$/)]],
  });
  protected readonly passwordForm = this.formBuilder.nonNullable.group(
    {
      newPassword: [
        '',
        [Validators.required, Validators.minLength(8), passwordStrengthValidator()],
      ],
      confirmPassword: ['', Validators.required],
    },
    { validators: matchingFieldsValidator('newPassword', 'confirmPassword') },
  );

  @HostListener('document:keydown.escape')
  protected close(): void {
    this.clearFlow();
    this.closed.emit();
  }

  protected submitEmail(): void {
    if (this.isSubmitting()) {
      return;
    }

    this.serverMessage.set(null);
    const control = this.emailForm.controls.correo;
    const normalizedEmail = control.value.trim().toLowerCase();
    control.setValue(normalizedEmail);

    if (this.emailForm.invalid) {
      this.emailForm.markAllAsTouched();
      this.serverMessage.set('Revisa los datos ingresados.');
      return;
    }

    this.isSubmitting.set(true);
    this.authService
      .requestPasswordRecovery(normalizedEmail)
      .pipe(
        finalize(() => this.isSubmitting.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: () => {
          this.emailAddress.set(normalizedEmail);
          this.serverMessage.set(null);
          this.step.set('code');
        },
        error: (error: HttpErrorResponse) => this.handleRequestError(error),
      });
  }

  protected submitCode(): void {
    if (this.isSubmitting()) {
      return;
    }

    this.serverMessage.set(null);
    if (this.codeForm.invalid || !this.emailAddress()) {
      this.codeForm.markAllAsTouched();
      this.serverMessage.set('Revisa los datos ingresados.');
      return;
    }

    this.isSubmitting.set(true);
    this.authService
      .verifyPasswordRecovery(this.emailAddress(), this.codeForm.controls.codigo.value)
      .pipe(
        finalize(() => this.isSubmitting.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (response) => {
          this.resetToken.set(response.reset_token);
          this.emailAddress.set('');
          this.emailForm.reset();
          this.codeForm.reset();
          this.serverMessage.set(null);
          this.step.set('password');
        },
        error: (error: HttpErrorResponse) => this.handleVerifyError(error),
      });
  }

  protected submitPassword(): void {
    if (this.isSubmitting()) {
      return;
    }

    this.serverMessage.set(null);
    const token = this.resetToken();
    if (this.passwordForm.invalid || !token) {
      this.passwordForm.markAllAsTouched();
      this.serverMessage.set('Revisa los datos ingresados.');
      return;
    }

    const value = this.passwordForm.getRawValue();
    this.isSubmitting.set(true);
    this.authService
      .resetPassword(token, value.newPassword, value.confirmPassword)
      .pipe(
        finalize(() => this.isSubmitting.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: () => {
          this.resetToken.set(null);
          this.passwordForm.reset();
          this.resetPasswordVisibility();
          this.serverMessage.set(null);
          this.step.set('success');
        },
        error: (error: HttpErrorResponse) => this.handleResetError(error),
      });
  }

  protected sanitizeCode(): void {
    const control = this.codeForm.controls.codigo;
    const sanitized = control.value.replace(/\D/g, '').slice(0, 6);
    if (sanitized !== control.value) {
      control.setValue(sanitized);
    }
  }

  protected emailInvalid(): boolean {
    const control = this.emailForm.controls.correo;
    return control.invalid && (control.touched || control.dirty);
  }

  protected codeInvalid(): boolean {
    const control = this.codeForm.controls.codigo;
    return control.invalid && (control.touched || control.dirty);
  }

  protected passwordInvalid(controlName: PasswordControlName): boolean {
    const control = this.passwordForm.controls[controlName];
    return control.invalid && (control.touched || control.dirty);
  }

  protected confirmationMismatch(): boolean {
    const confirmation = this.passwordForm.controls.confirmPassword;
    return (
      this.passwordForm.hasError('passwordMismatch') && (confirmation.touched || confirmation.dirty)
    );
  }

  protected passwordMeets(requirement: PasswordRequirement): boolean {
    return requirement.test(this.passwordForm.controls.newPassword.value);
  }

  private handleRequestError(error: HttpErrorResponse): void {
    this.serverMessage.set(
      error.status === 422
        ? 'Revisa los datos ingresados.'
        : 'No pudimos completar la recuperación en este momento. Inténtalo nuevamente.',
    );
  }

  private handleVerifyError(error: HttpErrorResponse): void {
    if (error.status === 400) {
      this.serverMessage.set('El código es inválido o expiró.');
      return;
    }

    this.handleRequestError(error);
  }

  private handleResetError(error: HttpErrorResponse): void {
    if (error.status === 400) {
      this.serverMessage.set('La sesión de recuperación es inválida o expiró.');
      return;
    }

    this.handleRequestError(error);
  }

  private clearFlow(): void {
    this.emailForm.reset();
    this.codeForm.reset();
    this.passwordForm.reset();
    this.emailAddress.set('');
    this.resetToken.set(null);
    this.serverMessage.set(null);
    this.isSubmitting.set(false);
    this.step.set('email');
    this.resetPasswordVisibility();
  }

  private resetPasswordVisibility(): void {
    this.showNewPassword.set(false);
    this.showConfirmation.set(false);
  }
}
