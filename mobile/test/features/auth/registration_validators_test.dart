import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/features/auth/registration_validators.dart';

void main() {
  group('RegistrationValidators', () {
    test('valida nombres usando el valor recortado y límites del backend', () {
      expect(
        RegistrationValidators.requiredName('  Ana  ', label: 'El nombre'),
        isNull,
      );
      expect(
        RegistrationValidators.requiredName(' ', label: 'El nombre'),
        'El nombre es obligatorio.',
      );
      expect(
        RegistrationValidators.requiredName('A', label: 'El nombre'),
        contains('al menos 2'),
      );
      expect(
        RegistrationValidators.requiredName(
          List.filled(101, 'a').join(),
          label: 'El nombre',
        ),
        contains('100'),
      );
    });

    test('valida correo y teléfono opcional con las reglas del backend', () {
      expect(RegistrationValidators.email('cliente@correo.com'), isNull);
      expect(RegistrationValidators.email('correo-invalido'), isNotNull);
      expect(RegistrationValidators.phone(''), isNull);
      expect(RegistrationValidators.phone('+591 700-12345'), isNull);
      expect(RegistrationValidators.phone('abc123'), isNotNull);
      expect(RegistrationValidators.phone('1234'), isNotNull);
    });

    test('exige longitud y complejidad de contraseña', () {
      expect(RegistrationValidators.password('Fashion@2026'), isNull);
      expect(RegistrationValidators.password('fashion@2026'), isNotNull);
      expect(RegistrationValidators.password('FASHION@2026'), isNotNull);
      expect(RegistrationValidators.password('FashionFashion@'), isNotNull);
      expect(RegistrationValidators.password('Fashion2026'), isNotNull);
    });

    test('confirmación debe existir y coincidir exactamente', () {
      expect(
        RegistrationValidators.confirmation('Fashion@2026', 'Fashion@2026'),
        isNull,
      );
      expect(
        RegistrationValidators.confirmation('Fashion@2025', 'Fashion@2026'),
        'Las contraseñas no coinciden.',
      );
    });
  });
}
