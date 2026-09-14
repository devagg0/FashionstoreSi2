import '../auth/registration_validators.dart';

abstract final class ChangePasswordValidators {
  static String? currentPassword(String? value) {
    final password = value ?? '';
    if (password.isEmpty) {
      return 'La contraseña actual es obligatoria.';
    }
    if (password.runes.length > 128) {
      return 'La contraseña actual no puede superar 128 caracteres.';
    }
    return null;
  }

  static String? newPassword(String? value, String currentPassword) {
    final validation = RegistrationValidators.password(value);
    if (validation != null) {
      return validation;
    }
    if (value == currentPassword) {
      return 'La nueva contraseña debe ser diferente a la actual.';
    }
    return null;
  }

  static String? confirmation(String? value, String newPassword) =>
      RegistrationValidators.confirmation(value, newPassword);
}
