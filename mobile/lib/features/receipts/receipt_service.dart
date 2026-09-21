import '../../core/errors/api_exception.dart';
import '../../core/services/api_service.dart';
import 'receipt_models.dart';

abstract interface class ReceiptGateway {
  Future<SaleReceipt> loadReceipt(int saleId);
}

class ReceiptService implements ReceiptGateway {
  ReceiptService({ApiService? apiService})
    : _apiService = apiService ?? ApiService(),
      _ownsApiService = apiService == null;

  final ApiService _apiService;
  final bool _ownsApiService;

  @override
  Future<SaleReceipt> loadReceipt(int saleId) async {
    try {
      final response = await _apiService.get('/api/client/purchases/$saleId/receipt');
      if (response is! Map<String, dynamic> || response['success'] != true) {
        throw const FormatException('Respuesta de comprobante inválida.');
      }
      final data = response['data'];
      if (data is! Map<String, dynamic>) throw const FormatException('Datos de comprobante ausentes.');
      return SaleReceipt.fromJson(data);
    } catch (error) {
      throw _mapFailure(error);
    }
  }

  ReceiptFailure _mapFailure(Object error) {
    if (error is ReceiptFailure) return error;
    if (error is ApiTimeoutException) return const ReceiptFailure(ReceiptFailureType.timeout, 'La solicitud tardó demasiado. Inténtalo nuevamente.');
    if (error is ApiNetworkException) return const ReceiptFailure(ReceiptFailureType.connection, 'No pudimos conectar con FashionStore. Revisa tu conexión.');
    if (error is ApiInvalidResponseException || error is FormatException) return const ReceiptFailure(ReceiptFailureType.invalidResponse, 'Recibimos una respuesta inesperada del comprobante.');
    if (error is ApiException) {
      final type = switch (error.statusCode) {
        401 => ReceiptFailureType.unauthorized,
        403 => ReceiptFailureType.forbidden,
        404 => ReceiptFailureType.notFound,
        409 => ReceiptFailureType.conflict,
        _ => ReceiptFailureType.server,
      };
      final message = switch (type) {
        ReceiptFailureType.unauthorized => 'Tu sesión expiró. Inicia sesión nuevamente.',
        ReceiptFailureType.forbidden => 'No tienes permiso para consultar este comprobante.',
        ReceiptFailureType.notFound => 'Comprobante no encontrado o no disponible.',
        ReceiptFailureType.conflict => 'El comprobante solo está disponible para ventas COMPLETADAS con pago válido.',
        _ => 'No pudimos consultar el comprobante. Inténtalo nuevamente.',
      };
      return ReceiptFailure(type, message);
    }
    return const ReceiptFailure(ReceiptFailureType.server, 'No pudimos consultar el comprobante. Inténtalo nuevamente.');
  }

  void close() {
    if (_ownsApiService) _apiService.close();
  }
}
