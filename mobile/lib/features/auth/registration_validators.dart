abstract final class RegistrationValidators {
  static final RegExp _emailPattern = RegExp(r'^[^\s@]+@[^\s@]+\.[^\s@]+$');
  static final RegExp _phonePattern = RegExp(r'^[0-9+().\-\s]+$');
  static final RegExp _upperCasePattern = RegExp(r'[A-ZÁÉÍÓÚÜÑ]');
  static final RegExp _lowerCasePattern = RegExp(r'[a-záéíóúüñ]');
  static final RegExp _digitPattern = RegExp(r'\d');
  static final RegExp _specialPattern = RegExp(r'[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9\s]');

  static String? requiredName(String? value, {required String label}) {
    final normalized = value?.trim() ?? '';
    if (normalized.isEmpty) {
      return '$label es obligatorio.';
    }
    if (normalized.runes.length < 2) {
      return '$label debe tener al menos 2 caracteres.';
    }
    if (normalized.runes.length > 100) {
      return '$label no puede superar 100 caracteres.';
    }
    return null;
  }

  static String? email(String? value) {
    final normalized = value?.trim() ?? '';
    if (normalized.isEmpty) {
      return 'El correo electrónico es obligatorio.';
    }
    if (!_emailPattern.hasMatch(normalized)) {
      return 'Ingresa un correo electrónico válido.';
    }
    return null;
  }

  static String? phone(String? value) {
    final normalized = value?.trim() ?? '';
    if (normalized.isEmpty) {
      return null;
    }
    if (normalized.runes.length < 5 ||
        normalized.runes.length > 30 ||
        !_phonePattern.hasMatch(normalized) ||
        !_digitPattern.hasMatch(normalized)) {
      return 'Ingresa un número de teléfono válido.';
    }
    return null;
  }

  static String? password(String? value) {
    final password = value ?? '';
    if (password.isEmpty) {
      return 'La contraseña es obligatoria.';
    }
    if (password.runes.length < 8) {
      return 'La contraseña debe tener al menos 8 caracteres.';
    }
    if (password.runes.length > 128) {
      return 'La contraseña no puede superar 128 caracteres.';
    }
    if (!meetsAllPasswordRequirements(password)) {
      return 'La contraseña no cumple todos los requisitos.';
    }
    return null;
  }

  static String? confirmation(String? value, String password) {
    final confirmation = value ?? '';
    if (confirmation.isEmpty) {
      return 'Confirma tu contraseña.';
    }
    if (confirmation.runes.length < 8 || confirmation.runes.length > 128) {
      return 'La confirmación debe tener entre 8 y 128 caracteres.';
    }
    if (confirmation != password) {
      return 'Las contraseñas no coinciden.';
    }
    return null;
  }

  static bool hasMinimumLength(String value) => value.runes.length >= 8;
  static bool hasUpperCase(String value) => _upperCasePattern.hasMatch(value);
  static bool hasLowerCase(String value) => _lowerCasePattern.hasMatch(value);
  static bool hasDigit(String value) => _digitPattern.hasMatch(value);
  static bool hasSpecialCharacter(String value) =>
      _specialPattern.hasMatch(value);

  static bool meetsAllPasswordRequirements(String value) =>
      hasMinimumLength(value) &&
      hasUpperCase(value) &&
      hasLowerCase(value) &&
      hasDigit(value) &&
      hasSpecialCharacter(value);
}
