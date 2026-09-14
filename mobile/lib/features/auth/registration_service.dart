import '../../core/errors/api_exception.dart';
import '../../core/services/api_service.dart';
import 'registration_models.dart';

abstract interface class ClientRegistrationGateway {
  Future<ClientRegistrationResult> register(ClientRegistrationRequest request);
}

enum RegistrationFailureType {
  duplicateEmail,
  invalidData,
  timeout,
  connection,
  server,
  invalidResponse,
}

class RegistrationFailure implements Exception {
  const RegistrationFailure(this.type, this.message);

  final RegistrationFailureType type;
  final String message;

  @override
  String toString() => 'RegistrationFailure($type): $message';
}

class RegistrationService implements ClientRegistrationGateway {
  RegistrationService({ApiService? apiService})
    : _apiService = apiService ?? ApiService(),
      _ownsApiService = apiService == null;

  static const endpoint = '/api/auth/register';

  final ApiService _apiService;
  final bool _ownsApiService;

  @override
  Future<ClientRegistrationResult> register(
    ClientRegistrationRequest request,
  ) async {
    try {
      final response = await _apiService.post(
        endpoint,
        request.toJson(),
        includeAuth: false,
      );
      if (response is! Map<String, dynamic> || response['success'] != true) {
        throw const FormatException('Respuesta de registro inválida.');
      }

      final data = response['data'];
      final message = response['message'];
      if (data is! Map<String, dynamic> || message is! String) {
        throw const FormatException('Respuesta de registro incompleta.');
      }

      return ClientRegistrationResult(
        message: message,
        client: RegisteredClient.fromJson(data),
      );
    } on ApiTimeoutException {
      throw const RegistrationFailure(
        RegistrationFailureType.timeout,
        'El servidor tardó demasiado en responder. Inténtalo nuevamente.',
      );
    } on ApiNetworkException {
      throw const RegistrationFailure(
        RegistrationFailureType.connection,
        'No pudimos conectar con FashionStore. Revisa tu conexión.',
      );
    } on ApiInvalidResponseException {
      throw const RegistrationFailure(
        RegistrationFailureType.invalidResponse,
        'Recibimos una respuesta inesperada. Inténtalo nuevamente.',
      );
    } on ApiException catch (error) {
      if (error.statusCode == 409) {
        throw const RegistrationFailure(
          RegistrationFailureType.duplicateEmail,
          'Este correo ya se encuentra registrado.',
        );
      }
      if (error.statusCode == 422) {
        throw const RegistrationFailure(
          RegistrationFailureType.invalidData,
          'Revisa los datos ingresados.',
        );
      }
      throw const RegistrationFailure(
        RegistrationFailureType.server,
        'No pudimos crear tu cuenta en este momento. Inténtalo nuevamente.',
      );
    } on FormatException {
      throw const RegistrationFailure(
        RegistrationFailureType.invalidResponse,
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
