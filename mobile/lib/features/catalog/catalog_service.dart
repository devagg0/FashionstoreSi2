import '../../core/errors/api_exception.dart';
import '../../core/services/api_service.dart';
import 'catalog_models.dart';

abstract interface class CatalogGateway {
  Future<CatalogPage> loadProducts(CatalogFilters filters);

  Future<CatalogProductDetail> loadProductDetail(int productId);
}

enum CatalogFailureType {
  notFound,
  invalidFilters,
  timeout,
  connection,
  server,
  invalidResponse,
}

class CatalogFailure implements Exception {
  const CatalogFailure(this.type, this.message);
  final CatalogFailureType type;
  final String message;

  @override
  String toString() => 'CatalogFailure($type): $message';
}

class CatalogService implements CatalogGateway {
  CatalogService({ApiService? apiService})
    : _apiService = apiService ?? ApiService(),
      _ownsApiService = apiService == null;

  static const endpoint = '/api/catalog/products';
  final ApiService _apiService;
  final bool _ownsApiService;

  @override
  Future<CatalogPage> loadProducts(CatalogFilters filters) async {
    try {
      final response = await _apiService.get(
        endpoint,
        queryParameters: filters.toQueryParameters(),
        includeAuth: false,
      );
      if (response is! Map<String, dynamic> || response['success'] != true) {
        throw const FormatException('Respuesta de catálogo inválida.');
      }
      final pagination = response['pagination'];
      final data = response['data'];
      if (pagination is! Map<String, dynamic> || data is! List) {
        throw const FormatException('Catálogo incompleto.');
      }
      final products = data
          .map((item) {
            if (item is! Map<String, dynamic>) {
              throw const FormatException('Producto inválido.');
            }
            return CatalogProduct.fromJson(item);
          })
          .toList(growable: false);
      return CatalogPage(
        products: products,
        pagination: CatalogPagination.fromJson(pagination),
      );
    } catch (error) {
      throw _mapFailure(error, detail: false);
    }
  }

  @override
  Future<CatalogProductDetail> loadProductDetail(int productId) async {
    try {
      final response = await _apiService.get(
        '$endpoint/$productId',
        includeAuth: false,
      );
      if (response is! Map<String, dynamic> || response['success'] != true) {
        throw const FormatException('Respuesta de detalle inválida.');
      }
      final data = response['data'];
      if (data is! Map<String, dynamic>) {
        throw const FormatException('Detalle de producto ausente.');
      }
      return CatalogProductDetail.fromJson(data);
    } catch (error) {
      throw _mapFailure(error, detail: true);
    }
  }

  CatalogFailure _mapFailure(Object error, {required bool detail}) {
    if (error is CatalogFailure) return error;
    if (error is ApiTimeoutException) {
      return const CatalogFailure(
        CatalogFailureType.timeout,
        'El catálogo tardó demasiado en responder. Inténtalo nuevamente.',
      );
    }
    if (error is ApiNetworkException) {
      return const CatalogFailure(
        CatalogFailureType.connection,
        'No pudimos conectar con FashionStore. Revisa tu conexión.',
      );
    }
    if (error is ApiInvalidResponseException || error is FormatException) {
      return const CatalogFailure(
        CatalogFailureType.invalidResponse,
        'Recibimos una respuesta inesperada del catálogo.',
      );
    }
    if (error is ApiException) {
      if (error.statusCode == 404) {
        return CatalogFailure(
          CatalogFailureType.notFound,
          detail
              ? 'La prenda ya no está disponible.'
              : 'No encontramos la selección solicitada.',
        );
      }
      if (error.statusCode == 422) {
        return const CatalogFailure(
          CatalogFailureType.invalidFilters,
          'Revisa los filtros seleccionados.',
        );
      }
    }
    return CatalogFailure(
      CatalogFailureType.server,
      detail
          ? 'No pudimos cargar esta prenda.'
          : 'No pudimos cargar el catálogo.',
    );
  }

  void close() {
    if (_ownsApiService) _apiService.close();
  }
}
