import '../../core/errors/api_exception.dart';
import '../../core/services/api_service.dart';
import 'cart_models.dart';

abstract interface class CartGateway {
  Future<CartData> loadCart();
  Future<CartData> addItem(int variantId, int quantity);
  Future<CartData> updateItem(int variantId, int quantity);
  Future<CartData> deleteItem(int variantId);
  Future<CartData> clearCart();
}

class CartService implements CartGateway {
  CartService({ApiService? apiService})
    : _apiService = apiService ?? ApiService(),
      _ownsApiService = apiService == null;

  static const endpoint = '/api/client/cart';

  final ApiService _apiService;
  final bool _ownsApiService;

  @override
  Future<CartData> loadCart() async {
    try {
      final response = await _apiService.get(endpoint);
      return _parseSuccess(response);
    } catch (error) {
      throw _mapFailure(error);
    }
  }

  @override
  Future<CartData> addItem(int variantId, int quantity) async {
    try {
      final response = await _apiService.post(
        '$endpoint/items',
        {'id_variante_producto': variantId, 'cantidad': quantity},
      );
      return _parseSuccess(response);
    } catch (error) {
      throw _mapFailure(error);
    }
  }

  @override
  Future<CartData> updateItem(int variantId, int quantity) async {
    try {
      final response = await _apiService.patch(
        '$endpoint/items/$variantId',
        {'cantidad': quantity},
      );
      return _parseSuccess(response);
    } catch (error) {
      throw _mapFailure(error);
    }
  }

  @override
  Future<CartData> deleteItem(int variantId) async {
    try {
      final response = await _apiService.delete('$endpoint/items/$variantId');
      return _parseSuccess(response);
    } catch (error) {
      throw _mapFailure(error);
    }
  }

  @override
  Future<CartData> clearCart() async {
    try {
      final response = await _apiService.delete('$endpoint/items');
      return _parseSuccess(response);
    } catch (error) {
      throw _mapFailure(error);
    }
  }

  CartData _parseSuccess(dynamic response) {
    if (response is! Map<String, dynamic> || response['success'] != true) {
      throw const FormatException('Respuesta del carrito inválida.');
    }
    final data = response['data'];
    if (data is! Map<String, dynamic>) {
      throw const FormatException('Datos del carrito ausentes.');
    }
    return CartData.fromJson(data);
  }

  CartFailure _mapFailure(Object error) {
    if (error is CartFailure) return error;
    if (error is ApiTimeoutException) {
      return const CartFailure(
        CartFailureType.timeout,
        'La solicitud tardó demasiado. Inténtalo nuevamente.',
      );
    }
    if (error is ApiNetworkException) {
      return const CartFailure(
        CartFailureType.connection,
        'No pudimos conectar con FashionStore. Revisa tu conexión.',
      );
    }
    if (error is ApiInvalidResponseException || error is FormatException) {
      return const CartFailure(
        CartFailureType.invalidResponse,
        'Recibimos una respuesta inesperada del carrito.',
      );
    }
    if (error is ApiException) {
      final type = switch (error.statusCode) {
        401 => CartFailureType.unauthorized,
        403 => CartFailureType.forbidden,
        404 => CartFailureType.notFound,
        409 => CartFailureType.conflict,
        422 => CartFailureType.invalidData,
        _ => CartFailureType.server,
      };
      final message = switch (type) {
        CartFailureType.unauthorized =>
          'Tu sesión expiró. Inicia sesión nuevamente.',
        CartFailureType.forbidden =>
          'Tu cuenta no puede gestionar el carrito.',
        CartFailureType.notFound => 'No encontramos este artículo en tu carrito.',
        CartFailureType.conflict =>
          'No hay stock suficiente para la cantidad solicitada.',
        CartFailureType.invalidData => 'Revisa la cantidad ingresada.',
        _ => 'No pudimos procesar tu carrito. Inténtalo nuevamente.',
      };
      return CartFailure(type, message);
    }
    return const CartFailure(
      CartFailureType.server,
      'No pudimos procesar tu carrito. Inténtalo nuevamente.',
    );
  }

  void close() {
    if (_ownsApiService) _apiService.close();
  }
}
