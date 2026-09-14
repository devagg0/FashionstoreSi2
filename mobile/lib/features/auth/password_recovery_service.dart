import '../../core/errors/api_exception.dart';
import '../../core/services/api_service.dart';
import 'password_recovery_models.dart';

abstract interface class PasswordRecoveryGateway {
  Future<String> requestRecovery(PasswordRecoveryRequest request);

  Future<PasswordRecoveryVerificationResult> verifyCode(
    PasswordRecoveryVerificationRequest request,
  );

  Future<String> resetPassword(PasswordResetRequest request);
}

enum PasswordRecoveryFailureType {
  invalidCode,
  invalidResetToken,
  invalidData,
  timeout,
  connection,
  server,
  invalidResponse,
}

class PasswordRecoveryFailure implements Exception {
  const PasswordRecoveryFailure(this.type, this.message);

  final PasswordRecoveryFailureType type;
  final String message;

  @override
  String toString() => 'PasswordRecoveryFailure($type): $message';
}

enum _RecoveryOperation { request, verify, reset }

class PasswordRecoveryService implements PasswordRecoveryGateway {
  PasswordRecoveryService({ApiService? apiService})
    : _apiService = apiService ?? ApiService(),
      _ownsApiService = apiService == null;

  static const requestEndpoint = '/api/auth/password-recovery/request';
  static const verifyEndpoint = '/api/auth/password-recovery/verify';
  static const resetEndpoint = '/api/auth/password-recovery/reset';

  final ApiService _apiService;
  final bool _ownsApiService;

  @override
  Future<String> requestRecovery(PasswordRecoveryRequest request) async {
    try {
      final response = await _apiService.post(
        requestEndpoint,
        request.toJson(),
        includeAuth: false,
      );
      return _successMessage(response);
    } catch (error) {
      throw _mapFailure(error, operation: _RecoveryOperation.request);
    }
  }

  @override
  Future<PasswordRecoveryVerificationResult> verifyCode(
    PasswordRecoveryVerificationRequest request,
  ) async {
    try {
      final response = await _apiService.post(
        verifyEndpoint,
        request.toJson(),
        includeAuth: false,
      );
      if (response is! Map<String, dynamic>) {
        throw const FormatException('Respuesta de verificación inválida.');
      }
      final message = _successMessage(response);
      final resetToken = response['reset_token'];
      if (resetToken is! String || resetToken.trim().isEmpty) {
        throw const FormatException('Reset token ausente.');
      }
      return PasswordRecoveryVerificationResult(
        message: message,
        resetToken: resetToken.trim(),
      );
    } catch (error) {
      throw _mapFailure(error, operation: _RecoveryOperation.verify);
    }
  }

  @override
  Future<String> resetPassword(PasswordResetRequest request) async {
    try {
      final response = await _apiService.post(
        resetEndpoint,
        request.toJson(),
        includeAuth: false,
      );
      return _successMessage(response);
    } catch (error) {
      throw _mapFailure(error, operation: _RecoveryOperation.reset);
    }
  }

  String _successMessage(dynamic response) {
    if (response is! Map<String, dynamic> || response['success'] != true) {
      throw const FormatException('Respuesta de recuperación inválida.');
    }
    final message = response['message'];
    if (message is! String || message.trim().isEmpty) {
      throw const FormatException('Mensaje de recuperación ausente.');
    }
    return message;
  }

  PasswordRecoveryFailure _mapFailure(
    Object error, {
    required _RecoveryOperation operation,
  }) {
    if (error is PasswordRecoveryFailure) {
      return error;
    }
    if (error is ApiTimeoutException) {
      return const PasswordRecoveryFailure(
        PasswordRecoveryFailureType.timeout,
        'El servidor tardó demasiado en responder. Inténtalo nuevamente.',
      );
    }
    if (error is ApiNetworkException) {
      return const PasswordRecoveryFailure(
        PasswordRecoveryFailureType.connection,
        'No pudimos conectar con FashionStore. Revisa tu conexión.',
      );
    }
    if (error is ApiInvalidResponseException || error is FormatException) {
      return const PasswordRecoveryFailure(
        PasswordRecoveryFailureType.invalidResponse,
        'Recibimos una respuesta inesperada. Inténtalo nuevamente.',
      );
    }
    if (error is ApiException) {
      if (error.statusCode == 400 && operation == _RecoveryOperation.verify) {
        return const PasswordRecoveryFailure(
          PasswordRecoveryFailureType.invalidCode,
          'El código es inválido o expiró. Solicita uno nuevo si es necesario.',
        );
      }
      if (error.statusCode == 400 && operation == _RecoveryOperation.reset) {
        return const PasswordRecoveryFailure(
          PasswordRecoveryFailureType.invalidResetToken,
          'La autorización para cambiar la contraseña es inválida o expiró.',
        );
      }
      if (error.statusCode == 422) {
        return const PasswordRecoveryFailure(
          PasswordRecoveryFailureType.invalidData,
          'Revisa los datos ingresados.',
        );
      }
    }
    return const PasswordRecoveryFailure(
      PasswordRecoveryFailureType.server,
      'No pudimos completar la recuperación en este momento.',
    );
  }

  void close() {
    if (_ownsApiService) {
      _apiService.close();
    }
  }
}
