import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../../core/storage/secure_token_storage.dart';
import '../../core/storage/token_storage.dart';
import 'login_models.dart';

abstract interface class AuthenticatedUserStorage {
  Future<void> saveUser(AuthenticatedUser user);

  Future<AuthenticatedUser?> getUser();

  Future<void> deleteUser();
}

class SecureAuthenticatedUserStorage implements AuthenticatedUserStorage {
  SecureAuthenticatedUserStorage({FlutterSecureStorage? storage})
    : _storage =
          storage ?? const FlutterSecureStorage(aOptions: AndroidOptions());

  static const _userKey = 'fashion_store_authenticated_user';

  final FlutterSecureStorage _storage;

  @override
  Future<void> saveUser(AuthenticatedUser user) =>
      _storage.write(key: _userKey, value: jsonEncode(user.toJson()));

  @override
  Future<AuthenticatedUser?> getUser() async {
    final value = await _storage.read(key: _userKey);
    if (value == null || value.trim().isEmpty) {
      return null;
    }

    try {
      final decoded = jsonDecode(value);
      return decoded is Map<String, dynamic>
          ? AuthenticatedUser.fromJson(decoded)
          : null;
    } on FormatException {
      return null;
    }
  }

  @override
  Future<void> deleteUser() => _storage.delete(key: _userKey);
}

class StoredSession {
  const StoredSession({required this.token, required this.user});

  final String token;
  final AuthenticatedUser user;
}

class SessionService {
  SessionService({
    TokenStorage? tokenStorage,
    AuthenticatedUserStorage? userStorage,
  }) : _tokenStorage = tokenStorage ?? SecureTokenStorage(),
       _userStorage = userStorage ?? SecureAuthenticatedUserStorage();

  final TokenStorage _tokenStorage;
  final AuthenticatedUserStorage _userStorage;

  Future<void> saveSession({
    required String token,
    required AuthenticatedUser user,
  }) async {
    await _tokenStorage.saveToken(token);
    try {
      await _userStorage.saveUser(user);
    } catch (_) {
      await _tokenStorage.deleteToken();
      rethrow;
    }
  }

  Future<StoredSession?> restoreSession() async {
    final token = await _tokenStorage.getToken();
    final user = await _userStorage.getUser();
    if (token == null || token.trim().isEmpty || user == null) {
      await logout();
      return null;
    }
    return StoredSession(token: token.trim(), user: user);
  }

  Future<void> logout() async {
    Object? firstError;
    StackTrace? firstStackTrace;
    try {
      await _tokenStorage.deleteToken();
    } catch (error, stackTrace) {
      firstError = error;
      firstStackTrace = stackTrace;
    }

    try {
      await _userStorage.deleteUser();
    } catch (error, stackTrace) {
      firstError ??= error;
      firstStackTrace ??= stackTrace;
    }

    if (firstError != null) {
      Error.throwWithStackTrace(firstError, firstStackTrace!);
    }
  }
}
