import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { finalize } from 'rxjs';
import { AuthService, ChangePasswordRequest } from '../../core/services/auth.service';
import { SessionService } from '../../core/services/session.service';
import { Icon } from '../../shared/components/icon/icon';
import {
  matchingFieldsValidator,
  PASSWORD_REQUIREMENTS,
  PasswordRequirement,
  passwordStrengthValidator,
} from '../../shared/validators/auth.validators';

type PasswordControlName = 'currentPassword' | 'newPassword' | 'confirmPassword';

@Component({
  selector: 'app-profile',
  imports: [Icon, ReactiveFormsModule],
  templateUrl: './profile.html',
  styleUrl: './profile.scss',
})
export class Profile {
  private readonly authService = inject(AuthService);
  private readonly formBuilder = inject(FormBuilder);
  private readonly router = inject(Router);
  private readonly sessionService = inject(SessionService);

  protected readonly user = this.sessionService.currentUser;
  protected readonly passwordPanelOpen = signal(false);
  protected readonly isSubmitting = signal(false);
  protected readonly serverMessage = signal<string | null>(null);
  protected readonly showCurrentPassword = signal(false);
  protected readonly showNewPassword = signal(false);
  protected readonly showConfirmation = signal(false);
  protected readonly passwordRequirements = PASSWORD_REQUIREMENTS;

  protected readonly passwordForm = this.formBuilder.nonNullable.group(
    {
      currentPassword: ['', Validators.required],
      newPassword: [
        '',
        [Validators.required, Validators.minLength(8), passwordStrengthValidator()],
      ],
      confirmPassword: ['', Validators.required],
    },
    { validators: matchingFieldsValidator('newPassword', 'confirmPassword') },
  );

  protected togglePasswordPanel(): void {
    if (this.isSubmitting()) {
      return;
    }

    this.passwordPanelOpen.update((isOpen) => !isOpen);
    this.serverMessage.set(null);

    if (!this.passwordPanelOpen()) {
      this.passwordForm.reset();
      this.resetPasswordVisibility();
    }
  }

  protected isInvalid(controlName: PasswordControlName): boolean {
    const control = this.passwordForm.controls[controlName];
    return control.invalid && (control.touched || control.dirty);
  }

  protected hasError(controlName: PasswordControlName, errorName: string): boolean {
    return this.passwordForm.controls[controlName].hasError(errorName);
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

  protected submitPasswordChange(): void {
    if (this.isSubmitting()) {
      return;
    }

    this.serverMessage.set(null);

    if (this.passwordForm.invalid) {
      this.passwordForm.markAllAsTouched();
      this.serverMessage.set('Revisa los datos ingresados.');
      return;
    }

    const value = this.passwordForm.getRawValue();
    const payload: ChangePasswordRequest = {
      current_password: value.currentPassword,
      new_password: value.newPassword,
      confirm_password: value.confirmPassword,
    };

    this.isSubmitting.set(true);
    this.authService
      .changePassword(payload)
      .pipe(finalize(() => this.isSubmitting.set(false)))
      .subscribe({
        next: () => this.completePasswordChange(),
        error: (error: HttpErrorResponse) => this.handlePasswordChangeError(error),
      });
  }

  private completePasswordChange(): void {
    this.passwordForm.reset();
    this.resetPasswordVisibility();
    this.sessionService.logout();
    void this.router.navigateByUrl('/login', {
      state: {
        successMessage: 'Contraseña actualizada. Inicia sesión nuevamente.',
      },
    });
  }

  private handlePasswordChangeError(error: HttpErrorResponse): void {
    if (error.status === 400) {
      const apiMessage = this.getApiMessage(error);
      this.serverMessage.set(
        apiMessage === 'La nueva contraseña debe ser diferente a la actual'
          ? 'La nueva contraseña debe ser diferente a la actual.'
          : 'La contraseña actual es incorrecta.',
      );
      return;
    }

    if (error.status === 422) {
      this.serverMessage.set('Revisa los datos ingresados.');
      return;
    }

    if (error.status === 401) {
      this.sessionService.logout();
      void this.router.navigateByUrl('/login');
      return;
    }

    this.serverMessage.set('No pudimos actualizar tu contraseña. Inténtalo nuevamente.');
  }

  private getApiMessage(error: HttpErrorResponse): string | null {
    const body: unknown = error.error;
    if (typeof body !== 'object' || body === null || !('message' in body)) {
      return null;
    }

    const message = body.message;
    return typeof message === 'string' ? message : null;
  }

  private resetPasswordVisibility(): void {
    this.showCurrentPassword.set(false);
    this.showNewPassword.set(false);
    this.showConfirmation.set(false);
  }
}
