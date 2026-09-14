import 'login_validators.dart';
import 'registration_validators.dart';

abstract final class PasswordRecoveryValidators {
  static final RegExp _sixDigits = RegExp(r'^\d{6}$');

  static String? email(String? value) => LoginValidators.email(value);

  static String? code(String? value) {
    final code = value?.trim() ?? '';
    if (code.isEmpty) {
      return 'El código es obligatorio.';
    }
    if (!_sixDigits.hasMatch(code)) {
      return 'Ingresa el código numérico de 6 dígitos.';
    }
    return null;
  }

  static String? password(String? value) =>
      RegistrationValidators.password(value);

  static String? confirmation(String? value, String password) =>
      RegistrationValidators.confirmation(value, password);
}
