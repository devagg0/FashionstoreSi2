import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mobile/core/services/api_service.dart';
import 'package:mobile/core/storage/token_storage.dart';
import 'package:mobile/features/auth/login_models.dart';
import 'package:mobile/features/auth/login_service.dart';
import 'package:mobile/features/auth/session_service.dart';

void main() {
  const loginRequest = LoginRequest(
    email: 'cliente@correo.com',
    password: 'cualquier-clave',
  );

  test('envía el request real y guarda token y usuario del CLIENTE', () async {
    final tokenStorage = _MemoryTokenStorage('token-anterior');
    final userStorage = _MemoryUserStorage();
    final client = MockClient((request) async {
      expect(request.method, 'POST');
      expect(request.url.path, '/api/auth/login');
      expect(request.headers['authorization'], isNull);
      expect(jsonDecode(request.body), {
        'correo': 'cliente@correo.com',
        'password': 'cualquier-clave',
      });
      return _successResponse();
    });
    final service = _service(
      client,
      tokenStorage: tokenStorage,
      userStorage: userStorage,
    );

    final user = await service.login(loginRequest);

    expect(user.userId, 42);
    expect(user.fullName, 'Ana Pérez');
    expect(user.role, 'CLIENTE');
    expect(tokenStorage.token, 'jwt-real');
    expect(userStorage.user?.email, 'cliente@correo.com');
  });

  test('convierte 401 en credenciales inválidas y no guarda sesión', () async {
    final tokenStorage = _MemoryTokenStorage();
    final service = _service(
      MockClient(
        (_) async => http.Response(
          jsonEncode({
            'success': false,
            'message': 'Correo o contraseña incorrectos',
          }),
          401,
        ),
      ),
      tokenStorage: tokenStorage,
    );

    await expectLater(
      service.login(loginRequest),
      throwsA(
        isA<LoginFailure>().having(
          (error) => error.type,
          'type',
          LoginFailureType.invalidCredentials,
        ),
      ),
    );
    expect(tokenStorage.saveCalls, 0);
  });

  test(
    'diferencia cuenta inactiva, datos inválidos y error servidor',
    () async {
      for (final scenario in [
        (403, LoginFailureType.inactiveAccount),
        (422, LoginFailureType.invalidData),
        (500, LoginFailureType.server),
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
          service.login(loginRequest),
          throwsA(
            isA<LoginFailure>().having(
              (error) => error.type,
              'type',
              scenario.$2,
            ),
          ),
        );
      }
    },
  );

  test('diferencia error de conexión y timeout', () async {
    final disconnected = _service(
      MockClient((_) async => throw http.ClientException('sin red')),
    );
    final timeout = _service(
      MockClient((_) async {
        await Future<void>.delayed(const Duration(milliseconds: 30));
        return _successResponse();
      }),
      timeout: const Duration(milliseconds: 1),
    );

    await expectLater(
      disconnected.login(loginRequest),
      throwsA(
        isA<LoginFailure>().having(
          (error) => error.type,
          'type',
          LoginFailureType.connection,
        ),
      ),
    );
    await expectLater(
      timeout.login(loginRequest),
      throwsA(
        isA<LoginFailure>().having(
          (error) => error.type,
          'type',
          LoginFailureType.timeout,
        ),
      ),
    );
  });

  for (final role in const ['ADMINISTRADOR', 'CAJERO', 'ENCARGADO']) {
    test('rechaza rol $role antes de guardar el token', () async {
      final tokenStorage = _MemoryTokenStorage();
      final userStorage = _MemoryUserStorage();
      final service = _service(
        MockClient((_) async => _successResponse(role: role)),
        tokenStorage: tokenStorage,
        userStorage: userStorage,
      );

      await expectLater(
        service.login(loginRequest),
        throwsA(
          isA<LoginFailure>().having(
            (error) => error.type,
            'type',
            LoginFailureType.unsupportedRole,
          ),
        ),
      );
      expect(tokenStorage.saveCalls, 0);
      expect(userStorage.user, isNull);
    });
  }
}

LoginService _service(
  http.Client client, {
  _MemoryTokenStorage? tokenStorage,
  _MemoryUserStorage? userStorage,
  Duration timeout = const Duration(seconds: 20),
}) {
  final tokens = tokenStorage ?? _MemoryTokenStorage();
  final users = userStorage ?? _MemoryUserStorage();
  return LoginService(
    apiService: ApiService(
      client: client,
      tokenStorage: tokens,
      timeout: timeout,
    ),
    sessionService: SessionService(tokenStorage: tokens, userStorage: users),
  );
}

http.Response _successResponse({String role = 'CLIENTE'}) => http.Response(
  jsonEncode({
    'success': true,
    'message': 'Inicio de sesión exitoso',
    'access_token': 'jwt-real',
    'token_type': 'bearer',
    'expires_in': 3600,
    'usuario': {
      'id_usuario': 42,
      'nombre': 'Ana',
      'apellido': 'Pérez',
      'correo': 'cliente@correo.com',
      'rol': role,
    },
  }),
  200,
);

class _MemoryTokenStorage implements TokenStorage {
  _MemoryTokenStorage([this.token]);

  String? token;
  int saveCalls = 0;
  int deleteCalls = 0;

  @override
  Future<void> deleteToken() async {
    deleteCalls++;
    token = null;
  }

  @override
  Future<String?> getToken() async => token;

  @override
  Future<void> saveToken(String token) async {
    saveCalls++;
    this.token = token;
  }
}

class _MemoryUserStorage implements AuthenticatedUserStorage {
  AuthenticatedUser? user;
  int deleteCalls = 0;

  @override
  Future<void> deleteUser() async {
    deleteCalls++;
    user = null;
  }

  @override
  Future<AuthenticatedUser?> getUser() async => user;

  @override
  Future<void> saveUser(AuthenticatedUser user) async => this.user = user;
}
