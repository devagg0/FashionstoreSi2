import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/storage/token_storage.dart';
import 'package:mobile/features/auth/login_models.dart';
import 'package:mobile/features/auth/session_service.dart';

void main() {
  test('logout elimina tanto el JWT como los datos del usuario', () async {
    final tokens = _TokenStorage('jwt');
    final users = _UserStorage(_user);
    final service = SessionService(tokenStorage: tokens, userStorage: users);

    await service.logout();

    expect(tokens.token, isNull);
    expect(users.user, isNull);
    expect(tokens.deleteCalls, 1);
    expect(users.deleteCalls, 1);
  });

  test('restaura una sesión completa y limpia una sesión incompleta', () async {
    final tokens = _TokenStorage('jwt');
    final users = _UserStorage(_user);
    final service = SessionService(tokenStorage: tokens, userStorage: users);

    final restored = await service.restoreSession();
    expect(restored?.token, 'jwt');
    expect(restored?.user.firstName, 'Ana');

    users.user = null;
    expect(await service.restoreSession(), isNull);
    expect(tokens.token, isNull);
  });
}

const _user = AuthenticatedUser(
  userId: 42,
  firstName: 'Ana',
  lastName: 'Pérez',
  email: 'cliente@correo.com',
  role: 'CLIENTE',
);

class _TokenStorage implements TokenStorage {
  _TokenStorage(this.token);

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

class _UserStorage implements AuthenticatedUserStorage {
  _UserStorage(this.user);

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
