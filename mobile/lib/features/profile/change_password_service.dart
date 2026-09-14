import '../../core/errors/api_exception.dart';
import '../../core/services/api_service.dart';
import 'change_password_models.dart';

abstract interface class ChangePasswordGateway {
  Future<String> changePassword(ChangePasswordRequest request);
}

enum ChangePasswordFailureType {
  incorrectCurrentPassword,
  reusedPassword,
  unauthorized,
  inactiveAccount,
  invalidData,
  timeout,
  connection,
  server,
  invalidResponse,
}

class ChangePasswordFailure implements Exception {
  const ChangePasswordFailure(this.type, this.message);

  final ChangePasswordFailureType type;
  final String message;

  bool get invalidatesSession =>
      type == ChangePasswordFailureType.unauthorized ||
      type == ChangePasswordFailureType.inactiveAccount;

  @override
  String toString() => 'ChangePasswordFailure($type): $message';
}

class ChangePasswordService implements ChangePasswordGateway {
  ChangePasswordService({ApiService? apiService})
    : _apiService = apiService ?? ApiService(),
      _ownsApiService = apiService == null;

  static const endpoint = '/api/auth/change-password';

  final ApiService _apiService;
  final bool _ownsApiService;

  @override
  Future<String> changePassword(ChangePasswordRequest request) async {
    try {
      final response = await _apiService.put(endpoint, request.toJson());
      if (response is! Map<String, dynamic> || response['success'] != true) {
        throw const FormatException('Respuesta de cambio inválida.');
      }
      final message = response['message'];
      if (message is! String || message.trim().isEmpty) {
        throw const FormatException('Respuesta de cambio incompleta.');
      }
      return message;
    } on ApiTimeoutException {
      throw const ChangePasswordFailure(
        ChangePasswordFailureType.timeout,
        'El servidor tardó demasiado en responder. Inténtalo nuevamente.',
      );
    } on ApiNetworkException {
      throw const ChangePasswordFailure(
        ChangePasswordFailureType.connection,
        'No pudimos conectar con FashionStore. Revisa tu conexión.',
      );
    } on ApiInvalidResponseException {
      throw const ChangePasswordFailure(
        ChangePasswordFailureType.invalidResponse,
        'Recibimos una respuesta inesperada. Inténtalo nuevamente.',
      );
    } on ApiException catch (error) {
      if (error.statusCode == 400 &&
          error.message == 'La contraseña actual es incorrecta') {
        throw const ChangePasswordFailure(
          ChangePasswordFailureType.incorrectCurrentPassword,
          'La contraseña actual es incorrecta.',
        );
      }
      if (error.statusCode == 400 &&
          error.message ==
              'La nueva contraseña debe ser diferente a la actual') {
        throw const ChangePasswordFailure(
          ChangePasswordFailureType.reusedPassword,
          'La nueva contraseña debe ser diferente a la actual.',
        );
      }
      if (error.statusCode == 401) {
        throw const ChangePasswordFailure(
          ChangePasswordFailureType.unauthorized,
          'Tu sesión expiró. Inicia sesión nuevamente.',
        );
      }
      if (error.statusCode == 403) {
        throw const ChangePasswordFailure(
          ChangePasswordFailureType.inactiveAccount,
          'La cuenta se encuentra inactiva.',
        );
      }
      if (error.statusCode == 422) {
        throw const ChangePasswordFailure(
          ChangePasswordFailureType.invalidData,
          'Revisa las contraseñas ingresadas.',
        );
      }
      throw const ChangePasswordFailure(
        ChangePasswordFailureType.server,
        'No pudimos actualizar la contraseña en este momento.',
      );
    } on FormatException {
      throw const ChangePasswordFailure(
        ChangePasswordFailureType.invalidResponse,
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
