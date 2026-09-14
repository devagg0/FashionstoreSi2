import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/features/auth/password_recovery_validators.dart';

void main() {
  test('valida correo y código según el contrato', () {
    expect(PasswordRecoveryValidators.email('correo-invalido'), isNotNull);
    expect(PasswordRecoveryValidators.email('cliente@correo.com'), isNull);
    expect(PasswordRecoveryValidators.code('12AB56'), isNotNull);
    expect(PasswordRecoveryValidators.code('12345'), isNotNull);
    expect(PasswordRecoveryValidators.code('123456'), isNull);
  });

  test('aplica complejidad y coincidencia de contraseña del backend', () {
    expect(PasswordRecoveryValidators.password('debil'), isNotNull);
    expect(PasswordRecoveryValidators.password('Nueva@2026'), isNull);
    expect(
      PasswordRecoveryValidators.confirmation('Distinta@2026', 'Nueva@2026'),
      'Las contraseñas no coinciden.',
    );
    expect(
      PasswordRecoveryValidators.confirmation('Nueva@2026', 'Nueva@2026'),
      isNull,
    );
  });
}
