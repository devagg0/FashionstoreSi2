import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mobile/core/services/api_service.dart';
import 'package:mobile/core/storage/token_storage.dart';
import 'package:mobile/features/profile/change_password_models.dart';
import 'package:mobile/features/profile/change_password_service.dart';

void main() {
  const request = ChangePasswordRequest(
    currentPassword: 'Actual@2026',
    newPassword: 'Nueva@2026',
    confirmPassword: 'Nueva@2026',
  );

  test(
    'envía PUT exacto con Bearer y conserva el token al tener éxito',
    () async {
      final tokens = _MemoryTokenStorage('jwt-seguro');
      final service = _service(
        MockClient((httpRequest) async {
          expect(httpRequest.method, 'PUT');
          expect(httpRequest.url.path, '/api/auth/change-password');
          expect(httpRequest.headers['authorization'], 'Bearer jwt-seguro');
          final body = jsonDecode(httpRequest.body) as Map<String, dynamic>;
          expect(body, {
            'current_password': 'Actual@2026',
            'new_password': 'Nueva@2026',
            'confirm_password': 'Nueva@2026',
          });
          expect(body.containsKey('id_usuario'), isFalse);
          return _response({
            'success': true,
            'message': 'Contraseña actualizada correctamente',
          });
        }),
        tokens: tokens,
      );

      final message = await service.changePassword(request);

      expect(message, 'Contraseña actualizada correctamente');
      expect(tokens.token, 'jwt-seguro');
      expect(tokens.deleteCalls, 0);
    },
  );

  test('mapea contraseña actual incorrecta y contraseña reutilizada', () async {
    for (final scenario in [
      (
        'La contraseña actual es incorrecta',
        ChangePasswordFailureType.incorrectCurrentPassword,
      ),
      (
        'La nueva contraseña debe ser diferente a la actual',
        ChangePasswordFailureType.reusedPassword,
      ),
    ]) {
      final service = _service(
        MockClient(
          (_) async => _response({
            'success': false,
            'message': scenario.$1,
          }, statusCode: 400),
        ),
      );

      await expectLater(
        service.changePassword(request),
        throwsA(
          isA<ChangePasswordFailure>().having(
            (error) => error.type,
            'type',
            scenario.$2,
          ),
        ),
      );
    }
  });

  test(
    'requiere token y diferencia sesión expirada de cuenta inactiva',
    () async {
      final withoutToken = _service(
        MockClient((httpRequest) async {
          expect(httpRequest.headers['authorization'], isNull);
          return _response({
            'success': false,
            'message': 'Token inválido o expirado',
          }, statusCode: 401);
        }),
      );
      final inactive = _service(
        MockClient(
          (_) async => _response({
            'success': false,
            'message': 'La cuenta se encuentra inactiva',
          }, statusCode: 403),
        ),
      );

      await expectLater(
        withoutToken.changePassword(request),
        throwsA(
          isA<ChangePasswordFailure>()
              .having(
                (error) => error.type,
                'type',
                ChangePasswordFailureType.unauthorized,
              )
              .having(
                (error) => error.invalidatesSession,
                'invalidatesSession',
                isTrue,
              ),
        ),
      );
      await expectLater(
        inactive.changePassword(request),
        throwsA(
          isA<ChangePasswordFailure>().having(
            (error) => error.type,
            'type',
            ChangePasswordFailureType.inactiveAccount,
          ),
        ),
      );
    },
  );

  test('mapea 422, conexión y timeout', () async {
    final invalidData = _service(
      MockClient(
        (_) async => _response({'detail': 'validation'}, statusCode: 422),
      ),
    );
    final disconnected = _service(
      MockClient((_) async => throw http.ClientException('sin conexión')),
    );
    final timeout = _service(
      MockClient((_) async {
        await Future<void>.delayed(const Duration(milliseconds: 30));
        return _response({'success': true, 'message': 'ok'});
      }),
      timeout: const Duration(milliseconds: 1),
    );

    for (final scenario in [
      (invalidData, ChangePasswordFailureType.invalidData),
      (disconnected, ChangePasswordFailureType.connection),
      (timeout, ChangePasswordFailureType.timeout),
    ]) {
      await expectLater(
        scenario.$1.changePassword(request),
        throwsA(
          isA<ChangePasswordFailure>().having(
            (error) => error.type,
            'type',
            scenario.$2,
          ),
        ),
      );
    }
  });
}

ChangePasswordService _service(
  http.Client client, {
  _MemoryTokenStorage? tokens,
  Duration timeout = const Duration(seconds: 20),
}) => ChangePasswordService(
  apiService: ApiService(
    client: client,
    tokenStorage: tokens ?? _MemoryTokenStorage(),
    timeout: timeout,
  ),
);

http.Response _response(Map<String, dynamic> body, {int statusCode = 200}) =>
    http.Response(jsonEncode(body), statusCode);

class _MemoryTokenStorage implements TokenStorage {
  _MemoryTokenStorage([this.token]);

  String? token;
  int deleteCalls = 0;

  @override
  Future<void> deleteToken() async {
    deleteCalls++;
    token = null;
  }

  @override
  Future<String?> getToken() async => token;

  @override
  Future<void> saveToken(String token) async => this.token = token;
}
