import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mobile/core/services/api_service.dart';
import 'package:mobile/core/storage/token_storage.dart';
import 'package:mobile/features/auth/registration_models.dart';
import 'package:mobile/features/auth/registration_service.dart';

void main() {
  const request = ClientRegistrationRequest(
    firstName: 'Ana',
    lastName: 'Pérez',
    email: 'ana@correo.com',
    phone: '70012345',
    password: 'Fashion@2026',
    confirmPassword: 'Fashion@2026',
  );

  test(
    'envía POST exacto, sin rol ni Authorization, y procesa el 201',
    () async {
      final client = MockClient((httpRequest) async {
        expect(httpRequest.method, 'POST');
        expect(httpRequest.url.path, '/api/auth/register');
        expect(httpRequest.headers['authorization'], isNull);
        final body = jsonDecode(httpRequest.body) as Map<String, dynamic>;
        expect(body, {
          'nombre': 'Ana',
          'apellido': 'Pérez',
          'correo': 'ana@correo.com',
          'telefono': '70012345',
          'password': 'Fashion@2026',
          'confirm_password': 'Fashion@2026',
        });
        expect(body.containsKey('rol'), isFalse);
        return http.Response(
          jsonEncode({
            'success': true,
            'message': 'Cliente registrado correctamente',
            'data': {
              'id_usuario': 42,
              'nombre': 'Ana',
              'apellido': 'Pérez',
              'correo': 'ana@correo.com',
            },
          }),
          201,
        );
      });
      final service = _service(client, token: 'token-que-no-debe-enviarse');

      final result = await service.register(request);

      expect(result.message, 'Cliente registrado correctamente');
      expect(result.client.userId, 42);
      expect(result.client.email, 'ana@correo.com');
    },
  );

  test('convierte correo duplicado 409 en fallo específico', () async {
    final service = _service(
      MockClient(
        (_) async => http.Response(
          jsonEncode({
            'success': false,
            'message': 'El correo ya se encuentra registrado',
          }),
          409,
        ),
      ),
    );

    expect(
      () => service.register(request),
      throwsA(
        isA<RegistrationFailure>().having(
          (error) => error.type,
          'type',
          RegistrationFailureType.duplicateEmail,
        ),
      ),
    );
  });

  test('convierte datos rechazados 422 y errores 500', () async {
    for (final scenario in [
      (422, RegistrationFailureType.invalidData),
      (500, RegistrationFailureType.server),
    ]) {
      final service = _service(
        MockClient(
          (_) async => http.Response(
            jsonEncode({'success': false, 'message': 'Error'}),
            scenario.$1,
          ),
        ),
      );

      await expectLater(
        service.register(request),
        throwsA(
          isA<RegistrationFailure>().having(
            (error) => error.type,
            'type',
            scenario.$2,
          ),
        ),
      );
    }
  });

  test('diferencia error de conexión y timeout', () async {
    final disconnectedService = _service(
      MockClient((_) async => throw http.ClientException('sin red')),
    );
    final timeoutService = RegistrationService(
      apiService: ApiService(
        client: MockClient((_) async {
          await Future<void>.delayed(const Duration(milliseconds: 30));
          return http.Response('{}', 200);
        }),
        tokenStorage: _TestTokenStorage(),
        timeout: const Duration(milliseconds: 1),
      ),
    );

    await expectLater(
      disconnectedService.register(request),
      throwsA(
        isA<RegistrationFailure>().having(
          (error) => error.type,
          'type',
          RegistrationFailureType.connection,
        ),
      ),
    );
    await expectLater(
      timeoutService.register(request),
      throwsA(
        isA<RegistrationFailure>().having(
          (error) => error.type,
          'type',
          RegistrationFailureType.timeout,
        ),
      ),
    );
  });
}

RegistrationService _service(http.Client client, {String? token}) =>
    RegistrationService(
      apiService: ApiService(
        client: client,
        tokenStorage: _TestTokenStorage(token),
      ),
    );

class _TestTokenStorage implements TokenStorage {
  _TestTokenStorage([this.token]);

  String? token;

  @override
  Future<void> deleteToken() async => token = null;

  @override
  Future<String?> getToken() async => token;

  @override
  Future<void> saveToken(String token) async => this.token = token;
}
