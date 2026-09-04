import { AbstractControl, ValidationErrors, ValidatorFn } from '@angular/forms';

export interface PasswordRequirement {
  label: string;
  test: (value: string) => boolean;
}

export const PASSWORD_REQUIREMENTS: readonly PasswordRequirement[] = [
  { label: 'Al menos 8 caracteres', test: (value) => value.length >= 8 },
  { label: 'Una letra mayúscula', test: (value) => /[A-ZÁÉÍÓÚÜÑ]/.test(value) },
  { label: 'Una letra minúscula', test: (value) => /[a-záéíóúüñ]/.test(value) },
  { label: 'Un número', test: (value) => /\d/.test(value) },
  {
    label: 'Un carácter especial',
    test: (value) => /[^\p{L}\p{N}\s]/u.test(value),
  },
];

export function trimmedLengthValidator(min: number, max: number): ValidatorFn {
  return (control: AbstractControl<string>): ValidationErrors | null => {
    const value = control.value.trim();

    if (!value) {
      return { required: true };
    }

    if (value.length < min) {
      return { minlength: { requiredLength: min, actualLength: value.length } };
    }

    if (value.length > max) {
      return { maxlength: { requiredLength: max, actualLength: value.length } };
    }

    return null;
  };
}

export function passwordStrengthValidator(): ValidatorFn {
  return (control: AbstractControl<string>): ValidationErrors | null => {
    const value = control.value;

    if (!value) {
      return null;
    }

    return PASSWORD_REQUIREMENTS.every((requirement) => requirement.test(value))
      ? null
      : { passwordStrength: true };
  };
}

export function optionalPhoneValidator(): ValidatorFn {
  return (control: AbstractControl<string>): ValidationErrors | null => {
    const value = control.value.trim();

    if (!value) {
      return null;
    }

    const hasReasonableLength = value.length >= 5 && value.length <= 30;
    const hasValidCharacters = /^[0-9+().\-\s]+$/.test(value) && /\d/.test(value);
    return hasReasonableLength && hasValidCharacters ? null : { invalidPhone: true };
  };
}

export function matchingFieldsValidator(
  fieldName: string,
  confirmationFieldName: string,
): ValidatorFn {
  return (group: AbstractControl): ValidationErrors | null => {
    const value = group.get(fieldName)?.value as string | undefined;
    const confirmation = group.get(confirmationFieldName)?.value as string | undefined;

    if (!value || !confirmation) {
      return null;
    }

    return value === confirmation ? null : { passwordMismatch: true };
  };
}
