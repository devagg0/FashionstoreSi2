import '../../core/errors/api_exception.dart';
import '../../core/services/api_service.dart';
import 'chatbot_models.dart';

abstract interface class ChatbotGateway {
  Future<ChatbotResponse> sendMessage({
    required String message,
    required List<ChatMessage> history,
  });
}

class ChatbotService implements ChatbotGateway {
  ChatbotService({ApiService? apiService})
    : _apiService = apiService ?? ApiService(),
      _ownsApiService = apiService == null;

  static const endpoint = '/api/client/chatbot/message';
  final ApiService _apiService;
  final bool _ownsApiService;

  @override
  Future<ChatbotResponse> sendMessage({
    required String message,
    required List<ChatMessage> history,
  }) async {
    try {
      final response = await _apiService.post(endpoint, {
        'message': message.trim(),
        'history': history
            .map(
              (item) => {
                'role': item.role == ChatMessageRole.user
                    ? 'user'
                    : 'assistant',
                'content': item.content,
              },
            )
            .toList(growable: false),
      }, includeAuth: true);
      if (response is! Map<String, dynamic>) {
        throw const FormatException('Respuesta del asistente inválida.');
      }
      return ChatbotResponse.fromJson(response);
    } catch (error) {
      throw _mapFailure(error);
    }
  }

  ChatbotFailure _mapFailure(Object error) {
    if (error is ChatbotFailure) return error;
    if (error is ApiTimeoutException) {
      return const ChatbotFailure(
        ChatbotFailureType.timeout,
        'La solicitud tardó demasiado. Inténtalo nuevamente.',
      );
    }
    if (error is ApiNetworkException) {
      return const ChatbotFailure(
        ChatbotFailureType.connection,
        'No pudimos conectar con FashionStore. Revisa tu conexión.',
      );
    }
    if (error is ApiInvalidResponseException || error is FormatException) {
      return const ChatbotFailure(
        ChatbotFailureType.invalidResponse,
        'Recibimos una respuesta inesperada del asistente.',
      );
    }
    if (error is ApiException) {
      final type = switch (error.statusCode) {
        401 => ChatbotFailureType.unauthorized,
        403 => ChatbotFailureType.forbidden,
        _ => ChatbotFailureType.server,
      };
      final message = switch (type) {
        ChatbotFailureType.unauthorized =>
          'Tu sesión expiró. Inicia sesión nuevamente.',
        ChatbotFailureType.forbidden =>
          'El asistente está disponible para cuentas de cliente.',
        _ => 'No pudimos procesar tu consulta. Inténtalo nuevamente.',
      };
      return ChatbotFailure(type, message);
    }
    return const ChatbotFailure(
      ChatbotFailureType.server,
      'No pudimos procesar tu consulta. Inténtalo nuevamente.',
    );
  }

  void close() {
    if (_ownsApiService) _apiService.close();
  }
}
