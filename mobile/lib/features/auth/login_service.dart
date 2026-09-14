import '../../core/errors/api_exception.dart';
import '../../core/services/api_service.dart';
import 'login_models.dart';
import 'session_service.dart';

abstract interface class ClientLoginGateway {
  Future<AuthenticatedUser> login(LoginRequest request);
}

enum LoginFailureType {
  invalidCredentials,
  inactiveAccount,
  invalidData,
  unsupportedRole,
  timeout,
  connection,
  server,
  invalidResponse,
  storage,
}

class LoginFailure implements Exception {
  const LoginFailure(this.type, this.message);

  final LoginFailureType type;
  final String message;

  @override
  String toString() => 'LoginFailure($type): $message';
}

class LoginService implements ClientLoginGateway {
  LoginService({ApiService? apiService, SessionService? sessionService})
    : _apiService = apiService ?? ApiService(),
      _ownsApiService = apiService == null,
      _sessionService = sessionService ?? SessionService();

  static const endpoint = '/api/auth/login';

  final ApiService _apiService;
  final bool _ownsApiService;
  final SessionService _sessionService;

  @override
  Future<AuthenticatedUser> login(LoginRequest request) async {
    try {
      final response = await _apiService.post(
        endpoint,
        request.toJson(),
        includeAuth: false,
      );
      if (response is! Map<String, dynamic>) {
        throw const FormatException('Respuesta de login inválida.');
      }

      final result = LoginResult.fromJson(response);
      if (!result.user.isClient) {
        throw const LoginFailure(
          LoginFailureType.unsupportedRole,
          'Esta aplicación móvil está disponible únicamente para clientes.',
        );
      }

      try {
        await _sessionService.saveSession(
          token: result.accessToken,
          user: result.user,
        );
      } catch (_) {
        throw const LoginFailure(
          LoginFailureType.storage,
          'No pudimos guardar la sesión de forma segura. Inténtalo nuevamente.',
        );
      }
      return result.user;
    } on LoginFailure {
      rethrow;
    } on ApiTimeoutException {
      throw const LoginFailure(
        LoginFailureType.timeout,
        'El servidor tardó demasiado en responder. Inténtalo nuevamente.',
      );
    } on ApiNetworkException {
      throw const LoginFailure(
        LoginFailureType.connection,
        'No pudimos conectar con FashionStore. Revisa tu conexión.',
      );
    } on ApiInvalidResponseException {
      throw const LoginFailure(
        LoginFailureType.invalidResponse,
        'Recibimos una respuesta inesperada. Inténtalo nuevamente.',
      );
    } on ApiException catch (error) {
      if (error.statusCode == 401) {
        throw const LoginFailure(
          LoginFailureType.invalidCredentials,
          'Correo o contraseña incorrectos.',
        );
      }
      if (error.statusCode == 403) {
        throw const LoginFailure(
          LoginFailureType.inactiveAccount,
          'La cuenta se encuentra inactiva.',
        );
      }
      if (error.statusCode == 422) {
        throw const LoginFailure(
          LoginFailureType.invalidData,
          'Revisa el correo y la contraseña ingresados.',
        );
      }
      throw const LoginFailure(
        LoginFailureType.server,
        'No pudimos iniciar sesión en este momento. Inténtalo nuevamente.',
      );
    } on FormatException {
      throw const LoginFailure(
        LoginFailureType.invalidResponse,
        'Recibimos una respuesta inesperada. Inténtalo nuevamente.',
      );
    }
  }

  void close() {
    if (_ownsApiService) {
      _apiService.close();
    }
  }
}
