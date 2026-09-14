import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mobile/core/services/api_service.dart';
import 'package:mobile/core/storage/token_storage.dart';
import 'package:mobile/features/profile/profile_service.dart';

void main() {
  test('carga el perfil real con GET y Authorization Bearer', () async {
    final service = _service(
      MockClient((request) async {
        expect(request.method, 'GET');
        expect(request.url.path, '/api/auth/me');
        expect(request.headers['authorization'], 'Bearer jwt-seguro');
        return _profileResponse();
      }),
      token: 'jwt-seguro',
    );

    final user = await service.loadProfile();

    expect(user.userId, 42);
    expect(user.firstName, 'Ana');
    expect(user.lastName, 'Pérez');
    expect(user.email, 'cliente@correo.com');
    expect(user.role, 'CLIENTE');
  });

  test(
    'sin token, el backend responde 401 y la sesión queda inválida',
    () async {
      final service = _service(
        MockClient((request) async {
          expect(request.headers['authorization'], isNull);
          return _errorResponse(401, 'Token inválido o expirado');
        }),
      );

      await expectLater(
        service.loadProfile(),
        throwsA(
          isA<ProfileFailure>()
              .having(
                (error) => error.type,
                'type',
                ProfileFailureType.unauthorized,
              )
              .having(
                (error) => error.invalidatesSession,
                'invalidatesSession',
                isTrue,
              ),
        ),
      );
    },
  );

  test('mapea token inválido, cuenta inactiva y rol no cliente', () async {
    for (final scenario in [
      (401, 'Token inválido o expirado', ProfileFailureType.unauthorized),
      (
        403,
        'La cuenta se encuentra inactiva',
        ProfileFailureType.inactiveAccount,
      ),
    ]) {
      final service = _service(
        MockClient((_) async => _errorResponse(scenario.$1, scenario.$2)),
        token: 'jwt',
      );
      await expectLater(
        service.loadProfile(),
        throwsA(
          isA<ProfileFailure>().having(
            (error) => error.type,
            'type',
            scenario.$3,
          ),
        ),
      );
    }

    final employee = _service(
      MockClient((_) async => _profileResponse(role: 'CAJERO')),
      token: 'jwt',
    );
    await expectLater(
      employee.loadProfile(),
      throwsA(
        isA<ProfileFailure>().having(
          (error) => error.type,
          'type',
          ProfileFailureType.unsupportedRole,
        ),
      ),
    );
  });

  test('mapea conexión, timeout y error servidor', () async {
    final disconnected = _service(
      MockClient((_) async => throw http.ClientException('sin conexión')),
      token: 'jwt',
    );
    final timeout = _service(
      MockClient((_) async {
        await Future<void>.delayed(const Duration(milliseconds: 30));
        return _profileResponse();
      }),
      token: 'jwt',
      timeout: const Duration(milliseconds: 1),
    );
    final server = _service(
      MockClient((_) async => _errorResponse(500, 'Error')),
      token: 'jwt',
    );

    for (final scenario in [
      (disconnected, ProfileFailureType.connection),
      (timeout, ProfileFailureType.timeout),
      (server, ProfileFailureType.server),
    ]) {
      await expectLater(
        scenario.$1.loadProfile(),
        throwsA(
          isA<ProfileFailure>().having(
            (error) => error.type,
            'type',
            scenario.$2,
          ),
        ),
      );
    }
  });
}

ProfileService _service(
  http.Client client, {
  String? token,
  Duration timeout = const Duration(seconds: 20),
}) => ProfileService(
  apiService: ApiService(
    client: client,
    tokenStorage: _TokenStorage(token),
    timeout: timeout,
  ),
);

http.Response _profileResponse({String role = 'CLIENTE'}) => http.Response(
  jsonEncode({
    'success': true,
    'data': {
      'id_usuario': 42,
      'nombre': 'Ana',
      'apellido': 'Pérez',
      'correo': 'cliente@correo.com',
      'rol': role,
    },
  }),
  200,
);

http.Response _errorResponse(int status, String message) =>
    http.Response(jsonEncode({'success': false, 'message': message}), status);

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
