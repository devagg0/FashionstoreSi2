import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/features/profile/change_password_validators.dart';

void main() {
  test('valida contraseña actual según el contrato', () {
    expect(ChangePasswordValidators.currentPassword(''), isNotNull);
    expect(ChangePasswordValidators.currentPassword('x' * 129), isNotNull);
    expect(ChangePasswordValidators.currentPassword('Actual@2026'), isNull);
  });

  test('valida complejidad, no reutilización y confirmación', () {
    expect(
      ChangePasswordValidators.newPassword('debil', 'Actual@2026'),
      isNotNull,
    );
    expect(
      ChangePasswordValidators.newPassword('Actual@2026', 'Actual@2026'),
      'La nueva contraseña debe ser diferente a la actual.',
    );
    expect(
      ChangePasswordValidators.newPassword('Nueva@2026', 'Actual@2026'),
      isNull,
    );
    expect(
      ChangePasswordValidators.confirmation('Otra@2026', 'Nueva@2026'),
      'Las contraseñas no coinciden.',
    );
  });
}
