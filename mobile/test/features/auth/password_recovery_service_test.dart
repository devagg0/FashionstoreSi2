import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mobile/core/services/api_service.dart';
import 'package:mobile/core/storage/token_storage.dart';
import 'package:mobile/features/auth/password_recovery_models.dart';
import 'package:mobile/features/auth/password_recovery_service.dart';

void main() {
  test('ejecuta los tres requests reales sin enviar Authorization', () async {
    final requestedPaths = <String>[];
    final client = MockClient((request) async {
      requestedPaths.add(request.url.path);
      expect(request.method, 'POST');
      expect(request.headers['authorization'], isNull);
      final body = jsonDecode(request.body) as Map<String, dynamic>;

      switch (request.url.path) {
        case PasswordRecoveryService.requestEndpoint:
          expect(body, {'correo': 'cliente@correo.com'});
          return _jsonResponse({
            'success': true,
            'message': 'Si el correo está registrado, recibirás un código de recuperación',
          });
        case PasswordRecoveryService.verifyEndpoint:
          expect(body, {'correo': 'cliente@correo.com', 'codigo': '123456'});
          return _jsonResponse({
            'success': true,
            'message': 'Código verificado correctamente',
            'reset_token': 'reset.jwt',
          });
        case PasswordRecoveryService.resetEndpoint:
          expect(body, {
            'reset_token': 'reset.jwt',
            'new_password': 'Nueva@2026',
            'confirm_password': 'Nueva@2026',
          });
          return _jsonResponse({
            'success': true,
            'message': 'Contraseña restablecida correctamente',
          });
      }
      return http.Response('{}', 404);
    });
    final service = _service(client, storedToken: 'jwt-que-no-debe-enviarse');

    final requestMessage = await service.requestRecovery(
      const PasswordRecoveryRequest(email: 'cliente@correo.com'),
    );
    final verification = await service.verifyCode(
      const PasswordRecoveryVerificationRequest(
        email: 'cliente@correo.com',
        code: '123456',
      ),
    );
    final resetMessage = await service.resetPassword(
      PasswordResetRequest(
        resetToken: verification.resetToken,
        newPassword: 'Nueva@2026',
        confirmPassword: 'Nueva@2026',
      ),
    );

    expect(requestMessage, startsWith('Si el correo'));
    expect(verification.resetToken, 'reset.jwt');
    expect(resetMessage, 'Contraseña restablecida correctamente');
    expect(requestedPaths, [
      PasswordRecoveryService.requestEndpoint,
      PasswordRecoveryService.verifyEndpoint,
      PasswordRecoveryService.resetEndpoint,
    ]);
  });

  test(
    'mantiene indistinguible la respuesta para un correo desconocido',
    () async {
      final service = _service(
        MockClient(
          (_) async => _jsonResponse({
            'success': true,
            'message': 'Si el correo está registrado, recibirás un código de recuperación',
          }),
        ),
      );

      final message = await service.requestRecovery(
        const PasswordRecoveryRequest(email: 'desconocido@correo.com'),
      );

      expect(message, startsWith('Si el correo está registrado'));
    },
  );

  test('distingue código y reset token inválidos', () async {
    final client = MockClient(
      (_) async => _jsonResponse({
        'success': false,
        'message': 'Inválido',
      }, statusCode: 400),
    );
    final service = _service(client);

    await expectLater(
      service.verifyCode(
        const PasswordRecoveryVerificationRequest(
          email: 'cliente@correo.com',
          code: '000000',
        ),
      ),
      throwsA(
        isA<PasswordRecoveryFailure>().having(
          (error) => error.type,
          'type',
          PasswordRecoveryFailureType.invalidCode,
        ),
      ),
    );
    await expectLater(
      service.resetPassword(
        const PasswordResetRequest(
          resetToken: 'expirado',
          newPassword: 'Nueva@2026',
          confirmPassword: 'Nueva@2026',
        ),
      ),
      throwsA(
        isA<PasswordRecoveryFailure>().having(
          (error) => error.type,
          'type',
          PasswordRecoveryFailureType.invalidResetToken,
        ),
      ),
    );
  });

  test('mapea 422, error servidor, conexión y timeout', () async {
    for (final scenario in [
      (422, PasswordRecoveryFailureType.invalidData),
      (500, PasswordRecoveryFailureType.server),
    ]) {
      final service = _service(
        MockClient(
          (_) async => _jsonResponse({
            'success': false,
            'message': 'Error',
          }, statusCode: scenario.$1),
        ),
      );
      await expectLater(
        service.requestRecovery(
          const PasswordRecoveryRequest(email: 'cliente@correo.com'),
        ),
        throwsA(
          isA<PasswordRecoveryFailure>().having(
            (error) => error.type,
            'type',
            scenario.$2,
          ),
        ),
      );
    }

    final disconnected = _service(
      MockClient((_) async => throw http.ClientException('sin conexión')),
    );
    final timeout = _service(
      MockClient((_) async {
        await Future<void>.delayed(const Duration(milliseconds: 30));
        return _jsonResponse({'success': true, 'message': 'ok'});
      }),
      timeout: const Duration(milliseconds: 1),
    );

    await expectLater(
      disconnected.requestRecovery(
        const PasswordRecoveryRequest(email: 'cliente@correo.com'),
      ),
      throwsA(
        isA<PasswordRecoveryFailure>().having(
          (error) => error.type,
          'type',
          PasswordRecoveryFailureType.connection,
        ),
      ),
    );
    await expectLater(
      timeout.requestRecovery(
        const PasswordRecoveryRequest(email: 'cliente@correo.com'),
      ),
      throwsA(
        isA<PasswordRecoveryFailure>().having(
          (error) => error.type,
          'type',
          PasswordRecoveryFailureType.timeout,
        ),
      ),
    );
  });
}

PasswordRecoveryService _service(
  http.Client client, {
  String? storedToken,
  Duration timeout = const Duration(seconds: 20),
}) => PasswordRecoveryService(
  apiService: ApiService(
    client: client,
    tokenStorage: _TokenStorage(storedToken),
    timeout: timeout,
  ),
);

http.Response _jsonResponse(
  Map<String, dynamic> body, {
  int statusCode = 200,
}) => http.Response(jsonEncode(body), statusCode);

class _TokenStorage implements TokenStorage {
  _TokenStorage(this.token);

  String? token;

  @override
  Future<void> deleteToken() async => token = null;

  @override
  Future<String?> getToken() async => token;

  @override
  Future<void> saveToken(String token) async => this.token = token;
}
