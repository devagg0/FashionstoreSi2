class ReturnLine {
  const ReturnLine({
    required this.detailId,
    required this.variantId,
    required this.quantity,
    required this.quantityToRefund,
    required this.refundAmount,
  });

  final int detailId;
  final int variantId;
  final int quantity;
  final int quantityToRefund;
  final double refundAmount;

  factory ReturnLine.fromJson(Map<String, dynamic> json) => ReturnLine(
    detailId: _int(json, 'id_detalle_devolucion'),
    variantId: _int(json, 'id_variante_producto'),
    quantity: _int(json, 'cantidad'),
    quantityToRefund: _int(json, 'cantidad_reintegrar'),
    refundAmount: _double(json, 'importe_restitucion'),
  );
}

class ReturnRequestData {
  const ReturnRequestData({
    required this.returnId,
    required this.saleId,
    required this.type,
    required this.state,
    required this.reason,
    required this.createdAt,
    required this.lines,
    required this.refunds,
  });

  final int returnId;
  final int saleId;
  final String type;
  final String state;
  final String reason;
  final DateTime? createdAt;
  final List<ReturnLine> lines;
  final List<ReturnRefund> refunds;

  factory ReturnRequestData.fromJson(Map<String, dynamic> json) => ReturnRequestData(
    returnId: _int(json, 'id_devolucion'),
    saleId: _int(json, 'id_venta'),
    type: _string(json, 'tipo'),
    state: _string(json, 'estado'),
    reason: _string(json, 'motivo'),
    createdAt: _date(json['created_at']),
    lines: _list(json, 'lineas', ReturnLine.fromJson),
    refunds: _list(json, 'reembolsos', ReturnRefund.fromJson),
  );
}

class ReturnRefund {
  const ReturnRefund({
    required this.refundId,
    required this.paymentId,
    required this.state,
    required this.amount,
  });

  final int refundId;
  final int paymentId;
  final String state;
  final double amount;

  factory ReturnRefund.fromJson(Map<String, dynamic> json) => ReturnRefund(
    refundId: _int(json, 'id_reembolso'),
    paymentId: _int(json, 'id_pago'),
    state: _string(json, 'estado'),
    amount: _double(json, 'monto'),
  );
}

enum ReturnFailureType {
  unauthorized,
  forbidden,
  notFound,
  conflict,
  invalidData,
  timeout,
  connection,
  invalidResponse,
  server,
}

class ReturnFailure implements Exception {
  const ReturnFailure(this.type, this.message);

  final ReturnFailureType type;
  final String message;

  bool get invalidatesSession => type == ReturnFailureType.unauthorized;
}

int _int(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is int) return value;
  throw FormatException('$key inválido.');
}

double _double(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is num) return value.toDouble();
  if (value is String) {
    final parsed = double.tryParse(value);
    if (parsed != null) return parsed;
  }
  throw FormatException('$key inválido.');
}

String _string(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is! String || value.trim().isEmpty) throw FormatException('$key inválido.');
  return value.trim();
}

DateTime? _date(Object? value) => value is String ? DateTime.tryParse(value) : null;

List<T> _list<T>(Map<String, dynamic> json, String key, T Function(Map<String, dynamic>) parser) {
  final value = json[key];
  if (value is! List) throw FormatException('$key inválido.');
  return value.map((item) {
    if (item is! Map<String, dynamic>) throw const FormatException('Item inválido.');
    return parser(item);
  }).toList(growable: false);
}
