import '../../core/errors/api_exception.dart';
import '../../core/services/api_service.dart';
import 'recommendation_models.dart';

abstract interface class RecommendationGateway {
  Future<RecommendationPage> loadRecommendations({int limit = 12});
}

class RecommendationPage {
  const RecommendationPage({required this.items, required this.origin});
  final List<RecommendationItem> items;
  final String origin;
}

class RecommendationService implements RecommendationGateway {
  RecommendationService({ApiService? apiService})
    : _apiService = apiService ?? ApiService(),
      _ownsApiService = apiService == null;

  final ApiService _apiService;
  final bool _ownsApiService;
  static const endpoint = '/api/client/recommendations';

  @override
  Future<RecommendationPage> loadRecommendations({int limit = 12}) async {
    try {
      final response = await _apiService.get(endpoint, queryParameters: {'limit': '$limit'});
      if (response is! Map<String, dynamic> || response['success'] != true) {
        throw const FormatException('Respuesta de recomendaciones inválida.');
      }
      final data = response['data'];
      if (data is! List) throw const FormatException('Lista de recomendaciones inválida.');
      return RecommendationPage(
        origin: response['origen'] is String ? response['origen'] as String : 'FALLBACK',
        items: data.map((item) {
          if (item is! Map<String, dynamic>) throw const FormatException('Recomendación inválida.');
          return RecommendationItem.fromJson(item);
        }).toList(growable: false),
      );
    } catch (error) {
      throw _mapFailure(error);
    }
  }

  RecommendationFailure _mapFailure(Object error) {
    if (error is RecommendationFailure) return error;
    if (error is ApiTimeoutException) return const RecommendationFailure(RecommendationFailureType.timeout, 'La solicitud tardó demasiado. Inténtalo nuevamente.');
    if (error is ApiNetworkException) return const RecommendationFailure(RecommendationFailureType.connection, 'No pudimos conectar con FashionStore. Revisa tu conexión.');
    if (error is ApiInvalidResponseException || error is FormatException) return const RecommendationFailure(RecommendationFailureType.invalidResponse, 'Recibimos una respuesta inesperada de recomendaciones.');
    if (error is ApiException) {
      final type = switch (error.statusCode) {
        401 => RecommendationFailureType.unauthorized,
        403 => RecommendationFailureType.forbidden,
        404 => RecommendationFailureType.notFound,
        422 => RecommendationFailureType.invalidData,
        _ => RecommendationFailureType.server,
      };
      final message = switch (type) {
        RecommendationFailureType.unauthorized => 'Tu sesión expiró. Inicia sesión nuevamente.',
        RecommendationFailureType.forbidden => 'Las recomendaciones están disponibles para cuentas de cliente.',
        RecommendationFailureType.notFound => 'No encontramos la ubicación solicitada.',
        RecommendationFailureType.invalidData => error.message,
        _ => 'No pudimos generar tus recomendaciones. Inténtalo nuevamente.',
      };
      return RecommendationFailure(type, message);
    }
    return const RecommendationFailure(RecommendationFailureType.server, 'No pudimos generar tus recomendaciones. Inténtalo nuevamente.');
  }

  void close() {
    if (_ownsApiService) _apiService.close();
  }
}
