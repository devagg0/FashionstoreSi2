import '../../core/errors/api_exception.dart';
import '../../core/services/api_service.dart';
import 'checkout_models.dart';

abstract interface class CheckoutGateway {
  Future<DigitalSale> confirmCheckout({
    required int cartId,
    required int branchId,
  });

  Future<DigitalSale> loadPendingSale(int saleId);
}

class CheckoutService implements CheckoutGateway {
  CheckoutService({ApiService? apiService})
    : _apiService = apiService ?? ApiService(),
      _ownsApiService = apiService == null;

  static const checkoutEndpoint = '/api/client/cart/checkout';

  final ApiService _apiService;
  final bool _ownsApiService;

  @override
  Future<DigitalSale> confirmCheckout({
    required int cartId,
    required int branchId,
  }) async {
    try {
      final response = await _apiService.post(checkoutEndpoint, {
        'id_carrito': cartId,
        'id_sucursal': branchId,
      });
      return _parse(response);
    } catch (error) {
      throw _mapFailure(error);
    }
  }

  @override
  Future<DigitalSale> loadPendingSale(int saleId) async {
    try {
      final response = await _apiService.get('/api/client/sales/$saleId');
      return _parse(response);
    } catch (error) {
      throw _mapFailure(error);
    }
  }

  DigitalSale _parse(dynamic response) {
    if (response is! Map<String, dynamic> || response['success'] != true) {
      throw const FormatException('Respuesta de compra inválida.');
    }
    final data = response['data'];
    if (data is! Map<String, dynamic>) {
      throw const FormatException('Datos de compra ausentes.');
    }
    return DigitalSale.fromJson(data);
  }

  CheckoutFailure _mapFailure(Object error) {
    if (error is CheckoutFailure) return error;
    if (error is ApiTimeoutException) {
      return const CheckoutFailure(
        CheckoutFailureType.timeout,
        'La solicitud tardó demasiado. Inténtalo nuevamente.',
      );
    }
    if (error is ApiNetworkException) {
      return const CheckoutFailure(
        CheckoutFailureType.connection,
        'No pudimos conectar con FashionStore. Revisa tu conexión.',
      );
    }
    if (error is ApiInvalidResponseException || error is FormatException) {
      return const CheckoutFailure(
        CheckoutFailureType.invalidResponse,
        'Recibimos una respuesta inesperada de la compra.',
      );
    }
    if (error is ApiException) {
      final type = switch (error.statusCode) {
        401 => CheckoutFailureType.unauthorized,
        403 => CheckoutFailureType.forbidden,
        404 => CheckoutFailureType.notFound,
        409 => CheckoutFailureType.conflict,
        422 => CheckoutFailureType.invalidData,
        _ => CheckoutFailureType.server,
      };
      final message = switch (type) {
        CheckoutFailureType.unauthorized =>
          'Tu sesión expiró. Inicia sesión nuevamente.',
        CheckoutFailureType.forbidden =>
          'Esta compra está disponible para cuentas de cliente.',
        CheckoutFailureType.notFound =>
          'El carrito, la variante, la sucursal o la venta ya no están disponibles.',
        CheckoutFailureType.conflict =>
          'No hay stock suficiente o el carrito ya fue convertido.',
        CheckoutFailureType.invalidData =>
          'Revisa el carrito y selecciona una sucursal válida.',
        _ => 'No fue posible procesar la compra. Inténtalo nuevamente.',
      };
      return CheckoutFailure(type, message);
    }
    return const CheckoutFailure(
      CheckoutFailureType.server,
      'No fue posible procesar la compra. Inténtalo nuevamente.',
    );
  }

  void close() {
    if (_ownsApiService) _apiService.close();
  }
}
