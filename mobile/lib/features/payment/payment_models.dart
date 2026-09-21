enum PaymentState {
  pending,
  approved,
  canceled,
}

class PaymentData {
  const PaymentData({
    required this.paymentId,
    required this.saleId,
    required this.method,
    required this.provider,
    required this.environment,
    required this.state,
    required this.amount,
    required this.currency,
    required this.externalReference,
    required this.idempotencyKey,
    required this.saleState,
  });

  final int paymentId;
  final int saleId;
  final String method;
  final String provider;
  final String environment;
  final String state;
  final double amount;
  final String currency;
  final String? externalReference;
  final String idempotencyKey;
  final String saleState;

  PaymentState get uiState {
    if (state == 'APROBADO' || saleState == 'COMPLETADA') {
      return PaymentState.approved;
    }
    if (state == 'CANCELADO') return PaymentState.canceled;
    return PaymentState.pending;
  }

  factory PaymentData.fromJson(Map<String, dynamic> json) => PaymentData(
    paymentId: _requiredInt(json, 'id_pago'),
    saleId: _requiredInt(json, 'id_venta'),
    method: _requiredString(json, 'medio'),
    provider: _requiredString(json, 'proveedor'),
    environment: _requiredString(json, 'entorno'),
    state: _requiredString(json, 'estado'),
    amount: _requiredDouble(json, 'monto'),
    currency: _requiredString(json, 'moneda'),
    externalReference: _optionalString(json['referencia_externa']),
    idempotencyKey: _requiredString(json, 'clave_idempotencia'),
    saleState: _requiredString(json, 'estado_venta'),
  );
}

class StripeCheckoutData {
  const StripeCheckoutData({
    required this.payment,
    required this.sessionId,
    required this.url,
  });

  final PaymentData payment;
  final String sessionId;
  final String url;

  factory StripeCheckoutData.fromJson(Map<String, dynamic> json) {
    final payment = json['payment'];
    if (payment is! Map<String, dynamic>) {
      throw const FormatException('Pago ausente en Checkout.');
    }
    return StripeCheckoutData(
      payment: PaymentData.fromJson(payment),
      sessionId: _requiredString(json, 'session_id'),
      url: _requiredString(json, 'url'),
    );
  }
}

enum PaymentFailureType {
  unauthorized,
  forbidden,
  notFound,
  conflict,
  invalidData,
  unavailable,
  timeout,
  connection,
  invalidResponse,
  server,
}

class PaymentFailure implements Exception {
  const PaymentFailure(this.type, this.message);

  final PaymentFailureType type;
  final String message;

  bool get invalidatesSession => type == PaymentFailureType.unauthorized;
}

int _requiredInt(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is int) return value;
  throw FormatException('$key inválido.');
}

double _requiredDouble(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is num) return value.toDouble();
  if (value is String) {
    final parsed = double.tryParse(value);
    if (parsed != null) return parsed;
  }
  throw FormatException('$key inválido.');
}

String _requiredString(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('$key inválido.');
  }
  return value.trim();
}

String? _optionalString(Object? value) {
  if (value == null) return null;
  if (value is! String) throw const FormatException('Texto inválido.');
  return value.trim().isEmpty ? null : value.trim();
}
