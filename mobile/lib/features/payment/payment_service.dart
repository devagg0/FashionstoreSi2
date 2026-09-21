import 'dart:io';

import '../../core/errors/api_exception.dart';
import '../../core/services/api_service.dart';
import 'payment_models.dart';

abstract interface class PaymentGateway {
  Future<PaymentData> startPayment({
    required int saleId,
    required String idempotencyKey,
  });

  Future<PaymentData> getPayment(int paymentId);

  Future<StripeCheckoutData> createCheckoutSession(int paymentId);

  Future<PaymentData> syncStripe(int paymentId);
}

class PaymentService implements PaymentGateway {
  PaymentService({ApiService? apiService})
    : _apiService = apiService ?? ApiService(),
      _ownsApiService = apiService == null;

  final ApiService _apiService;
  final bool _ownsApiService;
  final Map<int, PaymentData> _paymentsBySale = {};

  @override
  Future<PaymentData> startPayment({
    required int saleId,
    required String idempotencyKey,
  }) async {
    try {
      final previous = _paymentsBySale[saleId];
      if (previous != null) {
        final current = await getPayment(previous.paymentId);
        _paymentsBySale[saleId] = current;
        return current;
      }
      final response = await _apiService.post(
        '/api/sales/$saleId/payments',
        {'medio': 'TARJETA'},
        headers: {'Idempotency-Key': idempotencyKey},
      );
      final payment = _parsePayment(response);
      _paymentsBySale[saleId] = payment;
      return payment;
    } catch (error) {
      throw _mapFailure(error);
    }
  }

  @override
  Future<PaymentData> getPayment(int paymentId) async {
    try {
      final payment = _parsePayment(
        await _apiService.get('/api/payments/$paymentId'),
      );
      _paymentsBySale[payment.saleId] = payment;
      return payment;
    } catch (error) {
      throw _mapFailure(error);
    }
  }

  @override
  Future<StripeCheckoutData> createCheckoutSession(int paymentId) async {
    try {
      final response = await _apiService.post(
        '/api/payments/$paymentId/stripe/checkout-session',
        {'return_target': 'mobile'},
      );
      if (response is! Map<String, dynamic> || response['success'] != true) {
        throw const FormatException('Respuesta de Checkout inválida.');
      }
      final data = response['data'];
      if (data is! Map<String, dynamic>) {
        throw const FormatException('Datos de Checkout ausentes.');
      }
      final checkout = StripeCheckoutData.fromJson(data);
      if (checkout.payment.paymentId != paymentId ||
          checkout.payment.method != 'TARJETA' ||
          checkout.payment.provider != 'STRIPE' ||
          checkout.payment.environment != 'TEST' ||
          checkout.payment.state != 'PENDIENTE' ||
          !checkout.sessionId.startsWith('cs_test_') ||
          checkout.payment.externalReference != checkout.sessionId ||
          !_isStripeUrl(checkout.url)) {
        throw const PaymentFailure(
          PaymentFailureType.invalidResponse,
          'Stripe devolvió una sesión de Checkout no válida.',
        );
      }
      _paymentsBySale[checkout.payment.saleId] = checkout.payment;
      return checkout;
    } catch (error) {
      throw _mapFailure(error);
    }
  }

  @override
  Future<PaymentData> syncStripe(int paymentId) async {
    try {
      final payment = _parsePayment(
        await _apiService.post('/api/payments/$paymentId/stripe/sync', {}),
      );
      _paymentsBySale[payment.saleId] = payment;
      return payment;
    } catch (error) {
      throw _mapFailure(error);
    }
  }

  PaymentData _parsePayment(dynamic response) {
    if (response is! Map<String, dynamic> || response['success'] != true) {
      throw const FormatException('Respuesta de pago inválida.');
    }
    final data = response['data'];
    if (data is! Map<String, dynamic>) {
      throw const FormatException('Datos de pago ausentes.');
    }
    return PaymentData.fromJson(data);
  }

  bool _isStripeUrl(String value) {
    final uri = Uri.tryParse(value);
    return uri != null &&
        uri.scheme == 'https' &&
        uri.host == 'checkout.stripe.com' &&
        uri.userInfo.isEmpty;
  }

  PaymentFailure _mapFailure(Object error) {
    if (error is PaymentFailure) return error;
    if (error is ApiTimeoutException) {
      return const PaymentFailure(
        PaymentFailureType.timeout,
        'La solicitud tardó demasiado. Inténtalo nuevamente.',
      );
    }
    if (error is ApiNetworkException || error is SocketException) {
      return const PaymentFailure(
        PaymentFailureType.connection,
        'No pudimos conectar con FashionStore. Revisa tu conexión.',
      );
    }
    if (error is ApiInvalidResponseException || error is FormatException) {
      return const PaymentFailure(
        PaymentFailureType.invalidResponse,
        'Recibimos una respuesta inesperada del pago.',
      );
    }
    if (error is ApiException) {
      final type = switch (error.statusCode) {
        401 => PaymentFailureType.unauthorized,
        403 => PaymentFailureType.forbidden,
        404 => PaymentFailureType.notFound,
        409 => PaymentFailureType.conflict,
        422 => PaymentFailureType.invalidData,
        503 => PaymentFailureType.unavailable,
        _ => PaymentFailureType.server,
      };
      final message = switch (type) {
        PaymentFailureType.unauthorized => 'Tu sesión expiró. Inicia sesión nuevamente.',
        PaymentFailureType.forbidden => 'No tienes permiso para pagar esta venta.',
        PaymentFailureType.notFound => 'No se encontró la venta o el pago solicitado.',
        PaymentFailureType.conflict => 'El pago ya fue resuelto o tiene un conflicto. Consulta el mismo intento.',
        PaymentFailureType.invalidData => 'Este pago no está disponible para la venta.',
        PaymentFailureType.unavailable => 'Stripe no está disponible. Conservamos el mismo intento para reintentar.',
        _ => 'No pudimos verificar el pago. Inténtalo nuevamente.',
      };
      return PaymentFailure(type, message);
    }
    return const PaymentFailure(
      PaymentFailureType.server,
      'No pudimos verificar el pago. Inténtalo nuevamente.',
    );
  }

  void close() {
    if (_ownsApiService) _apiService.close();
  }
}
