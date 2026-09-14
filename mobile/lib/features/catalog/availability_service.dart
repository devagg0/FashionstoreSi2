import '../../core/errors/api_exception.dart';
import '../../core/services/api_service.dart';
import 'availability_models.dart';

abstract interface class CatalogAvailabilityGateway {
  Future<CatalogAvailabilityResult> loadVariantAvailability({
    required int productId,
    required int variantId,
  });
}

enum AvailabilityFailureType {
  invalidVariant,
  notFound,
  timeout,
  connection,
  server,
  invalidResponse,
}

class AvailabilityFailure implements Exception {
  const AvailabilityFailure(this.type, this.message);
  final AvailabilityFailureType type;
  final String message;
}

class CatalogAvailabilityService implements CatalogAvailabilityGateway {
  CatalogAvailabilityService({ApiService? apiService})
    : _apiService = apiService ?? ApiService(),
      _ownsApiService = apiService == null;

  final ApiService _apiService;
  final bool _ownsApiService;

  static String endpoint(int productId) =>
      '/api/catalog/products/$productId/availability';

  @override
  Future<CatalogAvailabilityResult> loadVariantAvailability({
    required int productId,
    required int variantId,
  }) async {
    try {
      final response = await _apiService.get(
        endpoint(productId),
        queryParameters: {'id_variante_producto': '$variantId'},
        includeAuth: false,
      );
      if (response is! Map<String, dynamic> || response['success'] != true) {
        throw const FormatException('Respuesta de disponibilidad inválida.');
      }
      final data = response['data'];
      if (data is! Map<String, dynamic>) {
        throw const FormatException('Datos de disponibilidad ausentes.');
      }
      final result = CatalogAvailabilityResult.fromJson(data);
      if (result.productId != productId) {
        throw const FormatException('El producto de la respuesta no coincide.');
      }
      return result;
    } catch (error) {
      throw _mapFailure(error);
    }
  }

  AvailabilityFailure _mapFailure(Object error) {
    if (error is AvailabilityFailure) return error;
    if (error is ApiTimeoutException) {
      return const AvailabilityFailure(
        AvailabilityFailureType.timeout,
        'La consulta tardó demasiado. Inténtalo nuevamente.',
      );
    }
    if (error is ApiNetworkException) {
      return const AvailabilityFailure(
        AvailabilityFailureType.connection,
        'No pudimos consultar la disponibilidad. Revisa tu conexión.',
      );
    }
    if (error is ApiInvalidResponseException || error is FormatException) {
      return const AvailabilityFailure(
        AvailabilityFailureType.invalidResponse,
        'Recibimos una respuesta inesperada de disponibilidad.',
      );
    }
    if (error is ApiException) {
      if (error.statusCode == 400) {
        return const AvailabilityFailure(
          AvailabilityFailureType.invalidVariant,
          'La variante seleccionada no corresponde a esta prenda.',
        );
      }
      if (error.statusCode == 404) {
        return const AvailabilityFailure(
          AvailabilityFailureType.notFound,
          'La prenda o variante seleccionada ya no está disponible.',
        );
      }
    }
    return const AvailabilityFailure(
      AvailabilityFailureType.server,
      'No pudimos consultar la disponibilidad. Inténtalo nuevamente.',
    );
  }

  void close() {
    if (_ownsApiService) _apiService.close();
  }
}
