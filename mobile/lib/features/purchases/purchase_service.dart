import '../../core/errors/api_exception.dart';
import '../../core/services/api_service.dart';
import 'purchase_models.dart';

abstract interface class PurchaseGateway {
  Future<PurchasePage> loadPurchases({int limit = 12, int offset = 0});
  Future<PurchaseDetail> loadPurchaseDetail(int saleId);
}

class PurchasePage {
  const PurchasePage({required this.items, required this.total, required this.limit, required this.offset});

  final List<PurchaseSummary> items;
  final int total;
  final int limit;
  final int offset;
}

class PurchaseService implements PurchaseGateway {
  PurchaseService({ApiService? apiService})
    : _apiService = apiService ?? ApiService(),
      _ownsApiService = apiService == null;

  static const endpoint = '/api/client/purchases';
  final ApiService _apiService;
  final bool _ownsApiService;

  @override
  Future<PurchasePage> loadPurchases({int limit = 12, int offset = 0}) async {
    try {
      final response = await _apiService.get(endpoint, queryParameters: {
        'limit': '$limit',
        'offset': '$offset',
      });
      if (response is! Map<String, dynamic> || response['success'] != true) {
        throw const FormatException('Respuesta de compras inválida.');
      }
      final data = response['data'];
      if (data is! Map<String, dynamic>) throw const FormatException('Datos de compras ausentes.');
      final items = data['items'];
      if (items is! List) throw const FormatException('Lista de compras inválida.');
      return PurchasePage(
        items: items.map((item) {
          if (item is! Map<String, dynamic>) throw const FormatException('Compra inválida.');
          return PurchaseSummary.fromJson(item);
        }).toList(growable: false),
        total: _int(data, 'total'),
        limit: _int(data, 'limit'),
        offset: _int(data, 'offset'),
      );
    } catch (error) {
      throw _mapFailure(error);
    }
  }

  @override
  Future<PurchaseDetail> loadPurchaseDetail(int saleId) async {
    try {
      final response = await _apiService.get('$endpoint/$saleId');
      if (response is! Map<String, dynamic> || response['success'] != true) {
        throw const FormatException('Respuesta de detalle inválida.');
      }
      final data = response['data'];
      if (data is! Map<String, dynamic>) throw const FormatException('Detalle ausente.');
      final detail = PurchaseDetail.fromJson(data);
      if (detail.saleId != saleId) throw const FormatException('Compra no coincidente.');
      return detail;
    } catch (error) {
      throw _mapFailure(error);
    }
  }

  PurchaseFailure _mapFailure(Object error) {
    if (error is PurchaseFailure) return error;
    if (error is ApiTimeoutException) return const PurchaseFailure(PurchaseFailureType.timeout, 'La solicitud tardó demasiado. Inténtalo nuevamente.');
    if (error is ApiNetworkException) return const PurchaseFailure(PurchaseFailureType.connection, 'No pudimos conectar con FashionStore. Revisa tu conexión.');
    if (error is ApiInvalidResponseException || error is FormatException) return const PurchaseFailure(PurchaseFailureType.invalidResponse, 'Recibimos una respuesta inesperada de compras.');
    if (error is ApiException) {
      final type = switch (error.statusCode) {
        401 => PurchaseFailureType.unauthorized,
        403 => PurchaseFailureType.forbidden,
        404 => PurchaseFailureType.notFound,
        _ => PurchaseFailureType.server,
      };
      final message = switch (type) {
        PurchaseFailureType.unauthorized => 'Tu sesión expiró. Inicia sesión nuevamente.',
        PurchaseFailureType.forbidden => 'No tienes permiso para consultar estas compras.',
        PurchaseFailureType.notFound => 'Compra no encontrada.',
        _ => 'No pudimos consultar tus compras. Inténtalo nuevamente.',
      };
      return PurchaseFailure(type, message);
    }
    return const PurchaseFailure(PurchaseFailureType.server, 'No pudimos consultar tus compras. Inténtalo nuevamente.');
  }

  void close() {
    if (_ownsApiService) _apiService.close();
  }
}

int _int(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is int) return value;
  throw FormatException('$key inválido.');
}
