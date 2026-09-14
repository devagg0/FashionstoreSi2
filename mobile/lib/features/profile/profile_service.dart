import '../../core/errors/api_exception.dart';
import '../../core/services/api_service.dart';
import '../auth/login_models.dart';

abstract interface class ProfileGateway {
  Future<AuthenticatedUser> loadProfile();
}

enum ProfileFailureType {
  unauthorized,
  inactiveAccount,
  unsupportedRole,
  timeout,
  connection,
  server,
  invalidResponse,
}

class ProfileFailure implements Exception {
  const ProfileFailure(this.type, this.message);

  final ProfileFailureType type;
  final String message;

  bool get invalidatesSession =>
      type == ProfileFailureType.unauthorized ||
      type == ProfileFailureType.inactiveAccount ||
      type == ProfileFailureType.unsupportedRole;

  @override
  String toString() => 'ProfileFailure($type): $message';
}

class ProfileService implements ProfileGateway {
  ProfileService({ApiService? apiService})
    : _apiService = apiService ?? ApiService(),
      _ownsApiService = apiService == null;

  static const endpoint = '/api/auth/me';

  final ApiService _apiService;
  final bool _ownsApiService;

  @override
  Future<AuthenticatedUser> loadProfile() async {
    try {
      final response = await _apiService.get(endpoint);
      if (response is! Map<String, dynamic> || response['success'] != true) {
        throw const FormatException('Respuesta de perfil inválida.');
      }
      final data = response['data'];
      if (data is! Map<String, dynamic>) {
        throw const FormatException('Datos de perfil ausentes.');
      }
      final user = AuthenticatedUser.fromJson(data);
      if (!user.isClient) {
        throw const ProfileFailure(
          ProfileFailureType.unsupportedRole,
          'Esta aplicación móvil está disponible únicamente para clientes.',
        );
      }
      return user;
    } on ProfileFailure {
      rethrow;
    } on ApiTimeoutException {
      throw const ProfileFailure(
        ProfileFailureType.timeout,
        'El servidor tardó demasiado en responder. Inténtalo nuevamente.',
      );
    } on ApiNetworkException {
      throw const ProfileFailure(
        ProfileFailureType.connection,
        'No pudimos conectar con FashionStore. Revisa tu conexión.',
      );
    } on ApiInvalidResponseException {
      throw const ProfileFailure(
        ProfileFailureType.invalidResponse,
        'Recibimos una respuesta inesperada. Inténtalo nuevamente.',
      );
    } on ApiException catch (error) {
      if (error.statusCode == 401) {
        throw const ProfileFailure(
          ProfileFailureType.unauthorized,
          'Tu sesión expiró. Inicia sesión nuevamente.',
        );
      }
      if (error.statusCode == 403) {
        throw const ProfileFailure(
          ProfileFailureType.inactiveAccount,
          'La cuenta se encuentra inactiva.',
        );
      }
      throw const ProfileFailure(
        ProfileFailureType.server,
        'No pudimos cargar tu perfil en este momento.',
      );
    } on FormatException {
      throw const ProfileFailure(
        ProfileFailureType.invalidResponse,
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
